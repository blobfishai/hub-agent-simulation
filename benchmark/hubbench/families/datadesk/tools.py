"""DataDesk provider-shaped tools over the family's SQLite world.

Read tools return warehouse-catalog, pipeline, feed, and reconciliation records
in provider shapes (dbt-style manifests, run logs, delivery logs, control
totals); write tools persist to the domain tables, refresh the affected
records, and record the exact payload for the sealed contract.  There is no
LLM anywhere here.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from ...engine.families import ToolSpec
from ...engine.validation import integer, obj, string
from ...engine.world import World

WINDOWS = {"NIGHT": ("01:00:00", "05:00:00"), "DAY": ("13:00:00", "17:00:00")}
ROW_UNIT = "ROW"


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #


def _model(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "resourceType": "Model",
        "model_id": row["model_id"],
        "name": row["name"],
        "unique_id": f"model.tidewater.{row['name']}",
        "layer": row["layer"],
        "schema": row["schema_name"],
        "materialization": row["materialization"],
        "owner": row["owner"],
        "status": row["status"],
        "description": row.get("description"),
    }


def _slot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "resourceType": "WarehouseWindow",
        "id": row["slot_id"],
        "cluster": row["cluster_id"],
        "serviceDate": row["service_date"],
        "window": row["window_name"],
        "start": f"{row['service_date']}T{row['start_time']}",
        "end": f"{row['service_date']}T{row['end_time']}",
        "status": row["status"],
        "holdReason": row.get("hold_reason"),
        "job": row.get("job_id"),
    }


def _schedule(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row)


# --------------------------------------------------------------------------- #
# Warehouse catalog
# --------------------------------------------------------------------------- #


def models_search(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("model_id"):
        rows = world.all("SELECT * FROM models WHERE model_id = ? ORDER BY model_id", (args["model_id"],))
    elif args.get("name"):
        rows = world.all("SELECT * FROM models WHERE instr(lower(name), lower(?)) > 0 ORDER BY model_id", (args["name"],))
    else:
        raise ValueError("model_id or name is required")
    return {"models": [_model(row) for row in rows], "total": len(rows)}


def models_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _model(world.one("SELECT * FROM models WHERE model_id = ?", (args["model_id"],), missing=f"model {args['model_id']} not found"))


def lineage_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT model_id FROM models WHERE model_id = ?", (args["model_id"],), missing=f"model {args['model_id']} not found")
    parents = world.all(
        "SELECT m.*, l.relationship FROM model_lineage l JOIN models m ON m.model_id = l.parent_model_id WHERE l.child_model_id = ? ORDER BY m.model_id",
        (args["model_id"],),
    )
    children = world.all(
        "SELECT m.*, l.relationship FROM model_lineage l JOIN models m ON m.model_id = l.child_model_id WHERE l.parent_model_id = ? ORDER BY m.model_id",
        (args["model_id"],),
    )
    return {
        "model_id": args["model_id"],
        "parents": [{**_model(row), "relationship": row["relationship"]} for row in parents],
        "children": [{**_model(row), "relationship": row["relationship"]} for row in children],
    }


def sla_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one(
        "SELECT * FROM sla_targets WHERE model_id = ? AND status = 'ACTIVE' ORDER BY sla_id",
        (args["model_id"],),
        missing=f"no active freshness SLA for {args['model_id']}",
    )
    return dict(row)


def clusters_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return {"clusters": world.all("SELECT * FROM clusters ORDER BY cluster_id")}


def slots_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses = ["service_date >= ?", "service_date <= ?"]
    params: list[Any] = [args["start_date"], args["end_date"]]
    if args.get("cluster_id"):
        clauses.append("cluster_id = ?")
        params.append(args["cluster_id"])
    if args.get("status"):
        clauses.append("status = ?")
        params.append(args["status"])
    rows = world.all(
        f"SELECT * FROM warehouse_slots WHERE {' AND '.join(clauses)} ORDER BY service_date, cluster_id, start_time",
        params,
    )
    return {"slots": [_slot(row) for row in rows]}


# --------------------------------------------------------------------------- #
# Pipelines
# --------------------------------------------------------------------------- #


def runs_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = ["model_id = ?"], [args["model_id"]]
    if args.get("partition_start"):
        clauses.append("partition_date >= ?")
        params.append(args["partition_start"])
    if args.get("partition_end"):
        clauses.append("partition_date <= ?")
        params.append(args["partition_end"])
    if args.get("status"):
        clauses.append("status = ?")
        params.append(args["status"])
    if args.get("trigger"):
        clauses.append("trigger = ?")
        params.append(args["trigger"])
    rows = world.all(f"SELECT * FROM pipeline_runs WHERE {' AND '.join(clauses)} ORDER BY partition_date, run_id", params)
    return {"model_id": args["model_id"], "runs": rows}


def runs_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM pipeline_runs WHERE run_id = ?", (args["run_id"],), missing=f"run {args['run_id']} not found"))


def schedules_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _schedule(world.one("SELECT * FROM run_schedules WHERE schedule_id = ?", (args["schedule_id"],), missing=f"schedule {args['schedule_id']} not found"))


def _split_datetime(value: str, label: str) -> tuple[str, str]:
    if len(value) != 19 or value[10] != "T":
        raise ValueError(f"{label} must be YYYY-MM-DDTHH:MM:SS")
    date.fromisoformat(value[:10])
    return value[:10], value[11:]


def _windows_for_interval(world: World, cluster_id: str, start: str, end: str) -> list[dict[str, Any]]:
    start_date, start_time = _split_datetime(start, "start_time")
    end_date, end_time = _split_datetime(end, "end_time")
    if start_date != end_date:
        raise ValueError("a warehouse reservation must start and end on the same service date")
    if start_time >= end_time:
        raise ValueError("start_time must precede end_time")
    rows = world.all("SELECT * FROM warehouse_slots WHERE cluster_id = ? AND service_date = ? ORDER BY start_time", (cluster_id, start_date))
    covering = [row for row in rows if row["start_time"] < end_time and row["end_time"] > start_time]
    if not covering:
        raise ValueError(f"no {cluster_id} batch window covers {start} - {end}")
    if start_time < min(row["start_time"] for row in covering) or end_time > max(row["end_time"] for row in covering):
        raise ValueError(f"{start} - {end} falls outside the {cluster_id} batch windows")
    return covering


def _require_free(windows: list[dict[str, Any]], *, holder: str | None = None) -> None:
    for row in windows:
        if row["status"] == "free":
            continue
        if holder and row.get("job_id") == holder:
            continue
        raise ValueError(
            f"{row['slot_id']} is {row['status']}: {row.get('hold_reason') or 'not available'}; protected and blocked windows cannot be displaced"
        )


def _claim(world: World, tool: str, windows: list[dict[str, Any]], job_id: str) -> None:
    for row in windows:
        world.connection.execute("UPDATE warehouse_slots SET status = 'busy', hold_reason = 'reserved', job_id = ? WHERE slot_id = ?", (job_id, row["slot_id"]))
        world.audit(tool, "warehouse_slots", row["slot_id"], "update", {"status": "busy", "job_id": job_id})


def _release(world: World, tool: str, job_id: str) -> None:
    for row in world.all("SELECT slot_id FROM warehouse_slots WHERE job_id = ?", (job_id,)):
        world.connection.execute("UPDATE warehouse_slots SET status = 'free', hold_reason = NULL, job_id = NULL WHERE slot_id = ?", (row["slot_id"],))
        world.audit(tool, "warehouse_slots", row["slot_id"], "update", {"status": "free", "job_id": None})


def _active_cluster(world: World, cluster_id: str) -> dict[str, Any]:
    cluster = world.one("SELECT * FROM clusters WHERE cluster_id = ?", (cluster_id,), missing=f"cluster {cluster_id} not found")
    if cluster["status"] != "ACTIVE":
        raise ValueError(f"{cluster_id} is {cluster['status']}: {cluster.get('status_note') or ''}".strip())
    return cluster


def _weekday_partitions(start: str, end: str) -> int:
    day = date.fromisoformat(start)
    last = date.fromisoformat(end)
    count = 0
    while day <= last:
        if day.weekday() < 5:
            count += 1
        day = date.fromordinal(day.toordinal() + 1)
    return count


def backfills_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM backfill_jobs WHERE job_id = ?", (args["job_id"],), missing=f"backfill job {args['job_id']} not found"))


def backfills_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "pipelines.backfills.create"
    model = world.one("SELECT * FROM models WHERE model_id = ?", (args["model_id"],), missing=f"model {args['model_id']} not found")
    if model["status"] != "ACTIVE":
        raise ValueError(f"model {args['model_id']} is {model['status']} and cannot be backfilled")
    if args["partition_start"] > args["partition_end"]:
        raise ValueError("partition_start must not follow partition_end")
    cluster = _active_cluster(world, args["cluster_id"])
    if not cluster["backfill_capable"]:
        raise ValueError(f"{args['cluster_id']} is not backfill-capable: {cluster.get('status_note') or 'no service-account write grants'}")
    windows = _windows_for_interval(world, args["cluster_id"], args["start_time"], args["end_time"])
    _require_free(windows)
    job_id = world.next_id("backfill_jobs", "job_id", "BF-")
    row = {
        "job_id": job_id,
        "model_id": args["model_id"],
        "partition_start": args["partition_start"],
        "partition_end": args["partition_end"],
        "partitions": _weekday_partitions(args["partition_start"], args["partition_end"]),
        "cluster_id": args["cluster_id"],
        "start_time": args["start_time"],
        "end_time": args["end_time"],
        "status": "SCHEDULED",
        "description": args.get("description"),
        "requested_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO backfill_jobs (job_id, model_id, partition_start, partition_end, partitions, cluster_id, start_time, end_time, status, description, requested_by, created_at, revision) "
        "VALUES (:job_id, :model_id, :partition_start, :partition_end, :partitions, :cluster_id, :start_time, :end_time, :status, :description, :requested_by, :created_at, :revision)",
        row,
    )
    world.audit(tool, "backfill_jobs", job_id, "insert", row)
    _claim(world, tool, windows, job_id)
    world.record_mutation(tool, "backfill_jobs", job_id, "SCHEDULED", args)
    return dict(row)


def schedules_update(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "pipelines.schedules.update"
    current = world.one("SELECT * FROM run_schedules WHERE schedule_id = ?", (args["schedule_id"],), missing=f"schedule {args['schedule_id']} not found")
    if current["status"] in {"cancelled", "completed"}:
        raise ValueError(f"schedule {args['schedule_id']} is {current['status']} and cannot be changed")
    changes = {key: args[key] for key in ("cluster_id", "start_time", "end_time", "status") if key in args}
    if not changes:
        raise ValueError("no change requested")
    updated = {**current, **changes}
    new_status = updated["status"]
    if new_status == "cancelled":
        _release(world, tool, current["schedule_id"])
    else:
        if any(key in changes for key in ("cluster_id", "start_time", "end_time")) or current["status"] != "scheduled":
            if not (updated.get("cluster_id") and updated.get("start_time") and updated.get("end_time")):
                raise ValueError("windowing a schedule needs cluster_id, start_time, and end_time")
            _active_cluster(world, updated["cluster_id"])
            windows = _windows_for_interval(world, updated["cluster_id"], updated["start_time"], updated["end_time"])
            _require_free(windows, holder=current["schedule_id"])
            _release(world, tool, current["schedule_id"])
            _claim(world, tool, windows, current["schedule_id"])
            if new_status not in {"scheduled", "pending"}:
                raise ValueError(f"unsupported status transition to {new_status}")
    updated["revision"] = int(current["revision"]) + 1
    updated["last_updated"] = world.clock()
    world.connection.execute(
        "UPDATE run_schedules SET cluster_id = :cluster_id, start_time = :start_time, end_time = :end_time, status = :status, revision = :revision, last_updated = :last_updated WHERE schedule_id = :schedule_id",
        updated,
    )
    world.audit(tool, "run_schedules", current["schedule_id"], "update", changes)
    world.record_mutation(tool, "run_schedules", current["schedule_id"], new_status, args, revision=updated["revision"])
    return _schedule(updated)


# --------------------------------------------------------------------------- #
# Feeds and vendor confirmations
# --------------------------------------------------------------------------- #


def feeds_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("vendor_id"):
        rows = world.all("SELECT * FROM feeds WHERE vendor_id = ? ORDER BY feed_id", (args["vendor_id"],))
    else:
        rows = world.all("SELECT * FROM feeds ORDER BY feed_id")
    return {"feeds": rows}


def feeds_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM feeds WHERE feed_id = ?", (args["feed_id"],), missing=f"feed {args['feed_id']} not found")
    vendor = world.one("SELECT * FROM vendors WHERE vendor_id = ?", (row["vendor_id"],))
    return {**row, "vendor_name": vendor["name"]}


def deliveries_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = ["feed_id = ?"], [args["feed_id"]]
    if args.get("start_date"):
        clauses.append("business_date >= ?")
        params.append(args["start_date"])
    if args.get("end_date"):
        clauses.append("business_date <= ?")
        params.append(args["end_date"])
    if args.get("status"):
        clauses.append("status = ?")
        params.append(args["status"])
    rows = world.all(f"SELECT * FROM feed_deliveries WHERE {' AND '.join(clauses)} ORDER BY business_date, delivery_id", params)
    return {"feed_id": args["feed_id"], "deliveries": rows}


def confirmations_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("feed_id", "vendor_id"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"confirmations": world.all(f"SELECT * FROM vendor_confirmations {where} ORDER BY confirmation_id", params)}


def confirmations_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM vendor_confirmations WHERE confirmation_id = ?", (args["confirmation_id"],), missing=f"confirmation {args['confirmation_id']} not found")
    vendor = world.one("SELECT * FROM vendors WHERE vendor_id = ?", (row["vendor_id"],))
    return {**row, "vendor_name": vendor["name"]}


# --------------------------------------------------------------------------- #
# Reconciliation
# --------------------------------------------------------------------------- #


def controls_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("model_id"):
        rows = world.all("SELECT * FROM recon_controls WHERE model_id = ? ORDER BY control_id", (args["model_id"],))
    else:
        rows = world.all("SELECT * FROM recon_controls ORDER BY control_id")
    return {"controls": rows}


def controls_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM recon_controls WHERE control_id = ?", (args["control_id"],), missing=f"control {args['control_id']} not found"))


def adjustments_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM adjustment_entries WHERE entry_id = ?", (args["entry_id"],), missing=f"adjustment entry {args['entry_id']} not found"))


def adjustments_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "recon.adjustments.create"
    model = world.one("SELECT * FROM models WHERE model_id = ?", (args["model_id"],), missing=f"model {args['model_id']} not found")
    if model["status"] != "ACTIVE":
        raise ValueError(f"model {args['model_id']} is {model['status']}; adjustments post only to active certified models")
    if args["period_start"] > args["period_end"]:
        raise ValueError("period_start must not follow period_end")
    if not args["reason"].strip():
        raise ValueError("reason is required")
    approval = world.one("SELECT * FROM approvals WHERE approval_id = ?", (args["approval_id"],), missing=f"approval {args['approval_id']} not found")
    if approval["status"] != "APPROVED":
        raise ValueError(f"approval {args['approval_id']} is {approval['status']}")
    scope = json.loads(approval["scope_json"])
    if scope.get("model_id") and scope["model_id"] != args["model_id"]:
        raise ValueError(f"approval {args['approval_id']} covers {scope['model_id']}, not {args['model_id']}")
    if scope.get("max_rows") is not None and args["rows"] > int(scope["max_rows"]):
        raise ValueError(f"approval {args['approval_id']} covers at most {scope['max_rows']} rows; {args['rows']} exceeds the signed scope")
    control = world.connection.execute(
        "SELECT control_id FROM recon_controls WHERE model_id = ? AND period_start <= ? AND period_end >= ? AND status = 'PUBLISHED' ORDER BY control_id",
        (args["model_id"], args["period_end"], args["period_start"]),
    ).fetchone()
    if control is None:
        raise ValueError(f"no published control total covers {args['model_id']} for {args['period_start']}..{args['period_end']}; adjustments without a covering control are rejected")
    entry_id = world.next_id("adjustment_entries", "entry_id", "ADJ-")
    row = {
        "entry_id": entry_id,
        "model_id": args["model_id"],
        "period_start": args["period_start"],
        "period_end": args["period_end"],
        "direction": args["direction"],
        "rows": args["rows"],
        "reason": args["reason"],
        "approval_id": args["approval_id"],
        "status": "POSTED",
        "created_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO adjustment_entries (entry_id, model_id, period_start, period_end, direction, rows, reason, approval_id, status, created_by, created_at, revision) "
        "VALUES (:entry_id, :model_id, :period_start, :period_end, :direction, :rows, :reason, :approval_id, :status, :created_by, :created_at, :revision)",
        row,
    )
    world.audit(tool, "adjustment_entries", entry_id, "insert", row)
    world.record_mutation(tool, "adjustment_entries", entry_id, "POSTED", args)
    return dict(row)


# --------------------------------------------------------------------------- #
# Approvals and collaboration surfaces
# --------------------------------------------------------------------------- #


def approvals_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("q"):
        rows = world.all("SELECT * FROM approvals WHERE instr(lower(subject), lower(?)) > 0 OR instr(lower(scope_json), lower(?)) > 0 ORDER BY approval_id", (args["q"], args["q"]))
    else:
        rows = world.all("SELECT * FROM approvals ORDER BY approval_id")
    return {"approvals": [{**row, "scope": json.loads(row["scope_json"])} for row in rows]}


def approvals_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM approvals WHERE approval_id = ?", (args["approval_id"],), missing=f"approval {args['approval_id']} not found")
    approver = world.one("SELECT * FROM users WHERE user_id = ?", (row["approver_id"],), missing="approver not found")
    return {**row, "scope": json.loads(row["scope_json"]), "approver": {"user_id": approver["user_id"], "display_name": approver["display_name"], "role": approver["role"]}}


def messages_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    query = args["q"].strip().strip('"')
    rows = world.all(
        "SELECT message_id, thread_id, channel, sender, subject, sent_at, labels FROM messages WHERE instr(subject, ?) > 0 OR instr(body, ?) > 0 OR instr(labels, ?) > 0 ORDER BY sent_at, message_id",
        (query, query, query),
    )
    limit = int(args.get("max_results", 20))
    return {"messages": [{"id": row["message_id"], "thread_id": row["thread_id"], "channel": row["channel"], "from": row["sender"], "subject": row["subject"], "sent_at": row["sent_at"], "labels": row["labels"]} for row in rows[:limit]]}


def messages_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM messages WHERE message_id = ?", (args["message_id"],), missing=f"message {args['message_id']} not found")
    return {
        "id": row["message_id"],
        "thread_id": row["thread_id"],
        "channel": row["channel"],
        "from": row["sender"],
        "to": row["recipients"],
        "subject": row["subject"],
        "sent_at": row["sent_at"],
        "body": row["body"],
        "attachments": json.loads(row["attachments_json"]),
        "labels": row["labels"],
    }


def chat_threads_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    query = args["q"].strip().strip('"')
    rows = world.all("SELECT thread_id, channel, title FROM chat_threads WHERE instr(title, ?) > 0 OR instr(messages_json, ?) > 0 ORDER BY thread_id", (query, query))
    return {"threads": rows}


def chat_threads_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM chat_threads WHERE thread_id = ?", (args["thread_id"],), missing=f"thread {args['thread_id']} not found")
    return {"thread_id": row["thread_id"], "channel": row["channel"], "title": row["title"], "messages": json.loads(row["messages_json"])}


def drive_files_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    query = args["q"].strip().strip('"')
    rows = world.all(
        "SELECT file_id, name, mime_type, modified_time, folder FROM drive_files WHERE instr(name, ?) > 0 OR instr(folder, ?) > 0 OR instr(content, ?) > 0 ORDER BY folder, name",
        (query, query, query),
    )
    return {"files": [{"id": row["file_id"], "name": row["name"], "mimeType": row["mime_type"], "modifiedTime": row["modified_time"], "folder": row["folder"]} for row in rows]}


def drive_files_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT file_id, name, mime_type, modified_time, folder, sha256 FROM drive_files WHERE file_id = ?", (args["file_id"],), missing=f"file {args['file_id']} not found")
    return {"id": row["file_id"], "name": row["name"], "mimeType": row["mime_type"], "modifiedTime": row["modified_time"], "folder": row["folder"], "sha256": row["sha256"]}


def drive_files_export(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM drive_files WHERE file_id = ?", (args["file_id"],), missing=f"file {args['file_id']} not found")
    return {"file_id": row["file_id"], "name": row["name"], "mime_type": row["mime_type"], "content": row["content"]}


def drafts_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "notes.drafts.create"
    if not args["recipient"].strip() or not args["body"].strip():
        raise ValueError("recipient and body are required")
    draft_id = world.next_id("note_drafts", "draft_id", "DRAFT-")
    row = {
        "draft_id": draft_id,
        "recipient": args["recipient"],
        "subject": args["subject"],
        "body": args["body"],
        "related_model_id": args.get("related_model_id"),
        "related_case": args.get("related_case"),
        "created_at": world.clock(),
        "status": "DRAFT",
    }
    world.connection.execute(
        "INSERT INTO note_drafts (draft_id, recipient, subject, body, related_model_id, related_case, created_at, status) "
        "VALUES (:draft_id, :recipient, :subject, :body, :related_model_id, :related_case, :created_at, :status)",
        row,
    )
    world.audit(tool, "note_drafts", draft_id, "insert", row)
    world.record_mutation(tool, "note_drafts", draft_id, "DRAFT", args)
    return dict(row)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

DATETIME = "ISO local date-time, YYYY-MM-DDTHH:MM:SS"

TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec("warehouse.models.search", "Search the model catalog by immutable model id or by name substring.", obj({"model_id": string(), "name": string("name substring")}), "read", models_search, "dbt-style model catalog search"),
    ToolSpec("warehouse.models.get", "Read one catalog model: layer, schema, materialization, owner, status.", obj({"model_id": string()}, ["model_id"]), "read", models_get, "dbt-style model catalog record"),
    ToolSpec("warehouse.lineage.get", "Read the lineage of one model: parent sources and child consumers with relationship type.", obj({"model_id": string()}, ["model_id"]), "read", lineage_get, "dbt-style lineage graph"),
    ToolSpec("warehouse.sla.get", "Read the active freshness SLA for a model: max staleness, refresh deadline, escalation, business reference.", obj({"model_id": string()}, ["model_id"]), "read", sla_get, "freshness SLA register"),
    ToolSpec("warehouse.clusters.list", "List warehouse compute clusters with status and backfill capability.", obj({}), "read", clusters_list, "warehouse cluster roster"),
    ToolSpec("warehouse.slots.list", "List warehouse batch windows between two dates with free / busy / protected / blocked status.", obj({"start_date": string("ISO date"), "end_date": string("ISO date"), "cluster_id": string(), "status": string()}, ["start_date", "end_date"]), "read", slots_list, "warehouse window calendar"),
    ToolSpec("pipelines.runs.list", "List pipeline runs for a model by partition window, status, or trigger, with durations and rows processed.", obj({"model_id": string(), "partition_start": string("ISO date"), "partition_end": string("ISO date"), "status": string(), "trigger": string()}, ["model_id"]), "read", runs_list, "pipeline run log"),
    ToolSpec("pipelines.runs.get", "Read one pipeline run.", obj({"run_id": string()}, ["run_id"]), "read", runs_get, "pipeline run log"),
    ToolSpec("pipelines.schedules.get", "Read one run schedule with cluster, window, status, and revision.", obj({"schedule_id": string()}, ["schedule_id"]), "read", schedules_get, "pipeline schedule record"),
    ToolSpec(
        "pipelines.schedules.update",
        "Window, move, or cancel a run schedule. Every batch window the interval touches must be free; protected and blocked windows are never displaced; the record revision increments.",
        obj(
            {"schedule_id": string(), "cluster_id": string(), "start_time": string(DATETIME), "end_time": string(DATETIME), "status": {"type": "string", "enum": ["scheduled", "pending", "cancelled"]}},
            ["schedule_id"],
        ),
        "write",
        schedules_update,
        "pipeline schedule update",
        idempotent=False,
    ),
    ToolSpec(
        "pipelines.backfills.create",
        "Schedule a backfill job on a backfill-capable cluster. Every batch window the interval touches must be free; protected and blocked windows are never displaced.",
        obj(
            {"model_id": string(), "partition_start": string("ISO date"), "partition_end": string("ISO date"), "cluster_id": string(), "start_time": string(DATETIME), "end_time": string(DATETIME), "description": string()},
            ["model_id", "partition_start", "partition_end", "cluster_id", "start_time", "end_time"],
        ),
        "write",
        backfills_create,
        "pipeline backfill job",
        idempotent=False,
    ),
    ToolSpec("pipelines.backfills.get", "Read one backfill job.", obj({"job_id": string()}, ["job_id"]), "read", backfills_get, "pipeline backfill job"),
    ToolSpec("feeds.list", "List source feeds, optionally by vendor.", obj({"vendor_id": string()}), "read", feeds_list, "source feed registry"),
    ToolSpec("feeds.get", "Read one source feed with its vendor.", obj({"feed_id": string()}, ["feed_id"]), "read", feeds_get, "source feed registry"),
    ToolSpec("feeds.deliveries.list", "List feed delivery log entries by business-date window and status: files, rows received, invalid, duplicate, and late counts.", obj({"feed_id": string(), "start_date": string("ISO date"), "end_date": string("ISO date"), "status": string()}, ["feed_id"]), "read", deliveries_list, "feed delivery log"),
    ToolSpec("feeds.confirmations.list", "List vendor redelivery confirmations.", obj({"feed_id": string(), "vendor_id": string()}), "read", confirmations_list, "vendor redelivery confirmation"),
    ToolSpec("feeds.confirmations.get", "Read one vendor redelivery confirmation: scope, standard and expedited redelivery dates, fee, validity.", obj({"confirmation_id": string()}, ["confirmation_id"]), "read", confirmations_get, "vendor redelivery confirmation"),
    ToolSpec("recon.controls.list", "List published finance control totals, optionally by model.", obj({"model_id": string()}), "read", controls_list, "finance control total"),
    ToolSpec("recon.controls.get", "Read one published finance control total.", obj({"control_id": string()}, ["control_id"]), "read", controls_get, "finance control total"),
    ToolSpec(
        "recon.adjustments.create",
        "Post a reconciling adjustment entry against a certified model. The entry must stay inside the signed approval's model and row maximum and a published control total must cover the period.",
        obj(
            {
                "model_id": string(),
                "period_start": string("ISO date"),
                "period_end": string("ISO date"),
                "direction": {"type": "string", "enum": ["add", "remove"]},
                "rows": integer(minimum=1),
                "reason": string(),
                "approval_id": string(),
            },
            ["model_id", "period_start", "period_end", "direction", "rows", "reason", "approval_id"],
        ),
        "write",
        adjustments_create,
        "reconciliation adjustment entry",
        idempotent=False,
    ),
    ToolSpec("recon.adjustments.get", "Read one adjustment entry.", obj({"entry_id": string()}, ["entry_id"]), "read", adjustments_get, "reconciliation adjustment entry"),
    ToolSpec("approvals.list", "List approval records, optionally by keyword.", obj({"q": string()}), "read", approvals_list, "approval workflow record"),
    ToolSpec("approvals.get", "Read one approval record with its exact scope and approver.", obj({"approval_id": string()}, ["approval_id"]), "read", approvals_get, "approval workflow record"),
    ToolSpec("messages.list", "Search mailbox messages by keyword (subject, body, labels).", obj({"q": string(), "max_results": integer(minimum=1)}, ["q"]), "read", messages_list, "mailbox search"),
    ToolSpec("messages.get", "Read one message with body and attachment list.", obj({"message_id": string()}, ["message_id"]), "read", messages_get, "mailbox message"),
    ToolSpec("chat.threads.list", "Search team chat threads by keyword.", obj({"q": string()}, ["q"]), "read", chat_threads_list, "team chat search"),
    ToolSpec("chat.threads.get", "Read one team chat thread.", obj({"thread_id": string()}, ["thread_id"]), "read", chat_threads_get, "team chat thread"),
    ToolSpec("drive.files.list", "Search shared-drive files by keyword (name, folder, content).", obj({"q": string()}, ["q"]), "read", drive_files_list, "shared drive search"),
    ToolSpec("drive.files.get", "Read shared-drive file metadata.", obj({"file_id": string()}, ["file_id"]), "read", drive_files_get, "shared drive file"),
    ToolSpec("drive.files.export", "Export a shared-drive file as text (spreadsheets as CSV, PDFs as extracted text).", obj({"file_id": string()}, ["file_id"]), "read", drive_files_export, "shared drive export"),
    ToolSpec(
        "notes.drafts.create",
        "Create, but do not send, a stakeholder draft note.",
        obj({"recipient": string(), "subject": string(), "body": string(), "related_model_id": string(), "related_case": string()}, ["recipient", "subject", "body"]),
        "write",
        drafts_create,
        "collaboration draft",
        idempotent=False,
    ),
)

SERVERS = {
    "warehouse": "Warehouse catalog: dbt-style models, lineage, freshness SLAs, clusters, and the batch window calendar.",
    "pipelines": "Pipeline runs, run schedules, and backfill jobs.",
    "feeds": "Source feeds, delivery logs, and vendor redelivery confirmations.",
    "recon": "Finance reconciliation: published control totals and adjustment entries.",
    "approvals": "Approval workflow records with exact scope.",
    "messages": "Mailbox for the data platform team.",
    "chat": "Data platform team chat threads.",
    "drive": "Shared drive holding policies, registers, calendars, and exports.",
    "notes": "Stakeholder draft notes (never sent by the benchmark).",
}

__all__ = ["SERVERS", "TOOLS", "WINDOWS"]
