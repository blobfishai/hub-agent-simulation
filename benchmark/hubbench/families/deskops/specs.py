"""Scenario data model and shared synthetic entities for the DeskOps family.

Everything here is clean-room synthetic: Larkspur Analytics is not a real
organisation and no person, venue, travel management company, booking, or
budget corresponds to a real one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from ...engine.assets import MARKDOWN
from ...engine.decision import Labels, Option
from .tools import HARD_KINDS

AS_OF = "2026-06-08"
ORGANIZATION = {
    "id": "larkspur-workplace-v1",
    "name": "Larkspur Analytics — Workplace & Events Operations",
    "organization_id": "ORG-LARKSPUR",
    "primary_site": "OFF-BRS",
    "systems": ["mail", "calendar", "directory", "docs", "sheets", "drive", "venues", "travel", "expense", "approvals", "chat", "notes"],
}
OFFICES = (
    {"office_id": "OFF-BRS", "name": "Bristol hub (headquarters)", "city": "Bristol", "country": "GB", "timezone": "Europe/London", "region": "europe"},
    {"office_id": "OFF-LIS", "name": "Lisbon office", "city": "Lisbon", "country": "PT", "timezone": "Europe/Lisbon", "region": "europe"},
    {"office_id": "OFF-TOR", "name": "Toronto office", "city": "Toronto", "country": "CA", "timezone": "America/Toronto", "region": "north-america"},
    {"office_id": "OFF-DEN", "name": "Denver office", "city": "Denver", "country": "US", "timezone": "America/Denver", "region": "north-america"},
    {"office_id": "OFF-SGP", "name": "Singapore office", "city": "Singapore", "country": "SG", "timezone": "Asia/Singapore", "region": "asia-pacific"},
)
OFFICE_BY_ID = {row["office_id"]: row for row in OFFICES}
ROOMS = (
    {"room_id": "ROOM-BRS-ATRIUM", "office_id": "OFF-BRS", "name": "Bristol atrium event space", "capacity": 40, "bookable": 0, "note": "closed 2026-06-15 to 2026-07-03 for HVAC replacement"},
    {"room_id": "ROOM-BRS-HARBOUR", "office_id": "OFF-BRS", "name": "Harbourside boardroom", "capacity": 14, "bookable": 1, "note": None},
    {"room_id": "ROOM-LIS-TAGUS", "office_id": "OFF-LIS", "name": "Tagus room", "capacity": 12, "bookable": 1, "note": None},
    {"room_id": "ROOM-TOR-LAKE", "office_id": "OFF-TOR", "name": "Lakeshore room", "capacity": 10, "bookable": 1, "note": None},
)
USERS = (
    {"user_id": "U-OPS", "display_name": "Workplace Operations Coordinator (you)", "role": "workplace_operations_coordinator", "approval_limit_usd": 0},
    {"user_id": "U-ACHTERBERG", "display_name": "Maren Achterberg", "role": "events_and_workplace_manager", "approval_limit_usd": 20000},
    {"user_id": "U-OKONKWO", "display_name": "Ifeoma Okonkwo", "role": "finance_business_partner", "approval_limit_usd": 120000},
    {"user_id": "U-SALDANHA", "display_name": "Rui Saldanha", "role": "travel_program_lead", "approval_limit_usd": 15000},
    {"user_id": "U-HAVILAND", "display_name": "Petra Haviland", "role": "chief_of_staff", "approval_limit_usd": 0},
)
TMCS = (
    {"tmc_id": "TMC-WAYFINDER", "name": "Wayfinder Corporate Travel", "account_number": "LA-2210"},
    {"tmc_id": "TMC-NORTHLANE", "name": "Northlane Travel Partners", "account_number": "LA-0877"},
)
OPS_EMAIL = "workplace-ops@larkspur.example"
HORIZON_START = "2026-06-15"
WEEK_COUNT = 12
SESSION_START_OFFSET = 1  # sessions start on the Tuesday of the venue week
WEEKDAYS = 5


def week_starts(start: str = HORIZON_START, weeks: int = WEEK_COUNT) -> list[str]:
    first = date.fromisoformat(start)
    if first.weekday() != 0:
        raise ValueError("the horizon must start on a Monday")
    return [(first + timedelta(days=7 * offset)).isoformat() for offset in range(weeks)]


def next_business_day(after: str) -> str:
    """First business day strictly after ``after`` (tickets are confirmed to travellers the next business day after issue)."""

    day = date.fromisoformat(after) + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.isoformat()


def offsite_dates(week_start: str, session_days: int) -> tuple[str, str]:
    start = date.fromisoformat(week_start) + timedelta(days=SESSION_START_OFFSET)
    return start.isoformat(), (start + timedelta(days=session_days - 1)).isoformat()


def session_dates(week_start: str, session_days: int) -> list[str]:
    start = date.fromisoformat(week_start) + timedelta(days=SESSION_START_OFFSET)
    return [(start + timedelta(days=offset)).isoformat() for offset in range(session_days)]


def week_id(venue_id: str, week_start: str) -> str:
    return f"VW-{venue_id.split('-', 1)[1]}-{week_start.replace('-', '')}"


def is_hard(kind: str) -> bool:
    return kind in HARD_KINDS


@dataclass(frozen=True)
class Person:
    person_id: str
    name: str
    email: str
    title: str
    team: str
    office_id: str
    employment: str = "employee"


@dataclass(frozen=True)
class Attendee:
    person_id: str
    required: bool = True
    response: str = "accepted"
    note: str = ""


@dataclass(frozen=True)
class BusyBlock:
    block_id: str
    person_id: str
    start: str
    end: str
    kind: str
    title: str
    transparency: str = "opaque"


@dataclass(frozen=True)
class Venue:
    venue_id: str
    name: str
    city: str
    country: str
    local_office_id: str | None
    capacity: int
    events_director: str
    hold_business_days: int = 10
    deposit_pct: int = 25
    note: str = ""


@dataclass(frozen=True)
class WeekStatus:
    venue_id: str
    week_start: str
    status: str
    note: str = ""
    hold_id: str | None = None


@dataclass(frozen=True)
class Quote:
    quote_id: str
    venue_id: str
    event_id: str | None
    reference: str
    week_start: str
    days: int
    total: int
    deposit: int
    issued_on: str
    valid_until: str
    status: str = "current"
    note: str = ""


@dataclass(frozen=True)
class SeedHold:
    hold_id: str
    venue_id: str
    event_id: str
    quote_id: str | None
    week_start: str
    deposit: int
    expires_on: str
    status: str
    created_at: str


@dataclass(frozen=True)
class Event:
    event_id: str
    title: str
    organizer_id: str
    start: str
    end: str
    session_days: int
    venue_id: str
    location: str
    agenda_doc_id: str
    budget_line_id: str
    cost_center: str
    description: str
    status: str = "confirmed"


@dataclass(frozen=True)
class Booking:
    booking_id: str
    person_id: str
    event_id: str
    tmc_id: str
    record_locator: str
    origin_office_id: str | None
    destination_city: str
    travel_date: str
    return_date: str
    fare_class: str
    fare: int
    changeable: bool
    change_fee: int
    refundable: bool = False
    kind: str = "flight"
    status: str = "ticketed"
    note: str = ""


@dataclass(frozen=True)
class Confirmation:
    confirmation_id: str
    tmc_id: str
    event_id: str
    reference: str
    seats_available: int
    group_fare: int
    standard_date: str
    rush_date: str
    rush_fee: int
    valid_until: str
    status: str = "OPEN"
    note: str = ""


@dataclass(frozen=True)
class BudgetLine:
    line_id: str
    cost_center: str
    name: str
    fiscal_period: str
    owner_id: str
    approved: int
    committed: int
    reserved: int
    ceiling: int
    status: str = "open"
    note: str = ""


@dataclass(frozen=True)
class WorkbookVersion:
    version: int
    status: str
    modified_time: str
    modified_by: str
    rows: tuple[tuple[Any, ...], ...]


@dataclass(frozen=True)
class Workbook:
    spreadsheet_id: str
    title: str
    folder: str
    versions: tuple[WorkbookVersion, ...]

    @property
    def current(self) -> WorkbookVersion:
        return next(item for item in self.versions if item.status == "current")


@dataclass(frozen=True)
class AgendaRevision:
    revision_id: str
    revision: int
    status: str
    modified_time: str
    modified_by: str
    body: str
    session_days: int
    note: str = ""


@dataclass(frozen=True)
class Agenda:
    doc_id: str
    title: str
    folder: str
    revisions: tuple[AgendaRevision, ...]

    @property
    def current(self) -> AgendaRevision:
        return next(item for item in self.revisions if item.status == "current")


@dataclass(frozen=True)
class Approval:
    approval_id: str
    subject: str
    approver_id: str
    approver_role: str
    granted_on: str
    scope: dict[str, Any]


@dataclass(frozen=True)
class Email:
    message_id: str
    thread_id: str
    sender: str
    recipients: str
    subject: str
    sent_at: str
    body: str
    attachments: tuple[str, ...] = ()
    labels: str = "workplace-ops"


@dataclass(frozen=True)
class Chat:
    thread_id: str
    title: str
    messages: tuple[tuple[str, str, str], ...]
    channel: str = "#workplace-ops"


@dataclass(frozen=True)
class Doc:
    path: str
    kind: str
    title: str
    content: str = ""
    media_type: str = MARKDOWN
    rows: tuple[tuple[Any, ...], ...] | None = None
    folder: str = "Workplace Operations"


@dataclass(frozen=True)
class PrimaryWrite:
    tool: str
    arguments: dict[str, Any]
    table: str
    record_id: str
    status: str
    domain_values: dict[str, Any]
    allowed_paths: tuple[str, ...]
    readback_tool: str
    readback_arguments: dict[str, Any]
    readback_expected: dict[str, Any]
    outcome_label: str
    extra_tables: tuple[str, ...] = ()
    extra_assertions: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class Scenario:
    ordinal: int
    title: str
    mode: str
    role: str
    instruction: str
    event: Event
    other_events: tuple[Event, ...]
    people: tuple[Person, ...]
    attendees: tuple[Attendee, ...]
    busy_blocks: tuple[BusyBlock, ...]
    venues: tuple[Venue, ...]
    week_overrides: tuple[WeekStatus, ...]
    quotes: tuple[Quote, ...]
    seed_holds: tuple[SeedHold, ...]
    bookings: tuple[Booking, ...]
    confirmation: Confirmation
    other_confirmations: tuple[Confirmation, ...]
    budget_line: BudgetLine
    other_lines: tuple[BudgetLine, ...]
    workbook: Workbook
    agenda: Agenda
    approval: Approval
    business_need: str
    business_need_reason: str
    item: str
    labels: Labels
    numbers: dict[str, Any]
    options: tuple[Option, Option, Option]
    option_basis: tuple[dict[str, Any], dict[str, Any], dict[str, Any]]
    standard_readiness: str
    expedited_readiness: str
    extra_answer: dict[str, Any]
    extra_descriptions: dict[str, str]
    extra_calculations: tuple[dict[str, Any], ...]
    fact_notes: dict[str, str]
    primary_write: PrimaryWrite
    collaboration: dict[str, str]
    unauthorized_write: dict[str, Any]
    decoy_doc: Doc
    email: Email
    chat: Chat
    docs: tuple[Doc, ...]
    availability_query: dict[str, str]
    selected_week: tuple[str, str]
    freebusy_query: dict[str, str]
    conflicted_person_id: str
    correlation_read: tuple[str, dict[str, Any], dict[str, Any]]
    default_week_status: tuple[str, str] = ("booked", "exclusive hire — another client")
    revision: str = "v1"
    seed: dict[str, Any] = field(default_factory=dict)

    @property
    def task_id(self) -> str:
        return f"deskops-{self.ordinal:03d}"

    @property
    def case_reference(self) -> str:
        return f"DESK-{self.ordinal:04d}"

    @property
    def target_venue(self) -> Venue:
        return next(item for item in self.venues if item.venue_id == self.numbers["target_venue"])

    @property
    def venue_by_id(self) -> dict[str, Venue]:
        return {item.venue_id: item for item in self.venues}

    @property
    def person_by_id(self) -> dict[str, Person]:
        return {item.person_id: item for item in self.people}

    @property
    def required_attendees(self) -> list[Attendee]:
        return [item for item in self.attendees if item.required]

    @property
    def target_quote(self) -> Quote:
        return next(item for item in self.quotes if item.quote_id == self.numbers["target_quote"])

    @property
    def selected_week_id(self) -> str:
        return week_id(self.selected_week[0], self.selected_week[1])


def travellers(scenario: Scenario, venue: Venue | None = None) -> list[Person]:
    """Required attendees whose home office is not the venue's local office."""

    venue = venue or scenario.target_venue
    people = scenario.person_by_id
    return [people[item.person_id] for item in scenario.required_attendees if people[item.person_id].office_id != venue.local_office_id]


def conflict_attendee_days(scenario: Scenario, week_start: str, session_days: int | None = None) -> int:
    """Session days on which a required attendee has a hard conflict, summed over required attendees."""

    days = session_dates(week_start, session_days or scenario.event.session_days)
    total = 0
    for attendee in scenario.required_attendees:
        blocks = [block for block in scenario.busy_blocks if block.person_id == attendee.person_id and is_hard(block.kind)]
        total += sum(1 for day in days if any(block.start <= day <= block.end for block in blocks))
    return total


def week_grid(scenario: Scenario) -> dict[tuple[str, str], dict[str, Any]]:
    overrides = {(item.venue_id, item.week_start): item for item in scenario.week_overrides}
    default_status, default_note = scenario.default_week_status
    grid: dict[tuple[str, str], dict[str, Any]] = {}
    for venue in scenario.venues:
        for week in week_starts():
            override = overrides.get((venue.venue_id, week))
            if override is None:
                grid[(venue.venue_id, week)] = {"status": default_status, "note": default_note, "hold_id": None}
            else:
                grid[(venue.venue_id, week)] = {"status": override.status, "note": override.note, "hold_id": override.hold_id}
    return grid


def first_clear_week(scenario: Scenario, venue_id: str, on_or_after: str) -> str | None:
    """First venue week on or after ``on_or_after`` that is OPEN, seats everyone, and has no required-attendee hard conflict on a session day."""

    grid = week_grid(scenario)
    venue = scenario.venue_by_id[venue_id]
    headcount = len(scenario.attendees)
    for week in week_starts():
        if week < on_or_after:
            continue
        entry = grid[(venue_id, week)]
        if entry["status"] != "open" or venue.capacity < headcount:
            continue
        if conflict_attendee_days(scenario, week) == 0:
            return week
    return None


__all__ = [
    "AS_OF",
    "Agenda",
    "AgendaRevision",
    "Approval",
    "Attendee",
    "Booking",
    "BudgetLine",
    "BusyBlock",
    "Chat",
    "Confirmation",
    "Doc",
    "Email",
    "Event",
    "HORIZON_START",
    "Labels",
    "OFFICES",
    "OFFICE_BY_ID",
    "OPS_EMAIL",
    "ORGANIZATION",
    "Option",
    "Person",
    "PrimaryWrite",
    "Quote",
    "ROOMS",
    "SESSION_START_OFFSET",
    "Scenario",
    "SeedHold",
    "TMCS",
    "USERS",
    "Venue",
    "WEEKDAYS",
    "WEEK_COUNT",
    "WeekStatus",
    "Workbook",
    "WorkbookVersion",
    "conflict_attendee_days",
    "first_clear_week",
    "is_hard",
    "next_business_day",
    "offsite_dates",
    "session_dates",
    "travellers",
    "week_grid",
    "week_id",
    "week_starts",
]
