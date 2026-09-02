"""ITSMDesk provider-shaped tools over the family's SQLite world.

Read tools return ServiceNow-shaped ITSM records, Grafana/Prometheus-shaped
telemetry, the change calendar, a PagerDuty-shaped on-call plane, and vendor
advisories; write tools persist to the domain tables, refresh the affected
records, and record the exact payload for the sealed contract.  There is no
LLM anywhere here.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

from ...engine.families import ToolSpec
from ...engine.validation import integer, obj, string
from ...engine.world import World

BUDGET_UNIT = "BUDGET_MINUTE"
NODE_UNIT = "NODE"
WATCH_MINUTES_TIER1 = 120
OVERRIDE_MAX_HOURS = 12


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
        "lane": row["lane_id"],
        "primary_engineer": f"Engineer/{row['primary_engineer_id']}" if row.get("primary_engineer_id") else None,
        "runtime": row["runtime"],
        "version": row["version"],
        "required_certification": row.get("required_certification"),
        "validation_minutes": row["validation_minutes"],
        "rollback_minutes": row["rollback_minutes"],
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


def _incident(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "incident_id": row["incident_id"],
        "service": f"Service/{row['service_id']}",
        "opened_at": row["opened_at"],
        "resolved_at": row["resolved_at"],
        "severity": row["severity"],
        "impact_minutes": row["impact_minutes"],
        "slo_charged": bool(row["slo_charged"]),
        "problem": f"Problem/{row['problem_id']}" if row.get("problem_id") else None,
        "summary": row["summary"],
    }


def _change(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "change_id": row["change_id"],
        "state": row["state"],
        "type": row["change_type"],
        "service": f"Service/{row['service_id']}",
        "advisory": row.get("advisory_id"),
        "lane": row.get("lane_id"),
        "window": row.get("window_id"),
        "planned_start": row.get("planned_start"),
        "planned_end": row.get("planned_end"),
        "downtime_minutes": row["downtime_minutes"],
        "restarts": row["restarts"],
        "risk": row["risk"],
        "requested_by": f"Engineer/{row['requested_by']}",
        "summary": row["summary"],
        "opened_at": row["opened_at"],
        "meta": {"versionId": str(row["revision"]), "lastUpdated": row["last_updated"]},
    }


def _window(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["window_id"],
        "lane": row["lane_id"],
        "serviceDate": row["service_date"],
        "session": row["session"],
        "start": f"{row['service_date']}T{row['start_time']}",
        "end": f"{row['service_date']}T{row['end_time']}",
        "status": row["status"],
        "holdReason": row.get("hold_reason"),
        "change": row.get("change_id"),
    }


def _shift(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "shift_id": row["shift_id"],
        "schedule": f"Schedule/{row['schedule_id']}",
        "engineer": f"Engineer/{row['engineer_id']}",
        "engineer_name": row.get("name"),
        "certifications": (row.get("certifications") or "").split(",") if row.get("certifications") else [],
        "start": row["start_time"],
        "end": row["end_time"],
        "source": row["source"],
    }


def _advisory(row: dict[str, Any], vendor_name: str | None = None) -> dict[str, Any]:
    rendered = dict(row)
    if vendor_name is not None:
        rendered["vendor_name"] = vendor_name
    return rendered


# --------------------------------------------------------------------------- #
# Time helpers
# --------------------------------------------------------------------------- #


def _split_datetime(value: str, label: str) -> tuple[str, str]:
    if len(value) != 19 or value[10] != "T":
        raise ValueError(f"{label} must be YYYY-MM-DDTHH:MM:SS")
    date.fromisoformat(value[:10])
    return value[:10], value[11:]


def _minutes(start: str, end: str) -> int:
    start_date, start_time = _split_datetime(start, "start_time")
    end_date, end_time = _split_datetime(end, "end_time")
    if start_date != end_date:
        raise ValueError("start_time and end_time must fall on the same date")
    if start_time >= end_time:
        raise ValueError("start_time must precede end_time")
    sh, sm = int(start_time[:2]), int(start_time[3:5])
    eh, em = int(end_time[:2]), int(end_time[3:5])
    return (eh * 60 + em) - (sh * 60 + sm)


def _ts(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if value.endswith("23:59:59"):
        parsed += timedelta(seconds=1)
    return parsed


def _next_business_day(after: str) -> str:
    day = date.fromisoformat(after) + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.isoformat()


# --------------------------------------------------------------------------- #
# Policy helpers shared by the write tools
# --------------------------------------------------------------------------- #


def budget_state(world: World, service_id: str, day: str) -> dict[str, Any]:
    """Budget, charged, reserve, and spendable minutes of the service's active SLO on ``day``."""

    slo = world.one(
        "SELECT * FROM slos WHERE service_id = ? AND status = 'ACTIVE' ORDER BY slo_id",
        (service_id,),
        missing=f"Service/{service_id} has no active SLO",
    )
    window_start = (date.fromisoformat(day) - timedelta(days=int(slo["window_days"]))).isoformat()
    charged = world.one(
        "SELECT COALESCE(SUM(impact_minutes), 0) AS minutes FROM incidents WHERE service_id = ? AND slo_charged = 1 "
        "AND substr(opened_at, 1, 10) > ? AND substr(opened_at, 1, 10) <= ?",
        (service_id, window_start, day),
    )["minutes"]
    spendable = int(slo["budget_minutes"]) - int(charged) - int(slo["reserve_minutes"])
    return {
        "slo_id": slo["slo_id"],
        "evaluation_day": day,
        "window_start_exclusive": window_start,
        "budget_minutes": int(slo["budget_minutes"]),
        "charged_minutes": int(charged),
        "reserve_minutes": int(slo["reserve_minutes"]),
        "remaining_minutes": int(slo["budget_minutes"]) - int(charged),
        "spendable_minutes": spendable,
    }


def _require_budget(world: World, service: dict[str, Any], day: str, minutes: int, label: str) -> None:
    if minutes <= 0:
        return
    state = budget_state(world, service["service_id"], day)
    if minutes > state["spendable_minutes"]:
        raise ValueError(
            f"error budget policy: {label} needs {minutes} budget minutes on {day} but only {state['spendable_minutes']} are spendable "
            f"({state['budget_minutes']} budget - {state['charged_minutes']} charged - {state['reserve_minutes']} reserve); "
            "a budget exception needs the change board chair"
        )


def _lane(world: World, lane_id: str) -> dict[str, Any]:
    lane = world.one("SELECT * FROM change_lanes WHERE lane_id = ?", (lane_id,), missing=f"lane {lane_id} not found")
    if lane["status"] != "ACTIVE":
        raise ValueError(f"{lane_id} is {lane['status']}: {lane.get('status_note') or 'no changes accepted'}")
    return lane


def _require_capable(lane: dict[str, Any], service: dict[str, Any]) -> None:
    if service["tier"] == "tier-1" and not int(lane["tier1_capable"]):
        raise ValueError(f"{lane['lane_id']} is not certified for tier-1 changes; {service['code']} is {service['tier']}")


def _windows_for_interval(world: World, lane_id: str, start: str, end: str) -> list[dict[str, Any]]:
    _minutes(start, end)
    start_date, start_time = start[:10], start[11:]
    end_time = end[11:]
    rows = world.all("SELECT * FROM maintenance_windows WHERE lane_id = ? AND service_date = ? ORDER BY start_time", (lane_id, start_date))
    covering = [row for row in rows if row["start_time"] < end_time and row["end_time"] > start_time]
    if not covering:
        raise ValueError(f"no {lane_id} window covers {start} - {end}; sessions are NIGHT 01:00-05:00 and EVE 19:00-23:00")
    if start_time < min(row["start_time"] for row in covering) or end_time > max(row["end_time"] for row in covering):
        raise ValueError(f"{start} - {end} falls outside the {lane_id} sessions")
    if len(covering) > 1:
        raise ValueError("a change must start and end inside one session")
    return covering


def _require_free(windows: list[dict[str, Any]], *, holder: str | None = None) -> None:
    for row in windows:
        if row["status"] == "free":
            continue
        if holder and row.get("change_id") == holder:
            continue
        raise ValueError(
            f"{row['window_id']} is {row['status']}: {row.get('hold_reason') or 'not available'}; protected and blocked windows cannot be displaced without the change board chair"
        )


def _claim(world: World, tool: str, windows: list[dict[str, Any]], change_id: str) -> None:
    for row in windows:
        world.connection.execute(
            "UPDATE maintenance_windows SET status = 'busy', hold_reason = 'scheduled change', change_id = ? WHERE window_id = ?",
            (change_id, row["window_id"]),
        )
        world.audit(tool, "maintenance_windows", row["window_id"], "update", {"status": "busy", "change_id": change_id})


def _release(world: World, tool: str, change_id: str) -> None:
    for row in world.all("SELECT window_id FROM maintenance_windows WHERE change_id = ?", (change_id,)):
        world.connection.execute(
            "UPDATE maintenance_windows SET status = 'free', hold_reason = NULL, change_id = NULL WHERE window_id = ?",
            (row["window_id"],),
        )
        world.audit(tool, "maintenance_windows", row["window_id"], "update", {"status": "free", "change_id": None})


def secondary_coverage(world: World, service: dict[str, Any], start: str, end: str) -> list[tuple[str, str]]:
    """Certified secondary rotation shifts and active overrides overlapping ``[start, end]``."""

    certification = service.get("required_certification")
    intervals: list[tuple[str, str]] = []
    schedules = world.all("SELECT * FROM oncall_schedules WHERE service_id = ? AND role = 'secondary' ORDER BY schedule_id", (service["service_id"],))
    for schedule in schedules:
        shifts = world.all(
            "SELECT s.start_time, s.end_time, e.certifications FROM oncall_shifts s JOIN engineers e ON e.engineer_id = s.engineer_id "
            "WHERE s.schedule_id = ? AND s.start_time < ? AND s.end_time > ? ORDER BY s.start_time",
            (schedule["schedule_id"], end, start),
        )
        overrides = world.all(
            "SELECT o.start_time, o.end_time, e.certifications FROM oncall_overrides o JOIN engineers e ON e.engineer_id = o.engineer_id "
            "WHERE o.schedule_id = ? AND o.status = 'ACTIVE' AND o.start_time < ? AND o.end_time > ? ORDER BY o.start_time",
            (schedule["schedule_id"], end, start),
        )
        for row in [*shifts, *overrides]:
            if not certification or certification in (row["certifications"] or "").split(","):
                intervals.append((row["start_time"], row["end_time"]))
    return sorted(intervals)


def covers(intervals: list[tuple[str, str]], start: str, end: str) -> bool:
    cursor = _ts(start)
    target = _ts(end)
    for interval_start, interval_end in intervals:
        if _ts(interval_start) > cursor + timedelta(seconds=61):
            break
        cursor = max(cursor, _ts(interval_end))
        if cursor >= target:
            return True
    return cursor >= target


def _require_secondary(world: World, service: dict[str, Any], start: str, end: str) -> None:
    certification = service.get("required_certification")
    if not certification:
        return
    watch = WATCH_MINUTES_TIER1 if service["tier"] == "tier-1" else 0
    block_end = (_ts(end) + timedelta(minutes=watch)).strftime("%Y-%m-%dT%H:%M:%S")
    if not covers(secondary_coverage(world, service, start, block_end), start, block_end):
        raise ValueError(
            f"no certified secondary responder ({certification}) covers {start} - {block_end} on the {service['code']} secondary schedule; "
            "an on-call override needs the SRE lead"
        )


def _require_package_ready(world: World, advisory_id: str | None, day: str) -> None:
    if not advisory_id:
        return
    advisory = world.one("SELECT * FROM vendor_advisories WHERE advisory_id = ?", (advisory_id,), missing=f"advisory {advisory_id} not found")
    if advisory["status"] != "CURRENT":
        raise ValueError(f"advisory {advisory_id} is {advisory['status']}; use the current revision")
    earliest = _next_business_day(advisory["expedited_release_date"])
    if day < earliest:
        raise ValueError(f"the {advisory['reference']} package is not production-eligible before {earliest} (next business day after the earliest release date)")


# --------------------------------------------------------------------------- #
# ITSM reads
# --------------------------------------------------------------------------- #


def cis_search(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("identifier"):
        rows = world.all("SELECT * FROM services WHERE code = ? ORDER BY service_id", (args["identifier"],))
    elif args.get("name"):
        rows = world.all(
            "SELECT * FROM services WHERE instr(lower(name), lower(?)) > 0 OR instr(lower(code), lower(?)) > 0 ORDER BY service_id",
            (args["name"], args["name"]),
        )
    else:
        raise ValueError("identifier or name is required")
    return {"total": len(rows), "services": [_service(row) for row in rows]}


def cis_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _service(world.one("SELECT * FROM services WHERE service_id = ?", (args["service_id"],), missing=f"Service/{args['service_id']} not found"))


def nodes_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT service_id FROM services WHERE service_id = ?", (args["service_id"],), missing=f"Service/{args['service_id']} not found")
    if args.get("pool"):
        rows = world.all("SELECT * FROM nodes WHERE service_id = ? AND pool = ? ORDER BY node_id", (args["service_id"], args["pool"]))
    else:
        rows = world.all("SELECT * FROM nodes WHERE service_id = ? ORDER BY node_id", (args["service_id"],))
    return {"total": len(rows), "nodes": rows}


def meterings_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT service_id FROM services WHERE service_id = ?", (args["service_id"],), missing=f"Service/{args['service_id']} not found")
    if args.get("metric"):
        rows = world.all(
            "SELECT * FROM meterings WHERE service_id = ? AND metric = ? ORDER BY measured_at DESC, metering_id",
            (args["service_id"], args["metric"]),
        )
    else:
        rows = world.all("SELECT * FROM meterings WHERE service_id = ? ORDER BY measured_at DESC, metering_id", (args["service_id"],))
    return {"total": len(rows), "meterings": [_metering(row) for row in rows]}


def incidents_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT service_id FROM services WHERE service_id = ?", (args["service_id"],), missing=f"Service/{args['service_id']} not found")
    clauses, params = ["service_id = ?"], [args["service_id"]]
    if args.get("start_date"):
        clauses.append("substr(opened_at, 1, 10) >= ?")
        params.append(args["start_date"])
    if args.get("end_date"):
        clauses.append("substr(opened_at, 1, 10) <= ?")
        params.append(args["end_date"])
    if "slo_charged" in args:
        clauses.append("slo_charged = ?")
        params.append(1 if args["slo_charged"] else 0)
    rows = world.all(f"SELECT * FROM incidents WHERE {' AND '.join(clauses)} ORDER BY opened_at, incident_id", params)
    return {"total": len(rows), "incidents": [_incident(row) for row in rows]}


def incidents_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _incident(world.one("SELECT * FROM incidents WHERE incident_id = ?", (args["incident_id"],), missing=f"Incident/{args['incident_id']} not found"))


def problems_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM problems WHERE problem_id = ?", (args["problem_id"],), missing=f"Problem/{args['problem_id']} not found")
    incidents = world.all("SELECT incident_id, slo_charged, impact_minutes FROM incidents WHERE problem_id = ? ORDER BY incident_id", (row["problem_id"],))
    return {**row, "incidents": [{"incident_id": i["incident_id"], "slo_charged": bool(i["slo_charged"]), "impact_minutes": i["impact_minutes"]} for i in incidents]}


def changes_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("service_id", "state", "advisory_id", "lane_id"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    if not clauses:
        raise ValueError("at least one of service_id, state, advisory_id, lane_id is required")
    rows = world.all(f"SELECT * FROM change_requests WHERE {' AND '.join(clauses)} ORDER BY change_id", params)
    return {"total": len(rows), "changes": [_change(row) for row in rows]}


def changes_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _change(world.one("SELECT * FROM change_requests WHERE change_id = ?", (args["change_id"],), missing=f"Change/{args['change_id']} not found"))


def tasks_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM change_tasks WHERE task_id = ?", (args["task_id"],), missing=f"ChangeTask/{args['task_id']} not found"))


def outages_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM planned_outages WHERE outage_id = ?", (args["outage_id"],), missing=f"Outage/{args['outage_id']} not found"))


# --------------------------------------------------------------------------- #
# ITSM writes
# --------------------------------------------------------------------------- #


def _service_row(world: World, service_id: str) -> dict[str, Any]:
    return world.one("SELECT * FROM services WHERE service_id = ?", (service_id,), missing=f"Service/{service_id} not found")


def changes_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "itsm.changes.create"
    service = _service_row(world, args["service_id"])
    advisory = world.one("SELECT * FROM vendor_advisories WHERE advisory_id = ?", (args["advisory_id"],), missing=f"advisory {args['advisory_id']} not found")
    lane = _lane(world, args["lane_id"])
    _require_capable(lane, service)
    start, end = args["start_time"], args["end_time"]
    interval = _minutes(start, end)
    downtime = int(args["downtime_minutes"])
    if downtime > interval:
        raise ValueError("downtime_minutes cannot exceed the planned interval")
    _require_package_ready(world, advisory["advisory_id"], start[:10])
    windows = _windows_for_interval(world, lane["lane_id"], start, end)
    _require_free(windows)
    _require_budget(world, service, start[:10], downtime, f"the {service['code']} change")
    _require_secondary(world, service, start, end)
    change_id = world.next_id("change_requests", "change_id", "CHG-")
    row = {
        "change_id": change_id,
        "service_id": service["service_id"],
        "advisory_id": advisory["advisory_id"],
        "change_type": args["change_type"],
        "state": "scheduled",
        "lane_id": lane["lane_id"],
        "window_id": windows[0]["window_id"],
        "planned_start": start,
        "planned_end": end,
        "downtime_minutes": downtime,
        "restarts": int(advisory["restarts_required"]),
        "risk": "moderate" if service["tier"] == "tier-1" else "low",
        "requested_by": service["primary_engineer_id"],
        "summary": f"{advisory['reference']} remediation for {service['code']}",
        "opened_at": world.clock(),
        "revision": 1,
        "last_updated": world.clock(),
    }
    world.connection.execute(
        "INSERT INTO change_requests (change_id, service_id, advisory_id, change_type, state, lane_id, window_id, planned_start, planned_end, downtime_minutes, restarts, risk, requested_by, summary, opened_at, revision, last_updated) "
        "VALUES (:change_id, :service_id, :advisory_id, :change_type, :state, :lane_id, :window_id, :planned_start, :planned_end, :downtime_minutes, :restarts, :risk, :requested_by, :summary, :opened_at, :revision, :last_updated)",
        row,
    )
    world.audit(tool, "change_requests", change_id, "insert", row)
    _claim(world, tool, windows, change_id)
    world.record_mutation(tool, "change_requests", change_id, "scheduled", args)
    return _change(row)


def changes_update(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "itsm.changes.update"
    current = world.one("SELECT * FROM change_requests WHERE change_id = ?", (args["change_id"],), missing=f"Change/{args['change_id']} not found")
    if current["state"] in {"implemented", "closed", "cancelled"}:
        raise ValueError(f"Change/{args['change_id']} is {current['state']} and cannot be changed")
    changes = {key: args[key] for key in ("lane_id", "start_time", "end_time", "state", "downtime_minutes") if key in args}
    if not changes:
        raise ValueError("no change requested")
    service = _service_row(world, current["service_id"])
    updated = {
        **current,
        "lane_id": changes.get("lane_id", current["lane_id"]),
        "planned_start": changes.get("start_time", current["planned_start"]),
        "planned_end": changes.get("end_time", current["planned_end"]),
        "state": changes.get("state", "scheduled" if ("start_time" in changes or "lane_id" in changes) else current["state"]),
        "downtime_minutes": int(changes.get("downtime_minutes", current["downtime_minutes"])),
    }
    new_state = updated["state"]
    if new_state == "cancelled":
        _release(world, tool, current["change_id"])
        updated["window_id"] = None
    else:
        if new_state not in {"scheduled", "pending"}:
            raise ValueError(f"unsupported state transition to {new_state}")
        rebook = any(key in changes for key in ("lane_id", "start_time", "end_time")) or current["state"] != "scheduled"
        if rebook:
            if not (updated.get("lane_id") and updated.get("planned_start") and updated.get("planned_end")):
                raise ValueError("scheduling a change needs lane_id, start_time, and end_time")
            lane = _lane(world, updated["lane_id"])
            _require_capable(lane, service)
            start, end = updated["planned_start"], updated["planned_end"]
            interval = _minutes(start, end)
            if updated["downtime_minutes"] > interval:
                raise ValueError("downtime_minutes cannot exceed the planned interval")
            _require_package_ready(world, current.get("advisory_id"), start[:10])
            windows = _windows_for_interval(world, lane["lane_id"], start, end)
            _require_free(windows, holder=current["change_id"])
            _require_budget(world, service, start[:10], updated["downtime_minutes"], f"Change/{current['change_id']}")
            _require_secondary(world, service, start, end)
            _release(world, tool, current["change_id"])
            _claim(world, tool, windows, current["change_id"])
            updated["window_id"] = windows[0]["window_id"]
    updated["revision"] = int(current["revision"]) + 1
    updated["last_updated"] = world.clock()
    world.connection.execute(
        "UPDATE change_requests SET lane_id = :lane_id, window_id = :window_id, planned_start = :planned_start, planned_end = :planned_end, state = :state, "
        "downtime_minutes = :downtime_minutes, revision = :revision, last_updated = :last_updated WHERE change_id = :change_id",
        updated,
    )
    world.audit(tool, "change_requests", current["change_id"], "update", changes)
    world.record_mutation(tool, "change_requests", current["change_id"], new_state, args, revision=updated["revision"])
    return _change(updated)


def tasks_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "itsm.tasks.create"
    change = world.one("SELECT * FROM change_requests WHERE change_id = ?", (args["change_id"],), missing=f"Change/{args['change_id']} not found")
    if change["state"] not in {"scheduled", "authorize", "assess"}:
        raise ValueError(f"Change/{args['change_id']} is {change['state']} and cannot take a new task")
    if not change.get("lane_id"):
        raise ValueError(f"Change/{args['change_id']} has no lane; schedule it first")
    service = _service_row(world, change["service_id"])
    start, end = args["start_time"], args["end_time"]
    _minutes(start, end)
    windows = _windows_for_interval(world, change["lane_id"], start, end)
    _require_free(windows, holder=change["change_id"])
    node_count = int(args["node_count"])
    pool = world.all(
        "SELECT * FROM nodes WHERE service_id = ? AND lane_id = ? AND status = 'active' ORDER BY node_id",
        (service["service_id"], change["lane_id"]),
    )
    patchable = [row for row in pool if not row.get("pinned_for")]
    if node_count > len(patchable):
        raise ValueError(
            f"{change['lane_id']} holds {len(patchable)} unpinned active {service['code']} nodes; pinned nodes are never patched before the pin ends"
        )
    state = budget_state(world, service["service_id"], start[:10])
    if state["remaining_minutes"] * 2 < state["budget_minutes"]:
        cap = len(pool) // 2
        if node_count > cap:
            raise ValueError(
                f"rolling batch cap: remaining budget {state['remaining_minutes']} of {state['budget_minutes']} minutes is below half the window budget, "
                f"so a batch may not exceed {cap} of the {len(pool)} active {service['code']} nodes on {change['lane_id']}"
            )
    _require_secondary(world, service, start, end)
    if not any(row.get("change_id") == change["change_id"] for row in windows):
        _claim(world, tool, windows, change["change_id"])
    task_id = world.next_id("change_tasks", "task_id", "CTASK-")
    row = {
        "task_id": task_id,
        "change_id": change["change_id"],
        "kind": args["kind"],
        "node_count": node_count,
        "window_id": windows[0]["window_id"],
        "planned_start": start,
        "planned_end": end,
        "status": "planned",
        "requested_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO change_tasks (task_id, change_id, kind, node_count, window_id, planned_start, planned_end, status, requested_by, created_at, revision) "
        "VALUES (:task_id, :change_id, :kind, :node_count, :window_id, :planned_start, :planned_end, :status, :requested_by, :created_at, :revision)",
        row,
    )
    world.audit(tool, "change_tasks", task_id, "insert", row)
    world.record_mutation(tool, "change_tasks", task_id, "planned", args)
    return dict(row)


def outages_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "itsm.outages.create"
    service = _service_row(world, args["service_id"])
    change = world.one("SELECT * FROM change_requests WHERE change_id = ?", (args["change_id"],), missing=f"Change/{args['change_id']} not found")
    if change["service_id"] != service["service_id"]:
        raise ValueError(f"Change/{change['change_id']} belongs to Service/{change['service_id']}, not {service['service_id']}")
    if change["state"] != "scheduled" or not change.get("planned_start"):
        raise ValueError(f"Change/{change['change_id']} is {change['state']}; a planned-outage notice needs a scheduled change")
    start, end = args["start_time"], args["end_time"]
    duration = _minutes(start, end)
    if start < change["planned_start"] or end > change["planned_end"]:
        raise ValueError(f"the notice {start} - {end} falls outside Change/{change['change_id']}'s planned interval {change['planned_start']} - {change['planned_end']}")
    downtime = int(args["downtime_minutes"])
    if downtime > duration:
        raise ValueError("downtime_minutes cannot exceed the notice length")
    _require_budget(world, service, start[:10], duration, f"the {service['code']} planned-outage notice")
    outage_id = world.next_id("planned_outages", "outage_id", "OUT-")
    row = {
        "outage_id": outage_id,
        "service_id": service["service_id"],
        "change_id": change["change_id"],
        "window_id": change.get("window_id"),
        "start_time": start,
        "end_time": end,
        "duration_minutes": duration,
        "downtime_minutes": downtime,
        "status": "planned",
        "requested_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO planned_outages (outage_id, service_id, change_id, window_id, start_time, end_time, duration_minutes, downtime_minutes, status, requested_by, created_at, revision) "
        "VALUES (:outage_id, :service_id, :change_id, :window_id, :start_time, :end_time, :duration_minutes, :downtime_minutes, :status, :requested_by, :created_at, :revision)",
        row,
    )
    world.audit(tool, "planned_outages", outage_id, "insert", row)
    world.record_mutation(tool, "planned_outages", outage_id, "planned", args)
    return dict(row)


# --------------------------------------------------------------------------- #
# Telemetry
# --------------------------------------------------------------------------- #


def slos_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT service_id FROM services WHERE service_id = ?", (args["service_id"],), missing=f"Service/{args['service_id']} not found")
    return {"slos": world.all("SELECT * FROM slos WHERE service_id = ? ORDER BY slo_id", (args["service_id"],))}


def slos_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM slos WHERE slo_id = ?", (args["slo_id"],), missing=f"SLO {args['slo_id']} not found"))


def budget_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    slo = world.one("SELECT * FROM slos WHERE slo_id = ?", (args["slo_id"],), missing=f"SLO {args['slo_id']} not found")
    as_of = world.task["as_of"]
    window_start = (date.fromisoformat(as_of) - timedelta(days=int(slo["window_days"]))).isoformat()
    latest = world.connection.execute(
        "SELECT * FROM burn_samples WHERE slo_id = ? ORDER BY sampled_at DESC, sample_id LIMIT 1", (slo["slo_id"],)
    ).fetchone()
    sample = dict(latest) if latest else None
    return {
        "slo_id": slo["slo_id"],
        "service": f"Service/{slo['service_id']}",
        "name": slo["name"],
        "objective_pct": slo["objective_pct"],
        "window_days": slo["window_days"],
        "window": {"start_exclusive": window_start, "end": as_of},
        "budget_minutes": slo["budget_minutes"],
        "reserve_minutes": slo["reserve_minutes"],
        "raw_consumed_minutes": sample["raw_consumed_minutes"] if sample else None,
        "burn_rate_1h": sample["burn_rate_1h"] if sample else None,
        "burn_rate_6h": sample["burn_rate_6h"] if sample else None,
        "sampled_at": sample["sampled_at"] if sample else None,
        "note": "Raw SLI burn is informational; the charged incident ledger governs consumed budget (policy section 2).",
    }


def burn_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT slo_id FROM slos WHERE slo_id = ?", (args["slo_id"],), missing=f"SLO {args['slo_id']} not found")
    clauses, params = ["slo_id = ?"], [args["slo_id"]]
    if args.get("start_date"):
        clauses.append("substr(sampled_at, 1, 10) >= ?")
        params.append(args["start_date"])
    if args.get("end_date"):
        clauses.append("substr(sampled_at, 1, 10) <= ?")
        params.append(args["end_date"])
    return {"samples": world.all(f"SELECT * FROM burn_samples WHERE {' AND '.join(clauses)} ORDER BY sampled_at, sample_id", params)}


def alerts_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT service_id FROM services WHERE service_id = ?", (args["service_id"],), missing=f"Service/{args['service_id']} not found")
    clauses, params = ["service_id = ?"], [args["service_id"]]
    if args.get("start_date"):
        clauses.append("substr(fired_at, 1, 10) >= ?")
        params.append(args["start_date"])
    if args.get("end_date"):
        clauses.append("substr(fired_at, 1, 10) <= ?")
        params.append(args["end_date"])
    return {"alerts": world.all(f"SELECT * FROM alerts WHERE {' AND '.join(clauses)} ORDER BY fired_at, alert_id", params)}


# --------------------------------------------------------------------------- #
# Change calendar
# --------------------------------------------------------------------------- #


def lanes_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return {"lanes": world.all("SELECT * FROM change_lanes ORDER BY lane_id")}


def freezes_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    rows = world.all(
        "SELECT * FROM freeze_windows WHERE start_date <= ? AND end_date >= ? ORDER BY start_date, freeze_id",
        (args["end_date"], args["start_date"]),
    )
    return {"freezes": [{**row, "lanes": row["lanes"].split(",") if row["lanes"] != "ALL" else ["ALL"]} for row in rows]}


def windows_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses = ["service_date >= ?", "service_date <= ?"]
    params: list[Any] = [args["start_date"], args["end_date"]]
    if args.get("lane_id"):
        clauses.append("lane_id = ?")
        params.append(args["lane_id"])
    if args.get("status"):
        clauses.append("status = ?")
        params.append(args["status"])
    rows = world.all(f"SELECT * FROM maintenance_windows WHERE {' AND '.join(clauses)} ORDER BY service_date, lane_id, start_time", params)
    return {"windows": [_window(row) for row in rows]}


# --------------------------------------------------------------------------- #
# On-call
# --------------------------------------------------------------------------- #


def schedules_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT service_id FROM services WHERE service_id = ?", (args["service_id"],), missing=f"Service/{args['service_id']} not found")
    return {"schedules": world.all("SELECT * FROM oncall_schedules WHERE service_id = ? ORDER BY schedule_id", (args["service_id"],))}


def shifts_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT schedule_id FROM oncall_schedules WHERE schedule_id = ?", (args["schedule_id"],), missing=f"schedule {args['schedule_id']} not found")
    rows = world.all(
        "SELECT s.*, e.name, e.certifications FROM oncall_shifts s JOIN engineers e ON e.engineer_id = s.engineer_id "
        "WHERE s.schedule_id = ? AND substr(s.start_time, 1, 10) >= ? AND substr(s.start_time, 1, 10) <= ? ORDER BY s.start_time, s.shift_id",
        (args["schedule_id"], args["start_date"], args["end_date"]),
    )
    return {"total": len(rows), "shifts": [_shift(row) for row in rows]}


def escalations_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM escalation_policies WHERE service_id = ?", (args["service_id"],), missing=f"no escalation policy for Service/{args['service_id']}")
    return {"policy_id": row["policy_id"], "service": f"Service/{row['service_id']}", "name": row["name"], "levels": json.loads(row["levels_json"])}


def users_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM engineers WHERE engineer_id = ?", (args["engineer_id"],), missing="engineer not found")
    return {"engineer_id": row["engineer_id"], "name": row["name"], "role": row["role"], "team": row["team"], "certifications": row["certifications"].split(",") if row["certifications"] else []}


def overrides_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM oncall_overrides WHERE override_id = ?", (args["override_id"],), missing=f"override {args['override_id']} not found"))


def overrides_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "oncall.overrides.create"
    schedule = world.one("SELECT * FROM oncall_schedules WHERE schedule_id = ?", (args["schedule_id"],), missing=f"schedule {args['schedule_id']} not found")
    engineer = world.one("SELECT * FROM engineers WHERE engineer_id = ?", (args["engineer_id"],), missing=f"engineer {args['engineer_id']} not found")
    certification = schedule.get("required_certification")
    if certification and certification not in (engineer["certifications"] or "").split(","):
        raise ValueError(f"{engineer['engineer_id']} does not hold {certification}; {schedule['schedule_id']} requires a certified responder")
    start, end = args["start_time"], args["end_time"]
    minutes = _minutes(start, end)
    if minutes % 60:
        raise ValueError("overrides are booked in whole hours")
    hours = minutes // 60
    if hours > OVERRIDE_MAX_HOURS:
        raise ValueError(f"an override may not exceed {OVERRIDE_MAX_HOURS} hours")
    clash = world.all(
        "SELECT override_id FROM oncall_overrides WHERE schedule_id = ? AND status = 'ACTIVE' AND start_time < ? AND end_time > ?",
        (schedule["schedule_id"], end, start),
    )
    if clash:
        raise ValueError(f"{clash[0]['override_id']} already covers part of {start} - {end} on {schedule['schedule_id']}")
    override_id = world.next_id("oncall_overrides", "override_id", "OVR-")
    row = {
        "override_id": override_id,
        "schedule_id": schedule["schedule_id"],
        "engineer_id": engineer["engineer_id"],
        "start_time": start,
        "end_time": end,
        "hours": hours,
        "status": "ACTIVE",
        "requested_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO oncall_overrides (override_id, schedule_id, engineer_id, start_time, end_time, hours, status, requested_by, created_at, revision) "
        "VALUES (:override_id, :schedule_id, :engineer_id, :start_time, :end_time, :hours, :status, :requested_by, :created_at, :revision)",
        row,
    )
    world.audit(tool, "oncall_overrides", override_id, "insert", row)
    world.record_mutation(tool, "oncall_overrides", override_id, "ACTIVE", args)
    return dict(row)


# --------------------------------------------------------------------------- #
# Vendor portal, approvals, collaboration surfaces
# --------------------------------------------------------------------------- #


def advisories_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("vendor_id", "product", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"advisories": [_advisory(row) for row in world.all(f"SELECT * FROM vendor_advisories {where} ORDER BY advisory_id", params)]}


def advisories_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM vendor_advisories WHERE advisory_id = ?", (args["advisory_id"],), missing=f"advisory {args['advisory_id']} not found")
    vendor = world.one("SELECT * FROM vendors WHERE vendor_id = ?", (row["vendor_id"],))
    return _advisory(row, vendor["name"])


def approvals_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("q"):
        rows = world.all(
            "SELECT * FROM approvals WHERE instr(lower(subject), lower(?)) > 0 OR instr(lower(scope_json), lower(?)) > 0 ORDER BY approval_id",
            (args["q"], args["q"]),
        )
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
    return {
        "messages": [
            {"id": row["message_id"], "thread_id": row["thread_id"], "channel": row["channel"], "from": row["sender"], "subject": row["subject"], "sent_at": row["sent_at"], "labels": row["labels"]}
            for row in rows[:limit]
        ]
    }


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
        "related_change_id": args.get("related_change_id"),
        "related_service_id": args.get("related_service_id"),
        "created_at": world.clock(),
        "status": "DRAFT",
    }
    world.connection.execute(
        "INSERT INTO note_drafts (draft_id, recipient, subject, body, related_change_id, related_service_id, created_at, status) "
        "VALUES (:draft_id, :recipient, :subject, :body, :related_change_id, :related_service_id, :created_at, :status)",
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
    ToolSpec("itsm.cis.search", "Search configuration items (services) by immutable service code or by name.", obj({"identifier": string("service code"), "name": string("name fragment")}), "read", cis_search, "ITSM CI search"),
    ToolSpec("itsm.cis.get", "Read one service CI: tier, lane, runtime, version, required responder certification, validation and rollback minutes.", obj({"service_id": string()}, ["service_id"]), "read", cis_get, "ITSM CI record"),
    ToolSpec("itsm.nodes.list", "List the nodes of a service with pool, lane, version, staged build state, and canary pins.", obj({"service_id": string(), "pool": string()}, ["service_id"]), "read", nodes_list, "ITSM node inventory"),
    ToolSpec("itsm.meterings.list", "List measured restart-to-healthy (RESTART-MIN) or node drain (DRAIN-MIN) meterings for a service, newest first.", obj({"service_id": string(), "metric": string("metric code")}, ["service_id"]), "read", meterings_list, "ITSM change metering"),
    ToolSpec("itsm.incidents.list", "List incidents for a service by opened-date window and SLO-charged flag, with charged impact minutes and problem links.", obj({"service_id": string(), "start_date": string("ISO date"), "end_date": string("ISO date"), "slo_charged": {"type": "boolean"}}, ["service_id"]), "read", incidents_list, "ITSM incident ledger"),
    ToolSpec("itsm.incidents.get", "Read one incident.", obj({"incident_id": string()}, ["incident_id"]), "read", incidents_get, "ITSM incident record"),
    ToolSpec("itsm.problems.get", "Read one problem record with its review note and the incidents it charged or reclassified.", obj({"problem_id": string()}, ["problem_id"]), "read", problems_get, "ITSM problem record"),
    ToolSpec("itsm.changes.list", "List change requests by service, state, advisory, or lane.", obj({"service_id": string(), "state": string(), "advisory_id": string(), "lane_id": string()}), "read", changes_list, "ITSM change search"),
    ToolSpec("itsm.changes.get", "Read one change request with lane, window, planned interval, downtime, and revision.", obj({"change_id": string()}, ["change_id"]), "read", changes_get, "ITSM change record"),
    ToolSpec(
        "itsm.changes.create",
        "Raise and schedule a change against a current advisory on a lane window. The lane must be active and certified for the service tier, every window the interval touches must be free, the package must be production-eligible, the downtime must fit the spendable error budget, and a certified secondary must cover the block.",
        obj(
            {
                "service_id": string(),
                "advisory_id": string(),
                "change_type": {"type": "string", "enum": ["standard", "normal", "emergency"]},
                "lane_id": string(),
                "start_time": string(DATETIME),
                "end_time": string(DATETIME),
                "downtime_minutes": integer(minimum=0),
            },
            ["service_id", "advisory_id", "change_type", "lane_id", "start_time", "end_time", "downtime_minutes"],
        ),
        "write",
        changes_create,
        "ITSM change create",
        idempotent=False,
    ),
    ToolSpec(
        "itsm.changes.update",
        "Schedule, move, re-lane, or cancel an existing change request. Scheduling re-validates the lane, windows, package eligibility, error budget, and secondary coverage; the record revision increments.",
        obj(
            {
                "change_id": string(),
                "lane_id": string(),
                "start_time": string(DATETIME),
                "end_time": string(DATETIME),
                "state": {"type": "string", "enum": ["scheduled", "pending", "cancelled"]},
                "downtime_minutes": integer(minimum=0),
            },
            ["change_id"],
        ),
        "write",
        changes_update,
        "ITSM change update",
        idempotent=False,
    ),
    ToolSpec("itsm.tasks.get", "Read one change task (implementation batch).", obj({"task_id": string()}, ["task_id"]), "read", tasks_get, "ITSM change task"),
    ToolSpec(
        "itsm.tasks.create",
        "Add an implementation task (rolling batch) to a scheduled change with an exact node count. Pinned nodes and nodes on another lane never count; the error-budget batch cap applies.",
        obj(
            {"change_id": string(), "kind": {"type": "string", "enum": ["rolling_batch", "canary", "validation"]}, "node_count": integer(minimum=1), "start_time": string(DATETIME), "end_time": string(DATETIME)},
            ["change_id", "kind", "node_count", "start_time", "end_time"],
        ),
        "write",
        tasks_create,
        "ITSM change task create",
        idempotent=False,
    ),
    ToolSpec("itsm.outages.get", "Read one planned-outage notice.", obj({"outage_id": string()}, ["outage_id"]), "read", outages_get, "ITSM planned outage"),
    ToolSpec(
        "itsm.outages.create",
        "Create a planned-outage notice for a scheduled change: the notice interval must sit inside the change's planned interval and fit the spendable error budget on that day.",
        obj(
            {"service_id": string(), "change_id": string(), "start_time": string(DATETIME), "end_time": string(DATETIME), "downtime_minutes": integer(minimum=0)},
            ["service_id", "change_id", "start_time", "end_time", "downtime_minutes"],
        ),
        "write",
        outages_create,
        "ITSM planned outage create",
        idempotent=False,
    ),
    ToolSpec("telemetry.slos.list", "List the SLOs published for a service.", obj({"service_id": string()}, ["service_id"]), "read", slos_list, "SLO catalog"),
    ToolSpec("telemetry.slos.get", "Read one SLO: objective, rolling window, whole-minute budget, and reserve floor.", obj({"slo_id": string()}, ["slo_id"]), "read", slos_get, "SLO definition"),
    ToolSpec("telemetry.budget.get", "Read the error-budget view of one SLO as of the planning date: window bounds, budget, reserve, and the raw SLI burn from the latest sample (informational).", obj({"slo_id": string()}, ["slo_id"]), "read", budget_get, "error budget view"),
    ToolSpec("telemetry.burn.list", "List burn-rate samples for an SLO by sample-date window.", obj({"slo_id": string(), "start_date": string("ISO date"), "end_date": string("ISO date")}, ["slo_id"]), "read", burn_list, "burn-rate history"),
    ToolSpec("telemetry.alerts.list", "List fired alerts for a service by date window.", obj({"service_id": string(), "start_date": string("ISO date"), "end_date": string("ISO date")}, ["service_id"]), "read", alerts_list, "alert history"),
    ToolSpec("calendar.lanes.list", "List change lanes with weekday policy, tier-1 certification, and status.", obj({}), "read", lanes_list, "change-lane roster"),
    ToolSpec("calendar.freezes.list", "List freeze windows overlapping a date range with the lanes and authority they name.", obj({"start_date": string("ISO date"), "end_date": string("ISO date")}, ["start_date", "end_date"]), "read", freezes_list, "freeze register"),
    ToolSpec("calendar.windows.list", "List maintenance windows between two dates with free / busy / protected / blocked status, optionally for one lane.", obj({"start_date": string("ISO date"), "end_date": string("ISO date"), "lane_id": string(), "status": string()}, ["start_date", "end_date"]), "read", windows_list, "change-window calendar"),
    ToolSpec("oncall.schedules.list", "List on-call schedules (primary / secondary) for a service with the certification each requires.", obj({"service_id": string()}, ["service_id"]), "read", schedules_list, "on-call schedules"),
    ToolSpec("oncall.shifts.list", "List rostered shifts of a schedule by date window with each responder's certifications.", obj({"schedule_id": string(), "start_date": string("ISO date"), "end_date": string("ISO date")}, ["schedule_id", "start_date", "end_date"]), "read", shifts_list, "on-call roster"),
    ToolSpec("oncall.escalations.get", "Read the escalation policy of a service.", obj({"service_id": string()}, ["service_id"]), "read", escalations_get, "escalation policy"),
    ToolSpec("oncall.users.get", "Read one responder with role, team, and certifications.", obj({"engineer_id": string()}, ["engineer_id"]), "read", users_get, "on-call user"),
    ToolSpec("oncall.overrides.get", "Read one on-call override.", obj({"override_id": string()}, ["override_id"]), "read", overrides_get, "on-call override"),
    ToolSpec(
        "oncall.overrides.create",
        "Create an on-call override on a schedule for an engineer over a whole-hour interval. The engineer must hold the schedule's certification; overlapping overrides are rejected.",
        obj({"schedule_id": string(), "engineer_id": string(), "start_time": string(DATETIME), "end_time": string(DATETIME)}, ["schedule_id", "engineer_id", "start_time", "end_time"]),
        "write",
        overrides_create,
        "on-call override create",
        idempotent=False,
    ),
    ToolSpec("vendor.advisories.list", "List vendor advisories, optionally by vendor, product, or status.", obj({"vendor_id": string(), "product": string(), "status": string()}), "read", advisories_list, "vendor advisory list"),
    ToolSpec("vendor.advisories.get", "Read one advisory: affected and fixed versions, restarts required, vendor estimate, standard and early-access release dates, fee, SLA.", obj({"advisory_id": string()}, ["advisory_id"]), "read", advisories_get, "vendor advisory"),
    ToolSpec("approvals.list", "List approval records, optionally by keyword.", obj({"q": string()}), "read", approvals_list, "approval workflow record"),
    ToolSpec("approvals.get", "Read one approval record with its exact scope and approver.", obj({"approval_id": string()}, ["approval_id"]), "read", approvals_get, "approval workflow record"),
    ToolSpec("messages.list", "Search the service-operations mailbox by keyword (subject, body, labels).", obj({"q": string(), "max_results": integer(minimum=1)}, ["q"]), "read", messages_list, "mailbox search"),
    ToolSpec("messages.get", "Read one message with body and attachment list.", obj({"message_id": string()}, ["message_id"]), "read", messages_get, "mailbox message"),
    ToolSpec("chat.threads.list", "Search team chat threads by keyword.", obj({"q": string()}, ["q"]), "read", chat_threads_list, "team chat search"),
    ToolSpec("chat.threads.get", "Read one team chat thread.", obj({"thread_id": string()}, ["thread_id"]), "read", chat_threads_get, "team chat thread"),
    ToolSpec("drive.files.list", "Search shared-drive files by keyword (name, folder, content).", obj({"q": string()}, ["q"]), "read", drive_files_list, "shared drive search"),
    ToolSpec("drive.files.get", "Read shared-drive file metadata.", obj({"file_id": string()}, ["file_id"]), "read", drive_files_get, "shared drive file"),
    ToolSpec("drive.files.export", "Export a shared-drive file as text (spreadsheets as CSV, PDFs as extracted text).", obj({"file_id": string()}, ["file_id"]), "read", drive_files_export, "shared drive export"),
    ToolSpec(
        "notes.drafts.create",
        "Create, but do not send, a stakeholder draft note (CAB note, requester update).",
        obj({"recipient": string(), "subject": string(), "body": string(), "related_change_id": string(), "related_service_id": string()}, ["recipient", "subject", "body"]),
        "write",
        drafts_create,
        "collaboration draft",
        idempotent=False,
    ),
)

SERVERS = {
    "itsm": "IT service management: service CIs, nodes, meterings, incidents, problems, change requests, change tasks, and planned-outage notices.",
    "telemetry": "Observability: SLO definitions, error-budget views, burn-rate samples, and alert history.",
    "calendar": "Change calendar: change lanes, freeze register, and the maintenance-window calendar.",
    "oncall": "On-call plane: schedules, rostered shifts, escalation policies, responders, and overrides.",
    "vendor": "Vendor patch portal: advisories with affected versions, restart requirements, release dates, and premium-support fees.",
    "approvals": "Approval workflow records with exact scope.",
    "messages": "Service-operations mailbox.",
    "chat": "Service-operations chat threads.",
    "drive": "Shared drive holding policies, registers, calendars, and exports.",
    "notes": "Stakeholder draft notes (never sent by the benchmark).",
}

__all__ = ["BUDGET_UNIT", "NODE_UNIT", "SERVERS", "TOOLS", "WATCH_MINUTES_TIER1", "budget_state", "covers", "secondary_coverage"]
