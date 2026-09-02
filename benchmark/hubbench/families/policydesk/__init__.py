"""PolicyDesk: the HubBench policy-compliance / instruction-following family.

Access-governance decisions against a policy library, an access-request queue,
an entitlement store with segregation-of-duties rules, an exceptions register,
an approver directory, training records, an audit-finding tracker, an approver
review calendar, and an external screening vendor.
"""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .build import FAMILY_SLUG, FAMILY_VERSION, build_tasks
from .specs import AS_OF, ORGANIZATION
from .tools import SERVERS, TOOLS

FAMILY = Family(
    slug=FAMILY_SLUG,
    name="PolicyDesk",
    version=FAMILY_VERSION,
    cluster="policy-compliance-instruction-following",
    description="Access-governance decisions against a policy library with numbered clauses, an access-request queue, an entitlement store with segregation-of-duties rules, an exceptions register, an approver directory with authority tiers, training records, an audit-finding tracker, an approver review calendar, and an external screening vendor.",
    schema_sql=(Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=build_tasks,
    organization=ORGANIZATION,
    as_of=AS_OF,
)

__all__ = ["FAMILY"]
