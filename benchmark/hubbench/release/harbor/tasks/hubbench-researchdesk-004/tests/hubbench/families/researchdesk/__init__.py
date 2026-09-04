"""ResearchDesk: vendored HubBench runtime family (provider-shaped tools + schema only).

Emitted by ``hubbench.engine.distribution`` for the distributed task package.  It
carries no task builder, no scenario data, no oracle policy, and no verifier
contract: the task world is loaded from the package's task.json.
"""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .tools import SERVERS, TOOLS


def _no_task_builder() -> list:
    raise RuntimeError("the distributed researchdesk runtime does not build tasks; load the task from task.json")


FAMILY = Family(
    slug='researchdesk',
    name='ResearchDesk',
    version='1.0.1',
    cluster='reasoning-knowledge-qa',
    description='Multi-source internal research across versioned knowledge, metric definitions, source provenance, ranked search, approvals, review capacity, published claims, and evidence packets.',
    schema_sql=Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=_no_task_builder,
    organization={'id': 'meridian-researchdesk-v1', 'name': 'Meridian Works — Strategy & Research', 'organization_id': 'ORG-MERIDIAN', 'primary_site': 'KNOWLEDGE-HQ', 'systems': ['knowledge', 'metrics', 'sources', 'search', 'reviews', 'research', 'approvals', 'messages', 'chat', 'drive', 'notes']},
    as_of='2026-07-13',
)

__all__ = ["FAMILY"]
