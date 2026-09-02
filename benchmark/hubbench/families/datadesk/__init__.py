"""DataDesk: the HubBench data-engineering-analytics family (warehouse + dbt-style models + pipeline runs)."""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .build import FAMILY_SLUG, FAMILY_VERSION, build_tasks
from .specs import AS_OF, ORGANIZATION
from .tools import SERVERS, TOOLS

FAMILY = Family(
    slug=FAMILY_SLUG,
    name="DataDesk",
    version=FAMILY_VERSION,
    cluster="data-engineering-analytics",
    description="Data engineering decisions against a dbt-style warehouse catalog, pipeline run history, vendor feed deliveries, freshness SLAs, batch-window capacity, and finance reconciliation controls.",
    schema_sql=(Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=build_tasks,
    organization=ORGANIZATION,
    as_of=AS_OF,
)

__all__ = ["FAMILY"]
