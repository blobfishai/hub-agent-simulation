"""Assemble ITSMDesk tasks: seed tables, scattered evidence, decision model, sealed contract.

Every declared number in a scenario is recomputed from the seeded world
(incident ledger, SLO budgets, node inventory, change calendar, on-call roster,
vendor advisories) and the build fails on any disagreement, so the answer
contract can never drift from the data the agent actually sees.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

from ...engine.assets import CSV, EML, JSON, MARKDOWN, PDF, XLSX, YAML, asset, eml, yaml_lines
from ...engine.catalog import answer_checks, build_rubric_milestones, milestone_descriptions, sequence_signature
from ...engine.decision import DecisionInputs, answer_schema, build_decision_model
from ...engine.families import CONTEXT_TOOL, SUBMIT_TOOL
from ...engine.quality_assets import quality_support_assets, quality_support_investigations, scoped_csv, scoped_markdown
from . import tools as itsm_tools
from .policy import SUPERSEDED_POLICY, effective_policy
from .scenarios import scenarios
from .specs import (
    AS_OF,
    ENGINEERS,
    ORGANIZATION,
    SESSION_TIMES,
    SESSIONS,
    USERS,
    VENDORS,
    WINDOW_HOURS,
    WINDOW_MINUTES,
    Change,
    Scenario,
    Service,
    calendar_days,
    certified,
    consumed_minutes,
    downtime_minutes,
    is_weekend,
    minutes_between,
    next_business_day,
    shifts_for,
    spendable_minutes,
    window_id,
)

BENCHMARK = "HubBench"
FAMILY_SLUG = "itsmdesk"
FAMILY_VERSION = "1.0.0"
PRIMARY_KEYS = {
    "change_requests": "change_id",
    "change_tasks": "task_id",
    "planned_outages": "outage_id",
    "oncall_overrides": "override_id",
}
ITEM_FIELD = {"plan": "coverage_item_or_resource", "quantity": "controlled_item_or_record", "schedule": "affected_resource_or_operation"}
GAP_FIELD = {"plan": "shortage_quantity", "quantity": "transaction_quantity", "schedule": "capacity_gap"}
CASE_FOLDER = "Service Operations/Cases/{case}"
POLICY_QUERY = "policy"
OPEN_SOURCE_ANCHORS = (
    {
        "name": "ITSM-Bench",
        "harbor_dataset": "vibrantlabsai/itsm-bench",
        "harbor_url": "https://hub.harborframework.com/datasets/vibrantlabsai/itsm-bench/latest",
        "upstream_url": "https://hub.harborframework.com/datasets/vibrantlabsai/itsm-bench",
        "license": "per the Harbor Hub listing; nothing from it is redistributed here",
        "evaluation_shape": "IT service-management ticket handling with deterministic end-state checks",
    },
    {
        "name": "o11y-bench",
        "harbor_dataset": "grafana/o11y-bench",
        "harbor_url": "https://hub.harborframework.com/datasets/grafana/o11y-bench/latest",
        "upstream_url": "https://hub.harborframework.com/datasets/grafana/o11y-bench",
        "license": "per the Harbor Hub listing; nothing from it is redistributed here",
        "evaluation_shape": "observability investigations over telemetry with graded conclusions",
    },
    {
        "name": "otel-bench",
        "harbor_dataset": "quesma/otel-bench",
        "harbor_url": "https://hub.harborframework.com/datasets/quesma/otel-bench/latest",
        "upstream_url": "https://hub.harborframework.com/datasets/quesma/otel-bench",
        "license": "per the Harbor Hub listing; nothing from it is redistributed here",
        "evaluation_shape": "telemetry-pipeline tasks with executable verification",
    },
)
PLAN_SELECTED_OPTIONS = {
    "weekend_standard_window": "standard",
    "post_freeze_monday_window": "standard",
    "expedite_arm_package": "expedited",
}
STANDING_APPROVAL = {
    "approval_id": "AP-SO-0090",
    "subject": "Quarterly observability licence renewal standing order",
    "approver_id": "U-LINDGREN",
    "approver_role": "change_manager",
    "status": "APPROVED",
    "granted_on": "2026-02-09",
    "scope_json": json.dumps({"category": "LICENCES", "max_spend_usd": 7000}, sort_keys=True),
}


# --------------------------------------------------------------------------- #
# Derivations
# --------------------------------------------------------------------------- #


def _shift_time(value: str, minutes: int) -> str:
    return (datetime.fromisoformat(value) + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")


def _services(scenario: Scenario) -> tuple[Service, ...]:
    return (scenario.service, *scenario.other_services)


def _version_tuple(value: str) -> tuple[int, ...] | None:
    parts = value.strip().split(".")
    if all(part.isdigit() for part in parts):
        return tuple(int(part) for part in parts)
    return None


def version_affected(version: str, spec: str) -> bool:
    """Whether a node version falls inside an advisory's affected-version spec."""

    spec = spec.split(" (")[0].strip()
    if "-" in spec:
        low, high = (piece.strip() for piece in spec.split("-", 1))
        current, lower, upper = _version_tuple(version), _version_tuple(low), _version_tuple(high)
        if current is not None and lower is not None and upper is not None:
            return lower <= current <= upper
    if spec.endswith(".x"):
        return version.startswith(spec[:-1])
    return version == spec


def needing_nodes(scenario: Scenario) -> list:
    return [
        node
        for node in scenario.nodes
        if node.service_id == scenario.service.service_id and node.status == "active" and version_affected(node.version, scenario.advisory.affected_versions)
    ]


def calendar(scenario: Scenario) -> dict[tuple[str, str, str], dict[str, Any]]:
    """The maintenance-window grid: embargo, freezes, booked changes, explicit overrides."""

    grid: dict[tuple[str, str, str], dict[str, Any]] = {}
    days = calendar_days()
    for day in days:
        for lane in scenario.lanes:
            for session in SESSIONS:
                if day == AS_OF and session == "NIGHT":
                    entry = {"status": "busy", "hold_reason": "elapsed before the planning time", "change_id": None}
                elif lane.weekday_policy == "embargo" and not is_weekend(day):
                    entry = {"status": "protected", "hold_reason": "tier-1 weekday change embargo (protected)", "change_id": None}
                else:
                    entry = {"status": "free", "hold_reason": None, "change_id": None}
                grid[(day, lane.lane_id, session)] = entry
    for freeze in scenario.freezes:
        if freeze.status != "ACTIVE":
            continue
        for day in days:
            if not freeze.start_date <= day <= freeze.end_date:
                continue
            for lane in scenario.lanes:
                if freeze.lanes != "ALL" and lane.lane_id not in freeze.lanes:
                    continue
                for session in SESSIONS:
                    grid[(day, lane.lane_id, session)] = {"status": "protected", "hold_reason": f"{freeze.name} (protected)", "change_id": None}
    for change in scenario.changes:
        if change.state == "scheduled" and change.lane_id and change.day and change.session:
            key = (change.day, change.lane_id, change.session)
            if key in grid:
                grid[key] = {"status": "busy", "hold_reason": "scheduled change", "change_id": change.change_id}
    for item in scenario.windows:
        key = (item.day, item.lane, item.session)
        if key not in grid:
            raise ValueError(f"{scenario.task_id}: window override {key} is not on the calendar")
        if item.status == "free":
            grid[key] = {"status": "free", "hold_reason": None, "change_id": None}
        elif item.status == "busy" and item.reason.startswith("CHG-"):
            grid[key] = {"status": "busy", "hold_reason": "scheduled change", "change_id": item.reason}
        else:
            grid[key] = {"status": item.status, "hold_reason": item.reason or item.status, "change_id": None}
    return grid


def _coverage_intervals(scenario: Scenario, day: str) -> list[tuple[str, str]]:
    schedule = scenario.secondary_schedule
    following = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    intervals: list[tuple[str, str]] = []
    for row in shifts_for(schedule, [day, following]):
        if certified(row["engineer_id"], schedule.required_certification):
            intervals.append((row["start_time"], row["end_time"]))
    for row in scenario.seed.get("overrides", ()):
        if row["schedule_id"] == schedule.schedule_id and row["status"] == "ACTIVE" and certified(row["engineer_id"], schedule.required_certification):
            intervals.append((row["start_time"], row["end_time"]))
    return sorted(intervals)


def _session_block(scenario: Scenario, day: str, session: str) -> tuple[str, str]:
    start = f"{day}T{SESSION_TIMES[session][0]}"
    interval = WINDOW_MINUTES if scenario.numbers.get("whole_window") else int(scenario.numbers.get("interval_minutes", WINDOW_MINUTES))
    watch = itsm_tools.WATCH_MINUTES_TIER1 if scenario.service.tier == "tier-1" else 0
    return start, _shift_time(start, interval + watch)


def secondary_covers(scenario: Scenario, day: str, session: str) -> bool:
    start, end = _session_block(scenario, day, session)
    return itsm_tools.covers(_coverage_intervals(scenario, day), start, end)


def spendable_on(scenario: Scenario, day: str) -> int:
    return spendable_minutes(scenario.incidents, scenario.service.service_id, scenario.slo, day)


def window_eligible(scenario: Scenario, grid: dict[tuple[str, str, str], dict[str, Any]], key: tuple[str, str, str]) -> bool:
    day, lane_id, session = key
    entry = grid[key]
    lane = next(item for item in scenario.lanes if item.lane_id == lane_id)
    held_by_primary = entry.get("change_id") == scenario.primary_change.change_id
    if entry["status"] != "free" and not held_by_primary:
        return False
    if lane.status != "ACTIVE" or lane_id not in scenario.numbers["eligible_lanes"]:
        return False
    if scenario.service.tier == "tier-1" and not lane.tier1_capable:
        return False
    required = scenario.numbers.get("budget_required")
    if required and spendable_on(scenario, day) < int(required):
        return False
    return secondary_covers(scenario, day, session)


def eligible_windows(scenario: Scenario) -> list[tuple[str, str, str]]:
    grid = calendar(scenario)
    keys = [key for key in grid if window_eligible(scenario, grid, key)]
    return sorted(keys, key=lambda key: (key[0], SESSIONS.index(key[2]), key[1]))


def first_windows_on_or_after(scenario: Scenario, start: str, count: int = 1, *, distinct_days: bool = False) -> list[tuple[str, str, str]]:
    chosen: list[tuple[str, str, str]] = []
    for key in eligible_windows(scenario):
        if key[0] < start:
            continue
        if distinct_days and chosen and chosen[-1][0] == key[0]:
            continue
        chosen.append(key)
        if len(chosen) == count:
            break
    return chosen


def _label(key: tuple[str, str, str] | None) -> str | None:
    return f"{key[1]}/{key[0]}/{key[2]}" if key else None


def _write_window(scenario: Scenario) -> tuple[str, str, str] | None:
    """(day, lane, session) of the primary write's interval, when it books a session."""

    args = scenario.primary_write.arguments
    if "start_time" not in args:
        return None
    day, clock = args["start_time"][:10], args["start_time"][11:]
    session = next((name for name, (start, end) in SESSION_TIMES.items() if start <= clock < end), None)
    if session is None:
        return None
    lane = args.get("lane_id") or scenario.primary_change.lane_id or scenario.service.lane_id
    return day, lane, session


def budget_roll_date(scenario: Scenario, required: int) -> str | None:
    return next((day for day in calendar_days() if spendable_on(scenario, day) >= required), None)


def verify_numbers(scenario: Scenario) -> None:
    numbers, extra = scenario.numbers, scenario.extra_answer
    service, slo, advisory = scenario.service, scenario.slo, scenario.advisory
    problems: list[str] = []

    def check(label: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            problems.append(f"{label}: computed {actual!r} but scenario declares {expected!r}")

    def intish(value: float) -> Any:
        return int(value) if float(value).is_integer() else value

    consumed_now = consumed_minutes(scenario.incidents, service.service_id, slo, AS_OF)
    downtime = downtime_minutes(service, advisory.restarts_required)
    basis = numbers["basis"]
    write_window = _write_window(scenario)
    args = scenario.primary_write.arguments

    if basis in {"budget", "outage"}:
        check("scope", downtime, numbers["scope"])
        check("observed", slo.budget_minutes, numbers["observed"])
        check("excluded", consumed_now + slo.reserve_minutes, numbers["excluded"])
        check("eligible", slo.budget_minutes - consumed_now - slo.reserve_minutes, numbers["eligible"])
        check("restarts_required", advisory.restarts_required, extra["restarts_required"])
        check("restart_minutes", intish(service.meter_value), extra["restart_minutes"])
        check("validation_minutes", service.validation_minutes, extra["validation_minutes"])
        check("budget_consumed_minutes", consumed_now, extra["budget_consumed_minutes"])
        check("budget_reserve_minutes", slo.reserve_minutes, extra["budget_reserve_minutes"])
        required = numbers["transaction_quantity"] if basis == "outage" else downtime
        check("budget_required", required, numbers["budget_required"])
        check("budget_roll_date", budget_roll_date(scenario, required), extra["budget_roll_date"])
        if basis == "budget":
            check("earliest_qualified_base_window", numbers["standard_slot_date"], extra["earliest_qualified_base_window"])
            check("expedite_completion_days_saved", (date.fromisoformat(numbers["standard_slot_date"]) - date.fromisoformat(numbers["expedited_slot_date"])).days, extra["expedite_completion_days_saved"])
            check("selected_lane_window", _label(write_window), extra["selected_lane_window"])
        else:
            check("transaction_quantity", downtime + service.rollback_minutes, numbers["transaction_quantity"])
            check("rollback_reserve_minutes", service.rollback_minutes, extra["rollback_reserve_minutes"])
            check("vendor_estimate_minutes", advisory.vendor_estimate_minutes, extra["vendor_estimate_minutes"])
            check("notice_window", _label(write_window), extra["notice_window"])
            check("notice length", minutes_between(args["start_time"], args["end_time"]), numbers["transaction_quantity"])
            check("notice downtime", args["downtime_minutes"], downtime)
    elif basis == "node_plan":
        needing = needing_nodes(scenario)
        staged = [node for node in needing if node.staged_build]
        excluded = [node for node in staged if node.build_status != "VALIDATED"]
        check("scope", len(needing), numbers["scope"])
        check("observed", len(staged), numbers["observed"])
        check("excluded", len(excluded), numbers["excluded"])
        check("eligible", len(staged) - len(excluded), numbers["eligible"])
        check("nodes_total", sum(1 for node in scenario.nodes if node.service_id == service.service_id and node.status == "active"), extra["nodes_total"])
        check("nodes_on_fixed_version", sum(1 for node in scenario.nodes if node.service_id == service.service_id and node.version == advisory.fixed_version), extra["nodes_on_fixed_version"])
        check("x86_nodes_validated", len(staged) - len(excluded), extra["x86_nodes_validated"])
        check("arm_nodes_superseded_build", len(excluded), extra["arm_nodes_superseded_build"])
        check("arm_downtime_minutes", downtime, extra["arm_downtime_minutes"])
        check("budget_required", downtime, numbers["budget_required"])
        check("earliest_qualified_base_window", numbers["standard_slot_date"], extra["earliest_qualified_base_window"])
        check("expedite_completion_days_saved", (date.fromisoformat(numbers["standard_slot_date"]) - date.fromisoformat(numbers["expedited_slot_date"])).days, extra["expedite_completion_days_saved"])
        check("selected_lane_window", _label(write_window), extra["selected_lane_window"])
    elif basis == "node_batch":
        needing = needing_nodes(scenario)
        lane = scenario.primary_change.lane_id
        on_lane = [node for node in needing if node.lane_id == lane]
        pinned = [node for node in on_lane if node.pinned_for]
        pool = [node for node in scenario.nodes if node.service_id == service.service_id and node.lane_id == lane and node.status == "active"]
        day = args["start_time"][:10]
        remaining = slo.budget_minutes - consumed_minutes(scenario.incidents, service.service_id, slo, day)
        cap = len(pool) // 2 if remaining * 2 < slo.budget_minutes else len(pool)
        capacity = WINDOW_MINUTES // int(service.meter_value)
        check("scope", len(needing), numbers["scope"])
        check("observed", len(on_lane), numbers["observed"])
        check("excluded", len(pinned), numbers["excluded"])
        check("eligible", len(on_lane) - len(pinned), numbers["eligible"])
        check("transaction_quantity", min(len(on_lane) - len(pinned), cap, capacity), numbers["transaction_quantity"])
        check("nodes_on_fixed_version", sum(1 for node in scenario.nodes if node.service_id == service.service_id and node.version == advisory.fixed_version), extra["nodes_on_fixed_version"])
        check("lane_nodes_active", len(pool), extra["lane_nodes_active"])
        check("dr_lane_nodes", len(needing) - len(on_lane), extra["dr_lane_nodes"])
        check("budget_remaining_minutes", remaining, extra["budget_remaining_minutes"])
        check("batch_cap_nodes", cap, extra["batch_cap_nodes"])
        check("drain_minutes_per_node", intish(service.meter_value), extra["drain_minutes_per_node"])
        check("window_capacity_nodes", capacity, extra["window_capacity_nodes"])
        check("first_batch_window", _label(write_window), extra["first_batch_window"])
        check("batch node_count", args["node_count"], numbers["transaction_quantity"])
        check("batch interval", minutes_between(args["start_time"], args["end_time"]), args["node_count"] * int(service.meter_value))
    elif basis == "oncall":
        change = scenario.primary_change
        block_start = change.planned_start
        block_end = _shift_time(change.planned_end, itsm_tools.WATCH_MINUTES_TIER1 if service.tier == "tier-1" else 0)
        schedule = scenario.secondary_schedule
        observed = excluded = 0
        uncovered: list[tuple[str, str]] = []
        for row in shifts_for(schedule, [block_start[:10]]):
            start, end = max(row["start_time"], block_start), min(row["end_time"], block_end)
            if start >= end:
                continue
            hours = minutes_between(start, end) // 60
            observed += hours
            if not certified(row["engineer_id"], schedule.required_certification):
                excluded += hours
                uncovered.append((start, end))
        check("scope", minutes_between(block_start, block_end) // 60, numbers["scope"])
        check("observed", observed, numbers["observed"])
        check("excluded", excluded, numbers["excluded"])
        check("eligible", observed - excluded, numbers["eligible"])
        check("transaction_quantity", excluded, numbers["transaction_quantity"])
        check("uncovered interval", uncovered, [(args["start_time"], args["end_time"])])
        check("override hours", minutes_between(args["start_time"], args["end_time"]) // 60, numbers["transaction_quantity"])
        check("window_hours", minutes_between(change.planned_start, change.planned_end) // 60, extra["window_hours"])
        check("post_change_watch_hours", itsm_tools.WATCH_MINUTES_TIER1 // 60, extra["post_change_watch_hours"])
        check("override_engineer", args["engineer_id"], extra["override_engineer"])
        check("override engineer certified", certified(args["engineer_id"], schedule.required_certification), True)
        check("change_window", f"{change.lane_id}/{change.day}/{change.session}", extra["change_window"])
        check("budget_required", downtime, numbers["budget_required"])
    elif basis == "window":
        grid = calendar(scenario)
        start_day, end_day = numbers["capacity_window"]
        keys = [(day, lane, session) for day in calendar_days() if start_day <= day <= end_day for lane in numbers["eligible_lanes"] for session in SESSIONS]
        usable = sum(1 for key in keys if window_eligible(scenario, grid, key))
        check("observed", len(keys) * WINDOW_HOURS, numbers["observed"])
        check("excluded", (len(keys) - usable) * WINDOW_HOURS, numbers["excluded"])
        check("eligible", usable * WINDOW_HOURS, numbers["eligible"])
        check("scope", int(numbers["sessions_needed"]) * WINDOW_HOURS, numbers["scope"])
        chosen = first_windows_on_or_after(scenario, start_day, int(numbers["sessions_needed"]), distinct_days=bool(numbers.get("distinct_days")))
        check("selected_resource", _label(chosen[0]) if chosen else None, numbers["selected_resource"])
        selected = next(option for option in scenario.options if option.recommended)
        check("selected completion", chosen[-1][0] if len(chosen) == int(numbers["sessions_needed"]) else None, selected.completion)
        check("selected_resource write", _label(write_window), numbers["selected_resource"])
        if "windows_required" in extra:
            check("windows_required", int(numbers["sessions_needed"]), extra["windows_required"])
        check("budget_required", downtime, numbers["budget_required"])
        if "interval_minutes" in extra:
            check("interval_minutes", minutes_between(args["start_time"], args["end_time"]), extra["interval_minutes"])
        if "downtime_minutes_required" in extra:
            check("downtime_minutes_required", downtime, extra["downtime_minutes_required"])
        if "restart_minutes" in extra:
            check("restart_minutes", intish(service.meter_value), extra["restart_minutes"])
        if "requested_day" in extra:
            check("requested_day", start_day, extra["requested_day"])
        if "requested_week_end" in extra:
            check("requested_week_end", end_day, extra["requested_week_end"])
    else:
        problems.append(f"unknown basis {basis!r}")

    check("gap", max(0, numbers["scope"] - numbers["eligible"]), numbers["gap"])
    check("standard_readiness", next_business_day(advisory.standard_date), scenario.standard_readiness)
    check("expedited_readiness", next_business_day(advisory.expedited_date), scenario.expedited_readiness)
    sessions_needed = int(numbers.get("sessions_needed", 1))
    slots = {}
    for label, readiness in (("standard", scenario.standard_readiness), ("expedited", scenario.expedited_readiness)):
        chosen = first_windows_on_or_after(scenario, readiness, 1)
        slots[label] = chosen[0][0] if chosen else None
        check(f"{label}_slot_date", slots[label], numbers[f"{label}_slot_date"])
    for index, label in numbers.get("option_slots", {}).items():
        check(f"option {index} completion", slots[label], scenario.options[int(index)].completion)
    selected = next(option for option in scenario.options if option.recommended)
    if selected.id in PLAN_SELECTED_OPTIONS:
        check("selected completion", slots[PLAN_SELECTED_OPTIONS[selected.id]], selected.completion)
    if write_window is not None:
        check("primary write window", window_id(write_window[1], write_window[0], write_window[2]), scenario.selected_window_id)
        if scenario.primary_write.tool in {"itsm.changes.update", "itsm.changes.create"}:
            expected_interval = WINDOW_MINUTES if numbers.get("whole_window") else downtime + service.rollback_minutes
            check("planned interval", minutes_between(args["start_time"], args["end_time"]), expected_interval)
            if sessions_needed == 1:
                check("primary write day", write_window[0], selected.completion)
    if scenario.selected_window_id not in {window_id(lane, day, session) for (day, lane, session) in calendar(scenario)}:
        problems.append(f"selected window {scenario.selected_window_id} is not on the calendar")
    if problems:
        raise ValueError(f"{scenario.task_id} scenario data disagrees with its declared numbers:\n  " + "\n  ".join(problems))


# --------------------------------------------------------------------------- #
# Seed tables
# --------------------------------------------------------------------------- #


def _meterings(service: Service, *, stale: bool) -> list[dict[str, Any]]:
    rows = [{"metering_id": service.metering_id, "service_id": service.service_id, "metric": service.meter_metric, "value": service.meter_value, "unit": "MIN", "measured_at": service.meter_date, "status": "final"}]
    if stale:
        rows.append({"metering_id": service.stale_metering_id, "service_id": service.service_id, "metric": service.meter_metric, "value": service.stale_value, "unit": "MIN", "measured_at": service.stale_date, "status": "final"})
    return rows


def _burn_samples(scenario: Scenario) -> list[dict[str, Any]]:
    consumed = consumed_minutes(scenario.incidents, scenario.service.service_id, scenario.slo, AS_OF)
    rows = []
    for offset in (2, 1, 0):
        day = (date.fromisoformat(AS_OF) - timedelta(days=offset)).isoformat()
        rows.append(
            {
                "sample_id": f"BURN-{scenario.ordinal:03d}-{3 - offset}",
                "slo_id": scenario.slo.slo_id,
                "sampled_at": f"{day}T08:00:00",
                "burn_rate_1h": round(0.4 + 0.1 * scenario.ordinal, 2),
                "burn_rate_6h": round(0.3 + 0.05 * scenario.ordinal, 2),
                "raw_consumed_minutes": round(consumed + 1.4 + 0.3 * scenario.ordinal - 0.2 * offset, 1),
            }
        )
    return rows


def _alerts(scenario: Scenario) -> list[dict[str, Any]]:
    rows = []
    for index, incident in enumerate(scenario.incidents, start=1):
        rows.append(
            {
                "alert_id": f"ALRT-{scenario.ordinal:03d}-{index:02d}",
                "service_id": incident.service_id,
                "rule": "availability-burn-fast" if incident.slo_charged else "synthetic-probe-failure",
                "severity": incident.severity,
                "fired_at": incident.opened_at,
                "resolved_at": incident.resolved_at,
                "incident_id": incident.incident_id,
            }
        )
    return rows


def _change_row(change: Change) -> dict[str, Any]:
    return {
        "change_id": change.change_id,
        "service_id": change.service_id,
        "advisory_id": change.advisory_id,
        "change_type": change.change_type,
        "state": change.state,
        "lane_id": change.lane_id,
        "window_id": window_id(change.lane_id, change.day, change.session) if change.lane_id and change.day and change.session else None,
        "planned_start": change.planned_start,
        "planned_end": change.planned_end,
        "downtime_minutes": change.downtime_minutes,
        "restarts": change.restarts,
        "risk": change.risk,
        "requested_by": change.requested_by,
        "summary": change.summary,
        "opened_at": change.opened_at,
        "revision": 1,
        "last_updated": "2026-04-13T17:30:00",
    }


def seed_tables(scenario: Scenario, drive_files: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grid = calendar(scenario)
    days = calendar_days()
    windows = [
        {"window_id": window_id(lane, day, session), "lane_id": lane, "service_date": day, "session": session, "start_time": SESSION_TIMES[session][0], "end_time": SESSION_TIMES[session][1], **entry}
        for (day, lane, session), entry in sorted(grid.items())
    ]
    services = _services(scenario)
    return {
        "users": [dict(row) for row in USERS],
        "engineers": [dict(row) for row in ENGINEERS],
        "vendors": [dict(row) for row in VENDORS],
        "change_lanes": [{"lane_id": l.lane_id, "name": l.name, "weekday_policy": l.weekday_policy, "tier1_capable": int(l.tier1_capable), "status": l.status, "status_note": l.note} for l in scenario.lanes],
        "services": [
            {
                "service_id": s.service_id, "code": s.code, "name": s.name, "tier": s.tier, "owner_team": s.owner_team, "lane_id": s.lane_id, "primary_engineer_id": s.engineer_id,
                "runtime": s.runtime, "version": s.version, "required_certification": s.required_certification, "validation_minutes": s.validation_minutes, "rollback_minutes": s.rollback_minutes,
            }
            for s in services
        ],
        "nodes": [
            {"node_id": n.node_id, "service_id": n.service_id, "pool": n.pool, "region": n.region, "lane_id": n.lane_id, "version": n.version, "status": n.status, "staged_build": n.staged_build, "build_status": n.build_status, "pinned_for": n.pinned_for}
            for n in scenario.nodes
        ],
        "meterings": [row for index, s in enumerate(services) for row in _meterings(s, stale=index == 0)],
        "slos": [
            {"slo_id": s.slo_id, "service_id": s.service_id, "name": s.name, "sli": s.sli, "objective_pct": s.objective_pct, "window_days": s.window_days, "budget_minutes": s.budget_minutes, "reserve_minutes": s.reserve_minutes, "status": s.status}
            for s in (scenario.slo, *scenario.other_slos)
        ],
        "burn_samples": _burn_samples(scenario),
        "problems": [{"problem_id": p.problem_id, "service_id": p.service_id, "title": p.title, "status": p.status, "review_note": p.review_note} for p in scenario.problems],
        "incidents": [
            {"incident_id": i.incident_id, "service_id": i.service_id, "opened_at": i.opened_at, "resolved_at": i.resolved_at, "severity": i.severity, "impact_minutes": i.impact_minutes, "slo_charged": int(i.slo_charged), "problem_id": i.problem_id, "summary": i.summary}
            for i in scenario.incidents
        ],
        "alerts": _alerts(scenario),
        "vendor_advisories": [
            {
                "advisory_id": a.advisory_id, "vendor_id": a.vendor_id, "reference": a.reference, "product": a.product, "severity": a.severity, "published_on": a.published_on, "remediation_sla_days": a.sla_days,
                "affected_versions": a.affected_versions, "fixed_version": a.fixed_version, "restarts_required": a.restarts_required, "vendor_estimate_minutes": a.vendor_estimate_minutes,
                "standard_release_date": a.standard_date, "expedited_release_date": a.expedited_date, "expedite_fee_usd": a.fee, "valid_until": a.valid_until, "status": a.status, "note": a.note,
            }
            for a in (scenario.advisory, *scenario.other_advisories)
        ],
        "freeze_windows": [
            {"freeze_id": f.freeze_id, "name": f.name, "kind": f.kind, "start_date": f.start_date, "end_date": f.end_date, "lanes": "ALL" if f.lanes == "ALL" else ",".join(f.lanes), "authority": f.authority, "status": f.status}
            for f in scenario.freezes
        ],
        "maintenance_windows": windows,
        "change_requests": [_change_row(change) for change in scenario.changes],
        "change_tasks": [dict(row) for row in scenario.seed.get("tasks", ())],
        "planned_outages": [dict(row) for row in scenario.seed.get("outages", ())],
        "oncall_schedules": [{"schedule_id": s.schedule_id, "service_id": s.service_id, "name": s.name, "role": s.role, "required_certification": s.required_certification} for s in scenario.schedules],
        "oncall_shifts": [row for schedule in scenario.schedules for row in shifts_for(schedule, days)],
        "escalation_policies": [
            {
                "policy_id": f"ESC-{scenario.service.service_id.split('-')[1]}",
                "service_id": scenario.service.service_id,
                "name": f"{scenario.service.code} escalation",
                "levels_json": json.dumps(
                    [
                        {"level": 1, "target": next(s.schedule_id for s in scenario.schedules if s.role == "primary"), "timeout_minutes": 10},
                        {"level": 2, "target": scenario.secondary_schedule.schedule_id, "timeout_minutes": 10},
                        {"level": 3, "target": "U-HAVILAND (SRE lead)", "timeout_minutes": 15},
                    ]
                ),
            }
        ],
        "oncall_overrides": [dict(row) for row in scenario.seed.get("overrides", ())],
        "approvals": [
            {
                "approval_id": scenario.approval.approval_id, "subject": scenario.approval.subject, "approver_id": scenario.approval.approver_id, "approver_role": scenario.approval.approver_role,
                "status": "APPROVED", "granted_on": scenario.approval.granted_on, "scope_json": json.dumps(scenario.approval.scope, sort_keys=True),
            },
            dict(STANDING_APPROVAL),
        ],
        "messages": [
            {
                "message_id": scenario.email.message_id, "thread_id": scenario.email.thread_id, "channel": "email", "sender": scenario.email.sender, "recipients": scenario.email.recipients,
                "subject": scenario.email.subject, "sent_at": scenario.email.sent_at, "body": scenario.email.body,
                "attachments_json": json.dumps([{"name": name, "mime_type": "application/pdf"} for name in scenario.email.attachments]),
                "labels": f"{scenario.email.labels},{scenario.case_reference}",
            },
            {
                "message_id": f"MSG-{scenario.ordinal:04d}-00", "thread_id": f"THR-{scenario.ordinal:04d}-OPS", "channel": "email", "sender": "wren.haviland@brightmoor.example", "recipients": OPS_EMAIL_ADDRESS,
                "subject": "Weekly service-operations note", "sent_at": "2026-04-13T08:00:00",
                "body": "On-call rotations for the week of 2026-04-13 are posted. Lane certification flags are on the shared drive roster; the change board meets Thursday.",
                "attachments_json": "[]", "labels": "operations",
            },
        ],
        "chat_threads": [
            {"thread_id": scenario.chat.thread_id, "channel": scenario.chat.channel, "title": scenario.chat.title, "messages_json": json.dumps([{"author": a, "ts": t, "text": x} for a, t, x in scenario.chat.messages])},
            {"thread_id": f"CHAT-{scenario.ordinal:04d}-GEN", "channel": "#service-ops", "title": "General — alert routing and CAB agenda", "messages_json": json.dumps([{"author": "Wren Haviland", "ts": "2026-04-12T16:40:00", "text": "Reminder: log every alert-routing change in the change tracker before the CAB agenda closes."}])},
        ],
        "drive_files": drive_files,
        "evidence_files": evidence,
    }


OPS_EMAIL_ADDRESS = "service-ops@brightmoor.example"


# --------------------------------------------------------------------------- #
# Evidence room
# --------------------------------------------------------------------------- #


def _change_json(scenario: Scenario, change: Change) -> str:
    rendered = itsm_tools._change(_change_row(change))
    return json.dumps({"export": "itsm.changes.get", "record": rendered}, indent=2, sort_keys=True) + "\n"


def _service_summary_json(scenario: Scenario) -> str:
    service = scenario.service
    rendered = itsm_tools._service(
        {
            "service_id": service.service_id, "code": service.code, "name": service.name, "tier": service.tier, "owner_team": service.owner_team, "lane_id": service.lane_id, "primary_engineer_id": service.engineer_id,
            "runtime": service.runtime, "version": service.version, "required_certification": service.required_certification, "validation_minutes": service.validation_minutes, "rollback_minutes": service.rollback_minutes,
        }
    )
    meterings = [itsm_tools._metering(row) for row in _meterings(service, stale=True)]
    return json.dumps({"export": "itsm.cis.get + itsm.meterings.list", "service": rendered, "meterings": meterings}, indent=2, sort_keys=True) + "\n"


def _advisory_text(scenario: Scenario) -> str:
    a = scenario.advisory
    vendor = next(row for row in VENDORS if row["vendor_id"] == a.vendor_id)
    return (
        f"{vendor['name']}\nSecurity advisory {a.reference} (portal id {a.advisory_id}) — status {a.status}\nCustomer: Brightmoor Commerce Service Operations, account {vendor['account_number']}\n"
        f"Case reference: {scenario.case_reference}\nProduct: {a.product}\nSeverity: {a.severity}; published {a.published_on}; remediation SLA {a.sla_days} days\n"
        f"Affected versions: {a.affected_versions}; fixed version: {a.fixed_version}\nRestarts required: {a.restarts_required}; vendor downtime estimate: {a.vendor_estimate_minutes} minutes (reference hardware)\n"
        f"Standard release date: {a.standard_date}\nEarly-access release date: {a.expedited_date} (premium-support fee USD {a.fee}, flat)\nValid until: {a.valid_until}\nNotes: {a.note}\n"
        "Packages are production-eligible only after the customer's canary soak.\n"
    )


def _decoy_asset(scenario: Scenario) -> dict[str, Any]:
    doc = scenario.decoy_doc
    if doc.kind == "policy_superseded":
        return asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=MARKDOWN, content=scoped_markdown(SUPERSEDED_POLICY, task_id=scenario.task_id, case_reference=scenario.case_reference), preview="2024 policy retained for audit only; superseded by v3.")
    if doc.kind == "decoy_change":
        change_id = doc.path.rsplit("/", 1)[-1].removeprefix("change-").removesuffix(".json")
        change = next(item for item in scenario.changes if item.change_id == change_id)
        return asset(doc.path, kind=doc.kind, title=doc.title, source="itsm_export", media_type=JSON, content=_change_json(scenario, change), preview="A cancelled duplicate change that must not be scheduled or resurrected.")
    if doc.media_type == XLSX:
        return asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=XLSX, rows=[list(row) for row in doc.rows or ()], preview=doc.title)
    content = scoped_csv(doc.content, task_id=scenario.task_id, case_reference=scenario.case_reference) if doc.media_type == CSV else doc.content
    return asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=doc.media_type, content=content, preview=doc.title)


def build_assets(scenario: Scenario) -> list[dict[str, Any]]:
    case = scenario.case_reference
    grid = calendar(scenario)
    service = scenario.service
    change = scenario.primary_change
    secondary = scenario.secondary_schedule
    roster_days = [day for day in calendar_days() if day <= (date.fromisoformat(AS_OF) + timedelta(days=13)).isoformat()]
    assets: list[dict[str, Any]] = [
        asset(
            "policy/change-and-error-budget-policy.md", kind="policy", title="Change and error-budget policy v3 (effective)", source="drive", media_type=MARKDOWN,
            content=scoped_markdown(effective_policy(AS_OF), task_id=scenario.task_id, case_reference=case), preview="Sizing, error-budget, window, vendor-package, and authority rules in force.",
        ),
    ]
    if scenario.decoy_doc.kind != "policy_superseded":
        assets.append(
            asset(
                "policy/superseded-change-policy-2024.md", kind="policy_superseded", title="Change and error-budget policy 2024 (superseded)", source="drive", media_type=MARKDOWN,
                content=scoped_markdown(SUPERSEDED_POLICY, task_id=scenario.task_id, case_reference=case), preview="2024 policy retained for audit only; superseded by v3.",
            )
        )
    assets.append(_decoy_asset(scenario))
    assets.extend(
        [
            asset(f"itsm/change-{change.change_id}.json", kind="change_export", title=f"Change {change.change_id} (ITSM export)", source="itsm_export", media_type=JSON, content=_change_json(scenario, change), preview="The change record in scope: state, lane, planned interval, downtime, and revision."),
            asset(f"itsm/service-{service.code}-summary.json", kind="service_summary", title=f"Service {service.code} summary with restart meterings (ITSM export)", source="itsm_export", media_type=JSON, content=_service_summary_json(scenario), preview="Service identity plus current and historical meterings."),
            asset(
                "telemetry/slo-catalog.csv", kind="slo_catalog", title="SLO catalog: objectives, windows, budgets, and reserve floors", source="telemetry_export", media_type=CSV,
                content="slo_id,service_id,name,objective_pct,window_days,budget_minutes,reserve_minutes,status\n" + "".join(f"{s.slo_id},{s.service_id},{s.name},{s.objective_pct},{s.window_days},{s.budget_minutes},{s.reserve_minutes},{s.status}\n" for s in (scenario.slo, *scenario.other_slos)),
                preview="Whole-minute budgets and reserve floors per SLO.",
            ),
            asset(
                "telemetry/error-budget-ledger.xlsx", kind="budget_ledger_workbook", title=f"Error-budget ledger — {service.code} (gross incident minutes)", source="telemetry_workbook", media_type=XLSX,
                rows=[["incident_id", "service_id", "opened_at", "severity", "impact_minutes", "slo_charged", "problem_id"], *[[i.incident_id, i.service_id, i.opened_at, i.severity, i.impact_minutes, "yes" if i.slo_charged else "no", i.problem_id or ""] for i in scenario.incidents]],
                preview="Every incident with its impact minutes and charged flag; window membership is a separate test.",
            ),
            asset(
                "itsm/incident-register.csv", kind="incident_register", title="Incident register with problem-review notes", source="itsm_export", media_type=CSV,
                content="incident_id,opened_at,resolved_at,severity,impact_minutes,slo_charged,problem_id,review_note,summary\n" + "".join(
                    f'{i.incident_id},{i.opened_at},{i.resolved_at},{i.severity},{i.impact_minutes},{"yes" if i.slo_charged else "no"},{i.problem_id or ""},"{next((p.review_note for p in scenario.problems if p.problem_id == i.problem_id), "")}","{i.summary}"\n' for i in scenario.incidents
                ),
                preview="Which incidents the problem review charged or reclassified.",
            ),
            asset(
                "telemetry/burn-rate-samples.csv", kind="burn_samples", title=f"Burn-rate samples — {scenario.slo.slo_id}", source="telemetry_export", media_type=CSV,
                content="sample_id,slo_id,sampled_at,burn_rate_1h,burn_rate_6h,raw_consumed_minutes\n" + "".join(f"{r['sample_id']},{r['slo_id']},{r['sampled_at']},{r['burn_rate_1h']},{r['burn_rate_6h']},{r['raw_consumed_minutes']}\n" for r in _burn_samples(scenario)),
                preview="Raw SLI burn (informational); the incident ledger governs.",
            ),
            asset(
                "calendar/change-calendar-2026-04-14.xlsx", kind="change_calendar", title="Change calendar, three weeks from 2026-04-14", source="calendar_workbook", media_type=XLSX,
                rows=[["service_date", "lane_id", "session", "start", "end", "status", "hold_reason", "change_id"], *[[day, lane, session, SESSION_TIMES[session][0], SESSION_TIMES[session][1], entry["status"], entry["hold_reason"] or "", entry["change_id"] or ""] for (day, lane, session), entry in sorted(grid.items())]],
                preview="Every lane session with free / busy / protected / blocked status.",
            ),
            asset(
                "calendar/freeze-register.csv", kind="freeze_register", title="Freeze register (change calendar)", source="calendar_export", media_type=CSV,
                content=scoped_csv("freeze_id,name,kind,start_date,end_date,lanes,authority,status\n" + "".join(f"{f.freeze_id},{f.name},{f.kind},{f.start_date},{f.end_date},{'ALL' if f.lanes == 'ALL' else '|'.join(f.lanes)},{f.authority},{f.status}\n" for f in scenario.freezes), task_id=scenario.task_id, case_reference=case),
                preview="Freeze windows with the lanes and authority they name.",
            ),
            asset(
                "calendar/lane-roster.csv", kind="lane_roster", title="Change-lane roster and certification", source="calendar_export", media_type=CSV,
                content=scoped_csv("lane_id,name,weekday_policy,tier1_capable,status,note\n" + "".join(f"{l.lane_id},{l.name},{l.weekday_policy},{'yes' if l.tier1_capable else 'no'},{l.status},{l.note or ''}\n" for l in scenario.lanes), task_id=scenario.task_id, case_reference=case),
                preview="Lane weekday policy, tier-1 certification, and suspension state.",
            ),
            asset(
                "oncall/secondary-roster.csv", kind="oncall_roster", title=f"Secondary on-call roster — {secondary.schedule_id}", source="oncall_export", media_type=CSV,
                content=scoped_csv("shift_id,schedule_id,engineer_id,start_time,end_time,source,certified\n" + "".join(f"{r['shift_id']},{r['schedule_id']},{r['engineer_id']},{r['start_time']},{r['end_time']},{r['source']},{'yes' if certified(r['engineer_id'], secondary.required_certification) else 'no'}\n" for r in shifts_for(secondary, roster_days)), task_id=scenario.task_id, case_reference=case),
                preview="Rostered secondary blocks for two weeks with the certification flag.",
            ),
            asset(f"vendor/advisory-{scenario.advisory.reference.split(' ')[0]}.pdf", kind="vendor_advisory", title=f"Vendor advisory {scenario.advisory.reference}", source="email_attachment", media_type=PDF, content=_advisory_text(scenario), preview="Affected versions, restarts, standard and early-access dates, fee, SLA."),
            asset(
                f"messages/{scenario.email.thread_id}.eml", kind="email", title=scenario.email.subject, source="messages", media_type=EML,
                content=eml(from_addr=scenario.email.sender, to_addr=scenario.email.recipients, subject=scenario.email.subject, date=scenario.email.sent_at, message_id=f"{scenario.email.message_id}@brightmoor.example", body=scenario.email.body, attachments=list(scenario.email.attachments)),
                preview="The request and the control date, in the requester's words.",
            ),
            asset(
                f"chat/{scenario.chat.thread_id}.json", kind="chat_thread", title=scenario.chat.title, source="chat", media_type=JSON,
                content=json.dumps({"thread_id": scenario.chat.thread_id, "channel": scenario.chat.channel, "title": scenario.chat.title, "messages": [{"author": a, "ts": t, "text": x} for a, t, x in scenario.chat.messages]}, indent=2, sort_keys=True) + "\n",
                preview="Team chat with budget, calendar, roster, and authority remarks.",
            ),
            asset(
                f"approvals/approval-{scenario.approval.approval_id}.json", kind="approval", title=f"Approval record {scenario.approval.approval_id}", source="approvals_export", media_type=JSON,
                content=json.dumps({"approval_id": scenario.approval.approval_id, "case_reference": case, "subject": scenario.approval.subject, "approver_id": scenario.approval.approver_id, "approver_role": scenario.approval.approver_role, "status": "APPROVED", "granted_on": scenario.approval.granted_on, "scope": scenario.approval.scope}, indent=2, sort_keys=True) + "\n",
                preview="Exactly what is approved, for which record, and what is not.",
            ),
            asset(
                f"exports/starting-state-{scenario.task_id}.json", kind="starting_state", title="Starting-state export (changes, tasks, outages, overrides)", source="itsm_export", media_type=JSON,
                content=json.dumps(
                    {
                        "case_reference": case, "as_of": AS_OF,
                        "changes": [{"change_id": c.change_id, "service_id": c.service_id, "state": c.state, "lane_id": c.lane_id, "planned_start": c.planned_start, "planned_end": c.planned_end} for c in scenario.changes],
                        "change_tasks": [{"task_id": row["task_id"], "status": row["status"]} for row in scenario.seed.get("tasks", ())],
                        "planned_outages": [{"outage_id": row["outage_id"], "status": row["status"]} for row in scenario.seed.get("outages", ())],
                        "oncall_overrides": [{"override_id": row["override_id"], "status": row["status"]} for row in scenario.seed.get("overrides", ())],
                        "note": "Snapshot before any action; row order does not indicate applicability.",
                    },
                    indent=2, sort_keys=True,
                ) + "\n",
                preview="Snapshot of ITSM and on-call state before any action.",
            ),
        ]
    )
    for doc in scenario.docs:
        if doc.media_type == XLSX:
            assets.append(asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=XLSX, rows=[list(row) for row in doc.rows or ()], preview=doc.title))
        else:
            content = scoped_csv(doc.content, task_id=scenario.task_id, case_reference=case) if doc.media_type == CSV else doc.content
            assets.append(asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=doc.media_type, content=content, preview=doc.title))
    assets.extend(
        quality_support_assets(
            task_id=scenario.task_id, ordinal=scenario.ordinal, case_reference=case, family_slug=FAMILY_SLUG, family_name="ITSMDesk", organization_name=ORGANIZATION["name"],
            subject_id=scenario.item, as_of=AS_OF, current_revision=scenario.revision, anchors=OPEN_SOURCE_ANCHORS,
        )
    )
    index = {"case_reference": case, "as_of": AS_OF, "files": [{"path": a["path"], "kind": a["kind"], "media_type": a["media_type"], "sha256": a["sha256"]} for a in assets]}
    assets.append(asset("audit/evidence-index.yaml", kind="evidence_index", title="Evidence index", source="drive", media_type=YAML, content=yaml_lines(index) + "\n", preview="Digest index of every evidence file in the room."))
    for position, record in enumerate(assets, start=1):
        record["asset_id"] = f"{scenario.task_id}-{position:02d}"
    return assets


def _folder(scenario: Scenario, record: dict[str, Any]) -> str:
    if record["kind"] == "policy":
        return "Service Operations/Policies"
    if record["kind"] == "policy_superseded":
        return "Service Operations/Policies/Archive"
    return CASE_FOLDER.format(case=scenario.case_reference)


def mount_drive(scenario: Scenario, assets: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    files: list[dict[str, Any]] = []
    ids: dict[str, str] = {}
    counter = 0
    for record in assets:
        if record["media_type"] == EML or record["kind"] == "chat_thread":
            continue
        counter += 1
        file_id = f"DRV-{scenario.ordinal:03d}-{counter:02d}"
        files.append({"file_id": file_id, "name": record["path"].rsplit("/", 1)[-1], "mime_type": record["media_type"], "modified_time": "2026-04-13T17:30:00", "folder": _folder(scenario, record), "content": record["content"], "sha256": record["sha256"]})
        ids[record["path"]] = file_id
    return files, ids


# --------------------------------------------------------------------------- #
# Decision model
# --------------------------------------------------------------------------- #


def build_facts(scenario: Scenario) -> tuple[dict[str, Any], ...]:
    notes = scenario.fact_notes
    labels = scenario.labels
    numbers = scenario.numbers
    selected = next(option for option in scenario.options if option.recommended)
    unauthorized = next(option for option in scenario.options if option.approval == "ADDITIONAL_APPROVAL_REQUIRED")
    accelerated = scenario.options[1]
    return (
        {"id": "authoritative_identity", "sources": ["itsm", "messages"], "statement": f"{scenario.case_reference}: {notes['identity']}; the effective revision is {scenario.revision}.", "rubric": f"Located {scenario.item} using immutable identifiers and preserved effective revision {scenario.revision}: {notes['identity']}."},
        {"id": "effective_requirement", "sources": ["itsm", "vendor", "drive"], "statement": f"The effective change, advisory, and policy establish {labels.scope_label} = {numbers['scope']} {labels.unit}: {notes['requirement']}. The control date is {scenario.business_need} ({scenario.business_need_reason}).", "rubric": f"Applied the effective change, advisory, and policy to establish {numbers['scope']} {labels.unit} for {labels.scope_label}, with control date {scenario.business_need}."},
        {"id": "eligible_coverage", "sources": ["telemetry", "itsm", "calendar"], "statement": f"{notes['coverage']}; eligibility requires netting the exclusions rather than trusting a headline total.", "rubric": f"Reconciled {numbers['observed']} observed less {numbers['excluded']} excluded to {numbers['eligible']} supported {labels.unit} for {labels.eligible_label}."},
        {"id": "conditional_external_recovery", "sources": ["vendor", "messages"], "statement": f"{labels.external_label}: {notes['external']}; a vendor release date alone proves neither eligibility nor approval.", "rubric": f"Used the independently confirmed {scenario.expedited_readiness} early-access readiness input for {accelerated.id}, then separately derived its {accelerated.completion} operating outcome under {labels.constraint_label} instead of treating a vendor date as authorization or a completion date."},
        {"id": "finite_capacity", "sources": ["calendar", "oncall", "drive"], "statement": f"{labels.capacity_label}: {notes['capacity']}; protected, frozen, and uncovered sessions cannot be displaced.", "rubric": f"Applied {labels.capacity_label} to derive the three option outcomes without using protected, frozen, blocked, or uncovered sessions."},
        {"id": "approval_scope", "sources": ["approvals", "chat"], "statement": f"{notes['approval']}. The approval does not select an option in advance and does not authorize {unauthorized.id}.", "rubric": f"Applied {scenario.approval.approval_id} only to {selected.id} and {scenario.item}; kept {unauthorized.id} outside current authority."},
        {"id": "business_impact", "sources": ["messages", "chat"], "statement": f"{notes['impact']}; a faster or broader action has value only if it remains inside {labels.constraint_label}.", "rubric": f"Compared all three alternatives and selected {selected.id}: it is the best currently authorized response that satisfies {labels.constraint_label}."},
    )


def build_model(scenario: Scenario) -> dict[str, Any]:
    numbers = scenario.numbers
    inputs = DecisionInputs(
        mode=scenario.mode, labels=scenario.labels, item=scenario.item, record=scenario.item, revision=scenario.revision,
        scope=int(numbers["scope"]), observed=int(numbers["observed"]), excluded=int(numbers["excluded"]), eligible=int(numbers["eligible"]), gap=int(numbers["gap"]),
        business_need=scenario.business_need, standard_readiness=scenario.standard_readiness, expedited_readiness=scenario.expedited_readiness, options=scenario.options,
        transaction_quantity=int(numbers["transaction_quantity"]) if "transaction_quantity" in numbers else None,
        selected_resource=str(numbers["selected_resource"]) if "selected_resource" in numbers else None,
        extra_answer=dict(scenario.extra_answer), extra_descriptions=dict(scenario.extra_descriptions), extra_calculations=scenario.extra_calculations, facts=build_facts(scenario),
    )
    return build_decision_model(inputs)


# --------------------------------------------------------------------------- #
# Investigations, oracle steps, contract
# --------------------------------------------------------------------------- #


def _investigation(number: int, milestone: str, description: str, tool: str, arguments: dict[str, Any], expected: dict[str, Any], weight: float = 1.0) -> dict[str, Any]:
    return {
        "id": f"investigation_{number:02d}",
        "milestone_id": milestone,
        "description": description,
        "weight": weight,
        "before_primary_mutation": True,
        "any_of": [{"tool": tool, "arguments": arguments, "match": "result_contains", "expected_result_contains": expected}],
    }


def build_investigations(scenario: Scenario, file_ids: dict[str, str]) -> list[dict[str, Any]]:
    case = scenario.case_reference
    service = scenario.service
    change = scenario.primary_change
    slo = scenario.slo
    advisory = scenario.advisory
    policy_id = file_ids["policy/change-and-error-budget-policy.md"]
    approval_id = file_ids[f"approvals/approval-{scenario.approval.approval_id}.json"]
    change_file_id = file_ids[f"itsm/change-{change.change_id}.json"]
    first_node = next(node for node in scenario.nodes if node.service_id == service.service_id)
    investigations = [
        _investigation(1, "investigation.scope", f"Established the isolated {case} scope, immutable handles, mounted systems, and evidence index before investigating {scenario.item}.", CONTEXT_TOOL, {}, {"reference_records": {"case_reference": case}}),
        _investigation(2, "investigation.scope", f"Located the task-scoped correspondence for {case} by searching the mailbox before opening any message; did not rely on a guessed sender or filename.", "messages.list", {"q": case}, {"messages": [{"id": scenario.email.message_id}]}),
        _investigation(3, "investigation.scope", f"Resolved service code {service.code} to the immutable CI record through an identifier search rather than a name match against a similarly named service.", "itsm.cis.search", {"identifier": service.code}, {"services": [{"service_id": service.service_id}]}),
        _investigation(4, "investigation.scope", f"Listed the {case} case folder on the shared drive and identified the approval record and the change export by immutable file id.", "drive.files.list", {"q": case}, {"files": [{"id": approval_id}, {"id": change_file_id}]}),
        _investigation(5, "investigation.scope", "Listed the policy folder and distinguished the effective v3 change and error-budget policy from the superseded 2024 edition by file identity, not title.", "drive.files.list", {"q": POLICY_QUERY}, {"files": [{"id": policy_id}]}),
        _investigation(6, "investigation.requirements", f"Read change {change.change_id}: state, lane, planned interval, downtime, restarts, and revision.", "itsm.changes.get", {"change_id": change.change_id}, {"change_id": change.change_id, "state": change.state}),
        _investigation(7, "investigation.requirements", f"Read the current final {service.meter_metric} metering for {service.service_id} and ignored the stale historical metering.", "itsm.meterings.list", {"service_id": service.service_id, "metric": service.meter_metric}, {"meterings": [{"metering_id": service.metering_id}]}),
        _investigation(8, "investigation.requirements", "Exported the effective v3 policy for the sizing, error-budget, session, freeze, coverage, vendor-package, and authority rules; did not apply the superseded 2024 edition.", "drive.files.export", {"file_id": policy_id}, {"file_id": policy_id}),
        _investigation(9, "investigation.requirements", f"Read the SLO definition {slo.slo_id}: objective, rolling window, whole-minute budget, and reserve floor.", "telemetry.slos.get", {"slo_id": slo.slo_id}, {"slo_id": slo.slo_id, "reserve_minutes": slo.reserve_minutes}),
        _investigation(10, "investigation.requirements", f"Listed the change requests for {service.service_id} and separated {change.change_id} from cancelled duplicates and other CIs' changes.", "itsm.changes.list", {"service_id": service.service_id}, {"changes": [{"change_id": change.change_id}]}),
        _investigation(11, "investigation.requirements", f"Read the incident ledger for {service.service_id} inside the SLO window to ground which incidents are charged, which were reclassified, and which fall outside the window.", "itsm.incidents.list", dict(scenario.incident_query), dict(scenario.incident_expected)),
        _investigation(12, "investigation.constraints", f"Read the error-budget view of {slo.slo_id}: window bounds, budget, reserve, and the informational raw burn, before netting the charged minutes.", "telemetry.budget.get", {"slo_id": slo.slo_id}, {"slo_id": slo.slo_id, "budget_minutes": slo.budget_minutes}),
        _investigation(13, "investigation.constraints", f"Listed the {service.code} nodes with pool, lane, version, staged build, and canary pins before counting what a change reaches.", "itsm.nodes.list", {"service_id": service.service_id}, {"nodes": [{"node_id": first_node.node_id}]}),
        _investigation(14, "investigation.constraints", f"Read the freeze register from {scenario.freeze_query['start_date']} to {scenario.freeze_query['end_date']} for the freeze windows and the authority each names.", "calendar.freezes.list", dict(scenario.freeze_query), dict(scenario.freeze_expected)),
        _investigation(15, "investigation.constraints", f"Read the change-window calendar for {scenario.windows_query['start_date']} onward to find the first free session that displaces no embargoed, frozen, or blocked window.", "calendar.windows.list", dict(scenario.windows_query), {"windows": [{"id": scenario.selected_window_id}]}),
        _investigation(16, "investigation.constraints", f"Read the vendor advisory {advisory.advisory_id} for the independently confirmed standard and early-access release dates, restarts required, fee, and SLA.", "vendor.advisories.get", {"advisory_id": advisory.advisory_id}, {"advisory_id": advisory.advisory_id, "standard_release_date": advisory.standard_date}),
        _investigation(17, "investigation.authority", f"Read approval {scenario.approval.approval_id} for its exact scope: record, lane, windows, quantity, fee allowance, and what it does not cover.", "approvals.get", {"approval_id": scenario.approval.approval_id}, {"approval_id": scenario.approval.approval_id}),
        _investigation(18, "investigation.authority", "Exported the approval record on the drive and confirmed it matches the workflow record before relying on it.", "drive.files.export", {"file_id": approval_id}, {"file_id": approval_id}),
        _investigation(19, "investigation.erp_correlation", f"Read the request message {scenario.email.message_id} for the documented control date and the business need in the requester's words.", "messages.get", {"message_id": scenario.email.message_id}, {"id": scenario.email.message_id}),
        _investigation(20, "investigation.erp_correlation", f"Read the team chat thread {scenario.chat.thread_id} for budget, calendar, roster, and authority remarks that qualify the system records.", "chat.threads.get", {"thread_id": scenario.chat.thread_id}, {"thread_id": scenario.chat.thread_id}),
        _investigation(21, "investigation.erp_correlation", f"Correlated the secondary on-call shifts on {scenario.shift_query['schedule_id']} by immutable shift id and responder certification for the sessions under consideration.", "oncall.shifts.list", dict(scenario.shift_query), dict(scenario.shift_expected)),
    ]
    investigations.extend(quality_support_investigations(start_number=len(investigations) + 1, file_ids=file_ids, make_investigation=_investigation, case_reference=case, subject_id=scenario.item))
    return investigations


def build_oracle_steps(scenario: Scenario, investigations: list[dict[str, Any]], model: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [{"phase": "context", "tool": CONTEXT_TOOL, "arguments": {}, "control": True}]
    order = [2, 19, 3, 10, 6, 7, 11, 4, 5, 8, 9, 12, 13, 21, 14, 15, 16, 17, 18, 20]
    by_number = {int(item["id"].rsplit("_", 1)[1]): item for item in investigations}
    order.extend(number for number in sorted(by_number) if number not in order)
    for number in order:
        call = by_number[number]["any_of"][0]
        steps.append({"phase": "investigation", "tool": call["tool"], "arguments": call["arguments"], "control": True})
    primary = scenario.primary_write
    steps.append({"phase": "primary_mutation", "tool": primary.tool, "arguments": primary.arguments, "control": False})
    steps.append({"phase": "post_write_verification", "tool": primary.readback_tool, "arguments": primary.readback_arguments, "control": True})
    steps.append(
        {
            "phase": "collaboration",
            "tool": "notes.drafts.create",
            "arguments": {
                "recipient": scenario.collaboration["recipient"],
                "subject": scenario.collaboration["subject"],
                "body": scenario.collaboration["body"],
                "related_change_id": _draft_change_id(scenario),
                "related_service_id": scenario.service.service_id,
            },
            "control": False,
        }
    )
    steps.append({"phase": "answer", "tool": SUBMIT_TOOL, "arguments": dict(model["answer"]), "control": False})
    return steps


def _draft_change_id(scenario: Scenario) -> str:
    return str(scenario.numbers.get("draft_change_id", scenario.primary_change.change_id))


def build_assertions(scenario: Scenario, model: dict[str, Any]) -> list[dict[str, Any]]:
    primary = scenario.primary_write
    task_id = scenario.task_id
    selected = model["selected_option"]
    completion = model["selected_completion"]
    payload_values = ", ".join(f"{key}={value!r}" for key, value in primary.arguments.items())
    return [
        {
            "id": "mutation_01", "milestone_id": "state.primary",
            "description": f"Required {scenario.item} to reach business outcome {primary.outcome_label!r} through {primary.tool} with exact provider-critical values {payload_values}. The audited change binds selected option {selected}, approval {scenario.approval.approval_id}, and constraint {scenario.labels.constraint_label}; no other record satisfies this state criterion.",
            "table": "mutations", "where": {"task_id": task_id, "mutation_id": f"{task_id}-mutation-01"},
            "values": {"tool": primary.tool, "table_name": primary.table, "record_id": primary.record_id, "status": primary.status},
            "payload_contains": {"tool": primary.tool, "arguments": primary.arguments}, "payload_allowed_argument_paths": list(primary.allowed_paths), "weight": 3.0,
        },
        {
            "id": "state_01", "milestone_id": "state.primary",
            "description": f"Persisted {primary.record_id} in {primary.table} with the supported values ({', '.join(f'{k}={v!r}' for k, v in primary.domain_values.items())}) so a later reader sees the change, not just the acknowledgement.",
            "table": primary.table, "where": {PRIMARY_KEYS[primary.table]: primary.record_id}, "values": dict(primary.domain_values), "weight": 2.0,
        },
        *[dict(item) for item in primary.extra_assertions],
        {
            "id": "mutation_02", "milestone_id": "state.collaboration",
            "description": f"Created — but did not send — the stakeholder draft carrying {selected}, the {completion} outcome, the binding constraint, and the {scenario.case_reference} business reference.",
            "table": "mutations", "where": {"task_id": task_id, "mutation_id": f"{task_id}-mutation-02"},
            "values": {"tool": "notes.drafts.create", "table_name": "note_drafts", "status": "DRAFT"},
            "payload_contains": {"tool": "notes.drafts.create", "arguments": {"recipient": scenario.collaboration["recipient"]}},
            "payload_text_contains": [selected, completion],
            "payload_text_any_of": [[scenario.case_reference, scenario.service.code, _draft_change_id(scenario)]],
            "weight": 1.5,
        },
        {
            "id": "containment_01", "milestone_id": "containment.scope",
            "description": f"Made exactly two state changes for {scenario.case_reference}: the primary change and the stakeholder draft; no additional change, task, notice, or override.",
            "table": "mutations", "where": {"task_id": task_id}, "count": 2, "weight": 1.0,
        },
    ]


def build_task(scenario: Scenario) -> dict[str, Any]:
    verify_numbers(scenario)
    assets = build_assets(scenario)
    drive_files, file_ids = mount_drive(scenario, assets)
    evidence = [{"asset_id": a["asset_id"], "task_id": scenario.task_id, "path": a["path"], "title": a["title"], "kind": a["kind"], "source": a["source"], "media_type": a["media_type"], "sha256": a["sha256"]} for a in assets]
    model = build_model(scenario)
    investigations = build_investigations(scenario, file_ids)
    steps = build_oracle_steps(scenario, investigations, model)
    assertions = build_assertions(scenario, model)
    primary = scenario.primary_write
    readback = {
        "id": "verify_primary_state", "milestone_id": "verification.readback", "after_tool": primary.tool,
        "any_of": [{"tool": primary.readback_tool, "arguments": primary.readback_arguments, "match": "result_contains", "expected_result_contains": primary.readback_expected}],
        "expected_result_contains": primary.readback_expected, "target_identity": primary.readback_arguments, "materializes_new_record": primary.tool.endswith(".create"),
        "description": f"Read {primary.record_id} back through {primary.readback_tool} after the change and confirmed the persisted provider values ({', '.join(f'{k}={v!r}' for k, v in primary.readback_expected.items())}) rather than relying on the write acknowledgement.",
        "weight": 2.0,
    }
    answer = model["answer"]
    checks = answer_checks(answer, ["recommended_option", "recommended_outcome_date", ITEM_FIELD[scenario.mode], GAP_FIELD[scenario.mode], "decision_timing_status"], f"{scenario.item}, revision {scenario.revision}, and the selected {model['selected_option']} outcome")
    descriptions = milestone_descriptions(
        case_reference=scenario.case_reference, record=scenario.item, revision=scenario.revision, subject=scenario.labels.subject, selected_option=model["selected_option"], selected_completion=model["selected_completion"],
        facts=model["facts"], primary_outcome=primary.outcome_label, correlated_systems=["itsm", "telemetry", "calendar", "oncall", "vendor", "messages", "chat"],
    )
    rubric = build_rubric_milestones(descriptions=descriptions, investigations=investigations, calculations=model["calculations"], assertions=assertions, answer_checks=checks, post_write_verifications=[readback])
    option_ids = [option["id"] for option in model["options"]]
    return {
        "task_id": scenario.task_id,
        "benchmark": BENCHMARK,
        "family": FAMILY_SLUG,
        "benchmark_version": FAMILY_VERSION,
        "mode": scenario.mode,
        "level": "employee-decision",
        "title": scenario.title,
        "role": scenario.role,
        "instruction": scenario.instruction,
        "as_of": AS_OF,
        "world": dict(ORGANIZATION),
        "seed_tables": seed_tables(scenario, drive_files, evidence),
        "assets": assets,
        "decision_model": {key: value for key, value in model.items() if key not in {"answer", "answer_descriptions"}},
        "answer_schema": answer_schema(answer, model["answer_descriptions"], option_ids),
        "expected": {"answer": answer, "answer_checks": checks, "calculations": model["calculations"], "assertions": assertions, "investigations": investigations, "post_write_verifications": [readback]},
        "required_investigations": investigations,
        "required_reads": [step["tool"] for step in steps if step["control"] and step["phase"] in {"context", "investigation"}],
        "required_read_calls": [item["any_of"][0] for item in investigations],
        "post_write_verifications": [readback],
        "oracle_steps": steps,
        "sequence_signature": sequence_signature(steps),
        "allowed_write_tables": sorted({primary.table, *primary.extra_tables, "note_drafts", "mutations", "answers", "audit_log"}),
        "rubric_milestones": rubric,
        "negative_controls": {"unauthorized_write": dict(scenario.unauthorized_write), "wrong_evidence": {"tool": "drive.files.export", "arguments": {"file_id": file_ids[scenario.decoy_doc.path]}}},
        "reference_records": {
            "case_reference": scenario.case_reference,
            "itsm": {"service_code": scenario.service.code, "service_search": {"tool": "itsm.cis.search", "arguments": {"identifier": scenario.service.code}}, "change_id": scenario.primary_change.change_id},
            "messages": {"search_query": scenario.case_reference},
            "drive": {"case_folder_query": scenario.case_reference, "policy_query": POLICY_QUERY},
            "telemetry": {"slo_id": scenario.slo.slo_id},
            "calendar": {"lanes": [lane.lane_id for lane in scenario.lanes], "calendar_window": scenario.windows_query},
            "oncall": {"secondary_schedule": scenario.secondary_schedule.schedule_id},
            "vendor": {"advisory_id": scenario.advisory.advisory_id},
            "approvals": {"approval_id": scenario.approval.approval_id},
            "chat": {"thread_id": scenario.chat.thread_id},
        },
        "starting_records": [
            *[{"system": "itsm", "resource_type": "ChangeRequest", "resource_id": c.change_id, "status": c.state} for c in scenario.changes],
            *[{"system": "itsm", "resource_type": "ChangeTask", "resource_id": row["task_id"], "status": row["status"]} for row in scenario.seed.get("tasks", ())],
            *[{"system": "itsm", "resource_type": "PlannedOutage", "resource_id": row["outage_id"], "status": row["status"]} for row in scenario.seed.get("outages", ())],
            *[{"system": "oncall", "resource_type": "Override", "resource_id": row["override_id"], "status": row["status"]} for row in scenario.seed.get("overrides", ())],
        ],
        "evaluation": {"metric": "HubScore", "strict_pass": "every rubric milestone passes", "llm_judge_calls": 0},
        "workflow": {"reads": len([s for s in steps if s["phase"] in {"context", "investigation"}]), "writes": 2, "readbacks": 1, "answer_fields": len(answer)},
    }


def build_tasks() -> list[dict[str, Any]]:
    return [build_task(scenario) for scenario in scenarios()]


__all__ = ["BENCHMARK", "FAMILY_SLUG", "FAMILY_VERSION", "build_task", "build_tasks", "calendar", "eligible_windows", "first_windows_on_or_after", "verify_numbers", "version_affected"]
