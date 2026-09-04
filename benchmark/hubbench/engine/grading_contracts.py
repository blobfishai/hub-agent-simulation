"""Versioned, structural text requirements for freshly built tasks only.

This is not a semantic judge. Critical state and structured answer fields stay
exact; only individually audited redundant prose fields lose sentence equality.
Historical task JSON and contracts are never migrated when loaded or verified.
"""

from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable, ParamSpec

TEXT_CONTRACT_POLICY = "hubbench.text-facts.v1"
P = ParamSpec("P")

# Explicit task/tool allowlist: new tasks do not inherit a prose exemption.
AUDITED_PROSE_FIELDS = {
    "clinicops-001": ("scheduling.appointments.create", "description"),
    "datadesk-002": ("pipelines.backfills.create", "description"),
    "datadesk-005": ("pipelines.backfills.create", "description"),
    "datadesk-008": ("pipelines.backfills.create", "description"),
    "hostops-001": ("buildfarm.reservations.create", "description"),
    "policydesk-003": ("reviews.sessions.create", "description"),
    "repodesk-001": ("deploy.changes.create", "description"),
    "scilab-001": ("instruments.bookings.create", "description"),
    "secops-001": ("oncall.bridges.create", "description"),
    "secops-006": ("oncall.bridges.create", "description"),
    "webstudio-001": ("cms.releases.create", "description"),
    "webstudio-008": ("cms.releases.create", "description"),
    "workplace-006": ("calendar.bookings.create", "description"),
    "researchdesk-001": ("research.claims.create", "note"),
    "researchdesk-004": ("research.claims.create", "note"),
    "researchdesk-006": ("research.claims.create", "note"),
    "researchdesk-003": ("reviews.reservations.create", "purpose"),
    "researchdesk-007": ("reviews.reservations.create", "purpose"),
}

INTERACTION_CONTRACT = {
    "investigation_evidence": (
        "Retrieve the applicable source records, policy, approval, and evidence "
        "through the connected provider tools before the first state change. "
        "The tool CLI, MCP, REST, and web tool forms share one audited trace. "
        "Reading /workspace/evidence directly is a convenience, but filesystem "
        "reads are not recorded and do not satisfy required tool investigations."
    ),
    "stakeholder_draft": (
        "Leave an unsent draft for the requested recipient. Its body must name "
        "the persisted primary record and supported outcome date; research "
        "drafts must also identify the current definition. Preserve the business "
        "reference and explain the decision and constraints. An internal option "
        "identifier is required only in the structured answer, not in prose."
    ),
    "text_matching": (
        "Required text facts use case-insensitive, punctuation-normalized whole "
        "tokens. Dates use ISO YYYY-MM-DD. These are structural checks, not a "
        "semantic assessment of arbitrary prose or contradictions."
    ),
}


def apply_fact_text_contract(task: dict[str, Any]) -> dict[str, Any]:
    """Return a new task; never mutate scenario arguments or a loaded release."""

    revised = deepcopy(task)
    assertions = {item["id"]: item for item in revised["expected"]["assertions"]}
    primary = assertions["mutation_01"]
    draft = assertions["mutation_02"]
    record_id = primary["values"]["record_id"]
    selected = revised["expected"]["answer"]["recommended_option"]

    audited = AUDITED_PROSE_FIELDS.get(revised["task_id"])
    if audited:
        tool, field = audited
        if primary["values"]["tool"] != tool:
            raise ValueError(f"{revised['task_id']}: audited primary tool changed")
        arguments = dict(primary["payload_contains"]["arguments"])
        if not isinstance(arguments.pop(field), str):
            raise ValueError(f"{revised['task_id']}: audited prose field changed")
        primary["payload_contains"]["arguments"] = arguments
        facts = []
        if field == "purpose":
            # These facts are not separate provider fields on a reservation.
            refs = revised["reference_records"]
            facts = [refs["metrics"]["definition_id"], refs["sources"]["source_set_id"]]
        primary["payload_argument_text"] = {field: facts}
        primary["description"] = (
            f"Persist {record_id} through {tool} with every declared structured "
            f"provider value exact. The {field} must be nonempty text"
            + (f" containing the current facts {', '.join(facts)}" if facts else "")
            + "; its sentence wording need not copy the reference. Target, "
            "resource, time, quantity, status and authority checks remain unchanged."
        )

    # Bind evidence to the BODY, not a hidden related_* argument or a subject.
    # All 104 reference drafts already include the actual persisted record.
    old_facts = draft.pop("payload_text_contains")
    if selected not in old_facts:
        raise ValueError(f"{revised['task_id']}: unexpected stakeholder contract")
    body_facts = [record_id, *(fact for fact in old_facts if fact != selected)]
    draft["payload_argument_text"] = {"body": body_facts}
    draft["description"] = (
        f"Create, but do not send, the stakeholder draft for the exact requested "
        f"recipient. Its body must contain the persisted record {record_id} and "
        f"the supported facts {', '.join(body_facts[1:])}. Preserve the existing "
        "business-reference check; internal option tokens are not required in prose."
    )
    for milestone in revised["rubric_milestones"]:
        if milestone["id"] == "state.collaboration":
            milestone["description"] = draft["description"]
    revised["evaluation"]["text_contract_policy"] = TEXT_CONTRACT_POLICY
    revised["world"]["interaction_contract"] = deepcopy(INTERACTION_CONTRACT)
    return revised


def fact_text_contract(
    builder: Callable[P, dict[str, Any]],
) -> Callable[P, dict[str, Any]]:
    """Explicit builder opt-in; loading an older immutable task stays unchanged."""

    @wraps(builder)
    def build(*args: P.args, **kwargs: P.kwargs) -> dict[str, Any]:
        return apply_fact_text_contract(builder(*args, **kwargs))

    return build
