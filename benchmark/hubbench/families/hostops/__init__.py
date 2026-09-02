"""HostOps: the HubBench terminal-operations family (Linux host + build + backup mock)."""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .build import FAMILY_SLUG, FAMILY_VERSION, build_tasks
from .specs import AS_OF, ORGANIZATION
from .tools import SERVERS, TOOLS

FAMILY = Family(
    slug=FAMILY_SLUG,
    name="HostOps",
    version=FAMILY_VERSION,
    cluster="terminal-operations",
    description="Host-operations recovery decisions against a Linux service inventory, cron/CI scheduler, backup catalog with retention and vendor retrievals, release build farm, and approval records.",
    schema_sql=(Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=build_tasks,
    organization=ORGANIZATION,
    as_of=AS_OF,
)

__all__ = ["FAMILY"]
