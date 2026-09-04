"""Build the eight ResearchDesk tasks, evidence rooms, and sealed contracts."""

from __future__ import annotations

import json
from typing import Any

from ...engine.assets import (
    CSV,
    EML,
    JSON,
    MARKDOWN,
    XLSX,
    YAML,
    asset,
    eml,
    yaml_lines,
)
from ...engine.catalog import (
    answer_checks,
    build_rubric_milestones,
    milestone_descriptions,
    sequence_signature,
)
from ...engine.decision import DecisionInputs, answer_schema, build_decision_model
from ...engine.families import CONTEXT_TOOL, SUBMIT_TOOL
from ...engine.grading_contracts import fact_text_contract
from ...engine.quality_assets import (
    quality_support_assets,
    quality_support_investigations,
    scoped_csv,
    scoped_markdown,
)
from .scenarios import scenarios
from .specs import AS_OF, ORGANIZATION, USERS, Scenario

BENCHMARK = "HubBench"
FAMILY_SLUG = "researchdesk"
FAMILY_VERSION = "1.0.1"
ITEM_FIELD = {
    "plan": "coverage_item_or_resource",
    "quantity": "controlled_item_or_record",
    "schedule": "affected_resource_or_operation",
}
GAP_FIELD = {
    "plan": "shortage_quantity",
    "quantity": "transaction_quantity",
    "schedule": "capacity_gap",
}
CASE_FOLDER = "Strategy & Research/Cases/{case}"
OPEN_SOURCE_ANCHORS = (
    {
        "name": "GAIA",
        "harbor_dataset": "gaia/gaia",
        "harbor_url": "https://hub.harborframework.com/datasets/gaia/gaia/latest",
        "upstream_url": "https://huggingface.co/datasets/gaia-benchmark/GAIA",
        "evaluation_shape": "multi-step questions requiring source discovery, reasoning, and exact answers",
        "distribution_note": "gated upstream; no tasks, answers, or attachments redistributed",
    },
    {
        "name": "DeepSearchQA",
        "harbor_dataset": "kgmon/deepsearchqa",
        "harbor_url": "https://hub.harborframework.com/datasets/kgmon/deepsearchqa/latest",
        "upstream_url": "https://huggingface.co/datasets/google/deepsearchqa",
        "license": "Apache-2.0",
        "evaluation_shape": "long-form multi-source information seeking with traceable evidence",
    },
    {
        "name": "SimpleQA",
        "harbor_dataset": "openai/simpleqa",
        "harbor_url": "https://hub.harborframework.com/datasets/openai/simpleqa/latest",
        "upstream_url": "https://github.com/openai/simple-evals",
        "license": "MIT",
        "evaluation_shape": "short fact-seeking questions with exact-answer evaluation",
    },
)

CURRENT_POLICY = """# Research evidence and publication policy v6

Effective 2026-07-01. A research claim or packet must bind an active article,
the CURRENT metric definition, the exact measurement period, a CURRENT source
set, and the signed task-scoped approval. Search rank is discovery evidence,
never authority. SUPERSEDED definitions and source records explain conflicts
but cannot support a publication. Protected methodology-review capacity cannot
be displaced without a separately signed exception. Every write must be read
back before a stakeholder draft is created.
"""
SUPERSEDED_POLICY = """# Research publication policy 2025 — SUPERSEDED

Historical rule: a top-ranked internal search result could be quoted while
methodology review was pending. This rule ended on 2026-06-30. It cannot
authorize a current claim, packet, or review reservation.
"""


def verify_numbers(scenario: Scenario) -> None:
    numbers = scenario.numbers
    observed = int(numbers["observed"])
    excluded = int(numbers["excluded"])
    eligible = int(numbers["eligible"])
    scope = int(numbers["scope"])
    if eligible != observed - excluded:
        raise ValueError(f"{scenario.task_id}: supported measure drift")
    if int(numbers["gap"]) != max(0, scope - eligible):
        raise ValueError(f"{scenario.task_id}: evidence gap drift")
    if scenario.mode == "quantity" and int(numbers["transaction_quantity"]) != eligible:
        raise ValueError(
            f"{scenario.task_id}: published claim must equal supported measure"
        )
    if (
        scenario.mode == "schedule"
        and numbers["selected_resource"] != scenario.selected_slot_id
    ):
        raise ValueError(f"{scenario.task_id}: selected review slot drift")
    if sum(option.recommended for option in scenario.options) != 1:
        raise ValueError(f"{scenario.task_id}: exactly one option must be recommended")


def build_facts(scenario: Scenario) -> tuple[dict[str, str], ...]:
    numbers = scenario.numbers
    return (
        {
            "id": "authoritative_identity",
            "evidence": f"Article {scenario.article_id} and current revision {scenario.current_revision_id}",
            "rubric": f"Resolved {scenario.article_id} by immutable identity and rejected the archived same-topic search result.",
        },
        {
            "id": "effective_requirement",
            "evidence": f"{scenario.current_definition} over {scenario.period_start}..{scenario.period_end}",
            "rubric": f"Applied {scenario.current_definition}, the exact period, and the {numbers['scope']} {scenario.unit} business requirement.",
        },
        {
            "id": "eligible_coverage",
            "evidence": f"{scenario.snapshot_id} and {scenario.source_set_id}",
            "rubric": f"Reconciled {numbers['observed']} observed minus {numbers['excluded']} excluded into {numbers['eligible']} supported {scenario.unit}.",
        },
        {
            "id": "conditional_external_recovery",
            "evidence": f"Independent source-set readiness dates {scenario.standard_readiness} and {scenario.expedited_readiness}",
            "rubric": "Kept later source reconciliation and the faster unqualified route conditional rather than treating either as current evidence.",
        },
        {
            "id": "finite_capacity",
            "evidence": f"Qualified slot {scenario.selected_slot_id}; protected slot {scenario.protected_slot_id}",
            "rubric": f"Applied {scenario.review_minutes} minutes of qualified capacity and preserved protected methodology work.",
        },
        {
            "id": "approval_scope",
            "evidence": scenario.approval_id,
            "rubric": f"Applied {scenario.approval_id} only to its article, metric, definition, source set, value, and review-capacity scope.",
        },
        {
            "id": "business_impact",
            "evidence": scenario.business_need,
            "rubric": f"Compared the supported outcome with {scenario.business_need}, the documented date for {scenario.business_need_reason}.",
        },
    )


def build_model(scenario: Scenario) -> dict[str, Any]:
    numbers = scenario.numbers
    return build_decision_model(
        DecisionInputs(
            mode=scenario.mode,
            labels=scenario.labels,
            item=scenario.article_id,
            record=scenario.article_id,
            revision=scenario.current_revision,
            scope=int(numbers["scope"]),
            observed=int(numbers["observed"]),
            excluded=int(numbers["excluded"]),
            eligible=int(numbers["eligible"]),
            gap=int(numbers["gap"]),
            business_need=scenario.business_need,
            standard_readiness=scenario.standard_readiness,
            expedited_readiness=scenario.expedited_readiness,
            options=scenario.options,
            transaction_quantity=int(numbers["transaction_quantity"])
            if "transaction_quantity" in numbers
            else None,
            selected_resource=str(numbers["selected_resource"])
            if "selected_resource" in numbers
            else None,
            extra_answer=dict(scenario.extra_answer),
            extra_descriptions=dict(scenario.extra_descriptions),
            extra_calculations=scenario.extra_calculations,
            facts=build_facts(scenario),
        )
    )


def _prior_id(prefix: str, base: int, ordinal: int) -> str:
    return f"{prefix}{base - 1 + ordinal}"


def seed_tables(
    scenario: Scenario,
    drive_files: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    current_source_ids = [
        source.source_id for source in scenario.sources if source.status == "VERIFIED"
    ]
    stale_source_ids = [
        source.source_id for source in scenario.sources if source.status != "VERIFIED"
    ]
    historic_slot_id = f"SLOT-RSH-{scenario.ordinal:04d}-HISTORICAL"
    return {
        "users": [dict(row) for row in USERS],
        "knowledge_articles": [
            {
                "article_id": scenario.article_id,
                "slug": scenario.article_slug,
                "title": scenario.article_title,
                "owner": "strategy-research",
                "status": "ACTIVE",
                "current_revision": scenario.current_revision,
                "summary": f"Current controlled article for {scenario.metric_name}; case {scenario.case_reference}.",
            },
            {
                "article_id": f"{scenario.article_id}-ARCHIVE",
                "slug": f"{scenario.article_slug}-archive",
                "title": f"{scenario.article_title} — archived headline",
                "owner": "research-archive",
                "status": "ARCHIVED",
                "current_revision": scenario.stale_revision,
                "summary": f"Retired article using {scenario.stale_definition}; not current evidence for {scenario.case_reference}.",
            },
        ],
        "knowledge_revisions": [
            {
                "revision_id": scenario.current_revision_id,
                "article_id": scenario.article_id,
                "revision": scenario.current_revision,
                "effective_from": "2026-07-01",
                "status": "CURRENT",
                "definition_id": scenario.current_definition,
                "body": f"Current {scenario.metric_name} article under {scenario.current_definition} for {scenario.period_start}..{scenario.period_end}.",
            },
            {
                "revision_id": scenario.stale_revision_id,
                "article_id": scenario.article_id,
                "revision": scenario.stale_revision,
                "effective_from": "2025-07-01",
                "status": "SUPERSEDED",
                "definition_id": scenario.stale_definition,
                "body": f"Retired calculation retained to explain the conflicting {scenario.metric_name} headline.",
            },
        ],
        "metric_definitions": [
            {
                "definition_id": scenario.current_definition,
                "metric_key": scenario.metric_key,
                "name": scenario.metric_name,
                "unit": scenario.unit,
                "numerator": scenario.definition_numerator,
                "denominator": scenario.definition_denominator,
                "exclusions": scenario.definition_exclusions,
                "effective_from": "2026-07-01",
                "status": "CURRENT",
            },
            {
                "definition_id": scenario.stale_definition,
                "metric_key": scenario.metric_key,
                "name": f"Retired {scenario.metric_name}",
                "unit": scenario.unit,
                "numerator": "legacy headline numerator",
                "denominator": "legacy denominator",
                "exclusions": "legacy exclusions omitted current controlled boundaries",
                "effective_from": "2025-07-01",
                "status": "SUPERSEDED",
            },
        ],
        "metric_snapshots": [
            {
                "snapshot_id": scenario.snapshot_id,
                "metric_key": scenario.metric_key,
                "period_start": scenario.period_start,
                "period_end": scenario.period_end,
                "definition_id": scenario.current_definition,
                "gross_value": int(scenario.numbers["observed"]),
                "excluded_value": int(scenario.numbers["excluded"]),
                "supported_value": int(scenario.numbers["eligible"]),
                "unit": scenario.unit,
                "source_set_id": scenario.source_set_id,
                "status": "PUBLISHED",
                "published_at": "2026-07-12T18:00:00",
            },
            {
                "snapshot_id": f"{scenario.snapshot_id}-OLD",
                "metric_key": scenario.metric_key,
                "period_start": scenario.period_start,
                "period_end": scenario.period_end,
                "definition_id": scenario.stale_definition,
                "gross_value": int(scenario.numbers["observed"]),
                "excluded_value": 0,
                "supported_value": int(scenario.numbers["observed"]),
                "unit": scenario.unit,
                "source_set_id": scenario.source_set_id,
                "status": "SUPERSEDED",
                "published_at": "2026-06-20T18:00:00",
            },
        ],
        "source_sets": [
            {
                "source_set_id": scenario.source_set_id,
                "description": f"Independent evidence for {scenario.article_title}",
                "required_sources": 3,
                "status": "CURRENT",
            }
        ],
        "source_records": [
            {
                "source_id": source.source_id,
                "source_set_id": scenario.source_set_id,
                "source_type": source.source_type,
                "source_name": source.source_name,
                "captured_at": f"2026-07-{8 + index:02d}T16:00:00",
                "value": source.value,
                "unit": scenario.unit,
                "status": source.status,
                "reliability": source.reliability,
                "note": source.note,
            }
            for index, source in enumerate(scenario.sources)
        ],
        "search_indexes": [
            {
                "index_id": "IDX-KNOWLEDGE-CURRENT",
                "name": "Current knowledge and evidence",
                "status": "ACTIVE",
                "revision": "2026-07-12.4",
                "last_refreshed": "2026-07-12T22:00:00",
            },
            {
                "index_id": "IDX-KNOWLEDGE-ARCHIVE",
                "name": "Research archive",
                "status": "ARCHIVE",
                "revision": "2026-07-01.1",
                "last_refreshed": "2026-07-01T01:00:00",
            },
        ],
        "search_hits": [
            {
                "hit_id": f"HIT-{scenario.ordinal:04d}-01",
                "index_id": "IDX-KNOWLEDGE-CURRENT",
                "query_key": scenario.query_key,
                "article_id": scenario.article_id,
                "source_id": scenario.sources[0].source_id,
                "rank": 1,
                "snippet": f"Current article {scenario.current_revision}; definition {scenario.current_definition}.",
                "status": "CURRENT",
            },
            {
                "hit_id": f"HIT-{scenario.ordinal:04d}-02",
                "index_id": "IDX-KNOWLEDGE-CURRENT",
                "query_key": scenario.query_key,
                "article_id": f"{scenario.article_id}-ARCHIVE",
                "source_id": scenario.sources[-1].source_id,
                "rank": 2,
                "snippet": f"Retired headline using {scenario.stale_definition}.",
                "status": "SUPERSEDED",
            },
            {
                "hit_id": f"HIT-{scenario.ordinal:04d}-03",
                "index_id": "IDX-KNOWLEDGE-CURRENT",
                "query_key": scenario.query_key,
                "article_id": scenario.article_id,
                "source_id": scenario.sources[2].source_id,
                "rank": 3,
                "snippet": scenario.business_need_reason,
                "status": "CURRENT",
            },
        ],
        "review_slots": [
            {
                "slot_id": scenario.selected_slot_id,
                "review_date": scenario.selected_review_date,
                "start_time": "13:00:00",
                "end_time": "15:00:00",
                "duration_minutes": max(120, scenario.review_minutes),
                "reviewer_id": scenario.selected_reviewer_id,
                "expertise": scenario.expertise,
                "status": "free",
                "hold_reason": None,
                "reservation_id": None,
            },
            {
                "slot_id": scenario.protected_slot_id,
                "review_date": scenario.expedited_readiness,
                "start_time": "09:00:00",
                "end_time": "11:00:00",
                "duration_minutes": 120,
                "reviewer_id": scenario.selected_reviewer_id,
                "expertise": scenario.expertise,
                "status": "protected",
                "hold_reason": "regulatory or close assurance work",
                "reservation_id": None,
            },
            {
                "slot_id": f"SLOT-RSH-{scenario.ordinal:04d}-GENERAL",
                "review_date": scenario.standard_readiness,
                "start_time": "15:00:00",
                "end_time": "17:00:00",
                "duration_minutes": 120,
                "reviewer_id": "U-IBARRA",
                "expertise": "general_research",
                "status": "free",
                "hold_reason": None,
                "reservation_id": None,
            },
            {
                "slot_id": historic_slot_id,
                "review_date": "2026-06-30",
                "start_time": "10:00:00",
                "end_time": "11:00:00",
                "duration_minutes": 60,
                "reviewer_id": "U-SATO",
                "expertise": "governance",
                "status": "completed",
                "hold_reason": None,
                "reservation_id": _prior_id("RSV-", 7000, scenario.ordinal),
            },
        ],
        "approvals": [
            {
                "approval_id": scenario.approval_id,
                "subject": f"{scenario.case_reference}: {scenario.article_title}",
                "approver_id": "U-IBARRA",
                "approver_role": "director_of_research",
                "status": "APPROVED",
                "granted_on": "2026-07-12",
                "valid_until": "2026-07-31",
                "scope_json": json.dumps(scenario.approval_scope, sort_keys=True),
            },
            {
                "approval_id": f"AP-RSH-{scenario.ordinal:04d}-OLD",
                "subject": "Retired annual research delegation",
                "approver_id": "U-OKAFOR",
                "approver_role": "vp_strategy",
                "status": "EXPIRED",
                "granted_on": "2025-01-02",
                "valid_until": "2025-12-31",
                "scope_json": json.dumps(
                    {"action": "publish_search_headline", "status": "retired"},
                    sort_keys=True,
                ),
            },
        ],
        "messages": [
            {
                "message_id": scenario.request["message_id"],
                "thread_id": scenario.request["thread_id"],
                "channel": "email",
                "sender": scenario.request["sender"],
                "recipients": scenario.request["recipients"],
                "subject": scenario.request["subject"],
                "sent_at": scenario.request["sent_at"],
                "body": scenario.request["body"],
                "attachments_json": json.dumps(
                    [
                        {
                            "name": f"approval-{scenario.approval_id}.json",
                            "mime_type": "application/json",
                        }
                    ]
                ),
                "labels": f"research,{scenario.case_reference}",
            },
            {
                "message_id": f"MSG-RSH-{scenario.ordinal:04d}-00",
                "thread_id": f"THR-RSH-{scenario.ordinal:04d}-GENERAL",
                "channel": "email",
                "sender": "library@meridian.example",
                "recipients": "researchdesk@meridian.example",
                "subject": "Weekly research-library digest",
                "sent_at": "2026-07-12T17:30:00",
                "body": "The weekly index refresh completed. Ranked snippets remain discovery aids and require source verification.",
                "attachments_json": "[]",
                "labels": "research-digest",
            },
        ],
        "chat_threads": [
            {
                "thread_id": scenario.chat_thread_id,
                "channel": "#strategy-research",
                "title": f"{scenario.case_reference} — {scenario.article_title}",
                "messages_json": json.dumps(
                    [
                        {"author": author, "ts": ts, "text": text}
                        for author, ts, text in scenario.chat_messages
                    ]
                ),
            },
            {
                "thread_id": f"CHAT-RSH-{scenario.ordinal:04d}-GENERAL",
                "channel": "#strategy-research",
                "title": "General — library indexing",
                "messages_json": json.dumps(
                    [
                        {
                            "author": "Mina Ibarra",
                            "ts": "2026-07-12T16:00:00",
                            "text": "Index refresh is complete; verify every quoted record against its source set.",
                        }
                    ]
                ),
            },
        ],
        "drive_files": drive_files,
        "evidence_files": evidence,
        "research_claims": [
            {
                "claim_id": _prior_id("CLM-", 5000, scenario.ordinal),
                "article_id": scenario.article_id,
                "metric_key": scenario.metric_key,
                "period_start": "2026-01-01",
                "period_end": "2026-03-31",
                "value": 1,
                "unit": scenario.unit,
                "definition_id": scenario.current_definition,
                "source_set_id": scenario.source_set_id,
                "approval_id": scenario.approval_id,
                "note": "Historical seed claim",
                "status": "ARCHIVED",
                "created_by": "director_of_research",
                "created_at": "2026-04-10T09:00:00",
                "revision": 1,
            }
        ],
        "evidence_packets": [
            {
                "packet_id": _prior_id("PKT-", 6000, scenario.ordinal),
                "article_id": scenario.article_id,
                "metric_key": scenario.metric_key,
                "source_set_id": scenario.source_set_id,
                "included_sources_json": json.dumps(current_source_ids, sort_keys=True),
                "excluded_sources_json": json.dumps(stale_source_ids, sort_keys=True),
                "approval_id": scenario.approval_id,
                "summary": "Historical seed packet",
                "status": "ARCHIVED",
                "created_by": "research_analyst",
                "created_at": "2026-04-10T09:00:00",
                "revision": 1,
            }
        ],
        "review_reservations": [
            {
                "reservation_id": _prior_id("RSV-", 7000, scenario.ordinal),
                "article_id": scenario.article_id,
                "metric_key": scenario.metric_key,
                "slot_id": historic_slot_id,
                "reviewer_id": "U-SATO",
                "minutes": 60,
                "approval_id": scenario.approval_id,
                "purpose": "Historical seed review",
                "status": "COMPLETED",
                "created_by": "research_analyst",
                "created_at": "2026-06-20T09:00:00",
                "revision": 1,
            }
        ],
    }


def build_assets(scenario: Scenario) -> list[dict[str, Any]]:
    case = scenario.case_reference
    assets: list[dict[str, Any]] = [
        asset(
            "policy/research-evidence-policy.md",
            kind="policy",
            title="Research evidence and publication policy v6 (effective)",
            source="drive",
            media_type=MARKDOWN,
            content=scoped_markdown(
                CURRENT_POLICY, task_id=scenario.task_id, case_reference=case
            ),
            preview="Current definition, source, authority, review, and readback controls.",
        ),
        asset(
            "policy/superseded-research-policy-2025.md",
            kind="policy_superseded",
            title="Research publication policy 2025 (superseded)",
            source="drive",
            media_type=MARKDOWN,
            content=scoped_markdown(
                SUPERSEDED_POLICY, task_id=scenario.task_id, case_reference=case
            ),
            preview="Retired search-rank rule retained only as conflicting evidence.",
        ),
        asset(
            f"knowledge/article-{scenario.article_id}.json",
            kind="knowledge_article",
            title=f"Knowledge article — {scenario.article_title}",
            source="knowledge_export",
            media_type=JSON,
            content=json.dumps(
                {
                    "article_id": scenario.article_id,
                    "slug": scenario.article_slug,
                    "title": scenario.article_title,
                    "status": "ACTIVE",
                    "current_revision": scenario.current_revision,
                    "current_revision_id": scenario.current_revision_id,
                    "case_reference": case,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            preview="Active article identity and current revision pointer.",
        ),
        asset(
            "knowledge/revision-history.csv",
            kind="revision_history",
            title=f"Revision history — {scenario.article_title}",
            source="knowledge_export",
            media_type=CSV,
            content=scoped_csv(
                "revision_id,revision,effective_from,status,definition_id\n"
                + f"{scenario.current_revision_id},{scenario.current_revision},2026-07-01,CURRENT,{scenario.current_definition}\n"
                + f"{scenario.stale_revision_id},{scenario.stale_revision},2025-07-01,SUPERSEDED,{scenario.stale_definition}\n",
                task_id=scenario.task_id,
                case_reference=case,
            ),
            preview="Current and superseded article revisions by immutable id.",
        ),
        asset(
            f"metrics/definition-{scenario.current_definition}.yaml",
            kind="metric_definition",
            title=f"Current definition — {scenario.metric_name}",
            source="metrics_registry",
            media_type=YAML,
            content=yaml_lines(
                {
                    "case_reference": case,
                    "definition_id": scenario.current_definition,
                    "metric_key": scenario.metric_key,
                    "unit": scenario.unit,
                    "numerator": scenario.definition_numerator,
                    "denominator": scenario.definition_denominator,
                    "exclusions": scenario.definition_exclusions,
                    "status": "CURRENT",
                }
            )
            + "\n",
            preview="Operative numerator, denominator, unit, and exclusions.",
        ),
        asset(
            f"metrics/snapshot-{scenario.snapshot_id}.xlsx",
            kind="metric_snapshot",
            title=f"Controlled metric snapshot — {scenario.period_start} to {scenario.period_end}",
            source="metrics_export",
            media_type=XLSX,
            rows=[
                [
                    "task_id",
                    "case_reference",
                    "snapshot_id",
                    "metric_key",
                    "period_start",
                    "period_end",
                    "definition_id",
                    "gross_value",
                    "excluded_value",
                    "supported_value",
                    "unit",
                    "source_set_id",
                ],
                [
                    scenario.task_id,
                    case,
                    scenario.snapshot_id,
                    scenario.metric_key,
                    scenario.period_start,
                    scenario.period_end,
                    scenario.current_definition,
                    scenario.numbers["observed"],
                    scenario.numbers["excluded"],
                    scenario.numbers["eligible"],
                    scenario.unit,
                    scenario.source_set_id,
                ],
            ],
            preview="Gross, excluded, and supported values for the controlled period.",
        ),
        asset(
            "sources/source-register.csv",
            kind="source_register",
            title=f"Source register — {scenario.source_set_id}",
            source="source_registry",
            media_type=CSV,
            content=scoped_csv(
                "source_id,source_type,source_name,value,unit,status,reliability,note\n"
                + "".join(
                    f"{source.source_id},{source.source_type},{source.source_name},{source.value},{scenario.unit},{source.status},{source.reliability},{source.note}\n"
                    for source in scenario.sources
                ),
                task_id=scenario.task_id,
                case_reference=case,
            ),
            preview="Independent current records plus the stale conflicting headline.",
        ),
        asset(
            "search/index-results.json",
            kind="search_results",
            title=f"Search results — {scenario.query_key}",
            source="search_export",
            media_type=JSON,
            content=json.dumps(
                {
                    "case_reference": case,
                    "index_id": "IDX-KNOWLEDGE-CURRENT",
                    "query_key": scenario.query_key,
                    "warning": "rank is not authority",
                    "hits": [
                        {
                            "rank": 1,
                            "article_id": scenario.article_id,
                            "revision": scenario.current_revision,
                            "status": "CURRENT",
                        },
                        {
                            "rank": 2,
                            "article_id": f"{scenario.article_id}-ARCHIVE",
                            "revision": scenario.stale_revision,
                            "status": "SUPERSEDED",
                        },
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            preview="A current hit and a deceptively relevant archived hit.",
        ),
        asset(
            "reviews/review-capacity.xlsx",
            kind="review_calendar",
            title=f"Research review capacity — {case}",
            source="reviews_export",
            media_type=XLSX,
            rows=[
                [
                    "slot_id",
                    "review_date",
                    "reviewer_id",
                    "expertise",
                    "duration_minutes",
                    "status",
                    "hold_reason",
                    "task_scope",
                ],
                [
                    scenario.selected_slot_id,
                    scenario.selected_review_date,
                    scenario.selected_reviewer_id,
                    scenario.expertise,
                    max(120, scenario.review_minutes),
                    "free",
                    "",
                    scenario.task_id,
                ],
                [
                    scenario.protected_slot_id,
                    scenario.expedited_readiness,
                    scenario.selected_reviewer_id,
                    scenario.expertise,
                    120,
                    "protected",
                    "regulatory or close assurance work",
                    scenario.task_id,
                ],
                [
                    f"SLOT-RSH-{scenario.ordinal:04d}-GENERAL",
                    scenario.standard_readiness,
                    "U-IBARRA",
                    "general_research",
                    120,
                    "free",
                    "",
                    scenario.task_id,
                ],
            ],
            preview="Qualified, protected, and generalist capacity are separate.",
        ),
        asset(
            f"approvals/approval-{scenario.approval_id}.json",
            kind="approval",
            title=f"Signed research approval {scenario.approval_id}",
            source="approvals_export",
            media_type=JSON,
            content=json.dumps(
                {
                    "approval_id": scenario.approval_id,
                    "case_reference": case,
                    "status": "APPROVED",
                    "approver_id": "U-IBARRA",
                    "valid_until": "2026-07-31",
                    "scope": scenario.approval_scope,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            preview="Exact article, definition, source, value, and capacity authority.",
        ),
        asset(
            f"exports/starting-state-{scenario.task_id}.json",
            kind="starting_state",
            title=f"Research starting state — {case}",
            source="provider_export",
            media_type=JSON,
            content=json.dumps(
                {
                    "task_id": scenario.task_id,
                    "case_reference": case,
                    "article_id": scenario.article_id,
                    "snapshot_id": scenario.snapshot_id,
                    "source_set_id": scenario.source_set_id,
                    "claim_count": 1,
                    "packet_count": 1,
                    "reservation_count": 1,
                    "state": "PRE_ACTION",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            preview="Pre-action domain state; it does not disclose the required outcome.",
        ),
        asset(
            "communications/request.eml",
            kind="email",
            title=scenario.request["subject"],
            source="messages",
            media_type=EML,
            content=eml(
                from_addr=scenario.request["sender"],
                to_addr=scenario.request["recipients"],
                subject=scenario.request["subject"],
                date=scenario.request["sent_at"],
                message_id=f"{scenario.request['message_id']}@meridian.example",
                body=scenario.request["body"],
                attachments=[f"approval-{scenario.approval_id}.json"],
            ),
            preview="Employee request and task-scoped authority pointer.",
        ),
        asset(
            "collaboration/research-thread.json",
            kind="chat_thread",
            title=f"Research thread — {case}",
            source="chat",
            media_type=JSON,
            content=json.dumps(
                {
                    "thread_id": scenario.chat_thread_id,
                    "case_reference": case,
                    "messages": [
                        {"author": author, "ts": ts, "text": text}
                        for author, ts, text in scenario.chat_messages
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            preview="Definition, source, and capacity corrections from the research team.",
        ),
    ]
    for doc in scenario.docs:
        assets.append(
            asset(
                doc.path,
                kind=doc.kind,
                title=doc.title,
                source="drive",
                media_type=doc.media_type,
                content=doc.content,
                rows=[list(row) for row in doc.rows] if doc.rows else None,
                preview=doc.title,
            )
        )
    assets.extend(
        quality_support_assets(
            task_id=scenario.task_id,
            ordinal=scenario.ordinal,
            case_reference=case,
            family_slug=FAMILY_SLUG,
            family_name="ResearchDesk",
            organization_name=ORGANIZATION["name"],
            subject_id=scenario.article_id,
            as_of=AS_OF,
            current_revision=scenario.current_revision,
            anchors=OPEN_SOURCE_ANCHORS,
        )
    )
    index = {
        "task_id": scenario.task_id,
        "case_reference": case,
        "as_of": AS_OF,
        "files": [
            {
                "path": record["path"],
                "kind": record["kind"],
                "media_type": record["media_type"],
                "sha256": record["sha256"],
            }
            for record in assets
        ],
    }
    assets.append(
        asset(
            "audit/evidence-index.yaml",
            kind="evidence_index",
            title=f"Evidence index — {case}",
            source="drive",
            media_type=YAML,
            content=yaml_lines(index) + "\n",
            preview="Digest index of every agent-visible evidence file.",
        )
    )
    for position, record in enumerate(assets, start=1):
        record["asset_id"] = f"{scenario.task_id}-{position:02d}"
    return assets


def _folder(scenario: Scenario, record: dict[str, Any]) -> str:
    if record["kind"] == "policy":
        return "Strategy & Research/Policies"
    if "superseded" in record["kind"]:
        return "Strategy & Research/Policies/Archive"
    return CASE_FOLDER.format(case=scenario.case_reference)


def mount_drive(
    scenario: Scenario, assets: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    files: list[dict[str, Any]] = []
    ids: dict[str, str] = {}
    counter = 0
    for record in assets:
        if record["media_type"] == EML or record["kind"] == "chat_thread":
            continue
        counter += 1
        file_id = f"DRV-RSH-{scenario.ordinal:03d}-{counter:02d}"
        files.append(
            {
                "file_id": file_id,
                "name": record["path"].rsplit("/", 1)[-1],
                "mime_type": record["media_type"],
                "modified_time": "2026-07-12T18:00:00",
                "folder": _folder(scenario, record),
                "content": record["content"],
                "sha256": record["sha256"],
            }
        )
        ids[record["path"]] = file_id
    return files, ids


def _investigation(
    number: int,
    milestone: str,
    description: str,
    tool: str,
    arguments: dict[str, Any],
    expected: dict[str, Any],
    weight: float = 1.0,
) -> dict[str, Any]:
    return {
        "id": f"investigation_{number:02d}",
        "milestone_id": milestone,
        "description": description,
        "weight": weight,
        "before_primary_mutation": True,
        "any_of": [
            {
                "tool": tool,
                "arguments": arguments,
                "match": "result_contains",
                "expected_result_contains": expected,
            }
        ],
    }


def build_investigations(
    scenario: Scenario, file_ids: dict[str, str]
) -> list[dict[str, Any]]:
    case = scenario.case_reference
    article_file = file_ids[f"knowledge/article-{scenario.article_id}.json"]
    approval_file = file_ids[f"approvals/approval-{scenario.approval_id}.json"]
    policy_file = file_ids["policy/research-evidence-policy.md"]
    stale_source = next(
        source for source in scenario.sources if source.status != "VERIFIED"
    )
    investigations = [
        _investigation(
            1,
            "investigation.scope",
            f"Established the isolated {case} world, immutable article identity, mounted systems, and evidence index before researching {scenario.article_id}.",
            CONTEXT_TOOL,
            {},
            {"reference_records": {"case_reference": case}},
        ),
        _investigation(
            2,
            "investigation.scope",
            f"Located the task-scoped request for {case} through mailbox search rather than guessing a sender or subject.",
            "messages.list",
            {"q": case},
            {"messages": [{"id": scenario.request["message_id"]}]},
        ),
        _investigation(
            3,
            "investigation.scope",
            f"Resolved {scenario.article_title} to active article {scenario.article_id}, separate from the archived same-topic result.",
            "knowledge.articles.search",
            {"q": scenario.article_slug},
            {"articles": [{"article_id": scenario.article_id, "status": "ACTIVE"}]},
        ),
        _investigation(
            4,
            "investigation.scope",
            f"Listed the {case} evidence folder and identified the article and approval exports by immutable file id.",
            "drive.files.list",
            {"q": case},
            {"files": [{"id": article_file}, {"id": approval_file}]},
        ),
        _investigation(
            5,
            "investigation.requirements",
            "Located the effective research evidence policy and distinguished it from the superseded search-rank rule.",
            "drive.files.list",
            {"q": "Research evidence and publication policy"},
            {"files": [{"id": policy_file}]},
        ),
        _investigation(
            6,
            "investigation.requirements",
            f"Read active article {scenario.article_id} and fixed its current revision pointer at {scenario.current_revision}.",
            "knowledge.articles.get",
            {"article_id": scenario.article_id},
            {
                "article_id": scenario.article_id,
                "current_revision": scenario.current_revision,
                "status": "ACTIVE",
            },
        ),
        _investigation(
            7,
            "investigation.requirements",
            f"Read the full revision history and separated CURRENT {scenario.current_revision_id} from SUPERSEDED {scenario.stale_revision_id}.",
            "knowledge.revisions.list",
            {"article_id": scenario.article_id},
            {
                "revisions": [
                    {"revision_id": scenario.current_revision_id, "status": "CURRENT"},
                    {"revision_id": scenario.stale_revision_id, "status": "SUPERSEDED"},
                ]
            },
        ),
        _investigation(
            8,
            "investigation.requirements",
            f"Read current definition {scenario.current_definition}: numerator, denominator, unit, exclusions, and effective status.",
            "metrics.definitions.get",
            {"definition_id": scenario.current_definition},
            {
                "definition_id": scenario.current_definition,
                "metric_key": scenario.metric_key,
                "status": "CURRENT",
            },
        ),
        _investigation(
            9,
            "investigation.requirements",
            f"Listed definition history for {scenario.metric_key} and confirmed that {scenario.stale_definition} is superseded.",
            "metrics.definitions.list",
            {"metric_key": scenario.metric_key},
            {
                "definitions": [
                    {"definition_id": scenario.stale_definition, "status": "SUPERSEDED"}
                ]
            },
        ),
        _investigation(
            10,
            "investigation.constraints",
            f"Read controlled snapshot {scenario.snapshot_id} and reconciled gross, excluded, and supported {scenario.unit} values for the exact period.",
            "metrics.snapshots.get",
            {"snapshot_id": scenario.snapshot_id},
            {
                "snapshot_id": scenario.snapshot_id,
                "gross_value": scenario.numbers["observed"],
                "excluded_value": scenario.numbers["excluded"],
                "supported_value": scenario.numbers["eligible"],
            },
        ),
        _investigation(
            11,
            "investigation.constraints",
            f"Read source-set contract {scenario.source_set_id} and its independent verification threshold.",
            "sources.sets.get",
            {"source_set_id": scenario.source_set_id},
            {
                "source_set_id": scenario.source_set_id,
                "required_sources": 3,
                "verified_count": 3,
            },
        ),
        _investigation(
            12,
            "investigation.constraints",
            f"Listed every record in {scenario.source_set_id}, retaining the verified records and explicitly separating stale material.",
            "sources.records.list",
            {"source_set_id": scenario.source_set_id},
            {
                "records": [
                    {"source_id": scenario.sources[0].source_id, "status": "VERIFIED"},
                    {"source_id": stale_source.source_id, "status": "SUPERSEDED"},
                ]
            },
        ),
        _investigation(
            13,
            "investigation.constraints",
            f"Read stale source {stale_source.source_id} and confirmed why its tempting headline cannot support the current decision.",
            "sources.records.get",
            {"source_id": stale_source.source_id},
            {
                "source_id": stale_source.source_id,
                "status": "SUPERSEDED",
                "reliability": "STALE",
            },
        ),
        _investigation(
            14,
            "investigation.constraints",
            f"Queried the current index for {scenario.query_key}, using rank only for discovery and checking each hit's status and source identity.",
            "search.query",
            {"index_id": "IDX-KNOWLEDGE-CURRENT", "query_key": scenario.query_key},
            {
                "hits": [
                    {"article_id": scenario.article_id, "status": "CURRENT"},
                    {
                        "article_id": f"{scenario.article_id}-ARCHIVE",
                        "status": "SUPERSEDED",
                    },
                ]
            },
        ),
        _investigation(
            15,
            "investigation.constraints",
            f"Read review capacity through {scenario.business_need}, separating qualified {scenario.selected_slot_id} from protected {scenario.protected_slot_id} and the generalist opening.",
            "reviews.slots.list",
            {"start_date": AS_OF, "end_date": scenario.business_need},
            {
                "slots": [
                    {
                        "slot_id": scenario.selected_slot_id,
                        "status": "free",
                        "expertise": scenario.expertise,
                    },
                    {"slot_id": scenario.protected_slot_id, "status": "protected"},
                ]
            },
        ),
        _investigation(
            16,
            "investigation.authority",
            f"Read approval {scenario.approval_id} and fixed its exact action, article, metric, definition, source, value, and slot boundaries.",
            "approvals.get",
            {"approval_id": scenario.approval_id},
            {
                "approval_id": scenario.approval_id,
                "status": "APPROVED",
                "scope": {
                    "article_id": scenario.article_id,
                    "metric_key": scenario.metric_key,
                },
            },
        ),
        _investigation(
            17,
            "investigation.erp_correlation",
            f"Read request {scenario.request['message_id']} for the documented business date and draft-only communication constraint.",
            "messages.get",
            {"message_id": scenario.request["message_id"]},
            {
                "id": scenario.request["message_id"],
                "subject": scenario.request["subject"],
            },
        ),
        _investigation(
            18,
            "investigation.erp_correlation",
            f"Read research thread {scenario.chat_thread_id} for the current-definition, source-status, and protected-capacity corrections.",
            "chat.threads.get",
            {"thread_id": scenario.chat_thread_id},
            {"thread_id": scenario.chat_thread_id},
        ),
    ]
    investigations.extend(
        quality_support_investigations(
            start_number=len(investigations) + 1,
            file_ids=file_ids,
            make_investigation=_investigation,
            case_reference=case,
            subject_id=scenario.article_id,
        )
    )
    return investigations


def build_oracle_steps(
    scenario: Scenario, investigations: list[dict[str, Any]], model: dict[str, Any]
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [
        {"phase": "context", "tool": CONTEXT_TOOL, "arguments": {}, "control": True}
    ]
    mode_order = {
        "quantity": [2, 3, 6, 7, 8, 9, 10, 11, 12, 13, 14, 5, 4, 16, 15, 17, 18],
        "plan": [2, 14, 3, 6, 7, 8, 11, 12, 13, 10, 9, 5, 4, 16, 15, 17, 18],
        "schedule": [2, 15, 3, 6, 7, 8, 10, 11, 12, 14, 13, 9, 5, 4, 16, 17, 18],
    }
    order = list(mode_order[scenario.mode])
    by_number = {int(item["id"].rsplit("_", 1)[1]): item for item in investigations}
    order.extend(number for number in sorted(by_number) if number not in order)
    for number in order:
        call = by_number[number]["any_of"][0]
        steps.append(
            {
                "phase": "investigation",
                "tool": call["tool"],
                "arguments": call["arguments"],
                "control": True,
            }
        )
    primary = scenario.primary_write
    steps.append(
        {
            "phase": "primary_mutation",
            "tool": primary.tool,
            "arguments": primary.arguments,
            "control": False,
        }
    )
    steps.append(
        {
            "phase": "post_write_verification",
            "tool": primary.readback_tool,
            "arguments": primary.readback_arguments,
            "control": True,
        }
    )
    steps.append(
        {
            "phase": "collaboration",
            "tool": "notes.drafts.create",
            "arguments": {
                "recipient": scenario.collaboration["recipient"],
                "subject": scenario.collaboration["subject"],
                "body": scenario.collaboration["body"],
                "related_article_id": scenario.article_id,
                "related_case": scenario.case_reference,
            },
            "control": False,
        }
    )
    steps.append(
        {
            "phase": "answer",
            "tool": SUBMIT_TOOL,
            "arguments": dict(model["answer"]),
            "control": False,
        }
    )
    return steps


def build_assertions(scenario: Scenario, model: dict[str, Any]) -> list[dict[str, Any]]:
    primary = scenario.primary_write
    selected = model["selected_option"]
    completion = model["selected_completion"]
    return [
        {
            "id": "mutation_01",
            "milestone_id": "state.primary",
            "description": f"Required {scenario.article_id} to reach {primary.outcome_label!r} through {primary.tool} with the exact current definition, source set, approval, and provider-critical values.",
            "table": "mutations",
            "where": {
                "task_id": scenario.task_id,
                "mutation_id": f"{scenario.task_id}-mutation-01",
            },
            "values": {
                "tool": primary.tool,
                "table_name": primary.table,
                "record_id": primary.record_id,
                "status": primary.status,
            },
            "payload_contains": {"tool": primary.tool, "arguments": primary.arguments},
            "payload_allowed_argument_paths": list(primary.allowed_paths),
            "weight": 3.0,
        },
        {
            "id": "state_01",
            "milestone_id": "state.primary",
            "description": f"Persisted {primary.record_id} in {primary.table} with the supported values so a later reader observes the outcome.",
            "table": primary.table,
            "where": {primary.primary_key: primary.record_id},
            "values": dict(primary.domain_values),
            "weight": 2.0,
        },
        *[dict(item) for item in primary.extra_assertions],
        {
            "id": "mutation_02",
            "milestone_id": "state.collaboration",
            "description": f"Created, but did not send, the stakeholder draft carrying {selected}, the {completion} outcome, the current definition, and {scenario.case_reference}.",
            "table": "mutations",
            "where": {
                "task_id": scenario.task_id,
                "mutation_id": f"{scenario.task_id}-mutation-02",
            },
            "values": {
                "tool": "notes.drafts.create",
                "table_name": "note_drafts",
                "status": "DRAFT",
            },
            "payload_contains": {
                "tool": "notes.drafts.create",
                "arguments": {"recipient": scenario.collaboration["recipient"]},
            },
            "payload_text_contains": [
                selected,
                completion,
                scenario.current_definition,
            ],
            "payload_text_any_of": [[scenario.case_reference, scenario.article_id]],
            "weight": 1.5,
        },
        {
            "id": "containment_01",
            "milestone_id": "containment.scope",
            "description": f"Made exactly two state changes for {scenario.case_reference}: the supported primary outcome and one stakeholder draft.",
            "table": "mutations",
            "where": {"task_id": scenario.task_id},
            "count": 2,
            "weight": 1.0,
        },
    ]


@fact_text_contract
def build_task(scenario: Scenario) -> dict[str, Any]:
    verify_numbers(scenario)
    assets = build_assets(scenario)
    drive_files, file_ids = mount_drive(scenario, assets)
    evidence = [
        {
            "asset_id": record["asset_id"],
            "task_id": scenario.task_id,
            "path": record["path"],
            "title": record["title"],
            "kind": record["kind"],
            "source": record["source"],
            "media_type": record["media_type"],
            "sha256": record["sha256"],
        }
        for record in assets
    ]
    model = build_model(scenario)
    investigations = build_investigations(scenario, file_ids)
    steps = build_oracle_steps(scenario, investigations, model)
    assertions = build_assertions(scenario, model)
    primary = scenario.primary_write
    readback = {
        "id": "verify_primary_state",
        "milestone_id": "verification.readback",
        "after_tool": primary.tool,
        "any_of": [
            {
                "tool": primary.readback_tool,
                "arguments": primary.readback_arguments,
                "match": "result_contains",
                "expected_result_contains": primary.readback_expected,
            }
        ],
        "expected_result_contains": primary.readback_expected,
        "target_identity": primary.readback_arguments,
        "materializes_new_record": True,
        "description": f"Read {primary.record_id} back through {primary.readback_tool} and confirmed the exact persisted outcome rather than trusting the write acknowledgement.",
        "weight": 2.0,
    }
    answer = model["answer"]
    checks = answer_checks(
        answer,
        [
            "recommended_option",
            "recommended_outcome_date",
            ITEM_FIELD[scenario.mode],
            GAP_FIELD[scenario.mode],
            "decision_timing_status",
        ],
        f"{scenario.article_id}, definition {scenario.current_definition}, source set {scenario.source_set_id}, and option {model['selected_option']}",
    )
    descriptions = milestone_descriptions(
        case_reference=scenario.case_reference,
        record=scenario.article_id,
        revision=scenario.current_revision,
        subject=scenario.article_title,
        selected_option=model["selected_option"],
        selected_completion=model["selected_completion"],
        facts=model["facts"],
        primary_outcome=primary.outcome_label,
        correlated_systems=[
            "knowledge",
            "metrics",
            "sources",
            "search",
            "reviews",
            "approvals",
            "messages",
            "chat",
        ],
    )
    rubric = build_rubric_milestones(
        descriptions=descriptions,
        investigations=investigations,
        calculations=model["calculations"],
        assertions=assertions,
        answer_checks=checks,
        post_write_verifications=[readback],
    )
    option_ids = [option["id"] for option in model["options"]]
    return {
        "task_id": scenario.task_id,
        "benchmark": BENCHMARK,
        "family": FAMILY_SLUG,
        "benchmark_version": FAMILY_VERSION,
        "mode": scenario.mode,
        "level": "employee-decision",
        "title": scenario.title,
        "role": scenario.role,
        "instruction": scenario.instruction,
        "as_of": AS_OF,
        "world": dict(ORGANIZATION),
        "seed_tables": seed_tables(scenario, drive_files, evidence),
        "assets": assets,
        "decision_model": {
            key: value
            for key, value in model.items()
            if key not in {"answer", "answer_descriptions"}
        },
        "answer_schema": answer_schema(
            answer, model["answer_descriptions"], option_ids
        ),
        "expected": {
            "answer": answer,
            "answer_checks": checks,
            "calculations": model["calculations"],
            "assertions": assertions,
            "investigations": investigations,
            "post_write_verifications": [readback],
        },
        "required_investigations": investigations,
        "required_reads": [
            step["tool"]
            for step in steps
            if step["control"] and step["phase"] in {"context", "investigation"}
        ],
        "required_read_calls": [item["any_of"][0] for item in investigations],
        "post_write_verifications": [readback],
        "oracle_steps": steps,
        "sequence_signature": sequence_signature(steps),
        "allowed_write_tables": sorted(
            {
                primary.table,
                *primary.extra_tables,
                "note_drafts",
                "mutations",
                "answers",
                "audit_log",
            }
        ),
        "rubric_milestones": rubric,
        "negative_controls": {
            "unauthorized_write": dict(scenario.unauthorized_write),
            "wrong_evidence": {
                "tool": "drive.files.export",
                "arguments": {
                    "file_id": file_ids["policy/superseded-research-policy-2025.md"]
                },
            },
        },
        "reference_records": {
            "case_reference": scenario.case_reference,
            "knowledge": {
                "article_id": scenario.article_id,
                "article_search": {
                    "tool": "knowledge.articles.search",
                    "arguments": {"q": scenario.article_slug},
                },
            },
            "metrics": {
                "definition_id": scenario.current_definition,
                "snapshot_id": scenario.snapshot_id,
            },
            "sources": {
                "source_set_id": scenario.source_set_id,
                "source_ids": [source.source_id for source in scenario.sources],
            },
            "search": {
                "index_id": "IDX-KNOWLEDGE-CURRENT",
                "query_key": scenario.query_key,
            },
            "reviews": {
                "selected_slot_id": scenario.selected_slot_id,
                "protected_slot_id": scenario.protected_slot_id,
            },
            "approvals": {"approval_id": scenario.approval_id},
            "messages": {
                "search_query": scenario.case_reference,
                "message_id": scenario.request["message_id"],
            },
            "drive": {
                "case_folder_query": scenario.case_reference,
                "policy_query": "Research evidence and publication policy",
            },
            "chat": {"thread_id": scenario.chat_thread_id},
        },
        "starting_records": [
            {
                "system": "knowledge",
                "resource_type": "Article",
                "resource_id": scenario.article_id,
                "status": "ACTIVE",
            },
            {
                "system": "metrics",
                "resource_type": "MetricSnapshot",
                "resource_id": scenario.snapshot_id,
                "status": "PUBLISHED",
            },
            {
                "system": "sources",
                "resource_type": "SourceSet",
                "resource_id": scenario.source_set_id,
                "status": "CURRENT",
            },
            {
                "system": "reviews",
                "resource_type": "ReviewSlot",
                "resource_id": scenario.selected_slot_id,
                "status": "free",
            },
        ],
        "evaluation": {
            "metric": "HubScore",
            "strict_pass": "every rubric milestone passes",
            "llm_judge_calls": 0,
        },
        "workflow": {
            "reads": len(
                [
                    step
                    for step in steps
                    if step["phase"] in {"context", "investigation"}
                ]
            ),
            "writes": 2,
            "readbacks": 1,
            "answer_fields": len(answer),
        },
    }


def build_tasks() -> list[dict[str, Any]]:
    return [build_task(scenario) for scenario in scenarios()]


__all__ = [
    "BENCHMARK",
    "FAMILY_SLUG",
    "FAMILY_VERSION",
    "build_task",
    "build_tasks",
    "verify_numbers",
]
