"""FactoryBench-100 adapter (structural: decision model + sealed verifier contract).

Released artifacts (``blobfishai/factory-agent-simulation``):

* ``benchmark/factorybench100/tasks/factorybench-NNN.json`` — the task spec
  carrying ``decision_model`` (``mode``, ``facts[]``, ``calculations[]`` with a
  graded ``field`` each, ``options[]`` with ``completion`` / ``incremental_cost``
  / ``approval`` / ``control_status`` / ``recommended``), ``expected.answer``,
  ``required_investigations[]`` (``milestone_id``, ``before_primary_mutation``),
  ``rubric_milestones[]``, ``required_reads[]`` and ``allowed_write_tables[]``.
* ``benchmark/factorybench100/verifiers/contracts/factorybench-NNN.json`` — the
  sealed verifier contract with ``assertions[]`` (``milestone_id``,
  ``payload_contains``, ``payload_text_contains``) and
  ``post_write_verifications[]``.
* ``benchmark/factorybench100/reports/build.json`` ``version``.

Hop evidence:

* H1  — two graded ``investigation.scope`` reads plus the ``authoritative_identity`` fact.
* H2-H6 — the mode-specific calculation ids in :data:`FACTORY_MODE_CHAINS` all
  present in ``decision_model.calculations`` (H5/H6 alternatively: the
  ``conditional_external_recovery`` / ``finite_capacity`` fact plus a graded
  pre-mutation read whose description names the external or capacity source).
* H7  — three options each carrying ``completion``, numeric ``incremental_cost``,
  ``approval`` + ``control_status``; one ``ADDITIONAL_APPROVAL_REQUIRED`` and one
  ``AVAILABLE_NOT_RECOMMENDED`` / ``NOT_SUPPORTED_BY_CURRENT_EVIDENCE``.
* H8  — ``choose_task_specific_option`` + ``calculate_recommended_outcome``
  calculations and ``recommended_option`` / ``recommended_outcome_date`` answer fields.
* H9  — ``identify_business_date`` / ``calculate_outcome_variance`` /
  ``state_honest_timing_status`` calculations with their answer fields.
* H10 — ``apply_escalation_authority`` calculation, a graded
  ``investigation.authority`` read, the ``approval_scope`` fact and the
  ``escalation_approval_required`` answer field.
* H11 — a ``state.primary`` assertion with ``payload_contains.arguments``, at
  least one post-write verification, a ``containment.scope`` milestone and a
  non-empty ``allowed_write_tables``.
* H12 — a ``state.collaboration`` assertion whose ``payload_text_contains``
  names the selected option or completion.
* H13 — at least twelve answer fields covering every calculation ``field``.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from .core import empty_measure, not_measured, read_json, release_path_label, summarize

SLUG = "factorybench-100"

FACTORY_MODE_CHAINS: dict[str, dict[str, set[str]]] = {
    "plan": {
        "H2": {"derive_plan_requirement"},
        "H3": {"read_gross_coverage", "remove_ineligible_coverage", "calculate_usable_coverage"},
        "H4": {"calculate_plan_gap"},
        "H5": {"read_standard_external_readiness", "read_expedited_external_readiness"},
        "H6": set(),
    },
    "quantity": {
        "H2": {"establish_source_quantity"},
        "H3": {"reconcile_observed_quantity", "identify_excluded_quantity", "calculate_supported_quantity"},
        "H4": {"bound_transaction_quantity"},
        "H5": set(),
        "H6": set(),
    },
    "schedule": {
        "H2": {"calculate_required_capacity"},
        "H3": {"establish_candidate_capacity", "remove_protected_capacity", "calculate_net_usable_capacity"},
        "H4": {"calculate_capacity_gap"},
        "H5": set(),
        "H6": {"identify_selected_resource_or_control"},
    },
    "financial": {
        "H2": {"establish_document_amount"},
        "H3": {"calculate_exception_amount", "calculate_supported_amount"},
        "H4": {"apply_financial_control_threshold"},
        "H5": set(),
        "H6": {"identify_financial_control"},
    },
    "identity": {
        "H2": {"construct_immutable_match"},
        "H3": {"enumerate_candidate_records", "exclude_nonmatching_records", "correlate_matching_records"},
        "H4": set(),
        "H5": set(),
        "H6": set(),
    },
    "forecast": {
        "H2": {"establish_forecast_source_measure"},
        "H3": {"exclude_invalid_forecast_measure", "qualify_forecast_measure"},
        "H4": {"calculate_due_date"},
        "H5": set(),
        "H6": {"bound_forecast_horizon", "identify_safe_window"},
    },
}
EXTERNAL_WORDS = re.compile(r"external|supplier|vendor|attachment|counterpart", re.I)
CAPACITY_WORDS = re.compile(r"calendar|capacity|window|schedule|shift|slot|dispatch", re.I)
UNAUTHORIZED_STATES = {"ADDITIONAL_APPROVAL_REQUIRED"}
INFERIOR_STATES = {"AVAILABLE_NOT_RECOMMENDED", "NOT_SUPPORTED_BY_CURRENT_EVIDENCE"}


def _answer_values(answer: dict[str, Any]) -> set[str]:
    return {str(value) for value in answer.values()}


def measure_factorybench_task(task: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    model = task["decision_model"]
    mode = model.get("mode")
    measure = empty_measure(task["task_id"], mode)
    hops = measure["hops"]
    answer = task["expected"]["answer"]
    answer_values = _answer_values(answer)
    calcs = {calc["id"] for calc in model.get("calculations", [])}
    calc_fields = {calc["field"] for calc in model.get("calculations", [])}
    facts = {fact["id"] for fact in model.get("facts", [])}
    milestones = {m["id"]: m for m in task.get("rubric_milestones", [])}
    investigations = task.get("required_investigations", [])
    by_milestone = Counter(inv["milestone_id"] for inv in investigations)
    chain = FACTORY_MODE_CHAINS.get(mode, {})

    def all_present(ids: set[str]) -> bool:
        return bool(ids) and ids <= calcs

    hops["H1"] = by_milestone.get("investigation.scope", 0) >= 2 and "authoritative_identity" in facts
    hops["H2"] = all_present(chain.get("H2", set()))
    hops["H3"] = all_present(chain.get("H3", set()))
    hops["H4"] = all_present(chain.get("H4", set()))
    graded_external_reads = sum(
        1 for inv in investigations if inv.get("before_primary_mutation") and EXTERNAL_WORDS.search(inv["description"])
    )
    graded_capacity_reads = sum(
        1
        for inv in investigations
        if inv.get("before_primary_mutation")
        and inv["milestone_id"] == "investigation.constraints"
        and CAPACITY_WORDS.search(inv["description"])
    )
    hops["H5"] = all_present(chain.get("H5", set())) or (
        "conditional_external_recovery" in facts and graded_external_reads >= 1
    )
    hops["H6"] = all_present(chain.get("H6", set())) or ("finite_capacity" in facts and graded_capacity_reads >= 1)

    options = model.get("options", [])
    alt = measure["alternatives"]
    alt["count"] = len(options)
    alt["withOutcome"] = sum(1 for o in options if o.get("completion"))
    alt["withCost"] = sum(1 for o in options if isinstance(o.get("incremental_cost"), (int, float)))
    alt["withAuthority"] = sum(1 for o in options if o.get("approval") and o.get("control_status"))
    alt["unauthorized"] = sum(1 for o in options if o.get("approval") in UNAUTHORIZED_STATES)
    alt["inferiorOrUnsupported"] = sum(1 for o in options if o.get("approval") in INFERIOR_STATES)
    alt["recommended"] = sum(1 for o in options if o.get("recommended"))
    alt["outcomesGraded"] = sum(1 for o in options if str(o.get("completion")) in answer_values)
    hops["H7"] = (
        alt["count"] >= 3
        and alt["withOutcome"] == alt["count"]
        and alt["withCost"] == alt["count"]
        and alt["withAuthority"] == alt["count"]
        and alt["unauthorized"] >= 1
        and alt["inferiorOrUnsupported"] >= 1
        and alt["recommended"] == 1
    )
    hops["H8"] = (
        {"choose_task_specific_option", "calculate_recommended_outcome"} <= calcs
        and {"recommended_option", "recommended_outcome_date"} <= answer.keys()
        and answer.get("recommended_option") == model.get("selected_option")
    )
    hops["H9"] = (
        {"identify_business_date", "calculate_outcome_variance", "state_honest_timing_status"} <= calcs
        and {"business_need_date", "outcome_vs_control_days", "decision_timing_status"} <= answer.keys()
    )
    hops["H10"] = (
        "apply_escalation_authority" in calcs
        and by_milestone.get("investigation.authority", 0) >= 1
        and "escalation_approval_required" in answer
        and "approval_scope" in facts
    )
    assertions = contract.get("assertions", [])
    primary = [a for a in assertions if a.get("milestone_id") == "state.primary"]
    readbacks = contract.get("post_write_verifications", [])
    hops["H11"] = (
        any(a.get("payload_contains", {}).get("arguments") for a in primary)
        and len(readbacks) >= 1
        and "containment.scope" in milestones
        and bool(task.get("allowed_write_tables"))
    )
    decision_tokens = {str(model.get("selected_option")), str(model.get("selected_completion"))}
    hops["H12"] = any(
        a.get("milestone_id") == "state.collaboration"
        and decision_tokens & set(map(str, a.get("payload_text_contains", [])))
        for a in assertions
    )
    hops["H13"] = len(answer) >= 12 and calc_fields <= answer.keys()

    measure["dependentDerivations"] = len(calcs)
    measure["sourceSystemsBeforeDecision"] = len({read.split(".")[0] for read in task.get("required_reads", [])})
    measure["evidenceReadsBeforeDecision"] = sum(1 for inv in investigations if inv.get("before_primary_mutation"))
    measure["gradedAnswerFields"] = len(answer)
    measure["intermediateValuesGraded"] = calc_fields <= answer.keys() and bool(calc_fields)
    measure["externalValueGraded"] = all_present(chain.get("H5", set()))
    measure["capacityValueGraded"] = all_present(chain.get("H6", set()))
    return measure


def audit(
    source_root: Path,
    entry: dict[str, Any],
    release_override: Path | None = None,
) -> dict[str, Any]:
    release = (
        release_override.resolve()
        if release_override
        else source_root / "factory-agent-simulation" / "benchmark" / "factorybench100"
    )
    tasks_dir = release / "tasks"
    contracts_dir = release / "verifiers" / "contracts"
    if not tasks_dir.is_dir() or not contracts_dir.is_dir():
        return not_measured(entry, f"release tree not found under {release_path_label(release, source_root)}")
    build = read_json(release / "reports" / "build.json") if (release / "reports" / "build.json").exists() else {}
    measures = []
    for task_path in sorted(tasks_dir.glob("factorybench-*.json")):
        task = read_json(task_path)
        contract = read_json(contracts_dir / task_path.name)
        measures.append(measure_factorybench_task(task, contract))
    return summarize(entry, measures, adapter="factorybench-structural", version=build.get("version"), source="benchmark/factorybench100 tasks + verifiers/contracts in blobfishai/factory-agent-simulation")
