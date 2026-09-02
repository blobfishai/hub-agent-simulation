"""Scenario data model and shared synthetic entities for the HostOps family.

Everything here is clean-room synthetic: Ridgeline Systems is not a real
organisation and no engineer, vendor, host, or service corresponds to a real
one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from ...engine.assets import MARKDOWN
from ...engine.decision import Labels, Option

AS_OF = "2026-04-13"
ORGANIZATION = {
    "id": "ridgeline-platform-v1",
    "name": "Ridgeline Systems — Platform Operations",
    "organization_id": "ORG-RIDGELINE",
    "primary_site": "STORE-NEAR",
    "systems": ["cmdb", "releases", "jobs", "backup", "buildfarm", "vendor", "approvals", "messages", "chat", "drive", "notes"],
}
STORES = (
    {"store_id": "STORE-NEAR", "name": "Nearline artifact store (primary DC)", "type": "nearline_store"},
    {"store_id": "STORE-DR", "name": "Drayton DR object store", "type": "dr_store"},
    {"store_id": "STORE-STAGE", "name": "Release staging store", "type": "staging_store"},
)
ENGINEERS = (
    {"engineer_id": "ENG-TIDEMAND", "name": "Freya Tidemand", "role": "release_owner", "focus": "Atlas platform"},
    {"engineer_id": "ENG-BHATT", "name": "Deepak Bhatt", "role": "service_owner", "focus": "Payments"},
    {"engineer_id": "ENG-CALLOWAY", "name": "June Calloway", "role": "data_engineering_lead", "focus": "Analytics pipelines"},
    {"engineer_id": "ENG-ROSSI", "name": "Matteo Rossi", "role": "security_engineer", "focus": "Compliance and audit"},
    {"engineer_id": "ENG-OKONJO", "name": "Amara Okonjo", "role": "sre_oncall", "focus": "Platform reliability"},
)
USERS = (
    {"user_id": "U-OPS", "display_name": "Platform Operations Coordinator (you)", "role": "platform_operations_coordinator", "approval_limit_usd": 0},
    {"user_id": "U-VANCE", "display_name": "Imogen Vance", "role": "release_engineering_manager", "approval_limit_usd": 20000},
    {"user_id": "U-OYELARAN", "display_name": "Bisi Oyelaran", "role": "infrastructure_director", "approval_limit_usd": 120000},
    {"user_id": "U-STROM", "display_name": "Annika Strøm", "role": "sre_lead", "approval_limit_usd": 15000},
    {"user_id": "U-KESSLER", "display_name": "Marta Kessler", "role": "change_board_chair", "approval_limit_usd": 0},
)
VENDORS = (
    {"vendor_id": "VND-COLDSPUR", "name": "Coldspur Archival Vaults", "account_number": "RS-1104"},
    {"vendor_id": "VND-IRONHOLD", "name": "Ironhold Data Custody", "account_number": "RS-0339"},
)
WINDOW_TIMES = {"AM": ("08:00:00", "12:00:00"), "PM": ("12:30:00", "16:30:00")}
WINDOW_HOURS = 4


def business_days(start: str = AS_OF, weeks: int = 3) -> list[str]:
    first = date.fromisoformat(start)
    days = []
    for offset in range(weeks * 7):
        day = first + timedelta(days=offset)
        if day.weekday() < 5:
            days.append(day.isoformat())
    return days


def next_business_day(after: str) -> str:
    """First business day strictly after ``after`` (retrieved data clears checksum verification the next business day)."""

    day = date.fromisoformat(after) + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.isoformat()


def window_id(runner: str, day: str, session: str) -> str:
    return f"WIN-{runner.split('-')[1]}-{day.replace('-', '')}-{session}"


def window_interval(day: str, session: str) -> tuple[str, str]:
    start, end = WINDOW_TIMES[session]
    return f"{day}T{start}", f"{day}T{end}"


@dataclass(frozen=True)
class Service:
    service_id: str
    code: str
    name: str
    tier: str
    owner_team: str
    engineer_id: str
    meter_metric: str
    meter_value: float
    meter_date: str
    stale_value: float = 0.0
    stale_date: str = "2026-01-16"

    @property
    def metering_id(self) -> str:
        return f"MTR-{self.service_id.split('-')[1]}"

    @property
    def stale_metering_id(self) -> str:
        return f"MTR-{self.service_id.split('-')[1]}-2601"


@dataclass(frozen=True)
class ArtifactClass:
    code: str
    display: str
    segment_gb: float
    storage_tier: str = "release-signed archive"
    min_retention_days: int = 14
    signed: bool = True
    interchangeable_with: str | None = None


@dataclass(frozen=True)
class Ticket:
    ticket_id: str
    service_id: str
    artifact_class: str
    unit_kind: str  # "bundle" | "day"
    unit_basis: str  # "fixed" | "metered"
    unit_gb: float | None
    units_in_scope: int
    scope_note: str
    build_minutes: int
    verify_minutes: int
    requested_by: str
    opened_at: str
    note: str = ""
    status: str = "open"
    priority: str = "routine"
    kind: str = "recovery"


@dataclass(frozen=True)
class SegmentSet:
    set_id: str
    set_label: str
    artifact_class: str
    store_id: str
    segments: int
    retention_expiry: str
    status: str = "VERIFIED"
    reason: str | None = None
    reserved_for: str | None = None
    register_excluded: bool = False
    register_note: str = ""


@dataclass(frozen=True)
class Job:
    job_id: str
    name: str
    service_id: str | None
    kind: str
    schedule: str
    status: str = "enabled"


@dataclass(frozen=True)
class JobRun:
    run_id: str
    job_id: str
    started_at: str
    finished_at: str
    status: str
    exit_code: int
    summary: str


@dataclass(frozen=True)
class Window:
    day: str
    runner: str
    session: str
    status: str
    reason: str = ""


@dataclass(frozen=True)
class Runner:
    runner_id: str
    name: str
    status: str = "ACTIVE"
    isolation_capable: bool = True
    note: str | None = None


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    service_id: str
    ticket_id: str | None
    runner_id: str | None
    start: str | None
    end: str | None
    status: str
    description: str


@dataclass(frozen=True)
class Confirmation:
    confirmation_id: str
    vendor_id: str
    artifact_class: str
    reference: str
    segments_available: int
    standard_date: str
    expedited_date: str
    fee: int
    per_segment_fee: float
    valid_until: str
    status: str = "OPEN"
    note: str = ""


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
    labels: str = "platform-ops"


@dataclass(frozen=True)
class Chat:
    thread_id: str
    title: str
    messages: tuple[tuple[str, str, str], ...]
    channel: str = "#platform-ops"


@dataclass(frozen=True)
class Doc:
    path: str
    kind: str
    title: str
    content: str = ""
    media_type: str = MARKDOWN
    rows: tuple[tuple[Any, ...], ...] | None = None
    folder: str = "Platform Operations"


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
    service: Service
    other_services: tuple[Service, ...]
    classes: tuple[ArtifactClass, ...]
    tickets: tuple[Ticket, ...]
    sets: tuple[SegmentSet, ...]
    jobs: tuple[Job, ...]
    job_runs: tuple[JobRun, ...]
    windows: tuple[Window, ...]
    runners: tuple[Runner, ...]
    reservations: tuple[Reservation, ...]
    confirmation: Confirmation
    other_confirmations: tuple[Confirmation, ...]
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
    run_query: dict[str, Any]
    run_expected: dict[str, Any]
    revision: str = "v1"
    seed: dict[str, Any] = field(default_factory=dict)

    @property
    def task_id(self) -> str:
        return f"hostops-{self.ordinal:03d}"

    @property
    def case_reference(self) -> str:
        return f"HOST-{self.ordinal:04d}"

    @property
    def primary_ticket(self) -> Ticket:
        return self.tickets[0]

    @property
    def primary_class(self) -> ArtifactClass:
        return next(item for item in self.classes if item.code == self.primary_ticket.artifact_class)


def segments_for_payload(payload_gb: float, segment_gb: float) -> int:
    whole, remainder = divmod(payload_gb, segment_gb)
    return int(whole) + (1 if remainder > 1e-9 else 0)


def ticket_unit_gb(ticket: Ticket, service_by_id: dict[str, Service]) -> float:
    if ticket.unit_basis == "fixed":
        if ticket.unit_gb is None:
            raise ValueError(f"{ticket.ticket_id}: fixed tickets need unit_gb")
        return ticket.unit_gb
    return service_by_id[ticket.service_id].meter_value


__all__ = [
    "AS_OF",
    "Approval",
    "ArtifactClass",
    "Chat",
    "Confirmation",
    "Doc",
    "ENGINEERS",
    "Email",
    "Job",
    "JobRun",
    "Labels",
    "ORGANIZATION",
    "Option",
    "PrimaryWrite",
    "Reservation",
    "Runner",
    "STORES",
    "Scenario",
    "SegmentSet",
    "Service",
    "Ticket",
    "USERS",
    "VENDORS",
    "WINDOW_HOURS",
    "WINDOW_TIMES",
    "Window",
    "business_days",
    "next_business_day",
    "segments_for_payload",
    "ticket_unit_gb",
    "window_id",
    "window_interval",
]
