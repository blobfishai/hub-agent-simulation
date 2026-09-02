"""Workplace provider-shaped tools over the family's SQLite world.

Read tools return helpdesk, tracker, wiki, calendar, HRIS, contract-register,
and counterparty-portal records; write tools persist to the domain tables,
refresh the affected records, and record the exact payload for the sealed
contract.  There is no LLM anywhere here.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from ...engine.families import ToolSpec
from ...engine.validation import integer, obj, string
from ...engine.world import World

# Standard constants the provider tools enforce; specs.py re-exports them so the
# vendored runtime (schema.sql + tools.py only) stays self-contained.
POINTS_PER_LEAVE_DAY = 2
QUALIFIED_LEVEL = 2
BASES = ("sla_response", "sla_resolution", "delivery_commitment", "goodwill")
BILLING_OPTIONS = ("standard_cycle", "off_cycle")
OPEN_ISSUE_STATUSES = ("To Do", "In Progress", "In Review")
ESCALATION_STATUSES = ("open", "committed", "monitoring")


def weekdays_between(start: str, end: str) -> list[str]:
    """Inclusive weekday dates between two ISO dates."""

    day = date.fromisoformat(start)
    last = date.fromisoformat(end)
    days = []
    while day <= last:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day += timedelta(days=1)
    return days


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #


def _customer(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "customer_id": row["customer_id"],
        "name": row["name"],
        "tier": row["tier"],
        "region": row["region"],
        "industry": row["industry"],
        "account_owner": f"User/{row['account_owner_user_id']}",
    }


def _ticket(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticket_id": row["ticket_id"],
        "customer": f"Customer/{row['customer_id']}",
        "subject": row["subject"],
        "priority": row["priority"],
        "status": row["status"],
        "opened_at": row["opened_at"],
        "first_response_at": row.get("first_response_at"),
        "resolved_at": row.get("resolved_at"),
        "channel": row["channel"],
        "requester": row["requester"],
        "duplicate_of": f"Ticket/{row['duplicate_of']}" if row.get("duplicate_of") else None,
        "escalation": f"Escalation/{row['escalation_id']}" if row.get("escalation_id") else None,
        "exempt_reason": row.get("exempt_reason"),
        "note": row.get("note") or "",
    }


def _escalation(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "escalation_id": row["escalation_id"],
        "ticket": f"Ticket/{row['ticket_id']}",
        "customer": f"Customer/{row['customer_id']}",
        "level": row["level"],
        "status": row["status"],
        "opened_at": row["opened_at"],
        "owner": f"User/{row['owner_user_id']}",
        "summary": row["summary"],
        "required_skill": row["required_skill"],
        "hands_on_minutes": row["hands_on_minutes"],
        "verification_minutes": row["verification_minutes"],
        "claim_ticket_ids": json.loads(row["claim_ticket_ids_json"]),
        "claim_basis": row.get("claim_basis"),
        "target_date": row.get("target_date"),
        "sprint": row.get("sprint_id"),
        "resolution_plan": row.get("resolution_plan"),
        "note": row.get("note") or "",
        "meta": {"versionId": str(row["revision"]), "lastUpdated": row["last_updated"]},
    }


def _issue(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": row["issue_key"],
        "project": row["project"],
        "summary": row["summary"],
        "type": row["type"],
        "status": row["status"],
        "story_points": row["story_points"],
        "priority": row["priority"],
        "required_skill": row["required_skill"],
        "escalation": row.get("escalation_id"),
        "sprint": row.get("sprint_id"),
        "assignee": row.get("assignee_id"),
        "note": row.get("note") or "",
        "meta": {"versionId": str(row["revision"]), "updated": row["updated_at"]},
    }


def _block(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["block_id"],
        "employee": row["employee_id"],
        "date": row["service_date"],
        "session": row["session"],
        "start": f"{row['service_date']}T{row['start_time']}",
        "end": f"{row['service_date']}T{row['end_time']}",
        "status": row["status"],
        "holdReason": row.get("hold_reason"),
        "booking": row.get("booking_id"),
    }


def _booking(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["booking_id"],
        "status": row["status"],
        "employee": row.get("employee_id"),
        "escalation": f"Escalation/{row['escalation_id']}" if row.get("escalation_id") else None,
        "issue": row.get("issue_key"),
        "start": row.get("start_time"),
        "end": row.get("end_time"),
        "description": row.get("description"),
        "meta": {"versionId": str(row["revision"]), "lastUpdated": row["last_updated"]},
    }


def _credit(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "credit_id": row["credit_id"],
        "agreement": f"Agreement/{row['agreement_id']}",
        "customer": f"Customer/{row['customer_id']}",
        "escalation": row.get("escalation_id"),
        "amount_usd": row["amount_usd"],
        "basis": row["basis"],
        "status": row["status"],
        "issued_on": row["issued_on"],
        "billing_option": row.get("billing_option"),
        "confirmation_id": row.get("confirmation_id"),
        "expected_application_date": row.get("expected_application_date"),
        "note": row.get("note") or "",
        "meta": {"versionId": str(row["revision"]), "createdAt": row["created_at"]},
    }


def _confirmation(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "confirmation_id": row["confirmation_id"],
        "customer": f"Customer/{row['customer_id']}",
        "kind": row["kind"],
        "counterparty": row["counterparty"],
        "reference": row["reference"],
        "standard_date": row["standard_date"],
        "expedited_date": row["expedited_date"],
        "expedite_fee_usd": row["expedite_fee_usd"],
        "valid_until": row["valid_until"],
        "status": row["status"],
        "capacity_points": row.get("capacity_points"),
        "skill_code": row.get("skill_code"),
        "note": row.get("note") or "",
    }


def _filters(args: dict[str, Any], keys: tuple[str, ...]) -> tuple[list[str], list[Any]]:
    clauses, params = [], []
    for key in keys:
        if args.get(key) not in (None, ""):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    return clauses, params


# --------------------------------------------------------------------------- #
# Helpdesk
# --------------------------------------------------------------------------- #


def customers_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _customer(world.one("SELECT * FROM customers WHERE customer_id = ?", (args["customer_id"],), missing=f"Customer/{args['customer_id']} not found"))


def tickets_search(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = _filters(args, ("customer_id", "escalation_id", "status", "priority"))
    if args.get("query"):
        clauses.append("(instr(lower(subject), lower(?)) > 0 OR instr(lower(ticket_id), lower(?)) > 0)")
        params.extend([args["query"], args["query"]])
    if not clauses:
        raise ValueError("at least one of customer_id, escalation_id, status, priority, query is required")
    rows = world.all(f"SELECT * FROM tickets WHERE {' AND '.join(clauses)} ORDER BY opened_at, ticket_id", params)
    return {"total": len(rows), "tickets": [_ticket(row) for row in rows]}


def tickets_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _ticket(world.one("SELECT * FROM tickets WHERE ticket_id = ?", (args["ticket_id"],), missing=f"Ticket/{args['ticket_id']} not found"))


def escalations_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = _filters(args, ("customer_id", "status", "level"))
    if not clauses:
        raise ValueError("at least one of customer_id, status, level is required")
    rows = world.all(f"SELECT * FROM escalations WHERE {' AND '.join(clauses)} ORDER BY opened_at, escalation_id", params)
    return {"total": len(rows), "escalations": [_escalation(row) for row in rows]}


def escalations_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _escalation(world.one("SELECT * FROM escalations WHERE escalation_id = ?", (args["escalation_id"],), missing=f"Escalation/{args['escalation_id']} not found"))


def _business_day(value: str, label: str) -> None:
    day = date.fromisoformat(value)
    if day.weekday() >= 5:
        raise ValueError(f"{label} {value} falls on a weekend")


def escalations_update(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "helpdesk.escalations.update"
    current = world.one("SELECT * FROM escalations WHERE escalation_id = ?", (args["escalation_id"],), missing=f"Escalation/{args['escalation_id']} not found")
    if current["status"] == "closed":
        raise ValueError(f"Escalation/{args['escalation_id']} is closed and cannot be changed")
    changes = {key: args[key] for key in ("status", "target_date", "sprint_id", "resolution_plan") if key in args}
    if not changes:
        raise ValueError("no change requested")
    if "status" in changes and changes["status"] not in ESCALATION_STATUSES:
        raise ValueError(f"status must be one of {list(ESCALATION_STATUSES)}; an escalation closes only when its linked issues are Done and the customer has verified")
    if "target_date" in changes:
        target = changes["target_date"]
        _business_day(target, "target_date")
        if target < world.task["as_of"]:
            raise ValueError(f"target_date {target} is before the planning date {world.task['as_of']}")
        guards = world.all(
            "SELECT c.commitment_id, c.committed_date FROM commitments c JOIN agreements a ON a.agreement_id = c.agreement_id "
            "WHERE a.customer_id = ? AND c.guards_escalation_id = ? AND c.status = 'committed' ORDER BY c.committed_date",
            (current["customer_id"], current["escalation_id"]),
        )
        for guard in guards:
            if target > guard["committed_date"]:
                raise ValueError(
                    f"target_date {target} is later than the registered customer commitment {guard['commitment_id']} ({guard['committed_date']}); "
                    "moving a committed date needs the support director"
                )
    if "sprint_id" in changes:
        sprint = world.one("SELECT * FROM sprints WHERE sprint_id = ?", (changes["sprint_id"],), missing=f"Sprint/{changes['sprint_id']} not found")
        if sprint["state"] == "closed":
            raise ValueError(f"Sprint/{changes['sprint_id']} is closed")
    updated = {**current, **changes}
    updated["revision"] = int(current["revision"]) + 1
    updated["last_updated"] = world.clock()
    world.connection.execute(
        "UPDATE escalations SET status = :status, target_date = :target_date, sprint_id = :sprint_id, resolution_plan = :resolution_plan, revision = :revision, last_updated = :last_updated WHERE escalation_id = :escalation_id",
        updated,
    )
    world.audit(tool, "escalations", current["escalation_id"], "update", changes)
    world.record_mutation(tool, "escalations", current["escalation_id"], updated["status"], args, revision=updated["revision"])
    return _escalation(updated)


def sla_policies_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM sla_policies WHERE sla_policy_id = ?", (args["sla_policy_id"],), missing=f"SLA policy {args['sla_policy_id']} not found")
    targets = world.all("SELECT priority, response_hours, resolution_hours, in_scope FROM sla_targets WHERE sla_policy_id = ? ORDER BY priority", (args["sla_policy_id"],))
    return {
        "sla_policy_id": row["sla_policy_id"],
        "name": row["name"],
        "version": row["version"],
        "status": row["status"],
        "effective_from": row["effective_from"],
        "clock": "continuous from ticket opening",
        "targets": [{**target, "in_scope": bool(target["in_scope"])} for target in targets],
        "note": row.get("note") or "",
    }


# --------------------------------------------------------------------------- #
# Tracker
# --------------------------------------------------------------------------- #


def issues_search(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = _filters(args, ("escalation_id", "sprint_id", "project", "status", "assignee_id"))
    if not clauses:
        raise ValueError("at least one of escalation_id, sprint_id, project, status, assignee_id is required")
    rows = world.all(f"SELECT * FROM issues WHERE {' AND '.join(clauses)} ORDER BY issue_key", params)
    return {"total": len(rows), "issues": [_issue(row) for row in rows]}


def issues_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _issue(world.one("SELECT * FROM issues WHERE issue_key = ?", (args["issue_key"],), missing=f"Issue/{args['issue_key']} not found"))


def _leave_days(world: World, employee_id: str, start: str, end: str) -> int:
    days = set()
    for row in world.all("SELECT start_date, end_date FROM timeoff WHERE employee_id = ? AND status = 'approved'", (employee_id,)):
        for day in weekdays_between(max(start, row["start_date"]), min(end, row["end_date"])):
            days.add(day)
    return len(days)


def _on_call(world: World, employee_id: str, start: str, end: str) -> bool:
    return bool(world.all("SELECT shift_id FROM oncall_shifts WHERE employee_id = ? AND start_date <= ? AND end_date >= ?", (employee_id, end, start)))


def _skill_level(world: World, employee_id: str, skill_code: str) -> int:
    row = world.connection.execute("SELECT level FROM skills WHERE employee_id = ? AND skill_code = ?", (employee_id, skill_code)).fetchone()
    return int(row["level"]) if row else 0


def issues_update(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "tracker.issues.update"
    current = world.one("SELECT * FROM issues WHERE issue_key = ?", (args["issue_key"],), missing=f"Issue/{args['issue_key']} not found")
    if current["status"] not in OPEN_ISSUE_STATUSES:
        raise ValueError(f"Issue/{args['issue_key']} is {current['status']} and cannot be changed")
    changes = {key: args[key] for key in ("sprint_id", "assignee_id", "status") if key in args}
    if not changes:
        raise ValueError("no change requested")
    if "status" in changes and changes["status"] not in OPEN_ISSUE_STATUSES:
        raise ValueError(f"status must be one of {list(OPEN_ISSUE_STATUSES)}; issues close through the release pipeline")
    updated = {**current, **changes}
    sprint = None
    if updated.get("sprint_id"):
        sprint = world.one("SELECT * FROM sprints WHERE sprint_id = ?", (updated["sprint_id"],), missing=f"Sprint/{updated['sprint_id']} not found")
        if sprint["state"] == "closed":
            raise ValueError(f"Sprint/{updated['sprint_id']} is closed")
    if updated.get("assignee_id"):
        person = world.one("SELECT * FROM employees WHERE employee_id = ?", (updated["assignee_id"],), missing=f"employee {updated['assignee_id']} not found")
        if person["status"] not in {"active", "contingent"}:
            raise ValueError(f"{updated['assignee_id']} is {person['status']}")
        level = _skill_level(world, updated["assignee_id"], current["required_skill"])
        if level < QUALIFIED_LEVEL:
            raise ValueError(f"{updated['assignee_id']} holds {current['required_skill']} at level {level}; the standard requires level {QUALIFIED_LEVEL} or above")
        if sprint is not None and sprint["state"] == "active" and ("sprint_id" in changes or "assignee_id" in changes):
            window_start = max(world.task["as_of"], sprint["start_date"])
            if _on_call(world, updated["assignee_id"], window_start, sprint["end_date"]):
                raise ValueError(f"{updated['assignee_id']} is on call during {sprint['sprint_id']} and carries no feature capacity (protected)")
            capacity = world.connection.execute(
                "SELECT capacity_points, committed_points FROM sprint_capacity WHERE sprint_id = ? AND employee_id = ?",
                (sprint["sprint_id"], updated["assignee_id"]),
            ).fetchone()
            remaining = (int(capacity["capacity_points"]) - int(capacity["committed_points"])) if capacity else 0
            leave = _leave_days(world, updated["assignee_id"], window_start, sprint["end_date"])
            effective = max(0, remaining - POINTS_PER_LEAVE_DAY * leave)
            if int(current["story_points"]) > effective:
                raise ValueError(
                    f"Issue/{current['issue_key']} ({current['story_points']} points) exceeds {updated['assignee_id']}'s {effective} remaining points in {sprint['sprint_id']} "
                    f"after approved leave; pulling work in beyond usable capacity needs the delivery manager's scope-change approval"
                )
    updated["revision"] = int(current["revision"]) + 1
    updated["updated_at"] = world.clock()
    world.connection.execute(
        "UPDATE issues SET sprint_id = :sprint_id, assignee_id = :assignee_id, status = :status, revision = :revision, updated_at = :updated_at WHERE issue_key = :issue_key",
        updated,
    )
    world.audit(tool, "issues", current["issue_key"], "update", changes)
    world.record_mutation(tool, "issues", current["issue_key"], updated["status"], args, revision=updated["revision"])
    return _issue(updated)


def sprints_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = _filters(args, ("state", "board"))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"sprints": world.all(f"SELECT * FROM sprints {where} ORDER BY start_date", params)}


def sprints_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM sprints WHERE sprint_id = ?", (args["sprint_id"],), missing=f"Sprint/{args['sprint_id']} not found"))


def sprints_capacity(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT sprint_id FROM sprints WHERE sprint_id = ?", (args["sprint_id"],), missing=f"Sprint/{args['sprint_id']} not found")
    rows = world.all("SELECT * FROM sprint_capacity WHERE sprint_id = ? ORDER BY employee_id", (args["sprint_id"],))
    return {
        "sprint_id": args["sprint_id"],
        "report_date": rows[0]["report_date"] if rows else None,
        "capacity": [
            {"employee": row["employee_id"], "capacity_points": row["capacity_points"], "committed_points": row["committed_points"], "remaining_points": row["capacity_points"] - row["committed_points"]}
            for row in rows
        ],
        "note": "Planning-time report: remaining = capacity - committed; leave, on-call, and skill eligibility are not applied here.",
    }


# --------------------------------------------------------------------------- #
# Wiki
# --------------------------------------------------------------------------- #


def _page(row: dict[str, Any], *, body: bool) -> dict[str, Any]:
    page = {"page_id": row["page_id"], "space": row["space"], "title": row["title"], "version": row["version"], "status": row["status"], "updated_at": row["updated_at"]}
    if body:
        page["body"] = row["body"]
    return page


def wiki_search(world: World, args: dict[str, Any]) -> dict[str, Any]:
    query = args["q"].strip().strip('"')
    clauses, params = ["(instr(lower(title), lower(?)) > 0 OR instr(lower(body), lower(?)) > 0)"], [query, query]
    if args.get("space"):
        clauses.append("space = ?")
        params.append(args["space"])
    rows = world.all(f"SELECT * FROM wiki_pages WHERE {' AND '.join(clauses)} ORDER BY root_page_id, version DESC", params)
    return {"pages": [_page(row, body=False) for row in rows]}


def wiki_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _page(world.one("SELECT * FROM wiki_pages WHERE page_id = ?", (args["page_id"],), missing=f"page {args['page_id']} not found"), body=True)


def wiki_versions(world: World, args: dict[str, Any]) -> dict[str, Any]:
    root = world.one("SELECT root_page_id FROM wiki_pages WHERE page_id = ?", (args["page_id"],), missing=f"page {args['page_id']} not found")["root_page_id"]
    rows = world.all("SELECT * FROM wiki_pages WHERE root_page_id = ? ORDER BY version DESC", (root,))
    return {"page_id": args["page_id"], "versions": [{"version": row["version"], "status": row["status"], "page_id": row["page_id"], "updated_at": row["updated_at"]} for row in rows]}


# --------------------------------------------------------------------------- #
# Calendar
# --------------------------------------------------------------------------- #


def blocks_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses: list[str] = ["service_date >= ?", "service_date <= ?"]
    params: list[Any] = [args["start_date"], args["end_date"]]
    for key in ("employee_id", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    rows = world.all(f"SELECT * FROM calendar_blocks WHERE {' AND '.join(clauses)} ORDER BY service_date, employee_id, session", params)
    return {"blocks": [_block(row) for row in rows]}


def timeoff_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses: list[str] = ["start_date <= ?", "end_date >= ?"]
    params: list[Any] = [args["end_date"], args["start_date"]]
    for key in ("employee_id", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    rows = world.all(f"SELECT * FROM timeoff WHERE {' AND '.join(clauses)} ORDER BY start_date, timeoff_id", params)
    return {"total": len(rows), "timeoff": rows}


def oncall_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses: list[str] = ["start_date <= ?", "end_date >= ?"]
    params: list[Any] = [args["end_date"], args["start_date"]]
    if args.get("rota"):
        clauses.append("rota = ?")
        params.append(args["rota"])
    rows = world.all(f"SELECT * FROM oncall_shifts WHERE {' AND '.join(clauses)} ORDER BY start_date, shift_id", params)
    return {"shifts": [{"shift_id": row["shift_id"], "employee": row["employee_id"], "rota": row["rota"], "start_date": row["start_date"], "end_date": row["end_date"]} for row in rows]}


def bookings_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = _filters(args, ("employee_id", "escalation_id", "status"))
    if args.get("start_date"):
        clauses.append("substr(start_time, 1, 10) >= ?")
        params.append(args["start_date"])
    if args.get("end_date"):
        clauses.append("substr(start_time, 1, 10) <= ?")
        params.append(args["end_date"])
    if not clauses:
        raise ValueError("at least one filter is required")
    rows = world.all(f"SELECT * FROM bookings WHERE {' AND '.join(clauses)} ORDER BY start_time, booking_id", params)
    return {"total": len(rows), "bookings": [_booking(row) for row in rows]}


def bookings_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _booking(world.one("SELECT * FROM bookings WHERE booking_id = ?", (args["booking_id"],), missing=f"Booking/{args['booking_id']} not found"))


def _split_datetime(value: str, label: str) -> tuple[str, str]:
    if len(value) != 19 or value[10] != "T":
        raise ValueError(f"{label} must be YYYY-MM-DDTHH:MM:SS")
    date.fromisoformat(value[:10])
    return value[:10], value[11:]


def _blocks_for_interval(world: World, employee_id: str, start: str, end: str) -> list[dict[str, Any]]:
    start_date, start_time = _split_datetime(start, "start")
    end_date, end_time = _split_datetime(end, "end")
    if start_date != end_date:
        raise ValueError("a booking must start and end on the same day; sessions are never split across days")
    if start_time >= end_time:
        raise ValueError("start must precede end")
    rows = world.all("SELECT * FROM calendar_blocks WHERE employee_id = ? AND service_date = ? ORDER BY start_time", (employee_id, start_date))
    covering = [row for row in rows if row["start_time"] < end_time and row["end_time"] > start_time]
    if not covering:
        raise ValueError(f"no {employee_id} calendar block covers {start} - {end}")
    if start_time < min(row["start_time"] for row in covering) or end_time > max(row["end_time"] for row in covering):
        raise ValueError(f"{start} - {end} falls outside {employee_id}'s calendar blocks")
    return covering


def _require_free(blocks: list[dict[str, Any]], *, holder: str | None = None) -> None:
    for row in blocks:
        if row["status"] == "free":
            continue
        if holder and row.get("booking_id") == holder:
            continue
        if row["status"] == "pto":
            raise ValueError(f"{row['block_id']} is approved leave: leave blocks are never booked")
        raise ValueError(f"{row['block_id']} is {row['status']}: {row.get('hold_reason') or 'not available'}; protected and booked blocks cannot be displaced")


def _claim_blocks(world: World, tool: str, blocks: list[dict[str, Any]], booking_id: str) -> None:
    for row in blocks:
        world.connection.execute("UPDATE calendar_blocks SET status = 'busy', hold_reason = 'booked', booking_id = ? WHERE block_id = ?", (booking_id, row["block_id"]))
        world.audit(tool, "calendar_blocks", row["block_id"], "update", {"status": "busy", "booking_id": booking_id})


def _release_blocks(world: World, tool: str, booking_id: str) -> None:
    for row in world.all("SELECT block_id FROM calendar_blocks WHERE booking_id = ?", (booking_id,)):
        world.connection.execute("UPDATE calendar_blocks SET status = 'free', hold_reason = NULL, booking_id = NULL WHERE block_id = ?", (row["block_id"],))
        world.audit(tool, "calendar_blocks", row["block_id"], "update", {"status": "free", "booking_id": None})


def _require_qualified(world: World, employee_id: str, escalation: dict[str, Any]) -> None:
    person = world.one("SELECT * FROM employees WHERE employee_id = ?", (employee_id,), missing=f"employee {employee_id} not found")
    if person["status"] not in {"active", "contingent"}:
        raise ValueError(f"{employee_id} is {person['status']}")
    level = _skill_level(world, employee_id, escalation["required_skill"])
    if level < QUALIFIED_LEVEL:
        raise ValueError(f"{employee_id} holds {escalation['required_skill']} at level {level}; customer-facing sessions need level {QUALIFIED_LEVEL} or above")


def bookings_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "calendar.bookings.create"
    escalation = world.one("SELECT * FROM escalations WHERE escalation_id = ?", (args["escalation_id"],), missing=f"Escalation/{args['escalation_id']} not found")
    if escalation["status"] == "closed":
        raise ValueError(f"Escalation/{args['escalation_id']} is closed")
    _require_qualified(world, args["employee_id"], escalation)
    blocks = _blocks_for_interval(world, args["employee_id"], args["start"], args["end"])
    _require_free(blocks)
    booking_id = world.next_id("bookings", "booking_id", "BKG-")
    row = {
        "booking_id": booking_id,
        "employee_id": args["employee_id"],
        "escalation_id": args["escalation_id"],
        "issue_key": args.get("issue_key"),
        "start_time": args["start"],
        "end_time": args["end"],
        "status": "booked",
        "description": args.get("description"),
        "revision": 1,
        "last_updated": world.clock(),
    }
    world.connection.execute(
        "INSERT INTO bookings (booking_id, employee_id, escalation_id, issue_key, start_time, end_time, status, description, revision, last_updated) "
        "VALUES (:booking_id, :employee_id, :escalation_id, :issue_key, :start_time, :end_time, :status, :description, :revision, :last_updated)",
        row,
    )
    world.audit(tool, "bookings", booking_id, "insert", row)
    _claim_blocks(world, tool, blocks, booking_id)
    world.record_mutation(tool, "bookings", booking_id, "booked", args)
    return _booking(row)


def bookings_update(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "calendar.bookings.update"
    current = world.one("SELECT * FROM bookings WHERE booking_id = ?", (args["booking_id"],), missing=f"Booking/{args['booking_id']} not found")
    if current["status"] in {"cancelled", "completed"}:
        raise ValueError(f"Booking/{args['booking_id']} is {current['status']} and cannot be changed")
    changes = {key: args[key] for key in ("employee_id", "start", "end", "status", "description") if key in args}
    if not changes:
        raise ValueError("no change requested")
    updated = {**current}
    if "employee_id" in changes:
        updated["employee_id"] = changes["employee_id"]
    if "start" in changes:
        updated["start_time"] = changes["start"]
    if "end" in changes:
        updated["end_time"] = changes["end"]
    if "status" in changes:
        updated["status"] = changes["status"]
    if "description" in changes:
        updated["description"] = changes["description"]
    new_status = updated["status"]
    if new_status == "cancelled":
        _release_blocks(world, tool, current["booking_id"])
    else:
        if any(key in changes for key in ("employee_id", "start", "end")) or current["status"] != "booked":
            if not (updated.get("employee_id") and updated.get("start_time") and updated.get("end_time")):
                raise ValueError("booking a session needs employee_id, start, and end")
            escalation = world.one("SELECT * FROM escalations WHERE escalation_id = ?", (current["escalation_id"],), missing="escalation not found")
            _require_qualified(world, updated["employee_id"], escalation)
            blocks = _blocks_for_interval(world, updated["employee_id"], updated["start_time"], updated["end_time"])
            _require_free(blocks, holder=current["booking_id"])
            _release_blocks(world, tool, current["booking_id"])
            _claim_blocks(world, tool, blocks, current["booking_id"])
            if new_status not in {"booked", "pending"}:
                raise ValueError(f"unsupported status transition to {new_status}")
    updated["revision"] = int(current["revision"]) + 1
    updated["last_updated"] = world.clock()
    world.connection.execute(
        "UPDATE bookings SET employee_id = :employee_id, start_time = :start_time, end_time = :end_time, status = :status, description = :description, revision = :revision, last_updated = :last_updated WHERE booking_id = :booking_id",
        updated,
    )
    world.audit(tool, "bookings", current["booking_id"], "update", changes)
    world.record_mutation(tool, "bookings", current["booking_id"], new_status, args, revision=updated["revision"])
    return _booking(updated)


# --------------------------------------------------------------------------- #
# HRIS
# --------------------------------------------------------------------------- #


def _employee(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "employee_id": row["employee_id"],
        "name": row["name"],
        "title": row["title"],
        "team": row["team"],
        "timezone": row["timezone"],
        "email": row["email"],
        "status": row["status"],
        "engagement_from": row.get("engagement_from"),
        "note": row.get("note") or "",
    }


def employees_search(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = _filters(args, ("team", "status"))
    if args.get("name"):
        clauses.append("instr(lower(name), lower(?)) > 0")
        params.append(args["name"])
    if not clauses:
        raise ValueError("at least one of name, team, status is required")
    rows = world.all(f"SELECT * FROM employees WHERE {' AND '.join(clauses)} ORDER BY employee_id", params)
    return {"total": len(rows), "employees": [_employee(row) for row in rows]}


def employees_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM employees WHERE employee_id = ?", (args["employee_id"],), missing=f"employee {args['employee_id']} not found")
    skills = world.all("SELECT skill_code, level, certified_on FROM skills WHERE employee_id = ? ORDER BY skill_code", (args["employee_id"],))
    return {**_employee(row), "skills": skills}


def skills_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = _filters(args, ("skill_code", "employee_id"))
    if not clauses:
        raise ValueError("skill_code or employee_id is required")
    rows = world.all(f"SELECT s.*, e.status AS employee_status FROM skills s JOIN employees e ON e.employee_id = s.employee_id WHERE {' AND '.join('s.' + c for c in clauses)} ORDER BY s.level DESC, s.employee_id", params)
    return {"skills": [{"employee_id": row["employee_id"], "skill_code": row["skill_code"], "level": row["level"], "certified_on": row["certified_on"], "employee_status": row["employee_status"]} for row in rows]}


# --------------------------------------------------------------------------- #
# Contract register
# --------------------------------------------------------------------------- #


def _agreement(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "agreement_id": row["agreement_id"],
        "customer": f"Customer/{row['customer_id']}",
        "plan": row["plan"],
        "monthly_fee_usd": row["monthly_fee_usd"],
        "sla_policy": row["sla_policy_id"],
        "credit_pct_per_breach": row["credit_pct_per_breach"],
        "credit_cap_pct": row["credit_cap_pct"],
        "start_date": row["start_date"],
        "end_date": row["end_date"],
        "status": row["status"],
        "note": row.get("note") or "",
    }


def agreements_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    rows = world.all("SELECT * FROM agreements WHERE customer_id = ? ORDER BY start_date DESC, agreement_id", (args["customer_id"],))
    return {"total": len(rows), "agreements": [_agreement(row) for row in rows]}


def agreements_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _agreement(world.one("SELECT * FROM agreements WHERE agreement_id = ?", (args["agreement_id"],), missing=f"Agreement/{args['agreement_id']} not found"))


def commitments_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = _filters(args, ("agreement_id", "status"))
    if not clauses:
        raise ValueError("agreement_id or status is required")
    rows = world.all(f"SELECT * FROM commitments WHERE {' AND '.join(clauses)} ORDER BY committed_date, commitment_id", params)
    return {"commitments": [{k: v for k, v in row.items() if k != "guards_escalation_id"} | {"guards_escalation": row.get("guards_escalation_id")} for row in rows]}


def credits_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = _filters(args, ("agreement_id", "escalation_id", "status"))
    if not clauses:
        raise ValueError("agreement_id, escalation_id, or status is required")
    rows = world.all(f"SELECT * FROM credits WHERE {' AND '.join(clauses)} ORDER BY issued_on, credit_id", params)
    return {"total": len(rows), "credits": [_credit(row) for row in rows], "note": "Gross ledger: voided, expired, and other-escalation credits are listed; apply the offset rule from the standard."}


def credits_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _credit(world.one("SELECT * FROM credits WHERE credit_id = ?", (args["credit_id"],), missing=f"credit {args['credit_id']} not found"))


def credits_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "contracts.credits.create"
    agreement = world.one("SELECT * FROM agreements WHERE agreement_id = ?", (args["agreement_id"],), missing=f"Agreement/{args['agreement_id']} not found")
    if agreement["status"] != "active":
        raise ValueError(f"Agreement/{args['agreement_id']} is {agreement['status']}")
    escalation = world.one("SELECT * FROM escalations WHERE escalation_id = ?", (args["escalation_id"],), missing=f"Escalation/{args['escalation_id']} not found")
    if escalation["customer_id"] != agreement["customer_id"]:
        raise ValueError(f"Escalation/{args['escalation_id']} does not belong to the customer on {args['agreement_id']}")
    if args["basis"] not in BASES:
        raise ValueError(f"basis must be one of {list(BASES)}")
    if args["billing_option"] not in BILLING_OPTIONS:
        raise ValueError(f"billing_option must be one of {list(BILLING_OPTIONS)}")
    confirmation = world.one("SELECT * FROM confirmations WHERE confirmation_id = ?", (args["confirmation_id"],), missing=f"confirmation {args['confirmation_id']} not found")
    if confirmation["kind"] != "billing_run" or confirmation["customer_id"] != agreement["customer_id"]:
        raise ValueError(f"confirmation {args['confirmation_id']} is not a billing-run confirmation for {agreement['customer_id']}")
    if confirmation["status"] != "OPEN":
        raise ValueError(f"confirmation {args['confirmation_id']} is {confirmation['status']}")
    cap = round(agreement["credit_cap_pct"] * agreement["monthly_fee_usd"] / 100)
    offsets = world.one(
        "SELECT COALESCE(SUM(amount_usd), 0) AS total FROM credits WHERE escalation_id = ? AND status IN ('ISSUED', 'PENDING', 'SUBMITTED')",
        (args["escalation_id"],),
    )["total"]
    if int(args["amount_usd"]) + int(offsets) > cap:
        raise ValueError(
            f"USD {args['amount_usd']} plus USD {int(offsets)} already issued or pending for {args['escalation_id']} exceeds the agreement's per-period credit cap of USD {cap}; "
            "any payout above the cap needs the finance controller"
        )
    expected = confirmation["standard_date"] if args["billing_option"] == "standard_cycle" else confirmation["expedited_date"]
    credit_id = world.next_id("credits", "credit_id", "CR-")
    row = {
        "credit_id": credit_id,
        "agreement_id": agreement["agreement_id"],
        "customer_id": agreement["customer_id"],
        "escalation_id": args["escalation_id"],
        "amount_usd": int(args["amount_usd"]),
        "basis": args["basis"],
        "status": "SUBMITTED",
        "issued_on": world.task["as_of"],
        "billing_option": args["billing_option"],
        "confirmation_id": args["confirmation_id"],
        "expected_application_date": expected,
        "note": args.get("note"),
        "requested_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO credits (credit_id, agreement_id, customer_id, escalation_id, amount_usd, basis, status, issued_on, billing_option, confirmation_id, expected_application_date, note, requested_by, created_at, revision) "
        "VALUES (:credit_id, :agreement_id, :customer_id, :escalation_id, :amount_usd, :basis, :status, :issued_on, :billing_option, :confirmation_id, :expected_application_date, :note, :requested_by, :created_at, :revision)",
        row,
    )
    world.audit(tool, "credits", credit_id, "insert", row)
    world.record_mutation(tool, "credits", credit_id, "SUBMITTED", args)
    return _credit(row)


def billing_runs_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses: list[str] = []
    params: list[Any] = []
    if args.get("start_date"):
        clauses.append("run_date >= ?")
        params.append(args["start_date"])
    if args.get("end_date"):
        clauses.append("run_date <= ?")
        params.append(args["end_date"])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"runs": world.all(f"SELECT * FROM billing_runs {where} ORDER BY run_date, run_id", params)}


# --------------------------------------------------------------------------- #
# Counterparty portal, approvals, collaboration surfaces
# --------------------------------------------------------------------------- #


def confirmations_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = _filters(args, ("customer_id", "kind", "status"))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"confirmations": [_confirmation(row) for row in world.all(f"SELECT * FROM confirmations {where} ORDER BY confirmation_id", params)]}


def confirmations_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _confirmation(world.one("SELECT * FROM confirmations WHERE confirmation_id = ?", (args["confirmation_id"],), missing=f"confirmation {args['confirmation_id']} not found"))


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
        "related_escalation_id": args.get("related_escalation_id"),
        "related_customer_id": args.get("related_customer_id"),
        "created_at": world.clock(),
        "status": "DRAFT",
    }
    world.connection.execute(
        "INSERT INTO note_drafts (draft_id, recipient, subject, body, related_escalation_id, related_customer_id, created_at, status) "
        "VALUES (:draft_id, :recipient, :subject, :body, :related_escalation_id, :related_customer_id, :created_at, :status)",
        row,
    )
    world.audit(tool, "note_drafts", draft_id, "insert", row)
    world.record_mutation(tool, "note_drafts", draft_id, "DRAFT", args)
    return dict(row)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

DATETIME = "ISO local date-time, YYYY-MM-DDTHH:MM:SS"
ISO_DATE = "ISO date"

TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec("helpdesk.customers.get", "Read one customer account record by immutable customer id.", obj({"customer_id": string()}, ["customer_id"]), "read", customers_get, "helpdesk customer record"),
    ToolSpec("helpdesk.tickets.search", "Search support tickets by customer, escalation, status, priority, or subject fragment.", obj({"customer_id": string(), "escalation_id": string(), "status": string(), "priority": string(), "query": string("subject or id fragment")}), "read", tickets_search, "helpdesk ticket search"),
    ToolSpec("helpdesk.tickets.get", "Read one ticket with its SLA timeline (opened, first response, resolved), duplicate link, and exemption.", obj({"ticket_id": string()}, ["ticket_id"]), "read", tickets_get, "helpdesk ticket record"),
    ToolSpec("helpdesk.escalations.list", "List escalations by customer, status, or level.", obj({"customer_id": string(), "status": string(), "level": integer()}), "read", escalations_list, "helpdesk escalation search"),
    ToolSpec("helpdesk.escalations.get", "Read one escalation: level, required skill, session sizing, claimed tickets, target date, and plan.", obj({"escalation_id": string()}, ["escalation_id"]), "read", escalations_get, "helpdesk escalation record"),
    ToolSpec(
        "helpdesk.escalations.update",
        "Commit or re-plan an escalation: status (open / committed / monitoring), target date, sprint, and resolution plan. A target date later than a registered customer commitment is rejected.",
        obj({"escalation_id": string(), "status": {"type": "string", "enum": list(ESCALATION_STATUSES)}, "target_date": string(ISO_DATE), "sprint_id": string(), "resolution_plan": string()}, ["escalation_id"]),
        "write",
        escalations_update,
        "helpdesk escalation update",
        idempotent=False,
    ),
    ToolSpec("helpdesk.sla_policies.get", "Read an SLA policy: per-priority response and resolution targets and scope.", obj({"sla_policy_id": string()}, ["sla_policy_id"]), "read", sla_policies_get, "helpdesk SLA policy"),
    ToolSpec("tracker.issues.search", "Search tracker issues by escalation, sprint, project, status, or assignee.", obj({"escalation_id": string(), "sprint_id": string(), "project": string(), "status": string(), "assignee_id": string()}), "read", issues_search, "tracker issue search"),
    ToolSpec("tracker.issues.get", "Read one tracker issue with type, status, story points, sprint, and assignee.", obj({"issue_key": string()}, ["issue_key"]), "read", issues_get, "tracker issue record"),
    ToolSpec(
        "tracker.issues.update",
        "Move an issue into a sprint and/or assign it. Assignees must hold the required skill at level 2+; moving into the active sprint is bounded by the assignee's remaining capacity after leave and on-call.",
        obj({"issue_key": string(), "sprint_id": string(), "assignee_id": string(), "status": {"type": "string", "enum": list(OPEN_ISSUE_STATUSES)}}, ["issue_key"]),
        "write",
        issues_update,
        "tracker issue update",
        idempotent=False,
    ),
    ToolSpec("tracker.sprints.list", "List sprints on the delivery board, optionally by state.", obj({"state": string(), "board": string()}), "read", sprints_list, "tracker sprint list"),
    ToolSpec("tracker.sprints.get", "Read one sprint: state, dates, and goal.", obj({"sprint_id": string()}, ["sprint_id"]), "read", sprints_get, "tracker sprint record"),
    ToolSpec("tracker.sprints.capacity", "Planning-time capacity report for a sprint: capacity, committed, and remaining points per engineer (leave, on-call, and skills not applied).", obj({"sprint_id": string()}, ["sprint_id"]), "read", sprints_capacity, "tracker capacity report"),
    ToolSpec("wiki.pages.search", "Search wiki pages by title or body fragment, optionally within a space.", obj({"q": string(), "space": string()}, ["q"]), "read", wiki_search, "wiki page search"),
    ToolSpec("wiki.pages.get", "Read one wiki page with its body, version, and status.", obj({"page_id": string()}, ["page_id"]), "read", wiki_get, "wiki page record"),
    ToolSpec("wiki.versions.list", "List the version history of a wiki page (current and superseded editions).", obj({"page_id": string()}, ["page_id"]), "read", wiki_versions, "wiki version history"),
    ToolSpec("calendar.blocks.list", "List staff calendar blocks between two dates with free / busy / protected / pto status.", obj({"start_date": string(ISO_DATE), "end_date": string(ISO_DATE), "employee_id": string(), "status": string()}, ["start_date", "end_date"]), "read", blocks_list, "staff calendar blocks"),
    ToolSpec("calendar.timeoff.list", "List leave requests overlapping a date range.", obj({"start_date": string(ISO_DATE), "end_date": string(ISO_DATE), "employee_id": string(), "status": string()}, ["start_date", "end_date"]), "read", timeoff_list, "staff calendar leave"),
    ToolSpec("calendar.oncall.list", "List on-call shifts overlapping a date range.", obj({"start_date": string(ISO_DATE), "end_date": string(ISO_DATE), "rota": string()}, ["start_date", "end_date"]), "read", oncall_list, "staff calendar on-call"),
    ToolSpec("calendar.bookings.list", "List customer-facing session bookings by employee, escalation, status, or date window.", obj({"employee_id": string(), "escalation_id": string(), "status": string(), "start_date": string(ISO_DATE), "end_date": string(ISO_DATE)}), "read", bookings_list, "staff calendar booking search"),
    ToolSpec("calendar.bookings.get", "Read one session booking.", obj({"booking_id": string()}, ["booking_id"]), "read", bookings_get, "staff calendar booking record"),
    ToolSpec(
        "calendar.bookings.create",
        "Book a customer-facing session for an escalation on an engineer's free blocks. Protected, leave, and booked blocks are never displaced; the engineer must hold the required skill at level 2+.",
        obj({"employee_id": string(), "escalation_id": string(), "start": string(DATETIME), "end": string(DATETIME), "issue_key": string(), "description": string()}, ["employee_id", "escalation_id", "start", "end"]),
        "write",
        bookings_create,
        "staff calendar booking create",
        idempotent=False,
    ),
    ToolSpec(
        "calendar.bookings.update",
        "Move, book, or cancel an existing session booking. Booking re-validates the target blocks; the record revision increments.",
        obj({"booking_id": string(), "employee_id": string(), "start": string(DATETIME), "end": string(DATETIME), "status": {"type": "string", "enum": ["booked", "pending", "cancelled"]}, "description": string()}, ["booking_id"]),
        "write",
        bookings_update,
        "staff calendar booking update",
        idempotent=False,
    ),
    ToolSpec("hris.employees.search", "Search the roster by name fragment, team, or status.", obj({"name": string(), "team": string(), "status": string()}), "read", employees_search, "HRIS roster search"),
    ToolSpec("hris.employees.get", "Read one roster record with skills and levels.", obj({"employee_id": string()}, ["employee_id"]), "read", employees_get, "HRIS roster record"),
    ToolSpec("hris.skills.list", "List certified skills by skill code or employee, with level.", obj({"skill_code": string(), "employee_id": string()}), "read", skills_list, "HRIS skill register"),
    ToolSpec("contracts.agreements.list", "List agreements for a customer (current and prior).", obj({"customer_id": string()}, ["customer_id"]), "read", agreements_list, "contract register agreement search"),
    ToolSpec("contracts.agreements.get", "Read one agreement: plan, monthly fee, SLA policy, credit percentage and cap, term, status.", obj({"agreement_id": string()}, ["agreement_id"]), "read", agreements_get, "contract register agreement"),
    ToolSpec("contracts.commitments.list", "List registered customer commitments (committed dates, weekly penalty, acceptance).", obj({"agreement_id": string(), "status": string()}), "read", commitments_list, "contract register commitment"),
    ToolSpec("contracts.credits.list", "List the credit ledger for an agreement or escalation (gross: issued, pending, voided, expired).", obj({"agreement_id": string(), "escalation_id": string(), "status": string()}), "read", credits_list, "credit ledger"),
    ToolSpec("contracts.credits.get", "Read one credit ledger entry.", obj({"credit_id": string()}, ["credit_id"]), "read", credits_get, "credit ledger entry"),
    ToolSpec(
        "contracts.credits.create",
        "Submit a credit memo against an agreement and escalation on a customer billing-run confirmation. The amount plus credits already issued or pending for the escalation may not exceed the agreement's cap.",
        obj(
            {
                "agreement_id": string(),
                "escalation_id": string(),
                "amount_usd": integer(minimum=1),
                "basis": {"type": "string", "enum": list(BASES)},
                "billing_option": {"type": "string", "enum": list(BILLING_OPTIONS)},
                "confirmation_id": string(),
                "note": string(),
            },
            ["agreement_id", "escalation_id", "amount_usd", "basis", "billing_option", "confirmation_id"],
        ),
        "write",
        credits_create,
        "credit memo",
        idempotent=False,
    ),
    ToolSpec("contracts.billing_runs.list", "List scheduled invoice runs with their credit-memo cut-off dates.", obj({"start_date": string(ISO_DATE), "end_date": string(ISO_DATE)}), "read", billing_runs_list, "billing run schedule"),
    ToolSpec("portal.confirmations.list", "List counterparty confirmations (partner staffing, customer change windows, customer billing runs).", obj({"customer_id": string(), "kind": string(), "status": string()}), "read", confirmations_list, "counterparty confirmation"),
    ToolSpec("portal.confirmations.get", "Read one counterparty confirmation: standard and expedited dates, fee, coverage, validity.", obj({"confirmation_id": string()}, ["confirmation_id"]), "read", confirmations_get, "counterparty confirmation"),
    ToolSpec("approvals.list", "List approval records, optionally by keyword.", obj({"q": string()}), "read", approvals_list, "approval workflow record"),
    ToolSpec("approvals.get", "Read one approval record with its exact scope and approver.", obj({"approval_id": string()}, ["approval_id"]), "read", approvals_get, "approval workflow record"),
    ToolSpec("mail.messages.list", "Search the delivery mailbox by keyword (subject, body, labels).", obj({"q": string(), "max_results": integer(minimum=1)}, ["q"]), "read", messages_list, "mailbox search"),
    ToolSpec("mail.messages.get", "Read one message with body and attachment list.", obj({"message_id": string()}, ["message_id"]), "read", messages_get, "mailbox message"),
    ToolSpec("chat.threads.list", "Search team chat threads by keyword.", obj({"q": string()}, ["q"]), "read", chat_threads_list, "team chat search"),
    ToolSpec("chat.threads.get", "Read one team chat thread.", obj({"thread_id": string()}, ["thread_id"]), "read", chat_threads_get, "team chat thread"),
    ToolSpec("drive.files.list", "Search shared-drive files by keyword (name, folder, content).", obj({"q": string()}, ["q"]), "read", drive_files_list, "shared drive search"),
    ToolSpec("drive.files.get", "Read shared-drive file metadata.", obj({"file_id": string()}, ["file_id"]), "read", drive_files_get, "shared drive file"),
    ToolSpec("drive.files.export", "Export a shared-drive file as text (spreadsheets as CSV, PDFs as extracted text).", obj({"file_id": string()}, ["file_id"]), "read", drive_files_export, "shared drive export"),
    ToolSpec(
        "notes.drafts.create",
        "Create, but do not send, a stakeholder draft note.",
        obj({"recipient": string(), "subject": string(), "body": string(), "related_escalation_id": string(), "related_customer_id": string()}, ["recipient", "subject", "body"]),
        "write",
        drafts_create,
        "collaboration draft",
        idempotent=False,
    ),
)

SERVERS = {
    "helpdesk": "Customer support desk: customer accounts, tickets with SLA timelines, escalations, and SLA policies.",
    "tracker": "Delivery tracker: issues, sprints, and planning-time capacity reports.",
    "wiki": "Team wiki: the Escalation Handling Standard and its version history.",
    "calendar": "Staff calendar: AM/PM blocks, leave, on-call shifts, and customer-facing session bookings.",
    "hris": "HRIS roster: employees, contractors, and certified skill levels.",
    "contracts": "Contract register: agreements, customer commitments, the credit ledger, and billing runs.",
    "portal": "Counterparty portal: partner staffing confirmations, customer change-window confirmations, and customer billing-run confirmations.",
    "approvals": "Approval workflow records with exact scope.",
    "mail": "Customer Delivery mailbox.",
    "chat": "Customer Delivery chat threads.",
    "drive": "Shared drive holding the standard, exports, registers, calendars, and confirmations.",
    "notes": "Stakeholder draft notes (never sent by the benchmark).",
}

__all__ = ["BASES", "BILLING_OPTIONS", "SERVERS", "TOOLS"]
