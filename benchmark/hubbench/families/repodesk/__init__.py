"""RepoDesk: the HubBench software-engineering family (repository + CI + issue tracker + deploy pipeline mock)."""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .build import FAMILY_SLUG, FAMILY_VERSION, build_tasks
from .specs import AS_OF, ORGANIZATION
from .tools import SERVERS, TOOLS

FAMILY = Family(
    slug=FAMILY_SLUG,
    name="RepoDesk",
    version=FAMILY_VERSION,
    cluster="software-engineering",
    description="Release-engineering decisions around a regression fix against a GitHub-shaped repository, a Jira-shaped issue tracker, a CI evidence register with flaky-test and runner-pool state, a deploy pipeline with release lanes, freeze windows, change records, and feature flags, customer cutover commitments, external certification partners, reviewer availability, and approval records.",
    schema_sql=(Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=build_tasks,
    organization=ORGANIZATION,
    as_of=AS_OF,
)

__all__ = ["FAMILY"]
