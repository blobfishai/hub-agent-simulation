"""DesignOps: vendored HubBench runtime family (provider-shaped tools + schema only).

Emitted by ``hubbench.engine.distribution`` for the distributed task package.  It
carries no task builder, no scenario data, no oracle policy, and no verifier
contract: the task world is loaded from the package's task.json.
"""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .tools import SERVERS, TOOLS


def _no_task_builder() -> list:
    raise RuntimeError("the distributed designops runtime does not build tasks; load the task from task.json")


FAMILY = Family(
    slug='designops',
    name='DesignOps',
    version='1.0.0',
    cluster='manufacturing-engineering-design',
    description='Engineering-change release decisions against a PLM with part revisions and CAD check-in history, change orders with affected items, a multi-level BOM, a certification register, a tooling register with calibration state, supplier-portal quotes, a production release calendar, and approval records.',
    schema_sql=Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=_no_task_builder,
    organization={'id': 'ashgrove-eco-v1', 'name': 'Ashgrove Motion Systems — Engineering Change Office', 'organization_id': 'ORG-ASHGROVE', 'primary_site': 'PLANT-ASH', 'systems': ['plm', 'eco', 'bom', 'cert', 'tooling', 'supplier', 'calendar', 'approvals', 'messages', 'chat', 'drive', 'notes']},
    as_of='2026-05-11',
)

__all__ = ["FAMILY"]
