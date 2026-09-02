"""SciLab: vendored HubBench runtime family (provider-shaped tools + schema only).

Emitted by ``hubbench.engine.distribution`` for the distributed task package.  It
carries no task builder, no scenario data, no oracle policy, and no verifier
contract: the task world is loaded from the package's task.json.
"""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .tools import SERVERS, TOOLS


def _no_task_builder() -> list:
    raise RuntimeError("the distributed scilab runtime does not build tasks; load the task from task.json")


FAMILY = Family(
    slug='scilab',
    name='SciLab',
    version='1.0.0',
    cluster='scientific-research',
    description='Assay-operations decisions against a LIMS with versioned protocols and QC results, an analyser schedule with calibration certificates, a reagent-lot inventory with expiry and quarantine state, supplier shipment confirmations, ELN method notes, and approval records.',
    schema_sql=Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=_no_task_builder,
    organization={'id': 'corvane-assay-ops-v1', 'name': 'Corvane Institute — Assay Operations Core', 'organization_id': 'ORG-CORVANE', 'primary_site': 'SITE-MAIN', 'systems': ['lims', 'instruments', 'inventory', 'supplier', 'eln', 'approvals', 'messages', 'chat', 'drive', 'notes']},
    as_of='2026-05-11',
)

__all__ = ["FAMILY"]
