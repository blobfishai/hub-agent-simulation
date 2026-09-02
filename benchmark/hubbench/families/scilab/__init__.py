"""SciLab: the HubBench scientific-research family (LIMS + instrument schedule + reagent inventory + literature index mock)."""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .build import FAMILY_SLUG, FAMILY_VERSION, build_tasks
from .specs import AS_OF, ORGANIZATION
from .tools import SERVERS, TOOLS

FAMILY = Family(
    slug=FAMILY_SLUG,
    name="SciLab",
    version=FAMILY_VERSION,
    cluster="scientific-research",
    description="Assay-operations decisions against a LIMS with versioned protocols and QC results, an analyser schedule with calibration certificates, a reagent-lot inventory with expiry and quarantine state, supplier shipment confirmations, ELN method notes, and approval records.",
    schema_sql=(Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=build_tasks,
    organization=ORGANIZATION,
    as_of=AS_OF,
)

__all__ = ["FAMILY"]
