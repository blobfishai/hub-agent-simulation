"""Assemble ClinicOps tasks: seed tables, scattered evidence, decision model, sealed contract.

Every declared number in a scenario is recomputed from the seeded world (lots,
calendar, orders, confirmations) and the build fails on any disagreement, so
the answer contract can never drift from the data the agent actually sees.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from ...engine.assets import (
    CSV,
    EML,
    JSON,
    MARKDOWN,
    PDF,
    XLSX,
    YAML,
    asset,
    eml,
    yaml_lines,
)
from ...engine.catalog import (
    answer_checks,
    build_rubric_milestones,
    milestone_descriptions,
    sequence_signature,
)
from ...engine.decision import (
    UNAUTHORIZED,
    DecisionInputs,
    answer_schema,
    build_decision_model,
)
from ...engine.families import CONTEXT_TOOL, SUBMIT_TOOL
from ...engine.grading_contracts import fact_text_contract
from ...engine.quality_assets import (
    quality_support_assets,
    quality_support_investigations,
    scoped_csv,
    scoped_markdown,
)
from . import tools as clinic_tools
from .policy import SUPERSEDED_POLICY, effective_policy
from .scenarios import scenarios
from .specs import (
    AS_OF,
    LOCATIONS,
    ORGANIZATION,
    PRACTITIONERS,
    SESSION_HOURS,
    SESSION_TIMES,
    SUPPLIERS,
    USERS,
    Lot,
    Order,
    Patient,
    Scenario,
    clinic_days,
    next_clinic_day,
    slot_id,
    vials_for_dose,
)

BENCHMARK = "HubBench"
FAMILY_SLUG = "clinicops"
FAMILY_VERSION = "1.0.1"
WEIGHT_CODE = "29463-7"
HEIGHT_CODE = "8302-2"
PRIMARY_KEYS = {
    "appointments": "appointment_id",
    "purchase_orders": "po_id",
    "stock_transfers": "transfer_id",
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
CASE_FOLDER = "Infusion Services/Cases/{case}"
OPEN_SOURCE_ANCHORS = (
    {
        "name": "MedAgentBench",
        "harbor_dataset": "stanford/medagentbench",
        "harbor_url": "https://hub.harborframework.com/datasets/stanford/medagentbench/latest",
        "upstream_url": "https://github.com/stanfordmlgroup/MedAgentBench",
        "license": "MIT",
        "evaluation_shape": "stateful FHIR-backed EHR retrieval and action tasks",
    },
    {
        "name": "PhysicianBench",
        "harbor_dataset": "josancamon19/physician-bench",
        "harbor_url": "https://hub.harborframework.com/datasets/josancamon19/physician-bench/latest",
        "upstream_url": "https://github.com/HealthRex/PhysicianBench",
        "license": "Apache-2.0",
        "evaluation_shape": "long-horizon clinical workflows with checkpointed FHIR interactions",
    },
)


# --------------------------------------------------------------------------- #
# Derivations and cross-checks
# --------------------------------------------------------------------------- #


def dose_amount(order: Order, patient: Patient) -> float:
    if order.dose_unit in {"mg/kg", "g/kg"}:
        return order.dose_value * patient.weight_kg
    return order.dose_value


def _short_dated(lot: Lot, scenario: Scenario) -> bool:
    horizon = date.fromisoformat(AS_OF) + timedelta(
        days=scenario.primary_medication.min_dating_days
    )
    return date.fromisoformat(lot.expiry) <= horizon


def _lot_excluded(lot: Lot, scenario: Scenario) -> bool:
    return (
        lot.status != "AVAILABLE"
        or lot.reserved_for is not None
        or lot.register_excluded
        or _short_dated(lot, scenario)
    )


def calendar(scenario: Scenario) -> dict[tuple[str, str, str], dict[str, Any]]:
    overrides = {
        (item.day, item.chair, item.session): item for item in scenario.sessions
    }
    grid: dict[tuple[str, str, str], dict[str, Any]] = {}
    for day in clinic_days():
        for chair in scenario.chairs:
            for session in ("AM", "PM"):
                key = (day, chair.chair_id, session)
                override = overrides.get(key)
                if override is None:
                    entry = {
                        "status": "busy",
                        "hold_reason": "booked",
                        "appointment_id": None,
                    }
                elif override.status == "busy" and override.reason.startswith("APPT-"):
                    entry = {
                        "status": "busy",
                        "hold_reason": "booked",
                        "appointment_id": override.reason,
                    }
                elif override.status == "free":
                    entry = {
                        "status": "free",
                        "hold_reason": None,
                        "appointment_id": None,
                    }
                else:
                    entry = {
                        "status": override.status,
                        "hold_reason": override.reason or override.status,
                        "appointment_id": None,
                    }
                grid[key] = entry
    return grid


def first_session_on_or_after(
    scenario: Scenario, start: str, sessions_needed: int, chairs: list[str]
) -> tuple[str, str, str] | None:
    grid = calendar(scenario)
    active = {chair.chair_id for chair in scenario.chairs if chair.status == "ACTIVE"}
    for day in clinic_days():
        if day < start:
            continue
        for chair in chairs:
            if chair not in active:
                continue
            free = [
                session
                for session in ("AM", "PM")
                if grid[(day, chair, session)]["status"] == "free"
            ]
            if sessions_needed == 1 and free:
                return day, chair, free[0]
            if sessions_needed == 2 and len(free) == 2:
                return day, chair, "AM+PM"
    return None


def in_scope_administrations(scenario: Scenario) -> list[tuple[Any, Order, Patient]]:
    window = scenario.numbers.get("in_scope_window")
    if not window:
        return []
    orders = {order.request_id: order for order in scenario.orders}
    patients = {
        patient.patient_id: patient
        for patient in (scenario.patient, *scenario.other_patients)
    }
    code = scenario.primary_medication.code
    selected = []
    for appointment in scenario.appointments:
        if appointment.status != "booked" or appointment.start is None:
            continue
        order = orders.get(appointment.request_id or "")
        if order is None or order.medication_code != code:
            continue
        if window[0] <= appointment.start[:10] <= window[1]:
            selected.append((appointment, order, patients[appointment.patient_id]))
    return sorted(selected, key=lambda item: item[0].start)


def verify_numbers(scenario: Scenario) -> None:
    numbers = scenario.numbers
    medication = scenario.primary_medication
    problems: list[str] = []

    def check(label: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            problems.append(
                f"{label}: computed {actual!r} but scenario declares {expected!r}"
            )

    scoped_lots = [
        lot
        for lot in scenario.lots
        if lot.medication_code == medication.code
        and lot.location_id == numbers["coverage_location"]
    ]
    if scenario.mode in {"plan", "quantity"}:
        observed = sum(lot.quantity for lot in scoped_lots)
        excluded = sum(
            lot.quantity for lot in scoped_lots if _lot_excluded(lot, scenario)
        )
        check("observed", observed, numbers["observed"])
        check("excluded", excluded, numbers["excluded"])
        check("eligible", observed - excluded, numbers["eligible"])
    if scenario.mode == "plan":
        order = scenario.primary_order
        amount = dose_amount(order, scenario.patient)
        per_dose = vials_for_dose(amount, medication.vial_strength)
        check(
            "required_dose_amount",
            int(amount) if float(amount).is_integer() else amount,
            scenario.extra_answer["required_dose_amount"],
        )
        check("vials_per_dose", per_dose, scenario.extra_answer["vials_per_dose"])
        check(
            "doses_in_scope",
            order.doses_in_scope,
            scenario.extra_answer["doses_in_scope"],
        )
        check("scope", per_dose * order.doses_in_scope, numbers["scope"])
    if scenario.mode == "quantity":
        administrations = in_scope_administrations(scenario)
        check(
            "scheduled_administrations",
            len(administrations),
            scenario.extra_answer["scheduled_administrations"],
        )
        scope = sum(
            vials_for_dose(dose_amount(order, patient), medication.vial_strength)
            for _, order, patient in administrations
        )
        check("scope", scope, numbers["scope"])
        first = administrations[0][0] if administrations else None
        if first is not None:
            session = "AM" if first.start[11:] < SESSION_TIMES["PM"][0] else "PM"
            check(
                "first_administration_slot",
                f"{first.chair_id}/{first.start[:10]}/{session}",
                scenario.extra_answer["first_administration_slot"],
            )
            check("business_need", first.start[:10], scenario.business_need)
        if "safety_stock" in numbers:
            check(
                "transaction_quantity",
                numbers["gap"] + numbers["safety_stock"],
                numbers["transaction_quantity"],
            )
            check(
                "safety_stock_quantity",
                numbers["safety_stock"],
                scenario.extra_answer["safety_stock_quantity"],
            )
        if "receiving_usable" in numbers:
            receiving = [
                lot
                for lot in scenario.lots
                if lot.medication_code == medication.code
                and lot.location_id == "LOC-PHARM"
                and not _lot_excluded(lot, scenario)
            ]
            check(
                "receiving_usable",
                sum(lot.quantity for lot in receiving),
                numbers["receiving_usable"],
            )
            check(
                "transaction_quantity",
                min(
                    numbers["scope"] - numbers["receiving_usable"], numbers["eligible"]
                ),
                numbers["transaction_quantity"],
            )
    if scenario.mode == "schedule":
        grid = calendar(scenario)
        start, end = numbers["capacity_window"]
        days = [day for day in clinic_days() if start <= day <= end]
        keys = [
            (day, chair, session)
            for day in days
            for chair in numbers["eligible_chairs"]
            for session in ("AM", "PM")
        ]
        candidate = len(keys) * SESSION_HOURS
        free = sum(1 for key in keys if grid[key]["status"] == "free")
        check("candidate", candidate, numbers["observed"])
        check("excluded", candidate - free * SESSION_HOURS, numbers["excluded"])
        check("eligible", free * SESSION_HOURS, numbers["eligible"])
        affected = [
            order
            for order in scenario.orders
            if order.medication_code == medication.code
        ]
        if scenario.ordinal == 3:
            hours = (
                scenario.primary_order.infusion_minutes
                + scenario.primary_order.observation_minutes
            ) / 60
        else:
            hours = sum(
                (order.infusion_minutes + order.observation_minutes) / 60
                for order in affected
            )
        check("scope", int(hours), numbers["scope"])
        usable = sum(
            lot.quantity for lot in scoped_lots if not _lot_excluded(lot, scenario)
        )
        check("drug_vials_usable", usable, scenario.extra_answer["drug_vials_usable"])
    gap = max(0, numbers["scope"] - numbers["eligible"])
    check("gap", gap, numbers["gap"])
    check(
        "standard_readiness",
        next_clinic_day(scenario.confirmation.standard_date),
        scenario.standard_readiness,
    )
    check(
        "expedited_readiness",
        next_clinic_day(scenario.confirmation.expedited_date),
        scenario.expedited_readiness,
    )
    sessions_needed = int(numbers.get("sessions_needed", 1))
    slot_chairs = numbers["eligible_chairs"]
    standard_slot = first_session_on_or_after(
        scenario,
        scenario.standard_readiness,
        2
        if scenario.mode == "schedule"
        and sessions_needed == 2
        and scenario.ordinal == 3
        else 1,
        slot_chairs,
    )
    expedited_slot = first_session_on_or_after(
        scenario,
        scenario.expedited_readiness,
        2
        if scenario.mode == "schedule"
        and sessions_needed == 2
        and scenario.ordinal == 3
        else 1,
        slot_chairs,
    )
    check(
        "standard_slot_date",
        standard_slot[0] if standard_slot else None,
        numbers["standard_slot_date"],
    )
    check(
        "expedited_slot_date",
        expedited_slot[0] if expedited_slot else None,
        numbers["expedited_slot_date"],
    )
    if scenario.mode == "plan":
        check(
            "earliest_qualified_base_slot",
            standard_slot[0] if standard_slot else None,
            scenario.extra_answer["earliest_qualified_base_slot"],
        )
        expedited_option = scenario.options[1]
        check(
            "expedited option date",
            expedited_slot[0] if expedited_slot else None,
            expedited_option.completion,
        )
        check(
            "expedite_completion_days_saved",
            (
                date.fromisoformat(numbers["standard_slot_date"])
                - date.fromisoformat(numbers["expedited_slot_date"])
            ).days,
            scenario.extra_answer["expedite_completion_days_saved"],
        )
        selected = next(option for option in scenario.options if option.recommended)
        selected_date = selected.completion
        slot = (
            first_session_on_or_after(
                scenario,
                scenario.standard_readiness
                if selected.id == "standard_delivery_plan"
                else scenario.expedited_readiness,
                1,
                slot_chairs,
            )
            if selected.id in {"standard_delivery_plan", "expedite_supplier_shipment"}
            else None
        )
        if slot is not None:
            check(
                "selected_chair_session",
                f"{slot[1]}/{slot[0]}/{slot[2]}",
                scenario.extra_answer["selected_chair_session"],
            )
            check("selected completion", slot[0], selected_date)
    if scenario.mode == "schedule":
        selected_date = next(
            option for option in scenario.options if option.recommended
        ).completion
        if scenario.ordinal == 3:
            full_day = first_session_on_or_after(
                scenario, numbers["capacity_window"][0], 2, numbers["eligible_chairs"]
            )
            check(
                "selected_resource",
                f"{full_day[1]}/{full_day[0]}/{full_day[2]}" if full_day else None,
                numbers["selected_resource"],
            )
            check(
                "selected completion", full_day[0] if full_day else None, selected_date
            )
        else:
            grid = calendar(scenario)
            free_sessions = [
                key
                for key in sorted(grid)
                if key[1] in numbers["eligible_chairs"]
                and grid[key]["status"] == "free"
                and key[0] >= numbers["capacity_window"][0]
            ]
            check(
                "selected_resource",
                f"{free_sessions[0][1]}/{free_sessions[0][0]}/{free_sessions[0][2]}"
                if free_sessions
                else None,
                numbers["selected_resource"],
            )
            check(
                "selected completion",
                free_sessions[sessions_needed - 1][0]
                if len(free_sessions) >= sessions_needed
                else None,
                selected_date,
            )
    if scenario.selected_slot_id not in {
        slot_id(chair, day, session) for (day, chair, session) in calendar(scenario)
    }:
        problems.append(
            f"selected slot {scenario.selected_slot_id} is not on the calendar"
        )
    if problems:
        raise ValueError(
            f"{scenario.task_id} scenario data disagrees with its declared numbers:\n  "
            + "\n  ".join(problems)
        )


# --------------------------------------------------------------------------- #
# Seed tables
# --------------------------------------------------------------------------- #


def _observations(patient: Patient, *, stale: bool) -> list[dict[str, Any]]:
    rows = [
        {
            "observation_id": patient.weight_observation_id,
            "patient_id": patient.patient_id,
            "code": WEIGHT_CODE,
            "display": "Body weight",
            "value": patient.weight_kg,
            "unit": "kg",
            "effective_date": patient.weight_date,
            "status": "final",
        },
        {
            "observation_id": patient.height_observation_id,
            "patient_id": patient.patient_id,
            "code": HEIGHT_CODE,
            "display": "Body height",
            "value": patient.height_cm,
            "unit": "cm",
            "effective_date": patient.weight_date,
            "status": "final",
        },
    ]
    if stale:
        rows.append(
            {
                "observation_id": f"{patient.weight_observation_id}-2025",
                "patient_id": patient.patient_id,
                "code": WEIGHT_CODE,
                "display": "Body weight",
                "value": patient.weight_kg - 5.0,
                "unit": "kg",
                "effective_date": "2025-09-12",
                "status": "final",
            }
        )
    return rows


def seed_tables(
    scenario: Scenario,
    drive_files: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    patients = [scenario.patient, *scenario.other_patients]
    grid = calendar(scenario)
    slots = [
        {
            "slot_id": slot_id(chair, day, session),
            "chair_id": chair,
            "service_date": day,
            "session": session,
            "start_time": SESSION_TIMES[session][0],
            "end_time": SESSION_TIMES[session][1],
            **entry,
        }
        for (day, chair, session), entry in sorted(grid.items())
    ]
    return {
        "users": [dict(row) for row in USERS],
        "locations": [dict(row) for row in LOCATIONS],
        "practitioners": [dict(row) for row in PRACTITIONERS],
        "patients": [
            {
                "patient_id": p.patient_id,
                "mrn": p.mrn,
                "family_name": p.family,
                "given_name": p.given,
                "birth_date": p.birth_date,
                "sex": p.sex,
                "primary_practitioner_id": p.practitioner_id,
            }
            for p in patients
        ],
        "observations": [
            row
            for index, p in enumerate(patients)
            for row in _observations(p, stale=index == 0)
        ],
        "medications": [
            {
                "medication_code": m.code,
                "display": m.display,
                "vial_strength_value": m.vial_strength,
                "vial_strength_unit": m.vial_unit,
                "route": m.route,
                "storage": m.storage,
                "minimum_dating_days": m.min_dating_days,
                "interchangeable_with": m.interchangeable_with,
            }
            for m in scenario.medications
        ],
        "medication_requests": [
            {
                "request_id": o.request_id,
                "patient_id": o.patient_id,
                "medication_code": o.medication_code,
                "dose_value": o.dose_value,
                "dose_unit": o.dose_unit,
                "regimen": o.regimen,
                "doses_in_scope": o.doses_in_scope,
                "infusion_minutes": o.infusion_minutes,
                "observation_minutes": o.observation_minutes,
                "status": o.status,
                "intent": o.intent,
                "priority": o.priority,
                "authored_on": o.authored_on,
                "requester_id": o.requester_id,
                "note": o.note or None,
            }
            for o in scenario.orders
        ],
        "inventory_lots": [
            {
                "lot_id": lot.lot_id,
                "medication_code": lot.medication_code,
                "lot_number": lot.lot_number,
                "location_id": lot.location_id,
                "quantity_on_hand": lot.quantity,
                "expiry_date": lot.expiry,
                "status": lot.status,
                "status_reason": lot.reason,
                "reserved_for_patient_id": lot.reserved_for,
            }
            for lot in scenario.lots
        ],
        "chairs": [
            {
                "chair_id": c.chair_id,
                "location_id": "LOC-INF",
                "name": c.name,
                "status": c.status,
                "first_dose_capable": int(c.first_dose_capable),
                "status_note": c.note,
            }
            for c in scenario.chairs
        ],
        "slots": slots,
        "appointments": [
            {
                "appointment_id": a.appointment_id,
                "patient_id": a.patient_id,
                "request_id": a.request_id,
                "chair_id": a.chair_id,
                "start_time": a.start,
                "end_time": a.end,
                "status": a.status,
                "description": a.description,
                "revision": 1,
                "last_updated": "2026-03-06T12:00:00",
            }
            for a in scenario.appointments
        ],
        "suppliers": [dict(row) for row in SUPPLIERS],
        "supplier_confirmations": [
            {
                "confirmation_id": c.confirmation_id,
                "supplier_id": c.supplier_id,
                "medication_code": c.medication_code,
                "reference": c.reference,
                "quantity_available": c.quantity_available,
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
        "purchase_orders": [
            {
                "po_id": "PO-5100",
                "supplier_id": "SUP-MERIDIAN",
                "confirmation_id": None,
                "medication_code": scenario.medications[-1].code,
                "quantity": 2,
                "unit": "VIAL",
                "delivery_option": "standard",
                "expected_delivery_date": "2026-02-26",
                "status": "RECEIVED",
                "requested_by": "infusion_pharmacy_buyer",
                "created_at": "2026-02-19T09:30:00",
                "revision": 1,
            },
        ],
        "stock_transfers": [dict(row) for row in scenario.seed.get("transfers", ())],
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
                "approval_id": "AP-CO-0090",
                "subject": "Quarterly saline and tubing standing order",
                "approver_id": "U-RAMAN",
                "approver_role": "pharmacy_manager",
                "status": "APPROVED",
                "granted_on": "2026-01-08",
                "scope_json": json.dumps(
                    {"medication_code": "CONSUMABLES", "max_spend_usd": 12000},
                    sort_keys=True,
                ),
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
                "attachments_json": json.dumps(
                    [
                        {"name": name, "mime_type": "application/pdf"}
                        for name in scenario.email.attachments
                    ]
                ),
                "labels": f"{scenario.email.labels},{scenario.case_reference}",
            },
            {
                "message_id": f"MSG-{scenario.ordinal:04d}-00",
                "thread_id": f"THR-{scenario.ordinal:04d}-STAFF",
                "channel": "email",
                "sender": "dana.whitfield@northlake.example",
                "recipients": "infusion-ops@northlake.example",
                "subject": "Weekly staffing note",
                "sent_at": "2026-03-06T08:00:00",
                "body": "Roster for the week of 2026-03-09 is posted. Chair capability flags are on the shared drive roster; no changes to protected blocks.",
                "attachments_json": "[]",
                "labels": "staffing",
            },
        ],
        "chat_threads": [
            {
                "thread_id": scenario.chat.thread_id,
                "channel": scenario.chat.channel,
                "title": scenario.chat.title,
                "messages_json": json.dumps(
                    [
                        {"author": author, "ts": ts, "text": text}
                        for author, ts, text in scenario.chat.messages
                    ]
                ),
            },
            {
                "thread_id": f"CHAT-{scenario.ordinal:04d}-GEN",
                "channel": "#infusion-ops",
                "title": "General — pump swaps and parking",
                "messages_json": json.dumps(
                    [
                        {
                            "author": "Dana Whitfield",
                            "ts": "2026-03-05T16:40:00",
                            "text": "Reminder: log every pump swap in biomed's sheet.",
                        }
                    ]
                ),
            },
        ],
        "drive_files": drive_files,
        "evidence_files": evidence,
    }


# --------------------------------------------------------------------------- #
# Evidence room
# --------------------------------------------------------------------------- #


def _fhir_order_json(scenario: Scenario, order: Order) -> str:
    medication = next(
        m for m in scenario.medications if m.code == order.medication_code
    )
    row = {
        "request_id": order.request_id,
        "patient_id": order.patient_id,
        "medication_code": order.medication_code,
        "dose_value": order.dose_value,
        "dose_unit": order.dose_unit,
        "regimen": order.regimen,
        "doses_in_scope": order.doses_in_scope,
        "infusion_minutes": order.infusion_minutes,
        "observation_minutes": order.observation_minutes,
        "status": order.status,
        "intent": order.intent,
        "priority": order.priority,
        "authored_on": order.authored_on,
        "requester_id": order.requester_id,
        "note": order.note,
    }
    resource = clinic_tools._medication_request(
        row, {"display": medication.display, "route": medication.route}
    )
    return (
        json.dumps(
            {
                "resourceType": "Bundle",
                "type": "collection",
                "entry": [{"resource": resource}],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _patient_summary_json(scenario: Scenario) -> str:
    patient = scenario.patient
    resources = [
        clinic_tools._patient(
            {
                "patient_id": patient.patient_id,
                "mrn": patient.mrn,
                "family_name": patient.family,
                "given_name": patient.given,
                "birth_date": patient.birth_date,
                "sex": patient.sex,
                "primary_practitioner_id": patient.practitioner_id,
            }
        )
    ]
    resources.extend(
        clinic_tools._observation(row) for row in _observations(patient, stale=True)
    )
    return (
        json.dumps(
            {
                "resourceType": "Bundle",
                "type": "collection",
                "entry": [{"resource": resource} for resource in resources],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _confirmation_text(scenario: Scenario) -> str:
    c = scenario.confirmation
    supplier = next(
        row["name"] for row in SUPPLIERS if row["supplier_id"] == c.supplier_id
    )
    return (
        f"{supplier}\nDelivery confirmation {c.reference} (system reference {c.confirmation_id})\nCustomer: Northlake Health Infusion Services, account {next(row['account_number'] for row in SUPPLIERS if row['supplier_id'] == c.supplier_id)}\n"
        f"Case reference: {scenario.case_reference}\nItem: {c.medication_code} — {scenario.primary_medication.display}\nQuantity available for this confirmation: {c.quantity_available} vials\nUnit price: USD {c.unit_price:.2f}\n"
        f"Standard delivery date: {c.standard_date}\nExpedited delivery date: {c.expedited_date} (expedite fee USD {c.fee}, flat)\nValid until: {c.valid_until}\nNotes: {c.note}\n"
        "Delivery is to the receiving dock; shelf release is subject to the customer's pharmacy verification.\n"
    )


def _decoy_asset(scenario: Scenario) -> dict[str, Any]:
    doc = scenario.decoy_doc
    if doc.kind == "policy_superseded":
        return asset(
            doc.path,
            kind=doc.kind,
            title=doc.title,
            source="drive",
            media_type=MARKDOWN,
            content=scoped_markdown(
                SUPERSEDED_POLICY,
                task_id=scenario.task_id,
                case_reference=scenario.case_reference,
            ),
            preview="2024 policy retained for audit only; superseded by v3.",
        )
    if doc.kind == "decoy_order":
        request_id = (
            doc.path.rsplit("/", 1)[-1]
            .removeprefix("medication-request-")
            .removesuffix(".json")
        )
        order = next(o for o in scenario.orders if o.request_id == request_id)
        return asset(
            doc.path,
            kind=doc.kind,
            title=doc.title,
            source="ehr_export",
            media_type=JSON,
            content=_fhir_order_json(scenario, order),
            preview="A similarly named or superseded order that must not drive the requirement.",
        )
    if doc.media_type == XLSX:
        return asset(
            doc.path,
            kind=doc.kind,
            title=doc.title,
            source="drive",
            media_type=XLSX,
            rows=[list(row) for row in doc.rows or ()],
            preview=doc.title,
        )
    return asset(
        doc.path,
        kind=doc.kind,
        title=doc.title,
        source="drive",
        media_type=doc.media_type,
        content=doc.content,
        preview=doc.title,
    )


def build_assets(scenario: Scenario) -> list[dict[str, Any]]:
    case = scenario.case_reference
    grid = calendar(scenario)
    assets: list[dict[str, Any]] = [
        asset(
            "policy/infusion-operations-policy.md",
            kind="policy",
            title="Infusion operations policy v3 (effective)",
            source="drive",
            media_type=MARKDOWN,
            content=scoped_markdown(
                effective_policy(AS_OF), task_id=scenario.task_id, case_reference=case
            ),
            preview="Dose rounding, dispensable-stock, chair, and authority rules in force.",
        ),
    ]
    if scenario.decoy_doc.kind != "policy_superseded":
        assets.append(
            asset(
                "policy/superseded-infusion-policy-2024.md",
                kind="policy_superseded",
                title="Infusion operations policy 2024 (superseded)",
                source="drive",
                media_type=MARKDOWN,
                content=scoped_markdown(
                    SUPERSEDED_POLICY, task_id=scenario.task_id, case_reference=case
                ),
                preview="2024 policy retained for audit only; superseded by v3.",
            )
        )
    assets.append(_decoy_asset(scenario))
    assets.extend(
        [
            asset(
                f"ehr/medication-request-{scenario.primary_order.request_id}.json",
                kind="medication_order",
                title=f"MedicationRequest {scenario.primary_order.request_id} (FHIR export)",
                source="ehr_export",
                media_type=JSON,
                content=_fhir_order_json(scenario, scenario.primary_order),
                preview="The active order: dose basis, regimen, infusion and observation minutes.",
            ),
            asset(
                f"ehr/patient-{scenario.patient.mrn}-summary.json",
                kind="patient_summary",
                title=f"Patient {scenario.patient.mrn} summary with weight observations (FHIR export)",
                source="ehr_export",
                media_type=JSON,
                content=_patient_summary_json(scenario),
                preview="Patient identity plus current and historical weight observations.",
            ),
            asset(
                "pharmacy/formulary-vial-strengths.csv",
                kind="formulary",
                title="Formulary vial strengths and minimum dating",
                source="pharmacy_export",
                media_type=CSV,
                content="medication_code,display,vial_strength_value,vial_strength_unit,storage,minimum_dating_days,interchangeable_with\n"
                + "".join(
                    f"{m.code},{m.display},{m.vial_strength:g},{m.vial_unit},{m.storage},{m.min_dating_days},{m.interchangeable_with or ''}\n"
                    for m in scenario.medications
                ),
                preview="Vial strengths used for rounding and the 14-day minimum dating.",
            ),
            asset(
                "pharmacy/on-hand-by-lot.xlsx",
                kind="on_hand_workbook",
                title="On-hand inventory by lot (gross)",
                source="pharmacy_workbook",
                media_type=XLSX,
                rows=[
                    [
                        "lot_number",
                        "medication_code",
                        "location_id",
                        "quantity_on_hand",
                        "expiry_date",
                    ],
                    *[
                        [
                            lot.lot_number,
                            lot.medication_code,
                            lot.location_id,
                            lot.quantity,
                            lot.expiry,
                        ]
                        for lot in scenario.lots
                    ],
                ],
                preview="Gross quantities by lot; status and reservations live in the lot register.",
            ),
            asset(
                "pharmacy/lot-status-register.csv",
                kind="quarantine_register",
                title="Lot status register (quarantine, reservation, excursion notes)",
                source="pharmacy_export",
                media_type=CSV,
                content="lot_number,medication_code,location_id,status,status_reason,reserved_for_patient_id,register_note\n"
                + "".join(
                    f"{lot.lot_number},{lot.medication_code},{lot.location_id},{lot.status},{lot.reason or ''},{lot.reserved_for or ''},{lot.register_note}\n"
                    for lot in scenario.lots
                ),
                preview="Which lots are quarantined, reserved, or flagged.",
            ),
            asset(
                "scheduling/chair-calendar-2026-03-09.xlsx",
                kind="chair_calendar",
                title="Chair calendar, three weeks from 2026-03-09",
                source="scheduling_workbook",
                media_type=XLSX,
                rows=[
                    [
                        "service_date",
                        "chair_id",
                        "session",
                        "start",
                        "end",
                        "status",
                        "hold_reason",
                    ],
                    *[
                        [
                            day,
                            chair,
                            session,
                            SESSION_TIMES[session][0],
                            SESSION_TIMES[session][1],
                            entry["status"],
                            entry["hold_reason"] or "",
                        ]
                        for (day, chair, session), entry in sorted(grid.items())
                    ],
                ],
                preview="Every chair session with free / busy / protected / blocked status.",
            ),
            asset(
                "scheduling/chair-roster-and-capabilities.csv",
                kind="chair_roster",
                title="Chair roster and first-dose capability",
                source="scheduling_export",
                media_type=CSV,
                content=scoped_csv(
                    "chair_id,name,status,first_dose_capable,note\n"
                    + "".join(
                        f"{c.chair_id},{c.name},{c.status},{'yes' if c.first_dose_capable else 'no'},{c.note or ''}\n"
                        for c in scenario.chairs
                    ),
                    task_id=scenario.task_id,
                    case_reference=case,
                ),
                preview="Chair status and nurse capability flags for the week.",
            ),
            asset(
                f"supplier/delivery-confirmation-{scenario.confirmation.reference}.pdf",
                kind="supplier_confirmation",
                title=f"Supplier delivery confirmation {scenario.confirmation.reference}",
                source="email_attachment",
                media_type=PDF,
                content=_confirmation_text(scenario),
                preview="Standard and expedited delivery dates, fee, and validity.",
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
                    message_id=f"{scenario.email.message_id}@northlake.example",
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
                    {
                        "thread_id": scenario.chat.thread_id,
                        "channel": scenario.chat.channel,
                        "title": scenario.chat.title,
                        "messages": [
                            {"author": a, "ts": t, "text": x}
                            for a, t, x in scenario.chat.messages
                        ],
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                preview="Team chat with lot, chair, and authority remarks.",
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
                title="Starting-state export (appointments, orders, transfers)",
                source="scheduling_export",
                media_type=JSON,
                content=json.dumps(
                    {
                        "case_reference": case,
                        "as_of": AS_OF,
                        "appointments": [
                            {
                                "appointment_id": a.appointment_id,
                                "patient_id": a.patient_id,
                                "request_id": a.request_id,
                                "chair_id": a.chair_id,
                                "start": a.start,
                                "end": a.end,
                                "status": a.status,
                            }
                            for a in scenario.appointments
                        ],
                        "purchase_orders": [{"po_id": "PO-5100", "status": "RECEIVED"}],
                        "stock_transfers": [
                            dict(row) for row in scenario.seed.get("transfers", ())
                        ],
                        "note": "Snapshot before any action; row order does not indicate applicability.",
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                preview="Snapshot of scheduling and procurement state before any action.",
            ),
        ]
    )
    for doc in scenario.docs:
        if doc.media_type == XLSX:
            assets.append(
                asset(
                    doc.path,
                    kind=doc.kind,
                    title=doc.title,
                    source="drive",
                    media_type=XLSX,
                    rows=[list(row) for row in doc.rows or ()],
                    preview=doc.title,
                )
            )
        else:
            assets.append(
                asset(
                    doc.path,
                    kind=doc.kind,
                    title=doc.title,
                    source="drive",
                    media_type=doc.media_type,
                    content=doc.content,
                    preview=doc.title,
                )
            )
    assets.extend(
        quality_support_assets(
            task_id=scenario.task_id,
            ordinal=scenario.ordinal,
            case_reference=case,
            family_slug=FAMILY_SLUG,
            family_name="ClinicOps",
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
        "files": [
            {
                "path": a["path"],
                "kind": a["kind"],
                "media_type": a["media_type"],
                "sha256": a["sha256"],
            }
            for a in assets
        ],
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
    return assets


def _folder(scenario: Scenario, record: dict[str, Any]) -> str:
    if record["kind"] == "policy":
        return "Infusion Services/Policies"
    if record["kind"] == "policy_superseded":
        return "Infusion Services/Policies/Archive"
    return CASE_FOLDER.format(case=scenario.case_reference)


def mount_drive(
    scenario: Scenario, assets: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, str]]:
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
                "modified_time": "2026-03-06T17:30:00",
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
    unauthorized = next(
        option for option in scenario.options if option.approval == UNAUTHORIZED
    )
    accelerated = scenario.options[1]
    return (
        {
            "id": "authoritative_identity",
            "sources": ["ehr", "messages"],
            "statement": f"{scenario.case_reference}: {notes['identity']}; the effective revision is {scenario.revision}.",
            "rubric": f"Located {scenario.item} using immutable identifiers and preserved effective revision {scenario.revision}: {notes['identity']}.",
        },
        {
            "id": "effective_requirement",
            "sources": ["ehr", "drive"],
            "statement": f"The effective order and policy establish {labels.scope_label} = {numbers['scope']} {labels.unit}: {notes['requirement']}. The control date is {scenario.business_need} ({scenario.business_need_reason}).",
            "rubric": f"Applied the effective order and policy to establish {numbers['scope']} {labels.unit} for {labels.scope_label}, with control date {scenario.business_need}.",
        },
        {
            "id": "eligible_coverage",
            "sources": ["pharmacy", "scheduling", "drive"],
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
            "sources": ["scheduling", "drive"],
            "statement": f"{labels.capacity_label}: {notes['capacity']}; protected and blocked sessions cannot be displaced.",
            "rubric": f"Applied {labels.capacity_label} to derive the three option outcomes without using protected or blocked sessions.",
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
        transaction_quantity=int(numbers["transaction_quantity"])
        if "transaction_quantity" in numbers
        else None,
        selected_resource=str(numbers["selected_resource"])
        if "selected_resource" in numbers
        else None,
        extra_answer=dict(scenario.extra_answer),
        extra_descriptions=dict(scenario.extra_descriptions),
        extra_calculations=scenario.extra_calculations,
        facts=build_facts(scenario),
    )
    return build_decision_model(inputs)


# --------------------------------------------------------------------------- #
# Investigations, oracle steps, contract
# --------------------------------------------------------------------------- #


def _investigation(
    number: int,
    milestone: str,
    description: str,
    tool: str,
    arguments: dict[str, Any],
    expected: dict[str, Any],
    weight: float = 1.0,
) -> dict[str, Any]:
    return {
        "id": f"investigation_{number:02d}",
        "milestone_id": milestone,
        "description": description,
        "weight": weight,
        "before_primary_mutation": True,
        "any_of": [
            {
                "tool": tool,
                "arguments": arguments,
                "match": "result_contains",
                "expected_result_contains": expected,
            }
        ],
    }


def build_investigations(
    scenario: Scenario, file_ids: dict[str, str]
) -> list[dict[str, Any]]:
    case = scenario.case_reference
    patient = scenario.patient
    order = scenario.primary_order
    medication = scenario.primary_medication
    policy_id = file_ids["policy/infusion-operations-policy.md"]
    approval_id = file_ids[f"approvals/approval-{scenario.approval.approval_id}.json"]
    order_file_id = file_ids[f"ehr/medication-request-{order.request_id}.json"]
    first_lot = next(
        lot for lot in scenario.lots if lot.medication_code == medication.code
    )
    in_scope = in_scope_administrations(scenario)
    if scenario.mode == "quantity":
        order_list_args = {"medication_code": medication.code, "status": "active"}
        order_list_expected = {
            "entry": [{"resource": {"id": o.request_id}} for _, o, _ in in_scope]
        }
        appointment_args = {
            "start_date": scenario.numbers["in_scope_window"][0],
            "end_date": scenario.numbers["in_scope_window"][1],
            "status": "booked",
        }
        appointment_expected = {
            "entry": [{"resource": {"id": a.appointment_id}} for a, _, _ in in_scope]
        }
    else:
        order_list_args = {"patient_id": patient.patient_id}
        order_list_expected = {"entry": [{"resource": {"id": order.request_id}}]}
        own = [a for a in scenario.appointments if a.patient_id == patient.patient_id]
        appointment_args = {"patient_id": patient.patient_id}
        appointment_expected = (
            {"entry": [{"resource": {"id": a.appointment_id}} for a in own]}
            if own
            else {"total": 0}
        )
    investigations = [
        _investigation(
            1,
            "investigation.scope",
            f"Established the isolated {case} scope, immutable handles, mounted systems, and evidence index before investigating {scenario.item}.",
            CONTEXT_TOOL,
            {},
            {"reference_records": {"case_reference": case}},
        ),
        _investigation(
            2,
            "investigation.scope",
            f"Located the task-scoped correspondence for {case} by searching the mailbox before opening any message; did not rely on a guessed sender or filename.",
            "messages.list",
            {"q": case},
            {"messages": [{"id": scenario.email.message_id}]},
        ),
        _investigation(
            3,
            "investigation.scope",
            f"Resolved {patient.mrn} to the immutable Patient record through an identifier search rather than a name match against a similarly named patient.",
            "ehr.patients.search",
            {"identifier": patient.mrn},
            {"entry": [{"resource": {"id": patient.patient_id}}]},
        ),
        _investigation(
            4,
            "investigation.scope",
            f"Listed the {case} case folder on the shared drive and identified the approval record and the order export by immutable file id.",
            "drive.files.list",
            {"q": case},
            {"files": [{"id": approval_id}, {"id": order_file_id}]},
        ),
        _investigation(
            5,
            "investigation.scope",
            "Listed the policy folder and distinguished the effective v3 policy from the superseded 2024 edition by file identity, not title.",
            "drive.files.list",
            {"q": "policy"},
            {"files": [{"id": policy_id}]},
        ),
        _investigation(
            6,
            "investigation.requirements",
            f"Read the active order {order.request_id}: dose basis, regimen, doses in scope, and infusion and observation minutes.",
            "ehr.medication_requests.get",
            {"request_id": order.request_id},
            {"id": order.request_id, "status": order.status},
        ),
        _investigation(
            7,
            "investigation.requirements",
            f"Read the current measured weight for {patient.patient_id} (Observation {WEIGHT_CODE}) and ignored the historical 2025 weight.",
            "ehr.observations.list",
            {"patient_id": patient.patient_id, "code": WEIGHT_CODE},
            {"entry": [{"resource": {"id": patient.weight_observation_id}}]},
        ),
        _investigation(
            8,
            "investigation.requirements",
            "Exported the effective v3 policy for the rounding, minimum-dating, stocking, chair, and authority rules; did not apply the superseded 2024 edition.",
            "drive.files.export",
            {"file_id": policy_id},
            {"file_id": policy_id},
        ),
        _investigation(
            9,
            "investigation.requirements",
            f"Read the formulary record for {medication.code}: vial strength and minimum remaining dating.",
            "pharmacy.medications.get",
            {"medication_code": medication.code},
            {"medication_code": medication.code},
        ),
        _investigation(
            10,
            "investigation.requirements",
            f"Listed the active orders that define the requirement ({', '.join(sorted({o.request_id for _, o, _ in in_scope}) if in_scope else [order.request_id])}) and excluded superseded or out-of-scope orders.",
            "ehr.medication_requests.list",
            order_list_args,
            order_list_expected,
        ),
        _investigation(
            11,
            "investigation.constraints",
            f"Listed every {medication.code} lot with quantity, expiry, quarantine status, and reservations before netting the on-hand coverage.",
            "pharmacy.lots.list",
            {"medication_code": medication.code},
            {"lots": [{"lot_id": first_lot.lot_id}]},
        ),
        _investigation(
            12,
            "investigation.constraints",
            f"Read the chair schedule (FHIR Slot sessions) for {scenario.numbers.get('capacity_window', [scenario.slots_query['start_date']])[0]} onward to find the first free session that displaces no protected or blocked slot.",
            "scheduling.slots.list",
            {"location_id": "LOC-INF", **scenario.slots_query},
            {"slots": [{"id": scenario.selected_slot_id}]},
        ),
        _investigation(
            13,
            "investigation.constraints",
            f"Read the supplier confirmation {scenario.confirmation.confirmation_id} for the independently confirmed standard and expedited delivery dates and the expedite fee.",
            "supplier.confirmations.get",
            {"confirmation_id": scenario.confirmation.confirmation_id},
            {
                "confirmation_id": scenario.confirmation.confirmation_id,
                "standard_delivery_date": scenario.confirmation.standard_date,
            },
        ),
        _investigation(
            14,
            "investigation.authority",
            f"Read approval {scenario.approval.approval_id} for its exact scope: record, quantity, supplier, fee allowance, and what it does not cover.",
            "approvals.get",
            {"approval_id": scenario.approval.approval_id},
            {"approval_id": scenario.approval.approval_id},
        ),
        _investigation(
            15,
            "investigation.authority",
            "Exported the approval record on the drive and confirmed it matches the workflow record before relying on it.",
            "drive.files.export",
            {"file_id": approval_id},
            {"file_id": approval_id},
        ),
        _investigation(
            16,
            "investigation.erp_correlation",
            f"Read the request message {scenario.email.message_id} for the documented control date and the business need in the requester's words.",
            "messages.get",
            {"message_id": scenario.email.message_id},
            {"id": scenario.email.message_id},
        ),
        _investigation(
            17,
            "investigation.erp_correlation",
            f"Read the team chat thread {scenario.chat.thread_id} for lot, chair, and authority remarks that qualify the system records.",
            "chat.threads.get",
            {"thread_id": scenario.chat.thread_id},
            {"thread_id": scenario.chat.thread_id},
        ),
        _investigation(
            18,
            "investigation.erp_correlation",
            "Correlated the appointment records that fix the schedule scope by immutable id.",
            "scheduling.appointments.list",
            appointment_args,
            appointment_expected,
        ),
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


def build_oracle_steps(
    scenario: Scenario, investigations: list[dict[str, Any]], model: dict[str, Any]
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [
        {"phase": "context", "tool": CONTEXT_TOOL, "arguments": {}, "control": True}
    ]
    order = [2, 16, 3, 10, 6, 7, 4, 5, 8, 9, 11, 18, 12, 13, 14, 15, 17]
    by_number = {int(item["id"].rsplit("_", 1)[1]): item for item in investigations}
    order.extend(number for number in sorted(by_number) if number not in order)
    for number in order:
        call = by_number[number]["any_of"][0]
        steps.append(
            {
                "phase": "investigation",
                "tool": call["tool"],
                "arguments": call["arguments"],
                "control": True,
            }
        )
    primary = scenario.primary_write
    steps.append(
        {
            "phase": "primary_mutation",
            "tool": primary.tool,
            "arguments": primary.arguments,
            "control": False,
        }
    )
    steps.append(
        {
            "phase": "post_write_verification",
            "tool": primary.readback_tool,
            "arguments": primary.readback_arguments,
            "control": True,
        }
    )
    steps.append(
        {
            "phase": "collaboration",
            "tool": "notes.drafts.create",
            "arguments": {
                "recipient": scenario.collaboration["recipient"],
                "subject": scenario.collaboration["subject"],
                "body": scenario.collaboration["body"],
                "related_request_id": scenario.primary_order.request_id,
                "related_patient_id": scenario.patient.patient_id,
            },
            "control": False,
        }
    )
    steps.append(
        {
            "phase": "answer",
            "tool": SUBMIT_TOOL,
            "arguments": dict(model["answer"]),
            "control": False,
        }
    )
    return steps


def build_assertions(scenario: Scenario, model: dict[str, Any]) -> list[dict[str, Any]]:
    primary = scenario.primary_write
    task_id = scenario.task_id
    selected = model["selected_option"]
    completion = model["selected_completion"]
    payload_values = ", ".join(
        f"{key}={value!r}" for key, value in primary.arguments.items()
    )
    return [
        {
            "id": "mutation_01",
            "milestone_id": "state.primary",
            "description": f"Required {scenario.item} to reach business outcome {primary.outcome_label!r} through {primary.tool} with exact provider-critical values {payload_values}. The audited change binds selected option {selected}, approval {scenario.approval.approval_id}, and constraint {scenario.labels.constraint_label}; no other record satisfies this state criterion.",
            "table": "mutations",
            "where": {"task_id": task_id, "mutation_id": f"{task_id}-mutation-01"},
            "values": {
                "tool": primary.tool,
                "table_name": primary.table,
                "record_id": primary.record_id,
                "status": primary.status,
            },
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
            "values": {
                "tool": "notes.drafts.create",
                "table_name": "note_drafts",
                "status": "DRAFT",
            },
            "payload_contains": {
                "tool": "notes.drafts.create",
                "arguments": {"recipient": scenario.collaboration["recipient"]},
            },
            "payload_text_contains": [selected, completion],
            "payload_text_any_of": [
                [
                    scenario.case_reference,
                    scenario.patient.mrn,
                    scenario.primary_order.request_id,
                ]
            ],
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


@fact_text_contract
def build_task(scenario: Scenario) -> dict[str, Any]:
    verify_numbers(scenario)
    assets = build_assets(scenario)
    drive_files, file_ids = mount_drive(scenario, assets)
    evidence = [
        {
            "asset_id": a["asset_id"],
            "task_id": scenario.task_id,
            "path": a["path"],
            "title": a["title"],
            "kind": a["kind"],
            "source": a["source"],
            "media_type": a["media_type"],
            "sha256": a["sha256"],
        }
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
        "any_of": [
            {
                "tool": primary.readback_tool,
                "arguments": primary.readback_arguments,
                "match": "result_contains",
                "expected_result_contains": primary.readback_expected,
            }
        ],
        "expected_result_contains": primary.readback_expected,
        "target_identity": primary.readback_arguments,
        "materializes_new_record": primary.tool.endswith(".create"),
        "description": f"Read {primary.record_id} back through {primary.readback_tool} after the change and confirmed the persisted provider values ({', '.join(f'{k}={v!r}' for k, v in primary.readback_expected.items())}) rather than relying on the write acknowledgement.",
        "weight": 2.0,
    }
    answer = model["answer"]
    checks = answer_checks(
        answer,
        [
            "recommended_option",
            "recommended_outcome_date",
            ITEM_FIELD[scenario.mode],
            GAP_FIELD[scenario.mode],
            "decision_timing_status",
        ],
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
        correlated_systems=["ehr", "scheduling", "pharmacy", "messages", "chat"],
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
        "decision_model": {
            key: value
            for key, value in model.items()
            if key not in {"answer", "answer_descriptions"}
        },
        "answer_schema": answer_schema(
            answer, model["answer_descriptions"], option_ids
        ),
        "expected": {
            "answer": answer,
            "answer_checks": checks,
            "calculations": model["calculations"],
            "assertions": assertions,
            "investigations": investigations,
            "post_write_verifications": [readback],
        },
        "required_investigations": investigations,
        "required_reads": [
            step["tool"]
            for step in steps
            if step["control"] and step["phase"] in {"context", "investigation"}
        ],
        "required_read_calls": [item["any_of"][0] for item in investigations],
        "post_write_verifications": [readback],
        "oracle_steps": steps,
        "sequence_signature": sequence_signature(steps),
        "allowed_write_tables": sorted(
            {
                primary.table,
                *primary.extra_tables,
                "note_drafts",
                "mutations",
                "answers",
                "audit_log",
            }
        ),
        "rubric_milestones": rubric,
        "negative_controls": {
            "unauthorized_write": dict(scenario.unauthorized_write),
            "wrong_evidence": {
                "tool": "drive.files.export",
                "arguments": {"file_id": file_ids[decoy_path]},
            },
        },
        "reference_records": {
            "case_reference": scenario.case_reference,
            "ehr": {
                "mrn": scenario.patient.mrn,
                "patient_search": {
                    "tool": "ehr.patients.search",
                    "arguments": {"identifier": scenario.patient.mrn},
                },
            },
            "messages": {"search_query": scenario.case_reference},
            "drive": {
                "case_folder_query": scenario.case_reference,
                "policy_query": "policy",
            },
            "pharmacy": {
                "medication_code": scenario.primary_medication.code,
                "locations": sorted({lot.location_id for lot in scenario.lots}),
            },
            "scheduling": {
                "location_id": "LOC-INF",
                "calendar_window": scenario.slots_query,
            },
            "supplier": {"confirmation_id": scenario.confirmation.confirmation_id},
            "approvals": {"approval_id": scenario.approval.approval_id},
            "chat": {"thread_id": scenario.chat.thread_id},
        },
        "starting_records": [
            *[
                {
                    "system": "scheduling",
                    "resource_type": "Appointment",
                    "resource_id": a.appointment_id,
                    "status": a.status,
                }
                for a in scenario.appointments
            ],
            {
                "system": "pharmacy",
                "resource_type": "PurchaseOrder",
                "resource_id": "PO-5100",
                "status": "RECEIVED",
            },
            *[
                {
                    "system": "pharmacy",
                    "resource_type": "StockTransfer",
                    "resource_id": row["transfer_id"],
                    "status": row["status"],
                }
                for row in scenario.seed.get("transfers", ())
            ],
        ],
        "evaluation": {
            "metric": "HubScore",
            "strict_pass": "every rubric milestone passes",
            "llm_judge_calls": 0,
        },
        "workflow": {
            "reads": len(
                [s for s in steps if s["phase"] in {"context", "investigation"}]
            ),
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
    "first_session_on_or_after",
    "verify_numbers",
]
