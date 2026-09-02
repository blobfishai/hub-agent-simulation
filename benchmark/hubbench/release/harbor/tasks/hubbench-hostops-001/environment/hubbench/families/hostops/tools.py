"""HostOps provider-shaped tools over the family's SQLite world.

Read tools return provider-shaped host, scheduler, backup-catalog, build-farm,
and vault records; write tools persist to the domain tables, refresh the
affected records, and record the exact payload for the sealed contract.
There is no LLM anywhere here.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from ...engine.families import ToolSpec
from ...engine.validation import integer, obj, string
from ...engine.world import World

SEGMENT_UNIT = "SEGMENT"


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #


def _service(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "service_id": row["service_id"],
        "code": row["code"],
        "name": row["name"],
        "tier": row["tier"],
        "owner_team": row["owner_team"],
        "primary_engineer": f"Engineer/{row['primary_engineer_id']}" if row.get("primary_engineer_id") else None,
    }


def _metering(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "metering_id": row["metering_id"],
        "service": f"Service/{row['service_id']}",
        "metric": row["metric"],
        "value": row["value"],
        "unit": row["unit"],
        "measured_at": row["measured_at"],
        "status": row["status"],
    }


def _ticket(row: dict[str, Any], artifact_class: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticket_id": row["ticket_id"],
        "status": row["status"],
        "kind": row["kind"],
        "priority": row["priority"],
        "service": f"Service/{row['service_id']}",
        "artifact_class": {"code": row["artifact_class"], "display": artifact_class["display"], "segment_size_gb": artifact_class["segment_size_gb"]},
        "unit_kind": row["unit_kind"],
        "unit_basis": row["unit_basis"],
        "unit_gb": row["unit_gb"],
        "units_in_scope": row["units_in_scope"],
        "scope_note": row["scope_note"],
        "build_minutes": row["build_minutes"],
        "verify_minutes": row["verify_minutes"],
        "opened_at": row["opened_at"],
        "requested_by": f"Engineer/{row['requested_by']}",
        "note": row.get("note") or "",
    }


def _reservation(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["reservation_id"],
        "status": row["status"],
        "description": row.get("description"),
        "start": row.get("start_time"),
        "end": row.get("end_time"),
        "runner": row.get("runner_id"),
        "service": f"Service/{row['service_id']}",
        "ticket": f"Ticket/{row['ticket_id']}" if row.get("ticket_id") else None,
        "meta": {"versionId": str(row["revision"]), "lastUpdated": row["last_updated"]},
    }


def _window(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["window_id"],
        "runner": row["runner_id"],
        "serviceDate": row["service_date"],
        "session": row["session"],
        "start": f"{row['service_date']}T{row['start_time']}",
        "end": f"{row['service_date']}T{row['end_time']}",
        "status": row["status"],
        "holdReason": row.get("hold_reason"),
        "reservation": row.get("reservation_id"),
    }


def _run(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "job": f"Job/{row['job_id']}",
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "status": row["status"],
        "exit_code": row["exit_code"],
        "summary": row["summary"],
    }


# --------------------------------------------------------------------------- #
# CMDB reads
# --------------------------------------------------------------------------- #


def services_search(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("identifier"):
        rows = world.all("SELECT * FROM services WHERE code = ? ORDER BY service_id", (args["identifier"],))
    elif args.get("name"):
        rows = world.all("SELECT * FROM services WHERE instr(lower(name), lower(?)) > 0 OR instr(lower(code), lower(?)) > 0 ORDER BY service_id", (args["name"], args["name"]))
    else:
        raise ValueError("identifier or name is required")
    return {"total": len(rows), "services": [_service(row) for row in rows]}


def services_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _service(world.one("SELECT * FROM services WHERE service_id = ?", (args["service_id"],), missing=f"Service/{args['service_id']} not found"))


def engineers_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM engineers WHERE engineer_id = ?", (args["engineer_id"],), missing="engineer not found")
    return {"engineer_id": row["engineer_id"], "name": row["name"], "role": row["role"], "focus": row["focus"]}


def hosts_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("service_id"):
        rows = world.all("SELECT * FROM hosts WHERE service_id = ? ORDER BY host_id", (args["service_id"],))
    else:
        rows = world.all("SELECT * FROM hosts ORDER BY host_id")
    return {"hosts": rows}


def meterings_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT service_id FROM services WHERE service_id = ?", (args["service_id"],), missing=f"Service/{args['service_id']} not found")
    if args.get("metric"):
        rows = world.all("SELECT * FROM meterings WHERE service_id = ? AND metric = ? ORDER BY measured_at DESC, metering_id", (args["service_id"], args["metric"]))
    else:
        rows = world.all("SELECT * FROM meterings WHERE service_id = ? ORDER BY measured_at DESC, metering_id", (args["service_id"],))
    return {"total": len(rows), "meterings": [_metering(row) for row in rows]}


# --------------------------------------------------------------------------- #
# Release tickets
# --------------------------------------------------------------------------- #


def _classes_by_code(world: World) -> dict[str, dict[str, Any]]:
    return {row["artifact_class"]: row for row in world.all("SELECT * FROM artifact_classes")}


def tickets_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("service_id", "artifact_class", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    if not clauses:
        raise ValueError("at least one of service_id, artifact_class, status is required")
    rows = world.all(f"SELECT * FROM tickets WHERE {' AND '.join(clauses)} ORDER BY ticket_id", params)
    classes = _classes_by_code(world)
    return {"total": len(rows), "tickets": [_ticket(row, classes[row["artifact_class"]]) for row in rows]}


def tickets_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM tickets WHERE ticket_id = ?", (args["ticket_id"],), missing=f"Ticket/{args['ticket_id']} not found")
    return _ticket(row, _classes_by_code(world)[row["artifact_class"]])


# --------------------------------------------------------------------------- #
# Scheduler (jobs and runs)
# --------------------------------------------------------------------------- #


def jobs_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("service_id", "kind"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"jobs": world.all(f"SELECT * FROM jobs {where} ORDER BY job_id", params)}


def jobs_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM jobs WHERE job_id = ?", (args["job_id"],), missing=f"Job/{args['job_id']} not found"))


def runs_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("job_id", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    if args.get("start_date"):
        clauses.append("substr(started_at, 1, 10) >= ?")
        params.append(args["start_date"])
    if args.get("end_date"):
        clauses.append("substr(started_at, 1, 10) <= ?")
        params.append(args["end_date"])
    if not clauses:
        raise ValueError("at least one filter is required")
    rows = world.all(f"SELECT * FROM job_runs WHERE {' AND '.join(clauses)} ORDER BY started_at, run_id", params)
    return {"total": len(rows), "runs": [_run(row) for row in rows]}


def runs_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _run(world.one("SELECT * FROM job_runs WHERE run_id = ?", (args["run_id"],), missing=f"JobRun/{args['run_id']} not found"))


# --------------------------------------------------------------------------- #
# Backup catalog
# --------------------------------------------------------------------------- #


def classes_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM artifact_classes WHERE artifact_class = ?", (args["artifact_class"],), missing=f"artifact class {args['artifact_class']} not found"))


def inventory_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("artifact_class", "store_id"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = world.all(
        f"SELECT artifact_class, store_id, SUM(segment_count) AS segment_count, COUNT(*) AS set_count FROM backup_sets {where} "
        "GROUP BY artifact_class, store_id ORDER BY artifact_class, store_id",
        params,
    )
    return {"balances": rows, "note": "Gross catalogued segments including checksum-failed, reserved, and purge-queued sets; see backup.sets.list for set status."}


def sets_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = ["artifact_class = ?"], [args["artifact_class"]]
    for key in ("store_id", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    rows = world.all(f"SELECT * FROM backup_sets WHERE {' AND '.join(clauses)} ORDER BY retention_expiry, set_id", params)
    return {"artifact_class": args["artifact_class"], "sets": rows}


def restores_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("status", "artifact_class"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"restores": world.all(f"SELECT * FROM restore_jobs {where} ORDER BY restore_id", params)}


def restores_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM restore_jobs WHERE restore_id = ?", (args["restore_id"],), missing=f"restore job {args['restore_id']} not found"))


def restores_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    vendor = world.one("SELECT * FROM vendors WHERE vendor_id = ?", (args["vendor_id"],), missing=f"vendor {args['vendor_id']} not found")
    world.one("SELECT artifact_class FROM artifact_classes WHERE artifact_class = ?", (args["artifact_class"],), missing=f"artifact class {args['artifact_class']} not found")
    confirmation = world.one(
        "SELECT * FROM retrieval_confirmations WHERE confirmation_id = ?",
        (args["confirmation_id"],),
        missing=f"retrieval confirmation {args['confirmation_id']} not found",
    )
    if confirmation["vendor_id"] != vendor["vendor_id"] or confirmation["artifact_class"] != args["artifact_class"]:
        raise ValueError(f"confirmation {args['confirmation_id']} does not cover {args['artifact_class']} from {args['vendor_id']}")
    if confirmation["status"] != "OPEN":
        raise ValueError(f"confirmation {args['confirmation_id']} is {confirmation['status']}")
    if args["segment_count"] > confirmation["segments_available"]:
        raise ValueError(f"confirmation {args['confirmation_id']} covers at most {confirmation['segments_available']} {SEGMENT_UNIT}")
    expected = confirmation["standard_ready_date"] if args["retrieval_option"] == "standard" else confirmation["expedited_ready_date"]
    restore_id = world.next_id("restore_jobs", "restore_id", "RST-")
    row = {
        "restore_id": restore_id,
        "vendor_id": vendor["vendor_id"],
        "confirmation_id": confirmation["confirmation_id"],
        "artifact_class": args["artifact_class"],
        "segment_count": args["segment_count"],
        "unit": SEGMENT_UNIT,
        "retrieval_option": args["retrieval_option"],
        "expected_ready_date": expected,
        "status": "SUBMITTED",
        "requested_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO restore_jobs (restore_id, vendor_id, confirmation_id, artifact_class, segment_count, unit, retrieval_option, expected_ready_date, status, requested_by, created_at, revision) "
        "VALUES (:restore_id, :vendor_id, :confirmation_id, :artifact_class, :segment_count, :unit, :retrieval_option, :expected_ready_date, :status, :requested_by, :created_at, :revision)",
        row,
    )
    world.audit("backup.restores.create", "restore_jobs", restore_id, "insert", row)
    world.record_mutation("backup.restores.create", "restore_jobs", restore_id, "SUBMITTED", args)
    return dict(row)


def copies_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM store_copies WHERE copy_id = ?", (args["copy_id"],), missing=f"copy {args['copy_id']} not found"))


def releasable_segments(world: World, artifact_class: str, store_id: str) -> int:
    record = world.one("SELECT * FROM artifact_classes WHERE artifact_class = ?", (artifact_class,), missing=f"artifact class {artifact_class} not found")
    horizon = (world.as_of + timedelta(days=int(record["minimum_retention_days"]))).isoformat()
    row = world.one(
        "SELECT COALESCE(SUM(segment_count), 0) AS quantity FROM backup_sets WHERE artifact_class = ? AND store_id = ? "
        "AND status = 'VERIFIED' AND reserved_for_ticket IS NULL AND retention_expiry > ?",
        (artifact_class, store_id, horizon),
    )
    return int(row["quantity"])


def copies_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    for key in ("from_store_id", "to_store_id"):
        world.one("SELECT store_id FROM stores WHERE store_id = ?", (args[key],), missing=f"store {args[key]} not found")
    if args["from_store_id"] == args["to_store_id"]:
        raise ValueError("a copy needs two different stores")
    releasable = releasable_segments(world, args["artifact_class"], args["from_store_id"])
    if args["segment_count"] > releasable:
        raise ValueError(f"{args['from_store_id']} holds only {releasable} releasable {SEGMENT_UNIT} of {args['artifact_class']}; reserved, checksum-failed, and purge-queued sets cannot move")
    copy_id = world.next_id("store_copies", "copy_id", "CPY-")
    row = {
        "copy_id": copy_id,
        "artifact_class": args["artifact_class"],
        "segment_count": args["segment_count"],
        "from_store_id": args["from_store_id"],
        "to_store_id": args["to_store_id"],
        "scheduled_date": args["scheduled_date"],
        "status": "SCHEDULED",
        "requested_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO store_copies (copy_id, artifact_class, segment_count, from_store_id, to_store_id, scheduled_date, status, requested_by, created_at, revision) "
        "VALUES (:copy_id, :artifact_class, :segment_count, :from_store_id, :to_store_id, :scheduled_date, :status, :requested_by, :created_at, :revision)",
        row,
    )
    world.audit("backup.copies.create", "store_copies", copy_id, "insert", row)
    world.record_mutation("backup.copies.create", "store_copies", copy_id, "SCHEDULED", args)
    return dict(row)


# --------------------------------------------------------------------------- #
# Build farm
# --------------------------------------------------------------------------- #


def runners_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("pool"):
        rows = world.all("SELECT * FROM runners WHERE pool = ? ORDER BY runner_id", (args["pool"],))
    else:
        rows = world.all("SELECT * FROM runners ORDER BY runner_id")
    return {"runners": rows}


def windows_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses = ["service_date >= ?", "service_date <= ?"]
    params: list[Any] = [args["start_date"], args["end_date"]]
    if args.get("runner_id"):
        clauses.append("runner_id = ?")
        params.append(args["runner_id"])
    if args.get("status"):
        clauses.append("status = ?")
        params.append(args["status"])
    rows = world.all(f"SELECT * FROM farm_windows WHERE {' AND '.join(clauses)} ORDER BY service_date, runner_id, session DESC", params)
    return {"windows": [_window(row) for row in rows]}


def reservations_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("ticket_id", "runner_id", "status", "service_id"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    if args.get("start_date"):
        clauses.append("substr(start_time, 1, 10) >= ?")
        params.append(args["start_date"])
    if args.get("end_date"):
        clauses.append("substr(start_time, 1, 10) <= ?")
        params.append(args["end_date"])
    if not clauses:
        raise ValueError("at least one filter is required")
    rows = world.all(f"SELECT * FROM reservations WHERE {' AND '.join(clauses)} ORDER BY start_time, reservation_id", params)
    return {"total": len(rows), "reservations": [_reservation(row) for row in rows]}


def reservations_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _reservation(world.one("SELECT * FROM reservations WHERE reservation_id = ?", (args["reservation_id"],), missing=f"Reservation/{args['reservation_id']} not found"))


def _split_datetime(value: str, label: str) -> tuple[str, str]:
    if len(value) != 19 or value[10] != "T":
        raise ValueError(f"{label} must be YYYY-MM-DDTHH:MM:SS")
    date.fromisoformat(value[:10])
    return value[:10], value[11:]


def _windows_for_interval(world: World, runner_id: str, start: str, end: str) -> list[dict[str, Any]]:
    start_date, start_time = _split_datetime(start, "start_time")
    end_date, end_time = _split_datetime(end, "end_time")
    if start_date != end_date:
        raise ValueError("a farm reservation must start and end on the same service date")
    if start_time >= end_time:
        raise ValueError("start_time must precede end_time")
    rows = world.all("SELECT * FROM farm_windows WHERE runner_id = ? AND service_date = ? ORDER BY start_time", (runner_id, start_date))
    covering = [row for row in rows if row["start_time"] < end_time and row["end_time"] > start_time]
    if not covering:
        raise ValueError(f"no {runner_id} window covers {start} - {end}")
    if start_time < min(row["start_time"] for row in covering) or end_time > max(row["end_time"] for row in covering):
        raise ValueError(f"{start} - {end} falls outside the {runner_id} farm windows")
    return covering


def _require_free(windows: list[dict[str, Any]], *, holder: str | None = None) -> None:
    for row in windows:
        if row["status"] == "free":
            continue
        if holder and row.get("reservation_id") == holder:
            continue
        raise ValueError(f"{row['window_id']} is {row['status']}: {row.get('hold_reason') or 'not available'}; protected and blocked windows cannot be displaced")


def _claim(world: World, tool: str, windows: list[dict[str, Any]], reservation_id: str) -> None:
    for row in windows:
        world.connection.execute("UPDATE farm_windows SET status = 'busy', hold_reason = 'reserved', reservation_id = ? WHERE window_id = ?", (reservation_id, row["window_id"]))
        world.audit(tool, "farm_windows", row["window_id"], "update", {"status": "busy", "reservation_id": reservation_id})


def _release(world: World, tool: str, reservation_id: str) -> None:
    for row in world.all("SELECT window_id FROM farm_windows WHERE reservation_id = ?", (reservation_id,)):
        world.connection.execute("UPDATE farm_windows SET status = 'free', hold_reason = NULL, reservation_id = NULL WHERE window_id = ?", (row["window_id"],))
        world.audit(tool, "farm_windows", row["window_id"], "update", {"status": "free", "reservation_id": None})


def reservations_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "buildfarm.reservations.create"
    ticket = world.one("SELECT * FROM tickets WHERE ticket_id = ?", (args["ticket_id"],), missing=f"Ticket/{args['ticket_id']} not found")
    if ticket["status"] not in {"open", "active"}:
        raise ValueError(f"Ticket/{args['ticket_id']} is {ticket['status']} and cannot be scheduled")
    runner = world.one("SELECT * FROM runners WHERE runner_id = ?", (args["runner_id"],), missing=f"runner {args['runner_id']} not found")
    if runner["status"] != "ACTIVE":
        raise ValueError(f"{args['runner_id']} is {runner['status']}: {runner.get('status_note') or ''}".strip())
    windows = _windows_for_interval(world, args["runner_id"], args["start_time"], args["end_time"])
    _require_free(windows)
    reservation_id = world.next_id("reservations", "reservation_id", "RES-")
    row = {
        "reservation_id": reservation_id,
        "service_id": ticket["service_id"],
        "ticket_id": args["ticket_id"],
        "runner_id": args["runner_id"],
        "start_time": args["start_time"],
        "end_time": args["end_time"],
        "status": "booked",
        "description": args.get("description"),
        "revision": 1,
        "last_updated": world.clock(),
    }
    world.connection.execute(
        "INSERT INTO reservations (reservation_id, service_id, ticket_id, runner_id, start_time, end_time, status, description, revision, last_updated) "
        "VALUES (:reservation_id, :service_id, :ticket_id, :runner_id, :start_time, :end_time, :status, :description, :revision, :last_updated)",
        row,
    )
    world.audit(tool, "reservations", reservation_id, "insert", row)
    _claim(world, tool, windows, reservation_id)
    world.record_mutation(tool, "reservations", reservation_id, "booked", args)
    return _reservation(row)


def reservations_update(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "buildfarm.reservations.update"
    current = world.one("SELECT * FROM reservations WHERE reservation_id = ?", (args["reservation_id"],), missing=f"Reservation/{args['reservation_id']} not found")
    if current["status"] in {"cancelled", "fulfilled"}:
        raise ValueError(f"Reservation/{args['reservation_id']} is {current['status']} and cannot be changed")
    changes = {key: args[key] for key in ("runner_id", "start_time", "end_time", "status", "description") if key in args}
    if not changes:
        raise ValueError("no change requested")
    updated = {**current, **changes}
    new_status = updated["status"]
    if new_status == "cancelled":
        _release(world, tool, current["reservation_id"])
    else:
        if any(key in changes for key in ("runner_id", "start_time", "end_time")) or current["status"] != "booked":
            if not (updated.get("runner_id") and updated.get("start_time") and updated.get("end_time")):
                raise ValueError("booking a reservation needs runner_id, start_time, and end_time")
            runner = world.one("SELECT * FROM runners WHERE runner_id = ?", (updated["runner_id"],), missing=f"runner {updated['runner_id']} not found")
            if runner["status"] != "ACTIVE":
                raise ValueError(f"{updated['runner_id']} is {runner['status']}: {runner.get('status_note') or ''}".strip())
            windows = _windows_for_interval(world, updated["runner_id"], updated["start_time"], updated["end_time"])
            _require_free(windows, holder=current["reservation_id"])
            _release(world, tool, current["reservation_id"])
            _claim(world, tool, windows, current["reservation_id"])
            if new_status not in {"booked", "pending"}:
                raise ValueError(f"unsupported status transition to {new_status}")
    updated["revision"] = int(current["revision"]) + 1
    updated["last_updated"] = world.clock()
    world.connection.execute(
        "UPDATE reservations SET runner_id = :runner_id, start_time = :start_time, end_time = :end_time, status = :status, description = :description, revision = :revision, last_updated = :last_updated WHERE reservation_id = :reservation_id",
        updated,
    )
    world.audit(tool, "reservations", current["reservation_id"], "update", changes)
    world.record_mutation(tool, "reservations", current["reservation_id"], new_status, args, revision=updated["revision"])
    return _reservation(updated)


# --------------------------------------------------------------------------- #
# Vendor, approvals, collaboration surfaces
# --------------------------------------------------------------------------- #


def confirmations_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("artifact_class", "vendor_id"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"confirmations": world.all(f"SELECT * FROM retrieval_confirmations {where} ORDER BY confirmation_id", params)}


def confirmations_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM retrieval_confirmations WHERE confirmation_id = ?", (args["confirmation_id"],), missing=f"confirmation {args['confirmation_id']} not found")
    vendor = world.one("SELECT * FROM vendors WHERE vendor_id = ?", (row["vendor_id"],))
    return {**row, "vendor_name": vendor["name"]}


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
        "related_ticket_id": args.get("related_ticket_id"),
        "related_service_id": args.get("related_service_id"),
        "created_at": world.clock(),
        "status": "DRAFT",
    }
    world.connection.execute(
        "INSERT INTO note_drafts (draft_id, recipient, subject, body, related_ticket_id, related_service_id, created_at, status) "
        "VALUES (:draft_id, :recipient, :subject, :body, :related_ticket_id, :related_service_id, :created_at, :status)",
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
    ToolSpec("cmdb.services.search", "Search deployable services by immutable service code or by name.", obj({"identifier": string("service code"), "name": string("name fragment")}), "read", services_search, "CMDB service search"),
    ToolSpec("cmdb.services.get", "Read one service record by id.", obj({"service_id": string()}, ["service_id"]), "read", services_get, "CMDB service record"),
    ToolSpec("cmdb.engineers.get", "Read one engineer record.", obj({"engineer_id": string()}, ["engineer_id"]), "read", engineers_get, "CMDB engineer record"),
    ToolSpec("cmdb.hosts.list", "List Linux hosts in the inventory, optionally for one service.", obj({"service_id": string()}), "read", hosts_list, "CMDB host inventory"),
    ToolSpec("cmdb.meterings.list", "List measured payload meterings for a service, optionally by metric (BUNDLE-GB, LOG-GB-PER-DAY, DATASET-GB), newest first.", obj({"service_id": string(), "metric": string("metric code")}, ["service_id"]), "read", meterings_list, "CMDB payload metering"),
    ToolSpec("releases.tickets.list", "List release and recovery tickets by service, artifact class, or status.", obj({"service_id": string(), "artifact_class": string(), "status": string()}), "read", tickets_list, "release ticket search"),
    ToolSpec("releases.tickets.get", "Read one release or recovery ticket with payload basis, scope, and run durations.", obj({"ticket_id": string()}, ["ticket_id"]), "read", tickets_get, "release ticket record"),
    ToolSpec("jobs.jobs.list", "List scheduled jobs (cron / CI), optionally by service or kind.", obj({"service_id": string(), "kind": string()}), "read", jobs_list, "scheduler job list"),
    ToolSpec("jobs.jobs.get", "Read one scheduled job definition.", obj({"job_id": string()}, ["job_id"]), "read", jobs_get, "scheduler job record"),
    ToolSpec("jobs.runs.list", "List job runs by job, status, or start-date window.", obj({"job_id": string(), "status": string(), "start_date": string("ISO date"), "end_date": string("ISO date")}), "read", runs_list, "scheduler run history"),
    ToolSpec("jobs.runs.get", "Read one job run with exit code and summary.", obj({"run_id": string()}, ["run_id"]), "read", runs_get, "scheduler run record"),
    ToolSpec("backup.classes.get", "Read an artifact class: segment size, storage tier, and minimum remaining retention.", obj({"artifact_class": string()}, ["artifact_class"]), "read", classes_get, "backup catalog class record"),
    ToolSpec("backup.inventory.list", "Gross catalogued segment balances by artifact class and store (no netting of checksum, reservation, or retention state).", obj({"artifact_class": string(), "store_id": string()}), "read", inventory_list, "backup catalog balance"),
    ToolSpec("backup.sets.list", "List catalogued segment sets for an artifact class with segment count, retention expiry, status, and reservations.", obj({"artifact_class": string(), "store_id": string(), "status": string()}, ["artifact_class"]), "read", sets_list, "backup set register"),
    ToolSpec("backup.restores.list", "List vendor restore jobs.", obj({"status": string(), "artifact_class": string()}), "read", restores_list, "vault restore job"),
    ToolSpec("backup.restores.get", "Read one vendor restore job.", obj({"restore_id": string()}, ["restore_id"]), "read", restores_get, "vault restore job"),
    ToolSpec(
        "backup.restores.create",
        "Create a vendor restore job against an open retrieval confirmation. The expected ready date is taken from the confirmation for the chosen retrieval option.",
        obj(
            {
                "vendor_id": string(),
                "confirmation_id": string(),
                "artifact_class": string(),
                "segment_count": integer(minimum=1),
                "retrieval_option": {"type": "string", "enum": ["standard", "expedited"]},
            },
            ["vendor_id", "confirmation_id", "artifact_class", "segment_count", "retrieval_option"],
        ),
        "write",
        restores_create,
        "vault restore job",
        idempotent=False,
    ),
    ToolSpec("backup.copies.get", "Read one inter-store segment copy.", obj({"copy_id": string()}, ["copy_id"]), "read", copies_get, "inter-store copy"),
    ToolSpec(
        "backup.copies.create",
        "Schedule an inter-store segment copy. Only releasable sets at the source (verified, unreserved, outside the purge-queue horizon) may move.",
        obj(
            {"artifact_class": string(), "segment_count": integer(minimum=1), "from_store_id": string(), "to_store_id": string(), "scheduled_date": string("ISO date")},
            ["artifact_class", "segment_count", "from_store_id", "to_store_id", "scheduled_date"],
        ),
        "write",
        copies_create,
        "inter-store copy",
        idempotent=False,
    ),
    ToolSpec("buildfarm.runners.list", "List release-farm runners with status and isolation capability.", obj({"pool": string()}), "read", runners_list, "build-farm runner list"),
    ToolSpec("buildfarm.windows.list", "List runner reservation windows between two dates with free / busy / protected / blocked status.", obj({"start_date": string("ISO date"), "end_date": string("ISO date"), "runner_id": string(), "status": string()}, ["start_date", "end_date"]), "read", windows_list, "build-farm window calendar"),
    ToolSpec("buildfarm.reservations.list", "List farm reservations by ticket, runner, service, status, or date window.", obj({"ticket_id": string(), "runner_id": string(), "service_id": string(), "status": string(), "start_date": string("ISO date"), "end_date": string("ISO date")}), "read", reservations_list, "build-farm reservation search"),
    ToolSpec("buildfarm.reservations.get", "Read one farm reservation.", obj({"reservation_id": string()}, ["reservation_id"]), "read", reservations_get, "build-farm reservation record"),
    ToolSpec(
        "buildfarm.reservations.create",
        "Book a farm reservation for a ticket on a runner. Every window the interval touches must be free; protected and blocked windows are never displaced.",
        obj(
            {"ticket_id": string(), "runner_id": string(), "start_time": string(DATETIME), "end_time": string(DATETIME), "description": string()},
            ["ticket_id", "runner_id", "start_time", "end_time"],
        ),
        "write",
        reservations_create,
        "build-farm reservation create",
        idempotent=False,
    ),
    ToolSpec(
        "buildfarm.reservations.update",
        "Move, book, or cancel an existing farm reservation. Moving re-validates the target windows; the record revision increments.",
        obj(
            {"reservation_id": string(), "runner_id": string(), "start_time": string(DATETIME), "end_time": string(DATETIME), "status": {"type": "string", "enum": ["booked", "pending", "cancelled"]}, "description": string()},
            ["reservation_id"],
        ),
        "write",
        reservations_update,
        "build-farm reservation update",
        idempotent=False,
    ),
    ToolSpec("vendor.confirmations.list", "List cold-archive retrieval confirmations.", obj({"artifact_class": string(), "vendor_id": string()}), "read", confirmations_list, "vault retrieval confirmation"),
    ToolSpec("vendor.confirmations.get", "Read one retrieval confirmation: segments, standard and expedited ready dates, fee, validity.", obj({"confirmation_id": string()}, ["confirmation_id"]), "read", confirmations_get, "vault retrieval confirmation"),
    ToolSpec("approvals.list", "List approval records, optionally by keyword.", obj({"q": string()}), "read", approvals_list, "approval workflow record"),
    ToolSpec("approvals.get", "Read one approval record with its exact scope and approver.", obj({"approval_id": string()}, ["approval_id"]), "read", approvals_get, "approval workflow record"),
    ToolSpec("messages.list", "Search operations mail by keyword (subject, body, labels).", obj({"q": string(), "max_results": integer(minimum=1)}, ["q"]), "read", messages_list, "mailbox search"),
    ToolSpec("messages.get", "Read one message with body and attachment list.", obj({"message_id": string()}, ["message_id"]), "read", messages_get, "mailbox message"),
    ToolSpec("chat.threads.list", "Search team chat threads by keyword.", obj({"q": string()}, ["q"]), "read", chat_threads_list, "team chat search"),
    ToolSpec("chat.threads.get", "Read one team chat thread.", obj({"thread_id": string()}, ["thread_id"]), "read", chat_threads_get, "team chat thread"),
    ToolSpec("drive.files.list", "Search shared-drive files by keyword (name, folder, content).", obj({"q": string()}, ["q"]), "read", drive_files_list, "shared drive search"),
    ToolSpec("drive.files.get", "Read shared-drive file metadata.", obj({"file_id": string()}, ["file_id"]), "read", drive_files_get, "shared drive file"),
    ToolSpec("drive.files.export", "Export a shared-drive file as text (spreadsheets as CSV, PDFs as extracted text).", obj({"file_id": string()}, ["file_id"]), "read", drive_files_export, "shared drive export"),
    ToolSpec(
        "notes.drafts.create",
        "Create, but do not send, a stakeholder draft note.",
        obj({"recipient": string(), "subject": string(), "body": string(), "related_ticket_id": string(), "related_service_id": string()}, ["recipient", "subject", "body"]),
        "write",
        drafts_create,
        "collaboration draft",
        idempotent=False,
    ),
)

SERVERS = {
    "cmdb": "Configuration database: services, engineers, Linux host inventory, and payload meterings.",
    "releases": "Release and recovery tickets with payload basis and run durations.",
    "jobs": "Scheduler: cron / CI job definitions and run history.",
    "backup": "Backup catalog: artifact classes, segment-set register, vendor restore jobs, and inter-store copies.",
    "buildfarm": "Release build farm: runners, reservation-window calendar, and reservations.",
    "vendor": "Cold-archive vault retrieval confirmations.",
    "approvals": "Approval workflow records with exact scope.",
    "messages": "Operations mailbox for the platform team.",
    "chat": "Platform operations chat threads.",
    "drive": "Shared drive holding runbooks, registers, calendars, and exports.",
    "notes": "Stakeholder draft notes (never sent by the benchmark).",
}

__all__ = ["SERVERS", "TOOLS", "releasable_segments"]
