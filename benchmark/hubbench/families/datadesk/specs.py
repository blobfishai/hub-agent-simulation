"""Scenario data model and shared synthetic entities for the DataDesk family.

Everything here is clean-room synthetic: Tidewater Supply Co. is not a real
organisation and no vendor, employee, model, or number corresponds to a real
one.  Shapes are dbt/warehouse-style only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from ...engine.assets import MARKDOWN
from ...engine.decision import Labels, Option

AS_OF = "2026-03-09"
ORGANIZATION = {
    "id": "tidewater-dataplatform-v1",
    "name": "Tidewater Supply Co. — Data Platform",
    "organization_id": "ORG-TIDEWATER",
    "primary_site": "WH-PROD",
    "systems": ["warehouse", "pipelines", "feeds", "recon", "approvals", "messages", "chat", "drive", "notes"],
}
USERS = (
    {"user_id": "U-ONCALL", "display_name": "Analytics Engineer on call (you)", "role": "analytics_engineer_oncall", "approval_limit_usd": 0},
    {"user_id": "U-VOSS", "display_name": "Ingrid Voss", "role": "data_platform_lead", "approval_limit_usd": 40000},
    {"user_id": "U-OYELARAN", "display_name": "Femi Oyelaran", "role": "head_of_data", "approval_limit_usd": 150000},
    {"user_id": "U-MARSH", "display_name": "Corin Marsh", "role": "finance_controller", "approval_limit_usd": 25000},
    {"user_id": "U-TANAKA", "display_name": "Rei Tanaka", "role": "warehouse_operations_manager", "approval_limit_usd": 10000},
)
VENDORS = (
    {"vendor_id": "VEND-SKYF", "name": "Skyfield Commerce Cloud", "account_number": "TW-3310"},
    {"vendor_id": "VEND-BLUE", "name": "Bluecrest Payment Systems", "account_number": "TW-1188"},
    {"vendor_id": "VEND-CORM", "name": "Cormorant Adtech", "account_number": "TW-0921"},
    {"vendor_id": "VEND-HARR", "name": "Harrier Logistics Data", "account_number": "TW-2205"},
)
WINDOW_TIMES = {"NIGHT": ("01:00:00", "05:00:00"), "DAY": ("13:00:00", "17:00:00")}
WINDOW_ORDER = ("NIGHT", "DAY")
WINDOW_HOURS = 4


def batch_days(start: str = AS_OF, weeks: int = 3) -> list[str]:
    """Weekday batch calendar, three weeks from the planning date."""

    first = date.fromisoformat(start)
    days = []
    for offset in range(weeks * 7):
        day = first + timedelta(days=offset)
        if day.weekday() < 5:
            days.append(day.isoformat())
    return days


def weekdays_between(start: str, end: str) -> list[str]:
    day = date.fromisoformat(start)
    last = date.fromisoformat(end)
    days = []
    while day <= last:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day += timedelta(days=1)
    return days


def next_batch_day(after: str) -> str:
    """First batch day strictly after ``after`` (redelivered files validate overnight)."""

    day = date.fromisoformat(after) + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.isoformat()


def slot_id(cluster: str, day: str, window: str) -> str:
    return f"SLOT-{cluster.split('-')[1]}-{day.replace('-', '')}-{window}"


def window_interval(day: str, window: str) -> tuple[str, str]:
    start, end = WINDOW_TIMES[window]
    return f"{day}T{start}", f"{day}T{end}"


@dataclass(frozen=True)
class Model:
    model_id: str
    name: str
    layer: str
    schema_name: str
    materialization: str
    owner: str
    status: str = "ACTIVE"
    description: str = ""


@dataclass(frozen=True)
class Edge:
    parent: str
    child: str
    relationship: str = "ref"


@dataclass(frozen=True)
class Sla:
    sla_id: str
    model_id: str
    max_staleness_hours: int
    refresh_deadline: str
    breach_escalation: str
    business_reference: str
    effective_from: str = "2026-01-12"
    status: str = "ACTIVE"


@dataclass(frozen=True)
class Run:
    run_id: str
    model_id: str
    partition_date: str
    started_at: str
    duration_minutes: int
    status: str
    rows_processed: int
    trigger: str = "scheduled"
    source_version: str | None = None
    note: str = ""


@dataclass(frozen=True)
class ScheduleRec:
    schedule_id: str
    model_id: str
    description: str
    duration_minutes: int
    cluster_id: str | None
    start: str | None
    end: str | None
    status: str
    displaced: bool = False


@dataclass(frozen=True)
class Job:
    job_id: str
    model_id: str
    partition_start: str
    partition_end: str
    partitions: int
    cluster_id: str | None
    start: str | None
    end: str | None
    status: str
    description: str = ""


@dataclass(frozen=True)
class Cluster:
    cluster_id: str
    name: str
    status: str = "ACTIVE"
    backfill_capable: bool = True
    note: str | None = None


@dataclass(frozen=True)
class Window:
    day: str
    cluster: str
    window: str
    status: str
    reason: str = ""


@dataclass(frozen=True)
class Feed:
    feed_id: str
    vendor_id: str
    name: str
    dataset: str
    cadence: str = "daily"
    status: str = "ACTIVE"


@dataclass(frozen=True)
class Delivery:
    delivery_id: str
    feed_id: str
    business_date: str
    files_expected: int
    files_received: int
    rows_received: int
    rows_invalid: int = 0
    rows_duplicate: int = 0
    rows_late: int = 0
    late_duplicate: int = 0  # narrative subset of rows_late, cross-checked at build
    status: str = "LOADED"
    received_at: str = ""
    note: str = ""


@dataclass(frozen=True)
class Control:
    control_id: str
    model_id: str
    metric: str
    period_start: str
    period_end: str
    control_total_rows: int
    source: str
    published_at: str
    status: str = "PUBLISHED"
    note: str = ""


@dataclass(frozen=True)
class Confirmation:
    confirmation_id: str
    vendor_id: str
    feed_id: str
    reference: str
    scope_note: str
    standard_date: str
    expedited_date: str
    fee: int
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
    labels: str = "data-platform"


@dataclass(frozen=True)
class Chat:
    thread_id: str
    title: str
    messages: tuple[tuple[str, str, str], ...]
    channel: str = "#data-platform"


@dataclass(frozen=True)
class Doc:
    path: str
    kind: str
    title: str
    content: str = ""
    media_type: str = MARKDOWN
    rows: tuple[tuple[Any, ...], ...] | None = None
    folder: str = "Data Platform"


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
    model: Model
    other_models: tuple[Model, ...]
    lineage: tuple[Edge, ...]
    slas: tuple[Sla, ...]
    runs: tuple[Run, ...]
    schedules: tuple[ScheduleRec, ...]
    jobs: tuple[Job, ...]
    clusters: tuple[Cluster, ...]
    windows: tuple[Window, ...]
    feeds: tuple[Feed, ...]
    deliveries: tuple[Delivery, ...]
    controls: tuple[Control, ...]
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
    slots_query: dict[str, str]
    selected_slot_id: str
    revision: str = "v4"
    seed: dict[str, Any] = field(default_factory=dict)

    @property
    def task_id(self) -> str:
        return f"datadesk-{self.ordinal:03d}"

    @property
    def case_reference(self) -> str:
        return f"DATA-{self.ordinal:04d}"

    @property
    def primary_feed(self) -> Feed:
        return self.feeds[0]

    @property
    def primary_control(self) -> Control | None:
        return self.controls[0] if self.controls else None


__all__ = [
    "AS_OF",
    "Approval",
    "Chat",
    "Cluster",
    "Confirmation",
    "Control",
    "Delivery",
    "Doc",
    "Edge",
    "Email",
    "Feed",
    "Job",
    "Labels",
    "Model",
    "ORGANIZATION",
    "Option",
    "PrimaryWrite",
    "Run",
    "Scenario",
    "ScheduleRec",
    "Sla",
    "USERS",
    "VENDORS",
    "WINDOW_HOURS",
    "WINDOW_ORDER",
    "WINDOW_TIMES",
    "Window",
    "batch_days",
    "next_batch_day",
    "slot_id",
    "weekdays_between",
    "window_interval",
]
