"""Shared measurement core for the reasoning-chain audit adapters.

Every adapter maps one benchmark's *released* task and verifier artifacts onto
the standard-v2 measure produced by :func:`empty_measure` (hop flags H1..H13,
dependent derivations, evidence reads, alternatives, graded answer fields) and
hands the per-task measures to :func:`summarize`, which applies the thresholds
from ``benchmark/realism-standard.json`` ``requirements.reasoningChain``.

Detection rules that every adapter must follow:

* structural only — a hop counts when the released task or verifier artifact
  shows the value is graded; prose in the prompt never counts;
* conservative — an artifact that does not expose a hop as graded data leaves
  the hop ``False``;
* no LLM calls, no threshold changes, no benchmark-specific relaxations.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
STANDARD_PATH = ROOT / "benchmark" / "realism-standard.json"
CATALOG_PATH = ROOT / "benchmark" / "catalog.json"
REPORT_DIR = ROOT / "benchmark" / "reports" / "reasoning-chain"
AGGREGATE_PATH = ROOT / "benchmark" / "reports" / "reasoning-chain-audit.json"
SCHEMA_VERSION = "blobfish.reasoning-chain-audit.v1"
HOP_IDS = [f"H{i}" for i in range(1, 14)]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def reasoning_chain_standard() -> dict[str, Any]:
    return read_json(STANDARD_PATH)["requirements"]["reasoningChain"]


# --------------------------------------------------------------------------- #
# Task-level judgement
# --------------------------------------------------------------------------- #


def judge_task(measure: dict[str, Any], chain: dict[str, Any]) -> dict[str, Any]:
    """Apply the reasoningChain thresholds to one measured task."""
    hops = measure["hops"]
    missing: list[str] = []
    for hop in chain["mandatoryHopClasses"]:
        if not hops.get(hop):
            missing.append(hop)
    constraint_hops = sum(1 for hop in chain["constraintHopClasses"] if hops.get(hop))
    if constraint_hops < chain["minimumConstraintHops"]:
        missing.append(f"constraint-hops<{chain['minimumConstraintHops']}")
    depth = sum(1 for hop in chain["spineHopClasses"] if hops.get(hop))
    if depth < chain["minimumChainDepth"]:
        missing.append(f"chain-depth<{chain['minimumChainDepth']}")
    if measure["dependentDerivations"] < chain["minimumDependentDerivations"]:
        missing.append(f"dependent-derivations<{chain['minimumDependentDerivations']}")
    if measure["sourceSystemsBeforeDecision"] < chain["minimumSourceSystemsBeforeDecision"]:
        missing.append(f"source-systems<{chain['minimumSourceSystemsBeforeDecision']}")
    if measure["evidenceReadsBeforeDecision"] < chain["minimumEvidenceReadsBeforeDecision"]:
        missing.append(f"evidence-reads<{chain['minimumEvidenceReadsBeforeDecision']}")
    options = measure["alternatives"]
    if options["count"] < chain["minimumAlternatives"]:
        missing.append(f"alternatives<{chain['minimumAlternatives']}")
    for carried, key in (("outcome", "withOutcome"), ("incrementalCost", "withCost"), ("authorityStatus", "withAuthority")):
        if carried in chain["alternativeMustCarry"] and options[key] < options["count"]:
            missing.append(f"alternative-without-{carried}")
    if chain["requiresUnauthorizedAlternative"] and options["unauthorized"] < 1:
        missing.append("no-unauthorized-alternative")
    if chain["requiresInferiorOrUnsupportedAlternative"] and options["inferiorOrUnsupported"] < 1:
        missing.append("no-inferior-or-unsupported-alternative")
    if chain["allAlternativeOutcomesGraded"] and options["outcomesGraded"] < options["count"]:
        missing.append("alternative-outcome-not-graded")
    if measure["gradedAnswerFields"] < chain["minimumGradedAnswerFields"]:
        missing.append(f"graded-answer-fields<{chain['minimumGradedAnswerFields']}")
    if chain["intermediateValuesGraded"] and not measure["intermediateValuesGraded"]:
        missing.append("intermediate-values-not-graded")
    if measure.get("llmJudgeCalls", 0) > chain["llmJudgeCalls"]:
        missing.append("llm-judge")
    measure["chainDepth"] = depth
    measure["constraintHops"] = constraint_hops
    measure["missing"] = missing
    measure["passes"] = not missing
    return measure


def empty_measure(task_id: str, mode: str | None = None) -> dict[str, Any]:
    return {
        "taskId": task_id,
        "mode": mode,
        "hops": {hop: False for hop in HOP_IDS},
        "dependentDerivations": 0,
        "sourceSystemsBeforeDecision": 0,
        "evidenceReadsBeforeDecision": 0,
        "alternatives": {
            "count": 0,
            "withOutcome": 0,
            "withCost": 0,
            "withAuthority": 0,
            "unauthorized": 0,
            "inferiorOrUnsupported": 0,
            "recommended": 0,
            "outcomesGraded": 0,
        },
        "gradedAnswerFields": 0,
        "intermediateValuesGraded": False,
        "llmJudgeCalls": 0,
        "detection": "structural",
    }


# --------------------------------------------------------------------------- #
# Benchmark-level reports
# --------------------------------------------------------------------------- #


def not_measured(entry: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "slug": entry["slug"],
        "name": entry["name"],
        "status": "not-measured",
        "adapter": None,
        "reason": reason,
        "tasks": entry["source"]["tasks"],
        "measuredTasks": 0,
        "passingTasks": 0,
    }


def summarize(entry: dict[str, Any], measures: list[dict[str, Any]], *, adapter: str, version: str | None, source: str) -> dict[str, Any]:
    chain = reasoning_chain_standard()
    judged = [judge_task(measure, chain) for measure in measures]
    hop_coverage = {hop: sum(1 for m in judged if m["hops"][hop]) for hop in HOP_IDS}
    depths = [m["chainDepth"] for m in judged]
    failures = [{"taskId": m["taskId"], "missing": m["missing"]} for m in judged if not m["passes"]]
    missing_counter = Counter(reason for m in judged for reason in m["missing"])
    return {
        "slug": entry["slug"],
        "name": entry["name"],
        "status": "measured",
        "adapter": adapter,
        "version": version,
        "source": source,
        "tasks": entry["source"]["tasks"],
        "measuredTasks": len(judged),
        "passingTasks": sum(1 for m in judged if m["passes"]),
        "meetsStandard": bool(judged) and all(m["passes"] for m in judged),
        "hopCoverage": hop_coverage,
        "chainDepth": {"min": min(depths), "max": max(depths)} if depths else None,
        "dependentDerivations": {
            "min": min(m["dependentDerivations"] for m in judged),
            "max": max(m["dependentDerivations"] for m in judged),
        }
        if judged
        else None,
        "sourceSystemsBeforeDecision": {
            "min": min(m["sourceSystemsBeforeDecision"] for m in judged),
            "max": max(m["sourceSystemsBeforeDecision"] for m in judged),
        }
        if judged
        else None,
        "evidenceReadsBeforeDecision": {
            "min": min(m["evidenceReadsBeforeDecision"] for m in judged),
            "max": max(m["evidenceReadsBeforeDecision"] for m in judged),
        }
        if judged
        else None,
        "gradedAnswerFields": {
            "min": min(m["gradedAnswerFields"] for m in judged),
            "max": max(m["gradedAnswerFields"] for m in judged),
        }
        if judged
        else None,
        "alternatives": {
            "tasksWithThreeFullyQualified": sum(1 for m in judged if m["hops"]["H7"]),
            "tasksWithAllOutcomesGraded": sum(
                1 for m in judged if m["alternatives"]["count"] and m["alternatives"]["outcomesGraded"] == m["alternatives"]["count"]
            ),
        },
        "modes": dict(sorted(Counter(m["mode"] for m in judged).items())),
        "failureReasons": dict(sorted(missing_counter.items())),
        "failures": failures,
        "taskMeasures": judged,
    }


def release_path_label(path: Path, source_root: Path) -> str:
    """Describe a release path without leaking the machine's home directory."""
    parent = source_root.parent
    if path.is_relative_to(parent):
        return str(path.relative_to(parent))
    return path.name


def release_version(release: Path, *candidates: str) -> str | None:
    """Read the release version from the first candidate report that carries one."""
    for candidate in candidates:
        path = release / candidate
        if path.exists():
            data = read_json(path)
            version = data.get("version") or data.get("benchmark_version")
            if version:
                return str(version)
    return None


def count_graded_leaves(value: Any) -> int:
    """Count the scalar fields an exact-equality answer contract grades.

    Dicts and lists of dicts recurse; a list of scalars is one set-valued
    field; a scalar is one field.
    """
    if isinstance(value, dict):
        return sum(count_graded_leaves(item) for item in value.values())
    if isinstance(value, list):
        if value and all(isinstance(item, dict) for item in value):
            return sum(count_graded_leaves(item) for item in value)
        return 1
    return 1


def alternatives_fully_qualified(alt: dict[str, int]) -> bool:
    """H7: three alternatives, each with outcome + cost + authority, one unauthorized,
    one inferior-or-unsupported, exactly one recommended."""
    return (
        alt["count"] >= 3
        and alt["withOutcome"] == alt["count"]
        and alt["withCost"] == alt["count"]
        and alt["withAuthority"] == alt["count"]
        and alt["unauthorized"] >= 1
        and alt["inferiorOrUnsupported"] >= 1
        and alt["recommended"] == 1
    )
