"""Clean-room synthetic records for the ResearchDesk HubBench family."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...engine.assets import MARKDOWN
from ...engine.decision import Labels, Option

AS_OF = "2026-07-13"
ORGANIZATION = {
    "id": "meridian-researchdesk-v1",
    "name": "Meridian Works — Strategy & Research",
    "organization_id": "ORG-MERIDIAN",
    "primary_site": "KNOWLEDGE-HQ",
    "systems": [
        "knowledge",
        "metrics",
        "sources",
        "search",
        "reviews",
        "research",
        "approvals",
        "messages",
        "chat",
        "drive",
        "notes",
    ],
}
USERS = (
    {
        "user_id": "U-ANALYST",
        "display_name": "Research analyst (you)",
        "role": "research_analyst",
        "approval_limit_usd": 0,
    },
    {
        "user_id": "U-IBARRA",
        "display_name": "Mina Ibarra",
        "role": "director_of_research",
        "approval_limit_usd": 50000,
    },
    {
        "user_id": "U-OKAFOR",
        "display_name": "Chidi Okafor",
        "role": "vp_strategy",
        "approval_limit_usd": 150000,
    },
    {
        "user_id": "U-KLEIN",
        "display_name": "Ruth Klein",
        "role": "finance_methodologist",
        "approval_limit_usd": 25000,
    },
    {
        "user_id": "U-SATO",
        "display_name": "Emi Sato",
        "role": "governance_reviewer",
        "approval_limit_usd": 10000,
    },
)


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    source_type: str
    source_name: str
    value: int
    status: str
    reliability: str
    note: str


@dataclass(frozen=True)
class Doc:
    path: str
    kind: str
    title: str
    content: str = ""
    media_type: str = MARKDOWN
    rows: tuple[tuple[Any, ...], ...] | None = None


@dataclass(frozen=True)
class PrimaryWrite:
    tool: str
    arguments: dict[str, Any]
    table: str
    primary_key: str
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
    article_id: str
    article_slug: str
    article_title: str
    metric_key: str
    metric_name: str
    unit: str
    period_start: str
    period_end: str
    current_definition: str
    stale_definition: str
    current_revision: str
    stale_revision: str
    definition_numerator: str
    definition_denominator: str
    definition_exclusions: str
    numbers: dict[str, int | str]
    business_need: str
    business_need_reason: str
    standard_readiness: str
    expedited_readiness: str
    labels: Labels
    options: tuple[Option, Option, Option]
    sources: tuple[SourceRecord, ...]
    source_set_id: str
    approval_id: str
    approval_scope: dict[str, Any]
    query_key: str
    selected_slot_id: str
    protected_slot_id: str
    selected_review_date: str
    selected_reviewer_id: str
    expertise: str
    review_minutes: int
    primary_write: PrimaryWrite
    unauthorized_write: dict[str, Any]
    collaboration: dict[str, str]
    request: dict[str, str]
    chat_messages: tuple[tuple[str, str, str], ...]
    docs: tuple[Doc, ...]
    extra_answer: dict[str, Any]
    extra_descriptions: dict[str, str]
    extra_calculations: tuple[dict[str, Any], ...]

    @property
    def task_id(self) -> str:
        return f"researchdesk-{self.ordinal:03d}"

    @property
    def case_reference(self) -> str:
        return f"RSH-{self.ordinal:04d}"

    @property
    def snapshot_id(self) -> str:
        return f"SNAP-{self.ordinal:04d}"

    @property
    def current_revision_id(self) -> str:
        return f"REV-{self.ordinal:04d}-CURRENT"

    @property
    def stale_revision_id(self) -> str:
        return f"REV-{self.ordinal:04d}-STALE"

    @property
    def chat_thread_id(self) -> str:
        return f"CHAT-RSH-{self.ordinal:04d}"


__all__ = [
    "AS_OF",
    "ORGANIZATION",
    "USERS",
    "Doc",
    "PrimaryWrite",
    "Scenario",
    "SourceRecord",
]
