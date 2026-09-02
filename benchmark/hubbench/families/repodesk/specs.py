"""Scenario data model and shared synthetic entities for the RepoDesk family.

Everything here is clean-room synthetic: Larkspur Systems is not a real
organisation and no engineer, customer, certification partner, repository,
module, or commit corresponds to a real one.  Shapes are GitHub / Jira /
CI / deploy-pipeline style only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from ...engine.assets import MARKDOWN
from ...engine.decision import Labels, Option

AS_OF = "2026-05-04"
ORGANIZATION = {
    "id": "larkspur-release-engineering-v1",
    "name": "Larkspur Systems — Release Engineering",
    "organization_id": "ORG-LARKSPUR",
    "primary_site": "REPO-PLATFORM",
    "systems": ["scm", "tracker", "ci", "deploy", "success", "partners", "oncall", "approvals", "messages", "chat", "drive", "notes"],
}
REPOSITORIES = (
    {"repo_id": "REPO-PLATFORM", "name": "larkspur/platform", "default_branch": "main", "visibility": "internal"},
    {"repo_id": "REPO-INFRA", "name": "larkspur/infra-images", "default_branch": "main", "visibility": "internal"},
)
ENVIRONMENTS = (
    {"environment_id": "ENV-PROD-SHARED", "name": "Production (shared multi-tenant)", "kind": "production", "cluster": "blue"},
    {"environment_id": "ENV-PROD-DEDICATED", "name": "Production (dedicated single-tenant pool)", "kind": "production", "cluster": "green"},
    {"environment_id": "ENV-STAGE", "name": "Staging", "kind": "staging", "cluster": "blue"},
)
RESULT_SOURCES = (
    {"source_id": "CI-MAIN", "name": "Release verification pipeline (release-eligible)", "type": "release_pipeline"},
    {"source_id": "CI-NIGHTLY", "name": "Nightly smoke pipeline (not release-eligible)", "type": "nightly_pipeline"},
    {"source_id": "LAB-CORVANE", "name": "Corvane Certification Labs (external)", "type": "external_lab"},
    {"source_id": "LAB-BRIGHTWATER", "name": "Brightwater Compliance Lab (external)", "type": "external_lab"},
)
ENGINEERS = (
    {"engineer_id": "ENG-KOWALCZYK", "name": "Ines Kowalczyk", "role": "component_owner", "focus": "Checkout and storefront"},
    {"engineer_id": "ENG-DESHPANDE", "name": "Rohan Deshpande", "role": "component_owner", "focus": "Payments"},
    {"engineer_id": "ENG-LINDGREN", "name": "Maja Lindgren", "role": "data_platform_lead", "focus": "Ledger, catalog, and ingest"},
    {"engineer_id": "ENG-ACHEBE", "name": "Chidi Achebe", "role": "security_engineer", "focus": "Compliance and CVE remediation"},
    {"engineer_id": "ENG-FARRELL", "name": "Siobhan Farrell", "role": "sre_oncall", "focus": "Platform reliability"},
)
USERS = (
    {"user_id": "U-RELENG", "display_name": "Release Engineering Coordinator (you)", "role": "release_engineering_coordinator", "approval_limit_usd": 0},
    {"user_id": "U-RAGHUNATHAN", "display_name": "Priya Raghunathan", "role": "release_engineering_manager", "approval_limit_usd": 20000},
    {"user_id": "U-WENDEL", "display_name": "Tobias Wendel", "role": "director_of_engineering", "approval_limit_usd": 120000},
    {"user_id": "U-SOLBERG", "display_name": "Hanna Solberg", "role": "sre_lead", "approval_limit_usd": 15000},
    {"user_id": "U-ADEYEMI", "display_name": "Marcus Adeyemi", "role": "change_board_chair", "approval_limit_usd": 0},
)
PARTNERS = (
    {"partner_id": "PRT-CORVANE", "name": "Corvane Certification Labs", "account_number": "LS-2210"},
    {"partner_id": "PRT-BRIGHTWATER", "name": "Brightwater Compliance Lab", "account_number": "LS-0874"},
)
WINDOW_TIMES = {"AM": ("08:00:00", "12:00:00"), "PM": ("13:00:00", "17:00:00")}
WINDOW_HOURS = 4
RUN_UNIT = "CHECK_RUN"
COMMIT_UNIT = "COMMIT"
HOUR_UNIT = "LANE_HOUR"


def business_days(start: str = AS_OF, weeks: int = 3) -> list[str]:
    first = date.fromisoformat(start)
    days = []
    for offset in range(weeks * 7):
        day = first + timedelta(days=offset)
        if day.weekday() < 5:
            days.append(day.isoformat())
    return days


def next_business_day(after: str) -> str:
    """First business day strictly after ``after`` (imported partner evidence clears the release gate the next business day)."""

    day = date.fromisoformat(after) + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.isoformat()


def window_id(lane: str, day: str, session: str) -> str:
    return f"RW-{lane.split('-')[1]}-{day.replace('-', '')}-{session}"


def window_interval(day: str, session: str) -> tuple[str, str]:
    start, end = WINDOW_TIMES[session]
    return f"{day}T{start}", f"{day}T{end}"


@dataclass(frozen=True)
class Component:
    """A deployable component (the owner of an issue) with its impact meterings."""

    component_id: str
    code: str
    name: str
    tier: str
    owner_team: str
    engineer_id: str
    impact_metric: str  # TOUCHED-MODULES | DATASET-GB
    impact_value: float
    impact_date: str
    stale_value: float = 0.0
    stale_date: str = "2026-04-20"
    repo_id: str = "REPO-PLATFORM"

    @property
    def impact_id(self) -> str:
        return f"IMP-{self.component_id.split('-')[1]}"

    @property
    def stale_impact_id(self) -> str:
        return f"IMP-{self.component_id.split('-')[1]}-04"


@dataclass(frozen=True)
class VerificationClass:
    code: str
    display: str
    runs_per_module: int
    required_checks: tuple[str, ...]
    evidence_tier: str = "release-gate evidence"
    min_validity_days: int = 14
    release_eligible: bool = True
    interchangeable_with: str | None = None


@dataclass(frozen=True)
class Module:
    module_id: str
    path: str
    component_id: str
    owner_team: str
    codeowner_id: str
    verification_class: str
    gate: str | None = None  # "reverted" | "flag_gated" | None
    gate_note: str = ""
    repo_id: str = "REPO-PLATFORM"


@dataclass(frozen=True)
class Commit:
    sha: str
    branch: str
    authored_at: str
    author_id: str
    message: str
    pr_number: int | None
    modules: tuple[str, ...]
    status: str = "merged"  # merged | reverted | embargoed | docs_only
    backported_to: str | None = None
    fix_for: str | None = None
    repo_id: str = "REPO-PLATFORM"


@dataclass(frozen=True)
class PullRequest:
    pr_id: str
    number: int
    title: str
    head_sha: str
    base_branch: str
    status: str
    issue_key: str | None
    author_id: str
    opened_at: str
    superseded_by: str | None = None
    repo_id: str = "REPO-PLATFORM"


@dataclass(frozen=True)
class Review:
    review_id: str
    pr_id: str
    reviewer_id: str
    state: str
    submitted_at: str


@dataclass(frozen=True)
class BranchRule:
    rule_id: str
    branch: str
    required_checks: tuple[str, ...]
    required_approvals: int = 1
    codeowner_review_required: bool = True
    status: str = "ACTIVE"
    repo_id: str = "REPO-PLATFORM"


@dataclass(frozen=True)
class Issue:
    key: str
    component_id: str
    verification_class: str
    basis: str  # "impact" | "fixed"
    fixed_modules: int | None
    gated_modules: int
    environments_in_scope: int
    scope_note: str
    build_minutes: int
    bake_minutes: int
    requested_by: str
    opened_at: str
    note: str = ""
    status: str = "open"
    severity: str = "S2"
    kind: str = "regression"
    title: str = ""
    customer_id: str | None = None
    commitment_id: str | None = None
    regression_from: str | None = None
    regression_to: str | None = None
    duplicate_of: str | None = None
    fix_version: str | None = None


@dataclass(frozen=True)
class Result:
    """One verification-result set in the CI evidence register."""

    result_id: str
    label: str
    verification_class: str
    source_id: str
    runs: int
    valid_until: str
    status: str = "PASSED"
    reason: str | None = None
    held_for: str | None = None
    register_excluded: bool = False
    register_note: str = ""


@dataclass(frozen=True)
class Pipeline:
    pipeline_id: str
    name: str
    component_id: str | None
    kind: str
    trigger: str
    base_minutes: int
    status: str = "enabled"
    repo_id: str = "REPO-PLATFORM"


@dataclass(frozen=True)
class PipelineRun:
    run_id: str
    pipeline_id: str
    started_at: str
    finished_at: str
    status: str
    exit_code: int
    summary: str
    head_sha: str = ""


@dataclass(frozen=True)
class Window:
    day: str
    lane: str
    session: str
    status: str
    reason: str = ""


@dataclass(frozen=True)
class Lane:
    lane_id: str
    name: str
    cluster: str = "blue"
    status: str = "ACTIVE"
    isolation_capable: bool = True
    note: str | None = None


@dataclass(frozen=True)
class Change:
    change_id: str
    component_id: str
    issue_key: str | None
    lane_id: str | None
    start: str | None
    end: str | None
    status: str
    description: str


@dataclass(frozen=True)
class Confirmation:
    confirmation_id: str
    partner_id: str
    verification_class: str
    reference: str
    runs_available: int
    standard_date: str
    expedited_date: str
    fee: int
    per_run_fee: float
    valid_until: str
    status: str = "OPEN"
    note: str = ""


@dataclass(frozen=True)
class Customer:
    customer_id: str
    name: str
    tier: str
    environment_id: str
    account_owner: str


@dataclass(frozen=True)
class Commitment:
    commitment_id: str
    customer_id: str
    issue_key: str
    cutover_date: str
    penalty_usd: int
    contract_ref: str
    kind: str = "cutover"
    status: str = "ACTIVE"
    note: str = ""


@dataclass(frozen=True)
class FlakyTest:
    flaky_id: str
    check_name: str
    module_id: str
    quarantined_since: str
    retry_minutes: int
    status: str = "QUARANTINED"
    note: str = ""


@dataclass(frozen=True)
class CoverageReport:
    report_id: str
    module_id: str
    build_sha: str
    line_coverage: float
    threshold: float
    generated_at: str
    status: str = "CURRENT"


@dataclass(frozen=True)
class RunnerPool:
    pool_id: str
    name: str
    capacity: int
    queue_minutes: int
    status: str = "ACTIVE"
    note: str = ""


@dataclass(frozen=True)
class FeatureFlag:
    flag_key: str
    environment_id: str
    state: str
    scope: str
    note: str = ""


@dataclass(frozen=True)
class Availability:
    availability_id: str
    engineer_id: str
    day: str
    session: str
    status: str
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
    labels: str = "release-eng"


@dataclass(frozen=True)
class Chat:
    thread_id: str
    title: str
    messages: tuple[tuple[str, str, str], ...]
    channel: str = "#release-eng"


@dataclass(frozen=True)
class Doc:
    path: str
    kind: str
    title: str
    content: str = ""
    media_type: str = MARKDOWN
    rows: tuple[tuple[Any, ...], ...] | None = None
    folder: str = "Release Engineering"


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
    component: Component
    other_components: tuple[Component, ...]
    classes: tuple[VerificationClass, ...]
    issues: tuple[Issue, ...]
    modules: tuple[Module, ...]
    commits: tuple[Commit, ...]
    pulls: tuple[PullRequest, ...]
    reviews: tuple[Review, ...]
    branch_rule: BranchRule
    results: tuple[Result, ...]
    pipelines: tuple[Pipeline, ...]
    pipeline_runs: tuple[PipelineRun, ...]
    windows: tuple[Window, ...]
    lanes: tuple[Lane, ...]
    changes: tuple[Change, ...]
    confirmation: Confirmation
    other_confirmations: tuple[Confirmation, ...]
    customer: Customer
    commitment: Commitment
    flaky: tuple[FlakyTest, ...]
    coverage: tuple[CoverageReport, ...]
    pool: RunnerPool
    flags: tuple[FeatureFlag, ...]
    availability: tuple[Availability, ...]
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
    commits_query: dict[str, Any]
    commits_expected: dict[str, Any]
    revision: str = "v1"
    seed: dict[str, Any] = field(default_factory=dict)

    @property
    def task_id(self) -> str:
        return f"repodesk-{self.ordinal:03d}"

    @property
    def case_reference(self) -> str:
        return f"SHIP-{self.ordinal:04d}"

    @property
    def primary_issue(self) -> Issue:
        return self.issues[0]

    @property
    def primary_class(self) -> VerificationClass:
        return next(item for item in self.classes if item.code == self.primary_issue.verification_class)


def components_by_id(scenario: Scenario) -> dict[str, Component]:
    return {item.component_id: item for item in (scenario.component, *scenario.other_components)}


def affected_modules(issue: Issue, components: dict[str, Component]) -> int:
    """Modules whose release gate must pass: the current impact count minus gated (reverted / flag-gated) modules, or the fixed scope."""

    if issue.basis == "impact":
        component = components[issue.component_id]
        if component.impact_metric != "TOUCHED-MODULES":
            raise ValueError(f"{issue.key}: impact basis needs a TOUCHED-MODULES metering")
        return int(component.impact_value) - issue.gated_modules
    if issue.fixed_modules is None:
        raise ValueError(f"{issue.key}: fixed issues need fixed_modules")
    return issue.fixed_modules - issue.gated_modules


def issue_runs(scenario: Scenario, issue: Issue) -> int:
    cls = next(item for item in scenario.classes if item.code == issue.verification_class)
    return affected_modules(issue, components_by_id(scenario)) * cls.runs_per_module * issue.environments_in_scope


__all__ = [
    "AS_OF",
    "Approval",
    "Availability",
    "BranchRule",
    "COMMIT_UNIT",
    "Change",
    "Chat",
    "Commit",
    "Commitment",
    "Component",
    "Confirmation",
    "CoverageReport",
    "Customer",
    "Doc",
    "ENGINEERS",
    "ENVIRONMENTS",
    "Email",
    "FeatureFlag",
    "FlakyTest",
    "HOUR_UNIT",
    "Issue",
    "Labels",
    "Lane",
    "Module",
    "ORGANIZATION",
    "Option",
    "PARTNERS",
    "Pipeline",
    "PipelineRun",
    "PrimaryWrite",
    "PullRequest",
    "REPOSITORIES",
    "RESULT_SOURCES",
    "RUN_UNIT",
    "Result",
    "Review",
    "RunnerPool",
    "Scenario",
    "USERS",
    "VerificationClass",
    "WINDOW_HOURS",
    "WINDOW_TIMES",
    "Window",
    "affected_modules",
    "business_days",
    "components_by_id",
    "issue_runs",
    "next_business_day",
    "window_id",
    "window_interval",
]
