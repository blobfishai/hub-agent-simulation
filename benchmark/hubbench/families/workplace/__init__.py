"""Workplace: the HubBench customer-workplace-agents family (issue tracker + wiki + chat + file share company mock)."""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .build import FAMILY_SLUG, FAMILY_VERSION, build_tasks
from .specs import AS_OF, ORGANIZATION
from .tools import SERVERS, TOOLS

FAMILY = Family(
    slug=FAMILY_SLUG,
    name="Workplace",
    version=FAMILY_VERSION,
    cluster="customer-workplace-agents",
    description="Customer-escalation delivery decisions against a helpdesk with SLA policies, a delivery tracker with sprints and capacity reports, a versioned wiki standard, a staff calendar with leave and on-call, an HRIS skills roster, a contract register with commitments and a credit ledger, counterparty confirmations, and approval records.",
    schema_sql=(Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=build_tasks,
    organization=ORGANIZATION,
    as_of=AS_OF,
)

__all__ = ["FAMILY"]
