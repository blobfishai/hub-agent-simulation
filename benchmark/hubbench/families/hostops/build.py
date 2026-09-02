"""Assemble HostOps tasks: seed tables, scattered evidence, decision model, sealed contract.

Every declared number in a scenario is recomputed from the seeded world
(segment sets, farm calendar, tickets, meterings, retrieval confirmations) and
the build fails on any disagreement, so the answer contract can never drift
from the data the agent actually sees.
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
from ...engine.decision import DecisionInputs, answer_schema, build_decision_model
from ...engine.families import CONTEXT_TOOL, SUBMIT_TOOL
from ...engine.quality_assets import (
    quality_support_assets,
    quality_support_investigations,
    scoped_csv,
    scoped_markdown,
)
from . import tools as host_tools
from .policy import SUPERSEDED_RUNBOOK, effective_runbook
from .scenarios import scenarios
from .specs import (
    AS_OF,
    ENGINEERS,
    ORGANIZATION,
    STORES,
    USERS,
    VENDORS,
    WINDOW_HOURS,
    WINDOW_TIMES,
    Scenario,
    SegmentSet,
    Service,
    Ticket,
    business_days,
    next_business_day,
    segments_for_payload,
    ticket_unit_gb,
    window_id,
)

BENCHMARK = "HubBench"
FAMILY_SLUG = "hostops"
FAMILY_VERSION = "1.0.0"
PRIMARY_KEYS = {
    "reservations": "reservation_id",
    "restore_jobs": "restore_id",
    "store_copies": "copy_id",
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
CASE_FOLDER = "Platform Operations/Cases/{case}"
OPEN_SOURCE_ANCHORS = (
    {
        "name": "Terminal-Bench",
        "harbor_dataset": "terminal-bench/terminal-bench",
        "harbor_url": "https://hub.harborframework.com/datasets/terminal-bench/terminal-bench/latest",
        "upstream_url": "https://github.com/harbor-framework/terminal-bench",
        "license": "Apache-2.0",
        "evaluation_shape": "stateful sandbox tasks with deterministic end-state verification",
    },
    {
        "name": "Terminal-Bench 2.1 file recovery",
        "harbor_dataset": "NovitaAI/tb21-file-recovery",
        "harbor_url": "https://hub.harborframework.com/datasets/NovitaAI/tb21-file-recovery/latest",
        "upstream_url": "https://github.com/harbor-framework/terminal-bench",
        "license": "Apache-2.0",
        "evaluation_shape": "file operations, data processing, log analysis, and recovery tasks",
    },
)
PLAN_SELECTED_OPTIONS = {
    "standard_retrieval_plan": "standard",
    "expedite_vendor_retrieval": "expedited",
}


# --------------------------------------------------------------------------- #
# Derivations and cross-checks
# --------------------------------------------------------------------------- #


def _services_by_id(scenario: Scenario) -> dict[str, Service]:
    return {svc.service_id: svc for svc in (scenario.service, *scenario.other_services)}


def _tickets_by_id(scenario: Scenario) -> dict[str, Ticket]:
    return {ticket.ticket_id: ticket for ticket in scenario.tickets}


def ticket_segments(scenario: Scenario, ticket: Ticket) -> int:
    payload = ticket_unit_gb(ticket, _services_by_id(scenario))
    seg_gb = next(
        item for item in scenario.classes if item.code == ticket.artifact_class
    ).segment_gb
    return segments_for_payload(payload, seg_gb) * ticket.units_in_scope


def _purge_horizon(scenario: Scenario) -> str:
    return (
        date.fromisoformat(AS_OF)
        + timedelta(days=scenario.primary_class.min_retention_days)
    ).isoformat()


def _set_excluded(item: SegmentSet, scenario: Scenario) -> bool:
    return (
        item.status != "VERIFIED"
        or item.reserved_for is not None
        or item.register_excluded
        or item.retention_expiry <= _purge_horizon(scenario)
    )


def calendar(scenario: Scenario) -> dict[tuple[str, str, str], dict[str, Any]]:
    overrides = {
        (item.day, item.runner, item.session): item for item in scenario.windows
    }
    grid: dict[tuple[str, str, str], dict[str, Any]] = {}
    for day in business_days():
        for runner in scenario.runners:
            for session in ("AM", "PM"):
                key = (day, runner.runner_id, session)
                override = overrides.get(key)
                if override is None:
                    entry = {
                        "status": "busy",
                        "hold_reason": "scheduled ci load",
                        "reservation_id": None,
                    }
                elif override.status == "busy" and override.reason.startswith("RES-"):
                    entry = {
                        "status": "busy",
                        "hold_reason": "reserved",
                        "reservation_id": override.reason,
                    }
                elif override.status == "free":
                    entry = {
                        "status": "free",
                        "hold_reason": None,
                        "reservation_id": None,
                    }
                else:
                    entry = {
                        "status": override.status,
                        "hold_reason": override.reason or override.status,
                        "reservation_id": None,
                    }
                grid[key] = entry
    return grid


def first_window_on_or_after(
    scenario: Scenario, start: str, windows_needed: int, runners: list[str]
) -> tuple[str, str, str] | None:
    grid = calendar(scenario)
    active = {
        runner.runner_id for runner in scenario.runners if runner.status == "ACTIVE"
    }
    for day in business_days():
        if day < start:
            continue
        for runner in runners:
            if runner not in active:
                continue
            free = [
                session
                for session in ("AM", "PM")
                if grid[(day, runner, session)]["status"] == "free"
            ]
            if windows_needed == 1 and free:
                return day, runner, free[0]
            if windows_needed == 2 and len(free) == 2:
                return day, runner, "AM+PM"
    return None


def in_scope_runs(scenario: Scenario) -> list[tuple[Any, Ticket]]:
    window = scenario.numbers.get("in_scope_window")
    if not window:
        return []
    tickets = _tickets_by_id(scenario)
    code = scenario.primary_class.code
    selected = []
    for reservation in scenario.reservations:
        if reservation.status != "booked" or reservation.start is None:
            continue
        ticket = tickets.get(reservation.ticket_id or "")
        if ticket is None or ticket.artifact_class != code:
            continue
        if window[0] <= reservation.start[:10] <= window[1]:
            selected.append((reservation, ticket))
    return sorted(selected, key=lambda item: (item[0].start, item[0].reservation_id))


def verify_numbers(scenario: Scenario) -> None:
    numbers = scenario.numbers
    extra = scenario.extra_answer
    cls = scenario.primary_class
    services = _services_by_id(scenario)
    problems: list[str] = []

    def check(label: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            problems.append(
                f"{label}: computed {actual!r} but scenario declares {expected!r}"
            )

    def intish(value: float) -> Any:
        return int(value) if float(value).is_integer() else value

    scoped_sets = [
        item
        for item in scenario.sets
        if item.artifact_class == cls.code
        and item.store_id == numbers["coverage_location"]
    ]
    if scenario.mode in {"plan", "quantity"}:
        observed = sum(item.segments for item in scoped_sets)
        excluded = sum(
            item.segments for item in scoped_sets if _set_excluded(item, scenario)
        )
        check("observed", observed, numbers["observed"])
        check("excluded", excluded, numbers["excluded"])
        check("eligible", observed - excluded, numbers["eligible"])
    if scenario.mode == "plan":
        ticket = scenario.primary_ticket
        payload = ticket_unit_gb(ticket, services)
        per_unit = segments_for_payload(payload, cls.segment_gb)
        check("required_payload_gb", intish(payload), extra["required_payload_gb"])
        check("segments_per_unit", per_unit, extra["segments_per_unit"])
        check("units_in_scope", ticket.units_in_scope, extra["units_in_scope"])
        check("scope", per_unit * ticket.units_in_scope, numbers["scope"])
    if scenario.mode == "quantity":
        runs = in_scope_runs(scenario)
        check("scheduled_runs", len(runs), extra["scheduled_runs"])
        scope = sum(ticket_segments(scenario, ticket) for _, ticket in runs)
        check("scope", scope, numbers["scope"])
        first = runs[0][0] if runs else None
        if first is not None:
            session = "AM" if first.start[11:] < WINDOW_TIMES["PM"][0] else "PM"
            check(
                "first_run_window",
                f"{first.runner_id}/{first.start[:10]}/{session}",
                extra["first_run_window"],
            )
            check("business_need", first.start[:10], scenario.business_need)
        metered = [ticket for _, ticket in runs if ticket.unit_basis == "metered"]
        if metered and "metered_bundle_gb" in extra:
            check(
                "metered_bundle_gb",
                intish(services[metered[0].service_id].meter_value),
                extra["metered_bundle_gb"],
            )
        if "margin" in numbers:
            check(
                "transaction_quantity",
                numbers["gap"] + numbers["margin"],
                numbers["transaction_quantity"],
            )
            check("margin_segments", numbers["margin"], extra["margin_segments"])
        if "receiving_usable" in numbers:
            receiving = [
                item
                for item in scenario.sets
                if item.artifact_class == cls.code
                and item.store_id == "STORE-NEAR"
                and not _set_excluded(item, scenario)
            ]
            check(
                "receiving_usable",
                sum(item.segments for item in receiving),
                numbers["receiving_usable"],
            )
            check(
                "receiving_store_usable",
                numbers["receiving_usable"],
                extra["receiving_store_usable"],
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
        days = [day for day in business_days() if start <= day <= end]
        keys = [
            (day, runner, session)
            for day in days
            for runner in numbers["eligible_runners"]
            for session in ("AM", "PM")
        ]
        candidate = len(keys) * WINDOW_HOURS
        free = sum(1 for key in keys if grid[key]["status"] == "free")
        check("candidate", candidate, numbers["observed"])
        check("excluded", candidate - free * WINDOW_HOURS, numbers["excluded"])
        check("eligible", free * WINDOW_HOURS, numbers["eligible"])
        affected = [
            ticket for ticket in scenario.tickets if ticket.artifact_class == cls.code
        ]
        if numbers.get("scope_source") == "primary":
            hours = (
                scenario.primary_ticket.build_minutes
                + scenario.primary_ticket.verify_minutes
            ) / 60
        else:
            hours = sum(
                (ticket.build_minutes + ticket.verify_minutes) / 60
                for ticket in affected
            )
        check("scope", int(hours), numbers["scope"])
        usable = sum(
            item.segments for item in scoped_sets if not _set_excluded(item, scenario)
        )
        for key in ("snapshot_segments_usable", "baseline_segments_usable"):
            if key in extra:
                check(key, usable, extra[key])
        if numbers.get("scope_source") == "primary":
            required_segments = ticket_segments(scenario, scenario.primary_ticket)
        else:
            required_segments = sum(
                ticket_segments(scenario, ticket) for ticket in affected
            )
        for key in ("snapshot_segments_required", "baseline_segments_required"):
            if key in extra:
                check(key, required_segments, extra[key])
        if "windows_required" in extra:
            check(
                "windows_required",
                int(numbers["sessions_needed"]),
                extra["windows_required"],
            )
        if "requested_day" in extra:
            check(
                "requested_day", numbers["capacity_window"][0], extra["requested_day"]
            )
        if "affected_reservations" in extra:
            tickets = _tickets_by_id(scenario)
            stranded = [
                r
                for r in scenario.reservations
                if tickets.get(r.ticket_id or "") in affected
            ]
            check(
                "affected_reservations", len(stranded), extra["affected_reservations"]
            )
        if "runs_per_window" in extra:
            check(
                "runs_per_window",
                extra["affected_reservations"] // extra["windows_required"],
                extra["runs_per_window"],
            )
    gap = max(0, numbers["scope"] - numbers["eligible"])
    check("gap", gap, numbers["gap"])
    check(
        "standard_readiness",
        next_business_day(scenario.confirmation.standard_date),
        scenario.standard_readiness,
    )
    check(
        "expedited_readiness",
        next_business_day(scenario.confirmation.expedited_date),
        scenario.expedited_readiness,
    )
    windows_needed = (
        2 if scenario.mode == "schedule" and numbers.get("full_day_needed") else 1
    )
    slot_runners = numbers["eligible_runners"]
    standard_slot = first_window_on_or_after(
        scenario, scenario.standard_readiness, windows_needed, slot_runners
    )
    expedited_slot = first_window_on_or_after(
        scenario, scenario.expedited_readiness, windows_needed, slot_runners
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
            "earliest_qualified_base_window",
            numbers["standard_slot_date"],
            extra["earliest_qualified_base_window"],
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
            extra["expedite_completion_days_saved"],
        )
        selected = next(option for option in scenario.options if option.recommended)
        if selected.id in PLAN_SELECTED_OPTIONS:
            readiness = (
                scenario.standard_readiness
                if PLAN_SELECTED_OPTIONS[selected.id] == "standard"
                else scenario.expedited_readiness
            )
            slot = first_window_on_or_after(scenario, readiness, 1, slot_runners)
            if slot is not None:
                check(
                    "selected_runner_window",
                    f"{slot[1]}/{slot[0]}/{slot[2]}",
                    extra["selected_runner_window"],
                )
                check("selected completion", slot[0], selected.completion)
    if scenario.mode == "schedule":
        selected_date = next(
            option for option in scenario.options if option.recommended
        ).completion
        if numbers.get("full_day_needed"):
            full_day = first_window_on_or_after(
                scenario, numbers["capacity_window"][0], 2, numbers["eligible_runners"]
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
            free_windows = [
                key
                for key in sorted(grid)
                if key[1] in numbers["eligible_runners"]
                and grid[key]["status"] == "free"
                and key[0] >= numbers["capacity_window"][0]
            ]
            check(
                "selected_resource",
                f"{free_windows[0][1]}/{free_windows[0][0]}/{free_windows[0][2]}"
                if free_windows
                else None,
                numbers["selected_resource"],
            )
            sessions_needed = int(numbers["sessions_needed"])
            check(
                "selected completion",
                free_windows[sessions_needed - 1][0]
                if len(free_windows) >= sessions_needed
                else None,
                selected_date,
            )
    if scenario.selected_window_id not in {
        window_id(runner, day, session) for (day, runner, session) in calendar(scenario)
    }:
        problems.append(
            f"selected window {scenario.selected_window_id} is not on the calendar"
        )
    if problems:
        raise ValueError(
            f"{scenario.task_id} scenario data disagrees with its declared numbers:\n  "
            + "\n  ".join(problems)
        )


# --------------------------------------------------------------------------- #
# Seed tables
# --------------------------------------------------------------------------- #


def _meterings(service: Service, *, stale: bool) -> list[dict[str, Any]]:
    rows = [
        {
            "metering_id": service.metering_id,
            "service_id": service.service_id,
            "metric": service.meter_metric,
            "value": service.meter_value,
            "unit": "GB",
            "measured_at": service.meter_date,
            "status": "final",
        },
    ]
    if stale:
        rows.append(
            {
                "metering_id": service.stale_metering_id,
                "service_id": service.service_id,
                "metric": service.meter_metric,
                "value": service.stale_value,
                "unit": "GB",
                "measured_at": service.stale_date,
                "status": "final",
            }
        )
    return rows


def _hosts(scenario: Scenario) -> list[dict[str, Any]]:
    rows = []
    for index, service in enumerate(
        (scenario.service, *scenario.other_services[:2]), start=1
    ):
        rows.append(
            {
                "host_id": f"H-{scenario.ordinal:03d}-{index:02d}",
                "hostname": f"{service.code}-01.prod.ridgeline.internal",
                "role": "app",
                "os_release": "ridgeline-linux 12.4",
                "status": "in_service",
                "service_id": service.service_id,
            }
        )
    rows.append(
        {
            "host_id": f"H-{scenario.ordinal:03d}-90",
            "hostname": "bastion-01.mgmt.ridgeline.internal",
            "role": "bastion",
            "os_release": "ridgeline-linux 12.4",
            "status": "in_service",
            "service_id": None,
        }
    )
    return rows


def seed_tables(
    scenario: Scenario,
    drive_files: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grid = calendar(scenario)
    windows = [
        {
            "window_id": window_id(runner, day, session),
            "runner_id": runner,
            "service_date": day,
            "session": session,
            "start_time": WINDOW_TIMES[session][0],
            "end_time": WINDOW_TIMES[session][1],
            **entry,
        }
        for (day, runner, session), entry in sorted(grid.items())
    ]
    return {
        "users": [dict(row) for row in USERS],
        "stores": [dict(row) for row in STORES],
        "engineers": [dict(row) for row in ENGINEERS],
        "services": [
            {
                "service_id": s.service_id,
                "code": s.code,
                "name": s.name,
                "tier": s.tier,
                "owner_team": s.owner_team,
                "primary_engineer_id": s.engineer_id,
            }
            for s in (scenario.service, *scenario.other_services)
        ],
        "hosts": _hosts(scenario),
        "meterings": [
            row
            for index, s in enumerate((scenario.service, *scenario.other_services))
            for row in _meterings(s, stale=index == 0)
        ],
        "artifact_classes": [
            {
                "artifact_class": c.code,
                "display": c.display,
                "segment_size_gb": c.segment_gb,
                "segment_unit": "GB",
                "storage_tier": c.storage_tier,
                "minimum_retention_days": c.min_retention_days,
                "signed": int(c.signed),
                "interchangeable_with": c.interchangeable_with,
            }
            for c in scenario.classes
        ],
        "tickets": [
            {
                "ticket_id": t.ticket_id,
                "service_id": t.service_id,
                "artifact_class": t.artifact_class,
                "unit_kind": t.unit_kind,
                "unit_basis": t.unit_basis,
                "unit_gb": t.unit_gb,
                "units_in_scope": t.units_in_scope,
                "scope_note": t.scope_note,
                "build_minutes": t.build_minutes,
                "verify_minutes": t.verify_minutes,
                "status": t.status,
                "kind": t.kind,
                "priority": t.priority,
                "opened_at": t.opened_at,
                "requested_by": t.requested_by,
                "note": t.note or None,
            }
            for t in scenario.tickets
        ],
        "backup_sets": [
            {
                "set_id": s.set_id,
                "artifact_class": s.artifact_class,
                "set_label": s.set_label,
                "store_id": s.store_id,
                "segment_count": s.segments,
                "retention_expiry": s.retention_expiry,
                "status": s.status,
                "status_reason": s.reason,
                "reserved_for_ticket": s.reserved_for,
            }
            for s in scenario.sets
        ],
        "jobs": [
            {
                "job_id": j.job_id,
                "name": j.name,
                "service_id": j.service_id,
                "kind": j.kind,
                "schedule": j.schedule,
                "status": j.status,
            }
            for j in scenario.jobs
        ],
        "job_runs": [
            {
                "run_id": r.run_id,
                "job_id": r.job_id,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
                "status": r.status,
                "exit_code": r.exit_code,
                "summary": r.summary,
            }
            for r in scenario.job_runs
        ],
        "runners": [
            {
                "runner_id": r.runner_id,
                "pool": "release-pool",
                "name": r.name,
                "status": r.status,
                "isolation_capable": int(r.isolation_capable),
                "status_note": r.note,
            }
            for r in scenario.runners
        ],
        "farm_windows": windows,
        "reservations": [
            {
                "reservation_id": r.reservation_id,
                "service_id": r.service_id,
                "ticket_id": r.ticket_id,
                "runner_id": r.runner_id,
                "start_time": r.start,
                "end_time": r.end,
                "status": r.status,
                "description": r.description,
                "revision": 1,
                "last_updated": "2026-04-10T12:00:00",
            }
            for r in scenario.reservations
        ],
        "vendors": [dict(row) for row in VENDORS],
        "retrieval_confirmations": [
            {
                "confirmation_id": c.confirmation_id,
                "vendor_id": c.vendor_id,
                "artifact_class": c.artifact_class,
                "reference": c.reference,
                "segments_available": c.segments_available,
                "standard_ready_date": c.standard_date,
                "expedited_ready_date": c.expedited_date,
                "expedite_fee_usd": c.fee,
                "per_segment_fee_usd": c.per_segment_fee,
                "valid_until": c.valid_until,
                "status": c.status,
                "note": c.note,
            }
            for c in (scenario.confirmation, *scenario.other_confirmations)
        ],
        "restore_jobs": [
            {
                "restore_id": "RST-3400",
                "vendor_id": "VND-IRONHOLD",
                "confirmation_id": None,
                "artifact_class": scenario.classes[-1].code,
                "segment_count": 2,
                "unit": "SEGMENT",
                "retrieval_option": "standard",
                "expected_ready_date": "2026-04-01",
                "status": "RECEIVED",
                "requested_by": "platform_operations_coordinator",
                "created_at": "2026-03-27T09:30:00",
                "revision": 1,
            },
        ],
        "store_copies": [dict(row) for row in scenario.seed.get("copies", ())],
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
                "approval_id": "AP-HO-0090",
                "subject": "Quarterly build-cache SSD replenishment standing order",
                "approver_id": "U-VANCE",
                "approver_role": "release_engineering_manager",
                "status": "APPROVED",
                "granted_on": "2026-02-06",
                "scope_json": json.dumps(
                    {"category": "CONSUMABLES", "max_spend_usd": 9000}, sort_keys=True
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
                "thread_id": f"THR-{scenario.ordinal:04d}-OPS",
                "channel": "email",
                "sender": "annika.strom@ridgeline.example",
                "recipients": "platform-ops@ridgeline.example",
                "subject": "Weekly operations note",
                "sent_at": "2026-04-10T08:00:00",
                "body": "On-call rota for the week of 2026-04-13 is posted. Runner capability flags are on the shared drive roster; no changes to protected blocks.",
                "attachments_json": "[]",
                "labels": "operations",
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
                "channel": "#platform-ops",
                "title": "General — kernel flags and cage access",
                "messages_json": json.dumps(
                    [
                        {
                            "author": "Annika Strøm",
                            "ts": "2026-04-09T16:40:00",
                            "text": "Reminder: log every kernel flag change in the change tracker.",
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


def _ticket_json(scenario: Scenario, ticket: Ticket) -> str:
    cls = next(c for c in scenario.classes if c.code == ticket.artifact_class)
    row = {
        "ticket_id": ticket.ticket_id,
        "service_id": ticket.service_id,
        "artifact_class": ticket.artifact_class,
        "unit_kind": ticket.unit_kind,
        "unit_basis": ticket.unit_basis,
        "unit_gb": ticket.unit_gb,
        "units_in_scope": ticket.units_in_scope,
        "scope_note": ticket.scope_note,
        "build_minutes": ticket.build_minutes,
        "verify_minutes": ticket.verify_minutes,
        "status": ticket.status,
        "kind": ticket.kind,
        "priority": ticket.priority,
        "opened_at": ticket.opened_at,
        "requested_by": ticket.requested_by,
        "note": ticket.note,
    }
    rendered = host_tools._ticket(
        row, {"display": cls.display, "segment_size_gb": cls.segment_gb}
    )
    return (
        json.dumps(
            {"export": "releases.tickets.get", "record": rendered},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _service_summary_json(scenario: Scenario) -> str:
    service = scenario.service
    rendered = host_tools._service(
        {
            "service_id": service.service_id,
            "code": service.code,
            "name": service.name,
            "tier": service.tier,
            "owner_team": service.owner_team,
            "primary_engineer_id": service.engineer_id,
        }
    )
    meterings = [host_tools._metering(row) for row in _meterings(service, stale=True)]
    return (
        json.dumps(
            {
                "export": "cmdb.services.get + cmdb.meterings.list",
                "service": rendered,
                "meterings": meterings,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _confirmation_text(scenario: Scenario) -> str:
    c = scenario.confirmation
    vendor = next(row["name"] for row in VENDORS if row["vendor_id"] == c.vendor_id)
    account = next(
        row["account_number"] for row in VENDORS if row["vendor_id"] == c.vendor_id
    )
    return (
        f"{vendor}\nRetrieval confirmation {c.reference} (system reference {c.confirmation_id})\nCustomer: Ridgeline Systems Platform Operations, account {account}\n"
        f"Case reference: {scenario.case_reference}\nItem: {c.artifact_class} — {scenario.primary_class.display}\nSegments available for this confirmation: {c.segments_available}\nPer-segment retrieval fee: USD {c.per_segment_fee:.2f}\n"
        f"Standard retrieval-ready date: {c.standard_date}\nExpedited retrieval-ready date: {c.expedited_date} (expedite fee USD {c.fee}, flat)\nValid until: {c.valid_until}\nNotes: {c.note}\n"
        "Segments are delivered to the customer's receiving endpoint; staging release is subject to the customer's checksum verification.\n"
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
                SUPERSEDED_RUNBOOK,
                task_id=scenario.task_id,
                case_reference=scenario.case_reference,
            ),
            preview="2024 runbook retained for audit only; superseded by v4.",
        )
    if doc.kind == "decoy_ticket":
        ticket_id = (
            doc.path.rsplit("/", 1)[-1].removeprefix("ticket-").removesuffix(".json")
        )
        ticket = next(t for t in scenario.tickets if t.ticket_id == ticket_id)
        return asset(
            doc.path,
            kind=doc.kind,
            title=doc.title,
            source="releases_export",
            media_type=JSON,
            content=_ticket_json(scenario, ticket),
            preview="A similarly named or superseded ticket that must not drive the requirement.",
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
    content = (
        scoped_csv(
            doc.content,
            task_id=scenario.task_id,
            case_reference=scenario.case_reference,
        )
        if doc.kind == "margin_policy"
        else doc.content
    )
    return asset(
        doc.path,
        kind=doc.kind,
        title=doc.title,
        source="drive",
        media_type=doc.media_type,
        content=content,
        preview=doc.title,
    )


def build_assets(scenario: Scenario) -> list[dict[str, Any]]:
    case = scenario.case_reference
    grid = calendar(scenario)
    assets: list[dict[str, Any]] = [
        asset(
            "runbook/platform-operations-runbook.md",
            kind="policy",
            title="Platform operations runbook v4 (effective)",
            source="drive",
            media_type=MARKDOWN,
            content=scoped_markdown(
                effective_runbook(AS_OF), task_id=scenario.task_id, case_reference=case
            ),
            preview="Sizing, restorable-source, window, and authority rules in force.",
        ),
    ]
    if scenario.decoy_doc.kind != "policy_superseded":
        assets.append(
            asset(
                "runbook/superseded-operations-runbook-2024.md",
                kind="policy_superseded",
                title="Platform operations runbook 2024 (superseded)",
                source="drive",
                media_type=MARKDOWN,
                content=scoped_markdown(
                    SUPERSEDED_RUNBOOK, task_id=scenario.task_id, case_reference=case
                ),
                preview="2024 runbook retained for audit only; superseded by v4.",
            )
        )
    assets.append(_decoy_asset(scenario))
    assets.extend(
        [
            asset(
                f"releases/ticket-{scenario.primary_ticket.ticket_id}.json",
                kind="ticket_export",
                title=f"Ticket {scenario.primary_ticket.ticket_id} (releases export)",
                source="releases_export",
                media_type=JSON,
                content=_ticket_json(scenario, scenario.primary_ticket),
                preview="The active ticket: payload basis, scope, and run durations.",
            ),
            asset(
                f"cmdb/service-{scenario.service.code}-summary.json",
                kind="service_summary",
                title=f"Service {scenario.service.code} summary with payload meterings (CMDB export)",
                source="cmdb_export",
                media_type=JSON,
                content=_service_summary_json(scenario),
                preview="Service identity plus current and historical payload meterings.",
            ),
            asset(
                "backup/artifact-class-catalog.csv",
                kind="class_catalog",
                title="Artifact class catalog: segment sizes and minimum retention",
                source="backup_export",
                media_type=CSV,
                content="artifact_class,display,segment_size_gb,storage_tier,minimum_retention_days,signed,interchangeable_with\n"
                + "".join(
                    f"{c.code},{c.display},{c.segment_gb:g},{c.storage_tier},{c.min_retention_days},{'yes' if c.signed else 'no'},{c.interchangeable_with or ''}\n"
                    for c in scenario.classes
                ),
                preview="Segment sizes used for rounding and the 14-day minimum retention.",
            ),
            asset(
                "backup/segment-holdings-by-set.xlsx",
                kind="holdings_workbook",
                title="Catalogued segment holdings by set (gross)",
                source="backup_workbook",
                media_type=XLSX,
                rows=[
                    [
                        "set_label",
                        "artifact_class",
                        "store_id",
                        "segment_count",
                        "retention_expiry",
                    ],
                    *[
                        [
                            s.set_label,
                            s.artifact_class,
                            s.store_id,
                            s.segments,
                            s.retention_expiry,
                        ]
                        for s in scenario.sets
                    ],
                ],
                preview="Gross segment counts by set; status and reservations live in the set register.",
            ),
            asset(
                "backup/set-status-register.csv",
                kind="verification_register",
                title="Segment-set status register (checksum, reservation, durability notes)",
                source="backup_export",
                media_type=CSV,
                content="set_label,artifact_class,store_id,status,status_reason,reserved_for_ticket,register_note\n"
                + "".join(
                    f"{s.set_label},{s.artifact_class},{s.store_id},{s.status},{s.reason or ''},{s.reserved_for or ''},{s.register_note}\n"
                    for s in scenario.sets
                ),
                preview="Which sets are checksum-failed, reserved, or flagged.",
            ),
            asset(
                "jobs/job-schedule-and-runs.csv",
                kind="job_schedule",
                title="Scheduler jobs and recent runs",
                source="scheduler_export",
                media_type=CSV,
                content="run_id,job_id,job_name,kind,schedule,started_at,finished_at,status,exit_code,summary\n"
                + "".join(
                    f'{r.run_id},{r.job_id},{next(j.name for j in scenario.jobs if j.job_id == r.job_id)},{next(j.kind for j in scenario.jobs if j.job_id == r.job_id)},{next(j.schedule for j in scenario.jobs if j.job_id == r.job_id)},{r.started_at},{r.finished_at},{r.status},{r.exit_code},"{r.summary}"\n'
                    for r in scenario.job_runs
                ),
                preview="The cron / CI schedule and the runs that triggered the case.",
            ),
            asset(
                "buildfarm/runner-calendar-2026-04-13.xlsx",
                kind="runner_calendar",
                title="Runner window calendar, three weeks from 2026-04-13",
                source="buildfarm_workbook",
                media_type=XLSX,
                rows=[
                    [
                        "service_date",
                        "runner_id",
                        "session",
                        "start",
                        "end",
                        "status",
                        "hold_reason",
                    ],
                    *[
                        [
                            day,
                            runner,
                            session,
                            WINDOW_TIMES[session][0],
                            WINDOW_TIMES[session][1],
                            entry["status"],
                            entry["hold_reason"] or "",
                        ]
                        for (day, runner, session), entry in sorted(grid.items())
                    ],
                ],
                preview="Every runner window with free / busy / protected / blocked status.",
            ),
            asset(
                "buildfarm/runner-roster-and-capabilities.csv",
                kind="runner_roster",
                title="Runner roster and isolation capability",
                source="buildfarm_export",
                media_type=CSV,
                content=scoped_csv(
                    "runner_id,name,status,isolation_capable,note\n"
                    + "".join(
                        f"{r.runner_id},{r.name},{r.status},{'yes' if r.isolation_capable else 'no'},{r.note or ''}\n"
                        for r in scenario.runners
                    ),
                    task_id=scenario.task_id,
                    case_reference=case,
                ),
                preview="Runner status and isolation capability flags for the week.",
            ),
            asset(
                f"vendor/retrieval-confirmation-{scenario.confirmation.reference}.pdf",
                kind="vendor_confirmation",
                title=f"Vault retrieval confirmation {scenario.confirmation.reference}",
                source="email_attachment",
                media_type=PDF,
                content=_confirmation_text(scenario),
                preview="Standard and expedited retrieval-ready dates, fee, and validity.",
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
                    message_id=f"{scenario.email.message_id}@ridgeline.example",
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
                preview="Team chat with set, window, and authority remarks.",
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
                title="Starting-state export (reservations, restores, copies)",
                source="buildfarm_export",
                media_type=JSON,
                content=json.dumps(
                    {
                        "case_reference": case,
                        "as_of": AS_OF,
                        "reservations": [
                            {
                                "reservation_id": r.reservation_id,
                                "service_id": r.service_id,
                                "ticket_id": r.ticket_id,
                                "runner_id": r.runner_id,
                                "start": r.start,
                                "end": r.end,
                                "status": r.status,
                            }
                            for r in scenario.reservations
                        ],
                        "restore_jobs": [
                            {"restore_id": "RST-3400", "status": "RECEIVED"}
                        ],
                        "store_copies": [
                            dict(row) for row in scenario.seed.get("copies", ())
                        ],
                        "note": "Snapshot before any action; row order does not indicate applicability.",
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                preview="Snapshot of farm and catalog state before any action.",
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
            content = (
                scoped_csv(doc.content, task_id=scenario.task_id, case_reference=case)
                if doc.kind == "margin_policy"
                else doc.content
            )
            assets.append(
                asset(
                    doc.path,
                    kind=doc.kind,
                    title=doc.title,
                    source="drive",
                    media_type=doc.media_type,
                    content=content,
                    preview=doc.title,
                )
            )
    assets.extend(
        quality_support_assets(
            task_id=scenario.task_id,
            ordinal=scenario.ordinal,
            case_reference=case,
            family_slug=FAMILY_SLUG,
            family_name="HostOps",
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
        return "Platform Operations/Runbooks"
    if record["kind"] == "policy_superseded":
        return "Platform Operations/Runbooks/Archive"
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
                "modified_time": "2026-04-10T17:30:00",
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
        option
        for option in scenario.options
        if option.approval == "ADDITIONAL_APPROVAL_REQUIRED"
    )
    accelerated = scenario.options[1]
    return (
        {
            "id": "authoritative_identity",
            "sources": ["cmdb", "messages"],
            "statement": f"{scenario.case_reference}: {notes['identity']}; the effective revision is {scenario.revision}.",
            "rubric": f"Located {scenario.item} using immutable identifiers and preserved effective revision {scenario.revision}: {notes['identity']}.",
        },
        {
            "id": "effective_requirement",
            "sources": ["releases", "drive"],
            "statement": f"The effective ticket and runbook establish {labels.scope_label} = {numbers['scope']} {labels.unit}: {notes['requirement']}. The control date is {scenario.business_need} ({scenario.business_need_reason}).",
            "rubric": f"Applied the effective ticket and runbook to establish {numbers['scope']} {labels.unit} for {labels.scope_label}, with control date {scenario.business_need}.",
        },
        {
            "id": "eligible_coverage",
            "sources": ["backup", "buildfarm", "drive"],
            "statement": f"{notes['coverage']}; eligibility requires netting the exclusions rather than trusting a header total.",
            "rubric": f"Reconciled {numbers['observed']} observed less {numbers['excluded']} excluded to {numbers['eligible']} supported {labels.unit} for {labels.eligible_label}.",
        },
        {
            "id": "conditional_external_recovery",
            "sources": ["vendor", "messages"],
            "statement": f"{labels.external_label}: {notes['external']}; a vendor confirmation alone proves neither eligibility nor approval.",
            "rubric": f"Used the independently confirmed {scenario.expedited_readiness} expedited readiness input for {accelerated.id}, then separately derived its {accelerated.completion} operating outcome under {labels.constraint_label} instead of treating a vendor promise as authorization or a completion date.",
        },
        {
            "id": "finite_capacity",
            "sources": ["buildfarm", "drive"],
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
    service = scenario.service
    ticket = scenario.primary_ticket
    cls = scenario.primary_class
    runbook_id = file_ids["runbook/platform-operations-runbook.md"]
    approval_id = file_ids[f"approvals/approval-{scenario.approval.approval_id}.json"]
    ticket_file_id = file_ids[f"releases/ticket-{ticket.ticket_id}.json"]
    first_set = next(item for item in scenario.sets if item.artifact_class == cls.code)
    runs = in_scope_runs(scenario)
    if scenario.mode == "quantity":
        ticket_list_args = {"artifact_class": cls.code, "status": "open"}
        ticket_list_expected = {
            "tickets": [{"ticket_id": t.ticket_id} for _, t in runs]
        }
        reservation_args = {
            "start_date": scenario.numbers["in_scope_window"][0],
            "end_date": scenario.numbers["in_scope_window"][1],
            "status": "booked",
        }
        reservation_expected = {
            "reservations": [{"id": r.reservation_id} for r, _ in runs]
        }
    else:
        ticket_list_args = {"service_id": service.service_id}
        ticket_list_expected = {"tickets": [{"ticket_id": ticket.ticket_id}]}
        own = [r for r in scenario.reservations if r.service_id == service.service_id]
        reservation_args = {"service_id": service.service_id}
        reservation_expected = (
            {"reservations": [{"id": r.reservation_id} for r in own]}
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
            f"Resolved service code {service.code} to the immutable service record through an identifier search rather than a name match against a similarly named service.",
            "cmdb.services.search",
            {"identifier": service.code},
            {"services": [{"service_id": service.service_id}]},
        ),
        _investigation(
            4,
            "investigation.scope",
            f"Listed the {case} case folder on the shared drive and identified the approval record and the ticket export by immutable file id.",
            "drive.files.list",
            {"q": case},
            {"files": [{"id": approval_id}, {"id": ticket_file_id}]},
        ),
        _investigation(
            5,
            "investigation.scope",
            "Listed the runbook folder and distinguished the effective v4 runbook from the superseded 2024 edition by file identity, not title.",
            "drive.files.list",
            {"q": "runbook"},
            {"files": [{"id": runbook_id}]},
        ),
        _investigation(
            6,
            "investigation.requirements",
            f"Read the active ticket {ticket.ticket_id}: payload basis, units in scope, and run durations.",
            "releases.tickets.get",
            {"ticket_id": ticket.ticket_id},
            {"ticket_id": ticket.ticket_id, "status": ticket.status},
        ),
        _investigation(
            7,
            "investigation.requirements",
            f"Read the current final payload metering for {service.service_id} ({service.meter_metric}) and ignored the stale historical metering.",
            "cmdb.meterings.list",
            {"service_id": service.service_id, "metric": service.meter_metric},
            {"meterings": [{"metering_id": service.metering_id}]},
        ),
        _investigation(
            8,
            "investigation.requirements",
            "Exported the effective v4 runbook for the sizing, minimum-retention, staging, window, and authority rules; did not apply the superseded 2024 edition.",
            "drive.files.export",
            {"file_id": runbook_id},
            {"file_id": runbook_id},
        ),
        _investigation(
            9,
            "investigation.requirements",
            f"Read the artifact class record for {cls.code}: segment size and minimum remaining retention.",
            "backup.classes.get",
            {"artifact_class": cls.code},
            {"artifact_class": cls.code},
        ),
        _investigation(
            10,
            "investigation.requirements",
            f"Listed the tickets that define the requirement ({', '.join(sorted({t.ticket_id for _, t in runs}) if runs else [ticket.ticket_id])}) and excluded superseded or out-of-scope tickets.",
            "releases.tickets.list",
            ticket_list_args,
            ticket_list_expected,
        ),
        _investigation(
            11,
            "investigation.requirements",
            f"Read the scheduler's run history for {scenario.run_query.get('job_id')} to ground what actually ran, what failed, and what the schedule does next.",
            "jobs.runs.list",
            dict(scenario.run_query),
            dict(scenario.run_expected),
        ),
        _investigation(
            12,
            "investigation.constraints",
            f"Listed every {cls.code} segment set with count, retention expiry, checksum status, and reservations before netting the coverage.",
            "backup.sets.list",
            {"artifact_class": cls.code},
            {"sets": [{"set_id": first_set.set_id}]},
        ),
        _investigation(
            13,
            "investigation.constraints",
            f"Read the runner window calendar for {scenario.windows_query['start_date']} onward to find the first free window that displaces no protected or blocked block.",
            "buildfarm.windows.list",
            dict(scenario.windows_query),
            {"windows": [{"id": scenario.selected_window_id}]},
        ),
        _investigation(
            14,
            "investigation.constraints",
            f"Read the vendor retrieval confirmation {scenario.confirmation.confirmation_id} for the independently confirmed standard and expedited ready dates and the expedite fee.",
            "vendor.confirmations.get",
            {"confirmation_id": scenario.confirmation.confirmation_id},
            {
                "confirmation_id": scenario.confirmation.confirmation_id,
                "standard_ready_date": scenario.confirmation.standard_date,
            },
        ),
        _investigation(
            15,
            "investigation.authority",
            f"Read approval {scenario.approval.approval_id} for its exact scope: record, quantity, vendor, fee allowance, and what it does not cover.",
            "approvals.get",
            {"approval_id": scenario.approval.approval_id},
            {"approval_id": scenario.approval.approval_id},
        ),
        _investigation(
            16,
            "investigation.authority",
            "Exported the approval record on the drive and confirmed it matches the workflow record before relying on it.",
            "drive.files.export",
            {"file_id": approval_id},
            {"file_id": approval_id},
        ),
        _investigation(
            17,
            "investigation.erp_correlation",
            f"Read the request message {scenario.email.message_id} for the documented control date and the business need in the requester's words.",
            "messages.get",
            {"message_id": scenario.email.message_id},
            {"id": scenario.email.message_id},
        ),
        _investigation(
            18,
            "investigation.erp_correlation",
            f"Read the team chat thread {scenario.chat.thread_id} for set, window, and authority remarks that qualify the system records.",
            "chat.threads.get",
            {"thread_id": scenario.chat.thread_id},
            {"thread_id": scenario.chat.thread_id},
        ),
        _investigation(
            19,
            "investigation.erp_correlation",
            "Correlated the farm reservations that fix the schedule scope by immutable id.",
            "buildfarm.reservations.list",
            reservation_args,
            reservation_expected,
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
    order = [2, 17, 3, 10, 6, 7, 11, 4, 5, 8, 9, 12, 19, 13, 14, 15, 16, 18]
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
                "related_ticket_id": scenario.primary_ticket.ticket_id,
                "related_service_id": scenario.service.service_id,
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
                    scenario.service.code,
                    scenario.primary_ticket.ticket_id,
                ]
            ],
            "weight": 1.5,
        },
        {
            "id": "containment_01",
            "milestone_id": "containment.scope",
            "description": f"Made exactly two state changes for {scenario.case_reference}: the primary change and the stakeholder draft; no additional restore, copy, or booking.",
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
        correlated_systems=[
            "cmdb",
            "releases",
            "jobs",
            "backup",
            "buildfarm",
            "messages",
            "chat",
        ],
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
            "cmdb": {
                "service_code": scenario.service.code,
                "service_search": {
                    "tool": "cmdb.services.search",
                    "arguments": {"identifier": scenario.service.code},
                },
            },
            "messages": {"search_query": scenario.case_reference},
            "drive": {
                "case_folder_query": scenario.case_reference,
                "runbook_query": "runbook",
            },
            "backup": {
                "artifact_class": scenario.primary_class.code,
                "stores": sorted({item.store_id for item in scenario.sets}),
            },
            "buildfarm": {
                "pool": "release-pool",
                "calendar_window": scenario.windows_query,
            },
            "jobs": {"job_id": scenario.run_query.get("job_id")},
            "vendor": {"confirmation_id": scenario.confirmation.confirmation_id},
            "approvals": {"approval_id": scenario.approval.approval_id},
            "chat": {"thread_id": scenario.chat.thread_id},
        },
        "starting_records": [
            *[
                {
                    "system": "buildfarm",
                    "resource_type": "Reservation",
                    "resource_id": r.reservation_id,
                    "status": r.status,
                }
                for r in scenario.reservations
            ],
            {
                "system": "backup",
                "resource_type": "RestoreJob",
                "resource_id": "RST-3400",
                "status": "RECEIVED",
            },
            *[
                {
                    "system": "backup",
                    "resource_type": "StoreCopy",
                    "resource_id": row["copy_id"],
                    "status": row["status"],
                }
                for row in scenario.seed.get("copies", ())
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
    "first_window_on_or_after",
    "verify_numbers",
]
