"""DesignOps: the HubBench manufacturing-engineering-design family (PLM + CAD metadata + ECO + BOM mock)."""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .build import FAMILY_SLUG, FAMILY_VERSION, build_tasks
from .specs import AS_OF, ORGANIZATION
from .tools import SERVERS, TOOLS

FAMILY = Family(
    slug=FAMILY_SLUG,
    name="DesignOps",
    version=FAMILY_VERSION,
    cluster="manufacturing-engineering-design",
    description="Engineering-change release decisions against a PLM with part revisions and CAD check-in history, change orders with affected items, a multi-level BOM, a certification register, a tooling register with calibration state, supplier-portal quotes, a production release calendar, and approval records.",
    schema_sql=(Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=build_tasks,
    organization=ORGANIZATION,
    as_of=AS_OF,
)

__all__ = ["FAMILY"]
