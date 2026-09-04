"""WebStudio: vendored HubBench runtime family (provider-shaped tools + schema only).

Emitted by ``hubbench.engine.distribution`` for the distributed task package.  It
carries no task builder, no scenario data, no oracle policy, and no verifier
contract: the task world is loaded from the package's task.json.
"""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .tools import SERVERS, TOOLS


def _no_task_builder() -> list:
    raise RuntimeError("the distributed webstudio runtime does not build tasks; load the task from task.json")


FAMILY = Family(
    slug='webstudio',
    name='WebStudio',
    version='1.0.1',
    cluster='web-product-design',
    description='Design-operations release decisions against a headless CMS, a design-token and component registry, a design-file index, an asset library with licence grants and vendor quotes, a release checklist, CDN deploy lanes, and approval records.',
    schema_sql=Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=_no_task_builder,
    organization={'id': 'larkspur-webstudio-v1', 'name': 'Larkspur Commerce — Web Platform Studio', 'organization_id': 'ORG-LARKSPUR', 'primary_site': 'ENV-PROD-WEB', 'systems': ['cms', 'tokens', 'design', 'dam', 'checklist', 'cdn', 'vendors', 'approvals', 'messages', 'chat', 'drive', 'notes']},
    as_of='2026-05-11',
)

__all__ = ["FAMILY"]
