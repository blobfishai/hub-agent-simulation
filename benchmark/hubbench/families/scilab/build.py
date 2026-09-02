"""Assemble SciLab tasks: seed tables, scattered evidence, decision model, sealed contract.

Every declared number in a scenario is recomputed from the seeded world
(reagent lots, analyser calendar, run requests, protocol versions, sample-batch
counts, shipment confirmations) and the build fails on any disagreement, so
the answer contract can never drift from the data the agent actually sees.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from ...engine.assets import CSV, EML, JSON, MARKDOWN, PDF, XLSX, YAML, asset, eml, yaml_lines
from ...engine.catalog import answer_checks, build_rubric_milestones, milestone_descriptions, sequence_signature
from ...engine.decision import DecisionInputs, answer_schema, build_decision_model
from ...engine.families import CONTEXT_TOOL, SUBMIT_TOOL
from ...engine.quality_assets import quality_support_assets, quality_support_investigations, scoped_csv, scoped_markdown
from . import tools as lab_tools
from .policy import SUPERSEDED_SOP, effective_sop
from .scenarios import scenarios
from .specs import (
    AS_OF,
    ORGANIZATION,
    SAMPLE_UNIT,
    SCIENTISTS,
    SITES,
    SUPPLIERS,
    USERS,
    VIAL_UNIT,
    WINDOW_HOURS,
    WINDOW_TIMES,
    Assay,
    Lot,
    Protocol,
    RunRequest,
    Scenario,
    lab_days,
    next_lab_day,
    plates_for_samples,
    request_samples,
    window_id,
)

BENCHMARK = "HubBench"
FAMILY_SLUG = "scilab"
FAMILY_VERSION = "1.0.0"
PRIMARY_KEYS = {
    "bookings": "booking_id",
    "reagent_orders": "order_id",
    "lot_transfers": "transfer_id",
}
ITEM_FIELD = {
    "plan": "coverage_item_or_resource",
    "quantity": "controlled_item_or_record",
    "schedule": "affected_resource_or_operation",
}
GAP_FIELD = {
    "plan": "shortage_quantity",
    "quantity": "transaction_quantity",
    "schedule": "capacity_gap",
}
CASE_FOLDER = "Assay Operations/Cases/{case}"
SOP_QUERY = "AO-014"
OPEN_SOURCE_ANCHORS = (
    {
        "name": "ScienceAgentBench",
        "harbor_dataset": "scienceagentbench/scienceagentbench",
        "harbor_url": "https://hub.harborframework.com/datasets/scienceagentbench/scienceagentbench/latest",
        "upstream_url": "https://github.com/OSU-NLP-Group/ScienceAgentBench",
        "license": "per the upstream repository; nothing from it is redistributed here",
        "evaluation_shape": "data-driven scientific tasks with program-executed, deterministic success checks",
    },
    {
        "name": "BixBench",
        "harbor_dataset": "futurehouse/bixbench",
        "harbor_url": "https://hub.harborframework.com/datasets/futurehouse/bixbench/latest",
        "upstream_url": "https://github.com/Future-House/BixBench",
        "license": "per the upstream repository; nothing from it is redistributed here",
        "evaluation_shape": "multi-step bioinformatics analysis capsules with exact graded answers",
    },
    {
        "name": "LAB-Bench",
        "harbor_dataset": "futurehouse/labbench",
        "harbor_url": "https://hub.harborframework.com/datasets/futurehouse/labbench/latest",
        "upstream_url": "https://github.com/Future-House/LAB-Bench",
        "license": "per the upstream repository; nothing from it is redistributed here",
        "evaluation_shape": "practical biology-laboratory reasoning over protocols, figures, and literature with exact answers",
    },
)
PLAN_SELECTED_OPTIONS = {
    "standard_order_plan": "standard",
    "expedite_supplier_shipment": "expedited",
}


# --------------------------------------------------------------------------- #
# Derivations and cross-checks
# --------------------------------------------------------------------------- #


def _assays_by_id(scenario: Scenario) -> dict[str, Assay]:
    return {item.assay_id: item for item in (scenario.assay, *scenario.other_assays)}


def _requests_by_id(scenario: Scenario) -> dict[str, RunRequest]:
    return {item.request_id: item for item in scenario.requests}


def _protocols_by_id(scenario: Scenario) -> dict[str, Protocol]:
    return {item.protocol_id: item for item in scenario.protocols}


def request_plates(scenario: Scenario, request: RunRequest) -> int:
    protocol = _protocols_by_id(scenario)[request.protocol_id]
    return plates_for_samples(request_samples(request, _assays_by_id(scenario)), protocol.samples_per_plate)


def request_vials(scenario: Scenario, request: RunRequest) -> int:
    protocol = _protocols_by_id(scenario)[request.protocol_id]
    return request_plates(scenario, request) * protocol.control_vials_per_plate * request.units_in_scope


def _dating_horizon(scenario: Scenario) -> str:
    return (date.fromisoformat(AS_OF) + timedelta(days=scenario.primary_reagent.min_dating_days)).isoformat()


def _lot_excluded(item: Lot, scenario: Scenario) -> bool:
    return item.status != "AVAILABLE" or item.reserved_for is not None or item.register_excluded or item.expiry <= _dating_horizon(scenario)


def calendar(scenario: Scenario) -> dict[tuple[str, str, str], dict[str, Any]]:
    overrides = {(item.day, item.instrument, item.session): item for item in scenario.windows}
    grid: dict[tuple[str, str, str], dict[str, Any]] = {}
    for day in lab_days():
        for instrument in scenario.instruments:
            for session in ("AM", "PM"):
                key = (day, instrument.instrument_id, session)
                override = overrides.get(key)
                if override is None:
                    entry = {"status": "busy", "hold_reason": "scheduled assay load", "booking_id": None}
                elif override.status == "busy" and override.reason.startswith("BK-"):
                    entry = {"status": "busy", "hold_reason": "booked", "booking_id": override.reason}
                elif override.status == "free":
                    entry = {"status": "free", "hold_reason": None, "booking_id": None}
                else:
                    entry = {"status": override.status, "hold_reason": override.reason or override.status, "booking_id": None}
                grid[key] = entry
    return grid


def first_window_on_or_after(scenario: Scenario, start: str, windows_needed: int, instruments: list[str]) -> tuple[str, str, str] | None:
    grid = calendar(scenario)
    active = {item.instrument_id for item in scenario.instruments if item.status == "ACTIVE"}
    for day in lab_days():
        if day < start:
            continue
        for instrument in instruments:
            if instrument not in active:
                continue
            free = [session for session in ("AM", "PM") if grid[(day, instrument, session)]["status"] == "free"]
            if windows_needed == 1 and free:
                return day, instrument, free[0]
            if windows_needed == 2 and len(free) == 2:
                return day, instrument, "AM+PM"
    return None


def in_scope_runs(scenario: Scenario) -> list[tuple[Any, RunRequest]]:
    window = scenario.numbers.get("in_scope_window")
    if not window:
        return []
    requests = _requests_by_id(scenario)
    code = scenario.primary_reagent.code
    selected = []
    for booking in scenario.bookings:
        if booking.status != "booked" or booking.start is None:
            continue
        request = requests.get(booking.request_id or "")
        if request is None or request.reagent_code != code:
            continue
        if window[0] <= booking.start[:10] <= window[1]:
            selected.append((booking, request))
    return sorted(selected, key=lambda item: (item[0].start, item[0].booking_id))


def verify_numbers(scenario: Scenario) -> None:
    numbers = scenario.numbers
    extra = scenario.extra_answer
    reagent = scenario.primary_reagent
    protocol = scenario.primary_protocol
    assays = _assays_by_id(scenario)
    problems: list[str] = []

    def check(label: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            problems.append(f"{label}: computed {actual!r} but scenario declares {expected!r}")

    scoped_lots = [item for item in scenario.lots if item.reagent_code == reagent.code and item.site_id == numbers["coverage_location"]]
    if scenario.mode in {"plan", "quantity"}:
        observed = sum(item.vials for item in scoped_lots)
        excluded = sum(item.vials for item in scoped_lots if _lot_excluded(item, scenario))
        check("observed", observed, numbers["observed"])
        check("excluded", excluded, numbers["excluded"])
        check("eligible", observed - excluded, numbers["eligible"])
        check("control_vials_per_plate", protocol.control_vials_per_plate, extra["control_vials_per_plate"])
        check("primary protocol status", protocol.status, "current")
    if scenario.mode == "plan":
        request = scenario.primary_request
        samples = request_samples(request, assays)
        plates = plates_for_samples(samples, protocol.samples_per_plate)
        check("required_samples", samples, extra["required_samples"])
        check("plates_per_unit", plates, extra["plates_per_unit"])
        check("units_in_scope", request.units_in_scope, extra["units_in_scope"])
        check("scope", plates * protocol.control_vials_per_plate * request.units_in_scope, numbers["scope"])
    if scenario.mode == "quantity":
        runs = in_scope_runs(scenario)
        check("scheduled_runs", len(runs), extra["scheduled_runs"])
        check("scope", sum(request_vials(scenario, request) for _, request in runs), numbers["scope"])
        first = runs[0][0] if runs else None
        if first is not None:
            session = "AM" if first.start[11:] < WINDOW_TIMES["PM"][0] else "PM"
            check("first_run_window", f"{first.instrument_id}/{first.start[:10]}/{session}", extra["first_run_window"])
            check("business_need", first.start[:10], scenario.business_need)
        metered = [request for _, request in runs if request.unit_basis == "metered"]
        if metered and "metered_samples" in extra:
            check("metered_samples", assays[metered[0].assay_id].meter_value, extra["metered_samples"])
        if runs and "samples_per_run" in extra:
            check("samples_per_run", request_samples(runs[0][1], assays), extra["samples_per_run"])
        if "margin" in numbers:
            check("transaction_quantity", numbers["gap"] + numbers["margin"], numbers["transaction_quantity"])
            check("margin_vials", numbers["margin"], extra["margin_vials"])
        if "receiving_usable" in numbers:
            receiving = [item for item in scenario.lots if item.reagent_code == reagent.code and item.site_id == "SITE-MAIN" and not _lot_excluded(item, scenario)]
            check("receiving_usable", sum(item.vials for item in receiving), numbers["receiving_usable"])
            check("receiving_site_usable", numbers["receiving_usable"], extra["receiving_site_usable"])
            check("transaction_quantity", min(numbers["scope"] - numbers["receiving_usable"], numbers["eligible"]), numbers["transaction_quantity"])
    if scenario.mode == "schedule":
        grid = calendar(scenario)
        start, end = numbers["capacity_window"]
        days = [day for day in lab_days() if start <= day <= end]
        keys = [(day, instrument, session) for day in days for instrument in numbers["eligible_instruments"] for session in ("AM", "PM")]
        candidate = len(keys) * WINDOW_HOURS
        free = sum(1 for key in keys if grid[key]["status"] == "free")
        check("candidate", candidate, numbers["observed"])
        check("excluded", candidate - free * WINDOW_HOURS, numbers["excluded"])
        check("eligible", free * WINDOW_HOURS, numbers["eligible"])
        affected = [request for request in scenario.requests if request.reagent_code == reagent.code]
        if numbers.get("scope_source") == "primary":
            hours = (scenario.primary_request.run_minutes + scenario.primary_request.read_minutes) / 60
        else:
            hours = sum((request.run_minutes + request.read_minutes) / 60 for request in affected)
        check("scope", int(hours), numbers["scope"])
        usable = sum(item.vials for item in scoped_lots if not _lot_excluded(item, scenario))
        if "control_vials_usable" in extra:
            check("control_vials_usable", usable, extra["control_vials_usable"])
        if numbers.get("scope_source") == "primary":
            required_vials = request_vials(scenario, scenario.primary_request)
        else:
            required_vials = sum(request_vials(scenario, request) for request in affected)
        if "control_vials_required" in extra:
            check("control_vials_required", required_vials, extra["control_vials_required"])
        if "windows_required" in extra:
            check("windows_required", int(numbers["sessions_needed"]), extra["windows_required"])
        if "requested_day" in extra:
            check("requested_day", numbers["capacity_window"][0], extra["requested_day"])
        if "affected_bookings" in extra:
            requests = _requests_by_id(scenario)
            stranded = [item for item in scenario.bookings if requests.get(item.request_id or "") in affected]
            check("affected_bookings", len(stranded), extra["affected_bookings"])
        if "runs_per_window" in extra:
            check("runs_per_window", extra["affected_bookings"] // extra["windows_required"], extra["runs_per_window"])
    gap = max(0, numbers["scope"] - numbers["eligible"])
    check("gap", gap, numbers["gap"])
    check("standard_readiness", next_lab_day(scenario.confirmation.standard_date), scenario.standard_readiness)
    check("expedited_readiness", next_lab_day(scenario.confirmation.expedited_date), scenario.expedited_readiness)
    windows_needed = 2 if scenario.mode == "schedule" and numbers.get("full_day_needed") else 1
    slot_instruments = numbers["eligible_instruments"]
    standard_slot = first_window_on_or_after(scenario, scenario.standard_readiness, windows_needed, slot_instruments)
    expedited_slot = first_window_on_or_after(scenario, scenario.expedited_readiness, windows_needed, slot_instruments)
    check("standard_slot_date", standard_slot[0] if standard_slot else None, numbers["standard_slot_date"])
    check("expedited_slot_date", expedited_slot[0] if expedited_slot else None, numbers["expedited_slot_date"])
    if scenario.mode == "plan":
        check("earliest_qualified_base_window", numbers["standard_slot_date"], extra["earliest_qualified_base_window"])
        expedited_option = scenario.options[1]
        check("expedited option date", expedited_slot[0] if expedited_slot else None, expedited_option.completion)
        check(
            "expedite_completion_days_saved",
            (date.fromisoformat(numbers["standard_slot_date"]) - date.fromisoformat(numbers["expedited_slot_date"])).days,
            extra["expedite_completion_days_saved"],
        )
        selected = next(option for option in scenario.options if option.recommended)
        if selected.id in PLAN_SELECTED_OPTIONS:
            readiness = scenario.standard_readiness if PLAN_SELECTED_OPTIONS[selected.id] == "standard" else scenario.expedited_readiness
            slot = first_window_on_or_after(scenario, readiness, 1, slot_instruments)
            if slot is not None:
                check("selected_instrument_window", f"{slot[1]}/{slot[0]}/{slot[2]}", extra["selected_instrument_window"])
                check("selected completion", slot[0], selected.completion)
    if scenario.mode == "schedule":
        selected_date = next(option for option in scenario.options if option.recommended).completion
        if numbers.get("full_day_needed"):
            full_day = first_window_on_or_after(scenario, numbers["capacity_window"][0], 2, numbers["eligible_instruments"])
            check("selected_resource", f"{full_day[1]}/{full_day[0]}/{full_day[2]}" if full_day else None, numbers["selected_resource"])
            check("selected completion", full_day[0] if full_day else None, selected_date)
        else:
            grid = calendar(scenario)
            free_windows = [
                key for key in sorted(grid)
                if key[1] in numbers["eligible_instruments"] and grid[key]["status"] == "free" and key[0] >= numbers["capacity_window"][0]
            ]
            check("selected_resource", f"{free_windows[0][1]}/{free_windows[0][0]}/{free_windows[0][2]}" if free_windows else None, numbers["selected_resource"])
            sessions_needed = int(numbers["sessions_needed"])
            check("selected completion", free_windows[sessions_needed - 1][0] if len(free_windows) >= sessions_needed else None, selected_date)
    if scenario.selected_window_id not in {window_id(instrument, day, session) for (day, instrument, session) in calendar(scenario)}:
        problems.append(f"selected window {scenario.selected_window_id} is not on the calendar")
    selected_instrument = _selected_instrument(scenario)
    if selected_instrument not in {item.instrument_id for item in scenario.instruments}:
        problems.append(f"selected window {scenario.selected_window_id} names an unknown analyser")
    if scenario.results and scenario.results_run_id not in {item.run_id for item in scenario.results}:
        problems.append(f"results run {scenario.results_run_id} has no QC results")
    if scenario.current_note.protocol_code != protocol.code:
        problems.append("the current method note does not reference the primary protocol code")
    if problems:
        raise ValueError(f"{scenario.task_id} scenario data disagrees with its declared numbers:\n  " + "\n  ".join(problems))


def _selected_instrument(scenario: Scenario) -> str:
    return f"INST-{scenario.selected_window_id.split('-')[1]}"


# --------------------------------------------------------------------------- #
# Seed tables
# --------------------------------------------------------------------------- #


def _batches(assay: Assay, *, stale: bool) -> list[dict[str, Any]]:
    rows = [
        {"batch_id": assay.batch_id, "assay_id": assay.assay_id, "metric": assay.meter_metric, "value": assay.meter_value, "unit": SAMPLE_UNIT, "counted_at": assay.meter_date, "status": "final"},
    ]
    if stale:
        rows.append(
            {"batch_id": assay.stale_batch_id, "assay_id": assay.assay_id, "metric": assay.meter_metric, "value": assay.stale_value, "unit": SAMPLE_UNIT, "counted_at": assay.stale_date, "status": "final"},
        )
    return rows


def _certificates(scenario: Scenario) -> list[dict[str, Any]]:
    rows = [
        {
            "cert_id": item.certificate_id,
            "instrument_id": item.instrument_id,
            "issued_on": item.cert_issued_on,
            "expires_on": item.cert_valid_until,
            "status": item.cert_status,
            "issuer": "Corvane metrology service",
            "note": item.note if item.cert_status != "VALID" else None,
        }
        for item in scenario.instruments
    ]
    rows.extend(
        {"cert_id": cert.cert_id, "instrument_id": cert.instrument_id, "issued_on": cert.issued_on, "expires_on": cert.expires_on, "status": cert.status, "issuer": cert.issuer, "note": cert.note or None}
        for cert in scenario.stale_certificates
    )
    return rows


def seed_tables(scenario: Scenario, drive_files: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grid = calendar(scenario)
    windows = [
        {
            "window_id": window_id(instrument, day, session),
            "instrument_id": instrument,
            "service_date": day,
            "session": session,
            "start_time": WINDOW_TIMES[session][0],
            "end_time": WINDOW_TIMES[session][1],
            **entry,
        }
        for (day, instrument, session), entry in sorted(grid.items())
    ]
    return {
        "users": [dict(row) for row in USERS],
        "sites": [dict(row) for row in SITES],
        "scientists": [dict(row) for row in SCIENTISTS],
        "assays": [
            {"assay_id": a.assay_id, "code": a.code, "name": a.name, "category": a.category, "owner_lab": a.owner_lab, "principal_scientist_id": a.scientist_id}
            for a in (scenario.assay, *scenario.other_assays)
        ],
        "sample_batches": [row for index, a in enumerate((scenario.assay, *scenario.other_assays)) for row in _batches(a, stale=index == 0)],
        "protocols": [
            {
                "protocol_id": p.protocol_id,
                "code": p.code,
                "version": p.version,
                "status": p.status,
                "samples_per_plate": p.samples_per_plate,
                "control_vials_per_plate": p.control_vials_per_plate,
                "control_rule": p.control_rule,
                "effective_from": p.effective_from,
                "superseded_by": p.superseded_by,
            }
            for p in scenario.protocols
        ],
        "reagents": [
            {
                "reagent_code": r.code,
                "display": r.display,
                "vial_format": r.vial_format,
                "storage": r.storage,
                "minimum_dating_days": r.min_dating_days,
                "validated": int(r.validated),
                "interchangeable_with": r.interchangeable_with,
            }
            for r in scenario.reagents
        ],
        "run_requests": [
            {
                "request_id": t.request_id,
                "assay_id": t.assay_id,
                "reagent_code": t.reagent_code,
                "protocol_id": t.protocol_id,
                "unit_kind": t.unit_kind,
                "unit_basis": t.unit_basis,
                "samples": t.samples,
                "units_in_scope": t.units_in_scope,
                "scope_note": t.scope_note,
                "run_minutes": t.run_minutes,
                "read_minutes": t.read_minutes,
                "status": t.status,
                "kind": t.kind,
                "priority": t.priority,
                "opened_at": t.opened_at,
                "requested_by": t.requested_by,
                "note": t.note or None,
            }
            for t in scenario.requests
        ],
        "reagent_lots": [
            {
                "lot_id": s.lot_id,
                "reagent_code": s.reagent_code,
                "lot_number": s.lot_number,
                "site_id": s.site_id,
                "vials_on_hand": s.vials,
                "expiry_date": s.expiry,
                "status": s.status,
                "status_reason": s.reason,
                "reserved_for_request": s.reserved_for,
            }
            for s in scenario.lots
        ],
        "instruments": [
            {
                "instrument_id": i.instrument_id,
                "site_id": "SITE-MAIN",
                "name": i.name,
                "model": i.model,
                "status": i.status,
                "validation_capable": int(i.validation_capable),
                "status_note": i.note,
            }
            for i in scenario.instruments
        ],
        "calibration_certificates": _certificates(scenario),
        "assay_runs": [
            {
                "run_id": r.run_id,
                "assay_id": r.assay_id,
                "protocol_id": r.protocol_id,
                "instrument_id": r.instrument_id,
                "kind": r.kind,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
                "status": r.status,
                "plates": r.plates,
                "summary": r.summary,
            }
            for r in scenario.runs
        ],
        "qc_results": [
            {
                "result_id": q.result_id,
                "run_id": q.run_id,
                "control_level": q.control_level,
                "lot_id": q.lot_id,
                "value": q.value,
                "unit": q.unit,
                "low_limit": q.low_limit,
                "high_limit": q.high_limit,
                "valid": int(q.valid),
                "note": q.note or None,
            }
            for q in scenario.results
        ],
        "instrument_windows": windows,
        "bookings": [
            {
                "booking_id": b.booking_id,
                "assay_id": b.assay_id,
                "request_id": b.request_id,
                "instrument_id": b.instrument_id,
                "start_time": b.start,
                "end_time": b.end,
                "status": b.status,
                "description": b.description,
                "revision": 1,
                "last_updated": "2026-05-08T12:00:00",
            }
            for b in scenario.bookings
        ],
        "suppliers": [dict(row) for row in SUPPLIERS],
        "shipment_confirmations": [
            {
                "confirmation_id": c.confirmation_id,
                "supplier_id": c.supplier_id,
                "reagent_code": c.reagent_code,
                "reference": c.reference,
                "vials_available": c.vials_available,
                "standard_delivery_date": c.standard_date,
                "expedited_delivery_date": c.expedited_date,
                "expedite_fee_usd": c.fee,
                "unit_price_usd": c.unit_price,
                "valid_until": c.valid_until,
                "status": c.status,
                "note": c.note,
            }
            for c in (scenario.confirmation, *scenario.other_confirmations)
        ],
        "reagent_orders": [
            {
                "order_id": "ORD-3400",
                "supplier_id": "SUP-CALDER",
                "confirmation_id": None,
                "reagent_code": scenario.reagents[-1].code,
                "quantity": 2,
                "unit": VIAL_UNIT,
                "delivery_option": "standard",
                "expected_delivery_date": "2026-04-29",
                "status": "RECEIVED",
                "requested_by": "assay_operations_coordinator",
                "created_at": "2026-04-24T09:30:00",
                "revision": 1,
            },
        ],
        "lot_transfers": [dict(row) for row in scenario.seed.get("transfers", ())],
        "method_notes": [
            {"note_id": n.note_id, "protocol_code": n.protocol_code, "version": n.version, "title": n.title, "status": n.status, "content": n.content, "updated_at": n.updated_at}
            for n in scenario.method_notes
        ],
        "approvals": [
            {
                "approval_id": scenario.approval.approval_id,
                "subject": scenario.approval.subject,
                "approver_id": scenario.approval.approver_id,
                "approver_role": scenario.approval.approver_role,
                "status": "APPROVED",
                "granted_on": scenario.approval.granted_on,
                "scope_json": json.dumps(scenario.approval.scope, sort_keys=True),
            },
            {
                "approval_id": "AP-SL-0090",
                "subject": "Quarterly pipette-tip and plate-seal consumables standing order",
                "approver_id": "U-VARGA",
                "approver_role": "qa_manager",
                "status": "APPROVED",
                "granted_on": "2026-02-06",
                "scope_json": json.dumps({"category": "CONSUMABLES", "max_spend_usd": 9000}, sort_keys=True),
            },
        ],
        "messages": [
            {
                "message_id": scenario.email.message_id,
                "thread_id": scenario.email.thread_id,
                "channel": "email",
                "sender": scenario.email.sender,
                "recipients": scenario.email.recipients,
                "subject": scenario.email.subject,
                "sent_at": scenario.email.sent_at,
                "body": scenario.email.body,
                "attachments_json": json.dumps([{"name": name, "mime_type": "application/pdf"} for name in scenario.email.attachments]),
                "labels": f"{scenario.email.labels},{scenario.case_reference}",
            },
            {
                "message_id": f"MSG-{scenario.ordinal:04d}-00",
                "thread_id": f"THR-{scenario.ordinal:04d}-OPS",
                "channel": "email",
                "sender": "petter.lindgren@corvane.example",
                "recipients": "assay-ops@corvane.example",
                "subject": "Weekly operations note",
                "sent_at": "2026-05-08T08:00:00",
                "body": "Operator rota for the week of 2026-05-11 is posted. Analyser qualification flags are on the shared drive roster; no changes to protected blocks.",
                "attachments_json": "[]",
                "labels": "operations",
            },
        ],
        "chat_threads": [
            {
                "thread_id": scenario.chat.thread_id,
                "channel": scenario.chat.channel,
                "title": scenario.chat.title,
                "messages_json": json.dumps([{"author": author, "ts": ts, "text": text} for author, ts, text in scenario.chat.messages]),
            },
            {
                "thread_id": f"CHAT-{scenario.ordinal:04d}-GEN",
                "channel": "#assay-ops",
                "title": "General — pipette calibration and cold-room access",
                "messages_json": json.dumps([{"author": "Petter Lindgren", "ts": "2026-05-07T16:40:00", "text": "Reminder: log every pipette calibration in the equipment tracker."}]),
            },
        ],
        "drive_files": drive_files,
        "evidence_files": evidence,
    }


# --------------------------------------------------------------------------- #
# Evidence room
# --------------------------------------------------------------------------- #


def _request_json(scenario: Scenario, request: RunRequest) -> str:
    reagent = next(r for r in scenario.reagents if r.code == request.reagent_code)
    protocol = _protocols_by_id(scenario)[request.protocol_id]
    row = {
        "request_id": request.request_id,
        "assay_id": request.assay_id,
        "reagent_code": request.reagent_code,
        "protocol_id": request.protocol_id,
        "unit_kind": request.unit_kind,
        "unit_basis": request.unit_basis,
        "samples": request.samples,
        "units_in_scope": request.units_in_scope,
        "scope_note": request.scope_note,
        "run_minutes": request.run_minutes,
        "read_minutes": request.read_minutes,
        "status": request.status,
        "kind": request.kind,
        "priority": request.priority,
        "opened_at": request.opened_at,
        "requested_by": request.requested_by,
        "note": request.note,
    }
    rendered = lab_tools._request(
        row,
        {"display": reagent.display, "vial_format": reagent.vial_format},
        {"code": protocol.code, "version": protocol.version, "status": protocol.status},
    )
    return json.dumps({"export": "lims.requests.get", "record": rendered}, indent=2, sort_keys=True) + "\n"


def _protocol_json(scenario: Scenario, protocol: Protocol) -> str:
    rendered = lab_tools._protocol(
        {
            "protocol_id": protocol.protocol_id,
            "code": protocol.code,
            "version": protocol.version,
            "status": protocol.status,
            "samples_per_plate": protocol.samples_per_plate,
            "control_vials_per_plate": protocol.control_vials_per_plate,
            "control_rule": protocol.control_rule,
            "effective_from": protocol.effective_from,
            "superseded_by": protocol.superseded_by,
        }
    )
    return json.dumps({"export": "lims.protocols.get", "case_reference": scenario.case_reference, "record": rendered}, indent=2, sort_keys=True) + "\n"


def _certificate_json(scenario: Scenario) -> str:
    cert = scenario.stale_certificates[0]
    record = {
        "cert_id": cert.cert_id,
        "instrument_id": cert.instrument_id,
        "issued_on": cert.issued_on,
        "expires_on": cert.expires_on,
        "status": cert.status,
        "issuer": cert.issuer,
        "note": cert.note,
    }
    return json.dumps({"export": "instruments.certificates.list", "case_reference": scenario.case_reference, "record": record}, indent=2, sort_keys=True) + "\n"


def _assay_summary_json(scenario: Scenario) -> str:
    assay = scenario.assay
    rendered = lab_tools._assay(
        {"assay_id": assay.assay_id, "code": assay.code, "name": assay.name, "category": assay.category, "owner_lab": assay.owner_lab, "principal_scientist_id": assay.scientist_id}
    )
    batches = [lab_tools._batch(row) for row in _batches(assay, stale=True)]
    return json.dumps({"export": "lims.assays.get + lims.batches.list", "assay": rendered, "sample_batches": batches}, indent=2, sort_keys=True) + "\n"


def _confirmation_text(scenario: Scenario) -> str:
    c = scenario.confirmation
    supplier = next(row["name"] for row in SUPPLIERS if row["supplier_id"] == c.supplier_id)
    account = next(row["account_number"] for row in SUPPLIERS if row["supplier_id"] == c.supplier_id)
    return (
        f"{supplier}\nShipment confirmation {c.reference} (system reference {c.confirmation_id})\nCustomer: Corvane Institute Assay Operations Core, account {account}\n"
        f"Case reference: {scenario.case_reference}\nItem: {c.reagent_code} — {scenario.primary_reagent.display}\nVials available for this confirmation: {c.vials_available}\nUnit price: USD {c.unit_price:.2f} per vial\n"
        f"Standard delivery date: {c.standard_date}\nExpedited delivery date: {c.expedited_date} (expedite fee USD {c.fee}, flat)\nValid until: {c.valid_until}\nCold chain: 2-8 °C validated shipper with temperature logger; frozen items on dry ice.\nNotes: {c.note}\n"
        "Vials are delivered to the customer's receiving bench; release to use is subject to the customer's incoming QC.\n"
    )


def _eln_export(scenario: Scenario) -> str:
    parts = [f"# ELN method notes — {scenario.primary_protocol.code} (export for {scenario.case_reference})\n"]
    for note in scenario.method_notes:
        parts.append(f"## {note.note_id} — {note.title}\n\nStatus: {note.status}. Protocol version: {note.version}. Updated: {note.updated_at}.\n\n{note.content}\n")
    return "\n".join(parts)


def _decoy_asset(scenario: Scenario) -> dict[str, Any]:
    doc = scenario.decoy_doc
    if doc.kind == "policy_superseded":
        return asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=MARKDOWN,
                     content=scoped_markdown(SUPERSEDED_SOP, task_id=scenario.task_id, case_reference=scenario.case_reference),
                     preview="2024 SOP edition retained for audit only; superseded by v3.")
    if doc.kind == "protocol_superseded":
        protocol = next(item for item in scenario.protocols if item.status == "superseded")
        return asset(doc.path, kind=doc.kind, title=doc.title, source="lims_export", media_type=JSON, content=_protocol_json(scenario, protocol),
                     preview="A superseded protocol version whose control requirement must not drive the plan.")
    if doc.kind == "decoy_request":
        request_id = doc.path.rsplit("/", 1)[-1].removeprefix("request-").removesuffix(".json")
        request = next(t for t in scenario.requests if t.request_id == request_id)
        return asset(doc.path, kind=doc.kind, title=doc.title, source="lims_export", media_type=JSON, content=_request_json(scenario, request),
                     preview="A similarly named or superseded run request that must not drive the requirement.")
    if doc.kind == "stale_certificate":
        return asset(doc.path, kind=doc.kind, title=doc.title, source="instruments_export", media_type=JSON, content=_certificate_json(scenario),
                     preview="An expired calibration certificate export that does not describe the analyser's current state.")
    if doc.media_type == XLSX:
        return asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=XLSX, rows=[list(row) for row in doc.rows or ()], preview=doc.title)
    content = scoped_csv(doc.content, task_id=scenario.task_id, case_reference=scenario.case_reference) if doc.kind == "margin_policy" else doc.content
    return asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=doc.media_type, content=content, preview=doc.title)


def build_assets(scenario: Scenario) -> list[dict[str, Any]]:
    case = scenario.case_reference
    grid = calendar(scenario)
    assays = _assays_by_id(scenario)
    assets: list[dict[str, Any]] = [
        asset(
            "sop/assay-operations-sop-ao-014.md",
            kind="policy",
            title="Assay operations SOP AO-014 v3 (effective)",
            source="drive",
            media_type=MARKDOWN,
            content=scoped_markdown(effective_sop(AS_OF), task_id=scenario.task_id, case_reference=case),
            preview="Sizing, usable-lot, window, and authority rules in force.",
        ),
    ]
    if scenario.decoy_doc.kind != "policy_superseded":
        assets.append(
            asset(
                "sop/superseded-assay-operations-sop-2024.md",
                kind="policy_superseded",
                title="Assay operations SOP AO-014 2024 edition (superseded)",
                source="drive",
                media_type=MARKDOWN,
                content=scoped_markdown(SUPERSEDED_SOP, task_id=scenario.task_id, case_reference=case),
                preview="2024 SOP edition retained for audit only; superseded by v3.",
            )
        )
    assets.append(_decoy_asset(scenario))
    assets.extend(
        [
            asset(
                f"lims/request-{scenario.primary_request.request_id}.json",
                kind="request_export",
                title=f"Run request {scenario.primary_request.request_id} (LIMS export)",
                source="lims_export",
                media_type=JSON,
                content=_request_json(scenario, scenario.primary_request),
                preview="The active run request: sample basis, scope, protocol version, and run durations.",
            ),
            asset(
                f"lims/assay-{scenario.assay.code}-summary.json",
                kind="assay_summary",
                title=f"Assay {scenario.assay.code} summary with sample-batch counts (LIMS export)",
                source="lims_export",
                media_type=JSON,
                content=_assay_summary_json(scenario),
                preview="Assay identity plus current and historical sample-batch counts.",
            ),
            asset(
                f"lims/protocol-{scenario.primary_protocol.code}-versions.csv",
                kind="protocol_versions",
                title=f"Protocol {scenario.primary_protocol.code} version register",
                source="lims_export",
                media_type=CSV,
                content="protocol_id,code,version,status,samples_per_plate,control_vials_per_plate,effective_from,superseded_by\n"
                + "".join(f"{p.protocol_id},{p.code},{p.version},{p.status},{p.samples_per_plate},{p.control_vials_per_plate},{p.effective_from},{p.superseded_by or ''}\n" for p in scenario.protocols),
                preview="Every version of the protocol with its plate layout and control requirement; only one is current.",
            ),
            asset(
                "inventory/reagent-catalog.csv",
                kind="reagent_catalog",
                title="Reagent catalog: vial format, storage, and minimum dating",
                source="inventory_export",
                media_type=CSV,
                content="reagent_code,display,vial_format,storage,minimum_dating_days,validated,interchangeable_with\n"
                + "".join(f"{r.code},{r.display},{r.vial_format},{r.storage},{r.min_dating_days},{'yes' if r.validated else 'no'},{r.interchangeable_with or ''}\n" for r in scenario.reagents),
                preview="Vial formats and the 14-day minimum remaining dating.",
            ),
            asset(
                "inventory/lot-holdings-by-lot.xlsx",
                kind="holdings_workbook",
                title="On-hand control vials by lot (gross)",
                source="inventory_workbook",
                media_type=XLSX,
                rows=[
                    ["lot_number", "reagent_code", "site_id", "vials_on_hand", "expiry_date"],
                    *[[s.lot_number, s.reagent_code, s.site_id, s.vials, s.expiry] for s in scenario.lots],
                ],
                preview="Gross vial counts by lot; status and reservations live in the lot register.",
            ),
            asset(
                "inventory/lot-status-register.csv",
                kind="lot_status_register",
                title="Lot status register (quarantine, reservation, stability notes)",
                source="inventory_export",
                media_type=CSV,
                content="lot_number,reagent_code,site_id,status,status_reason,reserved_for_request,register_note\n"
                + "".join(f"{s.lot_number},{s.reagent_code},{s.site_id},{s.status},{s.reason or ''},{s.reserved_for or ''},{s.register_note}\n" for s in scenario.lots),
                preview="Which lots are quarantined, expired, reserved, or flagged.",
            ),
            asset(
                "lims/run-history-and-qc.csv",
                kind="run_history",
                title="Assay runs and QC control results",
                source="lims_export",
                media_type=CSV,
                content="run_id,assay_id,instrument_id,kind,started_at,finished_at,status,plates,summary\n"
                + "".join(f'{r.run_id},{r.assay_id or ""},{r.instrument_id},{r.kind},{r.started_at},{r.finished_at},{r.status},{r.plates},"{r.summary}"\n' for r in scenario.runs)
                + "\nresult_id,run_id,control_level,lot_id,value,unit,low_limit,high_limit,valid,note\n"
                + "".join(f'{q.result_id},{q.run_id},{q.control_level},{q.lot_id or ""},{q.value},{q.unit},{q.low_limit},{q.high_limit},{"yes" if q.valid else "no"},"{q.note}"\n' for q in scenario.results),
                preview="The runs that triggered the case and the control results that decided their validity.",
            ),
            asset(
                "instruments/analyser-calendar-2026-05-11.xlsx",
                kind="instrument_calendar",
                title="Analyser window calendar, three weeks from 2026-05-11",
                source="instruments_workbook",
                media_type=XLSX,
                rows=[
                    ["service_date", "instrument_id", "session", "start", "end", "status", "hold_reason"],
                    *[[day, instrument, session, WINDOW_TIMES[session][0], WINDOW_TIMES[session][1], entry["status"], entry["hold_reason"] or ""] for (day, instrument, session), entry in sorted(grid.items())],
                ],
                preview="Every analyser window with free / busy / protected / blocked status.",
            ),
            asset(
                "instruments/analyser-roster-and-certificates.csv",
                kind="instrument_roster",
                title="Analyser roster, qualification flags, and calibration certificates",
                source="instruments_export",
                media_type=CSV,
                content=scoped_csv(
                    "instrument_id,name,status,validation_capable,cert_id,cert_status,cert_valid_until,note\n"
                    + "".join(f"{i.instrument_id},{i.name},{i.status},{'yes' if i.validation_capable else 'no'},{i.certificate_id},{i.cert_status},{i.cert_valid_until},{i.note or ''}\n" for i in scenario.instruments),
                    task_id=scenario.task_id,
                    case_reference=case,
                ),
                preview="Analyser status, operational-qualification flags, and certificate validity for the week.",
            ),
            asset(
                f"eln/method-notes-{scenario.primary_protocol.code}.md",
                kind="eln_export",
                title=f"ELN method notes — {scenario.primary_protocol.code}",
                source="eln_export",
                media_type=MARKDOWN,
                content=_eln_export(scenario),
                preview="Current and superseded method notes for the protocol; only the current one applies.",
            ),
            asset(
                f"supplier/shipment-confirmation-{scenario.confirmation.reference}.pdf",
                kind="supplier_confirmation",
                title=f"Shipment confirmation {scenario.confirmation.reference}",
                source="email_attachment",
                media_type=PDF,
                content=_confirmation_text(scenario),
                preview="Standard and expedited delivery dates, expedite fee, validity, and cold-chain terms.",
            ),
            asset(
                f"messages/{scenario.email.thread_id}.eml",
                kind="email",
                title=scenario.email.subject,
                source="messages",
                media_type=EML,
                content=eml(
                    from_addr=scenario.email.sender,
                    to_addr=scenario.email.recipients,
                    subject=scenario.email.subject,
                    date=scenario.email.sent_at,
                    message_id=f"{scenario.email.message_id}@corvane.example",
                    body=scenario.email.body,
                    attachments=list(scenario.email.attachments),
                ),
                preview="The request and the control date, in the requester's words.",
            ),
            asset(
                f"chat/{scenario.chat.thread_id}.json",
                kind="chat_thread",
                title=scenario.chat.title,
                source="chat",
                media_type=JSON,
                content=json.dumps(
                    {"thread_id": scenario.chat.thread_id, "channel": scenario.chat.channel, "title": scenario.chat.title, "messages": [{"author": a, "ts": t, "text": x} for a, t, x in scenario.chat.messages]},
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                preview="Team chat with lot, window, and authority remarks.",
            ),
            asset(
                f"approvals/approval-{scenario.approval.approval_id}.json",
                kind="approval",
                title=f"Approval record {scenario.approval.approval_id}",
                source="approvals_export",
                media_type=JSON,
                content=json.dumps(
                    {
                        "approval_id": scenario.approval.approval_id,
                        "case_reference": case,
                        "subject": scenario.approval.subject,
                        "approver_id": scenario.approval.approver_id,
                        "approver_role": scenario.approval.approver_role,
                        "status": "APPROVED",
                        "granted_on": scenario.approval.granted_on,
                        "scope": scenario.approval.scope,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                preview="Exactly what is approved, for which record, and what is not.",
            ),
            asset(
                f"exports/starting-state-{scenario.task_id}.json",
                kind="starting_state",
                title="Starting-state export (bookings, orders, transfers)",
                source="instruments_export",
                media_type=JSON,
                content=json.dumps(
                    {
                        "case_reference": case,
                        "as_of": AS_OF,
                        "bookings": [
                            {"booking_id": b.booking_id, "assay_id": b.assay_id, "request_id": b.request_id, "instrument_id": b.instrument_id, "start": b.start, "end": b.end, "status": b.status}
                            for b in scenario.bookings
                        ],
                        "reagent_orders": [{"order_id": "ORD-3400", "status": "RECEIVED"}],
                        "lot_transfers": [dict(row) for row in scenario.seed.get("transfers", ())],
                        "note": "Snapshot before any action; row order does not indicate applicability.",
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                preview="Snapshot of schedule and inventory state before any action.",
            ),
        ]
    )
    for doc in scenario.docs:
        if doc.media_type == XLSX:
            assets.append(asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=XLSX, rows=[list(row) for row in doc.rows or ()], preview=doc.title))
        else:
            content = scoped_csv(doc.content, task_id=scenario.task_id, case_reference=case) if doc.kind == "margin_policy" else doc.content
            assets.append(asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=doc.media_type, content=content, preview=doc.title))
    assets.extend(
        quality_support_assets(
            task_id=scenario.task_id,
            ordinal=scenario.ordinal,
            case_reference=case,
            family_slug=FAMILY_SLUG,
            family_name="SciLab",
            organization_name=ORGANIZATION["name"],
            subject_id=scenario.item,
            as_of=AS_OF,
            current_revision=scenario.revision,
            anchors=OPEN_SOURCE_ANCHORS,
        )
    )
    index = {
        "case_reference": case,
        "as_of": AS_OF,
        "files": [{"path": a["path"], "kind": a["kind"], "media_type": a["media_type"], "sha256": a["sha256"]} for a in assets],
    }
    assets.append(
        asset(
            "audit/evidence-index.yaml",
            kind="evidence_index",
            title="Evidence index",
            source="drive",
            media_type=YAML,
            content=yaml_lines(index) + "\n",
            preview="Digest index of every evidence file in the room.",
        )
    )
    for position, record in enumerate(assets, start=1):
        record["asset_id"] = f"{scenario.task_id}-{position:02d}"
    del assays
    return assets


def _folder(scenario: Scenario, record: dict[str, Any]) -> str:
    if record["kind"] == "policy":
        return "Assay Operations/SOPs"
    if record["kind"] == "policy_superseded":
        return "Assay Operations/SOPs/Archive"
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
        files.append(
            {
                "file_id": file_id,
                "name": record["path"].rsplit("/", 1)[-1],
                "mime_type": record["media_type"],
                "modified_time": "2026-05-08T17:30:00",
                "folder": _folder(scenario, record),
                "content": record["content"],
                "sha256": record["sha256"],
            }
        )
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
        {
            "id": "authoritative_identity",
            "sources": ["lims", "messages"],
            "statement": f"{scenario.case_reference}: {notes['identity']}; the effective revision is {scenario.revision}.",
            "rubric": f"Located {scenario.item} using immutable identifiers and preserved effective revision {scenario.revision}: {notes['identity']}.",
        },
        {
            "id": "effective_requirement",
            "sources": ["lims", "eln", "drive"],
            "statement": f"The effective run request, protocol version, and SOP establish {labels.scope_label} = {numbers['scope']} {labels.unit}: {notes['requirement']}. The control date is {scenario.business_need} ({scenario.business_need_reason}).",
            "rubric": f"Applied the effective run request, protocol version, and SOP to establish {numbers['scope']} {labels.unit} for {labels.scope_label}, with control date {scenario.business_need}.",
        },
        {
            "id": "eligible_coverage",
            "sources": ["inventory", "instruments", "drive"],
            "statement": f"{notes['coverage']}; eligibility requires netting the exclusions rather than trusting a header total.",
            "rubric": f"Reconciled {numbers['observed']} observed less {numbers['excluded']} excluded to {numbers['eligible']} supported {labels.unit} for {labels.eligible_label}.",
        },
        {
            "id": "conditional_external_recovery",
            "sources": ["supplier", "messages"],
            "statement": f"{labels.external_label}: {notes['external']}; a supplier confirmation alone proves neither eligibility nor approval.",
            "rubric": f"Used the independently confirmed {scenario.expedited_readiness} expedited readiness input for {accelerated.id}, then separately derived its {accelerated.completion} operating outcome under {labels.constraint_label} instead of treating a supplier promise as authorization or a completion date.",
        },
        {
            "id": "finite_capacity",
            "sources": ["instruments", "drive"],
            "statement": f"{labels.capacity_label}: {notes['capacity']}; protected and blocked windows cannot be displaced.",
            "rubric": f"Applied {labels.capacity_label} to derive the three option outcomes without using protected or blocked windows.",
        },
        {
            "id": "approval_scope",
            "sources": ["approvals", "chat"],
            "statement": f"{notes['approval']}. The approval does not select an option in advance and does not authorize {unauthorized.id}.",
            "rubric": f"Applied {scenario.approval.approval_id} only to {selected.id} and {scenario.item}; kept {unauthorized.id} outside current authority.",
        },
        {
            "id": "business_impact",
            "sources": ["messages", "chat"],
            "statement": f"{notes['impact']}; a faster or broader action has value only if it remains inside {labels.constraint_label}.",
            "rubric": f"Compared all three alternatives and selected {selected.id}: it is the best currently authorized response that satisfies {labels.constraint_label}.",
        },
    )


def build_model(scenario: Scenario) -> dict[str, Any]:
    numbers = scenario.numbers
    inputs = DecisionInputs(
        mode=scenario.mode,
        labels=scenario.labels,
        item=scenario.item,
        record=scenario.item,
        revision=scenario.revision,
        scope=int(numbers["scope"]),
        observed=int(numbers["observed"]),
        excluded=int(numbers["excluded"]),
        eligible=int(numbers["eligible"]),
        gap=int(numbers["gap"]),
        business_need=scenario.business_need,
        standard_readiness=scenario.standard_readiness,
        expedited_readiness=scenario.expedited_readiness,
        options=scenario.options,
        transaction_quantity=int(numbers["transaction_quantity"]) if "transaction_quantity" in numbers else None,
        selected_resource=str(numbers["selected_resource"]) if "selected_resource" in numbers else None,
        extra_answer=dict(scenario.extra_answer),
        extra_descriptions=dict(scenario.extra_descriptions),
        extra_calculations=scenario.extra_calculations,
        facts=build_facts(scenario),
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
    assay = scenario.assay
    request = scenario.primary_request
    reagent = scenario.primary_reagent
    protocol = scenario.primary_protocol
    note = scenario.current_note
    sop_id = file_ids["sop/assay-operations-sop-ao-014.md"]
    approval_id = file_ids[f"approvals/approval-{scenario.approval.approval_id}.json"]
    request_file_id = file_ids[f"lims/request-{request.request_id}.json"]
    first_lot = next(item for item in scenario.lots if item.reagent_code == reagent.code)
    selected_instrument = _selected_instrument(scenario)
    certificate_id = next(item.certificate_id for item in scenario.instruments if item.instrument_id == selected_instrument)
    first_result = next((item.result_id for item in scenario.results if item.run_id == scenario.results_run_id), None)
    runs = in_scope_runs(scenario)
    if scenario.mode == "quantity":
        request_list_args = {"reagent_code": reagent.code, "status": "open"}
        request_list_expected = {"requests": [{"request_id": t.request_id} for _, t in runs]}
        booking_args = {"start_date": scenario.numbers["in_scope_window"][0], "end_date": scenario.numbers["in_scope_window"][1], "status": "booked"}
        booking_expected = {"bookings": [{"id": b.booking_id} for b, _ in runs]}
    else:
        request_list_args = {"assay_id": assay.assay_id}
        request_list_expected = {"requests": [{"request_id": request.request_id}]}
        own = [b for b in scenario.bookings if b.assay_id == assay.assay_id]
        booking_args = {"assay_id": assay.assay_id}
        booking_expected = {"bookings": [{"id": b.booking_id} for b in own]} if own else {"total": 0}
    investigations = [
        _investigation(1, "investigation.scope", f"Established the isolated {case} scope, immutable handles, mounted systems, and evidence index before investigating {scenario.item}.", CONTEXT_TOOL, {}, {"reference_records": {"case_reference": case}}),
        _investigation(2, "investigation.scope", f"Located the task-scoped correspondence for {case} by searching the mailbox before opening any message; did not rely on a guessed sender or filename.", "messages.list", {"q": case}, {"messages": [{"id": scenario.email.message_id}]}),
        _investigation(3, "investigation.scope", f"Resolved assay code {assay.code} to the immutable LIMS assay record through an identifier search rather than a name match against a similarly named assay.", "lims.assays.search", {"identifier": assay.code}, {"assays": [{"assay_id": assay.assay_id}]}),
        _investigation(4, "investigation.scope", f"Listed the {case} case folder on the shared drive and identified the approval record and the run-request export by immutable file id.", "drive.files.list", {"q": case}, {"files": [{"id": approval_id}, {"id": request_file_id}]}),
        _investigation(5, "investigation.scope", "Listed the SOP folder and distinguished the effective AO-014 v3 SOP from the superseded 2024 edition by file identity, not title.", "drive.files.list", {"q": SOP_QUERY}, {"files": [{"id": sop_id}]}),
        _investigation(6, "investigation.requirements", f"Read the active run request {request.request_id}: sample basis, units in scope, protocol version, and run durations.", "lims.requests.get", {"request_id": request.request_id}, {"request_id": request.request_id, "status": request.status}),
        _investigation(7, "investigation.requirements", f"Read the current final sample-batch count for {assay.assay_id} ({assay.meter_metric}) and ignored the stale intake count.", "lims.batches.list", {"assay_id": assay.assay_id, "metric": assay.meter_metric}, {"batches": [{"batch_id": assay.batch_id}]}),
        _investigation(8, "investigation.requirements", "Exported the effective AO-014 v3 SOP for the sizing, minimum-dating, release, window, and authority rules; did not apply the superseded 2024 edition.", "drive.files.export", {"file_id": sop_id}, {"file_id": sop_id}),
        _investigation(9, "investigation.requirements", f"Read the reagent record for {reagent.code}: vial format, storage, minimum remaining dating, and validation status.", "inventory.reagents.get", {"reagent_code": reagent.code}, {"reagent_code": reagent.code}),
        _investigation(10, "investigation.requirements", f"Listed the run requests that define the requirement ({', '.join(sorted({t.request_id for _, t in runs}) if runs else [request.request_id])}) and excluded superseded or out-of-scope requests.", "lims.requests.list", request_list_args, request_list_expected),
        _investigation(11, "investigation.requirements", f"Read the LIMS run history ({', '.join(f'{k}={v}' for k, v in scenario.run_query.items())}) to ground what actually ran, what was invalidated or failed, and what the record says next.", "lims.runs.list", dict(scenario.run_query), dict(scenario.run_expected)),
        _investigation(12, "investigation.requirements", f"Read the current protocol version {protocol.protocol_id} ({protocol.code} {protocol.version}) for samples per plate and control vials per plate; did not apply a superseded version.", "lims.protocols.get", {"protocol_id": protocol.protocol_id}, {"protocol_id": protocol.protocol_id, "status": "current"}),
        _investigation(13, "investigation.requirements", f"Read the QC control results for run {scenario.results_run_id} with their acceptance ranges and validity flags before deciding what must be re-run or replaced.", "lims.results.list", {"run_id": scenario.results_run_id}, {"run_id": scenario.results_run_id, "results": [{"result_id": first_result}]} if first_result else {"run_id": scenario.results_run_id}),
        _investigation(14, "investigation.requirements", f"Searched the ELN for the {protocol.code} method notes and separated the current note from the superseded one by status.", "eln.notes.search", {"protocol_code": protocol.code}, {"notes": [{"note_id": note.note_id}]}),
        _investigation(15, "investigation.requirements", f"Read the current ELN method note {note.note_id} for the operative protocol version and its control rule.", "eln.notes.get", {"note_id": note.note_id}, {"note_id": note.note_id, "status": "current"}),
        _investigation(16, "investigation.constraints", f"Listed every {reagent.code} lot with vials on hand, expiry, status, and reservations before netting the coverage.", "inventory.lots.list", {"reagent_code": reagent.code}, {"lots": [{"lot_id": first_lot.lot_id}]}),
        _investigation(17, "investigation.constraints", f"Read the analyser window calendar for {scenario.windows_query['start_date']} onward to find the first free window that displaces no protected or blocked block.", "instruments.windows.list", dict(scenario.windows_query), {"windows": [{"id": scenario.selected_window_id}]}),
        _investigation(18, "investigation.constraints", f"Read the calibration certificate register for {selected_instrument} and confirmed a valid certificate covers the run date before relying on that analyser.", "instruments.certificates.list", {"instrument_id": selected_instrument}, {"certificates": [{"cert_id": certificate_id}]}),
        _investigation(19, "investigation.constraints", f"Read the supplier shipment confirmation {scenario.confirmation.confirmation_id} for the independently confirmed standard and expedited delivery dates and the expedite fee.", "supplier.confirmations.get", {"confirmation_id": scenario.confirmation.confirmation_id}, {"confirmation_id": scenario.confirmation.confirmation_id, "standard_delivery_date": scenario.confirmation.standard_date}),
        _investigation(20, "investigation.authority", f"Read approval {scenario.approval.approval_id} for its exact scope: record, quantity, supplier, fee allowance, and what it does not cover.", "approvals.get", {"approval_id": scenario.approval.approval_id}, {"approval_id": scenario.approval.approval_id}),
        _investigation(21, "investigation.authority", "Exported the approval record on the drive and confirmed it matches the workflow record before relying on it.", "drive.files.export", {"file_id": approval_id}, {"file_id": approval_id}),
        _investigation(22, "investigation.erp_correlation", f"Read the request message {scenario.email.message_id} for the documented control date and the business need in the requester's words.", "messages.get", {"message_id": scenario.email.message_id}, {"id": scenario.email.message_id}),
        _investigation(23, "investigation.erp_correlation", f"Read the team chat thread {scenario.chat.thread_id} for lot, window, and authority remarks that qualify the system records.", "chat.threads.get", {"thread_id": scenario.chat.thread_id}, {"thread_id": scenario.chat.thread_id}),
        _investigation(24, "investigation.erp_correlation", "Correlated the analyser bookings that fix the schedule scope by immutable id.", "instruments.bookings.list", booking_args, booking_expected),
    ]
    investigations.extend(
        quality_support_investigations(
            start_number=len(investigations) + 1,
            file_ids=file_ids,
            make_investigation=_investigation,
            case_reference=case,
            subject_id=scenario.item,
        )
    )
    return investigations


def build_oracle_steps(scenario: Scenario, investigations: list[dict[str, Any]], model: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [{"phase": "context", "tool": CONTEXT_TOOL, "arguments": {}, "control": True}]
    order = [2, 22, 3, 10, 6, 7, 11, 13, 12, 14, 15, 4, 5, 8, 9, 16, 24, 17, 18, 19, 20, 21, 23]
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
                "related_request_id": scenario.primary_request.request_id,
                "related_assay_id": scenario.assay.assay_id,
            },
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
            "id": "mutation_01",
            "milestone_id": "state.primary",
            "description": f"Required {scenario.item} to reach business outcome {primary.outcome_label!r} through {primary.tool} with exact provider-critical values {payload_values}. The audited change binds selected option {selected}, approval {scenario.approval.approval_id}, and constraint {scenario.labels.constraint_label}; no other record satisfies this state criterion.",
            "table": "mutations",
            "where": {"task_id": task_id, "mutation_id": f"{task_id}-mutation-01"},
            "values": {"tool": primary.tool, "table_name": primary.table, "record_id": primary.record_id, "status": primary.status},
            "payload_contains": {"tool": primary.tool, "arguments": primary.arguments},
            "payload_allowed_argument_paths": list(primary.allowed_paths),
            "weight": 3.0,
        },
        {
            "id": "state_01",
            "milestone_id": "state.primary",
            "description": f"Persisted {primary.record_id} in {primary.table} with the supported values ({', '.join(f'{k}={v!r}' for k, v in primary.domain_values.items())}) so a later reader sees the change, not just the acknowledgement.",
            "table": primary.table,
            "where": {PRIMARY_KEYS[primary.table]: primary.record_id},
            "values": dict(primary.domain_values),
            "weight": 2.0,
        },
        *[dict(item) for item in primary.extra_assertions],
        {
            "id": "mutation_02",
            "milestone_id": "state.collaboration",
            "description": f"Created — but did not send — the stakeholder draft carrying {selected}, the {completion} outcome, the binding constraint, and the {scenario.case_reference} business reference.",
            "table": "mutations",
            "where": {"task_id": task_id, "mutation_id": f"{task_id}-mutation-02"},
            "values": {"tool": "notes.drafts.create", "table_name": "note_drafts", "status": "DRAFT"},
            "payload_contains": {"tool": "notes.drafts.create", "arguments": {"recipient": scenario.collaboration["recipient"]}},
            "payload_text_contains": [selected, completion],
            "payload_text_any_of": [[scenario.case_reference, scenario.assay.code, scenario.primary_request.request_id]],
            "weight": 1.5,
        },
        {
            "id": "containment_01",
            "milestone_id": "containment.scope",
            "description": f"Made exactly two state changes for {scenario.case_reference}: the primary change and the stakeholder draft; no additional order, transfer, or booking.",
            "table": "mutations",
            "where": {"task_id": task_id},
            "count": 2,
            "weight": 1.0,
        },
    ]


def build_task(scenario: Scenario) -> dict[str, Any]:
    verify_numbers(scenario)
    assets = build_assets(scenario)
    drive_files, file_ids = mount_drive(scenario, assets)
    evidence = [
        {"asset_id": a["asset_id"], "task_id": scenario.task_id, "path": a["path"], "title": a["title"], "kind": a["kind"], "source": a["source"], "media_type": a["media_type"], "sha256": a["sha256"]}
        for a in assets
    ]
    model = build_model(scenario)
    investigations = build_investigations(scenario, file_ids)
    steps = build_oracle_steps(scenario, investigations, model)
    assertions = build_assertions(scenario, model)
    primary = scenario.primary_write
    readback = {
        "id": "verify_primary_state",
        "milestone_id": "verification.readback",
        "after_tool": primary.tool,
        "any_of": [{"tool": primary.readback_tool, "arguments": primary.readback_arguments, "match": "result_contains", "expected_result_contains": primary.readback_expected}],
        "expected_result_contains": primary.readback_expected,
        "target_identity": primary.readback_arguments,
        "materializes_new_record": primary.tool.endswith(".create"),
        "description": f"Read {primary.record_id} back through {primary.readback_tool} after the change and confirmed the persisted provider values ({', '.join(f'{k}={v!r}' for k, v in primary.readback_expected.items())}) rather than relying on the write acknowledgement.",
        "weight": 2.0,
    }
    answer = model["answer"]
    checks = answer_checks(
        answer,
        ["recommended_option", "recommended_outcome_date", ITEM_FIELD[scenario.mode], GAP_FIELD[scenario.mode], "decision_timing_status"],
        f"{scenario.item}, revision {scenario.revision}, and the selected {model['selected_option']} outcome",
    )
    descriptions = milestone_descriptions(
        case_reference=scenario.case_reference,
        record=scenario.item,
        revision=scenario.revision,
        subject=scenario.labels.subject,
        selected_option=model["selected_option"],
        selected_completion=model["selected_completion"],
        facts=model["facts"],
        primary_outcome=primary.outcome_label,
        correlated_systems=["lims", "instruments", "inventory", "supplier", "eln", "messages", "chat"],
    )
    rubric = build_rubric_milestones(
        descriptions=descriptions,
        investigations=investigations,
        calculations=model["calculations"],
        assertions=assertions,
        answer_checks=checks,
        post_write_verifications=[readback],
    )
    option_ids = [option["id"] for option in model["options"]]
    decoy_path = scenario.decoy_doc.path
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
        "expected": {
            "answer": answer,
            "answer_checks": checks,
            "calculations": model["calculations"],
            "assertions": assertions,
            "investigations": investigations,
            "post_write_verifications": [readback],
        },
        "required_investigations": investigations,
        "required_reads": [step["tool"] for step in steps if step["control"] and step["phase"] in {"context", "investigation"}],
        "required_read_calls": [item["any_of"][0] for item in investigations],
        "post_write_verifications": [readback],
        "oracle_steps": steps,
        "sequence_signature": sequence_signature(steps),
        "allowed_write_tables": sorted({primary.table, *primary.extra_tables, "note_drafts", "mutations", "answers", "audit_log"}),
        "rubric_milestones": rubric,
        "negative_controls": {
            "unauthorized_write": dict(scenario.unauthorized_write),
            "wrong_evidence": {"tool": "drive.files.export", "arguments": {"file_id": file_ids[decoy_path]}},
        },
        "reference_records": {
            "case_reference": scenario.case_reference,
            "lims": {
                "assay_code": scenario.assay.code,
                "assay_search": {"tool": "lims.assays.search", "arguments": {"identifier": scenario.assay.code}},
                "protocol_id": scenario.primary_protocol.protocol_id,
                "results_run_id": scenario.results_run_id,
            },
            "messages": {"search_query": scenario.case_reference},
            "drive": {"case_folder_query": scenario.case_reference, "sop_query": SOP_QUERY},
            "inventory": {"reagent_code": scenario.primary_reagent.code, "sites": sorted({item.site_id for item in scenario.lots})},
            "instruments": {"site_id": "SITE-MAIN", "calendar_window": scenario.windows_query},
            "supplier": {"confirmation_id": scenario.confirmation.confirmation_id},
            "eln": {"protocol_code": scenario.primary_protocol.code},
            "approvals": {"approval_id": scenario.approval.approval_id},
            "chat": {"thread_id": scenario.chat.thread_id},
        },
        "starting_records": [
            *[{"system": "instruments", "resource_type": "Booking", "resource_id": b.booking_id, "status": b.status} for b in scenario.bookings],
            {"system": "supplier", "resource_type": "ReagentOrder", "resource_id": "ORD-3400", "status": "RECEIVED"},
            *[{"system": "inventory", "resource_type": "LotTransfer", "resource_id": row["transfer_id"], "status": row["status"]} for row in scenario.seed.get("transfers", ())],
        ],
        "evaluation": {"metric": "HubScore", "strict_pass": "every rubric milestone passes", "llm_judge_calls": 0},
        "workflow": {
            "reads": len([s for s in steps if s["phase"] in {"context", "investigation"}]),
            "writes": 2,
            "readbacks": 1,
            "answer_fields": len(answer),
        },
    }


def build_tasks() -> list[dict[str, Any]]:
    return [build_task(scenario) for scenario in scenarios()]


__all__ = [
    "BENCHMARK",
    "FAMILY_SLUG",
    "FAMILY_VERSION",
    "build_task",
    "build_tasks",
    "calendar",
    "first_window_on_or_after",
    "request_vials",
    "verify_numbers",
]
