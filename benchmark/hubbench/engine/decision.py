"""Decision-model bundles for the plan / quantity / schedule modes.

A HubBench task is an employee decision, not a lookup.  The model below turns a
family's grounded numbers (requirement, observed coverage, exclusions, gap,
external readiness, capacity, three alternatives) into the graded calculation
chain and exact answer contract that the reasoning-chain audit measures.  The
calculation ids are the ones ``benchmark/reasoning_chain_audit.py`` keys on for
hops H2..H10, so a family that emits them is measurable without a custom audit.

Adapted from the FactoryBench-100 realism model (Apache-2.0, BlobfishAI).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

APPROVED = "APPROVED"
UNAUTHORIZED = "ADDITIONAL_APPROVAL_REQUIRED"
NOT_RECOMMENDED = "AVAILABLE_NOT_RECOMMENDED"
NOT_SUPPORTED = "NOT_SUPPORTED_BY_CURRENT_EVIDENCE"
INFERIOR_STATES = {NOT_RECOMMENDED, NOT_SUPPORTED}
MODES = ("plan", "quantity", "schedule")
REQUIRED_FACT_IDS = (
    "authoritative_identity",
    "effective_requirement",
    "eligible_coverage",
    "conditional_external_recovery",
    "finite_capacity",
    "approval_scope",
    "business_impact",
)


@dataclass(frozen=True)
class Labels:
    subject: str
    scope_label: str
    eligible_label: str
    excluded_label: str
    constraint_label: str
    external_label: str
    capacity_label: str
    unit: str
    economic_label: str = "incremental cost"


@dataclass(frozen=True)
class Option:
    id: str
    completion: str
    incremental_cost: int
    approval: str
    control_status: str
    consequence: str
    recommended: bool = False


@dataclass(frozen=True)
class DecisionInputs:
    mode: str
    labels: Labels
    item: str
    record: str
    revision: str
    scope: int
    observed: int
    excluded: int
    eligible: int
    gap: int
    business_need: str
    standard_readiness: str
    expedited_readiness: str
    options: tuple[Option, Option, Option]
    transaction_quantity: int | None = None
    selected_resource: str | None = None
    extra_answer: dict[str, Any] = field(default_factory=dict)
    extra_descriptions: dict[str, str] = field(default_factory=dict)
    extra_calculations: tuple[dict[str, Any], ...] = ()
    facts: tuple[dict[str, Any], ...] = ()


def criterion(criterion_id: str, field_name: str, weight: float, description: str, milestone_id: str = "analysis.inputs") -> dict[str, Any]:
    return {"id": criterion_id, "field": field_name, "weight": weight, "description": description, "milestone_id": milestone_id}


def _days(later: str, earlier: str) -> int:
    return (date.fromisoformat(later) - date.fromisoformat(earlier)).days


def build_decision_model(inputs: DecisionInputs) -> dict[str, Any]:
    """Return the sealed decision model, answer, descriptions, and calculations."""

    if inputs.mode not in MODES:
        raise ValueError(f"unknown decision mode: {inputs.mode}")
    labels = inputs.labels
    options = inputs.options
    if len(options) != 3:
        raise ValueError("a decision needs exactly three alternatives")
    recommended = [option for option in options if option.recommended]
    if len(recommended) != 1:
        raise ValueError("exactly one alternative must be recommended")
    selected = recommended[0]
    if selected.approval != APPROVED:
        raise ValueError("the recommended alternative must be inside current authority")
    if not any(option.approval == UNAUTHORIZED for option in options):
        raise ValueError("at least one alternative must need approval beyond current authority")
    if not any(option.approval in INFERIOR_STATES for option in options):
        raise ValueError("at least one alternative must be feasible-but-inferior or unsupported")
    if inputs.eligible != inputs.observed - inputs.excluded:
        raise ValueError("eligible coverage must equal observed minus excluded")
    if inputs.gap != max(0, inputs.scope - inputs.eligible):
        raise ValueError("gap must equal requirement minus eligible coverage, floored at zero")

    variance = _days(selected.completion, inputs.business_need)
    timing_status = "LATE" if variance > 0 else "ON_TIME"
    escalation_required = 1 if any(option.approval == UNAUTHORIZED for option in options) else 0
    option_ids = [option.id for option in options]
    dates = [option.completion for option in options]

    answer: dict[str, Any] = {
        "business_need_date": inputs.business_need,
        "recommended_option": selected.id,
        "recommended_outcome_date": selected.completion,
        "recommended_incremental_cost_usd": selected.incremental_cost,
        "escalation_approval_required": escalation_required,
        "outcome_vs_control_days": variance,
        "decision_timing_status": timing_status,
    }
    descriptions: dict[str, str] = {
        "business_need_date": "Documented business or clinical control date that the decision must protect (ISO date).",
        "recommended_option": f"Best authorized option identifier after comparing {', '.join(option_ids)}.",
        "recommended_outcome_date": "Date produced by the selected option after applying every source constraint (ISO date).",
        "recommended_incremental_cost_usd": f"Documented {labels.economic_label} of the selected option in USD; zero when spend is not a decision driver.",
        "escalation_approval_required": "Use 1 when an alternative is outside current authority and would need a separate approval; otherwise 0.",
        "outcome_vs_control_days": "Selected outcome date minus the documented control date; positive means late.",
        "decision_timing_status": "ON_TIME when the selected outcome is on or before the control date; otherwise LATE.",
    }
    calculations: list[dict[str, Any]] = [
        criterion("identify_business_date", "business_need_date", 1.0, f"Preserved {inputs.business_need} as the documented control date for {labels.subject}; did not infer urgency from a title or a request tone.", "analysis.timeline"),
    ]

    if inputs.mode == "plan":
        answer.update(
            {
                "coverage_item_or_resource": inputs.item,
                "required_quantity": inputs.scope,
                "observed_coverage_quantity": inputs.observed,
                "ineligible_coverage_quantity": inputs.excluded,
                "usable_coverage_quantity": inputs.eligible,
                "shortage_quantity": inputs.gap,
                "quantity_unit": labels.unit,
                "baseline_completion": dates[0],
                "accelerated_completion": dates[1],
                "escalated_completion": dates[2],
                "standard_external_readiness": inputs.standard_readiness,
                "expedited_external_readiness": inputs.expedited_readiness,
                "external_recovery_quantity": inputs.gap,
            }
        )
        descriptions.update(
            {
                "coverage_item_or_resource": "Immutable item or resource whose requirement and eligible coverage were reconciled.",
                "required_quantity": labels.scope_label,
                "observed_coverage_quantity": f"Gross observed coverage for {labels.eligible_label} before exclusions.",
                "ineligible_coverage_quantity": labels.excluded_label,
                "usable_coverage_quantity": f"Net eligible coverage after removing {labels.excluded_label}.",
                "shortage_quantity": f"Uncovered {labels.unit} after netting eligible coverage from the requirement.",
                "quantity_unit": f"Unit shared by the requirement and coverage calculations: {labels.unit}.",
                "baseline_completion": f"Outcome date for {option_ids[0]}.",
                "accelerated_completion": f"Outcome date for {option_ids[1]}.",
                "escalated_completion": f"Outcome date for {option_ids[2]}.",
                "standard_external_readiness": f"Standard readiness date independently confirmed for {labels.external_label}.",
                "expedited_external_readiness": f"Expedited readiness date independently confirmed for {labels.external_label}.",
                "external_recovery_quantity": f"Uncovered {labels.unit} that the external recovery must cover.",
            }
        )
        calculations.extend(
            [
                criterion("derive_plan_requirement", "required_quantity", 2.0, f"Derived {inputs.scope} {labels.unit} for {labels.scope_label} at revision {inputs.revision}."),
                criterion("read_gross_coverage", "observed_coverage_quantity", 1.0, f"Read {inputs.observed} {labels.unit} of gross observed {labels.eligible_label}."),
                criterion("remove_ineligible_coverage", "ineligible_coverage_quantity", 1.5, f"Excluded {inputs.excluded} {labels.unit} for {labels.excluded_label}."),
                criterion("calculate_usable_coverage", "usable_coverage_quantity", 2.0, f"Calculated {inputs.observed} observed − {inputs.excluded} ineligible = {inputs.eligible} usable {labels.unit}."),
                criterion("calculate_plan_gap", "shortage_quantity", 2.0, f"Calculated {inputs.scope} required − {inputs.eligible} usable = {inputs.gap} {labels.unit} uncovered."),
                criterion("preserve_plan_unit", "quantity_unit", 0.5, f"Kept every planning quantity in {labels.unit}."),
                criterion("compare_baseline_plan", "baseline_completion", 1.0, f"Calculated {option_ids[0]} outcome as {dates[0]} under {labels.capacity_label}."),
                criterion("compare_accelerated_plan", "accelerated_completion", 1.0, f"Calculated {option_ids[1]} outcome as {dates[1]} using {labels.external_label}."),
                criterion("compare_escalated_plan", "escalated_completion", 1.0, f"Calculated {option_ids[2]} outcome as {dates[2]} and kept its separate-approval condition."),
                criterion("read_standard_external_readiness", "standard_external_readiness", 1.0, f"Read {inputs.standard_readiness} as the independently confirmed standard readiness date for {labels.external_label}."),
                criterion("read_expedited_external_readiness", "expedited_external_readiness", 1.0, f"Read {inputs.expedited_readiness} as the independently confirmed expedited readiness date for {labels.external_label}."),
                criterion("bound_external_recovery_quantity", "external_recovery_quantity", 1.0, f"Bound external recovery to the {inputs.gap} {labels.unit} uncovered requirement rather than ordering the full header quantity."),
            ]
        )
    elif inputs.mode == "quantity":
        if inputs.transaction_quantity is None:
            raise ValueError("quantity mode needs transaction_quantity")
        answer.update(
            {
                "controlled_item_or_record": inputs.item,
                "source_quantity": inputs.scope,
                "observed_quantity": inputs.observed,
                "excluded_quantity": inputs.excluded,
                "supported_quantity": inputs.eligible,
                "transaction_quantity": inputs.transaction_quantity,
                "quantity_unit": labels.unit,
                "baseline_resolution_date": dates[0],
                "controlled_resolution_date": dates[1],
                "escalated_resolution_date": dates[2],
                "standard_external_readiness": inputs.standard_readiness,
                "expedited_external_readiness": inputs.expedited_readiness,
            }
        )
        descriptions.update(
            {
                "controlled_item_or_record": "Immutable item, lot set, or transaction record in scope.",
                "source_quantity": labels.scope_label,
                "observed_quantity": f"Gross observed quantity before applying the control for {labels.subject}.",
                "excluded_quantity": labels.excluded_label,
                "supported_quantity": labels.eligible_label,
                "transaction_quantity": "Exact quantity the primary state change may persist.",
                "quantity_unit": f"Unit of measure for every controlled quantity: {labels.unit}.",
                "baseline_resolution_date": f"Resolution date for {option_ids[0]}.",
                "controlled_resolution_date": f"Resolution date for {option_ids[1]}.",
                "escalated_resolution_date": f"Resolution date for {option_ids[2]}.",
                "standard_external_readiness": f"Standard readiness date independently confirmed for {labels.external_label}.",
                "expedited_external_readiness": f"Expedited readiness date independently confirmed for {labels.external_label}.",
            }
        )
        calculations.extend(
            [
                criterion("establish_source_quantity", "source_quantity", 1.5, f"Established {inputs.scope} {labels.unit} for {labels.scope_label}."),
                criterion("reconcile_observed_quantity", "observed_quantity", 1.5, f"Correlated the independent source records to {inputs.observed} observed {labels.unit}."),
                criterion("identify_excluded_quantity", "excluded_quantity", 1.5, f"Removed {inputs.excluded} {labels.unit} for {labels.excluded_label}."),
                criterion("calculate_supported_quantity", "supported_quantity", 2.0, f"Calculated {inputs.observed} observed − {inputs.excluded} excluded = {inputs.eligible} supported {labels.unit}."),
                criterion("bound_transaction_quantity", "transaction_quantity", 2.0, f"Bound the state change to exactly {inputs.transaction_quantity} {labels.unit}, the measure required by the chosen disposition under {labels.constraint_label}; did not substitute the header or another business quantity."),
                criterion("preserve_transaction_unit", "quantity_unit", 0.5, f"Kept the order, transfer, or dispense quantity in {labels.unit}."),
                criterion("compare_quantity_option_one", "baseline_resolution_date", 1.0, f"Derived {dates[0]} for {option_ids[0]}."),
                criterion("compare_quantity_option_two", "controlled_resolution_date", 1.0, f"Derived {dates[1]} for {option_ids[1]}."),
                criterion("compare_quantity_option_three", "escalated_resolution_date", 1.0, f"Derived {dates[2]} for {option_ids[2]} and recognized its control impact."),
                criterion("read_standard_external_readiness", "standard_external_readiness", 1.0, f"Read {inputs.standard_readiness} as the independently confirmed standard readiness date for {labels.external_label}."),
                criterion("read_expedited_external_readiness", "expedited_external_readiness", 1.0, f"Read {inputs.expedited_readiness} as the independently confirmed expedited readiness date for {labels.external_label}."),
            ]
        )
    else:  # schedule
        if not inputs.selected_resource:
            raise ValueError("schedule mode needs selected_resource")
        answer.update(
            {
                "affected_resource_or_operation": inputs.record,
                "required_capacity": inputs.scope,
                "candidate_capacity": inputs.observed,
                "unavailable_or_protected_capacity": inputs.excluded,
                "net_usable_capacity": inputs.eligible,
                "capacity_gap": inputs.gap,
                "capacity_unit": labels.unit,
                "selected_resource_or_control": inputs.selected_resource,
                "base_completion": dates[0],
                "qualified_alternative_completion": dates[1],
                "escalated_completion": dates[2],
                "standard_external_readiness": inputs.standard_readiness,
                "expedited_external_readiness": inputs.expedited_readiness,
            }
        )
        descriptions.update(
            {
                "affected_resource_or_operation": "Immutable appointment, order, or resource record in the recovery scope.",
                "required_capacity": labels.scope_label,
                "candidate_capacity": f"Gross candidate capacity associated with {labels.eligible_label} before protected or unavailable load is removed.",
                "unavailable_or_protected_capacity": labels.excluded_label,
                "net_usable_capacity": f"Candidate capacity remaining after removing {labels.excluded_label}.",
                "capacity_gap": f"Uncovered {labels.unit} after applying finite availability inside the requested window.",
                "capacity_unit": f"Capacity unit used throughout the schedule comparison: {labels.unit}.",
                "selected_resource_or_control": "Provider identifier of the qualified resource and session used by the selected recovery.",
                "base_completion": f"Completion under {option_ids[0]}.",
                "qualified_alternative_completion": f"Completion under {option_ids[1]}.",
                "escalated_completion": f"Completion under {option_ids[2]}.",
                "standard_external_readiness": f"Standard readiness date independently confirmed for {labels.external_label}.",
                "expedited_external_readiness": f"Expedited readiness date independently confirmed for {labels.external_label}.",
            }
        )
        calculations.extend(
            [
                criterion("calculate_required_capacity", "required_capacity", 2.0, f"Calculated {inputs.scope} {labels.unit} for {labels.scope_label}."),
                criterion("establish_candidate_capacity", "candidate_capacity", 1.5, f"Established {inputs.observed} gross candidate {labels.unit} associated with {labels.eligible_label}; did not call it usable before applying protected load."),
                criterion("remove_protected_capacity", "unavailable_or_protected_capacity", 1.5, f"Excluded {inputs.excluded} {labels.unit} for {labels.excluded_label}."),
                criterion("calculate_net_usable_capacity", "net_usable_capacity", 2.0, f"Calculated {inputs.observed} candidate − {inputs.excluded} unavailable/protected = {inputs.eligible} net usable {labels.unit}."),
                criterion("calculate_capacity_gap", "capacity_gap", 2.0, f"Calculated {inputs.scope} required − {inputs.eligible} net usable = {inputs.gap} {labels.unit} uncovered inside the requested window."),
                criterion("preserve_capacity_unit", "capacity_unit", 0.5, f"Kept load and availability in {labels.unit}."),
                criterion("identify_selected_resource_or_control", "selected_resource_or_control", 1.5, f"Bound the recovery to provider identifier {inputs.selected_resource} only after confirming {labels.constraint_label}."),
                criterion("compare_base_schedule", "base_completion", 1.0, f"Calculated {dates[0]} for {option_ids[0]}."),
                criterion("compare_qualified_schedule", "qualified_alternative_completion", 1.0, f"Calculated {dates[1]} for {option_ids[1]} using {labels.capacity_label}."),
                criterion("compare_escalated_schedule", "escalated_completion", 1.0, f"Calculated {dates[2]} for {option_ids[2]} and retained its authority constraint."),
                criterion("read_standard_external_readiness", "standard_external_readiness", 1.0, f"Read {inputs.standard_readiness} as the independently confirmed standard readiness date for {labels.external_label}."),
                criterion("read_expedited_external_readiness", "expedited_external_readiness", 1.0, f"Read {inputs.expedited_readiness} as the independently confirmed expedited readiness date for {labels.external_label}."),
            ]
        )

    answer.update(inputs.extra_answer)
    descriptions.update(inputs.extra_descriptions)
    calculations.extend(dict(item) for item in inputs.extra_calculations)
    unauthorized = next(option for option in options if option.approval == UNAUTHORIZED)
    calculations.extend(
        [
            criterion("calculate_selected_cost", "recommended_incremental_cost_usd", 1.0, f"Applied USD {selected.incremental_cost} as the documented {labels.economic_label} for {selected.id}; did not invent a premium where spend is not a decision driver.", "decision.options"),
            criterion("apply_escalation_authority", "escalation_approval_required", 1.0, f"Recognized that {unauthorized.id} remains outside current authority and requires an additional approval.", "decision.options"),
            criterion("choose_task_specific_option", "recommended_option", 2.0, f"Compared the timing, cost, control status, and consequence of {', '.join(option_ids)}; selected {selected.id} because it alone gives the best currently authorized result under {labels.constraint_label}.", "decision.options"),
            criterion("calculate_recommended_outcome", "recommended_outcome_date", 2.0, f"Calculated {selected.completion} as the supported outcome date for {selected.id}.", "analysis.timeline"),
            criterion("calculate_outcome_variance", "outcome_vs_control_days", 1.5, f"Compared {selected.completion} with the independent control date {inputs.business_need} and calculated a signed variance of {variance} day(s).", "analysis.timeline"),
            criterion("state_honest_timing_status", "decision_timing_status", 1.0, f"Reported {timing_status}; did not relabel a controlled but late result as on time.", "analysis.timeline"),
        ]
    )

    calc_ids = [calc["id"] for calc in calculations]
    if len(calc_ids) != len(set(calc_ids)):
        raise ValueError("duplicate calculation ids")
    calc_fields = {calc["field"] for calc in calculations}
    missing_fields = sorted(calc_fields - set(answer))
    if missing_fields:
        raise ValueError(f"calculations grade fields absent from the answer: {missing_fields}")
    if len(answer) < 12:
        raise ValueError("the answer contract must grade at least twelve fields")
    answer_values = {str(value) for value in answer.values()}
    for option in options:
        if option.completion not in answer_values:
            raise ValueError(f"alternative outcome {option.id}={option.completion} is not graded by the answer")
    fact_ids = {fact["id"] for fact in inputs.facts}
    missing_facts = sorted(set(REQUIRED_FACT_IDS) - fact_ids)
    if missing_facts:
        raise ValueError(f"decision facts missing: {missing_facts}")
    undescribed = sorted(set(answer) - set(descriptions))
    if undescribed:
        raise ValueError(f"answer fields without descriptions: {undescribed}")

    timing_reason = (
        f"is honestly {variance} day(s) late because no faster option passes the control"
        if variance > 0
        else f"lands {abs(variance)} day(s) on or before the control date"
    )
    return {
        "mode": inputs.mode,
        "facts": [dict(fact) for fact in inputs.facts],
        "calculations": calculations,
        "options": [
            {
                "id": option.id,
                "label": f"{option.id}: outcome {option.completion}, incremental cost USD {option.incremental_cost}, {option.control_status}",
                "completion": option.completion,
                "incremental_cost": option.incremental_cost,
                "approval": option.approval,
                "control_status": option.control_status,
                "consequence": option.consequence,
                "recommended": option.recommended,
            }
            for option in options
        ],
        "selected_option": selected.id,
        "selected_completion": selected.completion,
        "selected_cost": selected.incremental_cost,
        "binding_constraint": f"{labels.constraint_label}; {labels.excluded_label} = {inputs.excluded} {labels.unit}; uncovered scope = {inputs.gap} {labels.unit}",
        "recommendation_reason": f"{selected.id} is the best currently authorized response that satisfies {labels.constraint_label} and {timing_reason}.",
        "answer": answer,
        "answer_descriptions": descriptions,
    }


def answer_schema(answer: dict[str, Any], descriptions: dict[str, str], option_ids: list[str]) -> dict[str, Any]:
    """JSON schema for ``hubbench.submit_answer`` derived from the exact answer."""

    properties: dict[str, Any] = {}
    for field_name in sorted(answer):
        value = answer[field_name]
        schema: dict[str, Any] = {"description": descriptions[field_name]}
        if field_name == "recommended_option":
            schema.update({"type": "string", "enum": list(option_ids)})
        elif field_name == "decision_timing_status":
            schema.update({"type": "string", "enum": ["ON_TIME", "LATE"]})
        elif isinstance(value, bool):
            raise ValueError(f"{field_name}: booleans are not answer values")
        elif isinstance(value, int):
            schema["type"] = "integer"
        elif isinstance(value, float):
            schema.update({"type": "number", "multipleOf": 0.01})
        else:
            schema["type"] = "string"
        properties[field_name] = schema
    return {"type": "object", "properties": properties, "required": sorted(answer), "additionalProperties": False}


__all__ = [
    "APPROVED",
    "DecisionInputs",
    "INFERIOR_STATES",
    "Labels",
    "MODES",
    "NOT_RECOMMENDED",
    "NOT_SUPPORTED",
    "Option",
    "REQUIRED_FACT_IDS",
    "UNAUTHORIZED",
    "answer_schema",
    "build_decision_model",
    "criterion",
]
