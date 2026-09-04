"""RepoDesk: vendored HubBench runtime family (provider-shaped tools + schema only).

Emitted by ``hubbench.engine.distribution`` for the distributed task package.  It
carries no task builder, no scenario data, no oracle policy, and no verifier
contract: the task world is loaded from the package's task.json.
"""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .tools import SERVERS, TOOLS


def _no_task_builder() -> list:
    raise RuntimeError("the distributed repodesk runtime does not build tasks; load the task from task.json")


FAMILY = Family(
    slug='repodesk',
    name='RepoDesk',
    version='1.0.1',
    cluster='software-engineering',
    description='Release-engineering decisions around a regression fix against a GitHub-shaped repository, a Jira-shaped issue tracker, a CI evidence register with flaky-test and runner-pool state, a deploy pipeline with release lanes, freeze windows, change records, and feature flags, customer cutover commitments, external certification partners, reviewer availability, and approval records.',
    schema_sql=Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=_no_task_builder,
    organization={'id': 'larkspur-release-engineering-v1', 'name': 'Larkspur Systems — Release Engineering', 'organization_id': 'ORG-LARKSPUR', 'primary_site': 'REPO-PLATFORM', 'systems': ['scm', 'tracker', 'ci', 'deploy', 'success', 'partners', 'oncall', 'approvals', 'messages', 'chat', 'drive', 'notes']},
    as_of='2026-05-04',
)

__all__ = ["FAMILY"]
