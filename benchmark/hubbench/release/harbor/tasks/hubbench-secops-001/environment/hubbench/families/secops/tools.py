"""SecOps provider-shaped tools over the family's SQLite world.

Read tools return SIEM, EDR, IAM, cloud-key-registry, service-desk, playbook,
on-call, and identity-provider-vendor records; write tools persist to the
domain tables, refresh the affected records, and record the exact payload for
the sealed contract.  There is no LLM anywhere here, and every write is a
defensive containment action on the synthetic organisation's own credentials.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from ...engine.families import ToolSpec
from ...engine.validation import integer, obj, string
from ...engine.world import World

OBJECT_UNIT = "CREDENTIAL_OBJECT"


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #


def _identity(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "identity_id": row["identity_id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "kind": row["kind"],
        "tier": row["tier"],
        "owner_team": row["owner_team"],
        "owner": f"Analyst/{row['owner_analyst_id']}" if row.get("owner_analyst_id") else None,
    }


def _inventory(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "inventory_id": row["inventory_id"],
        "identity": f"Identity/{row['identity_id']}",
        "metric": row["metric"],
        "value": row["value"],
        "unit": row["unit"],
        "measured_at": row["measured_at"],
        "status": row["status"],
    }


def _ticket(row: dict[str, Any], credential_class: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticket_id": row["ticket_id"],
        "status": row["status"],
        "kind": row["kind"],
        "priority": row["priority"],
        "identity": f"Identity/{row['identity_id']}",
        "alert": f"Alert/{row['alert_id']}" if row.get("alert_id") else None,
        "tier_code": row["tier_code"],
        "credential_class": {"code": row["credential_class"], "display": credential_class["display"], "object_kind": credential_class["object_kind"]},
        "unit_kind": row["unit_kind"],
        "unit_basis": row["unit_basis"],
        "unit_objects": row["unit_objects"],
        "units_in_scope": row["units_in_scope"],
        "scope_note": row["scope_note"],
        "triage_minutes": row["triage_minutes"],
        "confirm_minutes": row["confirm_minutes"],
        "opened_at": row["opened_at"],
        "requested_by": f"Analyst/{row['requested_by']}",
        "note": row.get("note") or "",
    }


def _bridge(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["bridge_id"],
        "status": row["status"],
        "description": row.get("description"),
        "start": row.get("start_time"),
        "end": row.get("end_time"),
        "responder": row.get("responder_id"),
        "identity": f"Identity/{row['identity_id']}",
        "ticket": f"Ticket/{row['ticket_id']}" if row.get("ticket_id") else None,
        "meta": {"versionId": str(row["revision"]), "lastUpdated": row["last_updated"]},
    }


def _window(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["window_id"],
        "responder": row["responder_id"],
        "serviceDate": row["service_date"],
        "session": row["session"],
        "start": f"{row['service_date']}T{row['start_time']}",
        "end": f"{row['service_date']}T{row['end_time']}",
        "status": row["status"],
        "holdReason": row.get("hold_reason"),
        "bridge": row.get("bridge_id"),
    }


def _alert(row: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any]:
    return {
        "alert_id": row["alert_id"],
        "rule": {"rule_id": row["rule_id"], "name": rule["name"], "version": rule["version"], "status": rule["status"]},
        "identity": f"Identity/{row['identity_id']}" if row.get("identity_id") else None,
        "severity": row["severity"],
        "status": row["status"],
        "kind": row["kind"],
        "opened_at": row["opened_at"],
        "summary": row["summary"],
    }


def _event(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": row["event_id"],
        "alert": f"Alert/{row['alert_id']}",
        "ts": row["ts"],
        "kind": row["kind"],
        "source_ip": row["source_ip"],
        "detail": row["detail"],
    }


# --------------------------------------------------------------------------- #
# SIEM
# --------------------------------------------------------------------------- #


def _rules_by_id(world: World) -> dict[str, dict[str, Any]]:
    return {row["rule_id"]: row for row in world.all("SELECT * FROM detection_rules")}


def alerts_search(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("identifier"):
        rows = world.all("SELECT * FROM alerts WHERE alert_id = ? ORDER BY alert_id", (args["identifier"],))
    elif args.get("identity_id"):
        rows = world.all("SELECT * FROM alerts WHERE identity_id = ? ORDER BY opened_at, alert_id", (args["identity_id"],))
    elif args.get("q"):
        query = args["q"].strip().strip('"')
        rows = world.all("SELECT * FROM alerts WHERE instr(lower(summary), lower(?)) > 0 OR instr(lower(kind), lower(?)) > 0 ORDER BY opened_at, alert_id", (query, query))
    else:
        raise ValueError("identifier, identity_id, or q is required")
    rules = _rules_by_id(world)
    return {"total": len(rows), "alerts": [_alert(row, rules[row["rule_id"]]) for row in rows]}


def alerts_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM alerts WHERE alert_id = ?", (args["alert_id"],), missing=f"Alert/{args['alert_id']} not found")
    return _alert(row, _rules_by_id(world)[row["rule_id"]])


def events_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT alert_id FROM alerts WHERE alert_id = ?", (args["alert_id"],), missing=f"Alert/{args['alert_id']} not found")
    clauses, params = ["alert_id = ?"], [args["alert_id"]]
    if args.get("kind"):
        clauses.append("kind = ?")
        params.append(args["kind"])
    if args.get("start_date"):
        clauses.append("substr(ts, 1, 10) >= ?")
        params.append(args["start_date"])
    if args.get("end_date"):
        clauses.append("substr(ts, 1, 10) <= ?")
        params.append(args["end_date"])
    rows = world.all(f"SELECT * FROM alert_events WHERE {' AND '.join(clauses)} ORDER BY ts, event_id", params)
    return {"total": len(rows), "events": [_event(row) for row in rows]}


def rules_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM detection_rules WHERE rule_id = ?", (args["rule_id"],), missing=f"DetectionRule/{args['rule_id']} not found"))


def rules_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("status"):
        rows = world.all("SELECT * FROM detection_rules WHERE status = ? ORDER BY rule_id", (args["status"],))
    else:
        rows = world.all("SELECT * FROM detection_rules ORDER BY rule_id")
    return {"rules": rows}


# --------------------------------------------------------------------------- #
# EDR
# --------------------------------------------------------------------------- #


def hosts_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("identity_id"):
        rows = world.all("SELECT * FROM hosts WHERE identity_id = ? ORDER BY host_id", (args["identity_id"],))
    else:
        rows = world.all("SELECT * FROM hosts ORDER BY host_id")
    return {"hosts": rows}


def hosts_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM hosts WHERE host_id = ?", (args["host_id"],), missing=f"Host/{args['host_id']} not found"))


def detections_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("host_id", "status", "severity"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    if not clauses:
        raise ValueError("at least one of host_id, status, severity is required")
    rows = world.all(f"SELECT * FROM detections WHERE {' AND '.join(clauses)} ORDER BY detection_id", params)
    return {"total": len(rows), "detections": rows}


def detections_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM detections WHERE detection_id = ?", (args["detection_id"],), missing=f"Detection/{args['detection_id']} not found"))


# --------------------------------------------------------------------------- #
# IAM register
# --------------------------------------------------------------------------- #


def identities_search(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("identifier"):
        rows = world.all("SELECT * FROM identities WHERE username = ? ORDER BY identity_id", (args["identifier"],))
    elif args.get("name"):
        rows = world.all(
            "SELECT * FROM identities WHERE instr(lower(display_name), lower(?)) > 0 OR instr(lower(username), lower(?)) > 0 ORDER BY identity_id",
            (args["name"], args["name"]),
        )
    else:
        raise ValueError("identifier or name is required")
    return {"total": len(rows), "identities": [_identity(row) for row in rows]}


def identities_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _identity(world.one("SELECT * FROM identities WHERE identity_id = ?", (args["identity_id"],), missing=f"Identity/{args['identity_id']} not found"))


def analysts_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM analysts WHERE analyst_id = ?", (args["analyst_id"],), missing="analyst not found")
    return {"analyst_id": row["analyst_id"], "name": row["name"], "role": row["role"], "focus": row["focus"]}


def inventory_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT identity_id FROM identities WHERE identity_id = ?", (args["identity_id"],), missing=f"Identity/{args['identity_id']} not found")
    if args.get("metric"):
        rows = world.all("SELECT * FROM grant_inventory WHERE identity_id = ? AND metric = ? ORDER BY measured_at DESC, inventory_id", (args["identity_id"], args["metric"]))
    else:
        rows = world.all("SELECT * FROM grant_inventory WHERE identity_id = ? ORDER BY measured_at DESC, inventory_id", (args["identity_id"],))
    return {"total": len(rows), "inventory": [_inventory(row) for row in rows]}


def sessions_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT identity_id FROM identities WHERE identity_id = ?", (args["identity_id"],), missing=f"Identity/{args['identity_id']} not found")
    if args.get("status"):
        rows = world.all("SELECT * FROM sessions WHERE identity_id = ? AND status = ? ORDER BY started_at, session_id", (args["identity_id"], args["status"]))
    else:
        rows = world.all("SELECT * FROM sessions WHERE identity_id = ? ORDER BY started_at, session_id", (args["identity_id"],))
    return {"total": len(rows), "sessions": rows}


def factors_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT identity_id FROM identities WHERE identity_id = ?", (args["identity_id"],), missing=f"Identity/{args['identity_id']} not found")
    rows = world.all("SELECT * FROM mfa_factors WHERE identity_id = ? ORDER BY factor_id", (args["identity_id"],))
    return {"total": len(rows), "factors": rows}


def classes_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM credential_classes WHERE credential_class = ?", (args["credential_class"],), missing=f"credential class {args['credential_class']} not found"))


def grants_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = ["credential_class = ?"], [args["credential_class"]]
    for key in ("identity_id", "system", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    rows = world.all(f"SELECT * FROM grant_sets WHERE {' AND '.join(clauses)} ORDER BY expires_on, grant_id", params)
    return {"credential_class": args["credential_class"], "grants": rows}


def revocations_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM revocations WHERE revocation_id = ?", (args["revocation_id"],), missing=f"revocation {args['revocation_id']} not found"))


def revocable_objects(world: World, credential_class: str, identity_id: str, system: str) -> int:
    world.one("SELECT credential_class FROM credential_classes WHERE credential_class = ?", (credential_class,), missing=f"credential class {credential_class} not found")
    row = world.one(
        "SELECT COALESCE(SUM(object_count), 0) AS quantity FROM grant_sets WHERE credential_class = ? AND identity_id = ? AND system = ? "
        "AND status = 'ACTIVE' AND deferred_for_ticket IS NULL AND register_flag IS NULL",
        (credential_class, identity_id, system),
    )
    return int(row["quantity"])


def revocations_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "iam.revocations.create"
    world.one("SELECT identity_id FROM identities WHERE identity_id = ?", (args["identity_id"],), missing=f"Identity/{args['identity_id']} not found")
    if args["system"] not in {"iam", "cloudiam"}:
        raise ValueError("system must be iam or cloudiam")
    date.fromisoformat(args["effective_date"])
    revocable = revocable_objects(world, args["credential_class"], args["identity_id"], args["system"])
    if args["object_count"] > revocable:
        raise ValueError(
            f"{args['identity_id']} holds only {revocable} tenant-revocable {OBJECT_UNIT} of {args['credential_class']} in {args['system']}; "
            "expired, rotated, revoked, owner-deferred, and register-flagged provider-issued objects cannot be revoked by the tenant"
        )
    revocation_id = world.next_id("revocations", "revocation_id", "RVK-")
    row = {
        "revocation_id": revocation_id,
        "credential_class": args["credential_class"],
        "object_count": args["object_count"],
        "identity_id": args["identity_id"],
        "system": args["system"],
        "effective_date": args["effective_date"],
        "status": "SCHEDULED",
        "requested_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO revocations (revocation_id, credential_class, object_count, identity_id, system, effective_date, status, requested_by, created_at, revision) "
        "VALUES (:revocation_id, :credential_class, :object_count, :identity_id, :system, :effective_date, :status, :requested_by, :created_at, :revision)",
        row,
    )
    world.audit(tool, "revocations", revocation_id, "insert", row)
    world.record_mutation(tool, "revocations", revocation_id, "SCHEDULED", args)
    return dict(row)


# --------------------------------------------------------------------------- #
# Cloud key registry
# --------------------------------------------------------------------------- #


def keys_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = ["system = 'cloudiam'"], []
    for key in ("credential_class", "identity_id", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    rows = world.all(f"SELECT * FROM grant_sets WHERE {' AND '.join(clauses)} ORDER BY expires_on, grant_id", params)
    return {"keys": rows}


def keys_inventory(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("credential_class", "identity_id"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = world.all(
        f"SELECT credential_class, identity_id, system, SUM(object_count) AS object_count, COUNT(*) AS grant_count FROM grant_sets {where} "
        "GROUP BY credential_class, identity_id, system ORDER BY credential_class, identity_id, system",
        params,
    )
    return {"balances": rows, "note": "Gross registered credential objects including expired, rotated, revoked, and owner-deferred grants; see iam.grants.list for object status."}


# --------------------------------------------------------------------------- #
# Service desk and playbooks
# --------------------------------------------------------------------------- #


def _classes_by_code(world: World) -> dict[str, dict[str, Any]]:
    return {row["credential_class"]: row for row in world.all("SELECT * FROM credential_classes")}


def tickets_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("identity_id", "credential_class", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    if not clauses:
        raise ValueError("at least one of identity_id, credential_class, status is required")
    rows = world.all(f"SELECT * FROM tickets WHERE {' AND '.join(clauses)} ORDER BY ticket_id", params)
    classes = _classes_by_code(world)
    return {"total": len(rows), "tickets": [_ticket(row, classes[row["credential_class"]]) for row in rows]}


def tickets_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM tickets WHERE ticket_id = ?", (args["ticket_id"],), missing=f"Ticket/{args['ticket_id']} not found")
    return _ticket(row, _classes_by_code(world)[row["credential_class"]])


def tiers_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM containment_tiers WHERE tier_code = ?", (args["tier_code"],), missing=f"containment tier {args['tier_code']} not found"))


def tiers_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return {"tiers": world.all("SELECT * FROM containment_tiers ORDER BY tier_code")}


# --------------------------------------------------------------------------- #
# On-call roster, windows, and bridges
# --------------------------------------------------------------------------- #


def responders_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("pool"):
        rows = world.all("SELECT * FROM responders WHERE pool = ? ORDER BY responder_id", (args["pool"],))
    else:
        rows = world.all("SELECT * FROM responders ORDER BY responder_id")
    return {"responders": rows}


def windows_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses = ["service_date >= ?", "service_date <= ?"]
    params: list[Any] = [args["start_date"], args["end_date"]]
    if args.get("responder_id"):
        clauses.append("responder_id = ?")
        params.append(args["responder_id"])
    if args.get("status"):
        clauses.append("status = ?")
        params.append(args["status"])
    rows = world.all(f"SELECT * FROM oncall_windows WHERE {' AND '.join(clauses)} ORDER BY service_date, responder_id, session DESC", params)
    return {"windows": [_window(row) for row in rows]}


def bridges_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("ticket_id", "responder_id", "status", "identity_id"):
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
    rows = world.all(f"SELECT * FROM bridges WHERE {' AND '.join(clauses)} ORDER BY start_time, bridge_id", params)
    return {"total": len(rows), "bridges": [_bridge(row) for row in rows]}


def bridges_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _bridge(world.one("SELECT * FROM bridges WHERE bridge_id = ?", (args["bridge_id"],), missing=f"Bridge/{args['bridge_id']} not found"))


def _split_datetime(value: str, label: str) -> tuple[str, str]:
    if len(value) != 19 or value[10] != "T":
        raise ValueError(f"{label} must be YYYY-MM-DDTHH:MM:SS")
    date.fromisoformat(value[:10])
    return value[:10], value[11:]


def _windows_for_interval(world: World, responder_id: str, start: str, end: str) -> list[dict[str, Any]]:
    start_date, start_time = _split_datetime(start, "start_time")
    end_date, end_time = _split_datetime(end, "end_time")
    if start_date != end_date:
        raise ValueError("a responder bridge must start and end on the same service date")
    if start_time >= end_time:
        raise ValueError("start_time must precede end_time")
    rows = world.all("SELECT * FROM oncall_windows WHERE responder_id = ? AND service_date = ? ORDER BY start_time", (responder_id, start_date))
    covering = [row for row in rows if row["start_time"] < end_time and row["end_time"] > start_time]
    if not covering:
        raise ValueError(f"no {responder_id} window covers {start} - {end}")
    if start_time < min(row["start_time"] for row in covering) or end_time > max(row["end_time"] for row in covering):
        raise ValueError(f"{start} - {end} falls outside the {responder_id} on-call windows")
    return covering


def _require_free(windows: list[dict[str, Any]], *, holder: str | None = None) -> None:
    for row in windows:
        if row["status"] == "free":
            continue
        if holder and row.get("bridge_id") == holder:
            continue
        raise ValueError(f"{row['window_id']} is {row['status']}: {row.get('hold_reason') or 'not available'}; protected and blocked windows cannot be displaced")


def _claim(world: World, tool: str, windows: list[dict[str, Any]], bridge_id: str) -> None:
    for row in windows:
        world.connection.execute("UPDATE oncall_windows SET status = 'busy', hold_reason = 'bridge', bridge_id = ? WHERE window_id = ?", (bridge_id, row["window_id"]))
        world.audit(tool, "oncall_windows", row["window_id"], "update", {"status": "busy", "bridge_id": bridge_id})


def _release(world: World, tool: str, bridge_id: str) -> None:
    for row in world.all("SELECT window_id FROM oncall_windows WHERE bridge_id = ?", (bridge_id,)):
        world.connection.execute("UPDATE oncall_windows SET status = 'free', hold_reason = NULL, bridge_id = NULL WHERE window_id = ?", (row["window_id"],))
        world.audit(tool, "oncall_windows", row["window_id"], "update", {"status": "free", "bridge_id": None})


def bridges_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "oncall.bridges.create"
    ticket = world.one("SELECT * FROM tickets WHERE ticket_id = ?", (args["ticket_id"],), missing=f"Ticket/{args['ticket_id']} not found")
    if ticket["status"] not in {"open", "active"}:
        raise ValueError(f"Ticket/{args['ticket_id']} is {ticket['status']} and cannot be scheduled")
    responder = world.one("SELECT * FROM responders WHERE responder_id = ?", (args["responder_id"],), missing=f"responder {args['responder_id']} not found")
    if responder["status"] != "ACTIVE":
        raise ValueError(f"{args['responder_id']} is {responder['status']}: {responder.get('status_note') or ''}".strip())
    windows = _windows_for_interval(world, args["responder_id"], args["start_time"], args["end_time"])
    _require_free(windows)
    bridge_id = world.next_id("bridges", "bridge_id", "BRG-")
    row = {
        "bridge_id": bridge_id,
        "identity_id": ticket["identity_id"],
        "ticket_id": args["ticket_id"],
        "responder_id": args["responder_id"],
        "start_time": args["start_time"],
        "end_time": args["end_time"],
        "status": "booked",
        "description": args.get("description"),
        "revision": 1,
        "last_updated": world.clock(),
    }
    world.connection.execute(
        "INSERT INTO bridges (bridge_id, identity_id, ticket_id, responder_id, start_time, end_time, status, description, revision, last_updated) "
        "VALUES (:bridge_id, :identity_id, :ticket_id, :responder_id, :start_time, :end_time, :status, :description, :revision, :last_updated)",
        row,
    )
    world.audit(tool, "bridges", bridge_id, "insert", row)
    _claim(world, tool, windows, bridge_id)
    world.record_mutation(tool, "bridges", bridge_id, "booked", args)
    return _bridge(row)


def bridges_update(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "oncall.bridges.update"
    current = world.one("SELECT * FROM bridges WHERE bridge_id = ?", (args["bridge_id"],), missing=f"Bridge/{args['bridge_id']} not found")
    if current["status"] in {"cancelled", "closed"}:
        raise ValueError(f"Bridge/{args['bridge_id']} is {current['status']} and cannot be changed")
    changes = {key: args[key] for key in ("responder_id", "start_time", "end_time", "status", "description") if key in args}
    if not changes:
        raise ValueError("no change requested")
    updated = {**current, **changes}
    new_status = updated["status"]
    if new_status == "cancelled":
        _release(world, tool, current["bridge_id"])
    else:
        if any(key in changes for key in ("responder_id", "start_time", "end_time")) or current["status"] != "booked":
            if not (updated.get("responder_id") and updated.get("start_time") and updated.get("end_time")):
                raise ValueError("booking a bridge needs responder_id, start_time, and end_time")
            responder = world.one("SELECT * FROM responders WHERE responder_id = ?", (updated["responder_id"],), missing=f"responder {updated['responder_id']} not found")
            if responder["status"] != "ACTIVE":
                raise ValueError(f"{updated['responder_id']} is {responder['status']}: {responder.get('status_note') or ''}".strip())
            windows = _windows_for_interval(world, updated["responder_id"], updated["start_time"], updated["end_time"])
            _require_free(windows, holder=current["bridge_id"])
            _release(world, tool, current["bridge_id"])
            _claim(world, tool, windows, current["bridge_id"])
            if new_status not in {"booked", "pending"}:
                raise ValueError(f"unsupported status transition to {new_status}")
    updated["revision"] = int(current["revision"]) + 1
    updated["last_updated"] = world.clock()
    world.connection.execute(
        "UPDATE bridges SET responder_id = :responder_id, start_time = :start_time, end_time = :end_time, status = :status, description = :description, revision = :revision, last_updated = :last_updated WHERE bridge_id = :bridge_id",
        updated,
    )
    world.audit(tool, "bridges", current["bridge_id"], "update", changes)
    world.record_mutation(tool, "bridges", current["bridge_id"], new_status, args, revision=updated["revision"])
    return _bridge(updated)


# --------------------------------------------------------------------------- #
# Identity-provider vendor portal
# --------------------------------------------------------------------------- #


def confirmations_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("credential_class", "vendor_id"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"confirmations": world.all(f"SELECT * FROM invalidation_confirmations {where} ORDER BY confirmation_id", params)}


def confirmations_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM invalidation_confirmations WHERE confirmation_id = ?", (args["confirmation_id"],), missing=f"confirmation {args['confirmation_id']} not found")
    vendor = world.one("SELECT * FROM idp_vendors WHERE vendor_id = ?", (row["vendor_id"],))
    return {**row, "vendor_name": vendor["name"]}


def orders_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("status", "credential_class"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"orders": world.all(f"SELECT * FROM invalidation_orders {where} ORDER BY order_id", params)}


def orders_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM invalidation_orders WHERE order_id = ?", (args["order_id"],), missing=f"invalidation order {args['order_id']} not found"))


def orders_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    vendor = world.one("SELECT * FROM idp_vendors WHERE vendor_id = ?", (args["vendor_id"],), missing=f"vendor {args['vendor_id']} not found")
    world.one("SELECT credential_class FROM credential_classes WHERE credential_class = ?", (args["credential_class"],), missing=f"credential class {args['credential_class']} not found")
    confirmation = world.one(
        "SELECT * FROM invalidation_confirmations WHERE confirmation_id = ?",
        (args["confirmation_id"],),
        missing=f"invalidation confirmation {args['confirmation_id']} not found",
    )
    if confirmation["vendor_id"] != vendor["vendor_id"] or confirmation["credential_class"] != args["credential_class"]:
        raise ValueError(f"confirmation {args['confirmation_id']} does not cover {args['credential_class']} from {args['vendor_id']}")
    if confirmation["status"] != "OPEN":
        raise ValueError(f"confirmation {args['confirmation_id']} is {confirmation['status']}")
    if args["object_count"] > confirmation["objects_available"]:
        raise ValueError(f"confirmation {args['confirmation_id']} covers at most {confirmation['objects_available']} {OBJECT_UNIT}")
    expected = confirmation["standard_ready_date"] if args["service_option"] == "standard" else confirmation["expedited_ready_date"]
    order_id = world.next_id("invalidation_orders", "order_id", "IVO-")
    row = {
        "order_id": order_id,
        "vendor_id": vendor["vendor_id"],
        "confirmation_id": confirmation["confirmation_id"],
        "credential_class": args["credential_class"],
        "object_count": args["object_count"],
        "unit": OBJECT_UNIT,
        "service_option": args["service_option"],
        "expected_ready_date": expected,
        "status": "SUBMITTED",
        "requested_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO invalidation_orders (order_id, vendor_id, confirmation_id, credential_class, object_count, unit, service_option, expected_ready_date, status, requested_by, created_at, revision) "
        "VALUES (:order_id, :vendor_id, :confirmation_id, :credential_class, :object_count, :unit, :service_option, :expected_ready_date, :status, :requested_by, :created_at, :revision)",
        row,
    )
    world.audit("idpvendor.orders.create", "invalidation_orders", order_id, "insert", row)
    world.record_mutation("idpvendor.orders.create", "invalidation_orders", order_id, "SUBMITTED", args)
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
        "related_ticket_id": args.get("related_ticket_id"),
        "related_identity_id": args.get("related_identity_id"),
        "created_at": world.clock(),
        "status": "DRAFT",
    }
    world.connection.execute(
        "INSERT INTO note_drafts (draft_id, recipient, subject, body, related_ticket_id, related_identity_id, created_at, status) "
        "VALUES (:draft_id, :recipient, :subject, :body, :related_ticket_id, :related_identity_id, :created_at, :status)",
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
    ToolSpec("siem.alerts.search", "Search SIEM alerts by immutable alert id, by identity, or by keyword.", obj({"identifier": string("alert id"), "identity_id": string(), "q": string("keyword")}), "read", alerts_search, "SIEM alert search"),
    ToolSpec("siem.alerts.get", "Read one SIEM alert with its detection rule name, version, and status.", obj({"alert_id": string()}, ["alert_id"]), "read", alerts_get, "SIEM alert record"),
    ToolSpec("siem.events.list", "List the correlated events behind an alert, optionally by kind or date window.", obj({"alert_id": string(), "kind": string(), "start_date": string("ISO date"), "end_date": string("ISO date")}, ["alert_id"]), "read", events_list, "SIEM correlated events"),
    ToolSpec("siem.rules.get", "Read one detection rule: name, version, and enabled / retired status.", obj({"rule_id": string()}, ["rule_id"]), "read", rules_get, "SIEM detection rule"),
    ToolSpec("siem.rules.list", "List detection rules, optionally by status.", obj({"status": string()}), "read", rules_list, "SIEM detection rule list"),
    ToolSpec("edr.hosts.list", "List EDR-enrolled hosts, optionally for one identity.", obj({"identity_id": string()}), "read", hosts_list, "EDR host inventory"),
    ToolSpec("edr.hosts.get", "Read one host record with isolation state.", obj({"host_id": string()}, ["host_id"]), "read", hosts_get, "EDR host record"),
    ToolSpec("edr.detections.list", "List EDR detections by host, status, or severity.", obj({"host_id": string(), "status": string(), "severity": string()}), "read", detections_list, "EDR detection search"),
    ToolSpec("edr.detections.get", "Read one EDR detection.", obj({"detection_id": string()}, ["detection_id"]), "read", detections_get, "EDR detection record"),
    ToolSpec("iam.identities.search", "Search identities by immutable username or by display name.", obj({"identifier": string("username"), "name": string("name fragment")}), "read", identities_search, "IAM identity search"),
    ToolSpec("iam.identities.get", "Read one identity record by id.", obj({"identity_id": string()}, ["identity_id"]), "read", identities_get, "IAM identity record"),
    ToolSpec("iam.analysts.get", "Read one analyst or owner record.", obj({"analyst_id": string()}, ["analyst_id"]), "read", analysts_get, "IAM owner record"),
    ToolSpec("iam.inventory.list", "List final credential-inventory snapshots for an identity, optionally by metric (LIVE-GRANTS, LIVE-KEYS, LIVE-SESSIONS), newest first.", obj({"identity_id": string(), "metric": string("metric code")}, ["identity_id"]), "read", inventory_list, "IAM inventory snapshot"),
    ToolSpec("iam.sessions.list", "List sessions for an identity with source, geo, device, and risk, optionally by status.", obj({"identity_id": string(), "status": string()}, ["identity_id"]), "read", sessions_list, "IAM session list"),
    ToolSpec("iam.factors.list", "List MFA factors enrolled for an identity.", obj({"identity_id": string()}, ["identity_id"]), "read", factors_list, "IAM factor list"),
    ToolSpec("iam.classes.get", "Read a credential class: object kind, revocation channel, and privilege.", obj({"credential_class": string()}, ["credential_class"]), "read", classes_get, "IAM credential class record"),
    ToolSpec("iam.grants.list", "List registered credential-object grants for a class with object count, expiry, status, owner deferrals, and register flags.", obj({"credential_class": string(), "identity_id": string(), "system": string(), "status": string()}, ["credential_class"]), "read", grants_list, "IAM grant register"),
    ToolSpec("iam.revocations.get", "Read one tenant revocation record.", obj({"revocation_id": string()}, ["revocation_id"]), "read", revocations_get, "IAM tenant revocation"),
    ToolSpec(
        "iam.revocations.create",
        "Schedule a tenant revocation of credential objects for an identity. Only ACTIVE objects that are neither deferred for an owner ticket nor register-flagged as provider-issued may be revoked by the tenant.",
        obj(
            {"credential_class": string(), "object_count": integer(minimum=1), "identity_id": string(), "system": {"type": "string", "enum": ["iam", "cloudiam"]}, "effective_date": string("ISO date")},
            ["credential_class", "object_count", "identity_id", "system", "effective_date"],
        ),
        "write",
        revocations_create,
        "IAM tenant revocation",
        idempotent=False,
    ),
    ToolSpec("cloudiam.keys.list", "List access keys registered in the cloud key registry, optionally by class, identity, or status.", obj({"credential_class": string(), "identity_id": string(), "status": string()}), "read", keys_list, "cloud key register"),
    ToolSpec("cloudiam.keys.inventory", "Gross registered credential-object balances by class, identity, and system (no netting of expiry, rotation, or deferral state).", obj({"credential_class": string(), "identity_id": string()}), "read", keys_inventory, "cloud key balance"),
    ToolSpec("servicedesk.tickets.list", "List security tickets by identity, credential class, or status.", obj({"identity_id": string(), "credential_class": string(), "status": string()}), "read", tickets_list, "security ticket search"),
    ToolSpec("servicedesk.tickets.get", "Read one security ticket with object basis, scope, tier, and review durations.", obj({"ticket_id": string()}, ["ticket_id"]), "read", tickets_get, "security ticket record"),
    ToolSpec("playbooks.tiers.get", "Read one containment tier: immediate-revocation rule, owner-confirmation rule, authority level, and SLA.", obj({"tier_code": string()}, ["tier_code"]), "read", tiers_get, "containment tier record"),
    ToolSpec("playbooks.tiers.list", "List containment tiers.", obj({}), "read", tiers_list, "containment tier list"),
    ToolSpec("oncall.responders.list", "List on-call responders with status and Tier-2 qualification.", obj({"pool": string()}), "read", responders_list, "on-call responder roster"),
    ToolSpec("oncall.windows.list", "List responder windows between two dates with free / busy / protected / blocked status.", obj({"start_date": string("ISO date"), "end_date": string("ISO date"), "responder_id": string(), "status": string()}, ["start_date", "end_date"]), "read", windows_list, "on-call window calendar"),
    ToolSpec("oncall.bridges.list", "List incident bridges by ticket, responder, identity, status, or date window.", obj({"ticket_id": string(), "responder_id": string(), "identity_id": string(), "status": string(), "start_date": string("ISO date"), "end_date": string("ISO date")}), "read", bridges_list, "incident bridge search"),
    ToolSpec("oncall.bridges.get", "Read one incident bridge.", obj({"bridge_id": string()}, ["bridge_id"]), "read", bridges_get, "incident bridge record"),
    ToolSpec(
        "oncall.bridges.create",
        "Book an incident bridge for a ticket on a responder. Every window the interval touches must be free; protected and blocked windows are never displaced.",
        obj(
            {"ticket_id": string(), "responder_id": string(), "start_time": string(DATETIME), "end_time": string(DATETIME), "description": string()},
            ["ticket_id", "responder_id", "start_time", "end_time"],
        ),
        "write",
        bridges_create,
        "incident bridge create",
        idempotent=False,
    ),
    ToolSpec(
        "oncall.bridges.update",
        "Move, book, or cancel an existing incident bridge. Moving re-validates the target windows; the record revision increments.",
        obj(
            {"bridge_id": string(), "responder_id": string(), "start_time": string(DATETIME), "end_time": string(DATETIME), "status": {"type": "string", "enum": ["booked", "pending", "cancelled"]}, "description": string()},
            ["bridge_id"],
        ),
        "write",
        bridges_update,
        "incident bridge update",
        idempotent=False,
    ),
    ToolSpec("idpvendor.confirmations.list", "List identity-provider and key-custody vendor invalidation confirmations.", obj({"credential_class": string(), "vendor_id": string()}), "read", confirmations_list, "vendor invalidation confirmation"),
    ToolSpec("idpvendor.confirmations.get", "Read one invalidation confirmation: objects, standard and expedited job dates, fee, validity.", obj({"confirmation_id": string()}, ["confirmation_id"]), "read", confirmations_get, "vendor invalidation confirmation"),
    ToolSpec("idpvendor.orders.list", "List vendor invalidation orders.", obj({"status": string(), "credential_class": string()}), "read", orders_list, "vendor invalidation order"),
    ToolSpec("idpvendor.orders.get", "Read one vendor invalidation order.", obj({"order_id": string()}, ["order_id"]), "read", orders_get, "vendor invalidation order"),
    ToolSpec(
        "idpvendor.orders.create",
        "Place a vendor invalidation order against an open confirmation. The expected ready date is taken from the confirmation for the chosen service option.",
        obj(
            {
                "vendor_id": string(),
                "confirmation_id": string(),
                "credential_class": string(),
                "object_count": integer(minimum=1),
                "service_option": {"type": "string", "enum": ["standard", "expedited"]},
            },
            ["vendor_id", "confirmation_id", "credential_class", "object_count", "service_option"],
        ),
        "write",
        orders_create,
        "vendor invalidation order",
        idempotent=False,
    ),
    ToolSpec("approvals.list", "List approval records, optionally by keyword.", obj({"q": string()}), "read", approvals_list, "approval workflow record"),
    ToolSpec("approvals.get", "Read one approval record with its exact scope and approver.", obj({"approval_id": string()}, ["approval_id"]), "read", approvals_get, "approval workflow record"),
    ToolSpec("messages.list", "Search the security-operations mailbox by keyword (subject, body, labels).", obj({"q": string(), "max_results": integer(minimum=1)}, ["q"]), "read", messages_list, "mailbox search"),
    ToolSpec("messages.get", "Read one message with body and attachment list.", obj({"message_id": string()}, ["message_id"]), "read", messages_get, "mailbox message"),
    ToolSpec("chat.threads.list", "Search SOC chat threads by keyword.", obj({"q": string()}, ["q"]), "read", chat_threads_list, "team chat search"),
    ToolSpec("chat.threads.get", "Read one SOC chat thread.", obj({"thread_id": string()}, ["thread_id"]), "read", chat_threads_get, "team chat thread"),
    ToolSpec("drive.files.list", "Search shared-drive files by keyword (name, folder, content).", obj({"q": string()}, ["q"]), "read", drive_files_list, "shared drive search"),
    ToolSpec("drive.files.get", "Read shared-drive file metadata.", obj({"file_id": string()}, ["file_id"]), "read", drive_files_get, "shared drive file"),
    ToolSpec("drive.files.export", "Export a shared-drive file as text (spreadsheets as CSV, PDFs as extracted text).", obj({"file_id": string()}, ["file_id"]), "read", drive_files_export, "shared drive export"),
    ToolSpec(
        "notes.drafts.create",
        "Create, but do not send, a stakeholder draft note.",
        obj({"recipient": string(), "subject": string(), "body": string(), "related_ticket_id": string(), "related_identity_id": string()}, ["recipient", "subject", "body"]),
        "write",
        drafts_create,
        "collaboration draft",
        idempotent=False,
    ),
)

SERVERS = {
    "siem": "Security information and event management: alerts, correlated events, and versioned detection rules.",
    "edr": "Endpoint detection and response: host inventory with isolation state and detections.",
    "iam": "Workforce identity register: identities, owners, inventory snapshots, sessions, MFA factors, credential classes, grant register, and tenant revocations.",
    "cloudiam": "Cloud key registry: access-key register and gross credential-object balances.",
    "servicedesk": "Security ticket queue with object basis, tier, and review durations.",
    "playbooks": "Containment playbook library: tier records with revocation rules and authority levels.",
    "oncall": "On-call roster: responders, window calendar, and incident bridges.",
    "idpvendor": "Identity-provider and key-custody vendor portal: invalidation confirmations and orders.",
    "approvals": "Approval workflow records with exact scope.",
    "messages": "Security-operations mailbox.",
    "chat": "SOC incident chat threads.",
    "drive": "Shared drive holding playbooks, registers, calendars, and exports.",
    "notes": "Stakeholder draft notes (never sent by the benchmark).",
}

__all__ = ["SERVERS", "TOOLS", "revocable_objects"]
