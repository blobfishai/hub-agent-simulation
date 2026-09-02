"""Scenario data model and shared synthetic entities for the PolicyDesk family.

Everything here is clean-room synthetic: Meridian Grid Utilities is not a real
organisation and no person, resource, vendor, policy, or number corresponds to a
real one. No upstream benchmark task text is reproduced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from ...engine.assets import MARKDOWN
from ...engine.decision import Labels, Option

AS_OF = "2026-05-11"
ORGANIZATION = {
    "id": "meridian-access-governance-v1",
    "name": "Meridian Grid Utilities — Access Governance",
    "organization_id": "ORG-MERIDIAN",
    "primary_site": "IAM-DESK",
    "systems": [
        "policy",
        "requests",
        "resources",
        "grants",
        "exceptions",
        "directory",
        "training",
        "audit",
        "screening",
        "reviews",
        "approvals",
        "messages",
        "chat",
        "drive",
        "notes",
    ],
}
DEPARTMENTS = (
    {"department_id": "DEPT-FIN", "name": "Finance Operations", "cost_centre": "CC-4100"},
    {"department_id": "DEPT-GRID", "name": "Grid Control", "cost_centre": "CC-2200"},
    {"department_id": "DEPT-DATA", "name": "Data Platform", "cost_centre": "CC-3300"},
    {"department_id": "DEPT-SEC", "name": "Security & Risk", "cost_centre": "CC-5000"},
)
USERS = (
    {"user_id": "U-ANALYST", "display_name": "Access Governance Analyst (you)", "role": "access_governance_analyst", "approval_limit_usd": 0},
    {"user_id": "U-OKAFOR", "display_name": "Ngozi Okafor", "role": "resource_owner", "approval_limit_usd": 15000},
    {"user_id": "U-HALLORAN", "display_name": "Declan Halloran", "role": "risk_committee_chair", "approval_limit_usd": 90000},
    {"user_id": "U-BERGSTROM", "display_name": "Elin Bergström", "role": "governance_lead", "approval_limit_usd": 20000},
    {"user_id": "U-NAKAMURA", "display_name": "Yuki Nakamura", "role": "audit_manager", "approval_limit_usd": 0},
)
SCREENING_VENDORS = (
    {"vendor_id": "VND-SENTINEL", "name": "Sentinel Clearance Services", "account_number": "MG-7714"},
    {"vendor_id": "VND-ATTESTA", "name": "Attesta Credentialing", "account_number": "MG-3062"},
)
# Approver review windows: AM 09:00-12:00, PM 13:00-16:00, weekdays.
WINDOW_TIMES = {"AM": ("09:00:00", "12:00:00"), "PM": ("13:00:00", "16:00:00")}
WINDOW_HOURS = 3


def business_days(start: str = AS_OF, weeks: int = 3) -> list[str]:
    first = date.fromisoformat(start)
    days = []
    for offset in range(weeks * 7):
        day = first + timedelta(days=offset)
        if day.weekday() < 5:
            days.append(day.isoformat())
    return days


def next_business_day(after: str) -> str:
    """First business day strictly after ``after`` (screening clears the next business day)."""

    day = date.fromisoformat(after) + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.isoformat()


def window_id(approver: str, day: str, session: str) -> str:
    return f"RVW-{approver.split('-')[1]}-{day.replace('-', '')}-{session}"


def window_interval(day: str, session: str) -> tuple[str, str]:
    start, end = WINDOW_TIMES[session]
    return f"{day}T{start}", f"{day}T{end}"


@dataclass(frozen=True)
class Person:
    person_id: str
    name: str
    title: str
    department_id: str
    employment_type: str = "employee"
    manager_id: str | None = None


@dataclass(frozen=True)
class Resource:
    resource_id: str
    code: str
    name: str
    system: str
    sensitivity_tier: str  # tier-1 | tier-2 | tier-3
    sod_domain: str
    owner_id: str


@dataclass(frozen=True)
class Policy:
    policy_id: str
    code: str
    title: str
    version: str
    effective_date: str
    status: str = "EFFECTIVE"
    supersedes: str | None = None


@dataclass(frozen=True)
class Clause:
    clause_id: str
    policy_id: str
    number: str
    topic: str
    sensitivity_tier: str
    max_grant_days: int
    requires_tier: int
    requires_training: str | None
    allowed_control: str | None
    text: str


@dataclass(frozen=True)
class Request:
    request_id: str
    requester_id: str
    resource_id: str
    requested_role: str
    duration_days: int
    justification: str
    manager_attested: bool
    sensitivity_tier: str
    # disposition_basis is the ground-truth reason, one of:
    #   APPROVE | EXCEPTION | REFUSE | DUPLICATE
    disposition_basis: str
    submitted_at: str
    duplicate_of: str | None = None
    status: str = "PENDING"
    note: str = ""


@dataclass(frozen=True)
class Grant:
    grant_id: str
    resource_id: str
    request_id: str | None
    role: str
    sod_domain: str
    covers_request_count: int
    granted_on: str
    expires_on: str
    status: str = "ACTIVE"
    status_reason: str | None = None
    approval_id: str | None = None


@dataclass(frozen=True)
class SodRule:
    rule_id: str
    domain_a: str
    domain_b: str
    severity: str
    rule_text: str


@dataclass(frozen=True)
class Exception_:
    exception_id: str
    resource_id: str
    request_id: str | None
    reason: str
    compensating_control: str
    approver_tier: int
    covers_request_count: int
    granted_on: str
    expires_on: str
    status: str = "ACTIVE"
    approval_id: str | None = None


@dataclass(frozen=True)
class Approver:
    approver_id: str
    name: str
    authority_tier: int
    max_sensitivity_tier: str
    status: str = "AVAILABLE"
    person_id: str | None = None
    available_from: str | None = None
    status_note: str | None = None


@dataclass(frozen=True)
class Training:
    record_id: str
    person_id: str
    training_code: str
    completed_on: str | None
    expires_on: str | None
    status: str = "CURRENT"


@dataclass(frozen=True)
class Finding:
    finding_id: str
    resource_id: str | None
    severity: str
    title: str
    blocks_grant: bool
    opened_on: str
    status: str = "OPEN"
    remediation_due: str | None = None


@dataclass(frozen=True)
class Window:
    day: str
    approver: str
    session: str
    status: str
    reason: str = ""


@dataclass(frozen=True)
class Session:
    session_id: str
    request_id: str | None
    resource_id: str | None
    approver_id: str | None
    start: str | None
    end: str | None
    status: str
    description: str


@dataclass(frozen=True)
class Confirmation:
    confirmation_id: str
    vendor_id: str
    credential: str
    reference: str
    slots_available: int
    standard_date: str
    expedited_date: str
    fee: int
    per_slot_fee: float
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
    labels: str = "access-governance"


@dataclass(frozen=True)
class Chat:
    thread_id: str
    title: str
    messages: tuple[tuple[str, str, str], ...]
    channel: str = "#access-governance"


@dataclass(frozen=True)
class Doc:
    path: str
    kind: str
    title: str
    content: str = ""
    media_type: str = MARKDOWN
    rows: tuple[tuple[Any, ...], ...] | None = None
    folder: str = "Access Governance"


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
    resource: Resource
    other_resources: tuple[Resource, ...]
    people: tuple[Person, ...]
    policies: tuple[Policy, ...]
    clauses: tuple[Clause, ...]
    requests: tuple[Request, ...]
    grants: tuple[Grant, ...]
    sod_rules: tuple[SodRule, ...]
    exceptions: tuple[Exception_, ...]
    approvers: tuple[Approver, ...]
    trainings: tuple[Training, ...]
    findings: tuple[Finding, ...]
    windows: tuple[Window, ...]
    sessions: tuple[Session, ...]
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
    request_query: dict[str, Any]
    request_expected: dict[str, Any]
    revision: str = "v5"
    seed: dict[str, Any] = field(default_factory=dict)

    @property
    def task_id(self) -> str:
        return f"policydesk-{self.ordinal:03d}"

    @property
    def case_reference(self) -> str:
        return f"AGR-{self.ordinal:04d}"

    @property
    def primary_request(self) -> Request:
        return self.requests[0]

    @property
    def operative_policy(self) -> Policy:
        return next(p for p in self.policies if p.status == "EFFECTIVE")

    @property
    def operative_clause(self) -> Clause:
        tier = self.resource.sensitivity_tier
        policy_id = self.operative_policy.policy_id
        return next(c for c in self.clauses if c.policy_id == policy_id and c.sensitivity_tier == tier)


def batch_requests(scenario: Scenario) -> list[Request]:
    """Today's pending requests for the scenario's target resource."""

    return [
        request
        for request in scenario.requests
        if request.resource_id == scenario.resource.resource_id and request.status == "PENDING"
    ]


def disposition_counts(scenario: Scenario) -> dict[str, int]:
    """Approve / exception / refuse / duplicate counts for the target batch."""

    batch = batch_requests(scenario)
    counts = {"APPROVE": 0, "EXCEPTION": 0, "REFUSE": 0, "DUPLICATE": 0}
    for request in batch:
        counts[request.disposition_basis] += 1
    return counts


__all__ = [
    "AS_OF",
    "Approval",
    "Approval",
    "Approver",
    "Chat",
    "Clause",
    "Confirmation",
    "DEPARTMENTS",
    "Doc",
    "Email",
    "Exception_",
    "Finding",
    "Grant",
    "Labels",
    "ORGANIZATION",
    "Option",
    "Person",
    "Policy",
    "PrimaryWrite",
    "Request",
    "Resource",
    "SCREENING_VENDORS",
    "Scenario",
    "Session",
    "SodRule",
    "Training",
    "USERS",
    "WINDOW_HOURS",
    "WINDOW_TIMES",
    "Window",
    "batch_requests",
    "business_days",
    "disposition_counts",
    "next_business_day",
    "window_id",
    "window_interval",
]
