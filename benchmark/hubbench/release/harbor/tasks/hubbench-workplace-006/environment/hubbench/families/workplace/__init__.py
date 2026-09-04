"""Workplace: vendored HubBench runtime family (provider-shaped tools + schema only).

Emitted by ``hubbench.engine.distribution`` for the distributed task package.  It
carries no task builder, no scenario data, no oracle policy, and no verifier
contract: the task world is loaded from the package's task.json.
"""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .tools import SERVERS, TOOLS


def _no_task_builder() -> list:
    raise RuntimeError("the distributed workplace runtime does not build tasks; load the task from task.json")


FAMILY = Family(
    slug='workplace',
    name='Workplace',
    version='1.0.1',
    cluster='customer-workplace-agents',
    description='Customer-escalation delivery decisions against a helpdesk with SLA policies, a delivery tracker with sprints and capacity reports, a versioned wiki standard, a staff calendar with leave and on-call, an HRIS skills roster, a contract register with commitments and a credit ledger, counterparty confirmations, and approval records.',
    schema_sql=Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=_no_task_builder,
    organization={'id': 'ferngate-delivery-v1', 'name': 'Ferngate Software — Customer Delivery', 'organization_id': 'ORG-FERNGATE', 'primary_site': 'Customer Delivery squad', 'systems': ['helpdesk', 'tracker', 'wiki', 'calendar', 'hris', 'contracts', 'portal', 'approvals', 'mail', 'chat', 'drive', 'notes']},
    as_of='2026-04-14',
)

__all__ = ["FAMILY"]
