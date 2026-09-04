"""DeskOps: vendored HubBench runtime family (provider-shaped tools + schema only).

Emitted by ``hubbench.engine.distribution`` for the distributed task package.  It
carries no task builder, no scenario data, no oracle policy, and no verifier
contract: the task world is loaded from the package's task.json.
"""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .tools import SERVERS, TOOLS


def _no_task_builder() -> list:
    raise RuntimeError("the distributed deskops runtime does not build tasks; load the task from task.json")


FAMILY = Family(
    slug='deskops',
    name='DeskOps',
    version='1.0.1',
    cluster='computer-use-gui',
    description='Offsite-move decisions against a mailbox, a calendar with attendee free/busy, a people directory, agenda documents with revisions, a budget workbook with versions, a shared drive, a venue portal with weekly availability, quotes, and holds, a corporate travel desk with policy versions, bookings, group-ticketing confirmations, and booking changes, a budget system with lines and adjustments, and approval records.',
    schema_sql=Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=_no_task_builder,
    organization={'id': 'larkspur-workplace-v1', 'name': 'Larkspur Analytics — Workplace & Events Operations', 'organization_id': 'ORG-LARKSPUR', 'primary_site': 'OFF-BRS', 'systems': ['mail', 'calendar', 'directory', 'docs', 'sheets', 'drive', 'venues', 'travel', 'expense', 'approvals', 'chat', 'notes']},
    as_of='2026-06-08',
)

__all__ = ["FAMILY"]
