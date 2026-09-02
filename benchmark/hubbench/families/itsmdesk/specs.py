"""Scenario data model and shared synthetic entities for the ITSMDesk family.

Everything here is clean-room synthetic: Brightmoor Commerce is not a real
organisation and no engineer, vendor, service, advisory, or incident
corresponds to a real one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from ...engine.assets import MARKDOWN
from ...engine.decision import Labels, Option

AS_OF = "2026-04-14"
CALENDAR_DAYS = 21
ORGANIZATION = {
    "id": "brightmoor-serviceops-v1",
    "name": "Brightmoor Commerce — Service Operations",
    "organization_id": "ORG-BRIGHTMOOR",
    "primary_site": "DC-HALDEN",
    "systems": ["itsm", "telemetry", "calendar", "oncall", "vendor", "approvals", "messages", "chat", "drive", "notes"],
}
ENGINEERS = (
    {"engineer_id": "ENG-VARGA", "name": "Lena Varga", "role": "service_owner", "team": "Payments Platform", "certifications": "payments-runbook,change-implementer"},
    {"engineer_id": "ENG-OKAFOR", "name": "Chidi Okafor", "role": "sre_secondary", "team": "Platform SRE", "certifications": "payments-runbook,identity-runbook,checkout-runbook,web-runbook,change-implementer"},
    {"engineer_id": "ENG-DUBOIS", "name": "Mathis Dubois", "role": "sre_primary", "team": "Platform SRE", "certifications": "identity-runbook,checkout-runbook,change-implementer"},
    {"engineer_id": "ENG-SATO", "name": "Rin Sato", "role": "service_owner", "team": "Checkout", "certifications": "checkout-runbook,change-implementer"},
    {"engineer_id": "ENG-NKEMELU", "name": "Adaeze Nkemelu", "role": "data_platform_lead", "team": "Data Platform", "certifications": "data-runbook,messaging-runbook,change-implementer"},
    {"engineer_id": "ENG-HOLM", "name": "Dario Holm", "role": "sre_secondary", "team": "Platform SRE", "certifications": "change-implementer"},
    {"engineer_id": "ENG-RAMAN", "name": "Priya Raman", "role": "sre_secondary", "team": "Platform SRE", "certifications": "search-runbook,payments-runbook,fraud-runbook,data-runbook,messaging-runbook,change-implementer"},
    {"engineer_id": "ENG-FERREIRA", "name": "Bruno Ferreira", "role": "risk_engineer", "team": "Risk Platform", "certifications": "fraud-runbook,change-implementer"},
    {"engineer_id": "ENG-KOWALSKI", "name": "Zofia Kowalski", "role": "web_owner", "team": "Merchant Web", "certifications": "web-runbook,change-implementer"},
    {"engineer_id": "ENG-TANAKA", "name": "Yuki Tanaka", "role": "search_owner", "team": "Search Platform", "certifications": "search-runbook,change-implementer"},
)
USERS = (
    {"user_id": "U-OPS", "display_name": "Service Operations Coordinator (you)", "role": "service_operations_coordinator", "approval_limit_usd": 0},
    {"user_id": "U-LINDGREN", "display_name": "Saoirse Lindgren", "role": "change_manager", "approval_limit_usd": 5000},
    {"user_id": "U-ABARA", "display_name": "Tunde Abara", "role": "change_board_chair", "approval_limit_usd": 0},
    {"user_id": "U-HAVILAND", "display_name": "Wren Haviland", "role": "sre_lead", "approval_limit_usd": 8000},
    {"user_id": "U-MORAES", "display_name": "Inês Moraes", "role": "security_lead", "approval_limit_usd": 12000},
)
VENDORS = (
    {"vendor_id": "VND-QUILLSTONE", "name": "Quillstone Runtime Systems", "account_number": "BM-2207"},
    {"vendor_id": "VND-ORRINWAVE", "name": "Orrinwave Data Systems", "account_number": "BM-0931"},
    {"vendor_id": "VND-SABLEGATE", "name": "Sablegate Edge Security", "account_number": "BM-1148"},
)
SESSIONS = ("NIGHT", "EVE")
SESSION_TIMES = {"NIGHT": ("01:00:00", "05:00:00"), "EVE": ("19:00:00", "23:00:00")}
WINDOW_HOURS = 4
WINDOW_MINUTES = WINDOW_HOURS * 60
SHIFT_BLOCKS = (("00:00:00", "08:00:00"), ("08:00:00", "16:00:00"), ("16:00:00", "23:59:59"))
RESTART_METRIC = "RESTART-MIN"
DRAIN_METRIC = "DRAIN-MIN"


def calendar_days(start: str = AS_OF, days: int = CALENDAR_DAYS) -> list[str]:
    first = date.fromisoformat(start)
    return [(first + timedelta(days=offset)).isoformat() for offset in range(days)]


def next_business_day(after: str) -> str:
    """First business day strictly after ``after`` (a vendor package clears the canary soak the next business day)."""

    day = date.fromisoformat(after) + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.isoformat()


def is_weekend(day: str) -> bool:
    return date.fromisoformat(day).weekday() >= 5


def window_id(lane: str, day: str, session: str) -> str:
    return f"MW-{lane.split('-', 1)[1]}-{day.replace('-', '')}-{session}"


def window_interval(day: str, session: str) -> tuple[str, str]:
    start, end = SESSION_TIMES[session]
    return f"{day}T{start}", f"{day}T{end}"


def minutes_between(start: str, end: str) -> int:
    """Whole minutes between two same-day ``YYYY-MM-DDTHH:MM:SS`` timestamps."""

    if start[:10] != end[:10]:
        raise ValueError("start and end must fall on the same date")
    sh, sm = int(start[11:13]), int(start[14:16])
    eh, em = int(end[11:13]), int(end[14:16])
    return (eh * 60 + em) - (sh * 60 + sm)


def add_minutes(start: str, minutes: int) -> str:
    total = int(start[11:13]) * 60 + int(start[14:16]) + minutes
    return f"{start[:10]}T{total // 60:02d}:{total % 60:02d}:00"


@dataclass(frozen=True)
class Lane:
    lane_id: str
    name: str
    weekday_policy: str  # "embargo" | "open"
    tier1_capable: bool = True
    status: str = "ACTIVE"
    note: str | None = None


@dataclass(frozen=True)
class Service:
    service_id: str
    code: str
    name: str
    tier: str
    owner_team: str
    engineer_id: str
    lane_id: str
    runtime: str
    version: str
    required_certification: str
    validation_minutes: int
    rollback_minutes: int
    meter_metric: str
    meter_value: float
    meter_date: str
    stale_value: float = 0.0
    stale_date: str = "2026-01-20"

    @property
    def metering_id(self) -> str:
        return f"MTR-{self.service_id.split('-')[1]}"

    @property
    def stale_metering_id(self) -> str:
        return f"MTR-{self.service_id.split('-')[1]}-2601"


@dataclass(frozen=True)
class Node:
    node_id: str
    service_id: str
    pool: str
    region: str
    lane_id: str
    version: str
    status: str = "active"
    staged_build: str | None = None
    build_status: str | None = None
    pinned_for: str | None = None


@dataclass(frozen=True)
class Slo:
    slo_id: str
    service_id: str
    name: str
    sli: str
    objective_pct: float
    window_days: int
    budget_minutes: int
    reserve_minutes: int
    status: str = "ACTIVE"


@dataclass(frozen=True)
class Problem:
    problem_id: str
    service_id: str
    title: str
    status: str
    review_note: str


@dataclass(frozen=True)
class Incident:
    incident_id: str
    service_id: str
    opened_at: str
    resolved_at: str
    severity: str
    impact_minutes: int
    slo_charged: bool
    summary: str
    problem_id: str | None = None


@dataclass(frozen=True)
class Advisory:
    advisory_id: str
    vendor_id: str
    reference: str
    product: str
    severity: str
    published_on: str
    sla_days: int
    affected_versions: str
    fixed_version: str
    restarts_required: int
    vendor_estimate_minutes: int
    standard_date: str
    expedited_date: str
    fee: int
    valid_until: str
    status: str = "CURRENT"
    note: str = ""


@dataclass(frozen=True)
class Freeze:
    freeze_id: str
    name: str
    kind: str
    start_date: str
    end_date: str
    lanes: tuple[str, ...] | str  # lane ids or "ALL"
    authority: str
    status: str = "ACTIVE"


@dataclass(frozen=True)
class Change:
    change_id: str
    service_id: str
    advisory_id: str | None
    change_type: str
    state: str
    lane_id: str | None
    day: str | None
    session: str | None
    planned_start: str | None
    planned_end: str | None
    downtime_minutes: int
    restarts: int
    risk: str
    requested_by: str
    summary: str
    opened_at: str


@dataclass(frozen=True)
class Window:
    day: str
    lane: str
    session: str
    status: str
    reason: str = ""


@dataclass(frozen=True)
class Schedule:
    schedule_id: str
    service_id: str
    name: str
    role: str  # "primary" | "secondary"
    required_certification: str | None
    default_engineer: str
    overrides: dict[tuple[str, int], str] = field(default_factory=dict)  # (day, block index) -> engineer
    blocks: tuple[tuple[str, str], ...] = SHIFT_BLOCKS


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
    labels: str = "service-ops"


@dataclass(frozen=True)
class Chat:
    thread_id: str
    title: str
    messages: tuple[tuple[str, str, str], ...]
    channel: str = "#service-ops"


@dataclass(frozen=True)
class Doc:
    path: str
    kind: str
    title: str
    content: str = ""
    media_type: str = MARKDOWN
    rows: tuple[tuple[Any, ...], ...] | None = None
    folder: str = "Service Operations"


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
    nodes: tuple[Node, ...]
    slo: Slo
    other_slos: tuple[Slo, ...]
    problems: tuple[Problem, ...]
    incidents: tuple[Incident, ...]
    changes: tuple[Change, ...]
    advisory: Advisory
    other_advisories: tuple[Advisory, ...]
    lanes: tuple[Lane, ...]
    freezes: tuple[Freeze, ...]
    windows: tuple[Window, ...]
    schedules: tuple[Schedule, ...]
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
    incident_query: dict[str, Any]
    incident_expected: dict[str, Any]
    shift_query: dict[str, Any]
    shift_expected: dict[str, Any]
    freeze_query: dict[str, str]
    freeze_expected: dict[str, Any]
    revision: str = "v1"
    seed: dict[str, Any] = field(default_factory=dict)

    @property
    def task_id(self) -> str:
        return f"itsmdesk-{self.ordinal:03d}"

    @property
    def case_reference(self) -> str:
        return f"SVCOPS-{self.ordinal:04d}"

    @property
    def primary_change(self) -> Change:
        return self.changes[0]

    @property
    def secondary_schedule(self) -> Schedule:
        return next(item for item in self.schedules if item.service_id == self.service.service_id and item.role == "secondary")


def downtime_minutes(service: Service, restarts: int) -> int:
    """Downtime the effective policy sizes: restarts x current restart metering + runbook validation."""

    return int(round(restarts * service.meter_value)) + service.validation_minutes


def consumed_minutes(incidents: tuple[Incident, ...], service_id: str, slo: Slo, day: str) -> int:
    """Charged incident minutes inside the rolling SLO window ending on ``day`` (inclusive)."""

    window_start = (date.fromisoformat(day) - timedelta(days=slo.window_days)).isoformat()
    return sum(
        incident.impact_minutes
        for incident in incidents
        if incident.service_id == service_id and incident.slo_charged and window_start < incident.opened_at[:10] <= day
    )


def spendable_minutes(incidents: tuple[Incident, ...], service_id: str, slo: Slo, day: str) -> int:
    return slo.budget_minutes - consumed_minutes(incidents, service_id, slo, day) - slo.reserve_minutes


def certified(engineer_id: str, certification: str | None) -> bool:
    if not certification:
        return True
    record = next(row for row in ENGINEERS if row["engineer_id"] == engineer_id)
    return certification in record["certifications"].split(",")


def shifts_for(schedule: Schedule, days: list[str]) -> list[dict[str, Any]]:
    """Materialise the roster of one schedule over the calendar days."""

    rows = []
    suffix = schedule.schedule_id.split("-", 1)[1]
    for day in days:
        for index, (start, end) in enumerate(schedule.blocks):
            engineer = schedule.overrides.get((day, index), schedule.default_engineer)
            rows.append(
                {
                    "shift_id": f"SHIFT-{suffix}-{day.replace('-', '')}-{index + 1}",
                    "schedule_id": schedule.schedule_id,
                    "engineer_id": engineer,
                    "start_time": f"{day}T{start}",
                    "end_time": f"{day}T{end}",
                    "source": "rotation" if (day, index) not in schedule.overrides else "swap",
                }
            )
    return rows


__all__ = [
    "AS_OF",
    "Advisory",
    "Approval",
    "CALENDAR_DAYS",
    "Change",
    "Chat",
    "DRAIN_METRIC",
    "Doc",
    "ENGINEERS",
    "Email",
    "Freeze",
    "Incident",
    "Labels",
    "Lane",
    "Node",
    "ORGANIZATION",
    "Option",
    "PrimaryWrite",
    "Problem",
    "RESTART_METRIC",
    "SESSIONS",
    "SESSION_TIMES",
    "SHIFT_BLOCKS",
    "Scenario",
    "Schedule",
    "Service",
    "Slo",
    "USERS",
    "VENDORS",
    "WINDOW_HOURS",
    "WINDOW_MINUTES",
    "Window",
    "add_minutes",
    "calendar_days",
    "certified",
    "consumed_minutes",
    "downtime_minutes",
    "is_weekend",
    "minutes_between",
    "next_business_day",
    "shifts_for",
    "spendable_minutes",
    "window_id",
    "window_interval",
]
