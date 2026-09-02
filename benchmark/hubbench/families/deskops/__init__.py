"""DeskOps: the HubBench computer-use-gui family (mail + calendar + docs + sheets + drive + venue portal + travel desk + budget mock, as APIs not pixels)."""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .build import FAMILY_SLUG, FAMILY_VERSION, build_tasks
from .specs import AS_OF, ORGANIZATION
from .tools import SERVERS, TOOLS

FAMILY = Family(
    slug=FAMILY_SLUG,
    name="DeskOps",
    version=FAMILY_VERSION,
    cluster="computer-use-gui",
    description="Offsite-move decisions against a mailbox, a calendar with attendee free/busy, a people directory, agenda documents with revisions, a budget workbook with versions, a shared drive, a venue portal with weekly availability, quotes, and holds, a corporate travel desk with policy versions, bookings, group-ticketing confirmations, and booking changes, a budget system with lines and adjustments, and approval records.",
    schema_sql=(Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=build_tasks,
    organization=ORGANIZATION,
    as_of=AS_OF,
)

__all__ = ["FAMILY"]
