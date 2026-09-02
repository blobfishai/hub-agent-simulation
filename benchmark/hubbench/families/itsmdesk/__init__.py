"""ITSMDesk: the HubBench IT-operations-and-observability family (ITSM + change calendar + telemetry + on-call mock)."""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .build import FAMILY_SLUG, FAMILY_VERSION, build_tasks
from .specs import AS_OF, ORGANIZATION
from .tools import SERVERS, TOOLS

FAMILY = Family(
    slug=FAMILY_SLUG,
    name="ITSMDesk",
    version=FAMILY_VERSION,
    cluster="it-operations-observability",
    description="Change-scheduling decisions against a ServiceNow-shaped ITSM (CIs, incidents, problems, change requests, outage notices), Grafana-shaped SLOs and error budgets, a change calendar with lanes and freeze windows, a PagerDuty-shaped on-call plane, vendor patch advisories, and approval records.",
    schema_sql=(Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=build_tasks,
    organization=ORGANIZATION,
    as_of=AS_OF,
)

__all__ = ["FAMILY"]
