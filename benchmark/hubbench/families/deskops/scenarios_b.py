"""DeskOps scenarios 005-008 (quantity, schedule, plan, quantity)."""

from __future__ import annotations

import json

from ...engine.assets import CSV, JSON, MARKDOWN, PDF
from ...engine.decision import APPROVED, NOT_RECOMMENDED, NOT_SUPPORTED, UNAUTHORIZED, Labels, Option, criterion
from .scenarios_a import CONTINGENCY_DOC, PEOPLE, PER_DIEM_DOC, POLICY_DECOY, VENUES, agenda, flight, optional, required, stale_freebusy_doc, workbook
from .specs import OPS_EMAIL, Approval, BudgetLine, BusyBlock, Chat, Confirmation, Doc, Email, Event, Person, PrimaryWrite, Quote, Scenario, SeedHold, WeekStatus

ENGINEERS = tuple(
    Person(person_id, name, email, title, "Engineering", "OFF-BRS")
    for person_id, name, email, title in (
        ("P-ENG01", "Priya Venkataraman", "priya.venkataraman@larkspur.example", "Senior engineer"),
        ("P-ENG02", "Oskar Lindgren", "oskar.lindgren@larkspur.example", "Senior engineer"),
        ("P-ENG03", "Amara Nwosu", "amara.nwosu@larkspur.example", "Engineer"),
        ("P-ENG04", "Declan Murphy", "declan.murphy@larkspur.example", "Engineer"),
        ("P-ENG05", "Yara Haddad", "yara.haddad@larkspur.example", "Platform engineer"),
        ("P-ENG06", "Mateusz Kowalczyk", "mateusz.kowalczyk@larkspur.example", "Platform engineer"),
        ("P-ENG07", "Leila Farahani", "leila.farahani@larkspur.example", "Site reliability engineer"),
        ("P-ENG08", "Callum Fraser", "callum.fraser@larkspur.example", "Engineering manager"),
    )
)
CAST = {**PEOPLE, **{person.person_id: person for person in ENGINEERS}}


def cast(*ids: str) -> tuple[Person, ...]:
    return tuple(CAST[person_id] for person_id in ids)


# --------------------------------------------------------------------------- #
# 005 — quantity: size the booking changes for the analytics guild offsite
# --------------------------------------------------------------------------- #


def scenario_005() -> Scenario:
    event = Event(
        "EVT-ANA", "Analytics guild offsite", "P-OSEI", "2026-06-30", "2026-07-02", 3, "VEN-HARROW", "Harrow Court Conference Estate, Bath",
        "DOC-AGD-ANA", "BL-ANA-TRV-26H2", "CC-ANALYTICS",
        "Case DESK-0005 — Harrow Court withdrew the week of 2026-06-29 (substation power works); the estate offers 2026-07-13 and 2026-07-27.",
    )
    finance = Event("EVT-FIN-Q3", "Finance Q3 offsite", "P-OSEI", "2026-08-11", "2026-08-12", 2, "VEN-QUAYSIDE", "Quayside Assembly Rooms, Bristol", None, None, "CC-FINANCE", "Booking change CHG-8800 pending with the group desk.")
    attendees = (*required("P-OSEI", "P-FONSECA", "P-CARVALHO", "P-PARK", "P-NAKAGAWA", "P-PETROV", "P-ALDANA", "P-NGUYEN", "P-TAN"), *optional("P-WRONA"))
    bookings = (
        flight("BK-7501", "P-FONSECA", event.event_id, "OFF-LIS", "Bristol", "2026-06-29", "2026-07-02", "flex economy", 240, 95),
        flight("BK-7502", "P-CARVALHO", event.event_id, "OFF-LIS", "Bristol", "2026-06-29", "2026-07-02", "flex economy", 240, 95),
        flight("BK-7503", "P-PARK", event.event_id, "OFF-TOR", "Bristol", "2026-06-28", "2026-07-03", "flex economy", 980, 250),
        flight("BK-7504", "P-NAKAGAWA", event.event_id, "OFF-TOR", "Bristol", "2026-06-28", "2026-07-03", "basic economy", 640, 0, note="basic fare: not changeable; forfeited on a move"),
        flight("BK-7505", "P-PETROV", event.event_id, "OFF-DEN", "Bristol", "2026-06-28", "2026-07-03", "flex economy", 1040, 250),
        flight("BK-7506", "P-ALDANA", event.event_id, "OFF-DEN", "Bristol", "2026-06-28", "2026-07-03", "flex economy", 1040, 250),
        flight("BK-7507", "P-NGUYEN", event.event_id, "OFF-SGP", "Bristol", "2026-06-27", "2026-07-03", "basic economy", 1180, 0, note="basic fare: not changeable; forfeited on a move"),
        flight("BK-7508", "P-TAN", event.event_id, "OFF-SGP", "Bristol", "2026-06-27", "2026-07-03", "flex economy", 1450, 320),
    )
    busy = (
        BusyBlock("BB-5001", "P-PARK", "2026-06-30", "2026-07-01", "customer_commitment", "Harborline data review (Toronto)"),
        BusyBlock("BB-5002", "P-TAN", "2026-08-03", "2026-08-07", "leave", "Annual leave"),
        BusyBlock("BB-5003", "P-OSEI", "2026-07-15", "2026-07-15", "recurring", "Analytics guild sync (recurring)", "transparent"),
        BusyBlock("BB-5004", "P-PETROV", "2026-07-28", "2026-07-28", "focus_time", "Pipeline refactor (focus)", "transparent"),
        BusyBlock("BB-5005", "P-NGUYEN", "2026-07-14", "2026-07-14", "tentative", "Tentative: vendor demo", "transparent"),
    )
    weeks = (
        WeekStatus("VEN-HARROW", "2026-06-29", "blackout", "substation power works — week withdrawn by the venue"),
        WeekStatus("VEN-HARROW", "2026-07-13", "open", "open"),
        WeekStatus("VEN-HARROW", "2026-07-27", "open", "open"),
        WeekStatus("VEN-HARROW", "2026-08-03", "open", "open"),
        WeekStatus("VEN-QUAYSIDE", "2026-08-10", "booked", "Larkspur finance Q3 offsite"),
    )
    quotes = (
        Quote("QT-HAR-4433", "VEN-HARROW", event.event_id, "HC-4433", "2026-07-27", 3, 18400, 4600, "2026-06-05", "2026-06-19", note="re-dated exclusive hire at the contracted total"),
        Quote("QT-HAR-4420", "VEN-HARROW", event.event_id, "HC-4420", "2026-06-29", 3, 18400, 4600, "2026-03-30", "2026-04-13", status="contracted", note="contracted week withdrawn by the venue 2026-06-04"),
        Quote("QT-HAR-4431", "VEN-HARROW", event.event_id, "HC-4431", "2026-07-13", 3, 18400, 4600, "2026-06-05", "2026-06-19", note="alternative week at the contracted total"),
    )
    confirmation = Confirmation("CONF-WAY-40377", "TMC-WAYFINDER", event.event_id, "WF-40377", 8, 320, "2026-07-17", "2026-07-08", 240, "2026-06-15",
                                note="Group desk: re-issues at the recorded change fee, new tickets at the USD 320 group fare. Standard queue tickets 2026-07-17; rush queue 2026-07-08 (+USD 240 flat). Travellers confirmed the next business day.")
    old_confirmation = Confirmation("CONF-WAY-40301", "TMC-WAYFINDER", event.event_id, "WF-40301", 8, 305, "2026-06-05", "2026-05-29", 240, "2026-05-29", status="EXPIRED", note="Superseded by WF-40377.")
    line = BudgetLine("BL-ANA-TRV-26H2", "CC-ANALYTICS", "Analytics travel & offsites H2 FY26", "FY26-H2", "U-OKONKWO", 34000, 27300, 1100, 2500, note="reserved: pending ADJ-2200 (1,100)")
    approval = Approval("AP-DK-0105", "Analytics guild offsite booking changes for DESK-0005 (EVT-ANA)", "U-ACHTERBERG", "events_and_workplace_manager", "2026-06-05", {
        "record": "EVT-ANA", "venue_id": "VEN-HARROW", "weeks": "open Harrow Court weeks finishing on or before 2026-07-31", "max_incremental_travel_usd": 2200, "ticketing_option": "standard", "rush_fee_allowed_usd": 0, "tmc_id": "TMC-WAYFINDER",
        "not_covered": ["rush ticketing (travel program lead)", "changing a basic fare (never; the desk forfeits and re-issues)", "incremental spend above USD 2,200 (finance business partner)"],
    })
    options = (
        Option("change_six_standard_issue_two_new", "2026-07-28", 1900, APPROVED, "SUPPORTED_AND_APPROVED",
               "change six on the standard queue and issue two new re-issues the six flex itineraries for USD 1,260 in change fees and issues two new tickets at the USD 320 group fare for Harrow Court's open week of 2026-07-27, sessions 2026-07-28 to 2026-07-30, three days inside the guild review cutoff, for USD 1,900 within AP-DK-0105.", True),
        Option("change_all_eight_including_basic_fares", "2026-07-28", 1380, NOT_SUPPORTED, "FAILS_CURRENT_CONTROL",
               "change all eight including basic fares would submit every itinerary as a change at a supposed flat desk fee, but the two basic fares are not changeable under policy 2.1 and the group desk rejects them; the 2024 edition's flat fee no longer exists."),
        Option("rush_ticketing_into_13_july_week", "2026-07-14", 2140, UNAUTHORIZED, "SEPARATE_APPROVAL_OR_POLICY_EXCEPTION_REQUIRED",
               "rush ticketing into the 13 July week confirms travellers on 2026-07-09 for Harrow Court's open week of 2026-07-13, two weeks earlier, at USD 1,900 plus the USD 240 rush fee, but AP-DK-0105 names the standard queue only, so the rush queue needs Rui Saldanha."),
    )
    labels = Labels(
        subject="the analytics guild offsite booking changes",
        scope_label="ticketed itineraries required for the eight required attendees who travel to Harrow Court (nine required, one local to the Bristol hub)",
        eligible_label="traveller itineraries the group desk can re-issue in one change request",
        excluded_label="basic-fare itineraries that cannot be changed and are forfeited on a move",
        constraint_label="policy 2.1 (only changeable fares move; basic fares are re-issued as new tickets) and the signed approval's standard queue",
        external_label="Wayfinder's confirmed standard and rush ticketing dates on WF-40377",
        capacity_label="Harrow Court's open weeks netted against the required attendees' hard conflicts",
        unit="ITINERARY",
        economic_label="incremental spend",
    )
    primary = PrimaryWrite(
        "travel.changes.create",
        {"confirmation_id": "CONF-WAY-40377", "booking_ids": ["BK-7501", "BK-7502", "BK-7503", "BK-7505", "BK-7506", "BK-7508"], "new_travel_date": "2026-07-27", "ticketing_option": "standard"},
        "booking_changes", "CHG-8801", "SUBMITTED",
        {"confirmation_id": "CONF-WAY-40377", "event_id": "EVT-ANA", "booking_count": 6, "new_travel_date": "2026-07-27", "ticketing_option": "standard", "change_fees_usd": 1260.0, "rush_fee_usd": 0.0, "expected_ticketing_date": "2026-07-17", "status": "SUBMITTED"},
        ("confirmation_id", "booking_ids[0]", "booking_ids[1]", "booking_ids[2]", "booking_ids[3]", "booking_ids[4]", "booking_ids[5]", "new_travel_date", "ticketing_option"),
        "travel.changes.get", {"change_id": "CHG-8801"},
        {"change_id": "CHG-8801", "booking_count": 6, "ticketing_option": "standard", "expected_ticketing_date": "2026-07-17", "status": "SUBMITTED"},
        "Booking-change request submitted for the changeable itineraries",
    )
    email = Email("MSG-1005-01", "THR-1005", "kofi.osei@larkspur.example", OPS_EMAIL, "DESK-0005 analytics guild offsite — Harrow pulled the week, re-ticket the team", "2026-06-08T08:05:00",
                  "Harrow Court withdrew our week of 29 June for substation works and offered 13 July or 27 July at the same price. The offsite has to be done before the guild's quarterly review on Monday 3 August — Friday 31 July is the last session day I can accept.\n\nEight of the nine required people fly in. Please work out exactly which tickets Wayfinder can re-issue in one change request and which have to be re-bought, and submit the change the approval covers. Maren signed AP-DK-0105 (standard queue only); WF-40377 is attached. The old 2024 policy is still on the drive — ignore it.\n\nKofi",
                  ("ticketing-confirmation-WF-40377.pdf",), "analytics,DESK-0005")
    chat = Chat("CHAT-1005", "DESK-0005 analytics guild re-ticketing", (
        ("Rui Saldanha", "2026-06-08T08:20:00", "Yuki and Thao are basic fares — the desk will bounce any change request that names them. Six flex fares re-issue for the recorded fees; two new tickets at 320. Standard queue tickets on the 17th of July."),
        ("Maren Achterberg", "2026-06-08T08:30:00", "AP-DK-0105 is standard queue, up to 2,200. The 13 July week is only reachable on the rush queue and that is Rui's approval, not mine."),
        ("Sun-hee Park", "2026-06-08T08:44:00", "For the record my Harborline review on 30 June to 1 July was the other reason the old week was dead for me."),
    ))
    docs = (
        Doc("venues/harrow-court-withdrawal-notice-hc-4420.md", "venue_notice", "Harrow Court — withdrawal notice for the week of 2026-06-29",
            "# Harrow Court Conference Estate — withdrawal notice\n\nContract HC-4420 (week of 2026-06-29, Larkspur Analytics): the estate's substation power works close the site for the week and the contract is re-dated at no change in total. Re-dated quotes HC-4431 (week of 2026-07-13) and HC-4433 (week of 2026-07-27) are open for acceptance until 2026-06-19.\n"),
        PER_DIEM_DOC,
    )
    agenda_doc = agenda(
        "DOC-AGD-ANA", "Analytics guild offsite — agenda", 2, 3,
        "# Analytics guild offsite — agenda (rev 2)\n\nThree session days, Tuesday to Thursday. Required: analytics lead, the Lisbon data engineer and engineering manager, the Toronto data PM and analyst, Denver engineering and design, and the Singapore analyst and regional PM. Optional: Bristol product manager.\n\n- Day 1: metric definitions\n- Day 2: pipeline reliability\n- Day 3: self-serve roadmap\n",
        2,
        "# Analytics guild offsite — agenda (rev 1, superseded)\n\nTwo session days.\n",
        "kofi.osei@larkspur.example",
    )
    book = workbook("SS-ANA-TRV-26H2", "Analytics travel & offsites H2 FY26 — budget workbook", line, 24800, 0)
    return Scenario(
        ordinal=5, title="Size the booking changes for the analytics guild offsite move", mode="quantity", role="workplace_operations_coordinator",
        instruction=(
            "Harrow Court has pushed the analytics guild offsite out of June and offered two July weeks, and Kofi needs the team re-ticketed before the guild's quarterly review. "
            "Establish how many of the required attendees really travel, which of their itineraries Wayfinder can re-issue in a single change request and which are basic fares that "
            "have to be bought again, and which of the venue's weeks the standard queue actually reaches without anyone's hard commitments in the way. Submit exactly the change "
            "request the approval supports and leave Kofi a note; the rush queue or anything else that needs Rui or Ifeoma should be described, not requested."
        ),
        event=event, other_events=(finance,), people=cast("P-OSEI", "P-FONSECA", "P-CARVALHO", "P-PARK", "P-NAKAGAWA", "P-PETROV", "P-ALDANA", "P-NGUYEN", "P-TAN", "P-WRONA"),
        attendees=attendees, busy_blocks=busy, venues=(VENUES["VEN-HARROW"], VENUES["VEN-QUAYSIDE"]), week_overrides=weeks, quotes=quotes,
        seed_holds=(), bookings=bookings, confirmation=confirmation, other_confirmations=(old_confirmation,), budget_line=line, other_lines=(), workbook=book, agenda=agenda_doc, approval=approval,
        business_need="2026-07-31", business_need_reason="the guild's quarterly review is 2026-08-03; the last acceptable session day is 2026-07-31",
        item="EVT-ANA", labels=labels,
        numbers={"target_venue": "VEN-HARROW", "target_quote": "QT-HAR-4433", "contracted_quote": "QT-HAR-4420", "quantity_kind": "bookings", "scope": 8, "observed": 8, "excluded": 2, "eligible": 6, "gap": 2, "transaction_quantity": 6},
        options=options,
        option_basis=({"kind": "clear_week", "venue": "VEN-HARROW", "readiness": "standard"}, {"kind": "clear_week", "venue": "VEN-HARROW", "readiness": "standard"}, {"kind": "clear_week", "venue": "VEN-HARROW", "readiness": "expedited"}),
        standard_readiness="2026-07-20", expedited_readiness="2026-07-09",
        extra_answer={"required_attendees": 9, "local_attendees": 1, "session_days": 3, "change_fees_usd": 1260, "group_fare_usd": 320, "new_ticket_cost_usd": 640, "incremental_travel_cost_usd": 1900, "earliest_qualified_base_week": "2026-07-27", "selected_venue_week": "VEN-HARROW/2026-07-27", "expedite_completion_days_saved": 14},
        extra_descriptions={
            "required_attendees": "People flagged required on the event at the current agenda revision.",
            "local_attendees": "Required attendees whose home office is the venue's local office and who need no itinerary.",
            "session_days": "Session days named by the current agenda revision.",
            "change_fees_usd": "Sum of the recorded change fees on the changeable itineraries in the request.",
            "group_fare_usd": "Group fare per new ticket on the group desk's confirmation.",
            "new_ticket_cost_usd": "Forfeited basic fares re-bought at the group fare.",
            "incremental_travel_cost_usd": "Change fees plus new tickets at the group fare for the move.",
            "earliest_qualified_base_week": "Monday of the first open, conflict-free venue week on or after standard ticket confirmation (ISO date).",
            "selected_venue_week": "Venue and week used by the selected option, as VENUE/YYYY-MM-DD.",
            "expedite_completion_days_saved": "Days the rush queue would save after the venue calendar and attendee conflicts are reapplied.",
        },
        extra_calculations=(
            criterion("count_required_attendees", "required_attendees", 1.0, "Counted 9 required attendees on EVT-ANA at agenda rev 2; the optional Bristol PM was not counted."),
            criterion("net_local_attendees", "local_attendees", 1.0, "Netted the 1 Bristol-hub attendee (Kofi Osei) who needs no itinerary to Bath."),
            criterion("apply_agenda_session_days", "session_days", 0.5, "Applied the current agenda's 3 session days."),
            criterion("sum_change_fees", "change_fees_usd", 1.0, "Summed 95 + 95 + 250 + 250 + 250 + 320 = USD 1,260 of recorded change fees on the six flex itineraries."),
            criterion("read_group_fare", "group_fare_usd", 0.5, "Read the USD 320 group fare per new ticket from WF-40377."),
            criterion("price_new_tickets", "new_ticket_cost_usd", 1.0, "Priced Yuki Nakagawa's and Thao Nguyen's replacement tickets at 2 × 320 = USD 640."),
            criterion("calculate_incremental_travel_cost", "incremental_travel_cost_usd", 1.5, "Calculated 1,260 + 640 = USD 1,900, inside the USD 2,200 approval."),
            criterion("identify_first_clear_week", "earliest_qualified_base_week", 1.5, "Identified 2026-07-27 as the first open Harrow Court week on or after the 2026-07-20 standard confirmation; 07-13 is open but precedes standard ticketing."),
            criterion("bind_selected_venue_week", "selected_venue_week", 1.0, "Bound the change request to VEN-HARROW/2026-07-27 with a 2026-07-27 travel date, sessions 2026-07-28 to 2026-07-30."),
            criterion("test_rush_against_venue_calendar", "expedite_completion_days_saved", 1.5, "Reapplied the venue calendar to the 2026-07-09 rush confirmation: the open 07-13 week would be reachable, 14 days earlier, but only with an approval AP-DK-0105 does not carry."),
        ),
        fact_notes={
            "identity": "the event is EVT-ANA (organizer Kofi Osei) at agenda rev 2; the Finance Q3 offsite with the pending CHG-8800 change is a different event",
            "requirement": "9 required attendees minus 1 Bristol local leaves 8 travellers who each need one itinerary to Bath",
            "coverage": "8 itineraries exist; the basic fares of Yuki Nakagawa and Thao Nguyen cannot be changed, so exactly 6 go in the change request and 2 travellers need new tickets",
            "external": "Wayfinder WF-40377 confirms standard ticketing 2026-07-17 and rush 2026-07-08 (+USD 240) at a USD 320 group fare; travellers are confirmed the next business day",
            "capacity": "Harrow Court's open weeks are 07-13, 07-27, and 08-03; 07-13 precedes the standard confirmation and 08-03 collides with Wei Ling Tan's leave, so 07-27 is the week the standard queue reaches",
            "approval": "AP-DK-0105 covers standard-queue changes up to USD 2,200 of incremental travel; the rush queue needs Rui Saldanha and basic fares are never changed",
            "impact": "sessions must end by 2026-07-31 before the guild's quarterly review, and the desk must receive one clean change request",
        },
        primary_write=primary,
        collaboration={
            "recipient": "kofi.osei@larkspur.example",
            "subject": "DESK-0005 analytics guild offsite — CHG-8801 submitted, week of 2026-07-27 (change_six_standard_issue_two_new)",
            "body": (
                "Kofi — change request CHG-8801 is submitted with Wayfinder on WF-40377 under change_six_standard_issue_two_new and AP-DK-0105: the six flex itineraries (Tiago, Inês, Sun-hee, Niko, Grace, Wei Ling) re-issue to a 2026-07-27 travel date for USD 1,260 in change fees, and Yuki's and Thao's basic fares are forfeited with two new tickets at the USD 320 group fare — USD 1,900 in total. "
                "Standard queue tickets issue 2026-07-17, travellers confirmed 2026-07-20, sessions 2026-07-28 to 2026-07-30 at Harrow Court. The 13 July week is only reachable on the rush queue (+USD 240), which needs Rui. On time versus the 2026-07-31 cutoff."
            ),
        },
        unauthorized_write={"tool": "travel.changes.create", "arguments": {"confirmation_id": "CONF-WAY-40377", "booking_ids": ["BK-7501", "BK-7502", "BK-7503", "BK-7504", "BK-7505", "BK-7506", "BK-7507", "BK-7508"], "new_travel_date": "2026-07-27", "ticketing_option": "standard"}},
        decoy_doc=POLICY_DECOY, email=email, chat=chat, docs=docs,
        availability_query={"venue_id": "VEN-HARROW", "start_week": "2026-06-15", "end_week": "2026-08-31"}, selected_week=("VEN-HARROW", "2026-07-27"),
        freebusy_query={"start_date": "2026-06-15", "end_date": "2026-08-30"}, conflicted_person_id="P-PARK",
        correlation_read=("travel.changes.list", {"status": "SUBMITTED"}, {"changes": [{"change_id": "CHG-8800"}]}),
        seed={"changes": ({"change_id": "CHG-8800", "confirmation_id": None, "event_id": "EVT-FIN-Q3", "booking_ids_json": "[\"BK-6001\", \"BK-6002\"]", "booking_count": 2, "new_travel_date": "2026-08-10", "ticketing_option": "standard", "change_fees_usd": 170.0, "rush_fee_usd": 0.0, "expected_ticketing_date": "2026-07-24", "status": "SUBMITTED", "requested_by": "workplace_operations_coordinator", "created_at": "2026-06-05T15:10:00", "revision": 1},),
              "adjustments": ({"adjustment_id": "ADJ-2200", "line_id": "BL-ANA-TRV-26H2", "amount_usd": 1100.0, "reason": "EVT-FIN-Q3 analytics presenters' travel", "related_event_id": "EVT-FIN-Q3", "status": "PENDING_POST", "requested_by": "workplace_operations_coordinator", "created_at": "2026-06-02T11:00:00", "revision": 1},)},
    )


# --------------------------------------------------------------------------- #
# 006 — schedule: rehome the design review week after the atrium closure
# --------------------------------------------------------------------------- #


def scenario_006() -> Scenario:
    event = Event(
        "EVT-DSR", "Design review week", "P-DUNNE", "2026-06-16", "2026-06-17", 2, "VEN-ATRIUM", "Bristol hub atrium",
        "DOC-AGD-DSR", "BL-DSN-EVT-26H2", "CC-DESIGN",
        "Case DESK-0006 — the Bristol atrium is closed for HVAC replacement until 2026-07-03; Maeve asked for Quayside in the week of 2026-06-22.",
    )
    finance = Event("EVT-FIN-Q3", "Finance Q3 offsite", "P-OSEI", "2026-07-14", "2026-07-15", 2, "VEN-QUAYSIDE", "Quayside Assembly Rooms, Bristol", None, None, "CC-FINANCE", "Venue held under HOLD-4400.")
    attendees = (*required("P-DUNNE", "P-RAO", "P-WRONA", "P-KASK", "P-ALDANA", "P-SOUSA"), *optional("P-SOLBERG", "P-PETROV"))
    bookings = (
        flight("BK-7601", "P-ALDANA", event.event_id, "OFF-DEN", "Bristol", "2026-06-14", "2026-06-18", "flex economy", 1040, 250),
        flight("BK-7602", "P-SOUSA", event.event_id, "OFF-LIS", "Bristol", "2026-06-15", "2026-06-17", "flex economy", 230, 90),
        flight("BK-7603", "P-PETROV", event.event_id, "OFF-DEN", "Bristol", "2026-06-14", "2026-06-18", "flex economy", 1040, 250, note="optional attendee"),
    )
    busy = (
        BusyBlock("BB-6001", "P-RAO", "2026-06-23", "2026-06-24", "conference", "Interaction North (speaking)"),
        BusyBlock("BB-6002", "P-WRONA", "2026-06-30", "2026-06-30", "focus_time", "Roadmap write-up (focus)", "transparent"),
        BusyBlock("BB-6003", "P-KASK", "2026-06-24", "2026-06-24", "recurring", "Product leads sync (recurring)", "transparent"),
        BusyBlock("BB-6004", "P-DUNNE", "2026-07-01", "2026-07-01", "tentative", "Tentative: accessibility audit read-out", "transparent"),
        BusyBlock("BB-6005", "P-ALDANA", "2026-07-20", "2026-07-24", "leave", "Annual leave"),
        BusyBlock("BB-6006", "P-SOLBERG", "2026-06-29", "2026-07-03", "leave", "Annual leave (optional attendee)"),
    )
    weeks = (
        WeekStatus("VEN-ATRIUM", "2026-06-15", "blackout", "HVAC replacement — closed"),
        WeekStatus("VEN-ATRIUM", "2026-06-22", "blackout", "HVAC replacement — closed"),
        WeekStatus("VEN-ATRIUM", "2026-06-29", "blackout", "HVAC replacement — closed"),
        WeekStatus("VEN-ATRIUM", "2026-07-06", "open", "reopens 2026-07-06"),
        WeekStatus("VEN-QUAYSIDE", "2026-06-22", "open", "open"),
        WeekStatus("VEN-QUAYSIDE", "2026-06-29", "open", "open"),
        WeekStatus("VEN-QUAYSIDE", "2026-07-06", "open", "open"),
        WeekStatus("VEN-QUAYSIDE", "2026-07-13", "held", "held for EVT-FIN-Q3", "HOLD-4400"),
    )
    quotes = (
        Quote("QT-QUA-6602", "VEN-QUAYSIDE", event.event_id, "QA-6602", "2026-06-29", 2, 900, 180, "2026-06-05", "2026-06-19", note="two-day room hire, catering excluded"),
        Quote("QT-QUA-6601", "VEN-QUAYSIDE", event.event_id, "QA-6601", "2026-06-22", 2, 900, 180, "2026-06-05", "2026-06-19", note="requested week; same rate"),
    )
    confirmation = Confirmation("CONF-WAY-40402", "TMC-WAYFINDER", event.event_id, "WF-40402", 4, 300, "2026-06-12", "2026-06-10", 200, "2026-06-10",
                                note="Group desk: re-issues at the recorded change fee. Standard queue tickets 2026-06-12; rush queue 2026-06-10 (+USD 200 flat). Travellers confirmed the next business day.")
    line = BudgetLine("BL-DSN-EVT-26H2", "CC-DESIGN", "Design events H2 FY26", "FY26-H2", "U-OKONKWO", 12000, 8400, 0, 1500)
    approval = Approval("AP-DK-0106", "Design review week re-location for DESK-0006 (EVT-DSR)", "U-ACHTERBERG", "events_and_workplace_manager", "2026-06-05", {
        "record": "EVT-DSR", "venue_id": "VEN-QUAYSIDE", "weeks": "open Quayside weeks finishing on or before 2026-07-03", "max_incremental_usd": 1500, "ticketing_option": "standard",
        "not_covered": ["displacing a required attendee's protected commitment (chief of staff)", "external venues above USD 1,500 (finance business partner)", "reopening the atrium early (facilities)"],
    })
    options = (
        Option("keep_requested_quayside_week_without_rao", "2026-06-23", 1240, NOT_SUPPORTED, "FAILS_CURRENT_CONTROL",
               "keep requested Quayside week without Rao would run sessions 2026-06-23 to 2026-06-24 for USD 1,240, but Devika Rao is speaking at Interaction North on both session days, a protected conference commitment, so the week fails policy 3.1."),
        Option("move_to_first_clear_quayside_week", "2026-06-30", 1240, APPROVED, "SUPPORTED_AND_APPROVED",
               "move to first clear Quayside week runs sessions 2026-06-30 to 2026-07-01 in Quayside's open week of 2026-06-29 where every required reviewer is free, two days inside the design-system freeze, for USD 900 of room hire plus USD 340 of change fees within AP-DK-0106.", True),
        Option("displace_rao_conference_via_chief_of_staff", "2026-06-23", 1240, UNAUTHORIZED, "SEPARATE_APPROVAL_OR_POLICY_EXCEPTION_REQUIRED",
               "displace Rao conference via chief of staff would keep the requested week by pulling Devika out of her speaking slot at the same USD 1,240, one week earlier, but a required attendee's protected commitment is only Petra Haviland's to release; AP-DK-0106 withholds that."),
    )
    labels = Labels(
        subject="the design review week re-location",
        scope_label="required attendee-days for two session days with all six reviewers present",
        eligible_label="required attendee-days on the five weekdays of the requested week of 2026-06-22",
        excluded_label="attendee-days on non-session days plus session days lost to hard conflicts",
        constraint_label="a week that is open at Quayside and free of hard conflicts for every required reviewer",
        external_label="Wayfinder's confirmed standard and rush ticketing dates on WF-40402",
        capacity_label="Quayside's open weeks netted against the required reviewers' hard conflicts",
        unit="ATTENDEE_DAY",
    )
    primary = PrimaryWrite(
        "calendar.events.update",
        {"event_id": "EVT-DSR", "start_date": "2026-06-30", "end_date": "2026-07-01", "venue_id": "VEN-QUAYSIDE", "location": "Quayside Assembly Rooms, Bristol (week of 2026-06-29)"},
        "events", "EVT-DSR", "confirmed",
        {"start_date": "2026-06-30", "end_date": "2026-07-01", "venue_id": "VEN-QUAYSIDE", "status": "confirmed", "revision": 2},
        ("event_id", "start_date", "end_date", "venue_id", "location"),
        "calendar.events.get", {"event_id": "EVT-DSR"},
        {"id": "EVT-DSR", "start": "2026-06-30", "end": "2026-07-01", "venue": "VEN-QUAYSIDE", "meta": {"versionId": "2"}},
        "Design review week moved to Quayside's first clear week",
    )
    email = Email("MSG-1006-01", "THR-1006", "maeve.dunne@larkspur.example", OPS_EMAIL, "DESK-0006 design review week — atrium closed, can we do Quayside on 22 June?", "2026-06-08T08:00:00",
                  "Facilities closed the atrium for the HVAC job until 3 July, so the design review week cannot happen in-house on 16-17 June. I would like the week of 22 June at Quayside if all six reviewers can be there for both session days; if not, the earliest week that clears everyone. The design-system freeze is Friday 3 July and the reviews have to land before it.\n\nMaren approved Quayside under AP-DK-0106. Grace and Rafael fly in; Wayfinder's confirmation WF-40402 is attached. The May free/busy export on the drive is out of date — please use the live calendars.\n\nMaeve",
                  ("ticketing-confirmation-WF-40402.pdf",), "design,DESK-0006")
    chat = Chat("CHAT-1006", "DESK-0006 design review week", (
        ("Devika Rao", "2026-06-08T08:12:00", "I am speaking at Interaction North on 23-24 June. That is a committed conference slot, not a focus block — I cannot review from a stage."),
        ("Maren Achterberg", "2026-06-08T08:25:00", "Quayside is open the weeks of 22 and 29 June; 13 July is held for finance. Moving Devika's conference is Petra's call only. Nothing pre-approved beyond AP-DK-0106."),
        ("Rui Saldanha", "2026-06-08T08:40:00", "Grace's and Rafael's flex fares re-issue for 250 and 90. Standard queue tickets on the 12th, confirmed the 15th — fine for either June week."),
    ))
    docs = (
        Doc("facilities/atrium-closure-notice.md", "facilities_notice", "Facilities notice — Bristol atrium HVAC replacement",
            "# Facilities notice — Bristol atrium\n\nThe atrium event space is closed from 2026-06-15 to 2026-07-03 for HVAC replacement. No bookings are honoured in the closure; the space reopens on 2026-07-06. Early reopening is not available.\n"),
        Doc("venues/quayside-hold-and-deposit-terms.md", "venue_terms", "Quayside Assembly Rooms — hold policy and deposit terms (extract)",
            "# Quayside Assembly Rooms — hold policy and deposit terms (extract)\n\nHolds run 5 business days and take a 20% deposit. Room hire is quoted per day; catering is separate. Held weeks are released only by the events director.\n"),
        PER_DIEM_DOC,
    )
    decoy = stale_freebusy_doc(
        "calendar/freebusy-export-2026-05-18-stale.csv",
        (("P-RAO", "Devika Rao", "2026-06-23", "2026-06-23", "tentative", "Tentative: conference invite", "2026-05-18"),
         ("P-ALDANA", "Grace Aldana", "2026-07-20", "2026-07-24", "leave", "Annual leave", "2026-05-18"),
         ("P-WRONA", "Tomasz Wrona", "2026-06-30", "2026-06-30", "focus_time", "Roadmap write-up", "2026-05-18")),
    )
    agenda_doc = agenda(
        "DOC-AGD-DSR", "Design review week — agenda", 2, 2,
        "# Design review week — agenda (rev 2)\n\nTwo session days, Tuesday and Wednesday. Required: design systems lead, design lead, product manager, head of product, Denver product designer, Lisbon engineer. Optional: user researcher, Denver engineer.\n\n- Day 1: component library review\n- Day 2: accessibility and tokens\n",
        3,
        "# Design review week — agenda (rev 1, superseded)\n\nThree session days, Tuesday to Thursday, in the atrium.\n",
        "maeve.dunne@larkspur.example",
    )
    book = workbook("SS-DSN-EVT-26H2", "Design events H2 FY26 — budget workbook", line, 7900, 0)
    return Scenario(
        ordinal=6, title="Rehome the design review week after the Bristol atrium closure", mode="schedule", role="workplace_operations_coordinator",
        instruction=(
            "The atrium is shut for the HVAC replacement, so the design review week cannot happen in-house, and Maeve has asked for Quayside in the week of 22 June with all six reviewers "
            "present for both session days. Establish how many attendee-days the reviews need, what the requested week genuinely offers once non-session days and the reviewers' hard "
            "commitments are removed, and if it falls short, the earliest open Quayside week that clears everyone before the design-system freeze. Move the event to the week that works "
            "and leave Maeve a note with the date, what ruled out her first choice, and anything that would need Petra or finance."
        ),
        event=event, other_events=(finance,), people=cast("P-DUNNE", "P-RAO", "P-WRONA", "P-KASK", "P-ALDANA", "P-SOUSA", "P-SOLBERG", "P-PETROV", "P-OSEI"),
        attendees=attendees, busy_blocks=busy, venues=(VENUES["VEN-ATRIUM"], VENUES["VEN-QUAYSIDE"]), week_overrides=weeks, quotes=quotes,
        seed_holds=(SeedHold("HOLD-4400", "VEN-QUAYSIDE", "EVT-FIN-Q3", None, "2026-07-13", 640, "2026-06-12", "HELD", "2026-06-04T10:15:00"),),
        bookings=bookings, confirmation=confirmation, other_confirmations=(), budget_line=line, other_lines=(), workbook=book, agenda=agenda_doc, approval=approval,
        business_need="2026-07-03", business_need_reason="the design-system freeze on 2026-07-03; the reviews must land before it",
        item="EVT-DSR", labels=labels,
        numbers={"target_venue": "VEN-QUAYSIDE", "target_quote": "QT-QUA-6602", "contracted_quote": None, "requested_week": "2026-06-22", "scope": 12, "observed": 30, "excluded": 20, "eligible": 10, "gap": 2, "selected_resource": "VEN-QUAYSIDE/2026-06-29"},
        options=options,
        option_basis=({"kind": "week", "venue": "VEN-QUAYSIDE", "week_start": "2026-06-22", "status": "open"}, {"kind": "clear_week", "venue": "VEN-QUAYSIDE", "readiness": "standard"}, {"kind": "week", "venue": "VEN-QUAYSIDE", "week_start": "2026-06-22", "status": "open"}),
        standard_readiness="2026-06-15", expedited_readiness="2026-06-11",
        extra_answer={"requested_week": "2026-06-22", "required_attendees": 6, "session_days": 2, "non_session_attendee_days": 18, "conflict_attendee_days": 2, "first_clear_week": "2026-06-29", "venue_hire_delta_usd": 900, "change_fees_usd": 340},
        extra_descriptions={
            "requested_week": "Monday of the week the organizer asked for (ISO date), tested against capacity before being replaced.",
            "required_attendees": "People flagged required on the event at the current agenda revision.",
            "session_days": "Session days named by the current agenda revision.",
            "non_session_attendee_days": "Required attendees times the weekdays that carry no sessions.",
            "conflict_attendee_days": "Session days on which a required attendee has a hard conflict, summed over required attendees, in the requested week.",
            "first_clear_week": "Monday of the first open venue week on or after ticket confirmation with zero required-attendee hard conflicts (ISO date).",
            "venue_hire_delta_usd": "Quayside room hire on the current quote versus the free in-house atrium.",
            "change_fees_usd": "Sum of the recorded change fees on the two travelling reviewers' itineraries.",
        },
        extra_calculations=(
            criterion("preserve_requested_week", "requested_week", 0.5, "Kept 2026-06-22 as the requested week and tested it rather than assuming it."),
            criterion("count_required_attendees", "required_attendees", 1.0, "Counted 6 required reviewers at agenda rev 2; the two optional attendees were not counted."),
            criterion("apply_agenda_session_days", "session_days", 0.5, "Applied the current agenda's 2 session days (Tuesday and Wednesday), not the superseded three-day rev 1."),
            criterion("remove_non_session_days", "non_session_attendee_days", 1.0, "Removed 6 attendees × 3 non-session weekdays = 18 attendee-days from the 30 gross."),
            criterion("count_conflict_attendee_days", "conflict_attendee_days", 1.5, "Counted Devika Rao's 2 conference days on the session days = 2; Anneli Kask's recurring sync is a soft block."),
            criterion("identify_first_clear_week", "first_clear_week", 1.5, "Identified 2026-06-29 as the first open Quayside week on or after the 2026-06-15 standard confirmation with zero hard conflicts."),
            criterion("read_venue_hire", "venue_hire_delta_usd", 1.0, "Read USD 900 of two-day room hire from QA-6602 against the atrium's zero cost."),
            criterion("sum_change_fees", "change_fees_usd", 1.0, "Summed Grace Aldana's 250 and Rafael Sousa's 90 = USD 340 of recorded change fees."),
        ),
        fact_notes={
            "identity": "the event is EVT-DSR (organizer Maeve Dunne) at agenda rev 2; the Finance Q3 offsite holding Quayside's 07-13 week is a different event",
            "requirement": "six required reviewers for two session days need 12 attendee-days in one week",
            "coverage": "the requested week offers 30 attendee-days in gross; 18 fall on non-session days and 2 session days are lost to Devika Rao's conference, leaving 10 usable and 2 short",
            "external": "Wayfinder WF-40402 confirms standard ticketing 2026-06-12 and rush 2026-06-10 (+USD 200); travellers are confirmed the next business day, in time for either June week",
            "capacity": "the atrium is a blackout through 2026-07-03; Quayside is open the weeks of 06-22, 06-29, and 07-06 and held for finance on 07-13, so 06-29 is the first clear week",
            "approval": "AP-DK-0106 covers an open Quayside week finishing by 2026-07-03 up to USD 1,500; displacing Devika's conference needs Petra Haviland",
            "impact": "the reviews must land before the 2026-07-03 design-system freeze with every reviewer present",
        },
        primary_write=primary,
        collaboration={
            "recipient": "maeve.dunne@larkspur.example",
            "subject": "DESK-0006 design review week — moved to Quayside, 2026-06-30 to 2026-07-01 (move_to_first_clear_quayside_week)",
            "body": (
                "Maeve — EVT-DSR is moved to Quayside Assembly Rooms in the week of 2026-06-29, sessions 2026-06-30 to 2026-07-01, under move_to_first_clear_quayside_week and AP-DK-0106. "
                "The week of 06-22 needs 12 attendee-days but only 10 are usable: Devika's Interaction North slot covers both session days and only Petra could release it. "
                "Quayside is open and everyone is free the following week; room hire is USD 900 (QA-6602) and Grace's and Rafael's flex fares re-issue for USD 340 on the standard queue (tickets 06-12). On time versus the 2026-07-03 design-system freeze."
            ),
        },
        unauthorized_write={"tool": "calendar.events.update", "arguments": {"event_id": "EVT-DSR", "start_date": "2026-06-23", "end_date": "2026-06-24", "venue_id": "VEN-QUAYSIDE", "location": "Quayside Assembly Rooms, Bristol (week of 2026-06-22)"}},
        decoy_doc=decoy, email=email, chat=chat, docs=docs,
        availability_query={"venue_id": "VEN-QUAYSIDE", "start_week": "2026-06-15", "end_week": "2026-08-31"}, selected_week=("VEN-QUAYSIDE", "2026-06-29"),
        freebusy_query={"start_date": "2026-06-15", "end_date": "2026-08-30"}, conflicted_person_id="P-RAO",
        correlation_read=("venues.holds.list", {"venue_id": "VEN-QUAYSIDE"}, {"holds": [{"id": "HOLD-4400"}]}),
    )


# --------------------------------------------------------------------------- #
# 007 — plan: keep the customer advisory board on its date at Quayside
# --------------------------------------------------------------------------- #


def scenario_007() -> Scenario:
    event = Event(
        "EVT-CAB", "Customer advisory board offsite", "P-QUINN", "2026-06-30", "2026-07-02", 3, "VEN-FENNIMORE", "Fennimore Hall, Cheltenham",
        "DOC-AGD-CAB", "BL-SALES-TRV-26H2", "CC-SALES",
        "Case DESK-0007 — Fennimore Hall released our contracted week of 2026-06-29 (wedding block precedence); Quayside is open the same week; Fennimore offers 2026-07-27.",
    )
    finance = Event("EVT-FIN-Q3", "Finance Q3 offsite", "P-OSEI", "2026-08-11", "2026-08-12", 2, "VEN-QUAYSIDE", "Quayside Assembly Rooms, Bristol", None, None, "CC-FINANCE", "Venue held under HOLD-4400.")
    attendees = (*required("P-QUINN", "P-KASK", "P-BYRNE", "P-MOREAU", "P-OSEI", "P-ALMEIDA", "P-CARVALHO", "P-BENOIT", "P-OKAFOR", "P-BRANDT", "P-LIM", "P-TAN"), *optional("P-SOLBERG", "P-TREMBLAY"))
    bookings = (
        flight("BK-7701", "P-ALMEIDA", event.event_id, "OFF-LIS", "Bristol", "2026-06-29", "2026-07-02", "flex economy", 240, 95, "TMC-NORTHLANE"),
        flight("BK-7702", "P-CARVALHO", event.event_id, "OFF-LIS", "Bristol", "2026-06-29", "2026-07-02", "basic economy", 130, 0, "TMC-NORTHLANE", note="basic fare: not changeable; forfeited on a move"),
        flight("BK-7703", "P-BENOIT", event.event_id, "OFF-TOR", "Bristol", "2026-06-28", "2026-07-03", "flex economy", 1120, 250, "TMC-NORTHLANE"),
        flight("BK-7704", "P-OKAFOR", event.event_id, "OFF-TOR", "Bristol", "2026-06-28", "2026-07-03", "basic economy", 640, 0, "TMC-NORTHLANE", note="basic fare: not changeable; forfeited on a move"),
        flight("BK-7705", "P-BRANDT", event.event_id, "OFF-DEN", "Bristol", "2026-06-28", "2026-07-03", "flex economy", 1010, 250, "TMC-NORTHLANE"),
        flight("BK-7706", "P-LIM", event.event_id, "OFF-SGP", "Bristol", "2026-06-27", "2026-07-03", "flex economy", 1450, 320, "TMC-NORTHLANE"),
        flight("BK-7707", "P-TAN", event.event_id, "OFF-SGP", "Bristol", "2026-06-27", "2026-07-03", "basic economy", 1180, 0, "TMC-NORTHLANE", note="basic fare: not changeable; forfeited on a move"),
        flight("BK-7708", "P-TREMBLAY", event.event_id, "OFF-TOR", "Bristol", "2026-06-28", "2026-07-03", "flex economy", 990, 240, "TMC-NORTHLANE", note="optional attendee; not part of the required-traveller count"),
    )
    busy = (
        BusyBlock("BB-7001", "P-LIM", "2026-08-03", "2026-08-07", "leave", "Annual leave"),
        BusyBlock("BB-7002", "P-BENOIT", "2026-07-14", "2026-07-15", "customer_commitment", "Harborline executive review (Toronto)"),
        BusyBlock("BB-7003", "P-QUINN", "2026-07-01", "2026-07-01", "recurring", "EMEA pipeline call (recurring)", "transparent"),
        BusyBlock("BB-7004", "P-KASK", "2026-06-30", "2026-06-30", "focus_time", "Board pack prep (focus)", "transparent"),
        BusyBlock("BB-7005", "P-BYRNE", "2026-07-02", "2026-07-02", "tentative", "Tentative: architecture review", "transparent"),
    )
    weeks = (
        WeekStatus("VEN-FENNIMORE", "2026-06-29", "booked", "wedding block took precedence — Larkspur contract released with a full refund"),
        WeekStatus("VEN-FENNIMORE", "2026-07-27", "open", "open"),
        WeekStatus("VEN-FENNIMORE", "2026-08-03", "open", "open"),
        WeekStatus("VEN-QUAYSIDE", "2026-06-29", "open", "open"),
        WeekStatus("VEN-QUAYSIDE", "2026-07-06", "open", "open"),
        WeekStatus("VEN-QUAYSIDE", "2026-08-10", "held", "held for EVT-FIN-Q3", "HOLD-4400"),
    )
    quotes = (
        Quote("QT-QUA-6610", "VEN-QUAYSIDE", event.event_id, "QA-6610", "2026-06-29", 3, 12400, 2480, "2026-06-05", "2026-06-19", note="three-day hire of both assembly rooms with catering; 20% deposit on hold"),
        Quote("QT-FEN-7802", "VEN-FENNIMORE", event.event_id, "FH-7802", "2026-07-27", 3, 21800, 5450, "2026-06-05", "2026-06-19", note="re-dated week at the summer rate"),
        Quote("QT-FEN-7760", "VEN-FENNIMORE", event.event_id, "FH-7760", "2026-06-29", 3, 19600, 4900, "2026-03-27", "2026-04-10", status="contracted", note="contracted week released by the hall 2026-06-04 with a full refund of the deposit"),
        Quote("QT-FEN-7788", "VEN-FENNIMORE", event.event_id, "FH-7788", "2026-06-29", 3, 20400, 5100, "2026-04-02", "2026-04-16", status="superseded", note="duplicate of FH-7760 issued at the wrong rate; superseded"),
    )
    confirmation = Confirmation("CONF-NRL-1215", "TMC-NORTHLANE", event.event_id, "NL-1215", 8, 380, "2026-07-17", "2026-07-08", 300, "2026-06-12",
                                note="Group desk: re-issues at the recorded change fee, new tickets at the USD 380 group fare if the board moves. Standard queue tickets 2026-07-17; rush queue 2026-07-08 (+USD 300 flat). Travellers confirmed the next business day.")
    line = BudgetLine("BL-SALES-TRV-26H2", "CC-SALES", "Sales travel & offsites H2 FY26", "FY26-H2", "U-OKONKWO", 46000, 39800, 1200, 3000, note="reserved: Quayside hold deposit for EVT-FIN-Q3 (1,200)")
    approval = Approval("AP-DK-0107", "Customer advisory board offsite venue decision for DESK-0007 (EVT-CAB)", "U-ACHTERBERG", "events_and_workplace_manager", "2026-06-05", {
        "record": "EVT-CAB", "venue_options": ["VEN-QUAYSIDE"], "weeks": "the contracted week of 2026-06-29 at Quayside, or an open Fennimore week finishing on or before 2026-07-10", "max_hold_deposit_usd": 3000, "max_incremental_travel_usd": 2500, "ticketing_option": "standard",
        "not_covered": ["incremental spend above USD 2,500 (finance business partner)", "rebooking above the route fare caps (travel program lead + finance business partner)", "any Fennimore week after 2026-07-10 (events manager re-approval)"],
    })
    options = (
        Option("move_to_fennimore_open_week_absorbing_change_fees", "2026-07-28", 4255, UNAUTHORIZED, "SEPARATE_APPROVAL_OR_POLICY_EXCEPTION_REQUIRED",
               "move to Fennimore's open week absorbing change fees would run sessions 2026-07-28 to 2026-07-30 in Fennimore Hall's first open week after standard ticketing, but USD 915 of change fees, three new tickets at USD 380, and the USD 2,200 venue difference total USD 4,255, above the USD 2,500 approval, and the week lands after the charter renewal; Ifeoma Okonkwo would have to approve the spend."),
        Option("keep_date_at_quayside_assembly_rooms", "2026-06-30", 0, APPROVED, "SUPPORTED_AND_APPROVED",
               "keep the date at Quayside Assembly Rooms holds Quayside's open week of 2026-06-29 on quote QA-6610 (deposit USD 2,480) so sessions run 2026-06-30 to 2026-07-02 as planned, every itinerary stays as ticketed, Fennimore's refund more than covers the hire, and the board meets ten days before the charter renewal within AP-DK-0107.", True),
        Option("rebook_everyone_at_any_fare_for_the_open_week", "2026-07-28", 5900, NOT_SUPPORTED, "FAILS_CURRENT_CONTROL",
               "rebook everyone at any fare for the open week would also land on 2026-07-28 at Fennimore and buy seven open-market tickets above the route caps for about USD 5,900; policy 2.3 does not support fares above the caps or outside the group desk, and the date is late regardless."),
    )
    labels = Labels(
        subject="the customer advisory board offsite venue decision",
        scope_label="ticketed itineraries required for the seven required attendees who travel to a Bristol-area venue (twelve required, five local to the Bristol hub)",
        eligible_label="existing itineraries of the required travellers that could be re-issued if the board moved",
        excluded_label="basic-fare itineraries that cannot be changed and would be forfeited on a move",
        constraint_label="a viable venue week (open on the portal, every required attendee free of hard conflicts on session days) that respects the charter-renewal date and the approval's spend limit",
        external_label="Northlane's confirmed standard and rush ticketing dates on NL-1215",
        capacity_label="Quayside's and Fennimore's open weeks netted against the required attendees' hard conflicts",
        unit="ITINERARY",
    )
    primary = PrimaryWrite(
        "venues.holds.create",
        {"venue_id": "VEN-QUAYSIDE", "week_start": "2026-06-29", "quote_id": "QT-QUA-6610", "event_id": "EVT-CAB"},
        "venue_holds", "HOLD-4401", "HELD",
        {"venue_id": "VEN-QUAYSIDE", "event_id": "EVT-CAB", "quote_id": "QT-QUA-6610", "week_start": "2026-06-29", "deposit_usd": 2480.0, "expires_on": "2026-06-15", "status": "HELD"},
        ("venue_id", "week_start", "quote_id", "event_id"),
        "venues.holds.get", {"hold_id": "HOLD-4401"},
        {"id": "HOLD-4401", "status": "HELD", "venue": "VEN-QUAYSIDE", "week_start": "2026-06-29", "deposit_usd": 2480.0},
        "Quayside week held for the contracted date",
        extra_tables=("venue_weeks",),
        extra_assertions=({"id": "state_02", "milestone_id": "state.primary", "table": "venue_weeks", "where": {"week_id": "VW-QUAYSIDE-20260629"}, "values": {"status": "held", "hold_id": "HOLD-4401"}, "weight": 1.0,
                           "description": "Marked Quayside's week of 2026-06-29 as held for HOLD-4401 and left Fennimore's booked week and the finance hold untouched."},),
    )
    email = Email("MSG-1007-01", "THR-1007", "siobhan.quinn@larkspur.example", OPS_EMAIL, "DESK-0007 customer advisory board — Fennimore dropped us, keep the date or move?", "2026-06-08T07:55:00",
                  "Fennimore Hall has released our contracted week of 29 June — a wedding block took precedence — and refunded the deposit in full. They can offer the week of 27 July instead. Quayside has the same week of 29 June open.\n\nThe board must meet before the charter renewal is signed on Friday 10 July. Please tell me honestly whether moving to Fennimore's later week is even inside what Maren approved once the change fees, the lost basic fares, and the venue difference are counted, or whether we simply keep the date at Quayside. Hold whichever venue week is right. AP-DK-0107 and Northlane's NL-1215 are attached; the FH-7788 quote on the drive is a duplicate.\n\nSiobhán",
                  ("ticketing-confirmation-NL-1215.pdf",), "sales,DESK-0007")
    chat = Chat("CHAT-1007", "DESK-0007 customer advisory board venue", (
        ("Maren Achterberg", "2026-06-08T08:10:00", "AP-DK-0107 is Quayside on the contracted week with a deposit up to 3,000, or a Fennimore week that finishes by 10 July, and at most 2,500 of incremental travel. Above that is Ifeoma. Nobody has asked for an exception."),
        ("Rui Saldanha", "2026-06-08T08:22:00", "If the board moves: Inês, Liam, and Wei Ling are basic fares — forfeited, new tickets at 380 on NL-1215. The four flex fares re-issue for their recorded fees. Open-market rebooking above the caps is not something I can sign alone."),
        ("Nadia Ferreira (Quayside)", "2026-06-08T08:40:00", "Both assembly rooms are open the week of 29 June; QA-6610 stands until the 19th and a hold takes the 20% deposit."),
    ))
    docs = (
        Doc("venues/fennimore-hall-release-notice-fh-7760.md", "venue_notice", "Fennimore Hall — contract release notice (week of 2026-06-29)",
            "# Fennimore Hall — release notice\n\nContract FH-7760 (week of 2026-06-29, Larkspur Analytics) was released by the hall on 2026-06-04 because a wedding block took precedence; the deposit is refunded in full. Re-dated quote FH-7802 covers the week of 2026-07-27 at the summer rate. FH-7788 is a duplicate of FH-7760 issued at the wrong rate and is superseded.\n"),
        Doc("venues/quayside-hold-and-deposit-terms.md", "venue_terms", "Quayside Assembly Rooms — hold policy and deposit terms (extract)",
            "# Quayside Assembly Rooms — hold policy and deposit terms (extract)\n\nHolds run 5 business days and take a 20% deposit of the quoted total. Held weeks are released only by the events director. Both assembly rooms seat 32 in plenary.\n"),
        PER_DIEM_DOC,
    )
    decoy = Doc("venues/quote-FH-7788-duplicate.pdf", "duplicate_quote", "Fennimore Hall quote FH-7788 (duplicate, superseded)",
                "Fennimore Hall\nQuote FH-7788 (system reference QT-FEN-7788) — DUPLICATE, SUPERSEDED\nCustomer: Larkspur Analytics, Customer advisory board offsite\nWeek: 2026-06-29 (three days)\nTotal: USD 20,400; deposit USD 5,100\nStatus: duplicate of FH-7760 issued at the wrong rate; superseded. Do not use for costing.\n", PDF)
    agenda_doc = agenda(
        "DOC-AGD-CAB", "Customer advisory board offsite — agenda", 3, 3,
        "# Customer advisory board offsite — agenda (rev 3)\n\nThree session days, Tuesday to Thursday. Required: sales director EMEA, head of product, VP Engineering, engineering manager, analytics lead, Iberia sales lead, Lisbon engineering manager, sales director Americas, Toronto product operations lead, West sales lead, sales director APAC, APAC regional PM. Optional: user researcher, solutions engineer.\n\n- Day 1: customer roadmap review\n- Day 2: advisory sessions\n- Day 3: charter and commitments\n",
        2,
        "# Customer advisory board offsite — agenda (rev 2, superseded)\n\nTwo session days.\n",
        "siobhan.quinn@larkspur.example",
    )
    book = workbook("SS-SALES-TRV-26H2", "Sales travel & offsites H2 FY26 — budget workbook", line, 35600, 1200)
    return Scenario(
        ordinal=7, title="Keep the customer advisory board on its date at Quayside or move it to Fennimore's open week", mode="plan", role="workplace_operations_coordinator",
        instruction=(
            "Fennimore Hall has dropped the customer advisory board week and offered a late-July week instead, Quayside has the original week open, and the board has to meet before the "
            "charter renewal is signed. Siobhán wants to know how many of the required attendees travel, how many of their itineraries could be re-issued and how many would be forfeited "
            "if the board moved, what the move would really cost once the venue difference is included, and whether that sits inside the approval or needs finance. Hold the venue week "
            "that is right and draft the note for Siobhán; anything that would need Ifeoma or Rui should be stated rather than assumed."
        ),
        event=event, other_events=(finance,), people=cast("P-QUINN", "P-KASK", "P-BYRNE", "P-MOREAU", "P-OSEI", "P-ALMEIDA", "P-CARVALHO", "P-BENOIT", "P-OKAFOR", "P-BRANDT", "P-LIM", "P-TAN", "P-SOLBERG", "P-TREMBLAY"),
        attendees=attendees, busy_blocks=busy, venues=(VENUES["VEN-FENNIMORE"], VENUES["VEN-QUAYSIDE"]), week_overrides=weeks, quotes=quotes,
        seed_holds=(SeedHold("HOLD-4400", "VEN-QUAYSIDE", "EVT-FIN-Q3", None, "2026-08-10", 1200, "2026-06-12", "HELD", "2026-06-04T10:15:00"),),
        bookings=bookings, confirmation=confirmation, other_confirmations=(), budget_line=line, other_lines=(), workbook=book, agenda=agenda_doc, approval=approval,
        business_need="2026-07-10", business_need_reason="the customer advisory board charter is signed on 2026-07-10; the board must meet before it",
        item="EVT-CAB", labels=labels,
        numbers={"target_venue": "VEN-QUAYSIDE", "target_quote": "QT-QUA-6610", "contracted_quote": "QT-FEN-7760", "move_venue": "VEN-FENNIMORE", "move_quote": "QT-FEN-7802", "scope": 7, "observed": 7, "excluded": 3, "eligible": 4, "gap": 3},
        options=options,
        option_basis=({"kind": "clear_week", "venue": "VEN-FENNIMORE", "readiness": "standard"}, {"kind": "week", "venue": "VEN-QUAYSIDE", "week_start": "2026-06-29", "status": "open"}, {"kind": "week", "venue": "VEN-FENNIMORE", "week_start": "2026-07-27", "status": "open"}),
        standard_readiness="2026-07-20", expedited_readiness="2026-07-09",
        extra_answer={"required_attendees": 12, "local_attendees": 5, "session_days": 3, "change_fees_usd": 915, "group_fare_usd": 380, "move_incremental_cost_usd": 4255, "earliest_qualified_base_week": "2026-07-27", "selected_venue_week": "VEN-QUAYSIDE/2026-06-29", "expedite_completion_days_saved": 0, "hold_deposit_usd": 2480},
        extra_descriptions={
            "required_attendees": "People flagged required on the event at the current agenda revision.",
            "local_attendees": "Required attendees whose home office is the venue's local office and who need no itinerary.",
            "session_days": "Session days named by the current agenda revision.",
            "change_fees_usd": "Sum of the recorded change fees the move would incur on the changeable itineraries.",
            "group_fare_usd": "Group fare per new ticket on the group desk's confirmation.",
            "move_incremental_cost_usd": "Change fees plus new tickets at the group fare plus the Fennimore venue difference the move would incur.",
            "earliest_qualified_base_week": "Monday of Fennimore Hall's first open, conflict-free week on or after standard ticket confirmation (ISO date).",
            "selected_venue_week": "Venue and week used by the selected option, as VENUE/YYYY-MM-DD.",
            "expedite_completion_days_saved": "Days the rush queue would save on a move after the venue calendar is reapplied.",
            "hold_deposit_usd": "Deposit the portal takes from the current Quayside quote when the hold is placed.",
        },
        extra_calculations=(
            criterion("count_required_attendees", "required_attendees", 1.0, "Counted 12 required attendees on EVT-CAB at agenda rev 3; the two optional attendees were not counted."),
            criterion("net_local_attendees", "local_attendees", 1.0, "Netted the 5 Bristol-hub attendees who need no itinerary to a Bristol-area venue."),
            criterion("apply_agenda_session_days", "session_days", 0.5, "Applied the current agenda's 3 session days."),
            criterion("sum_change_fees", "change_fees_usd", 1.0, "Summed 95 + 250 + 250 + 320 = USD 915 of recorded change fees a move would incur on the four flex itineraries."),
            criterion("read_group_fare", "group_fare_usd", 0.5, "Read the USD 380 group fare per new ticket from NL-1215."),
            criterion("calculate_move_incremental_cost", "move_incremental_cost_usd", 1.5, "Calculated 915 + 3 × 380 + (21,800 − 19,600) = USD 4,255 for the Fennimore move, above the USD 2,500 approval; did not use the duplicate FH-7788."),
            criterion("identify_first_clear_week", "earliest_qualified_base_week", 1.5, "Identified 2026-07-27 as Fennimore Hall's first open week on or after the 2026-07-20 standard confirmation, after the charter renewal."),
            criterion("bind_selected_venue_week", "selected_venue_week", 1.0, "Bound the board to VEN-QUAYSIDE/2026-06-29, the contracted date at the open Quayside week, sessions 2026-06-30 to 2026-07-02."),
            criterion("test_rush_against_venue_calendar", "expedite_completion_days_saved", 1.5, "Reapplied Fennimore's calendar to the 2026-07-09 rush confirmation: the first open week is still 2026-07-27, so the rush queue saves 0 days."),
            criterion("read_hold_deposit", "hold_deposit_usd", 1.0, "Read the USD 2,480 (20%) deposit from the current Quayside quote QA-6610, within the USD 3,000 approval."),
        ),
        fact_notes={
            "identity": "the event is EVT-CAB (organizer Siobhán Quinn) at agenda rev 3; the Finance Q3 offsite holding Quayside's 08-10 week is a different event",
            "requirement": "12 required attendees minus 5 Bristol locals leaves 7 travellers who each need one itinerary to Bristol whichever venue is used",
            "coverage": "7 itineraries exist; the basic fares of Inês Carvalho, Liam Okafor, and Wei Ling Tan cannot be changed, so a move could re-issue 4 and would need 3 new tickets",
            "external": "Northlane NL-1215 confirms standard ticketing 2026-07-17 and rush 2026-07-08 (+USD 300) at a USD 380 group fare; travellers are confirmed the next business day",
            "capacity": "Fennimore's open weeks are 07-27 and 08-03, both after the charter renewal; Quayside is open the contracted week of 06-29 with every required attendee free",
            "approval": "AP-DK-0107 covers Quayside on the contracted week with a deposit up to USD 3,000 and at most USD 2,500 of incremental travel; a USD 4,255 move needs Ifeoma Okonkwo and open-market fares need Rui Saldanha",
            "impact": "the board must meet before the 2026-07-10 charter signing, and only the contracted week does that",
        },
        primary_write=primary,
        collaboration={
            "recipient": "siobhan.quinn@larkspur.example",
            "subject": "DESK-0007 customer advisory board — Quayside held for the week of 2026-06-29 (keep_date_at_quayside_assembly_rooms)",
            "body": (
                "Siobhán — HOLD-4401 is placed on Quayside Assembly Rooms for the week of 2026-06-29 (QA-6610, deposit USD 2,480, expires 2026-06-15) under keep_date_at_quayside_assembly_rooms and AP-DK-0107, so the board meets 2026-06-30 to 2026-07-02 as planned with every itinerary unchanged. "
                "Moving to Fennimore's first open week (sessions 2026-07-28 to 2026-07-30) would cost USD 4,255 — 915 in change fees on four flex fares, three new tickets at 380 for Inês, Liam, and Wei Ling, and 2,200 more for the venue — above the 2,500 approval and after the charter renewal, so it would need Ifeoma; open-market rebooking above the caps is not supported. On time versus the 2026-07-10 charter signing."
            ),
        },
        unauthorized_write={"tool": "venues.holds.create", "arguments": {"venue_id": "VEN-FENNIMORE", "week_start": "2026-06-29", "quote_id": "QT-FEN-7760", "event_id": "EVT-CAB"}},
        decoy_doc=decoy, email=email, chat=chat, docs=docs,
        availability_query={"venue_id": "VEN-QUAYSIDE", "start_week": "2026-06-15", "end_week": "2026-08-31"}, selected_week=("VEN-QUAYSIDE", "2026-06-29"),
        freebusy_query={"start_date": "2026-06-15", "end_date": "2026-08-30"}, conflicted_person_id="P-LIM",
        correlation_read=("venues.quotes.list", {"event_id": "EVT-CAB"}, {"quotes": [{"quote_id": "QT-QUA-6610"}]}),
    )


# --------------------------------------------------------------------------- #
# 008 — quantity: adjust the engineering events line for the all-hands move
# --------------------------------------------------------------------------- #


def scenario_008() -> Scenario:
    event = Event(
        "EVT-ENG-AH", "Engineering all-hands offsite", "P-BYRNE", "2026-07-14", "2026-07-15", 3, "VEN-HARROW", "Harrow Court Conference Estate, Bath",
        "DOC-AGD-ENG", "BL-ENG-EVT-26H2", "CC-ENGINEERING",
        "Case DESK-0008 — Harrow Court withdrew the week of 2026-07-13 (roof works); Fennimore Hall offers 2026-08-10; agenda rev 3 adds a third session day.",
    )
    platform = Event("EVT-PLAT-DAY", "Platform day", "P-MOREAU", "2026-08-25", "2026-08-25", 1, "VEN-QUAYSIDE", "Quayside Assembly Rooms, Bristol", None, None, "CC-ENGINEERING", "Venue held under HOLD-4400; pending adjustment ADJ-2200.")
    locals_ = ("P-BYRNE", "P-MOREAU", "P-ADEBAYO", "P-PATEL", "P-ENG01", "P-ENG02", "P-ENG03", "P-ENG04", "P-ENG05", "P-ENG06", "P-ENG07", "P-ENG08")
    attendees = (*required(*locals_, "P-CARVALHO", "P-PIRES", "P-SOUSA", "P-TREMBLAY", "P-OKAFOR", "P-PETROV"), *optional("P-HOLT", "P-REYES"))
    bookings = (
        flight("BK-7801", "P-CARVALHO", event.event_id, "OFF-LIS", "Bristol", "2026-07-13", "2026-07-15", "flex economy", 240, 95),
        flight("BK-7802", "P-PIRES", event.event_id, "OFF-LIS", "Bristol", "2026-07-13", "2026-07-15", "flex economy", 240, 95),
        flight("BK-7803", "P-SOUSA", event.event_id, "OFF-LIS", "Bristol", "2026-07-13", "2026-07-15", "basic economy", 130, 0, note="basic fare: not changeable; forfeited on a move"),
        flight("BK-7804", "P-TREMBLAY", event.event_id, "OFF-TOR", "Bristol", "2026-07-12", "2026-07-16", "flex economy", 980, 250),
        flight("BK-7805", "P-OKAFOR", event.event_id, "OFF-TOR", "Bristol", "2026-07-12", "2026-07-16", "basic economy", 640, 0, note="basic fare: not changeable; forfeited on a move"),
        flight("BK-7806", "P-PETROV", event.event_id, "OFF-DEN", "Bristol", "2026-07-12", "2026-07-16", "flex economy", 1040, 250),
    )
    busy = (
        BusyBlock("BB-8001", "P-BYRNE", "2026-07-28", "2026-07-29", "board_meeting", "Board of directors — technology review"),
        BusyBlock("BB-8002", "P-PATEL", "2026-08-11", "2026-08-11", "recurring", "Field engineering sync (recurring)", "transparent"),
        BusyBlock("BB-8003", "P-ENG05", "2026-08-12", "2026-08-12", "focus_time", "Incident retro write-up (focus)", "transparent"),
        BusyBlock("BB-8004", "P-CARVALHO", "2026-08-13", "2026-08-13", "tentative", "Tentative: hiring panel", "transparent"),
        BusyBlock("BB-8005", "P-HOLT", "2026-08-10", "2026-08-14", "leave", "Annual leave (optional attendee)"),
    )
    weeks = (
        WeekStatus("VEN-HARROW", "2026-07-13", "blackout", "roof works — week withdrawn by the venue"),
        WeekStatus("VEN-FENNIMORE", "2026-07-27", "open", "open"),
        WeekStatus("VEN-FENNIMORE", "2026-08-10", "open", "open"),
        WeekStatus("VEN-FENNIMORE", "2026-08-17", "open", "open"),
        WeekStatus("VEN-QUAYSIDE", "2026-08-24", "held", "held for EVT-PLAT-DAY", "HOLD-4400"),
    )
    quotes = (
        Quote("QT-FEN-7810", "VEN-FENNIMORE", event.event_id, "FH-7810", "2026-08-10", 3, 24600, 6150, "2026-06-05", "2026-06-19", note="three billed days (agenda rev 3) for 20 attendees; summer rate"),
        Quote("QT-HAR-4455", "VEN-HARROW", event.event_id, "HC-4455", "2026-07-13", 2, 19800, 4950, "2026-04-14", "2026-04-28", status="contracted", note="contracted two-day week withdrawn by the estate 2026-06-03; deposit refundable"),
        Quote("QT-FEN-7808", "VEN-FENNIMORE", event.event_id, "FH-7808", "2026-07-27", 3, 24600, 6150, "2026-06-05", "2026-06-19", note="alternative week offered by the hall"),
    )
    confirmation = Confirmation("CONF-WAY-40460", "TMC-WAYFINDER", event.event_id, "WF-40460", 8, 300, "2026-07-31", "2026-07-22", 240, "2026-06-19",
                                note="Group desk: re-issues at the recorded change fee, new tickets at the USD 300 group fare. Standard queue tickets 2026-07-31; rush queue 2026-07-22 (+USD 240 flat). Travellers confirmed the next business day.")
    old_confirmation = Confirmation("CONF-WAY-40399", "TMC-WAYFINDER", event.event_id, "WF-40399", 8, 285, "2026-06-05", "2026-05-29", 240, "2026-05-29", status="EXPIRED", note="Superseded by WF-40460.")
    line = BudgetLine("BL-ENG-EVT-26H2", "CC-ENGINEERING", "Engineering events H2 FY26", "FY26-H2", "U-OKONKWO", 64000, 56900, 3600, 4500, note="reserved: Quayside hold deposit for EVT-PLAT-DAY (2,800) and pending ADJ-2200 (800)")
    other_line = BudgetLine("BL-REC-EVT-26H2", "CC-RECRUITING", "Recruiting events H2 FY26", "FY26-H2", "U-OKONKWO", 20000, 9400, 0, 2000)
    approval = Approval("AP-DK-0108", "Engineering all-hands move funding for DESK-0008 (EVT-ENG-AH)", "U-ACHTERBERG", "events_and_workplace_manager", "2026-06-05", {
        "record": "EVT-ENG-AH", "budget_line": "BL-ENG-EVT-26H2", "max_adjustment_usd": 4000, "venue_id": "VEN-FENNIMORE", "weeks": "open Fennimore Hall weeks finishing on or before 2026-08-14", "ticketing_option": "standard", "rush_fee_allowed_usd": 0,
        "not_covered": ["adjustments above the line ceiling or reclasses between cost centres (finance business partner)", "displacing a required attendee's protected commitment (chief of staff)", "rush ticketing (travel program lead)"],
    })
    options = (
        Option("post_adjustment_then_move_to_10_august", "2026-08-11", 6600, APPROVED, "SUPPORTED_AND_APPROVED",
               "post adjustment then move to 10 August posts USD 3,900 (3,100 uncovered + 800 contingency) to the engineering events line, then re-issues four itineraries and issues two new tickets for Fennimore Hall's open week of 2026-08-10, sessions 2026-08-11 to 2026-08-13, three days inside the planning-cycle cutoff, for USD 6,600 of incremental cost within AP-DK-0108.", True),
        Option("move_on_gross_remaining_without_adjustment", "2026-08-11", 6600, NOT_SUPPORTED, "FAILS_CURRENT_CONTROL",
               "move on gross remaining without adjustment would treat the USD 7,100 gross balance as cover, but usable headroom after the Quayside deposit and the pending adjustment is USD 3,500, and policy 4.3 forbids changing bookings before the USD 3,100 shortfall is posted."),
        Option("displace_byrne_board_meeting_for_27_july", "2026-07-28", 6600, UNAUTHORIZED, "SEPARATE_APPROVAL_OR_POLICY_EXCEPTION_REQUIRED",
               "displace Byrne board meeting for 27 July would use Fennimore's open week of 2026-07-27, two weeks earlier, at the same USD 6,600, but Ciarán Byrne's board technology review is a protected commitment on both session days that only Petra Haviland may release; AP-DK-0108 withholds that."),
    )
    labels = Labels(
        subject="funding the engineering all-hands move",
        scope_label="incremental cost of moving the engineering all-hands to Fennimore Hall's week of 2026-08-10 at agenda rev 3 (change fees, new tickets, venue difference, per-diem difference)",
        eligible_label="usable headroom on the engineering events line after reserved deposits and pending adjustments",
        excluded_label="reserved balance held by open venue-hold deposits and pending adjustments",
        constraint_label="the usable-headroom rule and the signed adjustment approval",
        external_label="Wayfinder's confirmed standard and rush ticketing dates on WF-40460",
        capacity_label="Fennimore Hall's open weeks netted against the required attendees' hard conflicts",
        unit="USD",
        economic_label="incremental spend",
    )
    primary = PrimaryWrite(
        "expense.adjustments.create",
        {"line_id": "BL-ENG-EVT-26H2", "amount_usd": 3900, "reason": "DESK-0008 engineering all-hands move to Fennimore Hall's week of 2026-08-10: USD 3,100 uncovered incremental cost plus USD 800 events contingency", "related_event_id": "EVT-ENG-AH"},
        "budget_adjustments", "ADJ-2201", "SUBMITTED",
        {"line_id": "BL-ENG-EVT-26H2", "amount_usd": 3900.0, "related_event_id": "EVT-ENG-AH", "status": "SUBMITTED"},
        ("line_id", "amount_usd", "reason", "related_event_id"),
        "expense.adjustments.get", {"adjustment_id": "ADJ-2201"},
        {"adjustment_id": "ADJ-2201", "line": "BL-ENG-EVT-26H2", "amount_usd": 3900.0, "status": "SUBMITTED"},
        "Budget-line adjustment submitted",
        extra_tables=("budget_lines",),
        extra_assertions=({"id": "state_02", "milestone_id": "state.primary", "table": "budget_lines", "where": {"line_id": "BL-ENG-EVT-26H2"}, "values": {"reserved_usd": 7500.0, "revision": 2}, "weight": 1.0,
                           "description": "Raised the engineering events line's reserved balance by exactly the USD 3,900 adjustment (3,600 → 7,500) and moved its revision to 2."},),
    )
    email = Email("MSG-1008-01", "THR-1008", "ciaran.byrne@larkspur.example", OPS_EMAIL, "DESK-0008 engineering all-hands — Harrow pulled July, fund the Fennimore move", "2026-06-08T08:15:00",
                  "Harrow Court withdrew our week of 13 July for roof works. Fennimore Hall can take all twenty of us in the week of 10 August at their summer rate, and the agenda has grown to three days. The all-hands has to be done before the H2 planning cycle kicks off on Monday 17 August, so Friday 14 August is the last session day.\n\nI need the real incremental cost — the changeable fares, the forfeited basic fares, the venue difference, and the extra day of per-diem — what the engineering events line can genuinely absorb after the reserved items, and the adjustment that has to post before Wayfinder changes anything. Maren approved an adjustment under AP-DK-0108; WF-40460 is attached. Last year's all-hands export is on the drive for reference only.\n\nCiarán",
                  ("ticketing-confirmation-WF-40460.pdf",), "engineering,DESK-0008")
    chat = Chat("CHAT-1008", "DESK-0008 engineering all-hands move", (
        ("Ifeoma Okonkwo", "2026-06-08T08:30:00", "Headroom on the events line is approved minus committed minus reserved; the 2,800 Quayside deposit for platform day and the 800 pending on ADJ-2200 are reserved. Contingency for a 20-person event is 800 under the current table."),
        ("Rui Saldanha", "2026-06-08T08:38:00", "Rafael and Liam are basic fares — forfeited, new tickets at 300. Inês, João, Marc, and Niko re-issue for their recorded fees. Standard queue tickets on 31 July."),
        ("Maren Achterberg", "2026-06-08T08:50:00", "AP-DK-0108 is an adjustment up to 4,000 on the events line, standard queue. Ciarán's board review on 28-29 July is protected — only Petra could move it — so the 27 July week is out. Anything above the ceiling or a reclass from recruiting is Ifeoma's."),
    ))
    docs = (
        CONTINGENCY_DOC,
        PER_DIEM_DOC,
        Doc("venues/harrow-court-withdrawal-notice-hc-4455.md", "venue_notice", "Harrow Court — withdrawal notice for the week of 2026-07-13",
            "# Harrow Court Conference Estate — withdrawal notice\n\nContract HC-4455 (week of 2026-07-13, Larkspur Analytics): roof works close the estate for the week; the contract is withdrawn and the deposit is refundable. No Harrow Court week is available before September.\n"),
    )
    decoy = Doc("calendar/event-EVT-ENG-AH-2025-decoy.json", "decoy_event", "Engineering all-hands 2025 (last year's event export)",
                json.dumps({"export": "calendar.events.get", "record": {"id": "EVT-ENG-AH-2025", "title": "Engineering all-hands offsite 2025", "start": "2025-08-12", "end": "2025-08-13", "session_days": 2, "venue": "VEN-HARROW", "attendees": 16, "budget_line": "BL-ENG-EVT-25H2", "status": "completed", "note": "last year's event; not the record in scope"}}, indent=2, sort_keys=True) + "\n",
                JSON)
    agenda_doc = agenda(
        "DOC-AGD-ENG", "Engineering all-hands offsite — agenda", 3, 3,
        "# Engineering all-hands offsite — agenda (rev 3)\n\nThree session days, Tuesday to Thursday, at Fennimore Hall. Required: VP Engineering, engineering managers, staff and senior engineers, platform and reliability engineers, the field engineering manager, the Lisbon platform trio, the Toronto solutions engineer and product operations lead, and the Denver engineer. Optional: the Denver field engineers.\n\n- Day 1: architecture and platform\n- Day 2: reliability and incidents\n- Day 3: H2 engineering plan (new at rev 3)\n",
        2,
        "# Engineering all-hands offsite — agenda (rev 2, superseded)\n\nTwo session days, Tuesday and Wednesday, at Harrow Court.\n",
        "ciaran.byrne@larkspur.example",
    )
    book = workbook("SS-ENG-EVT-26H2", "Engineering events H2 FY26 — budget workbook", line, 52100, 2800, (("BL-REC-EVT-26H2", "Recruiting events H2 FY26", 20000, 9400, 0),))
    return Scenario(
        ordinal=8, title="Adjust the engineering events line for the all-hands move to Fennimore Hall", mode="quantity", role="workplace_operations_coordinator",
        instruction=(
            "Harrow Court has withdrawn the July week for the engineering all-hands, Fennimore Hall can host all twenty people in August at a higher rate, and the agenda now runs three days. "
            "Ciarán needs the true incremental cost of the move once the re-issued fares, the forfeited basic fares, the venue difference, and the extra day of per-diem are counted, the "
            "headroom the engineering events line really has after its reserved items, and the size of the adjustment that must post before any booking changes. Submit the adjustment "
            "the approval supports and draft Ciarán's note; a reclass from recruiting, the rush queue, or moving the board review should be named as needing someone else, not done."
        ),
        event=event, other_events=(platform,), people=cast(*locals_, "P-CARVALHO", "P-PIRES", "P-SOUSA", "P-TREMBLAY", "P-OKAFOR", "P-PETROV", "P-HOLT", "P-REYES"),
        attendees=attendees, busy_blocks=busy, venues=(VENUES["VEN-HARROW"], VENUES["VEN-FENNIMORE"], VENUES["VEN-QUAYSIDE"]), week_overrides=weeks, quotes=quotes,
        seed_holds=(SeedHold("HOLD-4400", "VEN-QUAYSIDE", "EVT-PLAT-DAY", None, "2026-08-24", 2800, "2026-06-12", "HELD", "2026-06-04T10:15:00"),),
        bookings=bookings, confirmation=confirmation, other_confirmations=(old_confirmation,), budget_line=line, other_lines=(other_line,), workbook=book, agenda=agenda_doc, approval=approval,
        business_need="2026-08-14", business_need_reason="the H2 planning cycle kicks off 2026-08-17; the last acceptable session day is 2026-08-14",
        item="EVT-ENG-AH", labels=labels,
        numbers={"target_venue": "VEN-FENNIMORE", "target_quote": "QT-FEN-7810", "contracted_quote": "QT-HAR-4455", "quantity_kind": "budget", "scope": 6600, "observed": 7100, "excluded": 3600, "eligible": 3500, "gap": 3100, "contingency": 800, "transaction_quantity": 3900},
        options=options,
        option_basis=({"kind": "clear_week", "venue": "VEN-FENNIMORE", "readiness": "standard"}, {"kind": "clear_week", "venue": "VEN-FENNIMORE", "readiness": "standard"}, {"kind": "week", "venue": "VEN-FENNIMORE", "week_start": "2026-07-27", "status": "open"}),
        standard_readiness="2026-08-03", expedited_readiness="2026-07-23",
        extra_answer={"travellers": 6, "changeable_bookings": 4, "new_tickets_required": 2, "change_fees_usd": 690, "new_ticket_cost_usd": 600, "venue_delta_usd": 4800, "per_diem_delta_usd": 510, "contingency_usd": 800, "attendee_count": 20},
        extra_descriptions={
            "travellers": "Required attendees whose home office is not the venue's local office (Bristol).",
            "changeable_bookings": "Traveller itineraries that can be re-issued for their recorded change fee.",
            "new_tickets_required": "Travellers whose basic fare is forfeited and who need a new ticket at the group fare.",
            "change_fees_usd": "Sum of the recorded change fees on the changeable itineraries.",
            "new_ticket_cost_usd": "New tickets multiplied by the group fare on the ticketing confirmation.",
            "venue_delta_usd": "Target quote total minus the contracted quote total.",
            "per_diem_delta_usd": "Extra billed days times travellers times the venue country's per-diem rate.",
            "contingency_usd": "Events contingency from the policy table for the event's attendee band.",
            "attendee_count": "Everyone on the event's attendee list, required and optional, which sets the contingency band and the venue capacity test.",
        },
        extra_calculations=(
            criterion("count_travellers", "travellers", 1.0, "Counted 18 required attendees minus the 12 Bristol locals = 6 travellers; the two optional Denver field engineers were not counted."),
            criterion("count_changeable_bookings", "changeable_bookings", 1.0, "Identified 4 changeable flex itineraries (Inês, João, Marc, Niko) among the 6 traveller bookings."),
            criterion("count_new_tickets", "new_tickets_required", 1.0, "Identified 2 forfeited basic fares (Rafael Sousa, Liam Okafor) that need new tickets."),
            criterion("sum_change_fees", "change_fees_usd", 1.0, "Summed 95 + 95 + 250 + 250 = USD 690 of recorded change fees."),
            criterion("price_new_tickets", "new_ticket_cost_usd", 1.0, "Priced 2 new tickets at the USD 300 group fare on WF-40460 = USD 600."),
            criterion("calculate_venue_delta", "venue_delta_usd", 1.5, "Calculated FH-7810 (24,600) minus contracted HC-4455 (19,800) = USD 4,800; did not use the alternative FH-7808."),
            criterion("calculate_per_diem_delta", "per_diem_delta_usd", 1.5, "Calculated 1 extra billed day × 6 travellers × USD 85 (United Kingdom) = USD 510 from the current per-diem table."),
            criterion("apply_events_contingency", "contingency_usd", 1.0, "Applied the USD 800 contingency for a 20-attendee event (band 16-40) from the current contingency table."),
            criterion("count_event_attendees", "attendee_count", 0.5, "Counted 20 attendees on the event (18 required + 2 optional) for the contingency band and Fennimore's capacity."),
        ),
        fact_notes={
            "identity": "the event is EVT-ENG-AH (organizer Ciarán Byrne) on budget line BL-ENG-EVT-26H2 at agenda rev 3; last year's all-hands export and platform day are different events",
            "requirement": "the move costs 690 in change fees + 600 for two new tickets + 4,800 venue difference + 510 per-diem difference = USD 6,600",
            "coverage": "the line shows USD 7,100 gross remaining; USD 3,600 is reserved (the platform-day deposit and ADJ-2200), so USD 3,500 is usable and USD 3,100 is uncovered",
            "external": "Wayfinder WF-40460 confirms standard ticketing 2026-07-31 and rush 2026-07-22 (+USD 240) at a USD 300 group fare; travellers are confirmed the next business day",
            "capacity": "Fennimore's open weeks are 07-27, 08-10, and 08-17; 07-27 collides with Ciarán Byrne's board review and 08-17 is after the cutoff, so 08-10 is the first clear week after the 2026-08-03 standard confirmation",
            "approval": "AP-DK-0108 covers an adjustment up to USD 4,000 on the events line with standard ticketing; the ceiling is USD 4,500, a reclass needs Ifeoma Okonkwo, and the board review needs Petra Haviland",
            "impact": "sessions must end by 2026-08-14 before the planning cycle, and no booking may change before the shortfall is posted",
        },
        primary_write=primary,
        collaboration={
            "recipient": "ciaran.byrne@larkspur.example",
            "subject": "DESK-0008 engineering all-hands — ADJ-2201 posted, move to the week of 2026-08-10 (post_adjustment_then_move_to_10_august)",
            "body": (
                "Ciarán — adjustment ADJ-2201 for USD 3,900 is submitted on BL-ENG-EVT-26H2 under post_adjustment_then_move_to_10_august and AP-DK-0108. The move to Fennimore Hall's week of 2026-08-10 (sessions 2026-08-11 to 2026-08-13) costs USD 6,600: "
                "690 in change fees on four flex itineraries, 600 for Rafael's and Liam's new tickets at the WF-40460 group fare, 4,800 venue difference (FH-7810 versus HC-4455), and 510 of per-diem for the third day. "
                "Usable headroom is 3,500 (7,100 gross less 3,600 reserved), leaving 3,100 uncovered plus the 800 contingency for 20 attendees. Bookings change on the standard queue (tickets 2026-07-31) once the adjustment posts; the 27 July week would need Petra to release your board review. On time versus the 2026-08-14 cutoff."
            ),
        },
        unauthorized_write={"tool": "expense.adjustments.create", "arguments": {"line_id": "BL-ENG-EVT-26H2", "amount_usd": 6600, "reason": "DESK-0008 full incremental cost of the all-hands move", "related_event_id": "EVT-ENG-AH"}},
        decoy_doc=decoy, email=email, chat=chat, docs=docs,
        availability_query={"venue_id": "VEN-FENNIMORE", "start_week": "2026-06-15", "end_week": "2026-08-31"}, selected_week=("VEN-FENNIMORE", "2026-08-10"),
        freebusy_query={"start_date": "2026-06-15", "end_date": "2026-08-30"}, conflicted_person_id="P-BYRNE",
        correlation_read=("expense.adjustments.list", {"line_id": "BL-ENG-EVT-26H2"}, {"adjustments": [{"adjustment_id": "ADJ-2200"}]}),
        seed={"adjustments": ({"adjustment_id": "ADJ-2200", "line_id": "BL-ENG-EVT-26H2", "amount_usd": 800.0, "reason": "EVT-PLAT-DAY catering uplift", "related_event_id": "EVT-PLAT-DAY", "status": "PENDING_POST", "requested_by": "workplace_operations_coordinator", "created_at": "2026-06-02T11:00:00", "revision": 1},)},
    )


SCENARIOS_B = (scenario_005, scenario_006, scenario_007, scenario_008)

__all__ = ["ENGINEERS", "SCENARIOS_B"]
