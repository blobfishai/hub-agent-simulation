"""ResearchDesk: deep internal-knowledge research with stateful evidence controls."""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .build import FAMILY_SLUG, FAMILY_VERSION, build_tasks
from .specs import AS_OF, ORGANIZATION
from .tools import SERVERS, TOOLS

FAMILY = Family(
    slug=FAMILY_SLUG,
    name="ResearchDesk",
    version=FAMILY_VERSION,
    cluster="reasoning-knowledge-qa",
    description="Multi-source internal research across versioned knowledge, metric definitions, source provenance, ranked search, approvals, review capacity, published claims, and evidence packets.",
    schema_sql=Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=build_tasks,
    organization=ORGANIZATION,
    as_of=AS_OF,
)

__all__ = ["FAMILY"]
