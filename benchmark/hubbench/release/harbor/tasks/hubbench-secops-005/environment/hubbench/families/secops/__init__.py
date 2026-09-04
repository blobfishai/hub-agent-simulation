"""SecOps: vendored HubBench runtime family (provider-shaped tools + schema only).

Emitted by ``hubbench.engine.distribution`` for the distributed task package.  It
carries no task builder, no scenario data, no oracle policy, and no verifier
contract: the task world is loaded from the package's task.json.
"""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .tools import SERVERS, TOOLS


def _no_task_builder() -> list:
    raise RuntimeError("the distributed secops runtime does not build tasks; load the task from task.json")


FAMILY = Family(
    slug='secops',
    name='SecOps',
    version='1.0.1',
    cluster='security',
    description='Defensive credential-compromise triage and containment decisions against a SIEM with versioned detection rules, an EDR host inventory, an IAM identity register with sessions, factors, and credential-object grants, a cloud key registry, a security ticket queue, containment-tier playbooks, a responder on-call calendar, identity-provider vendor invalidation confirmations, and approval records.',
    schema_sql=Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=_no_task_builder,
    organization={'id': 'kestrel-secops-v1', 'name': 'Kestrel Grid Utilities — Security Operations Center', 'organization_id': 'ORG-KESTREL', 'primary_site': 'TENANT-PRIMARY', 'systems': ['siem', 'edr', 'iam', 'cloudiam', 'servicedesk', 'playbooks', 'oncall', 'idpvendor', 'approvals', 'messages', 'chat', 'drive', 'notes']},
    as_of='2026-06-08',
)

__all__ = ["FAMILY"]
