"""Assemble Workplace tasks: seed tables, scattered evidence, decision model, sealed contract.

Every declared number in a scenario is recomputed from the seeded world
(linked issues, capacity report, roster skills, leave, on-call, the staff
calendar, ticket SLA timelines, the credit ledger, counterparty confirmations)
and the build fails on any disagreement, so the answer contract can never drift
from the data the agent actually sees.
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
from . import tools as wp_tools
from .policy import SUPERSEDED_STANDARD, effective_standard
from .scenarios import scenarios
from .specs import (
    AS_OF,
    BLOCK_HOURS,
    COUNTED_ISSUE_TYPES,
    OPEN_ISSUE_STATUSES,
    ORGANIZATION,
    PARTNER,
    POINTS_PER_LEAVE_DAY,
    QUALIFIED_LEVEL,
    SESSION_TIMES,
    STANDARD_PAGE_ID,
    SUPERSEDED_PAGE_ID,
    USERS,
    Employee,
    Issue,
    Scenario,
    Ticket,
    block_id,
    business_days,
    hours_between,
    next_business_day,
    weekdays_between,
)

BENCHMARK = "HubBench"
FAMILY_SLUG = "workplace"
FAMILY_VERSION = "1.0.1"
PRIMARY_KEYS = {"issues": "issue_key", "escalations": "escalation_id", "bookings": "booking_id", "credits": "credit_id"}
ITEM_FIELD = {"plan": "coverage_item_or_resource", "quantity": "controlled_item_or_record", "schedule": "affected_resource_or_operation"}
GAP_FIELD = {"plan": "shortage_quantity", "quantity": "transaction_quantity", "schedule": "capacity_gap"}
CASE_FOLDER = "Customer Delivery/Cases/{case}"
STANDARD_QUERY = "Escalation Handling Standard"
OPEN_SOURCE_ANCHORS = (
    {
        "name": "TheAgentCompany",
        "harbor_dataset": "theagentcompany/theagentcompany",
        "harbor_url": "https://hub.harborframework.com/datasets/theagentcompany/theagentcompany/latest",
        "upstream_url": "https://github.com/TheAgentCompany/TheAgentCompany",
        "license": "MIT",
        "evaluation_shape": "simulated-company work across issue tracker, wiki, chat, and file-share apps with checkpoint grading",
    },
    {
        "name": "tau3-bench",
        "harbor_dataset": "sierra-research/tau3-bench",
        "harbor_url": "https://hub.harborframework.com/datasets/sierra-research/tau3-bench/latest",
        "upstream_url": "https://github.com/sierra-research/tau2-bench",
        "license": "MIT",
        "evaluation_shape": "policy-bound customer-service tool use with database end-state checks",
    },
    {
        "name": "MMAU",
        "harbor_dataset": "apple/mmau",
        "harbor_url": "https://hub.harborframework.com/datasets/apple/mmau/latest",
        "upstream_url": "https://github.com/apple/axlearn",
        "license": "Apache-2.0",
        "evaluation_shape": "tool-use, planning, and problem-solving capability suite for agents",
    },
    {
        "name": "BFCL",
        "harbor_dataset": "gorilla/bfcl",
        "harbor_url": "https://hub.harborframework.com/datasets/gorilla/bfcl/latest",
        "upstream_url": "https://github.com/ShishirPatil/gorilla",
        "license": "Apache-2.0",
        "evaluation_shape": "function-calling accuracy with executable and state-based checks",
    },
)


# --------------------------------------------------------------------------- #
# Derivations and cross-checks
# --------------------------------------------------------------------------- #


def _people(scenario: Scenario) -> dict[str, Employee]:
    return {person.employee_id: person for person in scenario.roster}


def _tickets(scenario: Scenario) -> dict[str, Ticket]:
    return {ticket.ticket_id: ticket for ticket in scenario.tickets}


def counted_issues(scenario: Scenario) -> list[Issue]:
    esc = scenario.escalation.escalation_id
    return sorted(
        (item for item in scenario.issues if item.escalation_id == esc and item.type in COUNTED_ISSUE_TYPES and item.status in OPEN_ISSUE_STATUSES),
        key=lambda item: item.issue_key,
    )


def remaining_sprint_days(scenario: Scenario) -> list[str]:
    sprint = scenario.active_sprint
    return weekdays_between(max(AS_OF, sprint.start_date), sprint.end_date)


def leave_days(scenario: Scenario, employee_id: str, days: list[str]) -> int:
    taken = set()
    for item in scenario.timeoff:
        if item.employee_id != employee_id or item.status != "approved":
            continue
        for day in weekdays_between(item.start_date, item.end_date):
            if day in days:
                taken.add(day)
    return len(taken)


def on_call_between(scenario: Scenario, employee_id: str, start: str, end: str) -> bool:
    return any(shift.employee_id == employee_id and shift.start_date <= end and shift.end_date >= start for shift in scenario.oncall)


def qualified(person: Employee, skill: str) -> bool:
    return person.on_calendar and person.status == "active" and person.level(skill) >= QUALIFIED_LEVEL


def qualified_squad(scenario: Scenario) -> list[str]:
    skill = scenario.escalation.required_skill
    return sorted(person.employee_id for person in scenario.squad if qualified(person, skill))


def capacity_breakdown(scenario: Scenario) -> list[dict[str, Any]]:
    people = _people(scenario)
    skill = scenario.escalation.required_skill
    sprint = scenario.active_sprint
    days = remaining_sprint_days(scenario)
    rows = []
    for row in scenario.capacity:
        if row.sprint_id != sprint.sprint_id:
            continue
        person = people[row.employee_id]
        remaining = row.remaining
        if not qualified(person, skill):
            excluded, reason = remaining, f"{skill} level {person.level(skill)} (below {QUALIFIED_LEVEL})"
        elif on_call_between(scenario, row.employee_id, days[0], sprint.end_date):
            excluded, reason = remaining, "on-call shift overlaps the remaining sprint days"
        else:
            leave = leave_days(scenario, row.employee_id, days)
            excluded = min(remaining, POINTS_PER_LEAVE_DAY * leave)
            reason = f"{leave} approved leave day(s) x {POINTS_PER_LEAVE_DAY} points" if leave else ""
        rows.append({"employee_id": row.employee_id, "remaining": remaining, "excluded": excluded, "usable": remaining - excluded, "reason": reason, "qualified": qualified(person, skill) and not on_call_between(scenario, row.employee_id, days[0], sprint.end_date)})
    return rows


def calendar(scenario: Scenario) -> dict[tuple[str, str, str], dict[str, Any]]:
    overrides = {(item.day, item.employee_id, item.session): item for item in scenario.blocks}
    leave: dict[str, set[str]] = {}
    for item in scenario.timeoff:
        if item.status == "approved":
            leave.setdefault(item.employee_id, set()).update(weekdays_between(item.start_date, item.end_date))
    oncall: dict[str, set[str]] = {}
    for shift in scenario.oncall:
        oncall.setdefault(shift.employee_id, set()).update(weekdays_between(shift.start_date, shift.end_date))
    booked: dict[tuple[str, str, str], str] = {}
    for booking in scenario.bookings:
        if booking.status != "booked" or not booking.start or not booking.employee_id:
            continue
        day, start_time, end_time = booking.start[:10], booking.start[11:], booking.end[11:]
        for session, (block_start, block_end) in SESSION_TIMES.items():
            if block_start < end_time and block_end > start_time:
                booked[(day, booking.employee_id, session)] = booking.booking_id
    grid: dict[tuple[str, str, str], dict[str, Any]] = {}
    for day in business_days():
        for person in scenario.squad:
            for session in ("AM", "PM"):
                key = (day, person.employee_id, session)
                entry = {"status": "busy", "hold_reason": "sprint work", "booking_id": None}
                override = overrides.get(key)
                if override is not None:
                    if override.status == "free":
                        entry = {"status": "free", "hold_reason": None, "booking_id": None}
                    else:
                        entry = {"status": override.status, "hold_reason": override.reason or override.status, "booking_id": None}
                if day in oncall.get(person.employee_id, set()):
                    entry = {"status": "protected", "hold_reason": "on-call shift (protected)", "booking_id": None}
                if day in leave.get(person.employee_id, set()):
                    entry = {"status": "pto", "hold_reason": "approved leave", "booking_id": None}
                if key in booked:
                    entry = {"status": "busy", "hold_reason": "booked", "booking_id": booked[key]}
                grid[key] = entry
    return grid


def first_block_on_or_after(scenario: Scenario, start: str, blocks_needed: int, employees: list[str]) -> tuple[str, str, str] | None:
    grid = calendar(scenario)
    for day in business_days():
        if day < start:
            continue
        for employee_id in employees:
            free = [session for session in ("AM", "PM") if grid.get((day, employee_id, session), {}).get("status") == "free"]
            if blocks_needed == 1 and free:
                return day, employee_id, free[0]
            if blocks_needed == 2 and len(free) == 2:
                return day, employee_id, "AM+PM"
    return None


def claim_breakdown(scenario: Scenario) -> list[dict[str, Any]]:
    tickets = _tickets(scenario)
    policy = scenario.sla_policy
    basis = scenario.escalation.claim_basis
    rows = []
    for ticket_id in scenario.escalation.claim_ticket_ids:
        ticket = tickets[ticket_id]
        target = policy.target(ticket.priority)
        if basis == "sla_response":
            measured = hours_between(ticket.opened_at, ticket.first_response_at) if ticket.first_response_at else None
            limit = target.response_hours
        else:
            measured = hours_between(ticket.opened_at, ticket.resolved_at) if ticket.resolved_at else None
            limit = target.resolution_hours
        if ticket.duplicate_of:
            reason = f"duplicate of {ticket.duplicate_of}"
        elif ticket.exempt_reason:
            reason = ticket.exempt_reason
        elif not target.in_scope:
            reason = f"{ticket.priority} is outside the SLA credit scope"
        elif measured is None or measured <= limit:
            reason = f"{measured} h measured against a {limit} h target: not breached"
        else:
            reason = ""
        rows.append({"ticket_id": ticket_id, "priority": ticket.priority, "measured_hours": measured, "target_hours": limit, "supported": not reason, "reason": reason})
    return rows


def ledger_breakdown(scenario: Scenario) -> list[dict[str, Any]]:
    esc = scenario.escalation.escalation_id
    rows = []
    for credit in scenario.credits:
        if credit.agreement_id != scenario.agreement.agreement_id:
            continue
        if credit.status in {"VOID", "EXPIRED"}:
            reason = f"{credit.status.lower()} credit never offsets"
        elif credit.escalation_id != esc:
            reason = f"credit for {credit.escalation_id or 'no escalation'}, not {esc}"
        else:
            reason = ""
        rows.append({"credit_id": credit.credit_id, "amount": credit.amount_usd, "status": credit.status, "offsets": not reason, "reason": reason})
    return rows


def _cap_usd(scenario: Scenario) -> int:
    return round(scenario.agreement.credit_cap_pct * scenario.agreement.monthly_fee_usd / 100)


def _per_incident_usd(scenario: Scenario) -> int:
    return round(scenario.agreement.credit_pct_per_breach * scenario.agreement.monthly_fee_usd / 100)


def _next_id(existing: list[str], prefix: str) -> str:
    highest = 0
    for value in existing:
        if value.startswith(prefix) and value[len(prefix) :].isdigit():
            highest = max(highest, int(value[len(prefix) :]))
    return f"{prefix}{highest + 1}"


def verify_numbers(scenario: Scenario) -> None:
    numbers = scenario.numbers
    extra = scenario.extra_answer
    escalation = scenario.escalation
    problems: list[str] = []

    def check(label: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            problems.append(f"{label}: computed {actual!r} but scenario declares {expected!r}")

    check("standard_readiness", next_business_day(scenario.confirmation.standard_date), scenario.standard_readiness)
    check("expedited_readiness", next_business_day(scenario.confirmation.expedited_date), scenario.expedited_readiness)
    check("control date", scenario.control_commitment.committed_date, scenario.business_need)
    check("confirmation customer", scenario.confirmation.customer_id, scenario.customer.customer_id)
    grid = calendar(scenario)
    if scenario.selected_block_id not in {block_id(employee, day, session) for (day, employee, session) in grid}:
        problems.append(f"selected block {scenario.selected_block_id} is not on the calendar")
    eligible_people = qualified_squad(scenario)
    selected = next(option for option in scenario.options if option.recommended)

    if scenario.mode == "plan":
        issues = counted_issues(scenario)
        breakdown = capacity_breakdown(scenario)
        check("scope", sum(item.story_points for item in issues), numbers["scope"])
        check("observed", sum(row["remaining"] for row in breakdown), numbers["observed"])
        check("excluded", sum(row["excluded"] for row in breakdown), numbers["excluded"])
        check("eligible", sum(row["usable"] for row in breakdown), numbers["eligible"])
        check("counted_linked_issues", len(issues), extra["counted_linked_issues"])
        check("qualified_engineers", sum(1 for row in breakdown if row["qualified"]), extra["qualified_engineers"])
        check("leave_points_excluded", sum(row["excluded"] for row in breakdown if row["qualified"]), extra["leave_points_excluded"])
        check("sprint_end_date", scenario.active_sprint.end_date, extra["sprint_end_date"])
        check("eligible_engineers", eligible_people, numbers["eligible_engineers"])
        check("confirmation kind", scenario.confirmation.kind, "partner_staffing")
        check("confirmation skill", scenario.confirmation.skill_code, escalation.required_skill)
        gap = max(0, numbers["scope"] - numbers["eligible"])
        if scenario.confirmation.capacity_points is not None and gap > scenario.confirmation.capacity_points:
            problems.append("partner confirmation covers fewer points than the gap")
        standard_slot = first_block_on_or_after(scenario, scenario.standard_readiness, 1, eligible_people)
        expedited_slot = first_block_on_or_after(scenario, scenario.expedited_readiness, 1, eligible_people)
        check("standard_slot_date", standard_slot[0] if standard_slot else None, numbers["standard_slot_date"])
        check("expedited_slot_date", expedited_slot[0] if expedited_slot else None, numbers["expedited_slot_date"])
        check("earliest_qualified_base_block", numbers["standard_slot_date"], extra["earliest_qualified_base_block"])
        check("expedite_completion_days_saved", (date.fromisoformat(numbers["standard_slot_date"]) - date.fromisoformat(numbers["expedited_slot_date"])).days, extra["expedite_completion_days_saved"])
        for option in scenario.options:
            ready = scenario.option_ready.get(option.id)
            if ready:
                slot = first_block_on_or_after(scenario, ready, 1, eligible_people)
                check(f"{option.id} completion", slot[0] if slot else None, option.completion)
        ready = scenario.option_ready[selected.id]
        slot = first_block_on_or_after(scenario, ready, 1, eligible_people)
        check("selected_engineer_block", f"{slot[1]}/{slot[0]}/{slot[2]}" if slot else None, extra["selected_engineer_block"])
        check("selected block id", block_id(slot[1], slot[0], slot[2]) if slot else None, scenario.selected_block_id)
        if scenario.primary_write.tool == "tracker.issues.update":
            issue = next(item for item in scenario.issues if item.issue_key == scenario.primary_write.arguments["issue_key"])
            check("partner issue points equal the gap", issue.story_points, gap)
    elif scenario.mode == "quantity":
        agreement = scenario.agreement
        cap = _cap_usd(scenario)
        check("monthly_fee_usd", agreement.monthly_fee_usd, extra["monthly_fee_usd"])
        check("credit_cap_usd", cap, extra["credit_cap_usd"])
        check("confirmation kind", scenario.confirmation.kind, "billing_run")
        if escalation.claim_basis in {"sla_response", "sla_resolution"}:
            claims = claim_breakdown(scenario)
            per_incident = _per_incident_usd(scenario)
            supported = sum(1 for row in claims if row["supported"])
            check("claimed_incidents", len(claims), extra["claimed_incidents"])
            check("supported_incidents", supported, extra["supported_incidents"])
            check("credit_per_incident_usd", per_incident, extra["credit_per_incident_usd"])
            check("scope", min(supported * per_incident, cap), numbers["scope"])
            check("claimed_amount_usd", len(claims) * per_incident, extra["claimed_amount_usd"])
        else:
            commitment = scenario.control_commitment if numbers.get("ld_commitment_id") is None else next(item for item in scenario.commitments if item.commitment_id == numbers["ld_commitment_id"])
            weeks = (date.fromisoformat(commitment.accepted_on) - date.fromisoformat(commitment.committed_date)).days // 7
            check("supported_weeks_late", weeks, extra["supported_weeks_late"])
            check("ld_per_week_usd", commitment.penalty_usd_per_week, extra["ld_per_week_usd"])
            check("scope", min(weeks * commitment.penalty_usd_per_week, cap), numbers["scope"])
            check("claimed_amount_usd", extra["claimed_weeks_late"] * commitment.penalty_usd_per_week, extra["claimed_amount_usd"])
        check("unsupported_claim_usd", extra["claimed_amount_usd"] - numbers["scope"], extra["unsupported_claim_usd"])
        ledger = ledger_breakdown(scenario)
        check("observed", sum(row["amount"] for row in ledger), numbers["observed"])
        check("excluded", sum(row["amount"] for row in ledger if not row["offsets"]), numbers["excluded"])
        check("eligible", sum(row["amount"] for row in ledger if row["offsets"]), numbers["eligible"])
        gap = max(0, numbers["scope"] - numbers["eligible"])
        check("transaction_quantity", gap, numbers["transaction_quantity"])
        check("primary amount", scenario.primary_write.arguments["amount_usd"], numbers["transaction_quantity"])
        check("primary record id", _next_id([credit.credit_id for credit in scenario.credits], "CR-"), scenario.primary_write.record_id)
        if numbers["transaction_quantity"] + numbers["eligible"] > cap:
            problems.append("transaction plus offsets exceeds the agreement cap")
        readiness = {"standard": scenario.standard_readiness, "expedited": scenario.expedited_readiness}
        for option in scenario.options:
            basis = scenario.option_ready.get(option.id)
            if basis:
                check(f"{option.id} completion", readiness[basis], option.completion)
        selected_basis = scenario.option_ready[selected.id]
        check("primary billing option", scenario.primary_write.arguments["billing_option"], "standard_cycle" if selected_basis == "standard" else "off_cycle")
    else:
        hours = (escalation.hands_on_minutes + escalation.verification_minutes) / 60
        if not float(hours).is_integer():
            problems.append("session minutes do not make whole hours")
        check("scope", int(hours), numbers["scope"])
        start, end = numbers["capacity_window"]
        days = [day for day in business_days() if start <= day <= end]
        check("eligible_engineers", eligible_people, numbers["eligible_engineers"])
        keys = [(day, employee, session) for day in days for employee in eligible_people for session in ("AM", "PM")]
        free = sum(1 for key in keys if grid[key]["status"] == "free")
        leave_blocks = sum(1 for key in keys if grid[key]["status"] == "pto")
        check("candidate", len(keys) * BLOCK_HOURS, numbers["observed"])
        check("excluded", (len(keys) - free) * BLOCK_HOURS, numbers["excluded"])
        check("eligible", free * BLOCK_HOURS, numbers["eligible"])
        blocks_needed = -(-int(hours) // BLOCK_HOURS)
        check("sessions_needed", blocks_needed, numbers["sessions_needed"])
        check("blocks_required", blocks_needed, extra["blocks_required"])
        check("requested_day", start, extra["requested_day"])
        check("qualified_engineers", len(eligible_people), extra["qualified_engineers"])
        check("free_blocks_in_window", free, extra["free_blocks_in_window"])
        check("leave_blocks_in_window", leave_blocks, extra["leave_blocks_in_window"])
        slot = first_block_on_or_after(scenario, start, blocks_needed, eligible_people)
        check("selected_resource", f"{slot[1]}/{slot[0]}/{slot[2]}" if slot else None, numbers["selected_resource"])
        check("selected completion", slot[0] if slot else None, selected.completion)
        first_session = slot[2].split("+")[0] if slot else "AM"
        check("selected block id", block_id(slot[1], slot[0], first_session) if slot else None, scenario.selected_block_id)
        check("confirmation kind", scenario.confirmation.kind, "change_window")
    gap = max(0, numbers["scope"] - numbers["eligible"])
    check("gap", gap, numbers["gap"])
    if problems:
        raise ValueError(f"{scenario.task_id} scenario data disagrees with its declared numbers:\n  " + "\n  ".join(problems))


# --------------------------------------------------------------------------- #
# Seed tables
# --------------------------------------------------------------------------- #


def seed_tables(scenario: Scenario, drive_files: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grid = calendar(scenario)
    blocks = [
        {
            "block_id": block_id(employee, day, session),
            "employee_id": employee,
            "service_date": day,
            "session": session,
            "start_time": SESSION_TIMES[session][0],
            "end_time": SESSION_TIMES[session][1],
            **entry,
        }
        for (day, employee, session), entry in sorted(grid.items())
    ]
    return {
        "users": [dict(row) for row in USERS],
        "customers": [
            {"customer_id": c.customer_id, "name": c.name, "tier": c.tier, "region": c.region, "industry": c.industry, "account_owner_user_id": c.account_owner}
            for c in (scenario.customer,)
        ],
        "sla_policies": [
            {"sla_policy_id": p.sla_policy_id, "name": p.name, "version": p.version, "status": p.status, "effective_from": p.effective_from, "note": p.note or None}
            for p in scenario.sla_policies
        ],
        "sla_targets": [
            {"target_id": f"{p.sla_policy_id}-{t.priority}", "sla_policy_id": p.sla_policy_id, "priority": t.priority, "response_hours": t.response_hours, "resolution_hours": t.resolution_hours, "in_scope": int(t.in_scope)}
            for p in scenario.sla_policies
            for t in p.targets
        ],
        "agreements": [
            {
                "agreement_id": a.agreement_id,
                "customer_id": a.customer_id,
                "plan": a.plan,
                "monthly_fee_usd": a.monthly_fee_usd,
                "sla_policy_id": a.sla_policy_id,
                "credit_pct_per_breach": a.credit_pct_per_breach,
                "credit_cap_pct": a.credit_cap_pct,
                "start_date": a.start_date,
                "end_date": a.end_date,
                "status": a.status,
                "note": a.note or None,
            }
            for a in (scenario.agreement, *scenario.other_agreements)
        ],
        "commitments": [
            {
                "commitment_id": c.commitment_id,
                "agreement_id": c.agreement_id,
                "description": c.description,
                "committed_date": c.committed_date,
                "penalty_usd_per_week": c.penalty_usd_per_week,
                "status": c.status,
                "accepted_on": c.accepted_on,
                "guards_escalation_id": scenario.escalation.escalation_id if c.commitment_id == scenario.control_commitment_id and scenario.mode != "quantity" else None,
                "note": c.note or None,
            }
            for c in scenario.commitments
        ],
        "tickets": [
            {
                "ticket_id": t.ticket_id,
                "customer_id": t.customer_id,
                "subject": t.subject,
                "priority": t.priority,
                "status": t.status,
                "opened_at": t.opened_at,
                "first_response_at": t.first_response_at,
                "resolved_at": t.resolved_at,
                "channel": t.channel,
                "requester": t.requester,
                "duplicate_of": t.duplicate_of,
                "escalation_id": t.escalation_id,
                "exempt_reason": t.exempt_reason,
                "note": t.note or None,
            }
            for t in scenario.tickets
        ],
        "escalations": [
            {
                "escalation_id": e.escalation_id,
                "ticket_id": e.ticket_id,
                "customer_id": e.customer_id,
                "level": e.level,
                "status": e.status,
                "opened_at": e.opened_at,
                "owner_user_id": e.owner_user_id,
                "summary": e.summary,
                "required_skill": e.required_skill,
                "hands_on_minutes": e.hands_on_minutes,
                "verification_minutes": e.verification_minutes,
                "claim_ticket_ids_json": json.dumps(list(e.claim_ticket_ids)),
                "claim_basis": e.claim_basis,
                "target_date": e.target_date,
                "sprint_id": e.sprint_id,
                "resolution_plan": e.resolution_plan,
                "note": e.note or None,
                "revision": 1,
                "last_updated": "2026-04-13T17:30:00",
            }
            for e in scenario.escalations
        ],
        "sprints": [
            {"sprint_id": s.sprint_id, "board": s.board, "name": s.name, "state": s.state, "start_date": s.start_date, "end_date": s.end_date, "goal": s.goal}
            for s in scenario.sprints
        ],
        "employees": [
            {
                "employee_id": p.employee_id,
                "name": p.name,
                "title": p.title,
                "team": p.team,
                "timezone": p.timezone,
                "email": p.email,
                "status": p.status,
                "engagement_from": p.engagement_from,
                "note": p.note or None,
            }
            for p in scenario.roster
        ],
        "skills": [
            {"skill_id": f"SK-{p.employee_id.rsplit('-', 1)[1]}-{code}", "employee_id": p.employee_id, "skill_code": code, "level": level, "certified_on": "2025-09-15"}
            for p in scenario.roster
            for code, level in p.skills
        ],
        "issues": [
            {
                "issue_key": i.issue_key,
                "project": i.project,
                "summary": i.summary,
                "type": i.type,
                "status": i.status,
                "story_points": i.story_points,
                "priority": i.priority,
                "required_skill": i.required_skill,
                "escalation_id": i.escalation_id,
                "sprint_id": i.sprint_id,
                "assignee_id": i.assignee_id,
                "note": i.note or None,
                "revision": 1,
                "updated_at": "2026-04-13T16:00:00",
            }
            for i in scenario.issues
        ],
        "sprint_capacity": [
            {"capacity_id": f"CAP-{r.sprint_id.rsplit('-', 1)[1]}-{r.employee_id.rsplit('-', 1)[1]}", "sprint_id": r.sprint_id, "employee_id": r.employee_id, "capacity_points": r.capacity_points, "committed_points": r.committed_points, "report_date": r.report_date}
            for r in scenario.capacity
        ],
        "timeoff": [
            {"timeoff_id": t.timeoff_id, "employee_id": t.employee_id, "start_date": t.start_date, "end_date": t.end_date, "kind": t.kind, "status": t.status, "approved_on": t.approved_on}
            for t in scenario.timeoff
        ],
        "oncall_shifts": [
            {"shift_id": s.shift_id, "employee_id": s.employee_id, "rota": s.rota, "start_date": s.start_date, "end_date": s.end_date}
            for s in scenario.oncall
        ],
        "calendar_blocks": blocks,
        "bookings": [
            {
                "booking_id": b.booking_id,
                "employee_id": b.employee_id,
                "escalation_id": b.escalation_id,
                "issue_key": b.issue_key,
                "start_time": b.start,
                "end_time": b.end,
                "status": b.status,
                "description": b.description,
                "revision": 1,
                "last_updated": "2026-04-10T12:00:00",
            }
            for b in scenario.bookings
        ],
        "credits": [
            {
                "credit_id": c.credit_id,
                "agreement_id": c.agreement_id,
                "customer_id": c.customer_id,
                "escalation_id": c.escalation_id,
                "amount_usd": c.amount_usd,
                "basis": c.basis,
                "status": c.status,
                "issued_on": c.issued_on,
                "billing_option": c.billing_option,
                "confirmation_id": c.confirmation_id,
                "expected_application_date": c.expected_application_date,
                "note": c.note or None,
                "requested_by": "customer_delivery_coordinator",
                "created_at": f"{c.issued_on}T10:00:00",
                "revision": 1,
            }
            for c in scenario.credits
        ],
        "billing_runs": [
            {"run_id": r.run_id, "run_date": r.run_date, "cutoff_date": r.cutoff_date, "kind": r.kind, "status": r.status}
            for r in scenario.billing_runs
        ],
        "confirmations": [
            {
                "confirmation_id": c.confirmation_id,
                "customer_id": c.customer_id,
                "kind": c.kind,
                "counterparty": c.counterparty,
                "reference": c.reference,
                "standard_date": c.standard_date,
                "expedited_date": c.expedited_date,
                "expedite_fee_usd": c.expedite_fee_usd,
                "valid_until": c.valid_until,
                "status": c.status,
                "capacity_points": c.capacity_points,
                "skill_code": c.skill_code,
                "note": c.note or None,
            }
            for c in (scenario.confirmation, *scenario.other_confirmations)
        ],
        "wiki_pages": [
            {
                "page_id": STANDARD_PAGE_ID,
                "root_page_id": STANDARD_PAGE_ID,
                "space": "Customer Delivery",
                "title": "Escalation Handling Standard",
                "version": 5,
                "status": "current",
                "updated_at": "2026-03-02T09:00:00",
                "body": effective_standard(AS_OF),
            },
            {
                "page_id": SUPERSEDED_PAGE_ID,
                "root_page_id": STANDARD_PAGE_ID,
                "space": "Customer Delivery",
                "title": "Escalation Handling Standard (v4, superseded)",
                "version": 4,
                "status": "superseded",
                "updated_at": "2025-06-16T09:00:00",
                "body": SUPERSEDED_STANDARD,
            },
            {
                "page_id": "WIKI-4422",
                "root_page_id": "WIKI-4422",
                "space": "Customer Delivery",
                "title": "Squad working agreement",
                "version": 2,
                "status": "current",
                "updated_at": "2026-01-19T09:00:00",
                "body": "# Squad working agreement\n\nStand-up at 09:15. Sprint review on the last Friday of the sprint. Customer-facing sessions are booked through the staff calendar, never by email.\n",
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
                "approval_id": "AP-WP-0090",
                "subject": "Quarterly customer-delivery training budget (standing)",
                "approver_id": "U-HALE",
                "approver_role": "delivery_manager",
                "status": "APPROVED",
                "granted_on": "2026-02-09",
                "scope_json": json.dumps({"category": "TRAINING", "max_spend_usd": 6000}, sort_keys=True),
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
                "sender": "bronwyn.hale@ferngate.example",
                "recipients": "customer-delivery@ferngate.example",
                "subject": "Weekly delivery note",
                "sent_at": "2026-04-13T08:00:00",
                "body": "Sprint 27 mid-point: capacity report is the 04-10 tracker report, not the drive export. On-call rota and leave are on the staff calendar; protected blocks stay protected.",
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
                "channel": "#customer-delivery",
                "title": "General — stand-up and demo reminders",
                "messages_json": json.dumps([{"author": "Bronwyn Hale", "ts": "2026-04-13T09:20:00", "text": "Reminder: sprint review Friday 24 April, 15:30; keep customer sessions off that slot."}]),
            },
        ],
        "drive_files": drive_files,
        "evidence_files": evidence,
    }


# --------------------------------------------------------------------------- #
# Evidence room
# --------------------------------------------------------------------------- #


def _escalation_json(scenario: Scenario) -> str:
    e = scenario.escalation
    row = {
        "escalation_id": e.escalation_id,
        "ticket_id": e.ticket_id,
        "customer_id": e.customer_id,
        "level": e.level,
        "status": e.status,
        "opened_at": e.opened_at,
        "owner_user_id": e.owner_user_id,
        "summary": e.summary,
        "required_skill": e.required_skill,
        "hands_on_minutes": e.hands_on_minutes,
        "verification_minutes": e.verification_minutes,
        "claim_ticket_ids_json": json.dumps(list(e.claim_ticket_ids)),
        "claim_basis": e.claim_basis,
        "target_date": e.target_date,
        "sprint_id": e.sprint_id,
        "resolution_plan": e.resolution_plan,
        "note": e.note,
        "revision": 1,
        "last_updated": "2026-04-13T17:30:00",
    }
    return json.dumps({"export": "helpdesk.escalations.get", "case_reference": scenario.case_reference, "record": wp_tools._escalation(row)}, indent=2, sort_keys=True) + "\n"


def _ticket_json(scenario: Scenario, ticket: Ticket) -> str:
    row = {
        "ticket_id": ticket.ticket_id,
        "customer_id": ticket.customer_id,
        "subject": ticket.subject,
        "priority": ticket.priority,
        "status": ticket.status,
        "opened_at": ticket.opened_at,
        "first_response_at": ticket.first_response_at,
        "resolved_at": ticket.resolved_at,
        "channel": ticket.channel,
        "requester": ticket.requester,
        "duplicate_of": ticket.duplicate_of,
        "escalation_id": ticket.escalation_id,
        "exempt_reason": ticket.exempt_reason,
        "note": ticket.note,
    }
    return json.dumps({"export": "helpdesk.tickets.get", "case_reference": scenario.case_reference, "record": wp_tools._ticket(row)}, indent=2, sort_keys=True) + "\n"


def _agreement_json(scenario: Scenario) -> str:
    a = scenario.agreement
    rendered = wp_tools._agreement(
        {
            "agreement_id": a.agreement_id,
            "customer_id": a.customer_id,
            "plan": a.plan,
            "monthly_fee_usd": a.monthly_fee_usd,
            "sla_policy_id": a.sla_policy_id,
            "credit_pct_per_breach": a.credit_pct_per_breach,
            "credit_cap_pct": a.credit_cap_pct,
            "start_date": a.start_date,
            "end_date": a.end_date,
            "status": a.status,
            "note": a.note,
        }
    )
    return (
        json.dumps(
            {
                "export": "contracts.agreements.get + contracts.commitments.list",
                "case_reference": scenario.case_reference,
                "agreement": rendered,
                "prior_agreements": [other.agreement_id for other in scenario.other_agreements],
                "commitments": [
                    {"commitment_id": c.commitment_id, "description": c.description, "committed_date": c.committed_date, "penalty_usd_per_week": c.penalty_usd_per_week, "status": c.status, "accepted_on": c.accepted_on}
                    for c in scenario.commitments
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _confirmation_text(scenario: Scenario) -> str:
    c = scenario.confirmation
    lines = [
        c.counterparty,
        f"Confirmation {c.reference} (portal reference {c.confirmation_id})",
        f"Counterparty to: Ferngate Software Customer Delivery, customer {scenario.customer.name} ({scenario.customer.customer_id})",
        f"Case reference: {scenario.case_reference}",
        f"Kind: {c.kind}",
    ]
    if c.kind == "partner_staffing":
        lines.append(f"Skill: {c.skill_code} (certified contractor), covers up to {c.capacity_points} story points")
        lines.append(f"Standard delivery date: {c.standard_date}")
        lines.append(f"Expedited delivery date: {c.expedited_date} (rush fee USD {c.expedite_fee_usd}, flat)")
    elif c.kind == "billing_run":
        lines.append(f"Standard application: credits received by the cut-off are applied on the invoice run of {c.standard_date}")
        lines.append(f"Off-cycle credit note: applied {c.expedited_date} (processing recharge USD {c.expedite_fee_usd})")
    else:
        lines.append(f"Standard change window: {c.standard_date}")
        lines.append(f"Emergency change window: {c.expedited_date} (out-of-hours support fee USD {c.expedite_fee_usd})")
    lines.append(f"Valid until: {c.valid_until}")
    lines.append(f"Notes: {c.note}")
    lines.append("This confirmation records counterparty timing only; it grants no authority and selects no option.")
    return "\n".join(lines) + "\n"


def _scoped_doc(scenario: Scenario, doc) -> dict[str, Any]:
    case = scenario.case_reference
    if doc.media_type == XLSX:
        rows = [list(row) for row in doc.rows or ()]
        if rows:
            rows[0] = [*rows[0], "hubbench_task_scope"]
            rows[1:] = [[*row, scenario.task_id] for row in rows[1:]]
        return asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=XLSX, rows=rows, preview=doc.title)
    if doc.media_type == MARKDOWN:
        content = scoped_markdown(doc.content, task_id=scenario.task_id, case_reference=case)
    elif doc.media_type == CSV:
        content = scoped_csv(doc.content, task_id=scenario.task_id, case_reference=case)
    elif doc.media_type == JSON:
        payload = json.loads(doc.content)
        payload["hubbench_task_scope"] = scenario.task_id
        payload["case_reference"] = case
        content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    else:
        content = doc.content.rstrip() + f"\nEvidence-room mount: {scenario.task_id} / {case}.\n"
    return asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=doc.media_type, content=content, preview=doc.title)


def _decoy_asset(scenario: Scenario) -> dict[str, Any]:
    doc = scenario.decoy_doc
    if doc.kind == "policy_superseded":
        return asset(
            doc.path,
            kind=doc.kind,
            title=doc.title,
            source="drive",
            media_type=MARKDOWN,
            content=scoped_markdown(SUPERSEDED_STANDARD, task_id=scenario.task_id, case_reference=scenario.case_reference),
            preview="v4 standard retained for audit only; superseded by v5.",
        )
    if doc.kind == "decoy_ticket":
        ticket_id = doc.path.rsplit("/", 1)[-1].removeprefix("ticket-").removesuffix(".json")
        ticket = next(t for t in scenario.tickets if t.ticket_id == ticket_id)
        return asset(doc.path, kind=doc.kind, title=doc.title, source="helpdesk_export", media_type=JSON, content=_ticket_json(scenario, ticket), preview="A duplicate or similarly named ticket that must not drive the requirement.")
    return _scoped_doc(scenario, doc)


def build_assets(scenario: Scenario) -> list[dict[str, Any]]:
    case = scenario.case_reference
    grid = calendar(scenario)
    people = _people(scenario)
    assets: list[dict[str, Any]] = [
        asset(
            "standards/escalation-handling-standard-v5.md",
            kind="policy",
            title="Escalation Handling Standard v5 (effective)",
            source="drive",
            media_type=MARKDOWN,
            content=scoped_markdown(effective_standard(AS_OF), task_id=scenario.task_id, case_reference=case),
            preview="Requirement, capacity, calendar, partner, credit, and authority rules in force.",
        ),
    ]
    if scenario.decoy_doc.kind != "policy_superseded":
        assets.append(
            asset(
                "standards/escalation-handling-standard-v4-superseded.md",
                kind="policy_superseded",
                title="Escalation Handling Standard v4 (superseded)",
                source="drive",
                media_type=MARKDOWN,
                content=scoped_markdown(SUPERSEDED_STANDARD, task_id=scenario.task_id, case_reference=case),
                preview="v4 standard retained for audit only; superseded by v5.",
            )
        )
    assets.append(_decoy_asset(scenario))
    sprint = scenario.active_sprint
    policy = scenario.sla_policy
    assets.extend(
        [
            asset(
                f"helpdesk/escalation-{scenario.escalation.escalation_id}.json",
                kind="escalation_export",
                title=f"Escalation {scenario.escalation.escalation_id} (helpdesk export)",
                source="helpdesk_export",
                media_type=JSON,
                content=_escalation_json(scenario),
                preview="The active escalation: required skill, session sizing, claimed tickets, and status.",
            ),
            asset(
                f"helpdesk/ticket-{scenario.primary_ticket.ticket_id}.json",
                kind="ticket_export",
                title=f"Ticket {scenario.primary_ticket.ticket_id} (helpdesk export)",
                source="helpdesk_export",
                media_type=JSON,
                content=_ticket_json(scenario, scenario.primary_ticket),
                preview="The escalated ticket with its SLA timeline.",
            ),
            asset(
                f"helpdesk/sla-policy-{policy.sla_policy_id}.csv",
                kind="sla_policy",
                title=f"SLA policy {policy.sla_policy_id} targets",
                source="helpdesk_export",
                media_type=CSV,
                content=scoped_csv(
                    "sla_policy_id,version,status,priority,response_hours,resolution_hours,in_scope\n"
                    + "".join(f"{p.sla_policy_id},{p.version},{p.status},{t.priority},{t.response_hours:g},{t.resolution_hours:g},{'yes' if t.in_scope else 'no'}\n" for p in scenario.sla_policies for t in p.targets),
                    task_id=scenario.task_id,
                    case_reference=case,
                ),
                preview="Per-priority response and resolution targets, current and superseded policies.",
            ),
            asset(
                f"contracts/agreement-{scenario.agreement.agreement_id}.json",
                kind="agreement_export",
                title=f"Agreement {scenario.agreement.agreement_id} with commitments (contract register export)",
                source="contracts_export",
                media_type=JSON,
                content=_agreement_json(scenario),
                preview="Plan, monthly fee, credit percentage and cap, and registered commitments.",
            ),
            asset(
                f"contracts/commitment-register-{scenario.agreement.agreement_id}.csv",
                kind="commitment_register",
                title="Customer commitment register",
                source="contracts_export",
                media_type=CSV,
                content=scoped_csv(
                    "commitment_id,agreement_id,description,committed_date,penalty_usd_per_week,status,accepted_on\n"
                    + "".join(f'{c.commitment_id},{c.agreement_id},"{c.description}",{c.committed_date},{c.penalty_usd_per_week},{c.status},{c.accepted_on or ""}\n' for c in scenario.commitments),
                    task_id=scenario.task_id,
                    case_reference=case,
                ),
                preview="Committed customer dates, weekly penalties, and acceptance.",
            ),
            asset(
                f"contracts/credit-ledger-{scenario.agreement.agreement_id}.csv",
                kind="credit_ledger",
                title="Credit ledger (gross)",
                source="contracts_export",
                media_type=CSV,
                content=scoped_csv(
                    "credit_id,agreement_id,escalation_id,amount_usd,basis,status,issued_on,note\n"
                    + ("".join(f'{c.credit_id},{c.agreement_id},{c.escalation_id or ""},{c.amount_usd},{c.basis},{c.status},{c.issued_on},"{c.note}"\n' for c in scenario.credits) or f'(none),{scenario.agreement.agreement_id},,0,,NONE,{AS_OF},"no credits on the ledger for {scenario.agreement.agreement_id}"\n'),
                    task_id=scenario.task_id,
                    case_reference=case,
                ),
                preview="Issued, pending, voided, and expired credits; the offset rule is in the standard.",
            ),
            asset(
                f"tracker/linked-issues-{scenario.escalation.escalation_id}.csv",
                kind="issue_register",
                title=f"Tracker issues linked to {scenario.escalation.escalation_id}",
                source="tracker_export",
                media_type=CSV,
                content=scoped_csv(
                    "issue_key,type,status,story_points,sprint_id,assignee_id,required_skill,summary\n"
                    + "".join(f'{i.issue_key},{i.type},{i.status},{i.story_points},{i.sprint_id or ""},{i.assignee_id or ""},{i.required_skill},"{i.summary}"\n' for i in scenario.issues),
                    task_id=scenario.task_id,
                    case_reference=case,
                ),
                preview="Every linked issue with type, status, and points; only some count.",
            ),
            asset(
                f"tracker/sprint-capacity-{sprint.sprint_id}.xlsx",
                kind="capacity_workbook",
                title=f"Sprint capacity report {sprint.sprint_id} (planning-time)",
                source="tracker_workbook",
                media_type=XLSX,
                rows=[
                    ["task_id", "sprint_id", "employee_id", "name", "capacity_points", "committed_points", "remaining_points", "report_date"],
                    *[[scenario.task_id, r.sprint_id, r.employee_id, people[r.employee_id].name, r.capacity_points, r.committed_points, r.remaining, r.report_date] for r in scenario.capacity],
                ],
                preview="Capacity minus committed per engineer; leave, on-call, and skills are not applied.",
            ),
            asset(
                "hris/squad-roster-and-skills.csv",
                kind="roster",
                title="Squad roster with certified skill levels",
                source="hris_export",
                media_type=CSV,
                content=scoped_csv(
                    "employee_id,name,title,status,engagement_from,skill_code,level\n"
                    + "".join(f'{p.employee_id},{p.name},{p.title},{p.status},{p.engagement_from or ""},{code},{level}\n' for p in scenario.roster for code, level in p.skills),
                    task_id=scenario.task_id,
                    case_reference=case,
                ),
                preview="Who holds which skill at which level.",
            ),
            asset(
                f"calendar/staff-calendar-{AS_OF}.xlsx",
                kind="staff_calendar",
                title=f"Staff calendar blocks, four weeks from {AS_OF}",
                source="calendar_workbook",
                media_type=XLSX,
                rows=[
                    ["task_id", "service_date", "employee_id", "session", "start", "end", "status", "hold_reason"],
                    *[[scenario.task_id, day, employee, session, SESSION_TIMES[session][0], SESSION_TIMES[session][1], entry["status"], entry["hold_reason"] or ""] for (day, employee, session), entry in sorted(grid.items())],
                ],
                preview="Every AM/PM block with free / busy / protected / pto status.",
            ),
            asset(
                "calendar/leave-and-oncall.csv",
                kind="leave_register",
                title="Approved leave and on-call shifts",
                source="calendar_export",
                media_type=CSV,
                content=scoped_csv(
                    "record_id,employee_id,kind,start_date,end_date,status\n"
                    + "".join(f"{t.timeoff_id},{t.employee_id},{t.kind},{t.start_date},{t.end_date},{t.status}\n" for t in scenario.timeoff)
                    + "".join(f"{s.shift_id},{s.employee_id},on-call {s.rota},{s.start_date},{s.end_date},scheduled\n" for s in scenario.oncall),
                    task_id=scenario.task_id,
                    case_reference=case,
                ),
                preview="Leave and on-call records that reduce capacity and protect blocks.",
            ),
            asset(
                f"portal/confirmation-{scenario.confirmation.reference}.pdf",
                kind="counterparty_confirmation",
                title=f"Counterparty confirmation {scenario.confirmation.reference}",
                source="email_attachment",
                media_type=PDF,
                content=_confirmation_text(scenario),
                preview="Standard and expedited counterparty dates, fee, coverage, and validity.",
            ),
            asset(
                f"mail/{scenario.email.thread_id}.eml",
                kind="email",
                title=scenario.email.subject,
                source="mail",
                media_type=EML,
                content=eml(
                    from_addr=scenario.email.sender,
                    to_addr=scenario.email.recipients,
                    subject=scenario.email.subject,
                    date=scenario.email.sent_at,
                    message_id=f"{scenario.email.message_id}@ferngate.example",
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
                content=json.dumps({"thread_id": scenario.chat.thread_id, "channel": scenario.chat.channel, "title": scenario.chat.title, "messages": [{"author": a, "ts": t, "text": x} for a, t, x in scenario.chat.messages]}, indent=2, sort_keys=True) + "\n",
                preview="Squad chat with capacity, calendar, and authority remarks.",
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
                preview="Exactly what is approved, for which escalation, and what is not.",
            ),
            asset(
                f"exports/starting-state-{scenario.task_id}.json",
                kind="starting_state",
                title="Starting-state export (escalation, bookings, credit ledger)",
                source="helpdesk_export",
                media_type=JSON,
                content=json.dumps(
                    {
                        "case_reference": case,
                        "as_of": AS_OF,
                        "escalation": {"escalation_id": scenario.escalation.escalation_id, "status": scenario.escalation.status, "target_date": scenario.escalation.target_date, "sprint_id": scenario.escalation.sprint_id},
                        "bookings": [{"booking_id": b.booking_id, "employee_id": b.employee_id, "escalation_id": b.escalation_id, "start": b.start, "end": b.end, "status": b.status} for b in scenario.bookings],
                        "credits": [{"credit_id": c.credit_id, "escalation_id": c.escalation_id, "amount_usd": c.amount_usd, "status": c.status} for c in scenario.credits],
                        "note": "Snapshot before any action; row order does not indicate applicability.",
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                preview="Snapshot of escalation, calendar, and ledger state before any action.",
            ),
        ]
    )
    for doc in scenario.docs:
        assets.append(_scoped_doc(scenario, doc))
    assets.extend(
        quality_support_assets(
            task_id=scenario.task_id,
            ordinal=scenario.ordinal,
            case_reference=case,
            family_slug=FAMILY_SLUG,
            family_name="Workplace",
            organization_name=ORGANIZATION["name"],
            subject_id=scenario.item,
            as_of=AS_OF,
            current_revision=scenario.revision,
            anchors=OPEN_SOURCE_ANCHORS,
        )
    )
    index = {"case_reference": case, "as_of": AS_OF, "files": [{"path": a["path"], "kind": a["kind"], "media_type": a["media_type"], "sha256": a["sha256"]} for a in assets]}
    assets.append(asset("audit/evidence-index.yaml", kind="evidence_index", title="Evidence index", source="drive", media_type=YAML, content=yaml_lines(index) + "\n", preview="Digest index of every evidence file in the room."))
    for position, record in enumerate(assets, start=1):
        record["asset_id"] = f"{scenario.task_id}-{position:02d}"
    return assets


def _folder(scenario: Scenario, record: dict[str, Any]) -> str:
    if record["kind"] == "policy":
        return "Customer Delivery/Standards"
    if record["kind"] == "policy_superseded":
        return "Customer Delivery/Standards/Archive"
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
                "modified_time": "2026-04-13T17:45:00",
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
    return (
        {
            "id": "authoritative_identity",
            "sources": ["helpdesk", "mail"],
            "statement": f"{scenario.case_reference}: {notes['identity']}; the effective revision is {scenario.revision}.",
            "rubric": f"Located {scenario.item} using immutable identifiers and preserved effective revision {scenario.revision}: {notes['identity']}.",
        },
        {
            "id": "effective_requirement",
            "sources": ["helpdesk", "tracker", "wiki", "contracts"],
            "statement": f"The effective escalation record and the v5 standard establish {labels.scope_label} = {numbers['scope']} {labels.unit}: {notes['requirement']}. The control date is {scenario.business_need} ({scenario.business_need_reason}).",
            "rubric": f"Applied the escalation record and the v5 standard to establish {numbers['scope']} {labels.unit} for {labels.scope_label}, with control date {scenario.business_need}.",
        },
        {
            "id": "eligible_coverage",
            "sources": ["tracker", "hris", "calendar", "contracts"],
            "statement": f"{notes['coverage']}; eligibility requires netting the exclusions rather than trusting a header total.",
            "rubric": f"Reconciled {numbers['observed']} observed less {numbers['excluded']} excluded to {numbers['eligible']} supported {labels.unit} for {labels.eligible_label}.",
        },
        {
            "id": "conditional_external_recovery",
            "sources": ["portal", "mail"],
            "statement": f"{labels.external_label}: {notes['external']}; a counterparty confirmation alone proves neither eligibility nor approval.",
            "rubric": f"Used the independently confirmed {scenario.standard_readiness} standard and {scenario.expedited_readiness} expedited readiness inputs from {labels.external_label}, then separately derived each alternative's operating outcome under {labels.constraint_label} instead of treating a counterparty promise as authorization or a completion date.",
        },
        {
            "id": "finite_capacity",
            "sources": ["calendar", "tracker", "contracts"],
            "statement": f"{labels.capacity_label}: {notes['capacity']}; protected and leave blocks cannot be displaced.",
            "rubric": f"Applied {labels.capacity_label} to derive the three option outcomes without displacing protected blocks or committed dates.",
        },
        {
            "id": "approval_scope",
            "sources": ["approvals", "chat"],
            "statement": f"{notes['approval']}. The approval does not select an option in advance and does not authorize {unauthorized.id}.",
            "rubric": f"Applied {scenario.approval.approval_id} only to {selected.id} and {scenario.item}; kept {unauthorized.id} outside current authority.",
        },
        {
            "id": "business_impact",
            "sources": ["mail", "chat", "contracts"],
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
    customer = scenario.customer
    escalation = scenario.escalation
    ticket = scenario.primary_ticket
    agreement = scenario.agreement
    sprint = scenario.active_sprint
    approval_file = file_ids[f"approvals/approval-{scenario.approval.approval_id}.json"]
    escalation_file = file_ids[f"helpdesk/escalation-{escalation.escalation_id}.json"]
    own_bookings = [b for b in scenario.bookings if b.escalation_id == escalation.escalation_id]
    bookings_expected = {"bookings": [{"id": b.booking_id} for b in own_bookings]} if own_bookings else {"total": 0}
    ledger = [c for c in scenario.credits if c.agreement_id == agreement.agreement_id]
    ledger_expected = {"credits": [{"credit_id": ledger[0].credit_id}]} if ledger else {"total": 0}
    specs: list[tuple[str, str, str, dict[str, Any], dict[str, Any]]] = [
        ("investigation.scope", f"Established the isolated {case} scope, immutable handles, mounted systems, and evidence index before investigating {scenario.item}.", CONTEXT_TOOL, {}, {"reference_records": {"case_reference": case}}),
        ("investigation.scope", f"Located the task-scoped correspondence for {case} by searching the mailbox before opening any message; did not rely on a guessed sender or filename.", "mail.messages.list", {"q": case}, {"messages": [{"id": scenario.email.message_id}]}),
        ("investigation.scope", f"Resolved customer {customer.customer_id} to the immutable account record rather than matching on a similarly named organisation.", "helpdesk.customers.get", {"customer_id": customer.customer_id}, {"customer_id": customer.customer_id}),
        ("investigation.scope", f"Listed {customer.customer_id}'s open escalations and identified {escalation.escalation_id} by immutable id, not by the ticket subject.", "helpdesk.escalations.list", {"customer_id": customer.customer_id, "status": "open"}, {"escalations": [{"escalation_id": escalation.escalation_id}]}),
        ("investigation.scope", f"Listed the {case} case folder on the shared drive and identified the approval record and the escalation export by immutable file id.", "drive.files.list", {"q": case}, {"files": [{"id": approval_file}, {"id": escalation_file}]}),
        ("investigation.scope", "Searched the wiki and distinguished the effective v5 Escalation Handling Standard from the superseded v4 edition by page identity, not title.", "wiki.pages.search", {"q": STANDARD_QUERY}, {"pages": [{"page_id": STANDARD_PAGE_ID}]}),
        ("investigation.requirements", f"Read the escalation record {escalation.escalation_id}: required skill, session sizing, claimed tickets, and current status.", "helpdesk.escalations.get", {"escalation_id": escalation.escalation_id}, {"escalation_id": escalation.escalation_id, "status": escalation.status}),
        ("investigation.requirements", f"Read the escalated ticket {ticket.ticket_id} with its SLA timeline, priority, and duplicate link.", "helpdesk.tickets.get", {"ticket_id": ticket.ticket_id}, {"ticket_id": ticket.ticket_id, "priority": ticket.priority}),
        ("investigation.requirements", f"Listed {customer.customer_id}'s tickets and separated the escalated ticket from duplicates and unrelated tickets by immutable id.", "helpdesk.tickets.search", {"customer_id": customer.customer_id}, {"tickets": [{"ticket_id": ticket.ticket_id}]}),
        ("investigation.requirements", "Read the effective v5 standard for the requirement, capacity, calendar, partner, credit, and authority rules; did not apply the superseded v4 edition.", "wiki.pages.get", {"page_id": STANDARD_PAGE_ID}, {"page_id": STANDARD_PAGE_ID, "version": 5, "status": "current"}),
        ("investigation.requirements", f"Read SLA policy {agreement.sla_policy_id} for the per-priority targets and the credit scope.", "helpdesk.sla_policies.get", {"sla_policy_id": agreement.sla_policy_id}, {"sla_policy_id": agreement.sla_policy_id}),
        ("investigation.requirements", f"Read agreement {agreement.agreement_id}: monthly fee, credit percentage, cap, and term.", "contracts.agreements.get", {"agreement_id": agreement.agreement_id}, {"agreement_id": agreement.agreement_id, "monthly_fee_usd": agreement.monthly_fee_usd}),
        ("investigation.requirements", f"Read the commitment register for {agreement.agreement_id} to take the documented control date from {scenario.control_commitment_id}.", "contracts.commitments.list", {"agreement_id": agreement.agreement_id}, {"commitments": [{"commitment_id": scenario.control_commitment_id}]}),
    ]
    if scenario.mode == "quantity":
        claims = [t for t in scenario.tickets if t.ticket_id in escalation.claim_ticket_ids] or [ticket]
        offset = next((c for c in ledger if c.escalation_id == escalation.escalation_id and c.status in {"ISSUED", "PENDING"}), None)
        specs.extend(
            [
                ("investigation.requirements", f"Listed the tickets attached to claim {escalation.escalation_id} so each claimed incident is tested against the contract terms by its own record.", "helpdesk.tickets.search", {"customer_id": customer.customer_id, "escalation_id": escalation.escalation_id}, {"tickets": [{"ticket_id": t.ticket_id} for t in claims]}),
                ("investigation.requirements", f"Listed the tracker issues linked to {escalation.escalation_id} to confirm the fix status behind the claim.", "tracker.issues.search", {"escalation_id": escalation.escalation_id}, {"issues": [{"key": i.issue_key} for i in sorted(scenario.issues, key=lambda i: i.issue_key) if i.escalation_id == escalation.escalation_id][:1]}),
                ("investigation.constraints", f"Read the gross credit ledger for {agreement.agreement_id} before netting the offsets: issued, pending, voided, expired, and other-escalation credits.", "contracts.credits.list", {"agreement_id": agreement.agreement_id}, ledger_expected),
                ("investigation.constraints", "Read the billing-run schedule (calendar of invoice runs and credit-memo cut-offs) that fixes when a standard-cycle credit can post.", "contracts.billing_runs.list", {"start_date": AS_OF, "end_date": (date.fromisoformat(AS_OF) + timedelta(days=60)).isoformat()}, {"runs": [{"run_id": scenario.billing_runs[0].run_id}]}),
                ("investigation.constraints", f"Read the customer's external accounts-payable counterpart confirmation {scenario.confirmation.confirmation_id} for the independently confirmed standard and off-cycle application dates and the processing recharge.", "portal.confirmations.get", {"confirmation_id": scenario.confirmation.confirmation_id}, {"confirmation_id": scenario.confirmation.confirmation_id, "standard_date": scenario.confirmation.standard_date}),
            ]
        )
        if offset is not None:
            specs.append(("investigation.erp_correlation", f"Read credit {offset.credit_id} and correlated it to {escalation.escalation_id} by immutable escalation id before treating it as an offset.", "contracts.credits.get", {"credit_id": offset.credit_id}, {"credit_id": offset.credit_id, "status": offset.status}))
        specs.append(("investigation.erp_correlation", f"Correlated the session bookings for {escalation.escalation_id} by immutable id.", "calendar.bookings.list", {"escalation_id": escalation.escalation_id}, bookings_expected))
    else:
        counted = counted_issues(scenario)
        qualified_people = qualified_squad(scenario)
        people = _people(scenario)
        window_end = sprint.end_date if scenario.mode == "plan" else scenario.numbers["capacity_window"][1]
        leave = [t for t in scenario.timeoff if t.status == "approved" and t.start_date <= window_end and t.end_date >= AS_OF]
        leave_expected = {"timeoff": [{"timeoff_id": t.timeoff_id} for t in leave]} if leave else {"total": 0}
        shifts = [s for s in scenario.oncall if s.start_date <= window_end and s.end_date >= AS_OF]
        shifts_expected = {"shifts": [{"shift_id": s.shift_id} for s in shifts]} if shifts else {"shifts": []}
        specs.append(("investigation.requirements", f"Listed the tracker issues linked to {escalation.escalation_id} and counted only open Fix, Test, and Verification issues ({', '.join(i.issue_key for i in counted)}).", "tracker.issues.search", {"escalation_id": escalation.escalation_id}, {"issues": [{"key": i.issue_key} for i in counted]}))
        specs.append(("investigation.constraints", f"Read sprint {sprint.sprint_id} for the sprint window and end date that bounds 'this sprint'.", "tracker.sprints.get", {"sprint_id": sprint.sprint_id}, {"sprint_id": sprint.sprint_id, "end_date": sprint.end_date}))
        if scenario.mode == "plan":
            specs.append(("investigation.constraints", f"Read the planning-time capacity report for {sprint.sprint_id} (capacity minus committed per engineer) before applying skill, on-call, and leave exclusions.", "tracker.sprints.capacity", {"sprint_id": sprint.sprint_id}, {"capacity": [{"employee": r.employee_id} for r in scenario.capacity if r.sprint_id == sprint.sprint_id]}))
        specs.extend(
            [
                ("investigation.constraints", f"Listed the certified {escalation.required_skill} holders on the roster and kept only level {QUALIFIED_LEVEL}+ engineers ({', '.join(qualified_people)}).", "hris.skills.list", {"skill_code": escalation.required_skill}, {"skills": [{"employee_id": e, "level": people[e].level(escalation.required_skill)} for e in qualified_people]}),
                ("investigation.constraints", f"Read approved leave between {AS_OF} and {window_end} from the staff calendar, the only source that reflects it.", "calendar.timeoff.list", {"start_date": AS_OF, "end_date": window_end, "status": "approved"}, leave_expected),
                ("investigation.constraints", f"Read the on-call rota between {AS_OF} and {window_end}; the on-call engineer's blocks are protected and carry no feature capacity.", "calendar.oncall.list", {"start_date": AS_OF, "end_date": window_end}, shifts_expected),
                ("investigation.constraints", f"Read the staff calendar blocks for {scenario.blocks_query['start_date']} onward to find the first free block of a qualified engineer that displaces no protected or leave block.", "calendar.blocks.list", dict(scenario.blocks_query), {"blocks": [{"id": scenario.selected_block_id}]}),
                ("investigation.constraints", f"Read the external counterpart confirmation {scenario.confirmation.confirmation_id} for the independently confirmed standard and expedited dates and the fee.", "portal.confirmations.get", {"confirmation_id": scenario.confirmation.confirmation_id}, {"confirmation_id": scenario.confirmation.confirmation_id, "standard_date": scenario.confirmation.standard_date}),
                ("investigation.erp_correlation", f"Correlated the session bookings for {escalation.escalation_id} by immutable id.", "calendar.bookings.list", {"escalation_id": escalation.escalation_id}, bookings_expected),
                ("investigation.erp_correlation", f"Read the credit ledger for {agreement.agreement_id} so the stakeholder note states the credit position honestly.", "contracts.credits.list", {"agreement_id": agreement.agreement_id}, ledger_expected),
            ]
        )
    specs.extend(
        [
            ("investigation.authority", f"Read approval {scenario.approval.approval_id} for its exact scope: escalation, quantity, counterparty, fee allowance, and what it does not cover.", "approvals.get", {"approval_id": scenario.approval.approval_id}, {"approval_id": scenario.approval.approval_id}),
            ("investigation.authority", "Exported the approval record on the drive and confirmed it matches the workflow record before relying on it.", "drive.files.export", {"file_id": approval_file}, {"file_id": approval_file}),
            ("investigation.erp_correlation", f"Read the request message {scenario.email.message_id} for the documented control date and the business need in the requester's words.", "mail.messages.get", {"message_id": scenario.email.message_id}, {"id": scenario.email.message_id}),
            ("investigation.erp_correlation", f"Read the squad chat thread {scenario.chat.thread_id} for capacity, calendar, and authority remarks that qualify the system records.", "chat.threads.get", {"thread_id": scenario.chat.thread_id}, {"thread_id": scenario.chat.thread_id}),
            ("investigation.erp_correlation", "Correlated the standard's version history: v5 is current and v4 is superseded, so only v5 governs.", "wiki.versions.list", {"page_id": STANDARD_PAGE_ID}, {"versions": [{"version": 5, "status": "current"}, {"version": 4, "status": "superseded"}]}),
        ]
    )
    investigations = [_investigation(number, milestone, description, tool, arguments, expected) for number, (milestone, description, tool, arguments, expected) in enumerate(specs, start=1)]
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
    for item in investigations:
        call = item["any_of"][0]
        if call["tool"] == CONTEXT_TOOL:
            continue
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
                "related_escalation_id": scenario.escalation.escalation_id,
                "related_customer_id": scenario.customer.customer_id,
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
            "payload_text_any_of": [[scenario.case_reference, scenario.escalation.escalation_id, scenario.primary_ticket.ticket_id]],
            "weight": 1.5,
        },
        {
            "id": "containment_01",
            "milestone_id": "containment.scope",
            "description": f"Made exactly two state changes for {scenario.case_reference}: the primary change and the stakeholder draft; no additional booking, credit, assignment, or commitment change.",
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
        correlated_systems=["helpdesk", "tracker", "wiki", "calendar", "hris", "contracts", "portal", "mail", "chat"],
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
            "wrong_evidence": {"tool": "drive.files.export", "arguments": {"file_id": file_ids[scenario.decoy_doc.path]}},
        },
        "reference_records": {
            "case_reference": scenario.case_reference,
            "helpdesk": {
                "customer_id": scenario.customer.customer_id,
                "escalation_search": {"tool": "helpdesk.escalations.list", "arguments": {"customer_id": scenario.customer.customer_id, "status": "open"}},
            },
            "mail": {"search_query": scenario.case_reference},
            "drive": {"case_folder_query": scenario.case_reference, "standard_query": STANDARD_QUERY},
            "wiki": {"standard_query": STANDARD_QUERY},
            "tracker": {"board": "Customer Delivery", "active_sprint": scenario.active_sprint.sprint_id},
            "calendar": {"calendar_window": scenario.blocks_query},
            "contracts": {"agreement_id": scenario.agreement.agreement_id},
            "portal": {"confirmation_id": scenario.confirmation.confirmation_id},
            "approvals": {"approval_id": scenario.approval.approval_id},
            "chat": {"thread_id": scenario.chat.thread_id},
        },
        "starting_records": [
            {"system": "helpdesk", "resource_type": "Escalation", "resource_id": scenario.escalation.escalation_id, "status": scenario.escalation.status},
            *[{"system": "calendar", "resource_type": "Booking", "resource_id": b.booking_id, "status": b.status} for b in scenario.bookings],
            *[{"system": "contracts", "resource_type": "Credit", "resource_id": c.credit_id, "status": c.status} for c in scenario.credits],
        ],
        "evaluation": {"metric": "HubScore", "strict_pass": "every rubric milestone passes", "llm_judge_calls": 0},
        "workflow": {"reads": len([s for s in steps if s["phase"] in {"context", "investigation"}]), "writes": 2, "readbacks": 1, "answer_fields": len(answer)},
    }


def build_tasks() -> list[dict[str, Any]]:
    return [build_task(scenario) for scenario in scenarios()]


__all__ = ["BENCHMARK", "FAMILY_SLUG", "FAMILY_VERSION", "PARTNER", "build_task", "build_tasks", "calendar", "capacity_breakdown", "claim_breakdown", "first_block_on_or_after", "ledger_breakdown", "verify_numbers"]
