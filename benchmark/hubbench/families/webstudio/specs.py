"""Scenario data model and shared synthetic entities for the WebStudio family.

Everything here is clean-room synthetic: Larkspur Commerce is not a real
organisation and no designer, vendor, page, token, asset, or licence
corresponds to a real one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from ...engine.assets import MARKDOWN
from ...engine.decision import Labels, Option

AS_OF = "2026-05-11"
RENEWAL_HORIZON_DAYS = 14
ORGANIZATION = {
    "id": "larkspur-webstudio-v1",
    "name": "Larkspur Commerce — Web Platform Studio",
    "organization_id": "ORG-LARKSPUR",
    "primary_site": "ENV-PROD-WEB",
    "systems": ["cms", "tokens", "design", "dam", "checklist", "cdn", "vendors", "approvals", "messages", "chat", "drive", "notes"],
}
PEOPLE = (
    {"person_id": "PER-OSEI", "name": "Kwame Osei", "role": "growth_product_manager", "focus": "Pricing and plans"},
    {"person_id": "PER-LINDQVIST", "name": "Sara Lindqvist", "role": "brand_designer", "focus": "Orchid design system"},
    {"person_id": "PER-MORAES", "name": "Beatriz Moraes", "role": "localisation_lead", "focus": "Locale launches"},
    {"person_id": "PER-CHAUDHRY", "name": "Zain Chaudhry", "role": "front_end_lead", "focus": "Web platform"},
    {"person_id": "PER-HAVILAND", "name": "Nora Haviland", "role": "content_strategist", "focus": "Site content and legal copy"},
)
USERS = (
    {"user_id": "U-WEBOPS", "display_name": "Web Release Coordinator (you)", "role": "web_release_coordinator", "approval_limit_usd": 0},
    {"user_id": "U-AURBAKKEN", "display_name": "Helene Aurbakken", "role": "web_release_manager", "approval_limit_usd": 20000},
    {"user_id": "U-OKAFOR", "display_name": "Chidi Okafor", "role": "head_of_digital", "approval_limit_usd": 120000},
    {"user_id": "U-RAGHUNATHAN", "display_name": "Priya Raghunathan", "role": "design_system_owner", "approval_limit_usd": 15000},
    {"user_id": "U-WIERZBICKI", "display_name": "Tomasz Wierzbicki", "role": "brand_legal_counsel", "approval_limit_usd": 0},
    {"user_id": "U-DELGADO", "display_name": "Rosa Delgado", "role": "accessibility_lead", "approval_limit_usd": 0},
    {"user_id": "U-BELLO", "display_name": "Idris Bello", "role": "marketing_director", "approval_limit_usd": 0},
)
VENDORS = (
    {"vendor_id": "VND-STILLFRAME", "name": "Stillframe Stock Imagery", "account_number": "LK-2210"},
    {"vendor_id": "VND-GLYPHWORKS", "name": "Glyphworks Type Foundry", "account_number": "LK-0874"},
    {"vendor_id": "VND-ORCHIDWORKS", "name": "Orchidworks Design Agency", "account_number": "LK-1153"},
    {"vendor_id": "VND-MERIDIANEDGE", "name": "Meridian Edge Network", "account_number": "LK-3391"},
)
WINDOW_TIMES = {"AM": ("09:00:00", "13:00:00"), "PM": ("13:30:00", "17:30:00")}
WINDOW_HOURS = 4
LANE_ORDER = ("LANE-WEB-1", "LANE-WEB-2", "LANE-EDGE-3")


def business_days(start: str = AS_OF, weeks: int = 3) -> list[str]:
    first = date.fromisoformat(start)
    days = []
    for offset in range(weeks * 7):
        day = first + timedelta(days=offset)
        if day.weekday() < 5:
            days.append(day.isoformat())
    return days


def next_business_day(after: str) -> str:
    """First business day strictly after ``after`` (a vendor-issued licence or attestation is registered and usable the next business day)."""

    day = date.fromisoformat(after) + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.isoformat()


def renewal_horizon(as_of: str = AS_OF) -> str:
    return (date.fromisoformat(as_of) + timedelta(days=RENEWAL_HORIZON_DAYS)).isoformat()


def window_id(lane: str, day: str, session: str) -> str:
    return f"DW-{lane.rsplit('-', 1)[1]}-{day.replace('-', '')}-{session}"


def window_interval(day: str, session: str) -> tuple[str, str]:
    start, end = WINDOW_TIMES[session]
    return f"{day}T{start}", f"{day}T{end}"


@dataclass(frozen=True)
class Page:
    page_id: str
    slug: str
    title: str
    owner_team: str
    owner_person_id: str
    markets: tuple[str, ...]
    status: str = "published"


@dataclass(frozen=True)
class ChangeRequest:
    cr_id: str
    page_id: str
    title: str
    kind: str  # "content" | "design" | "token" | "full"
    territories: tuple[str, ...]
    entries_in_scope: int
    scope_note: str
    deploy_minutes: int
    verify_minutes: int
    requested_by: str
    opened_at: str
    note: str = ""
    status: str = "open"
    priority: str = "routine"
    duplicate_of: str | None = None
    impact_consumers: int | None = None


@dataclass(frozen=True)
class Entry:
    entry_id: str
    page_id: str
    cr_id: str | None
    content_type: str
    title: str
    status: str = "REVIEWED"
    revision: int = 3
    bound_token_id: str | None = None
    bound_component_id: str | None = None
    bound_asset_id: str | None = None
    blocked_reason: str | None = None


@dataclass(frozen=True)
class TokenSet:
    set_id: str
    name: str
    current_version: str


@dataclass(frozen=True)
class TokenVersion:
    version: str
    value: str
    status: str  # CURRENT | PROPOSED | DEPRECATED
    breaking: bool
    released_on: str
    note: str = ""


@dataclass(frozen=True)
class Token:
    token_id: str
    set_id: str
    name: str
    kind: str
    versions: tuple[TokenVersion, ...]

    @property
    def current(self) -> TokenVersion:
        return next(item for item in self.versions if item.status == "CURRENT")

    @property
    def proposed(self) -> TokenVersion | None:
        return next((item for item in self.versions if item.status == "PROPOSED"), None)


@dataclass(frozen=True)
class Component:
    component_id: str
    name: str
    library: str
    version: str
    allowed_variants: tuple[str, ...]
    status: str = "STABLE"
    deprecated: bool = False
    breaking_change_pending: bool = False
    note: str = ""


@dataclass(frozen=True)
class Consumer:
    consumer_id: str
    page_id: str
    surface: str
    status: str = "ACTIVE"  # ACTIVE | DEPRECATED | MIGRATED
    token_id: str | None = None
    component_id: str | None = None
    note: str = ""


@dataclass(frozen=True)
class DesignFile:
    file_id: str
    name: str
    page_id: str
    version: str
    status: str = "CURRENT"  # CURRENT | SUPERSEDED
    superseded_by: str | None = None
    review_status: str = "APPROVED"


@dataclass(frozen=True)
class Frame:
    frame_id: str
    file_id: str
    name: str
    status: str  # APPROVED | IN_REVIEW | SUPERSEDED
    components: tuple[str, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class Asset:
    asset_id: str
    kind: str  # image | font | icon | video
    name: str
    vendor_id: str
    page_id: str
    usage_count: int
    licence_required: bool = True
    status: str = "active"


@dataclass(frozen=True)
class Licence:
    licence_id: str
    asset_id: str
    vendor_id: str
    reference: str
    territories: tuple[str, ...]
    expires_on: str
    usage_scope: str = "web"
    status: str = "ACTIVE"  # ACTIVE | PENDING_COUNTERSIGN | SUSPENDED | EXPIRED | REVOKED
    reason: str | None = None
    reserved_for: str | None = None
    register_excluded: bool = False
    register_note: str = ""

    @property
    def territory_count(self) -> int:
        return len(self.territories)


@dataclass(frozen=True)
class Quote:
    quote_id: str
    vendor_id: str
    asset_id: str
    reference: str
    kind: str  # licence | agency_delivery | lane_recertification
    units_available: int
    standard_date: str
    expedited_date: str
    rush_fee: int
    per_unit_fee: float
    valid_until: str
    status: str = "OPEN"
    note: str = ""


@dataclass(frozen=True)
class Gate:
    gate_id: str
    cr_id: str
    name: str
    category: str  # qa | accessibility | legal | performance
    status: str  # PASSED | FAILED | PENDING | WAIVED | SUPERSEDED
    authority_role: str
    measured: str = ""
    budget: str = ""
    note: str = ""


@dataclass(frozen=True)
class Budget:
    budget_id: str
    page_id: str
    metric: str
    budget_value: float
    measured_value: float
    unit: str
    measured_at: str
    status: str = "WITHIN_BUDGET"


@dataclass(frozen=True)
class Lane:
    lane_id: str
    name: str
    status: str = "ACTIVE"
    rollback_capable: bool = True
    note: str | None = None


@dataclass(frozen=True)
class Window:
    day: str
    lane: str
    session: str
    status: str
    reason: str = ""


@dataclass(frozen=True)
class Release:
    release_id: str
    page_id: str
    cr_id: str | None
    lane_id: str | None
    start: str | None
    end: str | None
    status: str
    description: str
    entry_count: int | None = None


@dataclass(frozen=True)
class Pin:
    pin_id: str
    token_id: str
    version: str
    cr_id: str
    consumer_count: int
    status: str = "PINNED"
    created_at: str = "2026-05-08T16:10:00"


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
    labels: str = "web-studio"


@dataclass(frozen=True)
class Chat:
    thread_id: str
    title: str
    messages: tuple[tuple[str, str, str], ...]
    channel: str = "#web-releases"


@dataclass(frozen=True)
class Doc:
    path: str
    kind: str
    title: str
    content: str = ""
    media_type: str = MARKDOWN
    rows: tuple[tuple[Any, ...], ...] | None = None
    folder: str = "Web Studio"
    scoped: bool = False


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
    page: Page
    other_pages: tuple[Page, ...]
    change_requests: tuple[ChangeRequest, ...]
    entries: tuple[Entry, ...]
    token_sets: tuple[TokenSet, ...]
    tokens: tuple[Token, ...]
    components: tuple[Component, ...]
    consumers: tuple[Consumer, ...]
    design_files: tuple[DesignFile, ...]
    frames: tuple[Frame, ...]
    assets: tuple[Asset, ...]
    licences: tuple[Licence, ...]
    quote: Quote
    other_quotes: tuple[Quote, ...]
    gates: tuple[Gate, ...]
    budgets: tuple[Budget, ...]
    lanes: tuple[Lane, ...]
    windows: tuple[Window, ...]
    releases: tuple[Release, ...]
    pins: tuple[Pin, ...]
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
    revision: str = "v1"
    seed: dict[str, Any] = field(default_factory=dict)

    @property
    def task_id(self) -> str:
        return f"webstudio-{self.ordinal:03d}"

    @property
    def case_reference(self) -> str:
        return f"WEB-{self.ordinal:04d}"

    @property
    def primary_cr(self) -> ChangeRequest:
        return self.change_requests[0]

    @property
    def primary_asset(self) -> Asset:
        return self.assets[0]

    @property
    def primary_token(self) -> Token:
        return self.tokens[0]

    @property
    def current_design_file(self) -> DesignFile:
        return next(item for item in self.design_files if item.status == "CURRENT")

    @property
    def approved_frame(self) -> Frame:
        current = self.current_design_file.file_id
        return next(item for item in self.frames if item.file_id == current and item.status == "APPROVED")


__all__ = [
    "AS_OF",
    "Approval",
    "Asset",
    "Budget",
    "ChangeRequest",
    "Chat",
    "Component",
    "Consumer",
    "DesignFile",
    "Doc",
    "Email",
    "Entry",
    "Frame",
    "Gate",
    "LANE_ORDER",
    "Labels",
    "Lane",
    "Licence",
    "ORGANIZATION",
    "Option",
    "PEOPLE",
    "Page",
    "Pin",
    "PrimaryWrite",
    "Quote",
    "RENEWAL_HORIZON_DAYS",
    "Release",
    "Scenario",
    "Token",
    "TokenSet",
    "TokenVersion",
    "USERS",
    "VENDORS",
    "WINDOW_HOURS",
    "WINDOW_TIMES",
    "Window",
    "business_days",
    "next_business_day",
    "renewal_horizon",
    "window_id",
    "window_interval",
]
