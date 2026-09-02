"""ITSMDesk: vendored HubBench runtime family (provider-shaped tools + schema only).

Emitted by ``hubbench.engine.distribution`` for the distributed task package.  It
carries no task builder, no scenario data, no oracle policy, and no verifier
contract: the task world is loaded from the package's task.json.
"""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .tools import SERVERS, TOOLS


def _no_task_builder() -> list:
    raise RuntimeError("the distributed itsmdesk runtime does not build tasks; load the task from task.json")


FAMILY = Family(
    slug='itsmdesk',
    name='ITSMDesk',
    version='1.0.0',
    cluster='it-operations-observability',
    description='Change-scheduling decisions against a ServiceNow-shaped ITSM (CIs, incidents, problems, change requests, outage notices), Grafana-shaped SLOs and error budgets, a change calendar with lanes and freeze windows, a PagerDuty-shaped on-call plane, vendor patch advisories, and approval records.',
    schema_sql=Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=_no_task_builder,
    organization={'id': 'brightmoor-serviceops-v1', 'name': 'Brightmoor Commerce — Service Operations', 'organization_id': 'ORG-BRIGHTMOOR', 'primary_site': 'DC-HALDEN', 'systems': ['itsm', 'telemetry', 'calendar', 'oncall', 'vendor', 'approvals', 'messages', 'chat', 'drive', 'notes']},
    as_of='2026-04-14',
)

__all__ = ["FAMILY"]
