"""HostOps: vendored HubBench runtime family (provider-shaped tools + schema only).

Emitted by ``hubbench.engine.distribution`` for the distributed task package.  It
carries no task builder, no scenario data, no oracle policy, and no verifier
contract: the task world is loaded from the package's task.json.
"""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .tools import SERVERS, TOOLS


def _no_task_builder() -> list:
    raise RuntimeError("the distributed hostops runtime does not build tasks; load the task from task.json")


FAMILY = Family(
    slug='hostops',
    name='HostOps',
    version='1.0.0',
    cluster='terminal-operations',
    description='Host-operations recovery decisions against a Linux service inventory, cron/CI scheduler, backup catalog with retention and vendor retrievals, release build farm, and approval records.',
    schema_sql=Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=_no_task_builder,
    organization={'id': 'ridgeline-platform-v1', 'name': 'Ridgeline Systems — Platform Operations', 'organization_id': 'ORG-RIDGELINE', 'primary_site': 'STORE-NEAR', 'systems': ['cmdb', 'releases', 'jobs', 'backup', 'buildfarm', 'vendor', 'approvals', 'messages', 'chat', 'drive', 'notes']},
    as_of='2026-04-13',
)

__all__ = ["FAMILY"]
