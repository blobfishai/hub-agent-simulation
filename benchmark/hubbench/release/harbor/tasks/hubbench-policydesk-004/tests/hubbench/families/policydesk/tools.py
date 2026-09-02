"""PolicyDesk provider-shaped tools over the family's SQLite world.

Read tools return provider-shaped policy, request-queue, entitlement,
exception, directory, training, audit, screening, and review-calendar records;
write tools persist to the domain tables, refresh the affected records, and
record the exact payload for the sealed contract. There is no LLM anywhere here.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from ...engine.families import ToolSpec
from ...engine.validation import integer, obj, string
from ...engine.world import World

REQUEST_UNIT = "REQUEST"


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #


def _resource(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "resource_id": row["resource_id"],
        "code": row["code"],
        "name": row["name"],
        "system": row["system"],
        "sensitivity_tier": row["sensitivity_tier"],
        "sod_domain": row["sod_domain"],
        "owner": f"Person/{row['owner_id']}" if row.get("owner_id") else None,
    }


def _request(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": row["request_id"],
        "requester": f"Person/{row['requester_id']}",
        "resource": f"Resource/{row['resource_id']}",
        "requested_role": row["requested_role"],
        "duration_days": row["duration_days"],
        "justification": row["justification"],
        "manager_attested": bool(row["manager_attested"]),
        "sensitivity_tier": row["sensitivity_tier"],
        "duplicate_of": row.get("duplicate_of"),
        "submitted_at": row["submitted_at"],
        "status": row["status"],
        "decision": row.get("decision"),
        "decided_days": row.get("decided_days"),
        "note": row.get("note") or "",
    }


def _clause(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "clause_id": row["clause_id"],
        "policy": f"Policy/{row['policy_id']}",
        "number": row["number"],
        "topic": row["topic"],
        "sensitivity_tier": row["sensitivity_tier"],
        "max_grant_days": row["max_grant_days"],
        "requires_tier": row["requires_tier"],
        "requires_training": row.get("requires_training"),
        "allowed_control": row.get("allowed_control"),
        "text": row["text"],
    }


def _grant(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "grant_id": row["grant_id"],
        "resource": f"Resource/{row['resource_id']}",
        "request": f"Request/{row['request_id']}" if row.get("request_id") else None,
        "role": row["role"],
        "sod_domain": row["sod_domain"],
        "covers_request_count": row["covers_request_count"],
        "granted_on": row["granted_on"],
        "expires_on": row["expires_on"],
        "status": row["status"],
        "status_reason": row.get("status_reason"),
        "approval": f"Approval/{row['approval_id']}" if row.get("approval_id") else None,
        "meta": {"versionId": str(row["revision"])},
    }


def _exception(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "exception_id": row["exception_id"],
        "resource": f"Resource/{row['resource_id']}",
        "request": f"Request/{row['request_id']}" if row.get("request_id") else None,
        "reason": row["reason"],
        "compensating_control": row["compensating_control"],
        "approver_tier": row["approver_tier"],
        "covers_request_count": row["covers_request_count"],
        "granted_on": row["granted_on"],
        "expires_on": row["expires_on"],
        "status": row["status"],
        "approval": f"Approval/{row['approval_id']}" if row.get("approval_id") else None,
    }


def _approver(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "approver_id": row["approver_id"],
        "name": row["name"],
        "authority_tier": row["authority_tier"],
        "max_sensitivity_tier": row["max_sensitivity_tier"],
        "status": row["status"],
        "available_from": row.get("available_from"),
        "status_note": row.get("status_note"),
    }


def _session(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["session_id"],
        "status": row["status"],
        "description": row.get("description"),
        "start": row.get("start_time"),
        "end": row.get("end_time"),
        "approver": row.get("approver_id"),
        "request": f"Request/{row['request_id']}" if row.get("request_id") else None,
        "resource": f"Resource/{row['resource_id']}" if row.get("resource_id") else None,
        "meta": {"versionId": str(row["revision"]), "lastUpdated": row["last_updated"]},
    }


def _window(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["window_id"],
        "approver": row["approver_id"],
        "serviceDate": row["service_date"],
        "session": row["session"],
        "start": f"{row['service_date']}T{row['start_time']}",
        "end": f"{row['service_date']}T{row['end_time']}",
        "status": row["status"],
        "holdReason": row.get("hold_reason"),
        "session_ref": row.get("session_id"),
    }


# --------------------------------------------------------------------------- #
# Policy library
# --------------------------------------------------------------------------- #


def policy_library_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("status"):
        rows = world.all("SELECT * FROM policies WHERE status = ? ORDER BY policy_id", (args["status"],))
    else:
        rows = world.all("SELECT * FROM policies ORDER BY policy_id")
    return {"policies": [dict(row) for row in rows]}


def policy_documents_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM policies WHERE policy_id = ?", (args["policy_id"],), missing=f"Policy/{args['policy_id']} not found"))


def policy_clauses_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT policy_id FROM policies WHERE policy_id = ?", (args["policy_id"],), missing=f"Policy/{args['policy_id']} not found")
    if args.get("sensitivity_tier"):
        rows = world.all("SELECT * FROM policy_clauses WHERE policy_id = ? AND sensitivity_tier = ? ORDER BY clause_id", (args["policy_id"], args["sensitivity_tier"]))
    else:
        rows = world.all("SELECT * FROM policy_clauses WHERE policy_id = ? ORDER BY clause_id", (args["policy_id"],))
    return {"policy_id": args["policy_id"], "clauses": [_clause(row) for row in rows]}


# --------------------------------------------------------------------------- #
# Resources
# --------------------------------------------------------------------------- #


def resources_search(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("identifier"):
        rows = world.all("SELECT * FROM resources WHERE code = ? ORDER BY resource_id", (args["identifier"],))
    elif args.get("name"):
        rows = world.all("SELECT * FROM resources WHERE instr(lower(name), lower(?)) > 0 OR instr(lower(code), lower(?)) > 0 ORDER BY resource_id", (args["name"], args["name"]))
    else:
        raise ValueError("identifier or name is required")
    return {"total": len(rows), "resources": [_resource(row) for row in rows]}


def resources_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _resource(world.one("SELECT * FROM resources WHERE resource_id = ?", (args["resource_id"],), missing=f"Resource/{args['resource_id']} not found"))


# --------------------------------------------------------------------------- #
# Access-request queue
# --------------------------------------------------------------------------- #


def requests_queue_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("resource_id", "status", "requester_id"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    if not clauses:
        raise ValueError("at least one of resource_id, status, requester_id is required")
    rows = world.all(f"SELECT * FROM access_requests WHERE {' AND '.join(clauses)} ORDER BY request_id", params)
    return {"total": len(rows), "requests": [_request(row) for row in rows]}


def requests_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _request(world.one("SELECT * FROM access_requests WHERE request_id = ?", (args["request_id"],), missing=f"Request/{args['request_id']} not found"))


def requests_decide(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "requests.decide"
    row = world.one("SELECT * FROM access_requests WHERE request_id = ?", (args["request_id"],), missing=f"Request/{args['request_id']} not found")
    if row["status"] != "PENDING":
        raise ValueError(f"Request/{args['request_id']} is {row['status']} and cannot be decided again")
    decision = args["decision"]
    if decision == "APPROVE" and row["disposition_basis"] != "APPROVE":
        raise ValueError(f"Request/{args['request_id']} cannot be approved as requested under the current policy; it must be routed to an exception or refused")
    decided_days = int(args.get("decided_days", 0))
    world.connection.execute(
        "UPDATE access_requests SET status = 'DECIDED', decision = ?, decided_days = ? WHERE request_id = ?",
        (decision, decided_days, args["request_id"]),
    )
    world.audit(tool, "access_requests", args["request_id"], "update", {"decision": decision, "decided_days": decided_days})
    world.record_mutation(tool, "access_requests", args["request_id"], decision, args)
    return _request(world.one("SELECT * FROM access_requests WHERE request_id = ?", (args["request_id"],)))


# --------------------------------------------------------------------------- #
# Entitlement / grant store
# --------------------------------------------------------------------------- #


def _operative_clause(world: World, sensitivity_tier: str) -> dict[str, Any]:
    return world.one(
        "SELECT c.* FROM policy_clauses c JOIN policies p ON c.policy_id = p.policy_id "
        "WHERE p.status = 'EFFECTIVE' AND c.sensitivity_tier = ? ORDER BY c.clause_id",
        (sensitivity_tier,),
        missing=f"no operative clause for {sensitivity_tier}",
    )


def grants_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("resource_id", "status", "sod_domain"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = world.all(f"SELECT * FROM grants {where} ORDER BY grant_id", params)
    return {"grants": [_grant(row) for row in rows]}


def grants_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _grant(world.one("SELECT * FROM grants WHERE grant_id = ?", (args["grant_id"],), missing=f"grant {args['grant_id']} not found"))


def grants_sod_check(world: World, args: dict[str, Any]) -> dict[str, Any]:
    resource = world.one("SELECT * FROM resources WHERE resource_id = ?", (args["resource_id"],), missing=f"Resource/{args['resource_id']} not found")
    domain = resource["sod_domain"]
    rules = world.all("SELECT * FROM sod_rules WHERE domain_a = ? OR domain_b = ? ORDER BY rule_id", (domain, domain))
    conflicting_domains = {rule["domain_b"] if rule["domain_a"] == domain else rule["domain_a"] for rule in rules}
    active = world.all("SELECT * FROM grants WHERE status = 'ACTIVE' ORDER BY grant_id")
    conflicts = [_grant(row) for row in active if row["sod_domain"] in conflicting_domains]
    return {
        "resource": f"Resource/{args['resource_id']}",
        "sod_domain": domain,
        "rules": [dict(rule) for rule in rules],
        "conflicting_active_grants": conflicts,
    }


def grants_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "grants.create"
    resource = world.one("SELECT * FROM resources WHERE resource_id = ?", (args["resource_id"],), missing=f"Resource/{args['resource_id']} not found")
    approval = world.one("SELECT * FROM approvals WHERE approval_id = ?", (args["approval_id"],), missing=f"approval {args['approval_id']} not found")
    scope = json.loads(approval["scope_json"])
    clause = _operative_clause(world, resource["sensitivity_tier"])
    if int(args["duration_days"]) > int(clause["max_grant_days"]):
        raise ValueError(f"clause {clause['number']} caps {resource['sensitivity_tier']} grants at {clause['max_grant_days']} days; {args['duration_days']} exceeds it")
    if scope.get("resource_id") not in (None, args["resource_id"]):
        raise ValueError(f"approval {args['approval_id']} does not cover Resource/{args['resource_id']}")
    max_requests = int(scope.get("max_requests", 0))
    if int(args["covers_request_count"]) > max_requests:
        raise ValueError(f"approval {args['approval_id']} covers at most {max_requests} {REQUEST_UNIT.lower()}s")
    finding = world.all(
        "SELECT * FROM audit_findings WHERE resource_id = ? AND blocks_grant = 1 AND status = 'OPEN' ORDER BY finding_id",
        (args["resource_id"],),
    )
    if finding:
        raise ValueError(f"open audit finding {finding[0]['finding_id']} blocks new grants on Resource/{args['resource_id']}")
    grant_id = world.next_id("grants", "grant_id", "GRANT-")
    row = {
        "grant_id": grant_id,
        "resource_id": args["resource_id"],
        "request_id": args.get("request_id"),
        "role": args["role"],
        "sod_domain": resource["sod_domain"],
        "covers_request_count": int(args["covers_request_count"]),
        "granted_on": world.as_of.isoformat(),
        "expires_on": args["expires_on"],
        "status": "ACTIVE",
        "status_reason": None,
        "approval_id": args["approval_id"],
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO grants (grant_id, resource_id, request_id, role, sod_domain, covers_request_count, granted_on, expires_on, status, status_reason, approval_id, revision) "
        "VALUES (:grant_id, :resource_id, :request_id, :role, :sod_domain, :covers_request_count, :granted_on, :expires_on, :status, :status_reason, :approval_id, :revision)",
        row,
    )
    world.audit(tool, "grants", grant_id, "insert", row)
    world.record_mutation(tool, "grants", grant_id, "ACTIVE", args)
    return _grant(row)


# --------------------------------------------------------------------------- #
# Exceptions register
# --------------------------------------------------------------------------- #


def exceptions_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("resource_id", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = world.all(f"SELECT * FROM exceptions_register {where} ORDER BY exception_id", params)
    return {"exceptions": [_exception(row) for row in rows]}


def exceptions_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _exception(world.one("SELECT * FROM exceptions_register WHERE exception_id = ?", (args["exception_id"],), missing=f"exception {args['exception_id']} not found"))


def exceptions_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "exceptions.create"
    resource = world.one("SELECT * FROM resources WHERE resource_id = ?", (args["resource_id"],), missing=f"Resource/{args['resource_id']} not found")
    approval = world.one("SELECT * FROM approvals WHERE approval_id = ?", (args["approval_id"],), missing=f"approval {args['approval_id']} not found")
    scope = json.loads(approval["scope_json"])
    clause = _operative_clause(world, resource["sensitivity_tier"])
    required_tier = int(clause["requires_tier"])
    if int(args["approver_tier"]) < required_tier:
        raise ValueError(f"clause {clause['number']} requires a tier-{required_tier} approver for {resource['sensitivity_tier']} exceptions; tier-{args['approver_tier']} is insufficient")
    if not str(args["compensating_control"]).strip():
        raise ValueError("a documented compensating control is required")
    allowed = clause.get("allowed_control")
    if allowed and args["compensating_control"] != allowed:
        raise ValueError(f"clause {clause['number']} accepts only the '{allowed}' compensating control")
    max_requests = int(scope.get("max_requests", 0))
    if int(args["covers_request_count"]) > max_requests:
        raise ValueError(f"approval {args['approval_id']} covers at most {max_requests} {REQUEST_UNIT.lower()}s")
    exception_id = world.next_id("exceptions_register", "exception_id", "EXC-")
    row = {
        "exception_id": exception_id,
        "resource_id": args["resource_id"],
        "request_id": args.get("request_id"),
        "reason": args["reason"],
        "compensating_control": args["compensating_control"],
        "approver_tier": int(args["approver_tier"]),
        "covers_request_count": int(args["covers_request_count"]),
        "granted_on": world.as_of.isoformat(),
        "expires_on": args["expires_on"],
        "status": "ACTIVE",
        "approval_id": args["approval_id"],
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO exceptions_register (exception_id, resource_id, request_id, reason, compensating_control, approver_tier, covers_request_count, granted_on, expires_on, status, approval_id, revision) "
        "VALUES (:exception_id, :resource_id, :request_id, :reason, :compensating_control, :approver_tier, :covers_request_count, :granted_on, :expires_on, :status, :approval_id, :revision)",
        row,
    )
    world.audit(tool, "exceptions_register", exception_id, "insert", row)
    world.record_mutation(tool, "exceptions_register", exception_id, "ACTIVE", args)
    return _exception(row)


# --------------------------------------------------------------------------- #
# Approver directory, training, audit
# --------------------------------------------------------------------------- #


def people_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM people WHERE person_id = ?", (args["person_id"],), missing=f"Person/{args['person_id']} not found")
    return {"person_id": row["person_id"], "name": row["name"], "title": row["title"], "department": row.get("department_id"), "employment_type": row["employment_type"], "manager": row.get("manager_id")}


def approvers_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("min_tier"):
        rows = world.all("SELECT * FROM approvers WHERE authority_tier >= ? ORDER BY approver_id", (int(args["min_tier"]),))
    else:
        rows = world.all("SELECT * FROM approvers ORDER BY approver_id")
    return {"approvers": [_approver(row) for row in rows]}


def approvers_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _approver(world.one("SELECT * FROM approvers WHERE approver_id = ?", (args["approver_id"],), missing=f"approver {args['approver_id']} not found"))


def training_records_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("person_id", "training_code", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    if not clauses:
        raise ValueError("at least one of person_id, training_code, status is required")
    rows = world.all(f"SELECT * FROM training_records WHERE {' AND '.join(clauses)} ORDER BY record_id", params)
    return {"records": [dict(row) for row in rows]}


def training_records_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM training_records WHERE record_id = ?", (args["record_id"],), missing=f"training record {args['record_id']} not found"))


def audit_findings_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("resource_id", "status", "severity"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = world.all(f"SELECT * FROM audit_findings {where} ORDER BY finding_id", params)
    return {"findings": [dict(row) for row in rows]}


def audit_findings_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM audit_findings WHERE finding_id = ?", (args["finding_id"],), missing=f"finding {args['finding_id']} not found"))


# --------------------------------------------------------------------------- #
# Screening vendor
# --------------------------------------------------------------------------- #


def screening_confirmations_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("credential", "vendor_id"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"confirmations": world.all(f"SELECT * FROM screening_confirmations {where} ORDER BY confirmation_id", params)}


def screening_confirmations_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM screening_confirmations WHERE confirmation_id = ?", (args["confirmation_id"],), missing=f"confirmation {args['confirmation_id']} not found")
    vendor = world.one("SELECT * FROM screening_vendors WHERE vendor_id = ?", (row["vendor_id"],))
    return {**row, "vendor_name": vendor["name"]}


# --------------------------------------------------------------------------- #
# Approver review calendar
# --------------------------------------------------------------------------- #


def reviews_windows_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses = ["service_date >= ?", "service_date <= ?"]
    params: list[Any] = [args["start_date"], args["end_date"]]
    if args.get("approver_id"):
        clauses.append("approver_id = ?")
        params.append(args["approver_id"])
    if args.get("status"):
        clauses.append("status = ?")
        params.append(args["status"])
    rows = world.all(f"SELECT * FROM review_windows WHERE {' AND '.join(clauses)} ORDER BY service_date, approver_id, session", params)
    return {"windows": [_window(row) for row in rows]}


def reviews_sessions_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("request_id", "approver_id", "status", "resource_id"):
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
    rows = world.all(f"SELECT * FROM review_sessions WHERE {' AND '.join(clauses)} ORDER BY start_time, session_id", params)
    return {"total": len(rows), "sessions": [_session(row) for row in rows]}


def reviews_sessions_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _session(world.one("SELECT * FROM review_sessions WHERE session_id = ?", (args["session_id"],), missing=f"Session/{args['session_id']} not found"))


def _split_datetime(value: str, label: str) -> tuple[str, str]:
    if len(value) != 19 or value[10] != "T":
        raise ValueError(f"{label} must be YYYY-MM-DDTHH:MM:SS")
    date.fromisoformat(value[:10])
    return value[:10], value[11:]


def _windows_for_interval(world: World, approver_id: str, start: str, end: str) -> list[dict[str, Any]]:
    start_date, start_time = _split_datetime(start, "start_time")
    end_date, end_time = _split_datetime(end, "end_time")
    if start_date != end_date:
        raise ValueError("a review session must start and end on the same service date")
    if start_time >= end_time:
        raise ValueError("start_time must precede end_time")
    rows = world.all("SELECT * FROM review_windows WHERE approver_id = ? AND service_date = ? ORDER BY start_time", (approver_id, start_date))
    covering = [row for row in rows if row["start_time"] < end_time and row["end_time"] > start_time]
    if not covering:
        raise ValueError(f"no {approver_id} window covers {start} - {end}")
    if start_time < min(row["start_time"] for row in covering) or end_time > max(row["end_time"] for row in covering):
        raise ValueError(f"{start} - {end} falls outside the {approver_id} review windows")
    return covering


def _require_free(windows: list[dict[str, Any]], *, holder: str | None = None) -> None:
    for row in windows:
        if row["status"] == "free":
            continue
        if holder and row.get("session_id") == holder:
            continue
        raise ValueError(f"{row['window_id']} is {row['status']}: {row.get('hold_reason') or 'not available'}; protected and blocked windows cannot be displaced")


def _claim(world: World, tool: str, windows: list[dict[str, Any]], session_id: str) -> None:
    for row in windows:
        world.connection.execute("UPDATE review_windows SET status = 'busy', hold_reason = 'reserved', session_id = ? WHERE window_id = ?", (session_id, row["window_id"]))
        world.audit(tool, "review_windows", row["window_id"], "update", {"status": "busy", "session_id": session_id})


def _release(world: World, tool: str, session_id: str) -> None:
    for row in world.all("SELECT window_id FROM review_windows WHERE session_id = ?", (session_id,)):
        world.connection.execute("UPDATE review_windows SET status = 'free', hold_reason = NULL, session_id = NULL WHERE window_id = ?", (row["window_id"],))
        world.audit(tool, "review_windows", row["window_id"], "update", {"status": "free", "session_id": None})


def _require_available_approver(world: World, approver_id: str, sensitivity_tier: str) -> dict[str, Any]:
    approver = world.one("SELECT * FROM approvers WHERE approver_id = ?", (approver_id,), missing=f"approver {approver_id} not found")
    if approver["status"] != "AVAILABLE":
        raise ValueError(f"{approver_id} is {approver['status']}: {approver.get('status_note') or ''}".strip())
    tiers = ["tier-3", "tier-2", "tier-1"]
    if tiers.index(approver["max_sensitivity_tier"]) < tiers.index(sensitivity_tier):
        raise ValueError(f"{approver_id} may review at most {approver['max_sensitivity_tier']}; the cohort is {sensitivity_tier}")
    return approver


def reviews_sessions_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "reviews.sessions.create"
    resource = world.one("SELECT * FROM resources WHERE resource_id = ?", (args["resource_id"],), missing=f"Resource/{args['resource_id']} not found")
    _require_available_approver(world, args["approver_id"], resource["sensitivity_tier"])
    windows = _windows_for_interval(world, args["approver_id"], args["start_time"], args["end_time"])
    _require_free(windows)
    session_id = world.next_id("review_sessions", "session_id", "REV-")
    row = {
        "session_id": session_id,
        "request_id": args.get("request_id"),
        "resource_id": args["resource_id"],
        "approver_id": args["approver_id"],
        "start_time": args["start_time"],
        "end_time": args["end_time"],
        "status": "booked",
        "description": args.get("description"),
        "revision": 1,
        "last_updated": world.clock(),
    }
    world.connection.execute(
        "INSERT INTO review_sessions (session_id, request_id, resource_id, approver_id, start_time, end_time, status, description, revision, last_updated) "
        "VALUES (:session_id, :request_id, :resource_id, :approver_id, :start_time, :end_time, :status, :description, :revision, :last_updated)",
        row,
    )
    world.audit(tool, "review_sessions", session_id, "insert", row)
    _claim(world, tool, windows, session_id)
    world.record_mutation(tool, "review_sessions", session_id, "booked", args)
    return _session(row)


def reviews_sessions_update(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "reviews.sessions.update"
    current = world.one("SELECT * FROM review_sessions WHERE session_id = ?", (args["session_id"],), missing=f"Session/{args['session_id']} not found")
    if current["status"] in {"cancelled", "completed"}:
        raise ValueError(f"Session/{args['session_id']} is {current['status']} and cannot be changed")
    changes = {key: args[key] for key in ("approver_id", "start_time", "end_time", "status", "description") if key in args}
    if not changes:
        raise ValueError("no change requested")
    updated = {**current, **changes}
    new_status = updated["status"]
    if new_status == "cancelled":
        _release(world, tool, current["session_id"])
    else:
        if any(key in changes for key in ("approver_id", "start_time", "end_time")) or current["status"] != "booked":
            if not (updated.get("approver_id") and updated.get("start_time") and updated.get("end_time")):
                raise ValueError("booking a session needs approver_id, start_time, and end_time")
            resource = world.one("SELECT * FROM resources WHERE resource_id = ?", (updated["resource_id"],), missing="resource not found") if updated.get("resource_id") else None
            tier = resource["sensitivity_tier"] if resource else "tier-3"
            _require_available_approver(world, updated["approver_id"], tier)
            windows = _windows_for_interval(world, updated["approver_id"], updated["start_time"], updated["end_time"])
            _require_free(windows, holder=current["session_id"])
            _release(world, tool, current["session_id"])
            _claim(world, tool, windows, current["session_id"])
            if new_status not in {"booked", "pending"}:
                raise ValueError(f"unsupported status transition to {new_status}")
    updated["revision"] = int(current["revision"]) + 1
    updated["last_updated"] = world.clock()
    world.connection.execute(
        "UPDATE review_sessions SET approver_id = :approver_id, start_time = :start_time, end_time = :end_time, status = :status, description = :description, revision = :revision, last_updated = :last_updated WHERE session_id = :session_id",
        updated,
    )
    world.audit(tool, "review_sessions", current["session_id"], "update", changes)
    world.record_mutation(tool, "review_sessions", current["session_id"], new_status, args, revision=updated["revision"])
    return _session(updated)


# --------------------------------------------------------------------------- #
# Approvals, mailbox, chat, drive, notes
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
        "related_request_id": args.get("related_request_id"),
        "related_resource_id": args.get("related_resource_id"),
        "created_at": world.clock(),
        "status": "DRAFT",
    }
    world.connection.execute(
        "INSERT INTO note_drafts (draft_id, recipient, subject, body, related_request_id, related_resource_id, created_at, status) "
        "VALUES (:draft_id, :recipient, :subject, :body, :related_request_id, :related_resource_id, :created_at, :status)",
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
    ToolSpec("policy.library.list", "List access-governance policy documents, optionally by status (EFFECTIVE / SUPERSEDED).", obj({"status": string("policy status")}), "read", policy_library_list, "policy library index"),
    ToolSpec("policy.documents.get", "Read one policy document record: code, version, effective date, and status.", obj({"policy_id": string()}, ["policy_id"]), "read", policy_documents_get, "policy document record"),
    ToolSpec("policy.clauses.list", "List the numbered clauses of a policy, optionally for one sensitivity tier: max grant days, required approver tier, required training, allowed compensating control.", obj({"policy_id": string(), "sensitivity_tier": string()}, ["policy_id"]), "read", policy_clauses_list, "policy clause register"),
    ToolSpec("requests.queue.list", "List access requests by resource, status, or requester, with role, duration, justification, attestation, and duplicate links.", obj({"resource_id": string(), "status": string(), "requester_id": string()}), "read", requests_queue_list, "access-request queue"),
    ToolSpec("requests.get", "Read one access request with its attributes and any decision.", obj({"request_id": string()}, ["request_id"]), "read", requests_get, "access-request record"),
    ToolSpec(
        "requests.decide",
        "Record a disposition on a pending access request (APPROVE / EXCEPTION / REFUSE). A request the policy does not permit to be approved as requested cannot be APPROVEd.",
        obj({"request_id": string(), "decision": {"type": "string", "enum": ["APPROVE", "EXCEPTION", "REFUSE"]}, "decided_days": integer(minimum=0), "note": string()}, ["request_id", "decision"]),
        "write",
        requests_decide,
        "access-request decision",
        idempotent=False,
    ),
    ToolSpec("resources.search", "Search access resources by immutable resource code or by name.", obj({"identifier": string("resource code"), "name": string("name fragment")}), "read", resources_search, "resource catalog search"),
    ToolSpec("resources.get", "Read one resource: system, sensitivity tier, segregation-of-duties domain, and owner.", obj({"resource_id": string()}, ["resource_id"]), "read", resources_get, "resource catalog record"),
    ToolSpec("grants.list", "List entitlement grants by resource, status, or segregation-of-duties domain, with covered count and expiry.", obj({"resource_id": string(), "status": string(), "sod_domain": string()}), "read", grants_list, "entitlement grant register"),
    ToolSpec("grants.get", "Read one entitlement grant.", obj({"grant_id": string()}, ["grant_id"]), "read", grants_get, "entitlement grant record"),
    ToolSpec("grants.sod.check", "Return the segregation-of-duties rules touching a resource's domain and any active grants in the conflicting domains.", obj({"resource_id": string()}, ["resource_id"]), "read", grants_sod_check, "segregation-of-duties check"),
    ToolSpec(
        "grants.create",
        "Provision a time-boxed entitlement grant for the eligible cohort against a signed approval. Rejects a duration beyond the operative clause maximum, a covered count beyond the approval scope, a resource mismatch, or a resource with an open grant-blocking audit finding.",
        obj(
            {
                "resource_id": string(),
                "request_id": string(),
                "role": string(),
                "covers_request_count": integer(minimum=1),
                "duration_days": integer(minimum=1),
                "expires_on": string("ISO date"),
                "approval_id": string(),
            },
            ["resource_id", "role", "covers_request_count", "duration_days", "expires_on", "approval_id"],
        ),
        "write",
        grants_create,
        "entitlement grant create",
        idempotent=False,
    ),
    ToolSpec("exceptions.list", "List exceptions-register entries by resource or status, with compensating control, approver tier, covered count, and expiry.", obj({"resource_id": string(), "status": string()}), "read", exceptions_list, "exceptions register"),
    ToolSpec("exceptions.get", "Read one exceptions-register entry.", obj({"exception_id": string()}, ["exception_id"]), "read", exceptions_get, "exceptions register record"),
    ToolSpec(
        "exceptions.create",
        "Enter a time-boxed exception covering a blocked-but-recoverable cohort with a documented compensating control. Rejects an approver tier below the clause requirement, a missing or unlisted control, or a covered count beyond the approval scope.",
        obj(
            {
                "resource_id": string(),
                "request_id": string(),
                "reason": string(),
                "compensating_control": string(),
                "approver_tier": integer(minimum=1),
                "covers_request_count": integer(minimum=1),
                "expires_on": string("ISO date"),
                "approval_id": string(),
            },
            ["resource_id", "reason", "compensating_control", "approver_tier", "covers_request_count", "expires_on", "approval_id"],
        ),
        "write",
        exceptions_create,
        "exception register create",
        idempotent=False,
    ),
    ToolSpec("directory.people.get", "Read one person record: title, department, and manager.", obj({"person_id": string()}, ["person_id"]), "read", people_get, "identity directory record"),
    ToolSpec("directory.approvers.list", "List approvers in the directory, optionally at or above an authority tier, with maximum sensitivity tier and availability.", obj({"min_tier": integer(minimum=1)}), "read", approvers_list, "approver directory"),
    ToolSpec("directory.approvers.get", "Read one approver: authority tier, maximum sensitivity tier, status, and availability.", obj({"approver_id": string()}, ["approver_id"]), "read", approvers_get, "approver directory record"),
    ToolSpec("training.records.list", "List training and attestation records by person, training code, or status, with completion and expiry dates.", obj({"person_id": string(), "training_code": string(), "status": string()}), "read", training_records_list, "training attestation register"),
    ToolSpec("training.records.get", "Read one training or attestation record.", obj({"record_id": string()}, ["record_id"]), "read", training_records_get, "training attestation record"),
    ToolSpec("audit.findings.list", "List audit findings by resource, status, or severity, including whether each blocks new grants.", obj({"resource_id": string(), "status": string(), "severity": string()}), "read", audit_findings_list, "audit finding tracker"),
    ToolSpec("audit.findings.get", "Read one audit finding.", obj({"finding_id": string()}, ["finding_id"]), "read", audit_findings_get, "audit finding record"),
    ToolSpec("screening.confirmations.list", "List external screening / credentialing vendor confirmations.", obj({"credential": string(), "vendor_id": string()}), "read", screening_confirmations_list, "screening vendor confirmation"),
    ToolSpec("screening.confirmations.get", "Read one screening vendor confirmation: standard and expedited clearance dates, expedite fee, slots, and validity.", obj({"confirmation_id": string()}, ["confirmation_id"]), "read", screening_confirmations_get, "screening vendor confirmation"),
    ToolSpec("reviews.windows.list", "List approver review-session windows between two dates with free / busy / protected / blocked status and hold reason.", obj({"start_date": string("ISO date"), "end_date": string("ISO date"), "approver_id": string(), "status": string()}, ["start_date", "end_date"]), "read", reviews_windows_list, "review-session window calendar"),
    ToolSpec("reviews.sessions.list", "List approver review sessions by request, approver, resource, status, or date window.", obj({"request_id": string(), "approver_id": string(), "resource_id": string(), "status": string(), "start_date": string("ISO date"), "end_date": string("ISO date")}), "read", reviews_sessions_list, "review-session search"),
    ToolSpec("reviews.sessions.get", "Read one approver review session.", obj({"session_id": string()}, ["session_id"]), "read", reviews_sessions_get, "review-session record"),
    ToolSpec(
        "reviews.sessions.create",
        "Book an approver review session for a cohort on an available approver. Every window the interval touches must be free; protected and blocked windows are never displaced, and the approver's tier must cover the cohort.",
        obj(
            {"request_id": string(), "resource_id": string(), "approver_id": string(), "start_time": string(DATETIME), "end_time": string(DATETIME), "description": string()},
            ["resource_id", "approver_id", "start_time", "end_time"],
        ),
        "write",
        reviews_sessions_create,
        "review-session create",
        idempotent=False,
    ),
    ToolSpec(
        "reviews.sessions.update",
        "Move, book, or cancel an existing review session. Moving re-validates the target windows and approver; the record revision increments.",
        obj(
            {"session_id": string(), "approver_id": string(), "start_time": string(DATETIME), "end_time": string(DATETIME), "status": {"type": "string", "enum": ["booked", "pending", "cancelled"]}, "description": string()},
            ["session_id"],
        ),
        "write",
        reviews_sessions_update,
        "review-session update",
        idempotent=False,
    ),
    ToolSpec("approvals.list", "List approval records, optionally by keyword.", obj({"q": string()}), "read", approvals_list, "approval workflow record"),
    ToolSpec("approvals.get", "Read one approval record with its exact scope and approver.", obj({"approval_id": string()}, ["approval_id"]), "read", approvals_get, "approval workflow record"),
    ToolSpec("messages.list", "Search the governance mailbox by keyword (subject, body, labels).", obj({"q": string(), "max_results": integer(minimum=1)}, ["q"]), "read", messages_list, "mailbox search"),
    ToolSpec("messages.get", "Read one message with body and attachment list.", obj({"message_id": string()}, ["message_id"]), "read", messages_get, "mailbox message"),
    ToolSpec("chat.threads.list", "Search team chat threads by keyword.", obj({"q": string()}, ["q"]), "read", chat_threads_list, "team chat search"),
    ToolSpec("chat.threads.get", "Read one team chat thread.", obj({"thread_id": string()}, ["thread_id"]), "read", chat_threads_get, "team chat thread"),
    ToolSpec("drive.files.list", "Search shared-drive files by keyword (name, folder, content).", obj({"q": string()}, ["q"]), "read", drive_files_list, "shared drive search"),
    ToolSpec("drive.files.get", "Read shared-drive file metadata.", obj({"file_id": string()}, ["file_id"]), "read", drive_files_get, "shared drive file"),
    ToolSpec("drive.files.export", "Export a shared-drive file as text (spreadsheets as CSV, PDFs as extracted text).", obj({"file_id": string()}, ["file_id"]), "read", drive_files_export, "shared drive export"),
    ToolSpec(
        "notes.drafts.create",
        "Create, but do not send, a stakeholder draft note.",
        obj({"recipient": string(), "subject": string(), "body": string(), "related_request_id": string(), "related_resource_id": string()}, ["recipient", "subject", "body"]),
        "write",
        drafts_create,
        "collaboration draft",
        idempotent=False,
    ),
)

SERVERS = {
    "policy": "Policy library: access-governance standards with numbered clauses, versions, and effective dates.",
    "requests": "Access-request queue with requester, role, duration, justification, attestation, and duplicate links.",
    "resources": "Resource catalog: systems, sensitivity tiers, and segregation-of-duties domains.",
    "grants": "Entitlement grant store with segregation-of-duties rules, covered counts, and expiry.",
    "exceptions": "Exceptions register with compensating controls, approver tiers, and expiry.",
    "directory": "Identity directory and approver directory with authority tiers and availability.",
    "training": "Training and attestation records with completion and expiry dates.",
    "audit": "Audit-finding tracker with grant-blocking findings.",
    "screening": "External screening / credentialing vendor confirmations.",
    "reviews": "Approver review-session calendar, windows, and sessions.",
    "approvals": "Approval workflow records with exact scope.",
    "messages": "Access-governance mailbox.",
    "chat": "Access-governance team chat threads.",
    "drive": "Shared drive holding policies, registers, calendars, and exports.",
    "notes": "Stakeholder draft notes (never sent by the benchmark).",
}

__all__ = ["SERVERS", "TOOLS", "REQUEST_UNIT"]
