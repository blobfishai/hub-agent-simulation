"""Scenario data model and shared synthetic entities for the Workplace family.

Everything here is clean-room synthetic: Ferngate Software is not a real
organisation and no customer, employee, partner, contract, or ticket
corresponds to a real one.  Shapes are helpdesk / tracker / wiki / calendar /
HRIS / contract-register style only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from ...engine.assets import MARKDOWN
from ...engine.decision import Labels, Option
from .tools import POINTS_PER_LEAVE_DAY, QUALIFIED_LEVEL, weekdays_between

AS_OF = "2026-04-14"
ORGANIZATION = {
    "id": "ferngate-delivery-v1",
    "name": "Ferngate Software — Customer Delivery",
    "organization_id": "ORG-FERNGATE",
    "primary_site": "Customer Delivery squad",
    "systems": ["helpdesk", "tracker", "wiki", "calendar", "hris", "contracts", "portal", "approvals", "mail", "chat", "drive", "notes"],
}
USERS = (
    {"user_id": "U-COORD", "display_name": "Customer Delivery Coordinator (you)", "role": "customer_delivery_coordinator", "approval_limit_usd": 0},
    {"user_id": "U-HALE", "display_name": "Bronwyn Hale", "role": "delivery_manager", "approval_limit_usd": 8000},
    {"user_id": "U-ADEYEMI", "display_name": "Folake Adeyemi", "role": "account_director", "approval_limit_usd": 5000},
    {"user_id": "U-LINDGREN", "display_name": "Mats Lindgren", "role": "finance_controller", "approval_limit_usd": 60000},
    {"user_id": "U-SORENSEN", "display_name": "Kirsten Sørensen", "role": "engineering_lead", "approval_limit_usd": 3000},
    {"user_id": "U-QUAYLE", "display_name": "Desmond Quayle", "role": "support_director", "approval_limit_usd": 25000},
)
PARTNER = {"partner_id": "PRT-WRENFIELD", "name": "Wrenfield Delivery Partners", "agreement": "MSA-WRN-2025-11"}
SESSION_TIMES = {"AM": ("09:00:00", "13:00:00"), "PM": ("13:30:00", "17:30:00")}
BLOCK_HOURS = 4
COUNTED_ISSUE_TYPES = ("Fix", "Test", "Verification")
OPEN_ISSUE_STATUSES = ("To Do", "In Progress", "In Review")
STANDARD_PAGE_ID = "WIKI-4410"
SUPERSEDED_PAGE_ID = "WIKI-4410-V4"
DELIVERY_EMAIL = "customer-delivery@ferngate.example"


def business_days(start: str = AS_OF, weeks: int = 4) -> list[str]:
    """Weekday staff calendar, four weeks from the planning date."""

    first = date.fromisoformat(start)
    days = []
    for offset in range(weeks * 7):
        day = first + timedelta(days=offset)
        if day.weekday() < 5:
            days.append(day.isoformat())
    return days


def next_business_day(after: str) -> str:
    """First business day strictly after ``after`` (verification / posting lands the next business day)."""

    day = date.fromisoformat(after) + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.isoformat()


def hours_between(start: str, end: str) -> float:
    delta = datetime.fromisoformat(end) - datetime.fromisoformat(start)
    return round(delta.total_seconds() / 3600, 2)


def block_id(employee_id: str, day: str, session: str) -> str:
    return f"BLK-{employee_id.rsplit('-', 1)[1]}-{day.replace('-', '')}-{session}"


def block_interval(day: str, session: str) -> tuple[str, str]:
    start, end = SESSION_TIMES[session]
    return f"{day}T{start}", f"{day}T{end}"


@dataclass(frozen=True)
class Customer:
    customer_id: str
    name: str
    tier: str
    region: str
    account_owner: str
    industry: str


@dataclass(frozen=True)
class Agreement:
    agreement_id: str
    customer_id: str
    plan: str
    monthly_fee_usd: int
    sla_policy_id: str
    credit_pct_per_breach: int
    credit_cap_pct: int
    start_date: str
    end_date: str
    status: str = "active"
    note: str = ""


@dataclass(frozen=True)
class SlaTarget:
    priority: str
    response_hours: float
    resolution_hours: float
    in_scope: bool = True


@dataclass(frozen=True)
class SlaPolicy:
    sla_policy_id: str
    name: str
    version: int
    targets: tuple[SlaTarget, ...]
    status: str = "current"
    effective_from: str = "2026-01-05"
    note: str = ""

    def target(self, priority: str) -> SlaTarget:
        return next(item for item in self.targets if item.priority == priority)


@dataclass(frozen=True)
class Commitment:
    commitment_id: str
    agreement_id: str
    description: str
    committed_date: str
    penalty_usd_per_week: int
    status: str = "committed"
    accepted_on: str | None = None
    note: str = ""


@dataclass(frozen=True)
class Ticket:
    ticket_id: str
    customer_id: str
    subject: str
    priority: str
    status: str
    opened_at: str
    first_response_at: str | None
    resolved_at: str | None
    requester: str
    channel: str = "portal"
    duplicate_of: str | None = None
    escalation_id: str | None = None
    exempt_reason: str | None = None
    note: str = ""


@dataclass(frozen=True)
class Escalation:
    escalation_id: str
    ticket_id: str
    customer_id: str
    level: int
    status: str
    opened_at: str
    owner_user_id: str
    summary: str
    required_skill: str
    hands_on_minutes: int
    verification_minutes: int
    claim_ticket_ids: tuple[str, ...] = ()
    claim_basis: str | None = None
    target_date: str | None = None
    sprint_id: str | None = None
    resolution_plan: str | None = None
    note: str = ""


@dataclass(frozen=True)
class Issue:
    issue_key: str
    project: str
    summary: str
    type: str
    status: str
    story_points: int
    required_skill: str
    escalation_id: str | None = None
    sprint_id: str | None = None
    assignee_id: str | None = None
    priority: str = "High"
    note: str = ""


@dataclass(frozen=True)
class Sprint:
    sprint_id: str
    name: str
    state: str
    start_date: str
    end_date: str
    goal: str
    board: str = "Customer Delivery"


@dataclass(frozen=True)
class CapacityRow:
    sprint_id: str
    employee_id: str
    capacity_points: int
    committed_points: int
    report_date: str = "2026-04-10"

    @property
    def remaining(self) -> int:
        return self.capacity_points - self.committed_points


@dataclass(frozen=True)
class Employee:
    employee_id: str
    name: str
    title: str
    team: str
    timezone: str
    email: str
    skills: tuple[tuple[str, int], ...]
    status: str = "active"
    on_calendar: bool = True
    engagement_from: str | None = None
    note: str = ""

    def level(self, skill_code: str) -> int:
        return next((level for code, level in self.skills if code == skill_code), 0)


@dataclass(frozen=True)
class TimeOff:
    timeoff_id: str
    employee_id: str
    start_date: str
    end_date: str
    kind: str = "annual leave"
    status: str = "approved"
    approved_on: str = "2026-04-13"


@dataclass(frozen=True)
class OnCall:
    shift_id: str
    employee_id: str
    start_date: str
    end_date: str
    rota: str = "customer-delivery-primary"


@dataclass(frozen=True)
class Block:
    day: str
    employee_id: str
    session: str
    status: str
    reason: str = ""


@dataclass(frozen=True)
class Booking:
    booking_id: str
    employee_id: str | None
    escalation_id: str | None
    start: str | None
    end: str | None
    status: str
    description: str
    issue_key: str | None = None


@dataclass(frozen=True)
class Credit:
    credit_id: str
    agreement_id: str
    customer_id: str
    escalation_id: str | None
    amount_usd: int
    basis: str
    status: str
    issued_on: str
    note: str = ""
    billing_option: str | None = None
    confirmation_id: str | None = None
    expected_application_date: str | None = None


@dataclass(frozen=True)
class BillingRun:
    run_id: str
    run_date: str
    cutoff_date: str
    kind: str = "monthly invoice run"
    status: str = "scheduled"


@dataclass(frozen=True)
class Confirmation:
    confirmation_id: str
    customer_id: str
    kind: str  # partner_staffing | change_window | billing_run
    counterparty: str
    reference: str
    standard_date: str
    expedited_date: str
    expedite_fee_usd: int
    valid_until: str
    status: str = "OPEN"
    capacity_points: int | None = None
    skill_code: str | None = None
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
    labels: str = "customer-delivery"


@dataclass(frozen=True)
class Chat:
    thread_id: str
    title: str
    messages: tuple[tuple[str, str, str], ...]
    channel: str = "#customer-delivery"


@dataclass(frozen=True)
class Doc:
    path: str
    kind: str
    title: str
    content: str = ""
    media_type: str = MARKDOWN
    rows: tuple[tuple[Any, ...], ...] | None = None
    folder: str = "Customer Delivery"


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
    customer: Customer
    agreement: Agreement
    other_agreements: tuple[Agreement, ...]
    sla_policies: tuple[SlaPolicy, ...]
    commitments: tuple[Commitment, ...]
    tickets: tuple[Ticket, ...]
    escalations: tuple[Escalation, ...]
    issues: tuple[Issue, ...]
    sprints: tuple[Sprint, ...]
    capacity: tuple[CapacityRow, ...]
    roster: tuple[Employee, ...]
    timeoff: tuple[TimeOff, ...]
    oncall: tuple[OnCall, ...]
    blocks: tuple[Block, ...]
    bookings: tuple[Booking, ...]
    credits: tuple[Credit, ...]
    billing_runs: tuple[BillingRun, ...]
    confirmation: Confirmation
    other_confirmations: tuple[Confirmation, ...]
    approval: Approval
    business_need: str
    business_need_reason: str
    control_commitment_id: str
    item: str
    labels: Labels
    numbers: dict[str, Any]
    options: tuple[Option, Option, Option]
    option_ready: dict[str, str]
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
    blocks_query: dict[str, str]
    selected_block_id: str
    revision: str = "v1"
    seed: dict[str, Any] = field(default_factory=dict)

    @property
    def task_id(self) -> str:
        return f"workplace-{self.ordinal:03d}"

    @property
    def case_reference(self) -> str:
        return f"WORK-{self.ordinal:04d}"

    @property
    def escalation(self) -> Escalation:
        return self.escalations[0]

    @property
    def primary_ticket(self) -> Ticket:
        return next(ticket for ticket in self.tickets if ticket.ticket_id == self.escalation.ticket_id)

    @property
    def sla_policy(self) -> SlaPolicy:
        return next(policy for policy in self.sla_policies if policy.sla_policy_id == self.agreement.sla_policy_id)

    @property
    def active_sprint(self) -> Sprint:
        return next(sprint for sprint in self.sprints if sprint.state == "active")

    @property
    def control_commitment(self) -> Commitment:
        return next(item for item in self.commitments if item.commitment_id == self.control_commitment_id)

    @property
    def squad(self) -> tuple[Employee, ...]:
        return tuple(person for person in self.roster if person.on_calendar)


__all__ = [
    "AS_OF",
    "Agreement",
    "Approval",
    "BLOCK_HOURS",
    "BillingRun",
    "Block",
    "Booking",
    "COUNTED_ISSUE_TYPES",
    "CapacityRow",
    "Chat",
    "Commitment",
    "Confirmation",
    "Credit",
    "Customer",
    "DELIVERY_EMAIL",
    "Doc",
    "Email",
    "Employee",
    "Escalation",
    "Issue",
    "Labels",
    "OPEN_ISSUE_STATUSES",
    "ORGANIZATION",
    "OnCall",
    "Option",
    "PARTNER",
    "POINTS_PER_LEAVE_DAY",
    "PrimaryWrite",
    "QUALIFIED_LEVEL",
    "SESSION_TIMES",
    "STANDARD_PAGE_ID",
    "SUPERSEDED_PAGE_ID",
    "Scenario",
    "SlaPolicy",
    "SlaTarget",
    "Sprint",
    "Ticket",
    "TimeOff",
    "USERS",
    "block_id",
    "block_interval",
    "business_days",
    "hours_between",
    "next_business_day",
    "weekdays_between",
]
