#!/usr/bin/env python3
"""Import a Harbor model job into ``benchmark/hubbench/model_runs/<slug>/`` — fail-closed.

    python3 benchmark/hubbench/model_run.py <job-dir> --slug gpt-5.6-luna-v1.0.0-pilot-5 \
        --label "GPT-5.6 Luna (Codex 0.151.0, max reasoning)" --allow-partial

A run is **ranked** (eligible for a leaderboard row) only when it completed every
task of the published release exactly once with zero errors and zero retries and
every trial is bound to the published dataset (``source`` + ``task_name`` +
Harbor ``task_checksum``). Anything else is a **disclosed partial run**: its
trajectories are published, its scores are never ranked.

Per trial the importer keeps the durable world call trace pulled by the packaged
verifier (``verifier/trace.json`` — provider-independent, every surface), the
HubScore verdict (score, strict pass, per-category earned weight), and the
agent's token and cost receipt. Nothing is typed by hand; the release version,
task ids, and digests come from ``reports/publication.json``.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

HUBBENCH_ROOT = Path(__file__).resolve().parent
MODEL_RUNS = HUBBENCH_ROOT / "model_runs"
PUBLICATION = HUBBENCH_ROOT / "reports" / "publication.json"
SCHEMA_VERSION = "hubbench.model-run.v1"
RESULT_LIMIT = 2000


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _compact_result(value: Any, limit: int = RESULT_LIMIT) -> Any:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= limit:
        return value
    return {"_truncated": True, "_preview": text[: limit - 1] + "…", "_chars": len(text)}


def _category_scores(verdict: dict[str, Any]) -> dict[str, float]:
    earned: dict[str, float] = {}
    total: dict[str, float] = {}
    for check in verdict["checks"]:
        category = check["category"]
        weight = float(check.get("weight", 0.0) or 0.0)
        if not weight:
            # Older verdicts carry the milestone weight as atomic sums; fall back to earned/atomic ratio.
            passed = float(check.get("evidence", {}).get("passed_criteria", 0))
            atomic = float(check.get("evidence", {}).get("total_criteria", 0) or passed)
            weight = float(check.get("earned_weight", 0.0)) * (atomic / passed) if passed else 0.0
        earned[category] = earned.get(category, 0.0) + float(check.get("earned_weight", 0.0))
        total[category] = total.get(category, 0.0) + weight
    return {key: round(100.0 * earned[key] / total[key], 2) for key in sorted(total) if total[key]}


def import_trial(trial_dir: Path, publication: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    result = _read(trial_dir / "result.json")
    verdict = _read(trial_dir / "verifier" / "verdict.json")
    trace = _read(trial_dir / "verifier" / "trace.json")
    config = _read(trial_dir / "config.json")
    harbor_task = result["task_name"].split("/", 1)[1]
    if result.get("source") != publication["harborDataset"]:
        raise ValueError(f"{trial_dir.name}: trial source {result.get('source')!r} is not the published dataset")
    if harbor_task not in publication["publishedTasks"]:
        raise ValueError(f"{trial_dir.name}: {harbor_task} is not a published task")
    if result.get("exception_info"):
        raise ValueError(f"{trial_dir.name}: trial errored: {json.dumps(result['exception_info'])[:200]}")
    if verdict["task_id"] != trace["task_id"]:
        raise ValueError(f"{trial_dir.name}: verdict/trace task mismatch")
    reward = float(result["verifier_result"]["rewards"]["reward"])
    if abs(reward - verdict["score"] / 100.0) > 1e-6:
        raise ValueError(f"{trial_dir.name}: Harbor reward {reward} disagrees with the verdict score {verdict['score']}")
    agent = result.get("agent_result") or {}
    receipt = {
        "task_id": verdict["task_id"],
        "harbor_task": harbor_task,
        "trial": trial_dir.name,
        "harbor_task_checksum": result.get("task_checksum"),
        "published_digest": publication["publishedTaskDigests"][result["task_name"]],
        "score": verdict["score"],
        "strict_pass": bool(verdict["strict_pass"]),
        "passed_checks": verdict["passed_checks"],
        "total_checks": verdict["total_checks"],
        "passed_atomic_checks": verdict["passed_atomic_checks"],
        "total_atomic_checks": verdict["total_atomic_checks"],
        "category_scores": _category_scores(verdict),
        "tool_calls": len(trace["trace"]),
        "tokens": {"input": agent.get("n_input_tokens"), "cache": agent.get("n_cache_tokens"), "output": agent.get("n_output_tokens")},
        "cost_usd": agent.get("cost_usd"),
        "started_at": result.get("started_at"),
        "finished_at": result.get("finished_at"),
        "agent": result.get("agent_info"),
        "agent_config": config.get("agent"),
        "trace_source": f"{trial_dir.name}/verifier/trace.json (durable world call trace pulled by the packaged verifier)",
    }
    trial_record = {
        "schema_version": SCHEMA_VERSION,
        **receipt,
        "trace": [
            {"index": item["index"], "tool": item["tool"], "arguments": item.get("arguments") or {}, "success": item.get("success", True), "result": _compact_result(item.get("result"))}
            for item in trace["trace"]
        ],
    }
    return receipt, trial_record


def build_model_run(job_dir: Path, *, slug: str, label: str, allow_partial: bool, note: str | None = None) -> dict[str, Any]:
    publication = _read(PUBLICATION)
    job = _read(job_dir / "result.json")
    stats = job["stats"]
    trial_dirs = sorted(path for path in job_dir.iterdir() if path.is_dir() and "__" in path.name)
    receipts: list[dict[str, Any]] = []
    for trial_dir in trial_dirs:
        receipt, record = import_trial(trial_dir, publication)
        _write(MODEL_RUNS / slug / "trials" / f"{receipt['task_id']}.json", record)
        receipts.append(receipt)
    if not receipts:
        raise ValueError(f"{job_dir}: no completed trials")
    task_ids = [receipt["task_id"] for receipt in receipts]
    if len(set(task_ids)) != len(task_ids):
        raise ValueError("a task appears more than once; ranked runs are one attempt per task")
    errors = int(stats.get("n_errored_trials", 0))
    retries = int(stats.get("n_retries", 0))
    complete = len(receipts) == publication["harborTaskCount"]
    ranked = complete and errors == 0 and retries == 0
    if not ranked and not allow_partial:
        raise ValueError(
            f"run is not rankable (trials {len(receipts)}/{publication['harborTaskCount']}, errors {errors}, retries {retries}); pass --allow-partial to publish trajectories only"
        )
    agent = receipts[0]["agent"] or {}
    model = (agent.get("model_info") or {}).get("name") or "unknown"
    harness = f"harbor run -d {publication['harborDataset']}@{publication['harborTag']} -a {agent.get('name', 'agent')} {agent.get('version', '')} · model {model}".strip()
    categories: dict[str, list[float]] = {}
    for receipt in receipts:
        for key, value in receipt["category_scores"].items():
            categories.setdefault(key, []).append(value)
    run = {
        "schema_version": SCHEMA_VERSION,
        "slug": slug,
        "label": label,
        "harness": harness,
        "job": job_dir.name,
        "dataset": publication["harborDataset"],
        "version": publication["version"],
        "harbor_tag": publication["harborTag"],
        "ranked": ranked,
        "kind": "ranked" if ranked else "disclosed-partial",
        "note": note or ("" if ranked else f"Disclosed partial run: {len(receipts)} of {publication['harborTaskCount']} published tasks (one per family). Trajectories only — never ranked."),
        "published_tasks": publication["harborTaskCount"],
        "trials_completed": len(receipts),
        "errors": errors,
        "retries": retries,
        "mean_score": round(statistics.fmean(receipt["score"] for receipt in receipts), 2),
        "median_score": round(statistics.median(receipt["score"] for receipt in receipts), 2),
        "min_score": min(receipt["score"] for receipt in receipts),
        "max_score": max(receipt["score"] for receipt in receipts),
        "strict_passes": sum(1 for receipt in receipts if receipt["strict_pass"]),
        "strict_pass_rate": round(100.0 * sum(1 for receipt in receipts if receipt["strict_pass"]) / len(receipts), 2),
        "category_scores": {key: round(statistics.fmean(values), 2) for key, values in sorted(categories.items())},
        "mean_tool_calls": round(statistics.fmean(receipt["tool_calls"] for receipt in receipts), 1),
        "mean_cost_usd": round(statistics.fmean(receipt["cost_usd"] for receipt in receipts if receipt["cost_usd"] is not None), 4) if any(receipt["cost_usd"] is not None for receipt in receipts) else None,
        "total_cost_usd": round(sum(receipt["cost_usd"] or 0.0 for receipt in receipts), 4),
        "tokens": {
            "input": sum(receipt["tokens"]["input"] or 0 for receipt in receipts),
            "cache": sum(receipt["tokens"]["cache"] or 0 for receipt in receipts),
            "output": sum(receipt["tokens"]["output"] or 0 for receipt in receipts),
        },
        "trials": [
            {key: receipt[key] for key in ("task_id", "harbor_task", "trial", "harbor_task_checksum", "published_digest", "score", "strict_pass", "category_scores", "tool_calls", "tokens", "cost_usd", "trace_source")}
            for receipt in receipts
        ],
    }
    _write(MODEL_RUNS / slug / "run.json", run)
    return run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("job_dir", type=Path)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--note", default=None)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    run = build_model_run(args.job_dir, slug=args.slug, label=args.label, allow_partial=args.allow_partial, note=args.note)
    print(
        f"{run['slug']}: {run['kind']} — {run['trials_completed']}/{run['published_tasks']} tasks, mean HubScore {run['mean_score']}, "
        f"median {run['median_score']}, range {run['min_score']}–{run['max_score']}, strict {run['strict_passes']}, "
        f"mean cost ${run['mean_cost_usd']}, mean tool calls {run['mean_tool_calls']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
