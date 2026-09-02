"""Scenario data model and shared synthetic entities for the DesignOps family.

Everything here is clean-room synthetic: Ashgrove Motion Systems is not a
real organisation and no engineer, supplier, laboratory, plant, part, or
assembly corresponds to a real one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from ...engine.assets import MARKDOWN
from ...engine.decision import Labels, Option

AS_OF = "2026-05-11"
ORGANIZATION = {
    "id": "ashgrove-eco-v1",
    "name": "Ashgrove Motion Systems — Engineering Change Office",
    "organization_id": "ORG-ASHGROVE",
    "primary_site": "PLANT-ASH",
    "systems": ["plm", "eco", "bom", "cert", "tooling", "supplier", "calendar", "approvals", "messages", "chat", "drive", "notes"],
}
PLANTS = (
    {"plant_id": "PLANT-ASH", "name": "Ashgrove main plant (cells A and B)", "type": "assembly_plant"},
    {"plant_id": "PLANT-KEL", "name": "Kelbrook satellite plant", "type": "satellite_plant"},
    {"plant_id": "PLANT-TR", "name": "Ashgrove tool room and calibration lab", "type": "tool_room"},
)
ENGINEERS = (
    {"engineer_id": "ENG-HALE", "name": "Rowan Hale", "role": "design_engineer", "focus": "Brackets and structures"},
    {"engineer_id": "ENG-BAPTISTE", "name": "Célia Baptiste", "role": "manufacturing_engineer", "focus": "Cell A assembly lines"},
    {"engineer_id": "ENG-NAKAMURA", "name": "Kenji Nakamura", "role": "certification_engineer", "focus": "Product certification programs"},
    {"engineer_id": "ENG-OYELOWO", "name": "Tunde Oyelowo", "role": "quality_engineer", "focus": "Calibration and first-article inspection"},
    {"engineer_id": "ENG-SZABO", "name": "Márta Szabó", "role": "supplier_quality_engineer", "focus": "Tooling suppliers"},
)
USERS = (
    {"user_id": "U-ECO", "display_name": "Engineering Change Coordinator (you)", "role": "engineering_change_coordinator", "approval_limit_usd": 0},
    {"user_id": "U-ADEYEMI", "display_name": "Folake Adeyemi", "role": "configuration_manager", "approval_limit_usd": 25000},
    {"user_id": "U-LINDQVIST", "display_name": "Sören Lindqvist", "role": "director_of_engineering", "approval_limit_usd": 150000},
    {"user_id": "U-OKAFOR", "display_name": "Chidi Okafor", "role": "manufacturing_engineering_lead", "approval_limit_usd": 15000},
    {"user_id": "U-VOSS", "display_name": "Henrike Voss", "role": "change_board_chair", "approval_limit_usd": 0},
)
SUPPLIERS = (
    {"supplier_id": "SUP-BRAMWELL", "name": "Bramwell Tool & Gauge", "kind": "tooling", "account_number": "AM-2207"},
    {"supplier_id": "SUP-FERRIN", "name": "Ferrin Fixture Works", "kind": "tooling", "account_number": "AM-0918"},
    {"supplier_id": "LAB-NORTHBANK", "name": "Northbank Test Laboratories", "kind": "test_lab", "account_number": "AM-4471"},
)
WINDOW_TIMES = {"AM": ("07:00:00", "11:00:00"), "PM": ("12:00:00", "16:00:00")}
WINDOW_HOURS = 4
CALENDAR_WEEKS = 4


def business_days(start: str = AS_OF, weeks: int = CALENDAR_WEEKS) -> list[str]:
    first = date.fromisoformat(start)
    days = []
    for offset in range(weeks * 7):
        day = first + timedelta(days=offset)
        if day.weekday() < 5:
            days.append(day.isoformat())
    return days


def next_business_day(after: str) -> str:
    """First business day strictly after ``after`` (certificates issue and received sets release the next business day)."""

    day = date.fromisoformat(after) + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.isoformat()


def window_id(line: str, day: str, session: str) -> str:
    return f"WIN-{line.split('-')[1]}-{day.replace('-', '')}-{session}"


def window_interval(day: str, session: str) -> tuple[str, str]:
    start, end = WINDOW_TIMES[session]
    return f"{day}T{start}", f"{day}T{end}"


@dataclass(frozen=True)
class Revision:
    revision: str
    status: str  # RELEASED | SUPERSEDED | OBSOLETE | IN_WORK
    released_on: str | None = None
    superseded_on: str | None = None
    note: str = ""


@dataclass(frozen=True)
class Part:
    part_id: str
    number: str
    name: str
    part_type: str  # component | assembly
    owner_team: str
    engineer_id: str
    current_revision: str
    revisions: tuple[Revision, ...] = ()


@dataclass(frozen=True)
class Document:
    document_id: str
    part_id: str
    kind: str  # model | drawing
    number: str
    version: int
    revision: str
    status: str  # RELEASED | SUPERSEDED | IN_WORK
    checked_in_at: str
    checked_in_by: str
    note: str = ""


@dataclass(frozen=True)
class Checkin:
    checkin_id: str
    document_id: str
    version: int
    checked_in_at: str
    check_kind: str
    status: str  # PASSED | FAILED
    summary: str


@dataclass(frozen=True)
class ChangeOrder:
    change_id: str
    part_id: str
    from_revision: str
    to_revision: str
    change_class: str  # CLASS_I | CLASS_II
    title: str
    reason: str
    state: str  # DRAFT | SUBMITTED | CCB_APPROVED | RELEASED | WITHDRAWN | SUPERSEDED
    fixture_family: str
    fai_minutes: int
    changeover_minutes: int
    requested_by: str
    opened_at: str
    required_by: str | None = None
    effectivity_basis: str = "date"
    effectivity_date: str | None = None
    note: str = ""


@dataclass(frozen=True)
class AffectedItem:
    item_id: str
    change_id: str
    assembly_part_id: str
    assembly_revision: str
    disposition: str
    in_scope: bool = True
    note: str = ""


@dataclass(frozen=True)
class BomLine:
    line_id: str
    parent_part_id: str
    parent_revision: str
    component_part_id: str
    find_number: int
    qty_per: int
    line_kind: str = "primary"  # primary | alternate | phantom
    effectivity_end: str | None = None
    note: str = ""


@dataclass(frozen=True)
class Certification:
    cert_id: str
    assembly_part_id: str
    assembly_revision: str
    program: str
    status: str  # ACTIVE | EXPIRED | SUPERSEDED | WITHDRAWN
    issued_on: str
    expires_on: str
    covered: dict[str, str]
    recert_lead_days: int
    recert_test_fee_usd: float
    note: str = ""


@dataclass(frozen=True)
class FixtureFamily:
    code: str
    display: str
    sets_per_station: int = 1
    calibration_interval_days: int = 365
    min_remaining_calibration_days: int = 14
    revision_specific: bool = True
    interchangeable_with: str | None = None


@dataclass(frozen=True)
class FixtureSet:
    set_id: str
    set_label: str
    family: str
    plant_id: str
    sets: int
    calibration_due: str
    status: str = "CALIBRATED"
    reason: str | None = None
    reserved_for: str | None = None
    register_excluded: bool = False
    register_note: str = ""


@dataclass(frozen=True)
class Line:
    line_id: str
    name: str
    stations: int = 2
    plant_id: str = "PLANT-ASH"
    status: str = "ACTIVE"
    fai_capable: bool = True
    note: str | None = None


@dataclass(frozen=True)
class Window:
    day: str
    line: str
    session: str
    status: str
    reason: str = ""


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    assembly_part_id: str
    change_id: str | None
    line_id: str | None
    start: str | None
    end: str | None
    status: str
    description: str


@dataclass(frozen=True)
class Quote:
    quote_id: str
    supplier_id: str
    item_code: str
    reference: str
    quantity_available: int
    standard_date: str
    expedited_date: str
    fee: int
    unit_price: float
    valid_until: str
    status: str = "OPEN"
    note: str = ""


@dataclass(frozen=True)
class SeedOrder:
    order_id: str
    supplier_id: str
    item_code: str
    quantity: int
    unit: str
    service_option: str
    expected_ready_date: str
    total_cost_usd: float
    status: str
    created_at: str
    quote_id: str | None = None


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
    labels: str = "engineering-change"


@dataclass(frozen=True)
class Chat:
    thread_id: str
    title: str
    messages: tuple[tuple[str, str, str], ...]
    channel: str = "#engineering-change"


@dataclass(frozen=True)
class Doc:
    path: str
    kind: str
    title: str
    content: str = ""
    media_type: str = MARKDOWN
    rows: tuple[tuple[Any, ...], ...] | None = None
    folder: str = "Engineering Change Office"


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
    part: Part
    other_parts: tuple[Part, ...]
    change: ChangeOrder
    other_changes: tuple[ChangeOrder, ...]
    affected_items: tuple[AffectedItem, ...]
    bom_lines: tuple[BomLine, ...]
    documents: tuple[Document, ...]
    checkins: tuple[Checkin, ...]
    families: tuple[FixtureFamily, ...]
    fixture_sets: tuple[FixtureSet, ...]
    lines: tuple[Line, ...]
    windows: tuple[Window, ...]
    reservations: tuple[Reservation, ...]
    certifications: tuple[Certification, ...]
    quote: Quote
    other_quotes: tuple[Quote, ...]
    seed_orders: tuple[SeedOrder, ...]
    approval: Approval
    business_need: str
    business_need_reason: str
    item: str
    labels: Labels
    numbers: dict[str, Any]
    options: tuple[Option, Option, Option]
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
    windows_query: dict[str, str]
    selected_window_id: str
    checkin_query: dict[str, Any]
    checkin_expected: dict[str, Any]
    seed: dict[str, Any] = field(default_factory=dict)

    @property
    def task_id(self) -> str:
        return f"designops-{self.ordinal:03d}"

    @property
    def case_reference(self) -> str:
        return f"DSGN-{self.ordinal:04d}"

    @property
    def revision(self) -> str:
        return self.change.to_revision

    @property
    def primary_family(self) -> FixtureFamily:
        return next(item for item in self.families if item.code == self.change.fixture_family)

    @property
    def all_parts(self) -> tuple[Part, ...]:
        return (self.part, *self.other_parts)


def parts_by_id(scenario: Scenario) -> dict[str, Part]:
    return {part.part_id: part for part in scenario.all_parts}


def lines_by_id(scenario: Scenario) -> dict[str, Line]:
    return {line.line_id: line for line in scenario.lines}


__all__ = [
    "AS_OF",
    "AffectedItem",
    "Approval",
    "BomLine",
    "CALENDAR_WEEKS",
    "Certification",
    "ChangeOrder",
    "Chat",
    "Checkin",
    "Doc",
    "Document",
    "ENGINEERS",
    "Email",
    "FixtureFamily",
    "FixtureSet",
    "Labels",
    "Line",
    "ORGANIZATION",
    "Option",
    "PLANTS",
    "Part",
    "PrimaryWrite",
    "Quote",
    "Reservation",
    "Revision",
    "SUPPLIERS",
    "Scenario",
    "SeedOrder",
    "USERS",
    "WINDOW_HOURS",
    "WINDOW_TIMES",
    "Window",
    "business_days",
    "lines_by_id",
    "next_business_day",
    "parts_by_id",
    "window_id",
    "window_interval",
]
