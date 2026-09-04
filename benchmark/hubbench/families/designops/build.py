"""Assemble DesignOps tasks: seed tables, scattered evidence, decision model, sealed contract.

Every declared number in a scenario is recomputed from the seeded world
(BOM where-used, certification register, fixture-lot register, release
calendar, cut-in reservations, supplier quotes) and the build fails on any
disagreement, so the answer contract can never drift from the data the agent
actually sees.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from ...engine.assets import CSV, EML, JSON, MARKDOWN, PDF, XLSX, YAML, asset, eml, yaml_lines
from ...engine.catalog import answer_checks, build_rubric_milestones, milestone_descriptions, sequence_signature
from ...engine.decision import DecisionInputs, answer_schema, build_decision_model
from ...engine.families import CONTEXT_TOOL, SUBMIT_TOOL
from ...engine.grading_contracts import fact_text_contract
from ...engine.quality_assets import quality_support_assets, quality_support_investigations, scoped_csv, scoped_markdown
from . import tools as design_tools
from .policy import SUPERSEDED_PROCEDURE, effective_procedure
from .scenarios import scenarios
from .specs import (
    AS_OF,
    ENGINEERS,
    ORGANIZATION,
    PLANTS,
    SUPPLIERS,
    USERS,
    WINDOW_HOURS,
    WINDOW_TIMES,
    BomLine,
    Certification,
    ChangeOrder,
    FixtureSet,
    Reservation,
    Scenario,
    business_days,
    lines_by_id,
    next_business_day,
    parts_by_id,
    window_id,
)

BENCHMARK = "HubBench"
FAMILY_SLUG = "designops"
FAMILY_VERSION = "1.0.1"
PRIMARY_KEYS = {
    "change_orders": "change_id",
    "supplier_orders": "order_id",
    "fixture_transfers": "transfer_id",
    "cutin_reservations": "reservation_id",
}
ITEM_FIELD = {"plan": "coverage_item_or_resource", "quantity": "controlled_item_or_record", "schedule": "affected_resource_or_operation"}
GAP_FIELD = {"plan": "shortage_quantity", "quantity": "transaction_quantity", "schedule": "capacity_gap"}
CASE_FOLDER = "Engineering Change Office/Cases/{case}"
OPEN_SOURCE_ANCHORS = (
    {
        "name": "CAD-Bench",
        "harbor_dataset": "gnucleus-ai/cad-bench",
        "harbor_url": "https://hub.harborframework.com/datasets/gnucleus-ai/cad-bench/latest",
        "upstream_url": "https://cadbench.ai",
        "evaluation_shape": "parametric CAD tasks with executable geometry and editability checks",
        "distribution_note": "no upstream tasks, models, or scores redistributed",
    },
    {
        "name": "HWE-Bench",
        "harbor_dataset": "hwe-bench/hwe-bench",
        "harbor_url": "https://hub.harborframework.com/datasets/hwe-bench/hwe-bench/latest",
        "upstream_url": "https://hub.harborframework.com/datasets/hwe-bench/hwe-bench",
        "evaluation_shape": "hardware-engineering tasks with deterministic artifact verification",
        "distribution_note": "no upstream tasks or scores redistributed",
    },
    {
        "name": "FactoryBench-100",
        "harbor_dataset": "blobfishai/factorybench-100",
        "harbor_url": "https://hub.harborframework.com/datasets/blobfishai/factorybench-100/latest",
        "upstream_url": "https://github.com/blobfishai/factory-agent-simulation",
        "license": "Apache-2.0",
        "evaluation_shape": "factory scheduling decisions over an ERP mock with a deterministic contract verifier; this family covers the engineering-change side that it does not",
    },
)
PLAN_SELECTED_OPTIONS = {"release_after_standard_recert": "standard", "expedite_recert_test_slot": "expedited"}
CORRELATED_SYSTEMS = ["plm", "eco", "bom", "cert", "tooling", "calendar", "messages", "chat"]


# --------------------------------------------------------------------------- #
# Derivations and cross-checks
# --------------------------------------------------------------------------- #


def _revision_status(scenario: Scenario, part_id: str, revision: str) -> str:
    part = parts_by_id(scenario).get(part_id)
    if part is None:
        return "UNKNOWN"
    return next((item.status for item in part.revisions if item.revision == revision), "UNKNOWN")


def where_used_lines(scenario: Scenario) -> list[BomLine]:
    return [line for line in scenario.bom_lines if line.component_part_id == scenario.part.part_id]


def _line_excluded(scenario: Scenario, line: BomLine) -> bool:
    return _revision_status(scenario, line.parent_part_id, line.parent_revision) != "RELEASED" or line.line_kind != "primary" or line.effectivity_end is not None


def in_scope_assemblies(scenario: Scenario) -> list[str]:
    seen: list[str] = []
    for line in where_used_lines(scenario):
        if not _line_excluded(scenario, line) and line.parent_part_id not in seen:
            seen.append(line.parent_part_id)
    return seen


def _cert_invalidated(scenario: Scenario, cert: Certification) -> bool:
    return cert.status == "ACTIVE" and scenario.change.change_class == "CLASS_I" and cert.covered.get(scenario.part.part_id) == scenario.change.from_revision


def certification_rows(scenario: Scenario, assemblies: list[str]) -> list[Certification]:
    return [cert for cert in scenario.certifications if cert.assembly_part_id in assemblies]


def _calibration_horizon(scenario: Scenario) -> str:
    return (date.fromisoformat(AS_OF) + timedelta(days=scenario.primary_family.min_remaining_calibration_days)).isoformat()


def _set_excluded(item: FixtureSet, scenario: Scenario) -> bool:
    return item.status != "CALIBRATED" or item.reserved_for is not None or item.register_excluded or item.calibration_due <= _calibration_horizon(scenario)


def calendar(scenario: Scenario) -> dict[tuple[str, str, str], dict[str, Any]]:
    overrides = {(item.day, item.line, item.session): item for item in scenario.windows}
    grid: dict[tuple[str, str, str], dict[str, Any]] = {}
    for day in business_days():
        for line in scenario.lines:
            for session in ("AM", "PM"):
                key = (day, line.line_id, session)
                override = overrides.get(key)
                if override is None:
                    entry = {"status": "busy", "hold_reason": "scheduled production", "reservation_id": None}
                elif override.status == "busy" and override.reason.startswith("RES-"):
                    entry = {"status": "busy", "hold_reason": "reserved", "reservation_id": override.reason}
                elif override.status == "free":
                    entry = {"status": "free", "hold_reason": None, "reservation_id": None}
                else:
                    entry = {"status": override.status, "hold_reason": override.reason or override.status, "reservation_id": None}
                grid[key] = entry
    return grid


def first_window_on_or_after(scenario: Scenario, start: str, windows_needed: int, lines: list[str]) -> tuple[str, str, str] | None:
    grid = calendar(scenario)
    active = {line.line_id for line in scenario.lines if line.status == "ACTIVE"}
    for day in business_days():
        if day < start:
            continue
        for line in lines:
            if line not in active:
                continue
            free = [session for session in ("AM", "PM") if grid[(day, line, session)]["status"] == "free"]
            if windows_needed == 1 and free:
                return day, line, free[0]
            if windows_needed == 2 and len(free) == 2:
                return day, line, "AM+PM"
    return None


def in_scope_runs(scenario: Scenario) -> list[Reservation]:
    window = scenario.numbers.get("in_scope_window")
    if not window:
        return []
    selected = [
        reservation
        for reservation in scenario.reservations
        if reservation.status == "booked" and reservation.start is not None and reservation.change_id == scenario.change.change_id and window[0] <= reservation.start[:10] <= window[1]
    ]
    return sorted(selected, key=lambda item: (item.start, item.reservation_id))


def cutin_sets(scenario: Scenario, reservation: Reservation) -> int:
    line = lines_by_id(scenario)[reservation.line_id or ""]
    return line.stations * scenario.primary_family.sets_per_station


def _session_of(start: str) -> str:
    return "AM" if start[11:] < WINDOW_TIMES["PM"][0] else "PM"


def _run_hours(change: ChangeOrder) -> float:
    return (change.fai_minutes + change.changeover_minutes) / 60


def verify_numbers(scenario: Scenario) -> None:
    numbers = scenario.numbers
    extra = scenario.extra_answer
    family = scenario.primary_family
    lines = lines_by_id(scenario)
    problems: list[str] = []

    def check(label: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            problems.append(f"{label}: computed {actual!r} but scenario declares {expected!r}")

    def intish(value: float) -> Any:
        return int(value) if float(value).is_integer() else value

    scoped_sets = [item for item in scenario.fixture_sets if item.family == family.code and item.plant_id == numbers["coverage_plant"]]
    affected_assemblies = [item.assembly_part_id for item in scenario.affected_items if item.in_scope]
    invalidated_count = sum(1 for cert in certification_rows(scenario, affected_assemblies) if _cert_invalidated(scenario, cert))
    if scenario.mode == "quantity":
        observed = sum(item.sets for item in scoped_sets)
        excluded = sum(item.sets for item in scoped_sets if _set_excluded(item, scenario))
        check("observed", observed, numbers["observed"])
        check("excluded", excluded, numbers["excluded"])
        check("eligible", observed - excluded, numbers["eligible"])
        runs = in_scope_runs(scenario)
        check("scheduled_cutins", len(runs), extra["scheduled_cutins"])
        check("scope", sum(cutin_sets(scenario, run) for run in runs), numbers["scope"])
        if runs:
            first = runs[0]
            check("first_cutin_window", f"{first.line_id}/{first.start[:10]}/{_session_of(first.start)}", extra["first_cutin_window"])
            check("business_need", first.start[:10], scenario.business_need)
        check("sets_per_station", family.sets_per_station, extra["sets_per_station"])
        if "measured_line" in numbers:
            check("rebalanced_line_stations", lines[numbers["measured_line"]].stations, extra["rebalanced_line_stations"])
        if "margin" in numbers:
            check("transaction_quantity", numbers["gap"] + numbers["margin"], numbers["transaction_quantity"])
            check("margin_sets", numbers["margin"], extra["margin_sets"])
        if "receiving_usable" in numbers:
            receiving = [item for item in scenario.fixture_sets if item.family == family.code and item.plant_id == numbers["receiving_plant"] and not _set_excluded(item, scenario)]
            check("receiving_usable", sum(item.sets for item in receiving), numbers["receiving_usable"])
            check("receiving_plant_usable", numbers["receiving_usable"], extra["receiving_plant_usable"])
            check("transaction_quantity", min(numbers["scope"] - numbers["receiving_usable"], numbers["eligible"]), numbers["transaction_quantity"])
        if "kelbrook_reserved_sets" in extra:
            check("kelbrook_reserved_sets", sum(item.sets for item in scoped_sets if item.reserved_for), extra["kelbrook_reserved_sets"])
        check("certifications_invalidated", invalidated_count, extra["certifications_invalidated"])
    if scenario.mode == "plan":
        gross = where_used_lines(scenario)
        excluded_lines = [line for line in gross if _line_excluded(scenario, line)]
        assemblies = in_scope_assemblies(scenario)
        check("where_used_lines_gross", len(gross), extra["where_used_lines_gross"])
        check("where_used_lines_excluded", len(excluded_lines), extra["where_used_lines_excluded"])
        check("scope", len(gross) - len(excluded_lines), numbers["scope"])
        check("affected items agree with live where-used", sorted(affected_assemblies), sorted(assemblies))
        certs = certification_rows(scenario, assemblies)
        lapsed = sum(1 for cert in certs if cert.status != "ACTIVE")
        invalidated = sum(1 for cert in certs if _cert_invalidated(scenario, cert))
        check("observed", len(certs), numbers["observed"])
        check("lapsed_certifications", lapsed, extra["lapsed_certifications"])
        check("invalidated_certifications", invalidated, extra["invalidated_certifications"])
        check("excluded", lapsed + invalidated, numbers["excluded"])
        check("eligible", len(certs) - lapsed - invalidated, numbers["eligible"])
        check("change_class", scenario.change.change_class, extra["change_class"])
        check("recert_test_fee_usd", intish(numbers["gap"] * scenario.quote.unit_price), extra["recert_test_fee_usd"])
        order = next((item for item in scenario.seed_orders if item.item_code == family.code), None)
        if order is None:
            problems.append("plan scenarios need an in-flight fixture order for the primary family")
        else:
            ready = next_business_day(order.expected_ready_date)
            check("fixture_ready_date", ready, extra["fixture_ready_date"])
            check("fixture_order_cost_usd", intish(order.total_cost_usd), extra["fixture_order_cost_usd"])
            if ready > min(scenario.standard_readiness, scenario.expedited_readiness):
                problems.append(f"fixture readiness {ready} is later than certification readiness; tooling would be the binding constraint")
    if scenario.mode == "schedule":
        grid = calendar(scenario)
        start, end = numbers["capacity_window"]
        days = [day for day in business_days() if start <= day <= end]
        keys = [(day, line, session) for day in days for line in numbers["eligible_lines"] for session in ("AM", "PM")]
        candidate = len(keys) * WINDOW_HOURS
        free = sum(1 for key in keys if grid[key]["status"] == "free")
        check("candidate", candidate, numbers["observed"])
        check("excluded", candidate - free * WINDOW_HOURS, numbers["excluded"])
        check("eligible", free * WINDOW_HOURS, numbers["eligible"])
        own = [item for item in scenario.reservations if item.change_id == scenario.change.change_id]
        hours = _run_hours(scenario.change) if numbers.get("scope_source") == "primary" else _run_hours(scenario.change) * len(own)
        check("scope", int(hours), numbers["scope"])
        usable = sum(item.sets for item in scoped_sets if not _set_excluded(item, scenario))
        check("fixture_sets_usable", usable, extra["fixture_sets_usable"])
        if numbers.get("scope_source") == "primary":
            selected_line = str(numbers["selected_resource"]).split("/")[0]
            required = lines[selected_line].stations * family.sets_per_station
        else:
            required = len(own) * family.sets_per_station
        check("fixture_sets_required", required, extra["fixture_sets_required"])
        check("windows_required", int(numbers["sessions_needed"]), extra["windows_required"])
        if "requested_day" in extra:
            check("requested_day", numbers["capacity_window"][0], extra["requested_day"])
        if "affected_reservations" in extra:
            check("affected_reservations", len(own), extra["affected_reservations"])
        if "runs_per_window" in extra:
            check("runs_per_window", extra["affected_reservations"] // extra["windows_required"], extra["runs_per_window"])
    gap = max(0, numbers["scope"] - numbers["eligible"])
    check("gap", gap, numbers["gap"])
    check("standard_readiness", next_business_day(scenario.quote.standard_date), scenario.standard_readiness)
    check("expedited_readiness", next_business_day(scenario.quote.expedited_date), scenario.expedited_readiness)
    windows_needed = 2 if scenario.mode == "schedule" and numbers.get("full_day_needed") else 1
    slot_lines = numbers["eligible_lines"]
    standard_slot = first_window_on_or_after(scenario, scenario.standard_readiness, windows_needed, slot_lines)
    expedited_slot = first_window_on_or_after(scenario, scenario.expedited_readiness, windows_needed, slot_lines)
    check("standard_slot_date", standard_slot[0] if standard_slot else None, numbers["standard_slot_date"])
    check("expedited_slot_date", expedited_slot[0] if expedited_slot else None, numbers["expedited_slot_date"])
    if scenario.mode == "plan":
        check("earliest_qualified_base_window", numbers["standard_slot_date"], extra["earliest_qualified_base_window"])
        expedited_option = scenario.options[1]
        check("expedited option date", expedited_slot[0] if expedited_slot else None, expedited_option.completion)
        check("expedite_completion_days_saved", (date.fromisoformat(numbers["standard_slot_date"]) - date.fromisoformat(numbers["expedited_slot_date"])).days, extra["expedite_completion_days_saved"])
        selected = next(option for option in scenario.options if option.recommended)
        if selected.id in PLAN_SELECTED_OPTIONS:
            readiness = scenario.standard_readiness if PLAN_SELECTED_OPTIONS[selected.id] == "standard" else scenario.expedited_readiness
            slot = first_window_on_or_after(scenario, readiness, 1, slot_lines)
            if slot is not None:
                check("selected_line_window", f"{slot[1]}/{slot[0]}/{slot[2]}", extra["selected_line_window"])
                check("selected completion", slot[0], selected.completion)
    if scenario.mode == "schedule":
        selected_date = next(option for option in scenario.options if option.recommended).completion
        if numbers.get("full_day_needed"):
            full_day = first_window_on_or_after(scenario, numbers["capacity_window"][0], 2, numbers["eligible_lines"])
            check("selected_resource", f"{full_day[1]}/{full_day[0]}/{full_day[2]}" if full_day else None, numbers["selected_resource"])
            check("selected completion", full_day[0] if full_day else None, selected_date)
        else:
            grid = calendar(scenario)
            free_windows = [key for key in sorted(grid) if key[1] in numbers["eligible_lines"] and grid[key]["status"] == "free" and key[0] >= numbers["capacity_window"][0]]
            check("selected_resource", f"{free_windows[0][1]}/{free_windows[0][0]}/{free_windows[0][2]}" if free_windows else None, numbers["selected_resource"])
            sessions_needed = int(numbers["sessions_needed"])
            check("selected completion", free_windows[sessions_needed - 1][0] if len(free_windows) >= sessions_needed else None, selected_date)
    if scenario.selected_window_id not in {window_id(line, day, session) for (day, line, session) in calendar(scenario)}:
        problems.append(f"selected window {scenario.selected_window_id} is not on the calendar")
    if problems:
        raise ValueError(f"{scenario.task_id} scenario data disagrees with its declared numbers:\n  " + "\n  ".join(problems))


# --------------------------------------------------------------------------- #
# Seed tables
# --------------------------------------------------------------------------- #


def _change_row(change: ChangeOrder) -> dict[str, Any]:
    return {
        "change_id": change.change_id,
        "part_id": change.part_id,
        "from_revision": change.from_revision,
        "to_revision": change.to_revision,
        "change_class": change.change_class,
        "title": change.title,
        "reason": change.reason,
        "state": change.state,
        "effectivity_basis": change.effectivity_basis,
        "effectivity_date": change.effectivity_date,
        "fixture_family": change.fixture_family,
        "fai_minutes": change.fai_minutes,
        "changeover_minutes": change.changeover_minutes,
        "required_by": change.required_by,
        "requested_by": change.requested_by,
        "opened_at": change.opened_at,
        "note": change.note or None,
        "revision": 1,
        "last_updated": "2026-05-08T12:00:00",
    }


def seed_tables(scenario: Scenario, drive_files: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grid = calendar(scenario)
    windows = [
        {"window_id": window_id(line, day, session), "line_id": line, "service_date": day, "session": session, "start_time": WINDOW_TIMES[session][0], "end_time": WINDOW_TIMES[session][1], **entry}
        for (day, line, session), entry in sorted(grid.items())
    ]
    return {
        "users": [dict(row) for row in USERS],
        "plants": [dict(row) for row in PLANTS],
        "engineers": [dict(row) for row in ENGINEERS],
        "parts": [
            {"part_id": p.part_id, "number": p.number, "name": p.name, "part_type": p.part_type, "owner_team": p.owner_team, "current_revision": p.current_revision, "primary_engineer_id": p.engineer_id}
            for p in scenario.all_parts
        ],
        "part_revisions": [
            {"revision_id": f"{p.part_id}-{r.revision}", "part_id": p.part_id, "revision": r.revision, "status": r.status, "released_on": r.released_on, "superseded_on": r.superseded_on, "note": r.note or None}
            for p in scenario.all_parts
            for r in p.revisions
        ],
        "cad_documents": [
            {"document_id": d.document_id, "part_id": d.part_id, "kind": d.kind, "number": d.number, "version": d.version, "revision": d.revision, "status": d.status, "checked_in_at": d.checked_in_at, "checked_in_by": d.checked_in_by, "note": d.note or None}
            for d in scenario.documents
        ],
        "checkins": [
            {"checkin_id": c.checkin_id, "document_id": c.document_id, "version": c.version, "checked_in_at": c.checked_in_at, "check_kind": c.check_kind, "status": c.status, "summary": c.summary}
            for c in scenario.checkins
        ],
        "change_orders": [_change_row(change) for change in (scenario.change, *scenario.other_changes)],
        "affected_items": [
            {"item_id": a.item_id, "change_id": a.change_id, "assembly_part_id": a.assembly_part_id, "assembly_revision": a.assembly_revision, "disposition": a.disposition, "in_scope": int(a.in_scope), "note": a.note or None}
            for a in scenario.affected_items
        ],
        "bom_lines": [
            {"line_id": b.line_id, "parent_part_id": b.parent_part_id, "parent_revision": b.parent_revision, "component_part_id": b.component_part_id, "find_number": b.find_number, "qty_per": b.qty_per, "line_kind": b.line_kind, "effectivity_end": b.effectivity_end, "note": b.note or None}
            for b in scenario.bom_lines
        ],
        "certifications": [
            {"cert_id": c.cert_id, "assembly_part_id": c.assembly_part_id, "assembly_revision": c.assembly_revision, "program": c.program, "status": c.status, "issued_on": c.issued_on, "expires_on": c.expires_on,
             "covered_components_json": json.dumps(c.covered, sort_keys=True), "recert_lead_days": c.recert_lead_days, "recert_test_fee_usd": c.recert_test_fee_usd, "note": c.note or None}
            for c in scenario.certifications
        ],
        "fixture_families": [
            {"family_code": f.code, "display": f.display, "sets_per_station": f.sets_per_station, "calibration_interval_days": f.calibration_interval_days, "minimum_remaining_calibration_days": f.min_remaining_calibration_days, "revision_specific": int(f.revision_specific), "interchangeable_with": f.interchangeable_with}
            for f in scenario.families
        ],
        "fixture_sets": [
            {"set_id": s.set_id, "family_code": s.family, "set_label": s.set_label, "plant_id": s.plant_id, "set_count": s.sets, "calibration_due": s.calibration_due, "status": s.status, "status_reason": s.reason, "reserved_for_change": s.reserved_for}
            for s in scenario.fixture_sets
        ],
        "lines": [
            {"line_id": line.line_id, "plant_id": line.plant_id, "name": line.name, "stations": line.stations, "status": line.status, "fai_capable": int(line.fai_capable), "status_note": line.note}
            for line in scenario.lines
        ],
        "release_windows": windows,
        "cutin_reservations": [
            {"reservation_id": r.reservation_id, "assembly_part_id": r.assembly_part_id, "change_id": r.change_id, "line_id": r.line_id, "start_time": r.start, "end_time": r.end, "status": r.status, "description": r.description, "revision": 1, "last_updated": "2026-05-08T12:00:00"}
            for r in scenario.reservations
        ],
        "suppliers": [dict(row) for row in SUPPLIERS],
        "supplier_quotes": [
            {"quote_id": q.quote_id, "supplier_id": q.supplier_id, "item_code": q.item_code, "reference": q.reference, "quantity_available": q.quantity_available, "standard_ready_date": q.standard_date, "expedited_ready_date": q.expedited_date,
             "expedite_fee_usd": q.fee, "unit_price_usd": q.unit_price, "valid_until": q.valid_until, "status": q.status, "note": q.note}
            for q in (scenario.quote, *scenario.other_quotes)
        ],
        "supplier_orders": [
            {"order_id": o.order_id, "supplier_id": o.supplier_id, "quote_id": o.quote_id, "item_code": o.item_code, "quantity": o.quantity, "unit": o.unit, "service_option": o.service_option, "expected_ready_date": o.expected_ready_date,
             "total_cost_usd": o.total_cost_usd, "status": o.status, "requested_by": "engineering_change_coordinator", "created_at": o.created_at, "revision": 1}
            for o in scenario.seed_orders
        ],
        "fixture_transfers": [dict(row) for row in scenario.seed.get("transfers", ())],
        "approvals": [
            {"approval_id": scenario.approval.approval_id, "subject": scenario.approval.subject, "approver_id": scenario.approval.approver_id, "approver_role": scenario.approval.approver_role, "status": "APPROVED", "granted_on": scenario.approval.granted_on, "scope_json": json.dumps(scenario.approval.scope, sort_keys=True)},
            {"approval_id": "AP-DO-0090", "subject": "Quarterly gauge-block and consumable replenishment standing order", "approver_id": "U-ADEYEMI", "approver_role": "configuration_manager", "status": "APPROVED", "granted_on": "2026-02-06", "scope_json": json.dumps({"category": "CONSUMABLES", "max_spend_usd": 9000}, sort_keys=True)},
        ],
        "messages": [
            {"message_id": scenario.email.message_id, "thread_id": scenario.email.thread_id, "channel": "email", "sender": scenario.email.sender, "recipients": scenario.email.recipients, "subject": scenario.email.subject, "sent_at": scenario.email.sent_at, "body": scenario.email.body,
             "attachments_json": json.dumps([{"name": name, "mime_type": "application/pdf"} for name in scenario.email.attachments]), "labels": f"{scenario.email.labels},{scenario.case_reference}"},
            {"message_id": f"MSG-{scenario.ordinal:04d}-00", "thread_id": f"THR-{scenario.ordinal:04d}-ECO", "channel": "email", "sender": "chidi.okafor@ashgrove.example", "recipients": "change-office@ashgrove.example", "subject": "Weekly change office note", "sent_at": "2026-05-08T08:00:00",
             "body": "Cut-in coverage for the week of 2026-05-11 is posted. Line capability flags are on the shared drive roster; no changes to protected freeze blocks.", "attachments_json": "[]", "labels": "operations"},
        ],
        "chat_threads": [
            {"thread_id": scenario.chat.thread_id, "channel": scenario.chat.channel, "title": scenario.chat.title, "messages_json": json.dumps([{"author": author, "ts": ts, "text": text} for author, ts, text in scenario.chat.messages])},
            {"thread_id": f"CHAT-{scenario.ordinal:04d}-GEN", "channel": "#engineering-change", "title": "General — drawing standards and crib access", "messages_json": json.dumps([{"author": "Chidi Okafor", "ts": "2026-05-07T16:40:00", "text": "Reminder: log every fixture-crib withdrawal in the tooling register."}])},
        ],
        "drive_files": drive_files,
        "evidence_files": evidence,
    }


# --------------------------------------------------------------------------- #
# Evidence room
# --------------------------------------------------------------------------- #


def _change_json(change: ChangeOrder) -> str:
    return json.dumps({"export": "eco.changes.get", "record": design_tools._change(_change_row(change))}, indent=2, sort_keys=True) + "\n"


def _part_summary_json(scenario: Scenario) -> str:
    part = scenario.part
    rendered = design_tools._part({"part_id": part.part_id, "number": part.number, "name": part.name, "part_type": part.part_type, "owner_team": part.owner_team, "current_revision": part.current_revision, "primary_engineer_id": part.engineer_id})
    revisions = [design_tools._revision({"revision_id": f"{part.part_id}-{r.revision}", "part_id": part.part_id, "revision": r.revision, "status": r.status, "released_on": r.released_on, "superseded_on": r.superseded_on, "note": r.note}) for r in part.revisions]
    documents = [design_tools._document({"document_id": d.document_id, "part_id": d.part_id, "kind": d.kind, "number": d.number, "version": d.version, "revision": d.revision, "status": d.status, "checked_in_at": d.checked_in_at, "checked_in_by": d.checked_in_by, "note": d.note}) for d in scenario.documents if d.part_id == part.part_id]
    return json.dumps({"export": "plm.parts.get + plm.revisions.list + plm.documents.list", "part": rendered, "revisions": revisions, "documents": documents}, indent=2, sort_keys=True) + "\n"


def _whereused_json(scenario: Scenario) -> str:
    parts = parts_by_id(scenario)
    lines = [
        design_tools._bom_line({"line_id": b.line_id, "parent_part_id": b.parent_part_id, "parent_number": parts[b.parent_part_id].number, "parent_revision": b.parent_revision, "parent_revision_status": _revision_status(scenario, b.parent_part_id, b.parent_revision), "component_part_id": b.component_part_id, "find_number": b.find_number, "qty_per": b.qty_per, "line_kind": b.line_kind, "effectivity_end": b.effectivity_end, "note": b.note})
        for b in where_used_lines(scenario)
    ]
    return json.dumps({"export": "bom.whereused.list", "case_reference": scenario.case_reference, "component_part_id": scenario.part.part_id, "lines": lines, "note": "Gross where-used; apply ECP-12 rev 5 section 1 to net the scope."}, indent=2, sort_keys=True) + "\n"


def _quote_text(scenario: Scenario) -> str:
    q = scenario.quote
    supplier = next(row for row in SUPPLIERS if row["supplier_id"] == q.supplier_id)
    unit = "configuration" if supplier["kind"] == "test_lab" else "set"
    return (
        f"{supplier['name']}\nQuotation {q.reference} (portal reference {q.quote_id})\nCustomer: Ashgrove Motion Systems Engineering Change Office, account {supplier['account_number']}\n"
        f"Case reference: {scenario.case_reference}\nItem: {q.item_code}\nQuantity available on this quotation: {q.quantity_available} {unit}(s)\nPrice per {unit}: USD {q.unit_price:.2f}\n"
        f"Standard ready date: {q.standard_date}\nExpedited ready date: {q.expedited_date} (expedite fee USD {q.fee}, flat)\nValid until: {q.valid_until}\nNotes: {q.note}\n"
        "Delivery is to the customer's receiving endpoint; release to the line is subject to the customer's incoming inspection, calibration check, or certificate issue.\n"
    )


def _decoy_asset(scenario: Scenario) -> dict[str, Any]:
    doc = scenario.decoy_doc
    if doc.kind == "policy_superseded":
        return asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=MARKDOWN, content=scoped_markdown(SUPERSEDED_PROCEDURE, task_id=scenario.task_id, case_reference=scenario.case_reference), preview="ECP-12 rev 3 retained for audit only; superseded by rev 5.")
    if doc.kind in {"duplicate_change_order", "superseded_change_order"}:
        change_id = doc.path.rsplit("/", 1)[-1].removeprefix("change-").removesuffix(".json")
        change = next(item for item in scenario.other_changes if item.change_id == change_id)
        return asset(doc.path, kind=doc.kind, title=doc.title, source="eco_export", media_type=JSON, content=_change_json(change), preview="A duplicate or superseded change order that must not drive the scope.")
    if doc.media_type == XLSX:
        return asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=XLSX, rows=[list(row) for row in doc.rows or ()], preview=doc.title)
    content = scoped_csv(doc.content, task_id=scenario.task_id, case_reference=scenario.case_reference) if doc.kind == "margin_policy" else doc.content
    return asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=doc.media_type, content=content, preview=doc.title)


def build_assets(scenario: Scenario) -> list[dict[str, Any]]:
    case = scenario.case_reference
    grid = calendar(scenario)
    parts = parts_by_id(scenario)
    assets: list[dict[str, Any]] = [
        asset("procedure/change-control-procedure-ecp-12.md", kind="policy", title="Change control procedure ECP-12 rev 5 (effective)", source="drive", media_type=MARKDOWN,
              content=scoped_markdown(effective_procedure(AS_OF), task_id=scenario.task_id, case_reference=case), preview="Scope, certification, tooling, calendar, and authority rules in force."),
    ]
    if scenario.decoy_doc.kind != "policy_superseded":
        assets.append(asset("procedure/superseded-change-control-procedure-rev3.md", kind="policy_superseded", title="Change control procedure ECP-12 rev 3 (superseded)", source="drive", media_type=MARKDOWN,
                            content=scoped_markdown(SUPERSEDED_PROCEDURE, task_id=scenario.task_id, case_reference=case), preview="ECP-12 rev 3 retained for audit only; superseded by rev 5."))
    assets.append(_decoy_asset(scenario))
    assets.extend(
        [
            asset(f"eco/change-{scenario.change.change_id}.json", kind="change_export", title=f"Change order {scenario.change.change_id} (ECO export)", source="eco_export", media_type=JSON, content=_change_json(scenario.change), preview="The active change: class, revisions, workflow state, durations."),
            asset(f"plm/part-{scenario.part.number}-summary.json", kind="part_summary", title=f"Part {scenario.part.number} summary with revisions and CAD documents (PLM export)", source="plm_export", media_type=JSON, content=_part_summary_json(scenario), preview="Part identity plus revision lifecycle and drawing/model versions."),
            asset(f"bom/where-used-{scenario.part.number}.json", kind="whereused_export", title=f"Where-used {scenario.part.number} (live BOM export)", source="bom_export", media_type=JSON, content=_whereused_json(scenario), preview="Gross where-used with parent revision status, line kind, and effectivity."),
            asset("cert/certification-register.csv", kind="certification_register", title="Certification register: certified configurations and covered components", source="cert_export", media_type=CSV,
                  content=scoped_csv("cert_id,assembly_number,assembly_revision,program,status,issued_on,expires_on,covered_components,recert_lead_days,recert_test_fee_usd\n"
                                     + "".join(f"{c.cert_id},{parts[c.assembly_part_id].number},{c.assembly_revision},{c.program},{c.status},{c.issued_on},{c.expires_on},{' '.join(f'{k}@{v}' for k, v in sorted(c.covered.items()))},{c.recert_lead_days},{c.recert_test_fee_usd:g}\n" for c in scenario.certifications),
                                     task_id=scenario.task_id, case_reference=case),
                  preview="Which certificates are active, what they cover, and the re-certification lead time."),
            asset("tooling/fixture-family-catalog.csv", kind="family_catalog", title="Fixture family catalog: sets per station and calibration horizon", source="tooling_export", media_type=CSV,
                  content=scoped_csv("family_code,display,sets_per_station,calibration_interval_days,minimum_remaining_calibration_days,revision_specific,interchangeable_with\n"
                                     + "".join(f"{f.code},{f.display},{f.sets_per_station},{f.calibration_interval_days},{f.min_remaining_calibration_days},{'yes' if f.revision_specific else 'no'},{f.interchangeable_with or ''}\n" for f in scenario.families),
                                     task_id=scenario.task_id, case_reference=case),
                  preview="Sets per station used for sizing and the 14-day minimum remaining calibration."),
            asset("tooling/fixture-holdings-by-lot.xlsx", kind="holdings_workbook", title="Registered fixture-set holdings by lot (gross)", source="tooling_workbook", media_type=XLSX,
                  rows=[["set_label", "family_code", "plant_id", "set_count", "calibration_due"], *[[s.set_label, s.family, s.plant_id, s.sets, s.calibration_due] for s in scenario.fixture_sets]],
                  preview="Gross set counts by lot; status and reservations live in the lot register."),
            asset("tooling/fixture-lot-status-register.csv", kind="calibration_register", title="Fixture-lot status register (calibration, reservation, revision notes)", source="tooling_export", media_type=CSV,
                  content="set_label,family_code,plant_id,status,status_reason,reserved_for_change,register_note\n" + "".join(f"{s.set_label},{s.family},{s.plant_id},{s.status},{s.reason or ''},{s.reserved_for or ''},{s.register_note}\n" for s in scenario.fixture_sets),
                  preview="Which lots are calibration-failed, reserved, or flagged."),
            asset("plm/checkin-history.csv", kind="checkin_history", title="CAD check-in history", source="plm_export", media_type=CSV,
                  content="checkin_id,document_id,document_number,version,revision,checked_in_at,check_kind,status,summary\n"
                  + "".join(f'{c.checkin_id},{c.document_id},{next(d.number for d in scenario.documents if d.document_id == c.document_id)},{c.version},{next(d.revision for d in scenario.documents if d.document_id == c.document_id)},{c.checked_in_at},{c.check_kind},{c.status},"{c.summary}"\n' for c in scenario.checkins),
                  preview="The check-ins that passed and failed on the way to the revision."),
            asset("calendar/release-calendar-2026-05-11.xlsx", kind="release_calendar", title="Release calendar, four weeks from 2026-05-11", source="calendar_workbook", media_type=XLSX,
                  rows=[["service_date", "line_id", "session", "start", "end", "status", "hold_reason"], *[[day, line, session, WINDOW_TIMES[session][0], WINDOW_TIMES[session][1], entry["status"], entry["hold_reason"] or ""] for (day, line, session), entry in sorted(grid.items())]],
                  preview="Every cut-in window with free / busy / protected / blocked status."),
            asset("calendar/line-roster-and-capabilities.csv", kind="line_roster", title="Line roster: stations, status, and CMM capability", source="calendar_export", media_type=CSV,
                  content=scoped_csv("line_id,plant_id,name,stations,status,fai_capable,note\n" + "".join(f"{line.line_id},{line.plant_id},{line.name},{line.stations},{line.status},{'yes' if line.fai_capable else 'no'},{line.note or ''}\n" for line in scenario.lines), task_id=scenario.task_id, case_reference=case),
                  preview="Current station counts, line status, and first-article capability."),
            asset(f"supplier/quote-{scenario.quote.reference}.pdf", kind="supplier_quote", title=f"Supplier quotation {scenario.quote.reference}", source="email_attachment", media_type=PDF, content=_quote_text(scenario), preview="Standard and expedited ready dates, fee, unit price, and validity."),
            asset(f"messages/{scenario.email.thread_id}.eml", kind="email", title=scenario.email.subject, source="messages", media_type=EML,
                  content=eml(from_addr=scenario.email.sender, to_addr=scenario.email.recipients, subject=scenario.email.subject, date=scenario.email.sent_at, message_id=f"{scenario.email.message_id}@ashgrove.example", body=scenario.email.body, attachments=list(scenario.email.attachments)),
                  preview="The request and the control date, in the requester's words."),
            asset(f"chat/{scenario.chat.thread_id}.json", kind="chat_thread", title=scenario.chat.title, source="chat", media_type=JSON,
                  content=json.dumps({"thread_id": scenario.chat.thread_id, "channel": scenario.chat.channel, "title": scenario.chat.title, "messages": [{"author": a, "ts": t, "text": x} for a, t, x in scenario.chat.messages]}, indent=2, sort_keys=True) + "\n",
                  preview="Team chat with certificate, lot, window, and authority remarks."),
            asset(f"approvals/approval-{scenario.approval.approval_id}.json", kind="approval", title=f"Approval record {scenario.approval.approval_id}", source="approvals_export", media_type=JSON,
                  content=json.dumps({"approval_id": scenario.approval.approval_id, "case_reference": case, "subject": scenario.approval.subject, "approver_id": scenario.approval.approver_id, "approver_role": scenario.approval.approver_role, "status": "APPROVED", "granted_on": scenario.approval.granted_on, "scope": scenario.approval.scope}, indent=2, sort_keys=True) + "\n",
                  preview="Exactly what is approved, for which record, and what is not."),
            asset(f"exports/starting-state-{scenario.task_id}.json", kind="starting_state", title="Starting-state export (reservations, supplier orders, transfers)", source="calendar_export", media_type=JSON,
                  content=json.dumps({"case_reference": case, "as_of": AS_OF,
                                      "reservations": [{"reservation_id": r.reservation_id, "assembly_part_id": r.assembly_part_id, "change_id": r.change_id, "line_id": r.line_id, "start": r.start, "end": r.end, "status": r.status} for r in scenario.reservations],
                                      "supplier_orders": [{"order_id": o.order_id, "item_code": o.item_code, "quantity": o.quantity, "expected_ready_date": o.expected_ready_date, "status": o.status} for o in scenario.seed_orders],
                                      "fixture_transfers": [dict(row) for row in scenario.seed.get("transfers", ())],
                                      "note": "Snapshot before any action; row order does not indicate applicability."}, indent=2, sort_keys=True) + "\n",
                  preview="Snapshot of calendar, portal, and register state before any action."),
        ]
    )
    for doc in scenario.docs:
        if doc.media_type == XLSX:
            assets.append(asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=XLSX, rows=[list(row) for row in doc.rows or ()], preview=doc.title))
        else:
            content = scoped_csv(doc.content, task_id=scenario.task_id, case_reference=case) if doc.kind == "margin_policy" else doc.content
            assets.append(asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=doc.media_type, content=content, preview=doc.title))
    assets.extend(
        quality_support_assets(task_id=scenario.task_id, ordinal=scenario.ordinal, case_reference=case, family_slug=FAMILY_SLUG, family_name="DesignOps", organization_name=ORGANIZATION["name"],
                               subject_id=scenario.item, as_of=AS_OF, current_revision=scenario.revision, anchors=OPEN_SOURCE_ANCHORS)
    )
    index = {"case_reference": case, "as_of": AS_OF, "files": [{"path": a["path"], "kind": a["kind"], "media_type": a["media_type"], "sha256": a["sha256"]} for a in assets]}
    assets.append(asset("audit/evidence-index.yaml", kind="evidence_index", title="Evidence index", source="drive", media_type=YAML, content=yaml_lines(index) + "\n", preview="Digest index of every evidence file in the room."))
    for position, record in enumerate(assets, start=1):
        record["asset_id"] = f"{scenario.task_id}-{position:02d}"
    return assets


def _folder(scenario: Scenario, record: dict[str, Any]) -> str:
    if record["kind"] == "policy":
        return "Engineering Change Office/Procedures"
    if record["kind"] == "policy_superseded":
        return "Engineering Change Office/Procedures/Archive"
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
        files.append({"file_id": file_id, "name": record["path"].rsplit("/", 1)[-1], "mime_type": record["media_type"], "modified_time": "2026-05-08T17:30:00", "folder": _folder(scenario, record), "content": record["content"], "sha256": record["sha256"]})
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
        {"id": "authoritative_identity", "sources": ["plm", "messages"], "statement": f"{scenario.case_reference}: {notes['identity']}; the effective revision is {scenario.revision}.",
         "rubric": f"Located {scenario.item} using immutable identifiers and preserved effective revision {scenario.revision}: {notes['identity']}."},
        {"id": "effective_requirement", "sources": ["eco", "bom", "drive"], "statement": f"The effective change order and procedure establish {labels.scope_label} = {numbers['scope']} {labels.unit}: {notes['requirement']}. The control date is {scenario.business_need} ({scenario.business_need_reason}).",
         "rubric": f"Applied the effective change order and procedure to establish {numbers['scope']} {labels.unit} for {labels.scope_label}, with control date {scenario.business_need}."},
        {"id": "eligible_coverage", "sources": ["cert", "tooling", "calendar", "drive"], "statement": f"{notes['coverage']}; eligibility requires netting the exclusions rather than trusting a header total.",
         "rubric": f"Reconciled {numbers['observed']} observed less {numbers['excluded']} excluded to {numbers['eligible']} supported {labels.unit} for {labels.eligible_label}."},
        {"id": "conditional_external_recovery", "sources": ["supplier", "messages"], "statement": f"{labels.external_label}: {notes['external']}; a supplier or laboratory quotation alone proves neither eligibility nor approval.",
         "rubric": f"Used the independently confirmed {scenario.expedited_readiness} expedited readiness input for {accelerated.id}, then separately derived its {accelerated.completion} operating outcome under {labels.constraint_label} instead of treating a supplier promise as authorization or a completion date."},
        {"id": "finite_capacity", "sources": ["calendar", "drive"], "statement": f"{labels.capacity_label}: {notes['capacity']}; protected and blocked windows cannot be displaced.",
         "rubric": f"Applied {labels.capacity_label} to derive the three option outcomes without using protected or blocked windows."},
        {"id": "approval_scope", "sources": ["approvals", "chat"], "statement": f"{notes['approval']}. The approval does not select an option in advance and does not authorize {unauthorized.id}.",
         "rubric": f"Applied {scenario.approval.approval_id} only to {selected.id} and {scenario.item}; kept {unauthorized.id} outside current authority."},
        {"id": "business_impact", "sources": ["messages", "chat"], "statement": f"{notes['impact']}; a faster or broader action has value only if it remains inside {labels.constraint_label}.",
         "rubric": f"Compared all three alternatives and selected {selected.id}: it is the best currently authorized response that satisfies {labels.constraint_label}."},
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
        "id": f"investigation_{number:02d}", "milestone_id": milestone, "description": description, "weight": weight, "before_primary_mutation": True,
        "any_of": [{"tool": tool, "arguments": arguments, "match": "result_contains", "expected_result_contains": expected}],
    }


def build_investigations(scenario: Scenario, file_ids: dict[str, str]) -> list[dict[str, Any]]:
    case = scenario.case_reference
    part = scenario.part
    change = scenario.change
    family = scenario.primary_family
    procedure_id = file_ids["procedure/change-control-procedure-ecp-12.md"]
    approval_id = file_ids[f"approvals/approval-{scenario.approval.approval_id}.json"]
    change_file_id = file_ids[f"eco/change-{change.change_id}.json"]
    first_line = next(line for line in where_used_lines(scenario) if not _line_excluded(scenario, line))
    first_set = next(item for item in scenario.fixture_sets if item.family == family.code)
    in_scope_items = [item for item in scenario.affected_items if item.in_scope]
    runs = in_scope_runs(scenario)
    if scenario.mode == "quantity":
        run_assemblies = {run.assembly_part_id for run in runs}
        affected_expected = {"items": [{"item_id": item.item_id} for item in in_scope_items if item.assembly_part_id in run_assemblies]}
        reservation_args = {"start_date": scenario.numbers["in_scope_window"][0], "end_date": scenario.numbers["in_scope_window"][1], "status": "booked"}
        reservation_expected = {"reservations": [{"id": run.reservation_id} for run in runs]}
    else:
        affected_expected = {"items": [{"item_id": item.item_id} for item in in_scope_items]}
        own = [r for r in scenario.reservations if r.change_id == change.change_id]
        reservation_args = {"change_id": change.change_id}
        reservation_expected = {"reservations": [{"id": r.reservation_id} for r in own]} if own else {"total": 0}
    first_assembly = in_scope_items[0].assembly_part_id
    first_cert = next(cert for cert in scenario.certifications if cert.assembly_part_id == first_assembly)
    seed_orders = [order for order in scenario.seed_orders if order.item_code == family.code]
    investigations = [
        _investigation(1, "investigation.scope", f"Established the isolated {case} scope, immutable handles, mounted systems, and evidence index before investigating {scenario.item}.", CONTEXT_TOOL, {}, {"reference_records": {"case_reference": case}}),
        _investigation(2, "investigation.scope", f"Located the task-scoped correspondence for {case} by searching the mailbox before opening any message; did not rely on a guessed sender or filename.", "messages.list", {"q": case}, {"messages": [{"id": scenario.email.message_id}]}),
        _investigation(3, "investigation.scope", f"Resolved part number {part.number} to the immutable part record through an identifier search rather than a name match against a similarly named part.", "plm.parts.search", {"number": part.number}, {"parts": [{"part_id": part.part_id}]}),
        _investigation(4, "investigation.scope", f"Listed the {case} case folder on the shared drive and identified the approval record and the change-order export by immutable file id.", "drive.files.list", {"q": case}, {"files": [{"id": approval_id}, {"id": change_file_id}]}),
        _investigation(5, "investigation.scope", "Listed the procedure folder and distinguished the effective ECP-12 rev 5 from the superseded rev 3 by file identity, not title.", "drive.files.list", {"q": "procedure"}, {"files": [{"id": procedure_id}]}),
        _investigation(6, "investigation.requirements", f"Read the active change order {change.change_id}: class, revisions, workflow state, effectivity, and run durations.", "eco.changes.get", {"change_id": change.change_id}, {"change_id": change.change_id, "state": change.state}),
        _investigation(7, "investigation.requirements", f"Read the live where-used for {part.number} with parent revision status and line kind; did not take the scope from an export or the affected-item list alone.", "bom.whereused.list", {"component_part_id": part.part_id}, {"lines": [{"line_id": first_line.line_id}]}),
        _investigation(8, "investigation.requirements", "Exported the effective ECP-12 rev 5 for the scope, certification, tooling, calendar, and authority rules; did not apply the superseded rev 3.", "drive.files.export", {"file_id": procedure_id}, {"file_id": procedure_id}),
        _investigation(9, "investigation.requirements", f"Read the fixture family record for {family.code}: sets per station and minimum remaining calibration.", "tooling.families.get", {"family_code": family.code}, {"family_code": family.code}),
        _investigation(10, "investigation.requirements", f"Listed the affected items of {change.change_id} ({', '.join(item.assembly_part_id for item in in_scope_items)}) and excluded the out-of-scope items.", "eco.affected.list", {"change_id": change.change_id}, affected_expected),
        _investigation(11, "investigation.requirements", f"Read the CAD check-in history for {part.number} to ground which version passed, which failed, and what is approved for release.", "plm.checkins.list", dict(scenario.checkin_query), dict(scenario.checkin_expected)),
        _investigation(12, "investigation.constraints", f"Listed the certified configurations for {first_assembly} with status, covered component revisions, and re-certification lead time before netting the coverage.", "cert.configurations.list", {"assembly_part_id": first_assembly}, {"certifications": [{"cert_id": first_cert.cert_id}]}),
        _investigation(13, "investigation.constraints", f"Read the release calendar windows for {scenario.windows_query['start_date']} onward to find the first free cut-in window that displaces no protected or blocked block.", "calendar.windows.list", dict(scenario.windows_query), {"windows": [{"id": scenario.selected_window_id}]}),
        _investigation(14, "investigation.constraints", f"Read the supplier-portal quotation {scenario.quote.quote_id} for the independently confirmed standard and expedited ready dates and the expedite fee.", "supplier.quotes.get", {"quote_id": scenario.quote.quote_id}, {"quote_id": scenario.quote.quote_id, "standard_ready_date": scenario.quote.standard_date}),
        _investigation(15, "investigation.authority", f"Read approval {scenario.approval.approval_id} for its exact scope: record, quantity, supplier or laboratory, fee allowance, and what it does not cover.", "approvals.get", {"approval_id": scenario.approval.approval_id}, {"approval_id": scenario.approval.approval_id}),
        _investigation(16, "investigation.authority", "Exported the approval record on the drive and confirmed it matches the workflow record before relying on it.", "drive.files.export", {"file_id": approval_id}, {"file_id": approval_id}),
        _investigation(17, "investigation.erp_correlation", f"Read the request message {scenario.email.message_id} for the documented control date and the business need in the requester's words.", "messages.get", {"message_id": scenario.email.message_id}, {"id": scenario.email.message_id}),
        _investigation(18, "investigation.erp_correlation", f"Read the team chat thread {scenario.chat.thread_id} for certificate, lot, window, and authority remarks that qualify the system records.", "chat.threads.get", {"thread_id": scenario.chat.thread_id}, {"thread_id": scenario.chat.thread_id}),
        _investigation(19, "investigation.erp_correlation", "Correlated the cut-in reservations that fix the schedule scope by immutable id.", "calendar.reservations.list", reservation_args, reservation_expected),
        _investigation(20, "investigation.constraints", f"Listed every {family.code} fixture lot with set count, calibration due date, status, and reservations before netting the tooling coverage.", "tooling.sets.list", {"family_code": family.code}, {"sets": [{"set_id": first_set.set_id}]}),
        _investigation(21, "investigation.constraints", f"Listed the supplier-portal orders for {family.code} to read any in-flight order's confirmed ready date and to avoid double-ordering; did not count an open order as sets on hand.", "supplier.orders.list", {"item_code": family.code}, {"orders": [{"order_id": order.order_id} for order in seed_orders]}),
    ]
    investigations.extend(quality_support_investigations(start_number=len(investigations) + 1, file_ids=file_ids, make_investigation=_investigation, case_reference=case, subject_id=scenario.item))
    return investigations


def build_oracle_steps(scenario: Scenario, investigations: list[dict[str, Any]], model: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [{"phase": "context", "tool": CONTEXT_TOOL, "arguments": {}, "control": True}]
    order = [2, 17, 3, 6, 10, 7, 11, 4, 5, 8, 9, 12, 20, 21, 19, 13, 14, 15, 16, 18]
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
            "phase": "collaboration", "tool": "notes.drafts.create",
            "arguments": {"recipient": scenario.collaboration["recipient"], "subject": scenario.collaboration["subject"], "body": scenario.collaboration["body"], "related_change_id": scenario.change.change_id, "related_part_id": scenario.part.part_id},
            "control": False,
        }
    )
    steps.append({"phase": "answer", "tool": SUBMIT_TOOL, "arguments": dict(model["answer"]), "control": False})
    return steps


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
            "payload_text_contains": [selected, completion], "payload_text_any_of": [[scenario.case_reference, scenario.part.number, scenario.change.change_id]], "weight": 1.5,
        },
        {
            "id": "containment_01", "milestone_id": "containment.scope",
            "description": f"Made exactly two state changes for {scenario.case_reference}: the primary change and the stakeholder draft; no additional order, transfer, release, or booking.",
            "table": "mutations", "where": {"task_id": task_id}, "count": 2, "weight": 1.0,
        },
    ]


@fact_text_contract
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
        facts=model["facts"], primary_outcome=primary.outcome_label, correlated_systems=CORRELATED_SYSTEMS,
    )
    rubric = build_rubric_milestones(descriptions=descriptions, investigations=investigations, calculations=model["calculations"], assertions=assertions, answer_checks=checks, post_write_verifications=[readback])
    option_ids = [option["id"] for option in model["options"]]
    return {
        "task_id": scenario.task_id, "benchmark": BENCHMARK, "family": FAMILY_SLUG, "benchmark_version": FAMILY_VERSION, "mode": scenario.mode, "level": "employee-decision",
        "title": scenario.title, "role": scenario.role, "instruction": scenario.instruction, "as_of": AS_OF, "world": dict(ORGANIZATION),
        "seed_tables": seed_tables(scenario, drive_files, evidence), "assets": assets,
        "decision_model": {key: value for key, value in model.items() if key not in {"answer", "answer_descriptions"}},
        "answer_schema": answer_schema(answer, model["answer_descriptions"], option_ids),
        "expected": {"answer": answer, "answer_checks": checks, "calculations": model["calculations"], "assertions": assertions, "investigations": investigations, "post_write_verifications": [readback]},
        "required_investigations": investigations,
        "required_reads": [step["tool"] for step in steps if step["control"] and step["phase"] in {"context", "investigation"}],
        "required_read_calls": [item["any_of"][0] for item in investigations],
        "post_write_verifications": [readback],
        "oracle_steps": steps, "sequence_signature": sequence_signature(steps),
        "allowed_write_tables": sorted({primary.table, *primary.extra_tables, "note_drafts", "mutations", "answers", "audit_log"}),
        "rubric_milestones": rubric,
        "negative_controls": {"unauthorized_write": dict(scenario.unauthorized_write), "wrong_evidence": {"tool": "drive.files.export", "arguments": {"file_id": file_ids[scenario.decoy_doc.path]}}},
        "reference_records": {
            "case_reference": scenario.case_reference,
            "plm": {"part_number": scenario.part.number, "part_search": {"tool": "plm.parts.search", "arguments": {"number": scenario.part.number}}},
            "messages": {"search_query": scenario.case_reference},
            "drive": {"case_folder_query": scenario.case_reference, "procedure_query": "procedure"},
            "eco": {"change_id": scenario.change.change_id},
            "bom": {"component_part_id": scenario.part.part_id},
            "cert": {"assembly_part_ids": [item.assembly_part_id for item in scenario.affected_items if item.in_scope]},
            "tooling": {"family_code": scenario.primary_family.code, "plants": sorted({item.plant_id for item in scenario.fixture_sets})},
            "calendar": {"calendar_window": scenario.windows_query},
            "supplier": {"quote_id": scenario.quote.quote_id},
            "approvals": {"approval_id": scenario.approval.approval_id},
            "chat": {"thread_id": scenario.chat.thread_id},
        },
        "starting_records": [
            *[{"system": "calendar", "resource_type": "Reservation", "resource_id": r.reservation_id, "status": r.status} for r in scenario.reservations],
            *[{"system": "supplier", "resource_type": "Order", "resource_id": o.order_id, "status": o.status} for o in scenario.seed_orders],
            *[{"system": "tooling", "resource_type": "Transfer", "resource_id": row["transfer_id"], "status": row["status"]} for row in scenario.seed.get("transfers", ())],
        ],
        "evaluation": {"metric": "HubScore", "strict_pass": "every rubric milestone passes", "llm_judge_calls": 0},
        "workflow": {"reads": len([s for s in steps if s["phase"] in {"context", "investigation"}]), "writes": 2, "readbacks": 1, "answer_fields": len(answer)},
    }


def build_tasks() -> list[dict[str, Any]]:
    return [build_task(scenario) for scenario in scenarios()]


__all__ = ["BENCHMARK", "FAMILY_SLUG", "FAMILY_VERSION", "build_task", "build_tasks", "calendar", "first_window_on_or_after", "verify_numbers"]
