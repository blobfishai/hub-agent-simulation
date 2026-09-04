"""Assemble SecOps tasks: seed tables, scattered evidence, decision model, sealed contract.

Every declared number in a scenario is recomputed from the seeded world
(credential-object grants, responder calendar, tickets, inventory snapshots,
vendor invalidation confirmations) and the build fails on any disagreement,
so the answer contract can never drift from the data the agent actually sees.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from ...engine.assets import CSV, EML, JSON, MARKDOWN, PDF, XLSX, YAML, asset, eml, yaml_lines
from ...engine.catalog import answer_checks, build_rubric_milestones, milestone_descriptions, sequence_signature
from ...engine.decision import DecisionInputs, answer_schema, build_decision_model
from ...engine.families import CONTEXT_TOOL, SUBMIT_TOOL
from ...engine.grading_contracts import fact_text_contract
from ...engine.quality_assets import quality_support_assets, quality_support_investigations, scoped_csv, scoped_markdown
from . import tools as sec_tools
from .policy import SUPERSEDED_PLAYBOOK, effective_playbook
from .scenarios import scenarios
from .specs import (
    ANALYSTS,
    AS_OF,
    OBJECT_UNIT,
    ORGANIZATION,
    USERS,
    VENDORS,
    WINDOW_HOURS,
    WINDOW_TIMES,
    GrantSet,
    Identity,
    Scenario,
    Ticket,
    business_days,
    next_business_day,
    ticket_unit_objects,
    window_id,
)

BENCHMARK = "HubBench"
FAMILY_SLUG = "secops"
FAMILY_VERSION = "1.0.1"
PRIMARY_KEYS = {
    "bridges": "bridge_id",
    "invalidation_orders": "order_id",
    "revocations": "revocation_id",
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
CASE_FOLDER = "Security Operations/Cases/{case}"
PLAYBOOK_QUERY = "playbook"
OPEN_SOURCE_ANCHORS = (
    {
        "name": "CyberDefense-Bench",
        "harbor_dataset": "polyvorlabs/cyberdefense-bench",
        "harbor_url": "https://hub.harborframework.com/datasets/polyvorlabs/cyberdefense-bench/latest",
        "upstream_url": "https://github.com/polyvorlabs/cyberdefense-bench",
        "license": "per the upstream repository; nothing from it is redistributed here",
        "evaluation_shape": "defensive security-operations tasks with deterministic end-state verification",
    },
    {
        "name": "Terminal-Bench 2.1 systems security",
        "harbor_dataset": "NovitaAI/tb21-systems-security",
        "harbor_url": "https://hub.harborframework.com/datasets/NovitaAI/tb21-systems-security/latest",
        "upstream_url": "https://github.com/harbor-framework/terminal-bench",
        "license": "Apache-2.0",
        "evaluation_shape": "systems-security hardening and triage tasks graded on persisted state",
    },
    {
        "name": "binary-audit",
        "harbor_dataset": "binary-audit/binary-audit",
        "harbor_url": "https://hub.harborframework.com/datasets/binary-audit/binary-audit/latest",
        "upstream_url": "https://github.com/binary-audit/binary-audit",
        "license": "per the upstream repository; nothing from it is redistributed here",
        "evaluation_shape": "audit-style security analysis tasks with exact graded findings",
    },
)
PLAN_SELECTED_OPTIONS = {
    "standard_invalidation_plan": "standard",
    "expedite_vendor_invalidation": "expedited",
}


# --------------------------------------------------------------------------- #
# Derivations and cross-checks
# --------------------------------------------------------------------------- #


def _identities_by_id(scenario: Scenario) -> dict[str, Identity]:
    return {item.identity_id: item for item in (scenario.identity, *scenario.other_identities)}


def _tickets_by_id(scenario: Scenario) -> dict[str, Ticket]:
    return {ticket.ticket_id: ticket for ticket in scenario.tickets}


def ticket_objects(scenario: Scenario, ticket: Ticket) -> int:
    return ticket_unit_objects(ticket, _identities_by_id(scenario)) * ticket.units_in_scope


def _set_excluded(item: GrantSet) -> bool:
    return item.status != "ACTIVE" or item.deferred_for is not None or item.register_excluded


def calendar(scenario: Scenario) -> dict[tuple[str, str, str], dict[str, Any]]:
    overrides = {(item.day, item.responder, item.session): item for item in scenario.windows}
    grid: dict[tuple[str, str, str], dict[str, Any]] = {}
    for day in business_days():
        for responder in scenario.responders:
            for session in ("AM", "PM"):
                key = (day, responder.responder_id, session)
                override = overrides.get(key)
                if override is None:
                    entry = {"status": "busy", "hold_reason": "scheduled detection-engineering load", "bridge_id": None}
                elif override.status == "busy" and override.reason.startswith("BRG-"):
                    entry = {"status": "busy", "hold_reason": "bridge", "bridge_id": override.reason}
                elif override.status == "free":
                    entry = {"status": "free", "hold_reason": None, "bridge_id": None}
                else:
                    entry = {"status": override.status, "hold_reason": override.reason or override.status, "bridge_id": None}
                grid[key] = entry
    return grid


def first_window_on_or_after(scenario: Scenario, start: str, windows_needed: int, responders: list[str]) -> tuple[str, str, str] | None:
    grid = calendar(scenario)
    active = {item.responder_id for item in scenario.responders if item.status == "ACTIVE"}
    for day in business_days():
        if day < start:
            continue
        for responder in responders:
            if responder not in active:
                continue
            free = [session for session in ("AM", "PM") if grid[(day, responder, session)]["status"] == "free"]
            if windows_needed == 1 and free:
                return day, responder, free[0]
            if windows_needed == 2 and len(free) == 2:
                return day, responder, "AM+PM"
    return None


def in_scope_reviews(scenario: Scenario) -> list[tuple[Any, Ticket]]:
    window = scenario.numbers.get("in_scope_window")
    if not window:
        return []
    tickets = _tickets_by_id(scenario)
    code = scenario.primary_class.code
    selected = []
    for bridge in scenario.bridges:
        if bridge.status != "booked" or bridge.start is None:
            continue
        ticket = tickets.get(bridge.ticket_id or "")
        if ticket is None or ticket.credential_class != code:
            continue
        if window[0] <= bridge.start[:10] <= window[1]:
            selected.append((bridge, ticket))
    return sorted(selected, key=lambda item: (item[0].start, item[0].bridge_id))


def verify_numbers(scenario: Scenario) -> None:
    numbers = scenario.numbers
    extra = scenario.extra_answer
    cls = scenario.primary_class
    identities = _identities_by_id(scenario)
    problems: list[str] = []

    def check(label: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            problems.append(f"{label}: computed {actual!r} but scenario declares {expected!r}")

    scoped_sets = [item for item in scenario.sets if item.credential_class == cls.code and item.system == numbers["coverage_location"]]
    if scenario.mode in {"plan", "quantity"}:
        observed = sum(item.objects for item in scoped_sets)
        excluded = sum(item.objects for item in scoped_sets if _set_excluded(item))
        check("observed", observed, numbers["observed"])
        check("excluded", excluded, numbers["excluded"])
        check("eligible", observed - excluded, numbers["eligible"])
    if scenario.mode == "plan":
        ticket = scenario.primary_ticket
        per_unit = ticket_unit_objects(ticket, identities)
        check("metered_live_objects", per_unit, extra["metered_live_objects"])
        check("principals_in_scope", ticket.units_in_scope, extra["principals_in_scope"])
        check("scope", per_unit * ticket.units_in_scope, numbers["scope"])
    if scenario.mode == "quantity":
        reviews = in_scope_reviews(scenario)
        check("scheduled_reviews", len(reviews), extra["scheduled_reviews"])
        check("scope", sum(ticket_objects(scenario, ticket) for _, ticket in reviews), numbers["scope"])
        first = reviews[0][0] if reviews else None
        if first is not None:
            session = "AM" if first.start[11:] < WINDOW_TIMES["PM"][0] else "PM"
            check("first_review_window", f"{first.responder_id}/{first.start[:10]}/{session}", extra["first_review_window"])
            check("business_need", first.start[:10], scenario.business_need)
        metered = [ticket for _, ticket in reviews if ticket.unit_basis == "metered"]
        if metered and "metered_live_objects" in extra:
            check("metered_live_objects", identities[metered[0].identity_id].meter_value, extra["metered_live_objects"])
        if "margin" in numbers:
            check("transaction_quantity", numbers["gap"] + numbers["margin"], numbers["transaction_quantity"])
            check("margin_objects", numbers["margin"], extra["margin_objects"])
        if "receiving_usable" in numbers:
            receiving = [
                item
                for item in scenario.sets
                if item.credential_class == cls.code and item.system == numbers["receiving_system"] and not _set_excluded(item)
            ]
            check("receiving_usable", sum(item.objects for item in receiving), numbers["receiving_usable"])
            check("receiving_scope_usable", numbers["receiving_usable"], extra["receiving_scope_usable"])
            check("transaction_quantity", min(numbers["scope"] - numbers["receiving_usable"], numbers["eligible"]), numbers["transaction_quantity"])
    if scenario.mode == "schedule":
        grid = calendar(scenario)
        start, end = numbers["capacity_window"]
        days = [day for day in business_days() if start <= day <= end]
        keys = [(day, responder, session) for day in days for responder in numbers["eligible_responders"] for session in ("AM", "PM")]
        candidate = len(keys) * WINDOW_HOURS
        free = sum(1 for key in keys if grid[key]["status"] == "free")
        check("candidate", candidate, numbers["observed"])
        check("excluded", candidate - free * WINDOW_HOURS, numbers["excluded"])
        check("eligible", free * WINDOW_HOURS, numbers["eligible"])
        affected = [ticket for ticket in scenario.tickets if ticket.credential_class == cls.code]
        if numbers.get("scope_source") == "primary":
            hours = (scenario.primary_ticket.triage_minutes + scenario.primary_ticket.confirm_minutes) / 60
        else:
            hours = sum((ticket.triage_minutes + ticket.confirm_minutes) / 60 for ticket in affected)
        check("scope", int(hours), numbers["scope"])
        usable = sum(item.objects for item in scoped_sets if not _set_excluded(item))
        if "register_objects_usable" in extra:
            check("register_objects_usable", usable, extra["register_objects_usable"])
        if numbers.get("scope_source") == "primary":
            required_objects = ticket_objects(scenario, scenario.primary_ticket)
        else:
            required_objects = sum(ticket_objects(scenario, ticket) for ticket in affected)
        if "register_objects_required" in extra:
            check("register_objects_required", required_objects, extra["register_objects_required"])
        if "windows_required" in extra:
            check("windows_required", int(numbers["sessions_needed"]), extra["windows_required"])
        if "requested_day" in extra:
            check("requested_day", numbers["capacity_window"][0], extra["requested_day"])
        if "affected_bridges" in extra:
            tickets = _tickets_by_id(scenario)
            stranded = [item for item in scenario.bridges if tickets.get(item.ticket_id or "") in affected]
            check("affected_bridges", len(stranded), extra["affected_bridges"])
        if "reviews_per_window" in extra:
            check("reviews_per_window", extra["affected_bridges"] // extra["windows_required"], extra["reviews_per_window"])
    if "anomalous_sessions" in extra:
        check(
            "anomalous_sessions",
            sum(1 for item in scenario.sessions if item.identity_id == scenario.identity.identity_id and item.risk == "high"),
            extra["anomalous_sessions"],
        )
    if "owner_held_objects" in extra:
        check("owner_held_objects", sum(item.objects for item in scoped_sets if item.deferred_for is not None), extra["owner_held_objects"])
    gap = max(0, numbers["scope"] - numbers["eligible"])
    check("gap", gap, numbers["gap"])
    check("standard_readiness", next_business_day(scenario.confirmation.standard_date), scenario.standard_readiness)
    check("expedited_readiness", next_business_day(scenario.confirmation.expedited_date), scenario.expedited_readiness)
    windows_needed = 2 if scenario.mode == "schedule" and numbers.get("full_day_needed") else 1
    slot_responders = numbers["eligible_responders"]
    standard_slot = first_window_on_or_after(scenario, scenario.standard_readiness, windows_needed, slot_responders)
    expedited_slot = first_window_on_or_after(scenario, scenario.expedited_readiness, windows_needed, slot_responders)
    check("standard_slot_date", standard_slot[0] if standard_slot else None, numbers["standard_slot_date"])
    check("expedited_slot_date", expedited_slot[0] if expedited_slot else None, numbers["expedited_slot_date"])
    if scenario.mode == "plan":
        check("earliest_qualified_window", numbers["standard_slot_date"], extra["earliest_qualified_window"])
        expedited_option = scenario.options[1]
        check("expedited option date", expedited_slot[0] if expedited_slot else None, expedited_option.completion)
        check(
            "expedite_days_saved",
            (date.fromisoformat(numbers["standard_slot_date"]) - date.fromisoformat(numbers["expedited_slot_date"])).days,
            extra["expedite_days_saved"],
        )
        selected = next(option for option in scenario.options if option.recommended)
        if selected.id in PLAN_SELECTED_OPTIONS:
            readiness = scenario.standard_readiness if PLAN_SELECTED_OPTIONS[selected.id] == "standard" else scenario.expedited_readiness
            slot = first_window_on_or_after(scenario, readiness, 1, slot_responders)
            if slot is not None:
                check("selected_responder_window", f"{slot[1]}/{slot[0]}/{slot[2]}", extra["selected_responder_window"])
                check("selected completion", slot[0], selected.completion)
    if scenario.mode == "schedule":
        selected_date = next(option for option in scenario.options if option.recommended).completion
        if numbers.get("full_day_needed"):
            full_day = first_window_on_or_after(scenario, numbers["capacity_window"][0], 2, numbers["eligible_responders"])
            check("selected_resource", f"{full_day[1]}/{full_day[0]}/{full_day[2]}" if full_day else None, numbers["selected_resource"])
            check("selected completion", full_day[0] if full_day else None, selected_date)
        else:
            grid = calendar(scenario)
            free_windows = [
                key
                for key in sorted(grid)
                if key[1] in numbers["eligible_responders"] and grid[key]["status"] == "free" and key[0] >= numbers["capacity_window"][0]
            ]
            check("selected_resource", f"{free_windows[0][1]}/{free_windows[0][0]}/{free_windows[0][2]}" if free_windows else None, numbers["selected_resource"])
            sessions_needed = int(numbers["sessions_needed"])
            check("selected completion", free_windows[sessions_needed - 1][0] if len(free_windows) >= sessions_needed else None, selected_date)
    if scenario.selected_window_id not in {window_id(responder, day, session) for (day, responder, session) in calendar(scenario)}:
        problems.append(f"selected window {scenario.selected_window_id} is not on the calendar")
    if scenario.alert.rule_id not in {rule.rule_id for rule in scenario.rules}:
        problems.append(f"alert {scenario.alert.alert_id} names an unknown rule")
    if not any(event.alert_id == scenario.alert.alert_id for event in scenario.events):
        problems.append(f"alert {scenario.alert.alert_id} has no correlated events")
    if scenario.primary_ticket.alert_id != scenario.alert.alert_id:
        problems.append("the primary ticket does not reference the primary alert")
    if problems:
        raise ValueError(f"{scenario.task_id} scenario data disagrees with its declared numbers:\n  " + "\n  ".join(problems))


# --------------------------------------------------------------------------- #
# Seed tables
# --------------------------------------------------------------------------- #


def _inventory(identity: Identity, *, stale: bool) -> list[dict[str, Any]]:
    rows = [
        {
            "inventory_id": identity.inventory_id,
            "identity_id": identity.identity_id,
            "metric": identity.meter_metric,
            "value": identity.meter_value,
            "unit": OBJECT_UNIT,
            "measured_at": identity.meter_date,
            "status": "final",
        },
    ]
    if stale:
        rows.append(
            {
                "inventory_id": identity.stale_inventory_id,
                "identity_id": identity.identity_id,
                "metric": identity.meter_metric,
                "value": identity.stale_value,
                "unit": OBJECT_UNIT,
                "measured_at": identity.stale_date,
                "status": "final",
            }
        )
    return rows


def seed_tables(scenario: Scenario, drive_files: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grid = calendar(scenario)
    windows = [
        {
            "window_id": window_id(responder, day, session),
            "responder_id": responder,
            "service_date": day,
            "session": session,
            "start_time": WINDOW_TIMES[session][0],
            "end_time": WINDOW_TIMES[session][1],
            **entry,
        }
        for (day, responder, session), entry in sorted(grid.items())
    ]
    return {
        "users": [dict(row) for row in USERS],
        "analysts": [dict(row) for row in ANALYSTS],
        "identities": [
            {
                "identity_id": i.identity_id,
                "username": i.username,
                "display_name": i.display_name,
                "kind": i.kind,
                "tier": i.tier,
                "owner_team": i.owner_team,
                "owner_analyst_id": i.owner_id,
            }
            for i in (scenario.identity, *scenario.other_identities)
        ],
        "grant_inventory": [row for index, i in enumerate((scenario.identity, *scenario.other_identities)) for row in _inventory(i, stale=index == 0)],
        "credential_classes": [
            {
                "credential_class": c.code,
                "display": c.display,
                "object_kind": c.object_kind,
                "revocation_channel": c.revocation_channel,
                "privileged": int(c.privileged),
                "interchangeable_with": c.interchangeable_with,
            }
            for c in scenario.classes
        ],
        "containment_tiers": [
            {
                "tier_code": t.code,
                "name": t.name,
                "version": t.version,
                "immediate_revocation_allowed": int(t.immediate_allowed),
                "owner_confirmation_required": int(t.owner_confirmation_required),
                "authority_level": t.authority_level,
                "sla_hours": t.sla_hours,
                "note": t.note or None,
            }
            for t in scenario.tiers
        ],
        "tickets": [
            {
                "ticket_id": t.ticket_id,
                "identity_id": t.identity_id,
                "alert_id": t.alert_id or None,
                "tier_code": t.tier_code,
                "credential_class": t.credential_class,
                "unit_kind": t.unit_kind,
                "unit_basis": t.unit_basis,
                "unit_objects": t.unit_objects,
                "units_in_scope": t.units_in_scope,
                "scope_note": t.scope_note,
                "triage_minutes": t.triage_minutes,
                "confirm_minutes": t.confirm_minutes,
                "status": t.status,
                "kind": t.kind,
                "priority": t.priority,
                "opened_at": t.opened_at,
                "requested_by": t.requested_by,
                "note": t.note or None,
            }
            for t in scenario.tickets
        ],
        "grant_sets": [
            {
                "grant_id": s.grant_id,
                "credential_class": s.credential_class,
                "grant_label": s.grant_label,
                "identity_id": s.identity_id,
                "system": s.system,
                "object_count": s.objects,
                "expires_on": s.expires_on,
                "status": s.status,
                "status_reason": s.reason,
                "deferred_for_ticket": s.deferred_for,
                "register_flag": s.register_note if s.register_excluded else None,
            }
            for s in scenario.sets
        ],
        "detection_rules": [
            {"rule_id": r.rule_id, "name": r.name, "version": r.version, "status": r.status, "note": r.note or None}
            for r in scenario.rules
        ],
        "alerts": [
            {
                "alert_id": a.alert_id,
                "rule_id": a.rule_id,
                "identity_id": a.identity_id,
                "severity": a.severity,
                "status": a.status,
                "kind": a.kind,
                "opened_at": a.opened_at,
                "summary": a.summary,
            }
            for a in (scenario.alert, *scenario.other_alerts)
        ],
        "alert_events": [
            {"event_id": e.event_id, "alert_id": e.alert_id, "ts": e.ts, "kind": e.kind, "source_ip": e.source_ip, "detail": e.detail}
            for e in scenario.events
        ],
        "hosts": [
            {
                "host_id": h.host_id,
                "hostname": h.hostname,
                "identity_id": h.identity_id,
                "role": h.role,
                "isolation_state": h.isolation_state,
                "status": h.status,
                "note": h.note,
            }
            for h in scenario.hosts
        ],
        "detections": [
            {"detection_id": d.detection_id, "host_id": d.host_id, "tactic": d.tactic, "severity": d.severity, "status": d.status, "note": d.note or None}
            for d in scenario.detections
        ],
        "sessions": [
            {
                "session_id": s.session_id,
                "identity_id": s.identity_id,
                "source_ip": s.source_ip,
                "geo": s.geo,
                "device": s.device,
                "started_at": s.started_at,
                "risk": s.risk,
                "status": s.status,
            }
            for s in scenario.sessions
        ],
        "mfa_factors": [
            {
                "factor_id": f.factor_id,
                "identity_id": f.identity_id,
                "factor_type": f.factor_type,
                "status": f.status,
                "enrolled_at": f.enrolled_at,
                "last_used": f.last_used,
            }
            for f in scenario.factors
        ],
        "responders": [
            {
                "responder_id": r.responder_id,
                "pool": "soc-tier2",
                "name": r.name,
                "status": r.status,
                "tier2_capable": int(r.tier2_capable),
                "status_note": r.note,
            }
            for r in scenario.responders
        ],
        "oncall_windows": windows,
        "bridges": [
            {
                "bridge_id": b.bridge_id,
                "identity_id": b.identity_id,
                "ticket_id": b.ticket_id,
                "responder_id": b.responder_id,
                "start_time": b.start,
                "end_time": b.end,
                "status": b.status,
                "description": b.description,
                "revision": 1,
                "last_updated": "2026-06-05T12:00:00",
            }
            for b in scenario.bridges
        ],
        "idp_vendors": [dict(row) for row in VENDORS],
        "invalidation_confirmations": [
            {
                "confirmation_id": c.confirmation_id,
                "vendor_id": c.vendor_id,
                "credential_class": c.credential_class,
                "reference": c.reference,
                "objects_available": c.objects_available,
                "standard_ready_date": c.standard_date,
                "expedited_ready_date": c.expedited_date,
                "expedite_fee_usd": c.fee,
                "per_object_fee_usd": c.per_object_fee,
                "valid_until": c.valid_until,
                "status": c.status,
                "note": c.note,
            }
            for c in (scenario.confirmation, *scenario.other_confirmations)
        ],
        "invalidation_orders": [
            {
                "order_id": "IVO-3400",
                "vendor_id": "VND-HALYARD",
                "confirmation_id": None,
                "credential_class": scenario.classes[-1].code,
                "object_count": 2,
                "unit": OBJECT_UNIT,
                "service_option": "standard",
                "expected_ready_date": "2026-05-27",
                "status": "RECEIVED",
                "requested_by": "security_operations_coordinator",
                "created_at": "2026-05-22T09:30:00",
                "revision": 1,
            },
        ],
        "revocations": [
            {
                "revocation_id": "RVK-3400",
                "credential_class": scenario.classes[-1].code,
                "object_count": 1,
                "identity_id": scenario.identity.identity_id,
                "system": "iam",
                "effective_date": "2026-05-26",
                "status": "COMPLETED",
                "requested_by": "security_operations_coordinator",
                "created_at": "2026-05-26T10:15:00",
                "revision": 1,
            },
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
                "approval_id": "AP-SO-0090",
                "subject": "Quarterly hardware security-key replenishment standing order",
                "approver_id": "U-HAVILAND",
                "approver_role": "soc_manager",
                "status": "APPROVED",
                "granted_on": "2026-04-03",
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
                "sender": "beatriz.soriano@kestrelgrid.example",
                "recipients": "soc@kestrelgrid.example",
                "subject": "Weekly SOC operations note",
                "sent_at": "2026-06-05T08:00:00",
                "body": "On-call rota for the week of 2026-06-08 is posted. Responder qualification flags are on the shared drive roster; no changes to protected bridges.",
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
                "channel": "#soc-incidents",
                "title": "General — detection tuning and badge access",
                "messages_json": json.dumps(
                    [{"author": "Beatriz Soriano", "ts": "2026-06-04T16:40:00", "text": "Reminder: log every detection-rule version change in the change tracker."}]
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
    cls = next(c for c in scenario.classes if c.code == ticket.credential_class)
    row = {
        "ticket_id": ticket.ticket_id,
        "identity_id": ticket.identity_id,
        "alert_id": ticket.alert_id or None,
        "tier_code": ticket.tier_code,
        "credential_class": ticket.credential_class,
        "unit_kind": ticket.unit_kind,
        "unit_basis": ticket.unit_basis,
        "unit_objects": ticket.unit_objects,
        "units_in_scope": ticket.units_in_scope,
        "scope_note": ticket.scope_note,
        "triage_minutes": ticket.triage_minutes,
        "confirm_minutes": ticket.confirm_minutes,
        "status": ticket.status,
        "kind": ticket.kind,
        "priority": ticket.priority,
        "opened_at": ticket.opened_at,
        "requested_by": ticket.requested_by,
        "note": ticket.note,
    }
    rendered = sec_tools._ticket(row, {"display": cls.display, "object_kind": cls.object_kind})
    return json.dumps({"export": "servicedesk.tickets.get", "record": rendered}, indent=2, sort_keys=True) + "\n"


def _alert_json(scenario: Scenario, alert: Any) -> str:
    rule = next(r for r in scenario.rules if r.rule_id == alert.rule_id)
    row = {
        "alert_id": alert.alert_id,
        "rule_id": alert.rule_id,
        "identity_id": alert.identity_id,
        "severity": alert.severity,
        "status": alert.status,
        "kind": alert.kind,
        "opened_at": alert.opened_at,
        "summary": alert.summary,
    }
    rendered = sec_tools._alert(row, {"name": rule.name, "version": rule.version, "status": rule.status})
    return json.dumps({"export": "siem.alerts.get", "record": rendered}, indent=2, sort_keys=True) + "\n"


def _identity_summary_json(scenario: Scenario) -> str:
    identity = scenario.identity
    rendered = sec_tools._identity(
        {
            "identity_id": identity.identity_id,
            "username": identity.username,
            "display_name": identity.display_name,
            "kind": identity.kind,
            "tier": identity.tier,
            "owner_team": identity.owner_team,
            "owner_analyst_id": identity.owner_id,
        }
    )
    inventory = [sec_tools._inventory(row) for row in _inventory(identity, stale=True)]
    return json.dumps({"export": "iam.identities.get + iam.inventory.list", "identity": rendered, "inventory": inventory}, indent=2, sort_keys=True) + "\n"


def _confirmation_text(scenario: Scenario) -> str:
    c = scenario.confirmation
    vendor = next(row["name"] for row in VENDORS if row["vendor_id"] == c.vendor_id)
    account = next(row["account_number"] for row in VENDORS if row["vendor_id"] == c.vendor_id)
    return (
        f"{vendor}\nInvalidation confirmation {c.reference} (system reference {c.confirmation_id})\nCustomer: Kestrel Grid Utilities Security Operations, account {account}\n"
        f"Case reference: {scenario.case_reference}\nItem: {c.credential_class} — {scenario.primary_class.display}\nCredential objects available for this confirmation: {c.objects_available}\nPer-object invalidation fee: USD {c.per_object_fee:.2f}\n"
        f"Standard invalidation-job date: {c.standard_date}\nExpedited invalidation-job date: {c.expedited_date} (expedite fee USD {c.fee}, flat)\nValid until: {c.valid_until}\nNotes: {c.note}\n"
        "Invalidation is executed tenant-wide by the vendor; the register reflects it after the customer's verification on the next business day.\n"
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
            content=scoped_markdown(SUPERSEDED_PLAYBOOK, task_id=scenario.task_id, case_reference=scenario.case_reference),
            preview="2024 playbook retained for audit only; superseded by v5.",
        )
    if doc.kind == "decoy_ticket":
        ticket_id = doc.path.rsplit("/", 1)[-1].removeprefix("ticket-").removesuffix(".json")
        ticket = next(t for t in scenario.tickets if t.ticket_id == ticket_id)
        return asset(
            doc.path,
            kind=doc.kind,
            title=doc.title,
            source="servicedesk_export",
            media_type=JSON,
            content=_ticket_json(scenario, ticket),
            preview="A similarly named or out-of-scope ticket that must not drive the requirement.",
        )
    if doc.kind == "decoy_alert":
        alert_id = doc.path.rsplit("/", 1)[-1].removeprefix("alert-").removesuffix(".json")
        alert = next(a for a in scenario.other_alerts if a.alert_id == alert_id)
        return asset(
            doc.path,
            kind=doc.kind,
            title=doc.title,
            source="siem_export",
            media_type=JSON,
            content=_alert_json(scenario, alert),
            preview="A duplicate or retired-rule alert that must not drive the containment tier.",
        )
    if doc.media_type == XLSX:
        return asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=XLSX, rows=[list(row) for row in doc.rows or ()], preview=doc.title)
    content = scoped_csv(doc.content, task_id=scenario.task_id, case_reference=scenario.case_reference) if doc.kind == "margin_policy" else doc.content
    return asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=doc.media_type, content=content, preview=doc.title)


def build_assets(scenario: Scenario) -> list[dict[str, Any]]:
    case = scenario.case_reference
    grid = calendar(scenario)
    rules = {rule.rule_id: rule for rule in scenario.rules}
    assets: list[dict[str, Any]] = [
        asset(
            "playbooks/containment-playbook.md",
            kind="policy",
            title="Credential compromise containment playbook v5 (effective)",
            source="drive",
            media_type=MARKDOWN,
            content=scoped_markdown(effective_playbook(AS_OF), task_id=scenario.task_id, case_reference=case),
            preview="Sizing, revocable-object, responder-window, and authority rules in force.",
        ),
    ]
    if scenario.decoy_doc.kind != "policy_superseded":
        assets.append(
            asset(
                "playbooks/superseded-containment-playbook-2024.md",
                kind="policy_superseded",
                title="Credential compromise containment playbook 2024 (superseded)",
                source="drive",
                media_type=MARKDOWN,
                content=scoped_markdown(SUPERSEDED_PLAYBOOK, task_id=scenario.task_id, case_reference=case),
                preview="2024 playbook retained for audit only; superseded by v5.",
            )
        )
    assets.append(_decoy_asset(scenario))
    assets.extend(
        [
            asset(
                f"tickets/ticket-{scenario.primary_ticket.ticket_id}.json",
                kind="ticket_export",
                title=f"Ticket {scenario.primary_ticket.ticket_id} (service-desk export)",
                source="servicedesk_export",
                media_type=JSON,
                content=_ticket_json(scenario, scenario.primary_ticket),
                preview="The active ticket: object basis, scope, tier, and review durations.",
            ),
            asset(
                f"siem/alert-{scenario.alert.alert_id}.json",
                kind="alert_export",
                title=f"Alert {scenario.alert.alert_id} (SIEM export)",
                source="siem_export",
                media_type=JSON,
                content=_alert_json(scenario, scenario.alert),
                preview="The alert that opened the case with its detection rule version and status.",
            ),
            asset(
                f"iam/identity-{scenario.identity.username}-summary.json",
                kind="identity_summary",
                title=f"Identity {scenario.identity.username} summary with inventory snapshots (IAM export)",
                source="iam_export",
                media_type=JSON,
                content=_identity_summary_json(scenario),
                preview="Identity record plus current and historical credential-inventory snapshots.",
            ),
            asset(
                "iam/credential-class-catalog.csv",
                kind="class_catalog",
                title="Credential class catalog: object kinds and revocation channels",
                source="iam_export",
                media_type=CSV,
                content=scoped_csv(
                    "credential_class,display,object_kind,revocation_channel,privileged,interchangeable_with\n"
                    + "".join(
                        f"{c.code},{c.display},{c.object_kind},{c.revocation_channel},{'yes' if c.privileged else 'no'},{c.interchangeable_with or ''}\n"
                        for c in scenario.classes
                    ),
                    task_id=scenario.task_id,
                    case_reference=case,
                ),
                preview="Object kinds and the channel through which each class is revoked.",
            ),
            asset(
                "iam/credential-register-by-grant.xlsx",
                kind="holdings_workbook",
                title="Registered credential objects by grant (gross)",
                source="iam_workbook",
                media_type=XLSX,
                rows=[
                    ["grant_label", "credential_class", "identity_id", "system", "object_count", "expires_on"],
                    *[[s.grant_label, s.credential_class, s.identity_id, s.system, s.objects, s.expires_on] for s in scenario.sets],
                ],
                preview="Gross object counts by grant; status and owner deferrals live in the status register.",
            ),
            asset(
                "iam/grant-status-register.csv",
                kind="verification_register",
                title="Grant status register (expiry, rotation, revocation, owner deferrals)",
                source="iam_export",
                media_type=CSV,
                content="grant_label,credential_class,identity_id,system,status,status_reason,deferred_for_ticket,register_note\n"
                + "".join(
                    f"{s.grant_label},{s.credential_class},{s.identity_id},{s.system},{s.status},{s.reason or ''},{s.deferred_for or ''},{s.register_note}\n"
                    for s in scenario.sets
                ),
                preview="Which grants are expired, rotated, revoked, deferred to an owner, or flagged.",
            ),
            asset(
                f"siem/alert-{scenario.alert.alert_id}-events.csv",
                kind="alert_events",
                title=f"Correlated events and rule versions behind {scenario.alert.alert_id}",
                source="siem_export",
                media_type=CSV,
                content="event_id,alert_id,rule_id,rule_name,rule_version,rule_status,ts,kind,source_ip,detail\n"
                + "".join(
                    f'{e.event_id},{e.alert_id},{rules[a.rule_id].rule_id},{rules[a.rule_id].name},{rules[a.rule_id].version},{rules[a.rule_id].status},{e.ts},{e.kind},{e.source_ip},"{e.detail}"\n'
                    for e in scenario.events
                    for a in (scenario.alert, *scenario.other_alerts)
                    if a.alert_id == e.alert_id
                ),
                preview="The correlated events that triggered the case and the rule versions that fired.",
            ),
            asset(
                f"iam/sessions-and-factors-{scenario.identity.username}.csv",
                kind="session_register",
                title=f"Sessions and MFA factors for {scenario.identity.username}",
                source="iam_export",
                media_type=CSV,
                content="record_type,record_id,identity_id,source_ip_or_type,geo_or_status,device_or_enrolled,started_or_last_used,risk\n"
                + "".join(
                    f"session,{s.session_id},{s.identity_id},{s.source_ip},{s.geo},{s.device},{s.started_at},{s.risk}/{s.status}\n" for s in scenario.sessions
                )
                + "".join(
                    f"factor,{f.factor_id},{f.identity_id},{f.factor_type},{f.status},{f.enrolled_at},{f.last_used},\n" for f in scenario.factors
                ),
                preview="Live sessions with geo and device context, and the enrolled MFA factors.",
            ),
            asset(
                "edr/host-inventory-and-detections.csv",
                kind="edr_inventory",
                title="EDR host inventory and detections",
                source="edr_export",
                media_type=CSV,
                content="host_id,hostname,identity_id,role,isolation_state,status,detection_id,tactic,severity,detection_status,note\n"
                + "".join(
                    f"{h.host_id},{h.hostname},{h.identity_id or ''},{h.role},{h.isolation_state},{h.status},{d.detection_id},{d.tactic},{d.severity},{d.status},{d.note}\n"
                    for h in scenario.hosts
                    for d in scenario.detections
                    if d.host_id == h.host_id
                )
                + "".join(
                    f"{h.host_id},{h.hostname},{h.identity_id or ''},{h.role},{h.isolation_state},{h.status},,,,,{h.note or ''}\n"
                    for h in scenario.hosts
                    if not any(d.host_id == h.host_id for d in scenario.detections)
                ),
                preview="Hosts the identity used, their isolation state, and any detections.",
            ),
            asset(
                "oncall/responder-calendar-2026-06-08.xlsx",
                kind="responder_calendar",
                title="Responder window calendar, three weeks from 2026-06-08",
                source="oncall_workbook",
                media_type=XLSX,
                rows=[
                    ["service_date", "responder_id", "session", "start", "end", "status", "hold_reason"],
                    *[
                        [day, responder, session, WINDOW_TIMES[session][0], WINDOW_TIMES[session][1], entry["status"], entry["hold_reason"] or ""]
                        for (day, responder, session), entry in sorted(grid.items())
                    ],
                ],
                preview="Every responder window with free / busy / protected / blocked status.",
            ),
            asset(
                "oncall/responder-roster-and-qualification.csv",
                kind="responder_roster",
                title="Responder roster and Tier-2 qualification",
                source="oncall_export",
                media_type=CSV,
                content=scoped_csv(
                    "responder_id,name,status,tier2_capable,note\n"
                    + "".join(f"{r.responder_id},{r.name},{r.status},{'yes' if r.tier2_capable else 'no'},{r.note or ''}\n" for r in scenario.responders),
                    task_id=scenario.task_id,
                    case_reference=case,
                ),
                preview="Responder status and Tier-2 qualification flags for the week.",
            ),
            asset(
                f"idpvendor/invalidation-confirmation-{scenario.confirmation.reference}.pdf",
                kind="vendor_confirmation",
                title=f"Vendor invalidation confirmation {scenario.confirmation.reference}",
                source="email_attachment",
                media_type=PDF,
                content=_confirmation_text(scenario),
                preview="Standard and expedited invalidation-job dates, fee, and validity.",
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
                    message_id=f"{scenario.email.message_id}@kestrelgrid.example",
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
                        "messages": [{"author": a, "ts": t, "text": x} for a, t, x in scenario.chat.messages],
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                preview="SOC chat with grant, window, and authority remarks.",
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
                title="Starting-state export (bridges, invalidation orders, revocations)",
                source="oncall_export",
                media_type=JSON,
                content=json.dumps(
                    {
                        "case_reference": case,
                        "as_of": AS_OF,
                        "bridges": [
                            {
                                "bridge_id": b.bridge_id,
                                "identity_id": b.identity_id,
                                "ticket_id": b.ticket_id,
                                "responder_id": b.responder_id,
                                "start": b.start,
                                "end": b.end,
                                "status": b.status,
                            }
                            for b in scenario.bridges
                        ],
                        "invalidation_orders": [{"order_id": "IVO-3400", "status": "RECEIVED"}],
                        "revocations": [{"revocation_id": "RVK-3400", "status": "COMPLETED"}],
                        "note": "Snapshot before any action; row order does not indicate applicability.",
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                preview="Snapshot of bridge, order, and revocation state before any action.",
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
            family_name="SecOps",
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
    return assets


def _folder(scenario: Scenario, record: dict[str, Any]) -> str:
    if record["kind"] == "policy":
        return "Security Operations/Playbooks"
    if record["kind"] == "policy_superseded":
        return "Security Operations/Playbooks/Archive"
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
                "modified_time": "2026-06-05T17:30:00",
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
            "sources": ["iam", "siem", "messages"],
            "statement": f"{scenario.case_reference}: {notes['identity']}; the effective revision is {scenario.revision}.",
            "rubric": f"Located {scenario.item} using immutable identifiers and preserved effective revision {scenario.revision}: {notes['identity']}.",
        },
        {
            "id": "effective_requirement",
            "sources": ["servicedesk", "playbooks", "drive"],
            "statement": f"The effective ticket and playbook establish {labels.scope_label} = {numbers['scope']} {labels.unit}: {notes['requirement']}. The control date is {scenario.business_need} ({scenario.business_need_reason}).",
            "rubric": f"Applied the effective ticket and playbook to establish {numbers['scope']} {labels.unit} for {labels.scope_label}, with control date {scenario.business_need}.",
        },
        {
            "id": "eligible_coverage",
            "sources": ["iam", "oncall", "drive"],
            "statement": f"{notes['coverage']}; eligibility requires netting the exclusions rather than trusting a header total.",
            "rubric": f"Reconciled {numbers['observed']} observed less {numbers['excluded']} excluded to {numbers['eligible']} supported {labels.unit} for {labels.eligible_label}.",
        },
        {
            "id": "conditional_external_recovery",
            "sources": ["idpvendor", "messages"],
            "statement": f"{labels.external_label}: {notes['external']}; a vendor confirmation alone proves neither eligibility nor approval.",
            "rubric": f"Used the independently confirmed {scenario.expedited_readiness} expedited readiness input for {accelerated.id}, then separately derived its {accelerated.completion} operating outcome under {labels.constraint_label} instead of treating a vendor promise as authorization or a completion date.",
        },
        {
            "id": "finite_capacity",
            "sources": ["oncall", "drive"],
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
    identity = scenario.identity
    ticket = scenario.primary_ticket
    cls = scenario.primary_class
    tier = scenario.primary_tier
    playbook_id = file_ids["playbooks/containment-playbook.md"]
    approval_id = file_ids[f"approvals/approval-{scenario.approval.approval_id}.json"]
    ticket_file_id = file_ids[f"tickets/ticket-{ticket.ticket_id}.json"]
    first_set = next(item for item in scenario.sets if item.credential_class == cls.code)
    first_host = next((host for host in scenario.hosts if host.identity_id == identity.identity_id), scenario.hosts[0])
    first_session = next(item for item in scenario.sessions if item.identity_id == identity.identity_id)
    first_factor = next(item for item in scenario.factors if item.identity_id == identity.identity_id)
    reviews = in_scope_reviews(scenario)
    if scenario.mode == "quantity":
        ticket_list_args = {"credential_class": cls.code, "status": "open"}
        ticket_list_expected = {"tickets": [{"ticket_id": t.ticket_id} for _, t in reviews]}
        bridge_args = {"start_date": scenario.numbers["in_scope_window"][0], "end_date": scenario.numbers["in_scope_window"][1], "status": "booked"}
        bridge_expected = {"bridges": [{"id": b.bridge_id} for b, _ in reviews]}
    else:
        ticket_list_args = {"identity_id": identity.identity_id}
        ticket_list_expected = {"tickets": [{"ticket_id": ticket.ticket_id}]}
        own = [b for b in scenario.bridges if b.identity_id == identity.identity_id]
        bridge_args = {"identity_id": identity.identity_id}
        bridge_expected = {"bridges": [{"id": b.bridge_id} for b in own]} if own else {"total": 0}
    investigations = [
        _investigation(1, "investigation.scope", f"Established the isolated {case} scope, immutable handles, mounted systems, and evidence index before investigating {scenario.item}.", CONTEXT_TOOL, {}, {"reference_records": {"case_reference": case}}),
        _investigation(2, "investigation.scope", f"Located the task-scoped correspondence for {case} by searching the mailbox before opening any message; did not rely on a guessed sender or filename.", "messages.list", {"q": case}, {"messages": [{"id": scenario.email.message_id}]}),
        _investigation(3, "investigation.scope", f"Resolved username {identity.username} to the immutable identity record through an identifier search rather than a name match against a similarly named identity.", "iam.identities.search", {"identifier": identity.username}, {"identities": [{"identity_id": identity.identity_id}]}),
        _investigation(4, "investigation.scope", f"Listed the {case} case folder on the shared drive and identified the approval record and the ticket export by immutable file id.", "drive.files.list", {"q": case}, {"files": [{"id": approval_id}, {"id": ticket_file_id}]}),
        _investigation(5, "investigation.scope", "Listed the playbook folder and distinguished the effective v5 containment playbook from the superseded 2024 edition by file identity, not title.", "drive.files.list", {"q": PLAYBOOK_QUERY}, {"files": [{"id": playbook_id}]}),
        _investigation(6, "investigation.requirements", f"Read the active ticket {ticket.ticket_id}: object basis, principals in scope, tier, and review durations.", "servicedesk.tickets.get", {"ticket_id": ticket.ticket_id}, {"ticket_id": ticket.ticket_id, "status": ticket.status}),
        _investigation(7, "investigation.requirements", f"Read the current final credential-inventory snapshot for {identity.identity_id} ({identity.meter_metric}) and ignored the stale historical snapshot.", "iam.inventory.list", {"identity_id": identity.identity_id, "metric": identity.meter_metric}, {"inventory": [{"inventory_id": identity.inventory_id}]}),
        _investigation(8, "investigation.requirements", "Exported the effective v5 playbook for the sizing, revocable-object, vendor-invalidation, window, and authority rules; did not apply the superseded 2024 edition.", "drive.files.export", {"file_id": playbook_id}, {"file_id": playbook_id}),
        _investigation(9, "investigation.requirements", f"Read the containment tier record {tier.code}: immediate-revocation rule, owner-confirmation rule, authority level, and SLA.", "playbooks.tiers.get", {"tier_code": tier.code}, {"tier_code": tier.code}),
        _investigation(10, "investigation.requirements", f"Listed the tickets that define the requirement ({', '.join(sorted({t.ticket_id for _, t in reviews}) if reviews else [ticket.ticket_id])}) and excluded superseded or out-of-scope tickets.", "servicedesk.tickets.list", ticket_list_args, ticket_list_expected),
        _investigation(11, "investigation.requirements", f"Read the correlated events behind {scenario.event_query.get('alert_id')} to ground what actually happened, from which source, and in which window.", "siem.events.list", dict(scenario.event_query), dict(scenario.event_expected)),
        _investigation(12, "investigation.constraints", f"Listed every {cls.code} grant with object count, expiry, status, and owner deferrals before netting the revocable coverage.", "iam.grants.list", {"credential_class": cls.code}, {"grants": [{"grant_id": first_set.grant_id}]}),
        _investigation(13, "investigation.constraints", f"Read the responder window calendar for {scenario.windows_query['start_date']} onward to find the first free window that displaces no protected or blocked block.", "oncall.windows.list", dict(scenario.windows_query), {"windows": [{"id": scenario.selected_window_id}]}),
        _investigation(14, "investigation.constraints", f"Read the vendor invalidation confirmation {scenario.confirmation.confirmation_id} for the independently confirmed standard and expedited job dates and the expedite fee.", "idpvendor.confirmations.get", {"confirmation_id": scenario.confirmation.confirmation_id}, {"confirmation_id": scenario.confirmation.confirmation_id, "standard_ready_date": scenario.confirmation.standard_date}),
        _investigation(15, "investigation.authority", f"Read approval {scenario.approval.approval_id} for its exact scope: record, object count, vendor, fee allowance, and what it does not cover.", "approvals.get", {"approval_id": scenario.approval.approval_id}, {"approval_id": scenario.approval.approval_id}),
        _investigation(16, "investigation.authority", "Exported the approval record on the drive and confirmed it matches the workflow record before relying on it.", "drive.files.export", {"file_id": approval_id}, {"file_id": approval_id}),
        _investigation(17, "investigation.erp_correlation", f"Read the request message {scenario.email.message_id} for the documented control date and the business need in the requester's words.", "messages.get", {"message_id": scenario.email.message_id}, {"id": scenario.email.message_id}),
        _investigation(18, "investigation.erp_correlation", f"Read the SOC chat thread {scenario.chat.thread_id} for grant, window, and authority remarks that qualify the system records.", "chat.threads.get", {"thread_id": scenario.chat.thread_id}, {"thread_id": scenario.chat.thread_id}),
        _investigation(19, "investigation.erp_correlation", "Correlated the incident bridges that fix the review scope by immutable id.", "oncall.bridges.list", bridge_args, bridge_expected),
        _investigation(20, "investigation.requirements", f"Read alert {scenario.alert.alert_id} with its detection rule version and status, and distinguished it from the duplicate or retired-rule alert on the same identity.", "siem.alerts.get", {"alert_id": scenario.alert.alert_id}, {"alert_id": scenario.alert.alert_id, "status": scenario.alert.status}),
        _investigation(21, "investigation.requirements", f"Read detection rule {scenario.alert.rule_id} and confirmed its version was enabled at the alert time, the corroboration the tier rule requires.", "siem.rules.get", {"rule_id": scenario.alert.rule_id}, {"rule_id": scenario.alert.rule_id}),
        _investigation(22, "investigation.constraints", f"Listed the sessions of {identity.identity_id} with source, geo, device, and risk to separate the anomalous session from the owner's own.", "iam.sessions.list", {"identity_id": identity.identity_id}, {"sessions": [{"session_id": first_session.session_id}]}),
        _investigation(23, "investigation.constraints", f"Listed the MFA factors enrolled for {identity.identity_id} to establish which factor was used or bypassed.", "iam.factors.list", {"identity_id": identity.identity_id}, {"factors": [{"factor_id": first_factor.factor_id}]}),
        _investigation(24, "investigation.erp_correlation", f"Correlated the EDR hosts used by {identity.identity_id} with their isolation state and detections.", "edr.hosts.list", {"identity_id": identity.identity_id}, {"hosts": [{"host_id": first_host.host_id}]}),
        _investigation(25, "investigation.requirements", f"Read the credential class record for {cls.code}: object kind, revocation channel, and privilege.", "iam.classes.get", {"credential_class": cls.code}, {"credential_class": cls.code}),
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
    order = [2, 17, 3, 20, 21, 11, 10, 6, 7, 25, 22, 23, 24, 4, 5, 8, 9, 12, 19, 13, 14, 15, 16, 18]
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
                "related_ticket_id": scenario.primary_ticket.ticket_id,
                "related_identity_id": scenario.identity.identity_id,
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
            "payload_text_any_of": [[scenario.case_reference, scenario.identity.username, scenario.primary_ticket.ticket_id]],
            "weight": 1.5,
        },
        {
            "id": "containment_01",
            "milestone_id": "containment.scope",
            "description": f"Made exactly two state changes for {scenario.case_reference}: the primary change and the stakeholder draft; no additional invalidation order, revocation, or bridge.",
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
        correlated_systems=["siem", "edr", "iam", "servicedesk", "oncall", "messages", "chat"],
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
            "iam": {
                "username": scenario.identity.username,
                "identity_search": {"tool": "iam.identities.search", "arguments": {"identifier": scenario.identity.username}},
                "credential_class": scenario.primary_class.code,
                "systems": sorted({item.system for item in scenario.sets}),
            },
            "siem": {"alert_id": scenario.alert.alert_id, "rule_id": scenario.alert.rule_id},
            "messages": {"search_query": scenario.case_reference},
            "drive": {"case_folder_query": scenario.case_reference, "playbook_query": PLAYBOOK_QUERY},
            "oncall": {"pool": "soc-tier2", "calendar_window": scenario.windows_query},
            "idpvendor": {"confirmation_id": scenario.confirmation.confirmation_id},
            "approvals": {"approval_id": scenario.approval.approval_id},
            "chat": {"thread_id": scenario.chat.thread_id},
        },
        "starting_records": [
            *[{"system": "oncall", "resource_type": "Bridge", "resource_id": b.bridge_id, "status": b.status} for b in scenario.bridges],
            {"system": "idpvendor", "resource_type": "InvalidationOrder", "resource_id": "IVO-3400", "status": "RECEIVED"},
            {"system": "iam", "resource_type": "Revocation", "resource_id": "RVK-3400", "status": "COMPLETED"},
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
    "verify_numbers",
]
