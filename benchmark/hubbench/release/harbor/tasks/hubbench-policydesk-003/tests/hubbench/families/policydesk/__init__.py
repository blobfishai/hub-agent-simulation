"""PolicyDesk: vendored HubBench runtime family (provider-shaped tools + schema only).

Emitted by ``hubbench.engine.distribution`` for the distributed task package.  It
carries no task builder, no scenario data, no oracle policy, and no verifier
contract: the task world is loaded from the package's task.json.
"""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .tools import SERVERS, TOOLS


def _no_task_builder() -> list:
    raise RuntimeError("the distributed policydesk runtime does not build tasks; load the task from task.json")


FAMILY = Family(
    slug='policydesk',
    name='PolicyDesk',
    version='1.0.1',
    cluster='policy-compliance-instruction-following',
    description='Access-governance decisions against a policy library with numbered clauses, an access-request queue, an entitlement store with segregation-of-duties rules, an exceptions register, an approver directory with authority tiers, training records, an audit-finding tracker, an approver review calendar, and an external screening vendor.',
    schema_sql=Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=_no_task_builder,
    organization={'id': 'meridian-access-governance-v1', 'name': 'Meridian Grid Utilities — Access Governance', 'organization_id': 'ORG-MERIDIAN', 'primary_site': 'IAM-DESK', 'systems': ['policy', 'requests', 'resources', 'grants', 'exceptions', 'directory', 'training', 'audit', 'screening', 'reviews', 'approvals', 'messages', 'chat', 'drive', 'notes']},
    as_of='2026-05-11',
)

__all__ = ["FAMILY"]
