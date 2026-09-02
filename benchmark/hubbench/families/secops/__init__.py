"""SecOps: the HubBench security family (SIEM + EDR + IAM + key registry + ticketing + on-call mock; defensive operations only)."""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .build import FAMILY_SLUG, FAMILY_VERSION, build_tasks
from .specs import AS_OF, ORGANIZATION
from .tools import SERVERS, TOOLS

FAMILY = Family(
    slug=FAMILY_SLUG,
    name="SecOps",
    version=FAMILY_VERSION,
    cluster="security",
    description="Defensive credential-compromise triage and containment decisions against a SIEM with versioned detection rules, an EDR host inventory, an IAM identity register with sessions, factors, and credential-object grants, a cloud key registry, a security ticket queue, containment-tier playbooks, a responder on-call calendar, identity-provider vendor invalidation confirmations, and approval records.",
    schema_sql=(Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=build_tasks,
    organization=ORGANIZATION,
    as_of=AS_OF,
)

__all__ = ["FAMILY"]
