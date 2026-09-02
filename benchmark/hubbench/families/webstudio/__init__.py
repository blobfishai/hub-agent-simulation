"""WebStudio: the HubBench web-product-design family (CMS + design tokens + asset licences + release checklist mock)."""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .build import FAMILY_SLUG, FAMILY_VERSION, build_tasks
from .specs import AS_OF, ORGANIZATION
from .tools import SERVERS, TOOLS

FAMILY = Family(
    slug=FAMILY_SLUG,
    name="WebStudio",
    version=FAMILY_VERSION,
    cluster="web-product-design",
    description="Design-operations release decisions against a headless CMS, a design-token and component registry, a design-file index, an asset library with licence grants and vendor quotes, a release checklist, CDN deploy lanes, and approval records.",
    schema_sql=(Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=build_tasks,
    organization=ORGANIZATION,
    as_of=AS_OF,
)

__all__ = ["FAMILY"]
