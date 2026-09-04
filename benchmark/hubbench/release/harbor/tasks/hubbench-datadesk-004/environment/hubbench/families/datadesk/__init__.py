"""DataDesk: vendored HubBench runtime family (provider-shaped tools + schema only).

Emitted by ``hubbench.engine.distribution`` for the distributed task package.  It
carries no task builder, no scenario data, no oracle policy, and no verifier
contract: the task world is loaded from the package's task.json.
"""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .tools import SERVERS, TOOLS


def _no_task_builder() -> list:
    raise RuntimeError("the distributed datadesk runtime does not build tasks; load the task from task.json")


FAMILY = Family(
    slug='datadesk',
    name='DataDesk',
    version='1.0.1',
    cluster='data-engineering-analytics',
    description='Data engineering decisions against a dbt-style warehouse catalog, pipeline run history, vendor feed deliveries, freshness SLAs, batch-window capacity, and finance reconciliation controls.',
    schema_sql=Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=_no_task_builder,
    organization={'id': 'tidewater-dataplatform-v1', 'name': 'Tidewater Supply Co. — Data Platform', 'organization_id': 'ORG-TIDEWATER', 'primary_site': 'WH-PROD', 'systems': ['warehouse', 'pipelines', 'feeds', 'recon', 'approvals', 'messages', 'chat', 'drive', 'notes']},
    as_of='2026-03-09',
)

__all__ = ["FAMILY"]
