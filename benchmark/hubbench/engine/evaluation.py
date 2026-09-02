"""Oracle replay, negative controls, mutation omissions, and determinism.

Adapted from the FactoryBench-100 evaluator (Apache-2.0, BlobfishAI).  A task is
qualified only when its oracle scores 100 strictly, two independent replays
produce byte-identical episodes, every negative control is rejected, and every
reference mutation is proven necessary.
"""

from __future__ import annotations

import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from .families import CONTEXT_TOOL, SUBMIT_TOOL, Family
from .verifier import METRIC, verify_episode
from .world import World

NEGATIVE_POLICIES = (
    "noop",
    "shortcut",
    "state_only",
    "incomplete_read",
    "write_before_read",
    "missing_readback",
    "unauthorized_write",
    "wrong_value",
    "wrong_decision",
    "wrong_evidence",
)
POLICIES = ("oracle", *NEGATIVE_POLICIES)
_PREFERRED_WRONG_VALUE_FIELDS = (
    "shortage_quantity",
    "transaction_quantity",
    "capacity_gap",
    "usable_coverage_quantity",
    "supported_quantity",
    "net_usable_capacity",
    "required_quantity",
    "source_quantity",
    "required_capacity",
)


def _state_diff(before: dict[str, list[dict[str, Any]]], after: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    changed: dict[str, Any] = {}
    for table in sorted(set(before) | set(after)):
        if before.get(table, []) != after.get(table, []):
            changed[table] = {
                "before_count": len(before.get(table, [])),
                "after_count": len(after.get(table, [])),
                "before": before.get(table, []),
                "after": after.get(table, []),
            }
    return changed


def wrong_answer(task: dict[str, Any], *, decision: bool) -> dict[str, Any]:
    answer = deepcopy(task["expected"]["answer"])
    if decision:
        answer["recommended_option"] = next(option["id"] for option in task["decision_model"]["options"] if not option["recommended"])
        return answer
    properties = task["answer_schema"]["properties"]
    numeric = [name for name in sorted(properties) if properties[name]["type"] in {"integer", "number"}]
    for preferred in _PREFERRED_WRONG_VALUE_FIELDS:
        if preferred in numeric:
            answer[preferred] = answer[preferred] + 1
            return answer
    if numeric:
        answer[numeric[0]] = answer[numeric[0]] + 1
        return answer
    field = next(name for name in sorted(properties) if name != "recommended_option" and "enum" not in properties[name])
    answer[field] = f"{answer[field]}-unsupported"
    return answer


def policy_steps(task: dict[str, Any], policy: str) -> list[dict[str, Any]]:
    steps = deepcopy(task["oracle_steps"])
    if policy == "oracle":
        return steps
    if policy == "noop":
        return []
    if policy == "shortcut":
        return [step for step in steps if step["phase"] in {"primary_mutation", "collaboration", "answer"}]
    if policy == "state_only":
        return [step for step in steps if step["tool"] != SUBMIT_TOOL]
    if policy == "incomplete_read":
        omitted = max(index for index, step in enumerate(steps) if step.get("control") and step["phase"] == "investigation")
        return [step for index, step in enumerate(steps) if index != omitted]
    if policy == "write_before_read":
        primary_index = next(index for index, step in enumerate(steps) if step["phase"] == "primary_mutation")
        primary = steps.pop(primary_index)
        context_index = next(index for index, step in enumerate(steps) if step["tool"] == CONTEXT_TOOL)
        steps.insert(context_index + 1, primary)
        return steps
    if policy == "missing_readback":
        return [step for step in steps if step["phase"] != "post_write_verification"]
    if policy == "unauthorized_write":
        answer_index = next(index for index, step in enumerate(steps) if step["tool"] == SUBMIT_TOOL)
        extra = deepcopy(task["negative_controls"]["unauthorized_write"])
        extra.update({"phase": "negative_control", "control": False})
        steps.insert(answer_index, extra)
        return steps
    if policy == "wrong_value":
        next(step for step in steps if step["tool"] == SUBMIT_TOOL)["arguments"] = wrong_answer(task, decision=False)
        return steps
    if policy == "wrong_decision":
        next(step for step in steps if step["tool"] == SUBMIT_TOOL)["arguments"] = wrong_answer(task, decision=True)
        return steps
    if policy == "wrong_evidence":
        decoy = task["negative_controls"]["wrong_evidence"]
        candidates = [index for index, step in enumerate(steps) if step.get("control") and step["phase"] == "investigation" and step["tool"] == decoy["tool"]]
        if not candidates:
            raise ValueError(f"{task['task_id']} has no required read on {decoy['tool']}")
        steps[candidates[-1]] = {"phase": "negative_control", "control": True, "tool": decoy["tool"], "arguments": deepcopy(decoy["arguments"])}
        return steps
    raise ValueError(f"unknown policy: {policy}")


def run_episode(family: Family, task: dict[str, Any], policy: str, database_path: str | Path) -> dict[str, Any]:
    with World.fresh(family, task, database_path) as world:
        before = world.snapshot()
        for step in policy_steps(task, policy):
            world.call_tool(step["tool"], step["arguments"])
        verification = verify_episode(task, world)
        after = world.snapshot()
        return {**verification, "policy": policy, "trace": world.trace, "state_diff": _state_diff(before, after)}


def evaluate_policy(family: Family, policy: str, tasks: Iterable[dict[str, Any]], *, include_episodes: bool = False) -> dict[str, Any]:
    selected = list(tasks)
    with tempfile.TemporaryDirectory(prefix=f"hubbench-{family.slug}-") as temporary:
        root = Path(temporary)
        episodes = [run_episode(family, task, policy, root / f"{task['task_id']}.db") for task in selected]
    mean_score = round(sum(episode["score"] for episode in episodes) / len(episodes), 2) if episodes else 0.0
    result: dict[str, Any] = {
        "policy": policy,
        "metric": METRIC,
        "mean_score": mean_score,
        "strict_passes": sum(1 for episode in episodes if episode["strict_pass"]),
        "task_count": len(selected),
        "mode_scores": {
            mode: round(sum(e["score"] for e, t in zip(episodes, selected) if t["mode"] == mode) / max(1, sum(1 for t in selected if t["mode"] == mode)), 2)
            for mode in sorted({task["mode"] for task in selected})
        },
        "task_scores": {episode["task_id"]: episode["score"] for episode in episodes},
    }
    if include_episodes:
        result["episodes"] = episodes
    return result


def evaluate_mutation_omissions(family: Family, tasks: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Prove that every reference mutation is necessary for strict completion."""

    selected = list(tasks)
    failures: list[dict[str, Any]] = []
    total = 0
    mutating = family.write_tools - {SUBMIT_TOOL}
    with tempfile.TemporaryDirectory(prefix=f"hubbench-{family.slug}-omissions-") as temporary:
        root = Path(temporary)
        for task in selected:
            for omitted_index in [index for index, step in enumerate(task["oracle_steps"]) if step["tool"] in mutating]:
                total += 1
                with World.fresh(family, task, root / f"{task['task_id']}-{omitted_index}.db") as world:
                    for index, step in enumerate(task["oracle_steps"]):
                        if index != omitted_index:
                            world.call_tool(step["tool"], step["arguments"])
                    verification = verify_episode(task, world)
                if verification["strict_pass"] or verification["score"] == 100.0:
                    failures.append(
                        {
                            "task_id": task["task_id"],
                            "omitted_step": omitted_index,
                            "omitted_tool": task["oracle_steps"][omitted_index]["tool"],
                            "score": verification["score"],
                        }
                    )
    return {"total": total, "detected": total - len(failures), "all_detected": not failures, "failures": failures}


def qualify(family: Family, tasks: Iterable[dict[str, Any]]) -> dict[str, Any]:
    selected = list(tasks)
    results = [evaluate_policy(family, policy, selected) for policy in POLICIES]
    by_policy = {result["policy"]: result for result in results}
    oracle = by_policy["oracle"]
    omissions = evaluate_mutation_omissions(family, selected)
    with tempfile.TemporaryDirectory(prefix="hubbench-replay-a-") as first_dir, tempfile.TemporaryDirectory(prefix="hubbench-replay-b-") as second_dir:
        first = [run_episode(family, task, "oracle", Path(first_dir) / f"{task['task_id']}.db") for task in selected]
        second = [run_episode(family, task, "oracle", Path(second_dir) / f"{task['task_id']}.db") for task in selected]
    exact_matches = sum(left == right for left, right in zip(first, second, strict=True))
    deterministic = exact_matches == len(selected)
    negative_controls = {
        policy: {
            "executions": len(selected),
            "false_accepts": by_policy[policy]["strict_passes"],
            "correct_rejections": len(selected) - by_policy[policy]["strict_passes"],
            "mean_score": by_policy[policy]["mean_score"],
        }
        for policy in NEGATIVE_POLICIES
    }
    negatives_below_oracle = all(by_policy[policy]["mean_score"] < oracle["mean_score"] for policy in NEGATIVE_POLICIES)
    no_false_accepts = not any(control["false_accepts"] for control in negative_controls.values())
    passed = (
        oracle["strict_passes"] == len(selected)
        and oracle["mean_score"] == 100.0
        and deterministic
        and no_false_accepts
        and negatives_below_oracle
        and omissions["all_detected"]
    )
    return {
        "schema_version": "hubbench.qualification.v1",
        "benchmark": "HubBench",
        "family": family.slug,
        "version": family.version,
        "metric": METRIC,
        "task_count": len(selected),
        "modes": dict(sorted(((mode, sum(1 for task in selected if task["mode"] == mode)) for mode in {task["mode"] for task in selected}))),
        "executions": len(selected) * (2 + len(NEGATIVE_POLICIES)) + omissions["total"],
        "qualification_passed": passed,
        "oracle": {
            "executions": len(selected),
            "passes": oracle["strict_passes"],
            "failures": len(selected) - oracle["strict_passes"],
            "mean_score": oracle["mean_score"],
            "task_scores": oracle["task_scores"],
        },
        "determinism": {"replays": len(selected), "exact_episode_matches": exact_matches, "mismatches": len(selected) - exact_matches, "deterministic": deterministic},
        "negative_controls": negative_controls,
        "negative_controls_below_oracle": negatives_below_oracle,
        "false_accepts": sum(control["false_accepts"] for control in negative_controls.values()),
        "mutation_omissions": omissions,
        "policies": [{key: value for key, value in result.items() if key != "episodes"} for result in results],
    }


__all__ = ["NEGATIVE_POLICIES", "POLICIES", "evaluate_mutation_omissions", "evaluate_policy", "policy_steps", "qualify", "run_episode", "wrong_answer"]
