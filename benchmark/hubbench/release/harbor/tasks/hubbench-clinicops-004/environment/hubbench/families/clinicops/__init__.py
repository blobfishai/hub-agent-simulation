"""ClinicOps: vendored HubBench runtime family (provider-shaped tools + schema only).

Emitted by ``hubbench.engine.distribution`` for the distributed task package.  It
carries no task builder, no scenario data, no oracle policy, and no verifier
contract: the task world is loaded from the package's task.json.
"""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .tools import SERVERS, TOOLS


def _no_task_builder() -> list:
    raise RuntimeError("the distributed clinicops runtime does not build tasks; load the task from task.json")


FAMILY = Family(
    slug='clinicops',
    name='ClinicOps',
    version='1.0.0',
    cluster='healthcare',
    description='Infusion operations decisions against a FHIR-shaped EHR, chair scheduling, pharmacy inventory, supplier confirmations, and approval records.',
    schema_sql=Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=_no_task_builder,
    organization={'id': 'northlake-infusion-v1', 'name': 'Northlake Health — Infusion Services', 'organization_id': 'ORG-NORTHLAKE', 'primary_site': 'LOC-INF', 'systems': ['ehr', 'pharmacy', 'scheduling', 'supplier', 'approvals', 'messages', 'chat', 'drive', 'notes']},
    as_of='2026-03-09',
)

__all__ = ["FAMILY"]
