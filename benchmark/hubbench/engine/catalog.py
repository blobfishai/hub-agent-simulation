"""Task assembly helpers shared by every family: rubric, contracts, realism checks."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .decision import INFERIOR_STATES, REQUIRED_FACT_IDS, UNAUTHORIZED
from .families import CONTEXT_TOOL, SUBMIT_TOOL
from .validation import canonical_json

STANDARD_PATH = Path(__file__).resolve().parents[2] / "realism-standard.json"

MILESTONE_CATEGORIES: dict[str, str] = {
    "investigation.scope": "identity",
    "investigation.requirements": "investigation",
    "investigation.constraints": "investigation",
    "investigation.authority": "authority",
    "investigation.erp_correlation": "correlation",
    "analysis.inputs": "procedure",
    "analysis.timeline": "decision",
    "decision.options": "alternatives",
    "state.primary": "state",
    "state.collaboration": "state",
    "verification.readback": "procedure",
    "answer.insights": "answer",
    "containment.scope": "containment",
    "execution.mutations": "procedure",
}
MILESTONE_WEIGHTS: dict[str, float] = {
    "investigation.scope": 4.0,
    "investigation.requirements": 6.0,
    "investigation.constraints": 8.0,
    "investigation.authority": 6.0,
    "investigation.erp_correlation": 10.0,
    "analysis.inputs": 8.0,
    "analysis.timeline": 8.0,
    "decision.options": 8.0,
    "state.primary": 14.0,
    "state.collaboration": 6.0,
    "verification.readback": 6.0,
    "answer.insights": 10.0,
    "containment.scope": 4.0,
    "execution.mutations": 2.0,
}
FORBIDDEN_PROMPT_TOKENS = re.compile(
    r"tools/call|submit_answer|hubbench\.|json-rpc|rubric|milestone|criteri|verifier|graded|scor(e|ing)\b|step\s*\d|first,? call|then call|tool call",
    re.I,
)


def read_standard() -> dict[str, Any]:
    return json.loads(STANDARD_PATH.read_text(encoding="utf-8"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sequence_signature(steps: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        "\n".join(
            f"{step['tool']}|{canonical_json(step['arguments'])}" for step in steps
        ).encode("utf-8")
    ).hexdigest()


def word_count(text: str) -> int:
    return len(text.split())


def shingles(text: str, size: int = 5) -> set[tuple[str, ...]]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {
        tuple(words[index : index + size])
        for index in range(max(0, len(words) - size + 1))
    }


def shingle_jaccard(left: str, right: str, size: int = 5) -> float:
    a, b = shingles(left, size), shingles(right, size)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def milestone_descriptions(
    *,
    case_reference: str,
    record: str,
    revision: str,
    subject: str,
    selected_option: str,
    selected_completion: str,
    facts: list[dict[str, Any]],
    primary_outcome: str,
    correlated_systems: list[str],
) -> dict[str, str]:
    by_id = {fact["id"]: fact for fact in facts}
    return {
        "investigation.scope": f"Establish the isolated {case_reference} scope and immutable identities across the mailbox, document index, and mounted systems before relying on similarly named records.",
        "investigation.requirements": f"Determine the operative {revision} requirement for {record} from the order, the measured inputs, and the effective policy; distinguish current evidence from superseded or merely contextual records.",
        "investigation.constraints": f"Reconcile the supported operating inputs: {by_id['eligible_coverage']['rubric']} {by_id['finite_capacity']['rubric']} {by_id['conditional_external_recovery']['rubric']}",
        "investigation.authority": f"Establish what is actually authorized and what remains conditional: {by_id['approval_scope']['rubric']}",
        "investigation.erp_correlation": f"Correlate {record} by immutable identifiers across the systems of record ({', '.join(correlated_systems)}) and preserve the effective {revision} state.",
        "analysis.inputs": f"Derive the requirement, eligible coverage, exclusions, unit, and controlling threshold from the joined evidence rather than copying a headline quantity for {subject}.",
        "analysis.timeline": f"Calculate the feasible timing for {selected_option} under the actual operating window and report whether the {selected_completion} outcome meets the control date.",
        "decision.options": f"Compare all three task-specific alternatives, including timing, cost, authority, and residual risk; select {selected_option} only because the joined evidence supports it.",
        "state.primary": f"Persist exactly the supported {primary_outcome!r} change for {record} through the documented provider operation, with no neighboring record or unsupported field changed.",
        "state.collaboration": "After the primary outcome is known, leave a stakeholder draft carrying the supported decision, outcome date, binding constraint, and business reference for human review; do not send it.",
        "verification.readback": f"Read {record} back after the primary state change and verify the persisted provider state rather than trusting the write acknowledgement.",
        "answer.insights": f"Return the exact task-supported recommendation, outcome date, immutable business record, decisive operating insight, and timing status for {subject}.",
        "containment.scope": f"Keep all successful changes inside {case_reference}'s declared state, collaboration, answer, and audit scope.",
        "execution.mutations": "Complete without a rejected state-changing call; failed exploratory reads may be recovered from, but an invalid mutation is not accepted.",
    }


def build_rubric_milestones(
    *,
    descriptions: dict[str, str],
    investigations: list[dict[str, Any]],
    calculations: list[dict[str, Any]],
    assertions: list[dict[str, Any]],
    answer_checks: list[dict[str, Any]],
    post_write_verifications: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    atomic = [
        *investigations,
        *calculations,
        *assertions,
        *post_write_verifications,
        *answer_checks,
        {"id": "write_scope", "weight": 1.0, "milestone_id": "containment.scope"},
        {
            "id": "no_rejected_mutation",
            "weight": 1.0,
            "milestone_id": "execution.mutations",
        },
    ]
    by_milestone: dict[str, list[dict[str, Any]]] = {}
    for item in atomic:
        by_milestone.setdefault(str(item["milestone_id"]), []).append(item)
    unknown = sorted(set(by_milestone) - set(MILESTONE_WEIGHTS))
    if unknown:
        raise ValueError(f"criteria assigned to unknown milestones: {unknown}")
    absent = sorted(set(MILESTONE_WEIGHTS) - set(by_milestone))
    if absent:
        raise ValueError(f"task omitted required milestones: {absent}")
    missing_descriptions = sorted(set(MILESTONE_WEIGHTS) - set(descriptions))
    if missing_descriptions:
        raise ValueError(f"missing milestone descriptions: {missing_descriptions}")
    if abs(sum(MILESTONE_WEIGHTS.values()) - 100.0) > 1e-9:
        raise ValueError("milestone weights must total 100")
    ids = [str(item["id"]) for item in atomic]
    duplicates = sorted({value for value in ids if ids.count(value) > 1})
    if duplicates:
        raise ValueError(f"duplicate atomic criterion ids: {duplicates}")
    return [
        {
            "id": milestone_id,
            "category": MILESTONE_CATEGORIES[milestone_id],
            "description": descriptions[milestone_id],
            "weight": MILESTONE_WEIGHTS[milestone_id],
            "atomic_weight": round(
                sum(
                    float(item.get("weight", 1.0))
                    for item in by_milestone[milestone_id]
                ),
                2,
            ),
            "criterion_ids": [str(item["id"]) for item in by_milestone[milestone_id]],
        }
        for milestone_id in MILESTONE_WEIGHTS
    ]


def answer_checks(
    answer: dict[str, Any], fields: list[str], context: str
) -> list[dict[str, Any]]:
    checks = []
    for field_name in fields:
        value = answer[field_name]
        rendered = f"'{value}'" if isinstance(value, str) else str(value)
        checks.append(
            {
                "id": f"answer_{field_name}",
                "field": field_name,
                "weight": 1.0,
                "milestone_id": "answer.insights",
                "description": f"Reported {field_name.replace('_', ' ')} as {rendered}, tied to {context}.",
            }
        )
    return checks


def sealed_contract(task: dict[str, Any]) -> dict[str, Any]:
    expected = task["expected"]
    return {
        "answer": expected["answer"],
        "answer_checks": expected["answer_checks"],
        "assertions": expected["assertions"],
        "calculations": expected["calculations"],
        "investigations": task["required_investigations"],
        "post_write_verifications": task["post_write_verifications"],
    }


def atomic_criteria_count(task: dict[str, Any]) -> int:
    return sum(
        len(milestone["criterion_ids"]) for milestone in task["rubric_milestones"]
    )


def validate_tasks(
    tasks: list[dict[str, Any]], standard: dict[str, Any] | None = None
) -> None:
    """Raise ``ValueError`` listing every structural or realism violation."""

    standard = standard or read_standard()
    requirements = standard["requirements"]
    request_rules = requirements["employeeRequest"]
    asset_rules = requirements["assetRoom"]
    rubric_rules = requirements["rubric"]
    chain_rules = requirements["reasoningChain"]
    workflow_rules = requirements["workflow"]
    sandbox_rules = requirements["sandbox"]
    problems: list[str] = []
    signatures: dict[str, str] = {}
    instructions: dict[str, str] = {}
    asset_ids: dict[str, str] = {}
    asset_hashes: dict[str, str] = {}
    for task in tasks:
        task_id = task["task_id"]
        text = task["instruction"]
        words = word_count(text)
        if not request_rules["minimumWords"] <= words <= request_rules["maximumWords"]:
            problems.append(f"{task_id}: instruction has {words} words")
        if FORBIDDEN_PROMPT_TOKENS.search(text):
            problems.append(
                f"{task_id}: instruction carries procedure or grading language: {FORBIDDEN_PROMPT_TOKENS.search(text).group(0)!r}"
            )
        if text in instructions.values():
            problems.append(f"{task_id}: duplicate instruction")
        for other_id, other in instructions.items():
            if (
                shingle_jaccard(text, other)
                > request_rules["maximumPairwiseFiveShingleJaccard"]
            ):
                problems.append(f"{task_id}: instruction too similar to {other_id}")
        instructions[task_id] = text
        signature = task["sequence_signature"]
        if signature in signatures:
            problems.append(
                f"{task_id}: reference tool sequence duplicates {signatures[signature]}"
            )
        signatures[signature] = task_id
        assets = task["assets"]
        kinds = {asset["kind"] for asset in assets}
        media = {asset["media_type"] for asset in assets}
        paths = [str(asset["path"]) for asset in assets]
        if len(paths) != len(set(paths)):
            problems.append(f"{task_id}: duplicate evidence paths")
        for record in assets:
            asset_id = str(record.get("asset_id", ""))
            if not asset_id:
                problems.append(f"{task_id}/{record['path']}: missing global asset id")
            elif asset_id in asset_ids:
                problems.append(
                    f"{task_id}/{record['path']}: asset id duplicates {asset_ids[asset_id]}"
                )
            else:
                asset_ids[asset_id] = f"{task_id}/{record['path']}"
            digest = str(record.get("sha256", ""))
            if asset_rules["allAgentVisibleFilesGloballyUnique"]:
                if not re.fullmatch(r"[a-f0-9]{64}", digest):
                    problems.append(
                        f"{task_id}/{record['path']}: invalid evidence digest"
                    )
                elif digest in asset_hashes:
                    problems.append(
                        f"{task_id}/{record['path']}: evidence bytes duplicate {asset_hashes[digest]}"
                    )
                else:
                    asset_hashes[digest] = f"{task_id}/{record['path']}"
            hidden_parts = {part.casefold() for part in Path(str(record["path"])).parts}
            if hidden_parts & {
                "solution",
                "solutions",
                "verifier",
                "verifiers",
                "gold",
                "tests",
            }:
                problems.append(
                    f"{task_id}/{record['path']}: verifier-only artifact is agent visible"
                )
        if len(assets) < asset_rules["minimumAgentVisibleFilesPerTask"]:
            problems.append(f"{task_id}: {len(assets)} evidence files")
        if len(media) < asset_rules["minimumNativeFormatsPerTask"]:
            problems.append(f"{task_id}: {len(media)} native evidence formats")
        if asset_rules["requiresSpreadsheet"] and not any(
            "spreadsheet" in item for item in media
        ):
            problems.append(f"{task_id}: no spreadsheet evidence")
        if (
            asset_rules["requiresDocument"]
            and "text/markdown" not in media
            and "application/pdf" not in media
        ):
            problems.append(f"{task_id}: no document evidence")
        if asset_rules["requiresStructuredData"] and not media & {
            "application/json",
            "text/csv",
        }:
            problems.append(f"{task_id}: no structured evidence")
        if (
            asset_rules["requiresCommunicationRecord"]
            and "message/rfc822" not in media
            and not any(asset["kind"] in {"chat_thread", "email"} for asset in assets)
        ):
            problems.append(f"{task_id}: no communication record")
        stale_markers = ("archive", "decoy", "retired", "stale", "superseded")
        if asset_rules["requiresCurrentAndStaleOrConflictingEvidence"]:
            if "authority_current" not in kinds:
                problems.append(f"{task_id}: no explicit current authority evidence")
            if not any(
                any(marker in kind.casefold() for marker in stale_markers)
                for kind in kinds
            ):
                problems.append(f"{task_id}: no stale or conflicting evidence")
        if (
            asset_rules["requiresCrossFileIdentityAndRevisionCorrelation"]
            and not {"record_lineage", "evidence_index", "authority_current"} <= kinds
        ):
            problems.append(f"{task_id}: no complete identity/revision correlation set")
        if (
            sandbox_rules["providerContractDisclosureRequired"]
            and "provider_contract" not in kinds
        ):
            problems.append(f"{task_id}: no provider-contract disclosure")
        provenance = [
            record for record in assets if record["kind"] == "open_source_provenance"
        ]
        if len(provenance) != 1:
            problems.append(
                f"{task_id}: expected one open-source provenance record, found {len(provenance)}"
            )
        else:
            try:
                payload = json.loads(provenance[0]["content"])
            except (KeyError, TypeError, json.JSONDecodeError):
                problems.append(f"{task_id}: open-source provenance is not valid JSON")
            else:
                anchors = payload.get("anchors", [])
                if (
                    payload.get("clean_room") is not True
                    or payload.get("upstream_tasks_copied") is not False
                    or payload.get("upstream_scores_claimed") is not False
                ):
                    problems.append(
                        f"{task_id}: open-source provenance lacks clean-room boundaries"
                    )
                if not anchors or any(
                    not anchor.get("harbor_dataset")
                    or not str(anchor.get("harbor_url", "")).startswith(
                        "https://hub.harborframework.com/datasets/"
                    )
                    or not str(anchor.get("upstream_url", "")).startswith("https://")
                    for anchor in anchors
                ):
                    problems.append(
                        f"{task_id}: open-source provenance lacks exact Harbor and upstream anchors"
                    )
        criteria = atomic_criteria_count(task)
        if criteria < rubric_rules["minimumSpecificCriteriaPerTask"]:
            problems.append(f"{task_id}: {criteria} atomic criteria")
        categories = {milestone["category"] for milestone in task["rubric_milestones"]}
        missing_categories = sorted(
            set(rubric_rules["requiredCategories"]) - categories
        )
        if missing_categories:
            problems.append(f"{task_id}: rubric lacks categories {missing_categories}")
        model = task["decision_model"]
        options = model["options"]
        if len(options) < rubric_rules["minimumDecisionOptions"]:
            problems.append(f"{task_id}: {len(options)} options")
        if sum(1 for option in options if option["recommended"]) != 1:
            problems.append(f"{task_id}: recommended option count != 1")
        if not any(option["approval"] == UNAUTHORIZED for option in options):
            problems.append(f"{task_id}: no unauthorized alternative")
        if not any(option["approval"] in INFERIOR_STATES for option in options):
            problems.append(f"{task_id}: no inferior or unsupported alternative")
        fact_ids = {fact["id"] for fact in model["facts"]}
        if not set(REQUIRED_FACT_IDS) <= fact_ids:
            problems.append(
                f"{task_id}: facts missing {sorted(set(REQUIRED_FACT_IDS) - fact_ids)}"
            )
        investigations = task["required_investigations"]
        evidence_reads = len(investigations)
        provider_calls = [item["any_of"][0] for item in investigations]
        live_domain_reads = sum(call["tool"] != CONTEXT_TOOL for call in provider_calls)
        if evidence_reads < workflow_rules["minimumEvidenceReadsPerTask"]:
            problems.append(f"{task_id}: {evidence_reads} evidence reads")
        if len(provider_calls) < workflow_rules["minimumProviderEvidenceReadsPerTask"]:
            problems.append(f"{task_id}: {len(provider_calls)} provider evidence reads")
        if live_domain_reads < workflow_rules["minimumLiveDomainReadsPerTask"]:
            problems.append(f"{task_id}: {live_domain_reads} live-domain reads")
        graded_reads = sum(
            1 for item in investigations if item.get("before_primary_mutation")
        )
        if graded_reads < chain_rules["minimumEvidenceReadsBeforeDecision"]:
            problems.append(
                f"{task_id}: {graded_reads} graded evidence reads before the decision"
            )
        by_milestone = Counter(item["milestone_id"] for item in investigations)
        for milestone_id in (
            "investigation.scope",
            "investigation.requirements",
            "investigation.constraints",
            "investigation.authority",
            "investigation.erp_correlation",
        ):
            if not by_milestone.get(milestone_id):
                problems.append(f"{task_id}: no investigation at {milestone_id}")
        systems = {call["tool"].split(".")[0] for call in provider_calls}
        if len(systems) < workflow_rules["minimumIndependentEvidenceSources"]:
            problems.append(f"{task_id}: {len(systems)} independent evidence sources")
        if len(systems) < chain_rules["minimumSourceSystemsBeforeDecision"]:
            problems.append(f"{task_id}: {len(systems)} source systems")
        state_changes = sum(
            not step.get("control", False) and step.get("tool") != SUBMIT_TOOL
            for step in task.get("oracle_steps", [])
        )
        if state_changes < workflow_rules["minimumStateChangingCallsPerTask"]:
            problems.append(f"{task_id}: {state_changes} state-changing calls")
        if len(task["expected"]["answer"]) < chain_rules["minimumGradedAnswerFields"]:
            problems.append(
                f"{task_id}: {len(task['expected']['answer'])} graded answer fields"
            )
        if not task["allowed_write_tables"]:
            problems.append(f"{task_id}: no allowed write tables")
        if not any(
            assertion["milestone_id"] == "state.primary"
            and assertion.get("payload_contains", {}).get("arguments")
            for assertion in task["expected"]["assertions"]
        ):
            problems.append(
                f"{task_id}: no primary state assertion with an exact payload"
            )
        if not any(
            assertion["milestone_id"] == "state.collaboration"
            and (
                assertion.get("payload_text_contains")
                or assertion.get("payload_argument_text", {}).get("body")
            )
            for assertion in task["expected"]["assertions"]
        ):
            problems.append(
                f"{task_id}: no collaboration assertion carrying the decision"
            )
        if not task["post_write_verifications"]:
            problems.append(f"{task_id}: no post-write readback")
        controls = task.get("negative_controls", {})
        for key in ("unauthorized_write", "wrong_evidence"):
            if key not in controls:
                problems.append(f"{task_id}: negative control {key} not declared")
    if problems:
        raise ValueError(
            "task set violates the realism standard:\n  " + "\n  ".join(problems)
        )


__all__ = [
    "FORBIDDEN_PROMPT_TOKENS",
    "MILESTONE_CATEGORIES",
    "MILESTONE_WEIGHTS",
    "STANDARD_PATH",
    "answer_checks",
    "atomic_criteria_count",
    "build_rubric_milestones",
    "milestone_descriptions",
    "read_standard",
    "sealed_contract",
    "sequence_signature",
    "sha256_json",
    "shingle_jaccard",
    "validate_tasks",
    "word_count",
]
