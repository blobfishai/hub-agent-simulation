"""Scenario data model and shared synthetic entities for the SecOps family.

Everything here is clean-room synthetic: Kestrel Grid Utilities is not a real
organisation and no analyst, identity, host, detection rule, vendor, or
credential corresponds to a real one.  The family is defensive security
operations only — triage, containment, and revocation decisions about the
organisation's own credentials.  No exploit, attack tooling, or malware exists
anywhere in the world.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from ...engine.assets import MARKDOWN
from ...engine.decision import Labels, Option

AS_OF = "2026-06-08"
ORGANIZATION = {
    "id": "kestrel-secops-v1",
    "name": "Kestrel Grid Utilities — Security Operations Center",
    "organization_id": "ORG-KESTREL",
    "primary_site": "TENANT-PRIMARY",
    "systems": ["siem", "edr", "iam", "cloudiam", "servicedesk", "playbooks", "oncall", "idpvendor", "approvals", "messages", "chat", "drive", "notes"],
}
ANALYSTS = (
    {"analyst_id": "AN-OKAFOR", "name": "Chidi Okafor", "role": "soc_analyst_tier2", "focus": "Identity threat detection"},
    {"analyst_id": "AN-LINDQVIST", "name": "Maja Lindqvist", "role": "iam_platform_owner", "focus": "Workforce identity and SSO"},
    {"analyst_id": "AN-PRADHAN", "name": "Rohan Pradhan", "role": "cloud_platform_owner", "focus": "Cloud IAM and key custody"},
    {"analyst_id": "AN-DELACROIX", "name": "Solène Delacroix", "role": "grc_lead", "focus": "Regulatory notification and audit"},
    {"analyst_id": "AN-MBEKI", "name": "Thandiwe Mbeki", "role": "incident_commander", "focus": "Major incident coordination"},
)
USERS = (
    {"user_id": "U-SOC", "display_name": "Security Operations Coordinator (you)", "role": "security_operations_coordinator", "approval_limit_usd": 0},
    {"user_id": "U-HAVILAND", "display_name": "Imre Haviland", "role": "soc_manager", "approval_limit_usd": 20000},
    {"user_id": "U-ACHTERBERG", "display_name": "Nienke Achterberg", "role": "chief_information_security_officer", "approval_limit_usd": 120000},
    {"user_id": "U-SORIANO", "display_name": "Beatriz Soriano", "role": "on_call_lead", "approval_limit_usd": 15000},
    {"user_id": "U-KOVALENKO", "display_name": "Oksana Kovalenko", "role": "change_advisory_chair", "approval_limit_usd": 0},
)
VENDORS = (
    {"vendor_id": "VND-HALYARD", "name": "Halyard Identity Cloud (managed IdP)", "account_number": "KG-2210"},
    {"vendor_id": "VND-BRINDLE", "name": "Brindle Cloud Platform (key custody)", "account_number": "KG-0874"},
)
WINDOW_TIMES = {"AM": ("08:00:00", "12:00:00"), "PM": ("12:30:00", "16:30:00")}
WINDOW_HOURS = 4
OBJECT_UNIT = "CREDENTIAL_OBJECT"


def business_days(start: str = AS_OF, weeks: int = 3) -> list[str]:
    first = date.fromisoformat(start)
    days = []
    for offset in range(weeks * 7):
        day = first + timedelta(days=offset)
        if day.weekday() < 5:
            days.append(day.isoformat())
    return days


def next_business_day(after: str) -> str:
    """First business day strictly after ``after`` (a vendor invalidation job propagates and is verified the next business day)."""

    day = date.fromisoformat(after) + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.isoformat()


def window_id(responder: str, day: str, session: str) -> str:
    return f"OCW-{responder.split('-')[1]}-{day.replace('-', '')}-{session}"


def window_interval(day: str, session: str) -> tuple[str, str]:
    start, end = WINDOW_TIMES[session]
    return f"{day}T{start}", f"{day}T{end}"


@dataclass(frozen=True)
class Identity:
    identity_id: str
    username: str
    display_name: str
    kind: str  # "human" | "service_account"
    tier: str
    owner_team: str
    owner_id: str
    meter_metric: str
    meter_value: int
    meter_date: str
    stale_value: int = 0
    stale_date: str = "2026-03-13"

    @property
    def inventory_id(self) -> str:
        return f"INV-{self.identity_id.split('-')[1]}"

    @property
    def stale_inventory_id(self) -> str:
        return f"INV-{self.identity_id.split('-')[1]}-2603"


@dataclass(frozen=True)
class CredentialClass:
    code: str
    display: str
    object_kind: str = "app grant"
    revocation_channel: str = "tenant console plus federated invalidation"
    privileged: bool = True
    interchangeable_with: str | None = None


@dataclass(frozen=True)
class Tier:
    code: str
    name: str
    version: str
    immediate_allowed: bool
    owner_confirmation_required: bool
    authority_level: str
    sla_hours: int
    note: str = ""


@dataclass(frozen=True)
class Ticket:
    ticket_id: str
    identity_id: str
    credential_class: str
    unit_kind: str  # "principal" | "device"
    unit_basis: str  # "fixed" | "metered"
    unit_objects: int | None
    units_in_scope: int
    scope_note: str
    triage_minutes: int
    confirm_minutes: int
    requested_by: str
    opened_at: str
    note: str = ""
    status: str = "open"
    priority: str = "high"
    kind: str = "containment"
    alert_id: str = ""
    tier_code: str = "T2-CONFIRMED"


@dataclass(frozen=True)
class GrantSet:
    grant_id: str
    grant_label: str
    credential_class: str
    identity_id: str
    system: str
    objects: int
    expires_on: str
    status: str = "ACTIVE"
    reason: str | None = None
    deferred_for: str | None = None
    register_excluded: bool = False
    register_note: str = ""


@dataclass(frozen=True)
class Rule:
    rule_id: str
    name: str
    version: str
    status: str = "enabled"
    note: str = ""


@dataclass(frozen=True)
class Alert:
    alert_id: str
    rule_id: str
    identity_id: str | None
    severity: str
    status: str
    opened_at: str
    summary: str
    kind: str = "credential_compromise"


@dataclass(frozen=True)
class AlertEvent:
    event_id: str
    alert_id: str
    ts: str
    kind: str
    source_ip: str
    detail: str


@dataclass(frozen=True)
class Host:
    host_id: str
    hostname: str
    identity_id: str | None
    role: str
    isolation_state: str = "normal"
    status: str = "in_service"
    note: str | None = None


@dataclass(frozen=True)
class Detection:
    detection_id: str
    host_id: str
    tactic: str
    severity: str
    status: str
    note: str = ""


@dataclass(frozen=True)
class Session:
    session_id: str
    identity_id: str
    source_ip: str
    geo: str
    device: str
    started_at: str
    risk: str
    status: str = "ACTIVE"


@dataclass(frozen=True)
class Factor:
    factor_id: str
    identity_id: str
    factor_type: str
    status: str
    enrolled_at: str
    last_used: str


@dataclass(frozen=True)
class Window:
    day: str
    responder: str
    session: str
    status: str
    reason: str = ""


@dataclass(frozen=True)
class Responder:
    responder_id: str
    name: str
    status: str = "ACTIVE"
    tier2_capable: bool = True
    note: str | None = None


@dataclass(frozen=True)
class Bridge:
    bridge_id: str
    identity_id: str
    ticket_id: str | None
    responder_id: str | None
    start: str | None
    end: str | None
    status: str
    description: str


@dataclass(frozen=True)
class Confirmation:
    confirmation_id: str
    vendor_id: str
    credential_class: str
    reference: str
    objects_available: int
    standard_date: str
    expedited_date: str
    fee: int
    per_object_fee: float
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
    labels: str = "secops"


@dataclass(frozen=True)
class Chat:
    thread_id: str
    title: str
    messages: tuple[tuple[str, str, str], ...]
    channel: str = "#soc-incidents"


@dataclass(frozen=True)
class Doc:
    path: str
    kind: str
    title: str
    content: str = ""
    media_type: str = MARKDOWN
    rows: tuple[tuple[Any, ...], ...] | None = None
    folder: str = "Security Operations"


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
    identity: Identity
    other_identities: tuple[Identity, ...]
    classes: tuple[CredentialClass, ...]
    tiers: tuple[Tier, ...]
    tickets: tuple[Ticket, ...]
    sets: tuple[GrantSet, ...]
    rules: tuple[Rule, ...]
    alert: Alert
    other_alerts: tuple[Alert, ...]
    events: tuple[AlertEvent, ...]
    hosts: tuple[Host, ...]
    detections: tuple[Detection, ...]
    sessions: tuple[Session, ...]
    factors: tuple[Factor, ...]
    windows: tuple[Window, ...]
    responders: tuple[Responder, ...]
    bridges: tuple[Bridge, ...]
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
    event_query: dict[str, Any]
    event_expected: dict[str, Any]
    revision: str = "v1"
    seed: dict[str, Any] = field(default_factory=dict)

    @property
    def task_id(self) -> str:
        return f"secops-{self.ordinal:03d}"

    @property
    def case_reference(self) -> str:
        return f"SEC-{self.ordinal:04d}"

    @property
    def primary_ticket(self) -> Ticket:
        return self.tickets[0]

    @property
    def primary_class(self) -> CredentialClass:
        return next(item for item in self.classes if item.code == self.primary_ticket.credential_class)

    @property
    def primary_tier(self) -> Tier:
        return next(item for item in self.tiers if item.code == self.primary_ticket.tier_code)


def ticket_unit_objects(ticket: Ticket, identity_by_id: dict[str, Identity]) -> int:
    """Credential objects per principal or device: a fixed count or the identity's current inventory metering."""

    if ticket.unit_basis == "fixed":
        if ticket.unit_objects is None:
            raise ValueError(f"{ticket.ticket_id}: fixed tickets need unit_objects")
        return ticket.unit_objects
    return identity_by_id[ticket.identity_id].meter_value


__all__ = [
    "ANALYSTS",
    "AS_OF",
    "Alert",
    "AlertEvent",
    "Approval",
    "Bridge",
    "Chat",
    "Confirmation",
    "CredentialClass",
    "Detection",
    "Doc",
    "Email",
    "Factor",
    "GrantSet",
    "Host",
    "Identity",
    "Labels",
    "OBJECT_UNIT",
    "ORGANIZATION",
    "Option",
    "PrimaryWrite",
    "Responder",
    "Rule",
    "Scenario",
    "Session",
    "Ticket",
    "Tier",
    "USERS",
    "VENDORS",
    "WINDOW_HOURS",
    "WINDOW_TIMES",
    "Window",
    "business_days",
    "next_business_day",
    "ticket_unit_objects",
    "window_id",
    "window_interval",
]
