"""Assemble DeskOps tasks: seed tables, scattered evidence, decision model, sealed contract.

Every declared number in a scenario is recomputed from the seeded world
(attendee list and home offices, bookings and fare classes, venue availability
and quotes, busy blocks, ticketing confirmations, budget lines, policy tables)
and the build fails on any disagreement, so the answer contract can never
drift from the data the agent actually sees.
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
from . import tools as desk_tools
from .policy import CURRENT_PARAMETERS, CURRENT_POLICY_ID, PER_DIEM_USD, POLICY_CODE, SUPERSEDED_PARAMETERS, SUPERSEDED_POLICY, SUPERSEDED_POLICY_ID, contingency_for, effective_policy
from .scenarios import scenarios
from .specs import (
    AS_OF,
    OFFICES,
    OFFICE_BY_ID,
    ORGANIZATION,
    ROOMS,
    TMCS,
    USERS,
    WEEKDAYS,
    Booking,
    Scenario,
    conflict_attendee_days,
    first_clear_week,
    is_hard,
    next_business_day,
    offsite_dates,
    travellers,
    week_grid,
    week_id,
    week_starts,
)
from .tools import add_business_days

BENCHMARK = "HubBench"
FAMILY_SLUG = "deskops"
FAMILY_VERSION = "1.0.1"
PRIMARY_KEYS = {
    "events": "event_id",
    "venue_holds": "hold_id",
    "booking_changes": "change_id",
    "budget_adjustments": "adjustment_id",
}
ITEM_FIELD = {"plan": "coverage_item_or_resource", "quantity": "controlled_item_or_record", "schedule": "affected_resource_or_operation"}
GAP_FIELD = {"plan": "shortage_quantity", "quantity": "transaction_quantity", "schedule": "capacity_gap"}
CASE_FOLDER = "Workplace Operations/Cases/{case}"
POLICY_QUERY = POLICY_CODE
OPEN_SOURCE_ANCHORS = (
    {
        "name": "OSWorld-Verified",
        "harbor_dataset": "xlang-ai/osworld-verified",
        "harbor_url": "https://hub.harborframework.com/datasets/xlang-ai/osworld-verified/latest",
        "upstream_url": "https://github.com/xlang-ai/OSWorld",
        "license": "per the upstream repository; nothing from it is redistributed here",
        "evaluation_shape": "real desktop-application tasks (mail, calendar, office documents, spreadsheets, file management) with execution-based end-state checks",
    },
    {
        "name": "AndroidBench",
        "harbor_dataset": "android-bench/android-bench",
        "harbor_url": "https://hub.harborframework.com/datasets/android-bench/android-bench/latest",
        "upstream_url": "https://hub.harborframework.com/datasets/android-bench/android-bench/latest",
        "license": "per the upstream listing; nothing from it is redistributed here",
        "evaluation_shape": "mobile application workflows driven through the GUI with deterministic outcome checks",
    },
)


# --------------------------------------------------------------------------- #
# Derivations and cross-checks
# --------------------------------------------------------------------------- #


def traveller_flights(scenario: Scenario) -> list[Booking]:
    ids = {person.person_id for person in travellers(scenario)}
    return [b for b in scenario.bookings if b.event_id == scenario.event.event_id and b.kind == "flight" and b.status == "ticketed" and b.person_id in ids]


def _readiness(scenario: Scenario, kind: str) -> str:
    return {"standard": scenario.standard_readiness, "expedited": scenario.expedited_readiness, "asof": AS_OF}[kind]


def basis_week(scenario: Scenario, basis: dict[str, Any]) -> tuple[str, str] | None:
    if basis["kind"] == "clear_week":
        week = first_clear_week(scenario, basis["venue"], _readiness(scenario, basis["readiness"]))
        return (basis["venue"], week) if week else None
    if basis["kind"] == "week":
        return basis["venue"], basis["week_start"]
    return None


def basis_completion(scenario: Scenario, basis: dict[str, Any]) -> str | None:
    if basis["kind"] == "original":
        return scenario.event.start
    resolved = basis_week(scenario, basis)
    if resolved is None:
        return None
    return offsite_dates(resolved[1], scenario.event.session_days)[0]


def verify_numbers(scenario: Scenario) -> None:
    numbers = scenario.numbers
    extra = scenario.extra_answer
    problems: list[str] = []

    def check(label: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            problems.append(f"{label}: computed {actual!r} but scenario declares {expected!r}")

    venue = scenario.target_venue
    required = scenario.required_attendees
    trav = travellers(scenario)
    flights = traveller_flights(scenario)
    changeable = [b for b in flights if b.changeable]
    basic = [b for b in flights if not b.changeable]
    fees = sum(b.change_fee for b in changeable)
    new_tickets = len(trav) - len(changeable)
    conf = scenario.confirmation
    quote = scenario.target_quote
    contracted = next((q for q in scenario.quotes if q.quote_id == numbers.get("contracted_quote")), None)
    grid = week_grid(scenario)

    check("agenda session days", scenario.agenda.current.session_days, scenario.event.session_days)
    check("target quote venue", quote.venue_id, venue.venue_id)
    check("target quote status", quote.status, "current")
    if contracted is not None:
        check("contracted quote status", contracted.status, "contracted")
    check("standard_readiness", next_business_day(conf.standard_date), scenario.standard_readiness)
    check("expedited_readiness", next_business_day(conf.rush_date), scenario.expedited_readiness)
    if len(scenario.attendees) > venue.capacity:
        problems.append(f"{venue.venue_id} seats {venue.capacity} but the event lists {len(scenario.attendees)} attendees")

    if scenario.mode == "plan" or numbers.get("quantity_kind") == "bookings":
        check("scope", len(trav), numbers["scope"])
        check("observed", len(flights), numbers["observed"])
        check("excluded", len(basic), numbers["excluded"])
        check("eligible", len(changeable), numbers["eligible"])
        check("gap", new_tickets, numbers["gap"])
        if numbers.get("quantity_kind") == "bookings":
            check("transaction_quantity", len(changeable), numbers["transaction_quantity"])
            check("primary booking_ids", sorted(scenario.primary_write.arguments["booking_ids"]), sorted(b.booking_id for b in changeable))
    elif scenario.mode == "quantity":
        if contracted is None:
            problems.append("a budget-quantity scenario needs a contracted quote")
        else:
            venue_delta = quote.total - contracted.total
            per_diem_delta = (quote.days - contracted.days) * len(trav) * PER_DIEM_USD[venue.country]
            check("scope", fees + new_tickets * conf.group_fare + venue_delta + per_diem_delta, numbers["scope"])
            if "venue_delta_usd" in extra:
                check("venue_delta_usd", venue_delta, extra["venue_delta_usd"])
            if "per_diem_delta_usd" in extra:
                check("per_diem_delta_usd", per_diem_delta, extra["per_diem_delta_usd"])
        line = scenario.budget_line
        check("observed", line.approved - line.committed, numbers["observed"])
        check("excluded", line.reserved, numbers["excluded"])
        check("eligible", line.approved - line.committed - line.reserved, numbers["eligible"])
        check("gap", max(0, numbers["scope"] - numbers["eligible"]), numbers["gap"])
        check("contingency", contingency_for(len(scenario.attendees)), numbers["contingency"])
        check("transaction_quantity", numbers["gap"] + numbers["contingency"], numbers["transaction_quantity"])
        if numbers["transaction_quantity"] > scenario.approval.scope["max_adjustment_usd"]:
            problems.append("the adjustment exceeds the signed approval")
        if numbers["transaction_quantity"] > line.ceiling:
            problems.append("the adjustment exceeds the line ceiling")
        check("primary amount", scenario.primary_write.arguments["amount_usd"], numbers["transaction_quantity"])
    else:
        count = len(required)
        days = scenario.event.session_days
        conflicts = conflict_attendee_days(scenario, numbers["requested_week"])
        check("scope", count * days, numbers["scope"])
        check("observed", count * WEEKDAYS, numbers["observed"])
        check("excluded", count * (WEEKDAYS - days) + conflicts, numbers["excluded"])
        check("eligible", numbers["observed"] - numbers["excluded"], numbers["eligible"])
        check("gap", max(0, numbers["scope"] - numbers["eligible"]), numbers["gap"])
        if "non_session_attendee_days" in extra:
            check("non_session_attendee_days", count * (WEEKDAYS - days), extra["non_session_attendee_days"])
        if "conflict_attendee_days" in extra:
            check("conflict_attendee_days", conflicts, extra["conflict_attendee_days"])
        if "requested_week" in extra:
            check("requested_week", numbers["requested_week"], extra["requested_week"])
        if grid[(venue.venue_id, numbers["requested_week"])]["status"] != "open":
            problems.append("the requested week is not open at the target venue")
    check("gap floor", max(0, numbers["scope"] - numbers["eligible"]), numbers["gap"])

    derived = {
        "required_attendees": len(required),
        "local_attendees": len(required) - len(trav),
        "session_days": scenario.event.session_days,
        "travellers": len(trav),
        "changeable_bookings": len(changeable),
        "new_tickets_required": new_tickets,
        "change_fees_usd": fees,
        "group_fare_usd": conf.group_fare,
        "new_ticket_cost_usd": new_tickets * conf.group_fare,
        "incremental_travel_cost_usd": fees + new_tickets * conf.group_fare,
        "rush_fee_usd": conf.rush_fee,
        "hold_deposit_usd": quote.deposit,
        "attendee_count": len(scenario.attendees),
        "contingency_usd": contingency_for(len(scenario.attendees)),
        "hold_expires_on": add_business_days(AS_OF, venue.hold_business_days),
        "venue_hire_delta_usd": quote.total - (contracted.total if contracted else 0),
    }
    if "move_incremental_cost_usd" in extra:
        move_quote = next(q for q in scenario.quotes if q.quote_id == numbers["move_quote"])
        derived["move_incremental_cost_usd"] = fees + new_tickets * conf.group_fare + (move_quote.total - (contracted.total if contracted else 0))
    for key, value in derived.items():
        if key in extra:
            check(key, value, extra[key])

    for option, basis in zip(scenario.options, scenario.option_basis, strict=True):
        check(f"{option.id} completion", basis_completion(scenario, basis), option.completion)
        if basis["kind"] == "week":
            entry = grid.get((basis["venue"], basis["week_start"]))
            check(f"{option.id} week status", entry["status"] if entry else None, basis["status"])
    selected = next(index for index, option in enumerate(scenario.options) if option.recommended)
    selected_week = basis_week(scenario, scenario.option_basis[selected])
    check("selected_week", selected_week, scenario.selected_week)
    if "selected_venue_week" in extra:
        check("selected_venue_week", f"{selected_week[0]}/{selected_week[1]}" if selected_week else None, extra["selected_venue_week"])
    if "selected_resource" in numbers:
        check("selected_resource", f"{selected_week[0]}/{selected_week[1]}" if selected_week else None, numbers["selected_resource"])
    base_venue = numbers.get("move_venue", venue.venue_id)
    standard_week = first_clear_week(scenario, base_venue, scenario.standard_readiness)
    expedited_week = first_clear_week(scenario, base_venue, scenario.expedited_readiness)
    if "earliest_qualified_base_week" in extra:
        check("earliest_qualified_base_week", standard_week, extra["earliest_qualified_base_week"])
    if "first_clear_week" in extra:
        check("first_clear_week", standard_week, extra["first_clear_week"])
    if "expedite_completion_days_saved" in extra:
        saved = (date.fromisoformat(standard_week) - date.fromisoformat(expedited_week)).days if standard_week and expedited_week else None
        check("expedite_completion_days_saved", saved, extra["expedite_completion_days_saved"])
    if scenario.selected_week[1] not in week_starts() or scenario.selected_week[0] not in scenario.venue_by_id:
        problems.append(f"selected week {scenario.selected_week} is not on the venue calendar")
    blocks = [b for b in scenario.busy_blocks if b.person_id == scenario.conflicted_person_id and is_hard(b.kind) and b.start <= scenario.freebusy_query["end_date"] and b.end >= scenario.freebusy_query["start_date"]]
    if not blocks:
        problems.append(f"{scenario.conflicted_person_id} has no hard conflict inside the free/busy query range")
    if scenario.conflicted_person_id not in {a.person_id for a in scenario.attendees}:
        problems.append(f"{scenario.conflicted_person_id} is not on the attendee list")
    people = scenario.person_by_id
    for attendee in scenario.attendees:
        if attendee.person_id not in people:
            problems.append(f"attendee {attendee.person_id} is not in the scenario cast")
    for event in (scenario.event, *scenario.other_events):
        if event.organizer_id not in people:
            problems.append(f"organizer {event.organizer_id} of {event.event_id} is not in the scenario cast")
        if event.venue_id not in scenario.venue_by_id:
            problems.append(f"{event.event_id} uses venue {event.venue_id} outside the scenario")
    if problems:
        raise ValueError(f"{scenario.task_id} scenario data disagrees with its declared numbers:\n  " + "\n  ".join(problems))


# --------------------------------------------------------------------------- #
# Seed tables
# --------------------------------------------------------------------------- #


def _event_row(event: Any) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "title": event.title,
        "organizer_id": event.organizer_id,
        "start_date": event.start,
        "end_date": event.end,
        "session_days": event.session_days,
        "venue_id": event.venue_id,
        "location": event.location,
        "status": event.status,
        "agenda_doc_id": event.agenda_doc_id,
        "budget_line_id": event.budget_line_id,
        "cost_center": event.cost_center,
        "description": event.description,
        "revision": 1,
        "last_updated": "2026-06-05T16:30:00",
    }


def _line_row(line: Any) -> dict[str, Any]:
    return {
        "line_id": line.line_id,
        "cost_center": line.cost_center,
        "name": line.name,
        "fiscal_period": line.fiscal_period,
        "owner_id": line.owner_id,
        "approved_usd": float(line.approved),
        "committed_usd": float(line.committed),
        "reserved_usd": float(line.reserved),
        "adjustment_ceiling_usd": float(line.ceiling),
        "status": line.status,
        "note": line.note or None,
        "revision": 1,
        "last_updated": "2026-06-05T18:00:00",
    }


def _policy_rows() -> list[dict[str, Any]]:
    return [
        {"policy_id": CURRENT_POLICY_ID, "code": POLICY_CODE, "version": "v5", "title": "Travel & Events Policy TE-07 v5", "status": "current", "effective_from": "2026-03-02", "superseded_by": None, "parameters_json": json.dumps(CURRENT_PARAMETERS, sort_keys=True)},
        {"policy_id": SUPERSEDED_POLICY_ID, "code": POLICY_CODE, "version": "2024", "title": "Travel & Events Policy TE-07 2024 edition", "status": "superseded", "effective_from": "2024-01-15", "superseded_by": CURRENT_POLICY_ID, "parameters_json": json.dumps(SUPERSEDED_PARAMETERS, sort_keys=True)},
    ]


def seed_tables(scenario: Scenario, drive_files: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grid = week_grid(scenario)
    return {
        "users": [dict(row) for row in USERS],
        "offices": [dict(row) for row in OFFICES],
        "rooms": [dict(row) for row in ROOMS],
        "people": [{"person_id": p.person_id, "name": p.name, "email": p.email, "title": p.title, "team": p.team, "office_id": p.office_id, "employment": p.employment} for p in scenario.people],
        "venues": [
            {"venue_id": v.venue_id, "name": v.name, "city": v.city, "country": v.country, "local_office_id": v.local_office_id, "capacity": v.capacity, "hold_business_days": v.hold_business_days, "deposit_pct": v.deposit_pct, "events_director": v.events_director, "note": v.note or None}
            for v in scenario.venues
        ],
        "budget_lines": [_line_row(line) for line in (scenario.budget_line, *scenario.other_lines)],
        "documents": [{"doc_id": scenario.agenda.doc_id, "title": scenario.agenda.title, "folder": scenario.agenda.folder, "current_revision": scenario.agenda.current.revision, "modified_time": scenario.agenda.current.modified_time}],
        "document_revisions": [
            {"revision_id": r.revision_id, "doc_id": scenario.agenda.doc_id, "revision": r.revision, "status": r.status, "modified_time": r.modified_time, "modified_by": r.modified_by, "body": r.body, "metadata_json": json.dumps({"session_days": r.session_days, "status": r.status, "note": r.note}, sort_keys=True)}
            for r in scenario.agenda.revisions
        ],
        "events": [_event_row(event) for event in (scenario.event, *scenario.other_events)],
        "event_attendees": [
            {"attendee_id": f"ATT-{scenario.ordinal:03d}-{index:02d}", "event_id": scenario.event.event_id, "person_id": a.person_id, "required": int(a.required), "response": a.response, "note": a.note or None}
            for index, a in enumerate(scenario.attendees, start=1)
        ],
        "busy_blocks": [{"block_id": b.block_id, "person_id": b.person_id, "start_date": b.start, "end_date": b.end, "kind": b.kind, "title": b.title, "transparency": b.transparency} for b in scenario.busy_blocks],
        "venue_weeks": [
            {"week_id": week_id(venue_id, week), "venue_id": venue_id, "week_start": week, "status": entry["status"], "note": entry["note"] or None, "hold_id": entry["hold_id"]}
            for (venue_id, week), entry in sorted(grid.items())
        ],
        "venue_quotes": [
            {"quote_id": q.quote_id, "venue_id": q.venue_id, "event_id": q.event_id, "reference": q.reference, "week_start": q.week_start, "days": q.days, "total_usd": float(q.total), "deposit_usd": float(q.deposit), "issued_on": q.issued_on, "valid_until": q.valid_until, "status": q.status, "note": q.note or None}
            for q in scenario.quotes
        ],
        "venue_holds": [
            {"hold_id": h.hold_id, "venue_id": h.venue_id, "event_id": h.event_id, "quote_id": h.quote_id, "week_start": h.week_start, "deposit_usd": float(h.deposit), "expires_on": h.expires_on, "status": h.status, "requested_by": "workplace_operations_coordinator", "created_at": h.created_at, "revision": 1}
            for h in scenario.seed_holds
        ],
        "travel_policies": _policy_rows(),
        "tmcs": [dict(row) for row in TMCS],
        "bookings": [
            {
                "booking_id": b.booking_id, "person_id": b.person_id, "event_id": b.event_id, "kind": b.kind, "tmc_id": b.tmc_id, "record_locator": b.record_locator, "origin_office_id": b.origin_office_id,
                "destination_city": b.destination_city, "travel_date": b.travel_date, "return_date": b.return_date, "fare_class": b.fare_class, "fare_usd": float(b.fare), "changeable": int(b.changeable),
                "change_fee_usd": float(b.change_fee), "refundable": int(b.refundable), "status": b.status, "note": b.note or None,
            }
            for b in scenario.bookings
        ],
        "ticketing_confirmations": [
            {"confirmation_id": c.confirmation_id, "tmc_id": c.tmc_id, "event_id": c.event_id, "reference": c.reference, "seats_available": c.seats_available, "group_fare_usd": float(c.group_fare), "standard_ticketing_date": c.standard_date, "rush_ticketing_date": c.rush_date, "rush_fee_usd": float(c.rush_fee), "valid_until": c.valid_until, "status": c.status, "note": c.note or None}
            for c in (scenario.confirmation, *scenario.other_confirmations)
        ],
        "booking_changes": [dict(row) for row in scenario.seed.get("changes", ())],
        "budget_adjustments": [dict(row) for row in scenario.seed.get("adjustments", ())],
        "spreadsheets": [{"spreadsheet_id": scenario.workbook.spreadsheet_id, "title": scenario.workbook.title, "folder": scenario.workbook.folder, "current_version": scenario.workbook.current.version, "modified_time": scenario.workbook.current.modified_time}],
        "spreadsheet_versions": [
            {"version_id": f"{scenario.workbook.spreadsheet_id}-V{v.version}", "spreadsheet_id": scenario.workbook.spreadsheet_id, "version": v.version, "status": v.status, "modified_time": v.modified_time, "modified_by": v.modified_by, "rows_json": json.dumps([list(row) for row in v.rows])}
            for v in scenario.workbook.versions
        ],
        "approvals": [
            {"approval_id": scenario.approval.approval_id, "subject": scenario.approval.subject, "approver_id": scenario.approval.approver_id, "approver_role": scenario.approval.approver_role, "status": "APPROVED", "granted_on": scenario.approval.granted_on, "scope_json": json.dumps(scenario.approval.scope, sort_keys=True)},
            {"approval_id": "AP-DK-0090", "subject": "Quarterly catering and room-supplies standing order", "approver_id": "U-ACHTERBERG", "approver_role": "events_and_workplace_manager", "status": "APPROVED", "granted_on": "2026-02-06", "scope_json": json.dumps({"category": "CATERING_SUPPLIES", "max_spend_usd": 9000}, sort_keys=True)},
        ],
        "messages": [
            {
                "message_id": scenario.email.message_id, "thread_id": scenario.email.thread_id, "channel": "email", "sender": scenario.email.sender, "recipients": scenario.email.recipients, "subject": scenario.email.subject, "sent_at": scenario.email.sent_at, "body": scenario.email.body,
                "attachments_json": json.dumps([{"name": name, "mime_type": "application/pdf"} for name in scenario.email.attachments]), "labels": f"{scenario.email.labels},{scenario.case_reference}",
            },
            {
                "message_id": f"MSG-{scenario.ordinal:04d}-00", "thread_id": f"THR-{scenario.ordinal:04d}-OPS", "channel": "email", "sender": "maren.achterberg@larkspur.example", "recipients": "workplace-ops@larkspur.example", "subject": "Weekly workplace note", "sent_at": "2026-06-05T08:00:00",
                "body": "Venue portal logins rotate on 2026-06-12. Hold expiries are on the shared calendar; no changes to the policy tables this week.", "attachments_json": "[]", "labels": "operations",
            },
        ],
        "chat_threads": [
            {"thread_id": scenario.chat.thread_id, "channel": scenario.chat.channel, "title": scenario.chat.title, "messages_json": json.dumps([{"author": author, "ts": ts, "text": text} for author, ts, text in scenario.chat.messages])},
            {"thread_id": f"CHAT-{scenario.ordinal:04d}-GEN", "channel": "#workplace-ops", "title": "General — badge access and catering", "messages_json": json.dumps([{"author": "Maren Achterberg", "ts": "2026-06-04T16:40:00", "text": "Reminder: log every venue hold and its expiry in the tracker."}])},
        ],
        "drive_files": drive_files,
        "evidence_files": evidence,
    }


# --------------------------------------------------------------------------- #
# Evidence room
# --------------------------------------------------------------------------- #


def _event_json(scenario: Scenario) -> str:
    rendered = desk_tools._event(_event_row(scenario.event))
    return json.dumps({"export": "calendar.events.get", "case_reference": scenario.case_reference, "record": rendered}, indent=2, sort_keys=True) + "\n"


def _attendee_csv(scenario: Scenario) -> str:
    people = scenario.person_by_id
    lines = ["person_id,name,title,team,office_id,timezone,required,response"]
    for attendee in scenario.attendees:
        person = people[attendee.person_id]
        lines.append(f"{person.person_id},{person.name},{person.title},{person.team},{person.office_id},{OFFICE_BY_ID[person.office_id]['timezone']},{'yes' if attendee.required else 'no'},{attendee.response}")
    return "\n".join(lines) + "\n"


def _directory_json(scenario: Scenario) -> str:
    people = [desk_tools._person({"person_id": p.person_id, "name": p.name, "email": p.email, "title": p.title, "team": p.team, "office_id": p.office_id, "employment": p.employment}, OFFICE_BY_ID[p.office_id]) for p in scenario.people]
    return json.dumps({"export": "directory.people.search + directory.offices.list", "case_reference": scenario.case_reference, "offices": [dict(row) for row in OFFICES], "people": people}, indent=2, sort_keys=True) + "\n"


def _quote_text(scenario: Scenario, quote: Any) -> str:
    venue = scenario.venue_by_id[quote.venue_id]
    return (
        f"{venue.name}\nQuote {quote.reference} (system reference {quote.quote_id})\nCustomer: {ORGANIZATION['name']}\nEvent: {scenario.event.title} ({scenario.event.event_id})\nCase reference: {scenario.case_reference}\n"
        f"Week: {quote.week_start} ({quote.days} billed days)\nTotal: USD {quote.total:,}\nDeposit on hold: USD {quote.deposit:,} ({venue.deposit_pct}%)\nIssued: {quote.issued_on}; valid until: {quote.valid_until}\nStatus: {quote.status}\n"
        f"Hold policy: holds run {venue.hold_business_days} business days; held, booked, and blackout weeks are released only by the events director ({venue.events_director}).\nNotes: {quote.note}\n"
    )


def _confirmation_text(scenario: Scenario) -> str:
    c = scenario.confirmation
    tmc = next(row for row in TMCS if row["tmc_id"] == c.tmc_id)
    return (
        f"{tmc['name']}\nGroup-desk ticketing confirmation {c.reference} (system reference {c.confirmation_id})\nCustomer: {ORGANIZATION['name']}, account {tmc['account_number']}\n"
        f"Case reference: {scenario.case_reference}\nEvent: {scenario.event.title} ({scenario.event.event_id})\nSeats the desk can issue on this confirmation: {c.seats_available}\nGroup fare per new ticket: USD {c.group_fare:.2f}\n"
        f"Standard queue ticketing date: {c.standard_date}\nRush queue ticketing date: {c.rush_date} (rush fee USD {c.rush_fee}, flat)\nValid until: {c.valid_until}\nNotes: {c.note}\n"
        "Re-issues carry the change fee recorded on the booking; basic fares are forfeited and re-issued as new tickets. Travellers receive confirmed itineraries the next business day after ticketing.\n"
    )


def _bookings_csv(scenario: Scenario) -> str:
    lines = ["booking_id,person_id,kind,tmc_id,record_locator,origin_office_id,destination_city,travel_date,return_date,fare_class,fare_usd,changeable,change_fee_usd,refundable,status,note"]
    for b in scenario.bookings:
        lines.append(f"{b.booking_id},{b.person_id},{b.kind},{b.tmc_id},{b.record_locator},{b.origin_office_id or ''},{b.destination_city},{b.travel_date},{b.return_date},{b.fare_class},{b.fare},{'yes' if b.changeable else 'no'},{b.change_fee},{'yes' if b.refundable else 'no'},{b.status},{b.note}")
    return "\n".join(lines) + "\n"


def _quotes_csv(scenario: Scenario) -> str:
    lines = ["quote_id,venue_id,reference,week_start,days,total_usd,deposit_usd,issued_on,valid_until,status,note"]
    for q in scenario.quotes:
        lines.append(f"{q.quote_id},{q.venue_id},{q.reference},{q.week_start},{q.days},{q.total},{q.deposit},{q.issued_on},{q.valid_until},{q.status},{q.note}")
    return "\n".join(lines) + "\n"


def _line_json(scenario: Scenario) -> str:
    rendered = desk_tools._line(_line_row(scenario.budget_line))
    return json.dumps({"export": "expense.budget_lines.get", "case_reference": scenario.case_reference, "record": rendered}, indent=2, sort_keys=True) + "\n"


def _agenda_markdown(scenario: Scenario) -> str:
    current = scenario.agenda.current
    return f"{current.body}\n---\nDocument {scenario.agenda.doc_id}, revision {current.revision} ({current.status}), modified {current.modified_time} by {current.modified_by}. Session days: {current.session_days}. Case {scenario.case_reference}.\n"


def _decoy_asset(scenario: Scenario) -> dict[str, Any]:
    doc = scenario.decoy_doc
    if doc.kind == "policy_superseded":
        return asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=MARKDOWN, content=scoped_markdown(SUPERSEDED_POLICY, task_id=scenario.task_id, case_reference=scenario.case_reference), preview="2024 policy edition retained for audit only; superseded by v5.")
    if doc.media_type == XLSX:
        return asset(doc.path, kind=doc.kind, title=doc.title, source="sheets_export", media_type=XLSX, rows=[list(row) for row in doc.rows or ()], preview="A superseded workbook snapshot that predates the current commitments.")
    if doc.kind == "stale_freebusy_export":
        return asset(doc.path, kind=doc.kind, title=doc.title, source="calendar_export", media_type=doc.media_type, content=scoped_csv(doc.content, task_id=scenario.task_id, case_reference=scenario.case_reference), preview="A free/busy export that predates the live calendar's hard conflicts.")
    if doc.kind == "agenda_superseded":
        return asset(doc.path, kind=doc.kind, title=doc.title, source="docs_export", media_type=MARKDOWN, content=scoped_markdown(doc.content, task_id=scenario.task_id, case_reference=scenario.case_reference), preview="A superseded agenda revision whose attendee list and session days no longer apply.")
    source = "venues_export" if doc.kind == "duplicate_quote" else "calendar_export" if doc.kind == "decoy_event" else "drive"
    return asset(doc.path, kind=doc.kind, title=doc.title, source=source, media_type=doc.media_type, content=doc.content, preview="A duplicate, stale, or similarly named record that must not drive the decision.")


def build_assets(scenario: Scenario) -> list[dict[str, Any]]:
    case = scenario.case_reference
    grid = week_grid(scenario)
    people = scenario.person_by_id
    required_ids = {a.person_id for a in scenario.required_attendees}
    assets: list[dict[str, Any]] = [
        asset("policy/travel-and-events-policy-te-07.md", kind="policy", title="Travel & Events Policy TE-07 v5 (effective)", source="drive", media_type=MARKDOWN,
              content=scoped_markdown(effective_policy(AS_OF), task_id=scenario.task_id, case_reference=case), preview="Attendance, booking-change, viability, budget, and authority rules in force."),
    ]
    if scenario.decoy_doc.kind != "policy_superseded":
        assets.append(
            asset("policy/superseded-travel-and-events-policy-2024.md", kind="policy_superseded", title="Travel & Events Policy TE-07 2024 edition (superseded)", source="drive", media_type=MARKDOWN,
                  content=scoped_markdown(SUPERSEDED_POLICY, task_id=scenario.task_id, case_reference=case), preview="2024 policy edition retained for audit only; superseded by v5.")
        )
    assets.append(_decoy_asset(scenario))
    assets.extend(
        [
            asset(f"calendar/event-{scenario.event.event_id}.json", kind="event_export", title=f"Calendar event {scenario.event.event_id} (export)", source="calendar_export", media_type=JSON, content=_event_json(scenario),
                  preview="The event in scope: dates, session days, venue, organizer, linked agenda and budget line, revision."),
            asset(f"calendar/attendees-{scenario.event.event_id}.csv", kind="attendee_roster", title=f"Attendee roster for {scenario.event.event_id}", source="calendar_export", media_type=CSV, content=_attendee_csv(scenario),
                  preview="Required and optional attendees with home office and timezone."),
            asset("calendar/freebusy-required-attendees-2026-06-08.xlsx", kind="freebusy_workbook", title="Free/busy blocks of the required attendees, 2026-06-15 to 2026-08-30", source="calendar_workbook", media_type=XLSX,
                  rows=[["person_id", "name", "start", "end", "kind", "title", "transparency", "hard"], *[[b.person_id, people[b.person_id].name, b.start, b.end, b.kind, b.title, b.transparency, "yes" if is_hard(b.kind) else "no"] for b in scenario.busy_blocks if b.person_id in required_ids]],
                  preview="Every busy block on a required attendee's calendar with the policy's hard-conflict flag."),
            asset("directory/people-directory-export.json", kind="directory_export", title="People directory export (offices and timezones)", source="directory_export", media_type=JSON, content=_directory_json(scenario),
                  preview="Home offices and timezones behind the attendee list."),
            asset("venues/availability-2026-06-15.xlsx", kind="venue_calendar", title="Venue availability by week, twelve weeks from 2026-06-15", source="venues_workbook", media_type=XLSX,
                  rows=[["venue_id", "week_start", "status", "note"], *[[venue_id, week, entry["status"], entry["note"] or ""] for (venue_id, week), entry in sorted(grid.items())]],
                  preview="Every venue week with open / held / booked / blackout status."),
            asset(f"venues/quote-{scenario.target_quote.reference}.pdf", kind="venue_quote", title=f"Venue quote {scenario.target_quote.reference}", source="email_attachment", media_type=PDF, content=_quote_text(scenario, scenario.target_quote),
                  preview="Week, billed days, total, deposit, validity, and hold policy of the current quote."),
            asset(f"venues/quotes-register-{scenario.event.event_id}.csv", kind="quote_register", title=f"Venue quotes attached to {scenario.event.event_id}", source="venues_export", media_type=CSV, content=_quotes_csv(scenario),
                  preview="Every quote on the event with its status: current, contracted, superseded, or indicative."),
            asset(f"travel/bookings-register-{scenario.event.event_id}.csv", kind="bookings_register", title=f"Bookings register for {scenario.event.event_id}", source="travel_export", media_type=CSV, content=_bookings_csv(scenario),
                  preview="Every booking with fare class, changeability, change fee, and refundability."),
            asset(f"travel/ticketing-confirmation-{scenario.confirmation.reference}.pdf", kind="tmc_confirmation", title=f"Group-desk ticketing confirmation {scenario.confirmation.reference}", source="email_attachment", media_type=PDF, content=_confirmation_text(scenario),
                  preview="Seats, group fare, standard and rush ticketing dates, rush fee, and validity."),
            asset("travel/policy-parameters-te-07-v5.json", kind="policy_parameters", title="Travel policy TE-07 v5 — structured parameters", source="travel_export", media_type=JSON,
                  content=json.dumps({"policy_id": CURRENT_POLICY_ID, "case_reference": case, "parameters": CURRENT_PARAMETERS}, indent=2, sort_keys=True) + "\n",
                  preview="Per-diem, fare caps, contingency bands, thresholds, and conflict kinds as the travel desk serves them."),
            asset(f"expense/budget-line-{scenario.budget_line.line_id}.json", kind="budget_line_export", title=f"Budget line {scenario.budget_line.line_id} (export)", source="expense_export", media_type=JSON, content=_line_json(scenario),
                  preview="Approved, committed, reserved, gross remaining, and the adjustment ceiling."),
            asset(f"sheets/{scenario.workbook.spreadsheet_id}-v{scenario.workbook.current.version}.xlsx", kind="budget_workbook", title=f"{scenario.workbook.title} (v{scenario.workbook.current.version}, current)", source="sheets_export", media_type=XLSX,
                  rows=[list(row) for row in scenario.workbook.current.rows], preview="The current workbook version mirroring the budget system's lines."),
            asset(f"docs/agenda-{scenario.event.event_id}-rev{scenario.agenda.current.revision}.md", kind="agenda_current", title=f"{scenario.agenda.title} (rev {scenario.agenda.current.revision}, current)", source="docs_export", media_type=MARKDOWN, content=_agenda_markdown(scenario),
                  preview="The current agenda revision: session days and the required attendee roles."),
            asset(f"mail/{scenario.email.thread_id}.eml", kind="email", title=scenario.email.subject, source="mail", media_type=EML,
                  content=eml(from_addr=scenario.email.sender, to_addr=scenario.email.recipients, subject=scenario.email.subject, date=scenario.email.sent_at, message_id=f"{scenario.email.message_id}@larkspur.example", body=scenario.email.body, attachments=list(scenario.email.attachments)),
                  preview="The request and the control date, in the requester's words."),
            asset(f"chat/{scenario.chat.thread_id}.json", kind="chat_thread", title=scenario.chat.title, source="chat", media_type=JSON,
                  content=json.dumps({"thread_id": scenario.chat.thread_id, "channel": scenario.chat.channel, "title": scenario.chat.title, "messages": [{"author": a, "ts": t, "text": x} for a, t, x in scenario.chat.messages]}, indent=2, sort_keys=True) + "\n",
                  preview="Team chat with venue, fare, and authority remarks."),
            asset(f"approvals/approval-{scenario.approval.approval_id}.json", kind="approval", title=f"Approval record {scenario.approval.approval_id}", source="approvals_export", media_type=JSON,
                  content=json.dumps({"approval_id": scenario.approval.approval_id, "case_reference": case, "subject": scenario.approval.subject, "approver_id": scenario.approval.approver_id, "approver_role": scenario.approval.approver_role, "status": "APPROVED", "granted_on": scenario.approval.granted_on, "scope": scenario.approval.scope}, indent=2, sort_keys=True) + "\n",
                  preview="Exactly what is approved, for which event, and what is not."),
            asset(f"exports/starting-state-{scenario.task_id}.json", kind="starting_state", title="Starting-state export (events, holds, changes, adjustments)", source="calendar_export", media_type=JSON,
                  content=json.dumps(
                      {
                          "case_reference": case, "as_of": AS_OF,
                          "events": [{"event_id": e.event_id, "start": e.start, "end": e.end, "venue_id": e.venue_id, "status": e.status, "revision": 1} for e in (scenario.event, *scenario.other_events)],
                          "venue_holds": [{"hold_id": h.hold_id, "venue_id": h.venue_id, "event_id": h.event_id, "week_start": h.week_start, "status": h.status} for h in scenario.seed_holds],
                          "booking_changes": [{"change_id": row["change_id"], "event_id": row["event_id"], "status": row["status"]} for row in scenario.seed.get("changes", ())],
                          "budget_adjustments": [{"adjustment_id": row["adjustment_id"], "line_id": row["line_id"], "amount_usd": row["amount_usd"], "status": row["status"]} for row in scenario.seed.get("adjustments", ())],
                          "note": "Snapshot before any action; row order does not indicate applicability.",
                      },
                      indent=2, sort_keys=True,
                  ) + "\n",
                  preview="Snapshot of calendar, venue, travel, and budget state before any action."),
        ]
    )
    for doc in scenario.docs:
        if doc.media_type == XLSX:
            assets.append(asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=XLSX, rows=[list(row) for row in doc.rows or ()], preview=doc.title))
        else:
            content = scoped_csv(doc.content, task_id=scenario.task_id, case_reference=case) if doc.media_type == CSV else scoped_markdown(doc.content, task_id=scenario.task_id, case_reference=case) if doc.media_type == MARKDOWN else doc.content
            assets.append(asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=doc.media_type, content=content, preview=doc.title))
    assets.extend(
        quality_support_assets(
            task_id=scenario.task_id, ordinal=scenario.ordinal, case_reference=case, family_slug=FAMILY_SLUG, family_name="DeskOps", organization_name=ORGANIZATION["name"],
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
        return "Workplace Operations/Policies"
    if record["kind"] == "policy_superseded":
        return "Workplace Operations/Policies/Archive"
    if record["kind"] == "agenda_superseded":
        return "Workplace Operations/Agendas/Archive"
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
        files.append({"file_id": file_id, "name": record["path"].rsplit("/", 1)[-1], "mime_type": record["media_type"], "modified_time": "2026-06-05T17:30:00", "folder": _folder(scenario, record), "content": record["content"], "sha256": record["sha256"]})
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
        {"id": "authoritative_identity", "sources": ["calendar", "mail"], "statement": f"{scenario.case_reference}: {notes['identity']}; the effective revision is {scenario.revision}.",
         "rubric": f"Located {scenario.item} using immutable identifiers and preserved effective revision {scenario.revision}: {notes['identity']}."},
        {"id": "effective_requirement", "sources": ["calendar", "docs", "drive"], "statement": f"The event, the current agenda revision, and the policy establish {labels.scope_label} = {numbers['scope']} {labels.unit}: {notes['requirement']}. The control date is {scenario.business_need} ({scenario.business_need_reason}).",
         "rubric": f"Applied the event, the current agenda revision, and the policy to establish {numbers['scope']} {labels.unit} for {labels.scope_label}, with control date {scenario.business_need}."},
        {"id": "eligible_coverage", "sources": ["travel", "expense", "calendar", "venues"], "statement": f"{notes['coverage']}; eligibility requires netting the exclusions rather than trusting a header total.",
         "rubric": f"Reconciled {numbers['observed']} observed less {numbers['excluded']} excluded to {numbers['eligible']} supported {labels.unit} for {labels.eligible_label}."},
        {"id": "conditional_external_recovery", "sources": ["travel", "mail"], "statement": f"{labels.external_label}: {notes['external']}; a group-desk confirmation alone proves neither viability nor approval.",
         "rubric": f"Used the independently confirmed {scenario.expedited_readiness} rush-queue confirmation input for {accelerated.id}, then separately derived its {accelerated.completion} operating outcome under {labels.constraint_label} instead of treating a travel vendor's promise as authorization or a completion date."},
        {"id": "finite_capacity", "sources": ["venues", "calendar"], "statement": f"{labels.capacity_label}: {notes['capacity']}; held, booked, and blackout weeks and protected commitments cannot be displaced.",
         "rubric": f"Applied {labels.capacity_label} to derive the three option outcomes without displacing a held, booked, or blackout week or a protected commitment."},
        {"id": "approval_scope", "sources": ["approvals", "chat"], "statement": f"{notes['approval']}. The approval does not select an option in advance and does not authorize {unauthorized.id}.",
         "rubric": f"Applied {scenario.approval.approval_id} only to {selected.id} and {scenario.item}; kept {unauthorized.id} outside current authority."},
        {"id": "business_impact", "sources": ["mail", "chat"], "statement": f"{notes['impact']}; a faster or broader action has value only if it remains inside {labels.constraint_label}.",
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
        "id": f"investigation_{number:02d}",
        "milestone_id": milestone,
        "description": description,
        "weight": weight,
        "before_primary_mutation": True,
        "any_of": [{"tool": tool, "arguments": arguments, "match": "result_contains", "expected_result_contains": expected}],
    }


def build_investigations(scenario: Scenario, file_ids: dict[str, str]) -> list[dict[str, Any]]:
    case = scenario.case_reference
    event = scenario.event
    venue = scenario.target_venue
    policy_id = file_ids["policy/travel-and-events-policy-te-07.md"]
    approval_id = file_ids[f"approvals/approval-{scenario.approval.approval_id}.json"]
    event_file_id = file_ids[f"calendar/event-{event.event_id}.json"]
    first_required = scenario.required_attendees[0].person_id
    first_booking = scenario.bookings[0].booking_id
    current_revision = scenario.agenda.current
    tmc_name = next(row["name"] for row in TMCS if row["tmc_id"] == scenario.confirmation.tmc_id)
    correlation_tool, correlation_args, correlation_expected = scenario.correlation_read
    investigations = [
        _investigation(1, "investigation.scope", f"Established the isolated {case} scope, immutable handles, mounted systems, and evidence index before investigating {scenario.item}.", CONTEXT_TOOL, {}, {"reference_records": {"case_reference": case}}),
        _investigation(2, "investigation.scope", f"Located the task-scoped correspondence for {case} by searching the mailbox before opening any message; did not rely on a guessed sender or filename.", "mail.messages.list", {"q": case}, {"messages": [{"id": scenario.email.message_id}]}),
        _investigation(3, "investigation.scope", f"Resolved {case} to the immutable calendar event through a search rather than a title match against a similarly named event.", "calendar.events.list", {"q": case}, {"events": [{"id": event.event_id}]}),
        _investigation(4, "investigation.scope", f"Listed the {case} case folder on the shared drive and identified the approval record and the event export by immutable file id.", "drive.files.list", {"q": case}, {"files": [{"id": approval_id}, {"id": event_file_id}]}),
        _investigation(5, "investigation.scope", "Listed the policy folder and distinguished the effective TE-07 v5 policy from the superseded 2024 edition by file identity, not title.", "drive.files.list", {"q": POLICY_QUERY}, {"files": [{"id": policy_id}]}),
        _investigation(6, "investigation.requirements", f"Read the calendar event {event.event_id}: dates, session days, venue, organizer, linked agenda and budget line, and revision.", "calendar.events.get", {"event_id": event.event_id}, {"id": event.event_id, "status": event.status}),
        _investigation(7, "investigation.requirements", f"Listed the attendees of {event.event_id} with their required flag and home office before sizing who travels.", "calendar.attendees.list", {"event_id": event.event_id}, {"attendees": [{"person_id": first_required}]}),
        _investigation(8, "investigation.requirements", f"Read the office directory for home offices and timezones and identified {venue.local_office_id} as the venue's local office whose attendees need no itinerary.", "directory.offices.list", {}, {"offices": [{"office_id": venue.local_office_id}]}),
        _investigation(9, "investigation.requirements", "Exported the effective TE-07 v5 policy for the attendance, booking-change, viability, budget, and authority rules; did not apply the superseded 2024 edition.", "drive.files.export", {"file_id": policy_id}, {"file_id": policy_id}),
        _investigation(10, "investigation.requirements", f"Read the current travel policy version {CURRENT_POLICY_ID} from the travel desk for its structured parameters (per-diem, fare caps, contingency bands, thresholds, conflict kinds).", "travel.policies.get", {"policy_id": CURRENT_POLICY_ID}, {"policy_id": CURRENT_POLICY_ID, "status": "current"}),
        _investigation(11, "investigation.requirements", f"Listed the revisions of agenda {scenario.agenda.doc_id} and separated the current revision from the superseded one by status.", "docs.revisions.list", {"doc_id": scenario.agenda.doc_id}, {"revisions": [{"revision_id": current_revision.revision_id, "status": "current"}]}),
        _investigation(12, "investigation.requirements", f"Read the current agenda revision {current_revision.revision_id} for the session days and the required attendee roles.", "docs.revisions.get", {"revision_id": current_revision.revision_id}, {"revision_id": current_revision.revision_id, "status": "current"}),
        _investigation(13, "investigation.constraints", f"Read {venue.name}'s availability calendar from {scenario.availability_query['start_week']} to find the open weeks that displace no held, booked, or blackout week.", "venues.availability.list", dict(scenario.availability_query), {"weeks": [{"id": scenario.selected_week_id, "status": "open"}]}),
        _investigation(14, "investigation.constraints", f"Queried the required attendees' free/busy calendar from {scenario.freebusy_query['start_date']} and separated hard conflicts from soft blocks before judging any week.", "calendar.freebusy.query", {"event_id": event.event_id, **scenario.freebusy_query}, {"calendars": [{"person_id": scenario.conflicted_person_id, "busy": [{"hard": True}]}]}),
        _investigation(15, "investigation.constraints", f"Listed the bookings on {event.event_id} with fare class, changeability, change fee, and status before netting what can be re-issued.", "travel.bookings.list", {"event_id": event.event_id}, {"bookings": [{"booking_id": first_booking}]}),
        _investigation(16, "investigation.constraints", f"Read the external travel vendor's group-desk confirmation {scenario.confirmation.confirmation_id} ({tmc_name}) for the independently confirmed standard and rush ticketing dates, seats, group fare, and rush fee.", "travel.confirmations.get", {"confirmation_id": scenario.confirmation.confirmation_id}, {"confirmation_id": scenario.confirmation.confirmation_id, "standard_ticketing_date": scenario.confirmation.standard_date}),
        _investigation(17, "investigation.constraints", f"Read the current venue quote {scenario.target_quote.quote_id} for its week, billed days, total, deposit, and validity; did not use a superseded or indicative quote.", "venues.quotes.get", {"quote_id": scenario.target_quote.quote_id}, {"quote_id": scenario.target_quote.quote_id, "status": "current"}),
        _investigation(18, "investigation.constraints", f"Read budget line {scenario.budget_line.line_id} for approved, committed, reserved, and the adjustment ceiling before treating any balance as headroom.", "expense.budget_lines.get", {"line_id": scenario.budget_line.line_id}, {"line_id": scenario.budget_line.line_id}),
        _investigation(19, "investigation.authority", f"Read approval {scenario.approval.approval_id} for its exact scope: event, venue, weeks, spend, queue, and what it does not cover.", "approvals.get", {"approval_id": scenario.approval.approval_id}, {"approval_id": scenario.approval.approval_id}),
        _investigation(20, "investigation.authority", "Exported the approval record on the drive and confirmed it matches the workflow record before relying on it.", "drive.files.export", {"file_id": approval_id}, {"file_id": approval_id}),
        _investigation(21, "investigation.erp_correlation", f"Read the request message {scenario.email.message_id} for the documented control date and the business need in the requester's words.", "mail.messages.get", {"message_id": scenario.email.message_id}, {"id": scenario.email.message_id}),
        _investigation(22, "investigation.erp_correlation", f"Read the team chat thread {scenario.chat.thread_id} for venue, fare, and authority remarks that qualify the system records.", "chat.threads.get", {"thread_id": scenario.chat.thread_id}, {"thread_id": scenario.chat.thread_id}),
        _investigation(23, "investigation.erp_correlation", f"Read the current version of budget workbook {scenario.workbook.spreadsheet_id} and reconciled it to the budget system's line rather than a superseded snapshot.", "sheets.values.get", {"spreadsheet_id": scenario.workbook.spreadsheet_id, "version": scenario.workbook.current.version}, {"spreadsheet_id": scenario.workbook.spreadsheet_id, "version": scenario.workbook.current.version, "status": "current"}),
        _investigation(24, "investigation.erp_correlation", "Correlated the existing holds, changes, quotes, or adjustments that fix the starting state by immutable id.", correlation_tool, dict(correlation_args), dict(correlation_expected)),
    ]
    investigations.extend(quality_support_investigations(start_number=len(investigations) + 1, file_ids=file_ids, make_investigation=_investigation, case_reference=case, subject_id=scenario.item))
    return investigations


def build_oracle_steps(scenario: Scenario, investigations: list[dict[str, Any]], model: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [{"phase": "context", "tool": CONTEXT_TOOL, "arguments": {}, "control": True}]
    order = [2, 21, 3, 6, 7, 8, 4, 5, 9, 10, 11, 12, 23, 13, 14, 15, 16, 17, 18, 19, 20, 22, 24]
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
            "arguments": {"recipient": scenario.collaboration["recipient"], "subject": scenario.collaboration["subject"], "body": scenario.collaboration["body"], "related_event_id": scenario.event.event_id, "related_line_id": scenario.budget_line.line_id},
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
            "payload_text_contains": [selected, completion],
            "payload_text_any_of": [[scenario.case_reference, scenario.event.event_id, scenario.target_venue.venue_id]],
            "weight": 1.5,
        },
        {
            "id": "containment_01", "milestone_id": "containment.scope",
            "description": f"Made exactly two state changes for {scenario.case_reference}: the primary change and the stakeholder draft; no additional hold, booking change, adjustment, or calendar move.",
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
        facts=model["facts"], primary_outcome=primary.outcome_label, correlated_systems=["calendar", "venues", "travel", "expense", "docs", "sheets", "mail", "chat"],
    )
    rubric = build_rubric_milestones(descriptions=descriptions, investigations=investigations, calculations=model["calculations"], assertions=assertions, answer_checks=checks, post_write_verifications=[readback])
    option_ids = [option["id"] for option in model["options"]]
    decoy_path = scenario.decoy_doc.path
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
        "oracle_steps": steps,
        "sequence_signature": sequence_signature(steps),
        "allowed_write_tables": sorted({primary.table, *primary.extra_tables, "note_drafts", "mutations", "answers", "audit_log"}),
        "rubric_milestones": rubric,
        "negative_controls": {"unauthorized_write": dict(scenario.unauthorized_write), "wrong_evidence": {"tool": "drive.files.export", "arguments": {"file_id": file_ids[decoy_path]}}},
        "reference_records": {
            "case_reference": scenario.case_reference,
            "calendar": {"event_id": scenario.event.event_id, "event_search": {"tool": "calendar.events.list", "arguments": {"q": scenario.case_reference}}, "freebusy_window": scenario.freebusy_query},
            "mail": {"search_query": scenario.case_reference},
            "drive": {"case_folder_query": scenario.case_reference, "policy_query": POLICY_QUERY},
            "venues": {"venue_id": scenario.target_venue.venue_id, "calendar_window": scenario.availability_query, "quote_id": scenario.target_quote.quote_id},
            "travel": {"confirmation_id": scenario.confirmation.confirmation_id, "policy_id": CURRENT_POLICY_ID},
            "expense": {"line_id": scenario.budget_line.line_id},
            "docs": {"agenda_doc_id": scenario.agenda.doc_id},
            "sheets": {"spreadsheet_id": scenario.workbook.spreadsheet_id},
            "approvals": {"approval_id": scenario.approval.approval_id},
            "chat": {"thread_id": scenario.chat.thread_id},
        },
        "starting_records": [
            *[{"system": "calendar", "resource_type": "Event", "resource_id": e.event_id, "status": e.status} for e in (scenario.event, *scenario.other_events)],
            *[{"system": "venues", "resource_type": "VenueHold", "resource_id": h.hold_id, "status": h.status} for h in scenario.seed_holds],
            *[{"system": "travel", "resource_type": "BookingChange", "resource_id": row["change_id"], "status": row["status"]} for row in scenario.seed.get("changes", ())],
            *[{"system": "expense", "resource_type": "BudgetAdjustment", "resource_id": row["adjustment_id"], "status": row["status"]} for row in scenario.seed.get("adjustments", ())],
        ],
        "evaluation": {"metric": "HubScore", "strict_pass": "every rubric milestone passes", "llm_judge_calls": 0},
        "workflow": {"reads": len([s for s in steps if s["phase"] in {"context", "investigation"}]), "writes": 2, "readbacks": 1, "answer_fields": len(answer)},
    }


def build_tasks() -> list[dict[str, Any]]:
    return [build_task(scenario) for scenario in scenarios()]


__all__ = ["BENCHMARK", "FAMILY_SLUG", "FAMILY_VERSION", "basis_completion", "build_task", "build_tasks", "first_clear_week", "traveller_flights", "verify_numbers"]
