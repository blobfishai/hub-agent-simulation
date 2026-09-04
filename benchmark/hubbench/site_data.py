#!/usr/bin/env python3
"""Build the APEX-style explorer data for blobfish.ai/benchmarks/hubbench.

    python3 benchmark/hubbench/site_data.py                      # write the explorer JSON
    python3 benchmark/hubbench/site_data.py --import-gate <job> --frozen <release>/harbor --import-only

Emits ``products/website/app/benchmarks/hubbench/hubbench-explorer-data.json``
conforming to ``products/website/app/benchmarks/explorer/types.ts``
(``blobfish.benchmark-page.v1``): the task catalog with a full public sample
(prompt, evidence room, costed alternatives, graded milestones) for every task,
the tool contract of every family, the HubScore scoring categories, the
executed qualification controls (oracle + ten negative controls — never ranked
with models), reference trajectories imported from a Harbor oracle gate, model
trajectories and leaderboard rows from imported model runs, and distribution
links that exist only when ``reports/publication.json`` records them as live.
Every number is computed from the committed release, reports, and receipts.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

HUBBENCH_ROOT = Path(__file__).resolve().parent
BENCHMARK_ROOT = HUBBENCH_ROOT.parent
REPO_ROOT = BENCHMARK_ROOT.parent
sys.path.insert(0, str(BENCHMARK_ROOT))

from hubbench.engine.assets import asset_bytes  # noqa: E402
from hubbench.engine.catalog import sha256_json  # noqa: E402
from hubbench.engine.distribution import (  # noqa: E402
    BENCHMARK,
    DEFAULT_VERSION,
    HARBOR_DATASET,
    HF_DATASET,
    discover_families,
    harbor_task_id,
)
from hubbench.engine.families import CONTEXT_TOOL, SUBMIT_TOOL, load_family  # noqa: E402
from hubbench.engine.tasks import load_release_tasks  # noqa: E402
from hubbench.publication_receipt import validated_frozen_release, validated_oracle_job  # noqa: E402

OUTPUT = REPO_ROOT / "products" / "website" / "app" / "benchmarks" / "hubbench" / "hubbench-explorer-data.json"
REPORTS = HUBBENCH_ROOT / "reports"
REFERENCE_TRAJECTORIES = REPORTS / "reference-trajectories"
MODEL_RUNS = HUBBENCH_ROOT / "model_runs"
PUBLICATION = REPORTS / "publication.json"
RELEASE_RECEIPT = HUBBENCH_ROOT / "release" / "reports" / "release.json"
PAGE_URL = "https://blobfish.ai/benchmarks/hubbench"
SCHEMA_VERSION = "blobfish.benchmark-page.v1"
RESULT_LIMIT = 480

CATEGORY_COPY: dict[str, tuple[str, str]] = {
    "identity": ("Identity", "Establish the isolated task scope and immutable record identities before relying on similarly named records."),
    "investigation": ("Investigation", "Read the operative evidence — policy, request, and live records — before the first write."),
    "authority": ("Authority", "Respect approval tiers: what can be committed now versus what must be flagged for a director or owner."),
    "correlation": ("Correlation", "Reconcile the same fact across independent systems and set aside superseded, duplicate, or decoy records."),
    "procedure": ("Procedure", "Follow the required call order: every required investigation precedes the primary write, the readback follows it."),
    "decision": ("Decision", "Select the policy-supported option and state the binding constraint that drives it."),
    "alternatives": ("Alternatives", "Weigh every costed alternative with its exact outcome, incremental cost, and authority status."),
    "state": ("State change", "Commit the durable, task-scoped state change with the right payload, then read it back."),
    "answer": ("Answer", "Submit the exact graded answer fields, including every intermediate derivation."),
    "containment": ("Containment", "Change nothing outside the task's allowed tables; unrelated records stay untouched."),
}
CONTROL_COPY: dict[str, tuple[str, str]] = {
    "oracle": ("Oracle reference policy", "Replays the reference investigation, write, readback, draft, and answer. Must score 100 on every task."),
    "noop": ("Control: no-op", "Submits nothing. Establishes the floor for doing no work."),
    "shortcut": ("Control: answer only", "Submits the right answer without any investigation, write, or readback."),
    "state_only": ("Control: state only", "Makes the state change but never submits the graded answer."),
    "incomplete_read": ("Control: incomplete read", "Skips required evidence reads before deciding."),
    "write_before_read": ("Control: write before read", "Commits the state change before the required investigations."),
    "missing_readback": ("Control: missing readback", "Never reads its own write back."),
    "unauthorized_write": ("Control: unauthorized write", "Writes outside the task's allowed tables or past its authority."),
    "wrong_value": ("Control: wrong value", "Submits a plausible but wrong quantity or date."),
    "wrong_decision": ("Control: wrong decision", "Recommends an alternative the policy does not support."),
    "wrong_evidence": ("Control: wrong evidence", "Builds the answer from a superseded or decoy record."),
}
FORMAT_LABELS = {
    "text/markdown": "Markdown",
    "application/json": "JSON",
    "text/csv": "CSV",
    "application/x-yaml": "YAML",
    "text/yaml": "YAML",
    "application/yaml": "YAML",
    "application/pdf": "PDF",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "XLSX",
    "message/rfc822": "EML",
    "text/plain": "Text",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def compact(value: Any, limit: int = RESULT_LIMIT) -> str:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return text if len(text) <= limit else text[: limit - 1] + "…"


def bounds(values: list[int | float]) -> dict[str, float | int]:
    return {"min": min(values), "max": max(values)}


def format_label(media_type: str) -> str:
    return FORMAT_LABELS.get(media_type, media_type.rsplit("/", 1)[-1].upper())


def criteria_count(task: dict[str, Any]) -> int:
    return sum(len(milestone["criterion_ids"]) for milestone in task["rubric_milestones"])


def publication() -> dict[str, Any]:
    return read_json(PUBLICATION) if PUBLICATION.is_file() else {}


def live_links(pub: dict[str, Any]) -> dict[str, str]:
    links = {"blobfishPage": PAGE_URL}
    for key, field in (("harbor", "harborDatasetUrl"), ("huggingFace", "huggingFaceUrl"), ("source", "sourceRepositoryUrl")):
        if pub.get(field):
            links[key] = pub[field]
    return links


def is_published(pub: dict[str, Any], hf_task_id: str) -> bool:
    return bool(pub.get("huggingFaceUrl")) and hf_task_id in set(pub.get("publishedTasks") or [])


def asset_url(pub: dict[str, Any], hf_task_id: str, path: str) -> str | None:
    if not is_published(pub, hf_task_id):
        return None
    revision = pub.get("huggingFaceRevision") or "main"
    return f"{pub['huggingFaceUrl']}/blob/{revision}/assets/{hf_task_id}/{path}"


def load_families() -> list[dict[str, Any]]:
    entries = []
    for slug in discover_families():
        family = load_family(slug)
        tasks = load_release_tasks(family)
        release_dir = HUBBENCH_ROOT / "families" / slug / "release"
        tools = read_json(release_dir / "tools.json")
        manifest = read_json(release_dir / "manifest.json")
        qualification = read_json(REPORTS / f"{slug}-qualification.json")
        chain = read_json(REPORTS / "reasoning-chain" / f"{slug}.json")
        tables = sum(1 for line in family.schema_sql.splitlines() if line.strip().upper().startswith("CREATE TABLE"))
        entries.append({
            "slug": slug,
            "family": family,
            "tasks": tasks,
            "tools": tools,
            "manifest": manifest,
            "qualification": qualification,
            "chain": chain,
            "tables": tables,
        })
    return entries


def scoring_categories(all_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    weights: dict[str, float] = {}
    for task in all_tasks:
        for milestone in task["rubric_milestones"]:
            weights[milestone["category"]] = weights.get(milestone["category"], 0.0) + float(milestone["weight"])
    order = [key for key in CATEGORY_COPY if key in weights] + sorted(key for key in weights if key not in CATEGORY_COPY)
    categories = []
    for key in order:
        label, description = CATEGORY_COPY.get(key, (key.replace("_", " ").title(), f"Milestones graded under '{key}'."))
        categories.append({"key": key, "label": label, "weight": round(weights[key] / len(all_tasks), 1), "description": description})
    return categories


def task_summary(entry: dict[str, Any], task: dict[str, Any], ordinal: int, pub: dict[str, Any]) -> dict[str, Any]:
    hf_task_id = harbor_task_id(task)
    summary = {
        "id": task["task_id"],
        "ordinal": ordinal,
        "title": task["title"],
        "category": entry["slug"],
        "organization": task["world"]["name"],
        "asOf": task["as_of"],
        "summary": (
            f"{task['role']} · {task['mode']} decision · {len(task['assets'])} evidence files across "
            f"{len({asset['media_type'] for asset in task['assets']})} formats · {criteria_count(task)} deterministic checks · "
            f"{len(task['oracle_steps'])} reference tool calls."
        ),
        "documents": len(task["assets"]),
        "referenceToolCalls": len(task["oracle_steps"]),
        "sample": True,
    }
    if is_published(pub, hf_task_id):
        revision = pub.get("huggingFaceRevision") or "main"
        summary["datasetUrl"] = f"{pub['huggingFaceUrl']}/blob/{revision}/verifiers/{hf_task_id}.json"
    return summary


def task_sample(entry: dict[str, Any], task: dict[str, Any], categories: list[dict[str, Any]], pub: dict[str, Any]) -> dict[str, Any]:
    hf_task_id = harbor_task_id(task)
    investigations = task["required_investigations"]
    before_write = sum(1 for item in investigations if item.get("before_primary_mutation"))
    milestones = [
        {"id": milestone["id"], "category": milestone["category"], "description": milestone["description"]}
        for milestone in task["rubric_milestones"]
    ]
    options = [
        {
            "id": option["id"],
            "label": option.get("label") or option["id"],
            "reason": option.get("consequence") or option.get("reason") or "",
            "selected": bool(option.get("recommended")),
        }
        for option in task["decision_model"]["options"]
    ]
    assets = []
    for record in task["assets"]:
        try:
            size = len(asset_bytes(record))
        except Exception:  # pragma: no cover - binary assets always decode; keep the page build alive otherwise
            size = len(record.get("content", "").encode("utf-8"))
        asset = {
            "path": record["path"],
            "name": record.get("title") or record["path"],
            "format": format_label(record["media_type"]),
            "bytes": size,
            "preview": record.get("preview", ""),
            "role": record.get("kind", ""),
        }
        url = asset_url(pub, hf_task_id, record["path"])
        if url:
            asset["url"] = url
        assets.append(asset)
    weights: dict[str, float] = {}
    for milestone in task["rubric_milestones"]:
        weights[milestone["category"]] = weights.get(milestone["category"], 0.0) + float(milestone["weight"])
    scoring_weights = [
        {"key": category["key"], "label": category["label"], "weight": round(weights.get(category["key"], 0.0), 1), "description": category["description"]}
        for category in categories
        if weights.get(category["key"])
    ]
    return {
        "taskId": task["task_id"],
        "prompt": task["instruction"],
        "gradedCriteria": [f"{milestone['category']}: {milestone['description']}" for milestone in task["rubric_milestones"]],
        "evaluationNarrative": {
            "summary": (
                f"{task['title']} — a {task['mode']} decision for the {task['role']} at {task['world']['name']} as of {task['as_of']}. "
                f"Binding constraint: {task['decision_model']['binding_constraint']}"
            ),
            "success": f"Strict pass: {task['evaluation']['strict_pass']}. HubScore is the weighted share of {criteria_count(task)} deterministic checks across {len(milestones)} milestones; no LLM judge is involved.",
            "callOrderPolicy": (
                f"{before_write} of {len(investigations)} required investigations must precede the primary state change; "
                f"{len(task['post_write_verifications'])} post-write readback(s) must follow it; writes are contained to {len(task['allowed_write_tables'])} allowed tables."
            ),
            "milestones": milestones,
        },
        "decisionOptions": options,
        "assets": assets,
        "scoringWeights": scoring_weights,
    }


def tool_records(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Names are scoped to a family world, not to the portfolio. Even common
    # tools (such as submission) can require different fields in each family.
    tools: list[dict[str, Any]] = []
    for entry in entries:
        for tool in entry["tools"]:
            name = tool["name"]
            meta = (tool.get("_meta") or {}).get("hubbench") or {}
            tools.append({
                "name": name,
                "family": entry["slug"],
                "title": (tool.get("annotations") or {}).get("title") or name,
                "description": tool.get("description", ""),
                "inputSchema": tool.get("inputSchema", {}),
                "server": meta.get("server") or name.split(".", 1)[0],
                "annotations": tool.get("annotations") or {},
                "_meta": {"hubbench": {**meta, "families": [entry["slug"]]}},
            })
    return sorted(tools, key=lambda tool: (tool["family"], tool["server"], tool["name"]))


def evaluation_controls(entries: list[dict[str, Any]], total_tasks: int) -> list[dict[str, Any]]:
    rows = []
    policies = [policy["policy"] for policy in entries[0]["qualification"]["policies"]]
    for policy in policies:
        scores: list[float] = []
        strict = 0
        for entry in entries:
            record = next(item for item in entry["qualification"]["policies"] if item["policy"] == policy)
            scores.extend(float(value) for value in record["task_scores"].values())
            strict += int(record["strict_passes"])
        label, note = CONTROL_COPY.get(policy, (f"Control: {policy}", ""))
        rows.append({
            "rank": "—",
            "name": label,
            "harness": "hubbench.engine.evaluation (in-process qualification)",
            "kind": "reference",
            "tasks": len(scores),
            "score": round(statistics.fmean(scores), 2),
            "strictPassRate": round(100.0 * strict / len(scores), 2),
            "note": note,
        })
    assert all(row["tasks"] == total_tasks for row in rows)
    return rows


def stage_for(tool: str, write_tools: set[str], seen_write: bool) -> str:
    if tool == CONTEXT_TOOL:
        return "context"
    if tool == SUBMIT_TOOL:
        return "answer"
    if tool in write_tools:
        return "write"
    return "readback" if seen_write else "investigation"


def trajectory_from_trace(task: dict[str, Any], family_tools: list[dict[str, Any]], trace: list[dict[str, Any]], meta: dict[str, Any], *, result_limit: int = RESULT_LIMIT) -> dict[str, Any]:
    write_tools = {tool["name"] for tool in family_tools if not (tool.get("annotations") or {}).get("readOnlyHint", True)}
    events: list[dict[str, Any]] = [
        {"index": 0, "kind": "message", "role": "employee-request", "stage": "context", "text": task["instruction"]},
    ]
    seen_write = False
    calls = 0
    raw_calls = len(trace)
    collapsed: list[dict[str, Any]] = []
    for record in trace:
        previous = collapsed[-1] if collapsed else None
        if (
            previous is not None
            and record["tool"] == CONTEXT_TOOL
            and previous["tool"] == CONTEXT_TOOL
            and not (record.get("arguments") or {})
            and not (previous.get("arguments") or {})
        ):
            previous["_repeats"] = previous.get("_repeats", 1) + 1
            continue
        collapsed.append(dict(record))
    for record in collapsed:
        tool = record["tool"]
        stage = stage_for(tool, write_tools, seen_write)
        if stage == "write":
            seen_write = True
        calls += 1
        arguments = record.get("arguments") or {}
        if len(json.dumps(arguments, ensure_ascii=False)) > max(result_limit, 160):
            arguments = {"_compact": compact(arguments, max(result_limit, 160))}
        events.append({
            "index": len(events),
            "kind": "tool",
            "stage": stage,
            "call": calls,
            "tool": tool,
            "server": tool.split(".", 1)[0],
            "arguments": arguments,
            "outcome": "ok" if record.get("success", True) else "error",
            "result": (
                f"(repeated ×{record['_repeats']}: identical argument-free context reads collapsed — in v1.0.0 packages the compose "
                f"healthcheck polled the task endpoint through the graded trace; v1.1.0 probes the private /health endpoint) "
                if record.get("_repeats", 1) > 1
                else ""
            ) + compact(record.get("result"), result_limit),
        })
    stages = [{"key": key, "label": label} for key, label in (("context", "Context"), ("investigation", "Investigation"), ("write", "State change"), ("readback", "Readback"), ("answer", "Answer"))]
    used = {event.get("stage") for event in events}
    return {
        "taskId": task["task_id"],
        "model": meta["model"],
        "harness": meta["harness"],
        "kind": meta.get("kind", "reference"),
        "traceMode": "provider-native",
        "traceSource": meta.get("traceSource", "durable world call trace (verifier/trace.json)"),
        "passed": meta.get("passed"),
        "score": meta.get("score"),
        "toolCalls": calls,
        "rawToolCalls": raw_calls,
        "stages": [stage for stage in stages if stage["key"] in used],
        "events": events,
    }


def import_gate(job_dir: Path, frozen: Path) -> int:
    """Validate the whole package-bound gate before writing any reference records."""

    release = validated_frozen_release(frozen)
    _, stats, evidence = validated_oracle_job(job_dir, release)
    records = {}
    proof = {
        "schema_version": "hubbench.oracle-gate.v1",
        "job": job_dir.name,
        "dataset": release["name"],
        "version": release["version"],
        "harbor_root_sha256": release["root"],
        "agent": "oracle", "environment": "docker", "stats": stats,
        "trials": {},
    }
    for harbor_task, item in evidence.items():
        trace, verdict = item["trace"], item["verdict"]
        task_id = trace["task_id"]
        record = {
            "schema_version": "hubbench.reference-trajectory.v1",
            "benchmark_version": release["version"],
            "task_digest": item["task_digest"],
            "task_id": task_id,
            "harbor_task": harbor_task,
            "job": job_dir.name,
            "trial": item["trial"],
            "agent": "oracle",
            "score": verdict["score"],
            "strict_pass": verdict["strict_pass"],
            "reward": 1.0,
            "trace": [
                {"index": item["index"], "tool": item["tool"], "arguments": item.get("arguments") or {}, "success": item.get("success", True), "result": json.loads(compact(item.get("result"), 4000)) if isinstance(item.get("result"), (dict, list)) and len(json.dumps(item.get("result"))) <= 4000 else compact(item.get("result"), 4000)}
                for item in trace["trace"]
            ],
        }
        records[task_id] = record
        proof["trials"][harbor_task] = {
            **{key: value for key, value in item.items() if key not in ("trace", "verdict")},
            "reference_sha256": sha256_json(record),
        }
    proof_path = REPORTS / "gates" / f"{job_dir.name}.json"
    if proof_path.exists() and read_json(proof_path) != proof:
        raise ValueError(f"refusing to replace different evidence for {job_dir.name}")
    write_json(proof_path, proof)
    for task_id, record in records.items():
        write_json(REFERENCE_TRAJECTORIES / f"{task_id}.json", record)
    return len(records)


def reference_trajectories(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One reference trajectory per family (the lowest-numbered gated task)."""

    trajectories = []
    for entry in entries:
        for task in entry["tasks"]:
            path = REFERENCE_TRAJECTORIES / f"{task['task_id']}.json"
            if not path.is_file():
                continue
            record = read_json(path)
            meta = {
                "model": "Oracle reference policy",
                "harness": f"harbor run -a oracle ({record['job']}, Docker)",
                "kind": "reference",
                "passed": bool(record["strict_pass"]),
                "score": record["score"],
                "traceSource": f"{record['trial']}/verifier/trace.json",
            }
            trajectories.append(trajectory_from_trace(task, entry["tools"], record["trace"], meta))
            break
    return trajectories


def model_runs(entries: list[dict[str, Any]], total_tasks: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Leaderboard rows and model trajectories from imported model runs (``model_runs/<slug>/run.json``)."""

    rows: list[dict[str, Any]] = []
    trajectories: list[dict[str, Any]] = []
    if not MODEL_RUNS.is_dir():
        return rows, trajectories
    tasks_by_id = {task["task_id"]: (entry, task) for entry in entries for task in entry["tasks"]}
    for run_dir in sorted(path for path in MODEL_RUNS.iterdir() if (path / "run.json").is_file()):
        run = read_json(run_dir / "run.json")
        trials = run["trials"]
        if run.get("ranked") and len(trials) == total_tasks and run.get("errors", 0) == 0:
            rows.append({
                "rank": len(rows) + 1,
                "name": run["label"],
                "harness": run["harness"],
                "kind": "model",
                "tasks": len(trials),
                "score": run["mean_score"],
                "strictPassRate": run["strict_pass_rate"],
                "categoryScores": run.get("category_scores"),
                "averageCalls": run.get("mean_tool_calls"),
                "averageCost": run.get("mean_cost_usd"),
                "note": run.get("note"),
                "runUrl": run.get("run_url"),
            })
        for trial in trials:
            entry, task = tasks_by_id[trial["task_id"]]
            trace_path = run_dir / "trials" / f"{trial['task_id']}.json"
            if not trace_path.is_file():
                continue
            trace = read_json(trace_path)
            meta = {
                "model": run["label"],
                "harness": run["harness"],
                "kind": "model",
                "passed": bool(trial.get("strict_pass")),
                "score": trial.get("score"),
                "traceSource": trial.get("trace_source", "harbor trial receipt"),
            }
            trajectory = trajectory_from_trace(task, entry["tools"], trace["trace"], meta, result_limit=120)
            if trial.get("cost_usd") is not None:
                trajectory["costUsd"] = trial["cost_usd"]
            if trial.get("tokens"):
                trajectory["tokens"] = trial["tokens"]
            trajectories.append(trajectory)
    rows.sort(key=lambda row: -float(row["score"]))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows, trajectories


def model_run_summaries() -> list[dict[str, Any]]:
    if not MODEL_RUNS.is_dir():
        return []
    summaries = []
    for run_dir in sorted(path for path in MODEL_RUNS.iterdir() if (path / "run.json").is_file()):
        run = read_json(run_dir / "run.json")
        summaries.append({key: run[key] for key in ("slug", "label", "harness", "kind", "ranked", "version", "trials_completed", "published_tasks", "errors", "retries", "mean_score", "median_score", "min_score", "max_score", "strict_passes", "mean_cost_usd", "total_cost_usd", "mean_tool_calls", "note")})
    return summaries


COVERAGE_REPORT = BENCHMARK_ROOT / "reports" / "harbor-hub-coverage.json"
HF_CENSUS = BENCHMARK_ROOT / "reports" / "hf-dataset-census.json"


def methodology_sections(entries: list[dict[str, Any]], pub: dict[str, Any], receipt: dict[str, Any]) -> list[dict[str, str]]:
    """The explorer's methodology: admission gate, families, hub + Hugging Face census, surfaces, ranking rules — all computed."""

    all_tasks = [task for entry in entries for task in entry["tasks"]]
    quals = [entry["qualification"] for entry in entries]
    executions = sum(q["executions"] for q in quals)
    oracle = sum(q["oracle"]["passes"] for q in quals)
    controls = sum(sum(policy["task_count"] for policy in q["policies"] if policy["policy"] != "oracle") for q in quals)
    omissions = sum(q["mutation_omissions"]["detected"] for q in quals)
    omissions_total = sum(q["mutation_omissions"]["total"] for q in quals)
    chain_pass = sum(entry["chain"]["passingTasks"] for entry in entries)
    families_text = " ".join(
        f"{entry['family'].name} ({entry['family'].cluster}; {len(entry['tasks'])} tasks, {len(entry['family'].servers) + 1} mock servers, {len(entry['tools'])} tools, {entry['tables']} tables): {next((f['employeeQuestion'] for f in _coverage_families() if f['family'] == entry['slug']), '')}"
        for entry in entries
    )
    sections = [
        {
            "title": "Admission gate",
            "body": (
                f"Every released task passed the same gate before it counted: the reasoning-chain audit graded the full dependent chain "
                f"(hop classes H1–H13, depth 8), the packaged oracle scored a HubScore of exactly 100, a second execution reproduced that episode "
                f"byte for byte, and ten negative-control policies were rejected. Across {len(entries)} families the harness executed {executions:,} isolated "
                f"episodes: {oracle}/{len(all_tasks)} oracle strict passes, {controls:,} negative-control episodes with 0 false accepts, "
                f"{omissions}/{omissions_total} mutation omissions detected, chain audit {chain_pass}/{len(all_tasks)}. Numbers are recomputed from "
                f"the committed reports by the tests; nothing is typed by hand."
            ),
        },
        {
            "title": "HubScore",
            "body": (
                "A task's rubric is a set of milestones (identity, investigation, authority, correlation, procedure, decision, alternatives, state change, "
                "answer, containment), each made of atomic checks with fixed weights that sum to 100. Required investigations must precede the primary "
                "write and the readback must follow it; the graded answer covers every intermediate derivation, and writes outside the task's allowed "
                "tables cost containment. A strict pass means every milestone passes. There is no LLM judge and no prescribed call order."
            ),
        },
        {"title": f"The {len(entries)} released families", "body": families_text},
        {"title": "Harbor Hub census", "body": _hub_census_text()},
        {"title": "Hugging Face census", "body": _hf_census_text()},
        {
            "title": "Surfaces",
            "body": (
                "Every family world is one isolated SQLite database behind provider-shaped tools. The same world is reachable as MCP servers over stdio "
                "and over streamable HTTP (one endpoint per mock provider, the shape Harbor task packages mount), as a REST API, as a server-rendered web "
                "console with forms for every write tool, and as a terminal `tool` CLI — state written on one surface is visible on every other, and one "
                "session spread across surfaces grades as one episode. The sealed verifier contract, the expected answer, and the call trace are never "
                "readable on any surface."
            ),
        },
        {
            "title": "Ranking and disclosure",
            "body": (
                "A leaderboard row is admitted only when one Harbor job completes every published task of the tagged release exactly once with zero errors and "
                "zero retries; every trial is bound to the published dataset and task, its verdict must equal the Harbor reward, and its cost and token receipt "
                "is kept. Anything else is a disclosed partial run: its trajectories are published, its scores are never ranked. Qualification controls are "
                "shown below the ranked table and never receive ranks."
                + (
                    f" Published so far: {len(pub['publishedTasks'])} tasks in v{pub['version']} ({', '.join(pub['publishedFamilies'])}); newer families are queued for the next tagged release."
                    if pub.get("publishedTasks")
                    else ""
                )
            ),
        },
    ]
    return sections


def _coverage_families() -> list[dict[str, Any]]:
    if not COVERAGE_REPORT.is_file():
        return []
    return read_json(COVERAGE_REPORT).get("hubbench", {}).get("families", [])


def _hub_census_text() -> str:
    if not COVERAGE_REPORT.is_file():
        return "Coverage report not built."
    coverage = read_json(COVERAGE_REPORT)
    totals = coverage["totals"]
    filt = coverage.get("filter", {}).get("totals", coverage.get("filter", {}))
    return (
        f"On {coverage['observedAt']} the Harbor Hub listed {totals['datasets']} public datasets ({totals['tasks']:,} upstream tasks) in {totals['domainClusters']} professional-domain clusters. "
        f"Each dataset is classified by interface and domain: {filt.get('mcp', 0)} expose MCP or tool-calling surfaces, {filt.get('domainSpecific', 0)} sit in a professional domain, "
        f"{filt.get('selected', 0)} were selected (either), {filt.get('selectedAnd', 0)} both. These are historical domain-family mappings, not individually rebuilt datasets. "
        "HubBench publishes independently authored worlds for thirteen of these domain clusters; seed shapes are named per family for provenance and no upstream task is copied. "
        "The source catalog at /datasets separates current listings, license evidence, pending adaptations, and related released worlds."
    )


def _hf_census_text() -> str:
    if not HF_CENSUS.is_file():
        return "Hugging Face census not built."
    census = read_json(HF_CENSUS)
    total = census["platform"]["totalDatasets"]["value"]
    filt = census["filter"].get("totals", census["filter"])
    rows = census.get("datasets", [])
    return (
        f"The same filter applied to Hugging Face ({total:,} datasets on the platform): {len(rows)} agent-benchmark candidates surfaced by {len(census.get('queries', []))} fixed searches, "
        f"{filt.get('selected', 0)} selected ({filt.get('mcp', 0)} MCP or tool-calling, {filt.get('domainSpecific', 0)} domain-specific). "
        "These historical mappings are not source-specific adaptations. Recall was search-based, not exhaustive; the unfiltered pagination inventory and its completion status are available at /datasets."
    )


def build() -> dict[str, Any]:
    pub = publication()
    entries = load_families()
    all_tasks = [task for entry in entries for task in entry["tasks"]]
    categories = scoring_categories(all_tasks)
    receipt = read_json(RELEASE_RECEIPT) if RELEASE_RECEIPT.is_file() else {}
    tasks: list[dict[str, Any]] = []
    samples: dict[str, dict[str, Any]] = {}
    ordinal = 0
    for entry in entries:
        for task in entry["tasks"]:
            ordinal += 1
            tasks.append(task_summary(entry, task, ordinal, pub))
            samples[task["task_id"]] = task_sample(entry, task, categories, pub)
    tools = tool_records(entries)
    reference_calls = sorted(len(task["oracle_steps"]) for task in all_tasks)
    criteria = [criteria_count(task) for task in all_tasks]
    leaderboard, model_trajectories = model_runs(entries, len(all_tasks))
    trajectories = reference_trajectories(entries) + model_trajectories
    pins = [
        {"name": "Metric", "value": "HubScore — deterministic, contract-driven, 0 LLM-judge calls"},
        {"name": "Surfaces", "value": "MCP (stdio + streamable HTTP per server) · REST API · web console · terminal `tool` CLI — one SQLite world"},
        {"name": "Harbor dataset", "value": f"{HARBOR_DATASET} v{receipt.get('version', DEFAULT_VERSION)}"},
    ]
    if receipt:
        pins.append({"name": "Harbor root sha256", "value": receipt["harbor_root_sha256"]})
        pins.append({"name": "Hugging Face payload manifest", "value": receipt["huggingface_manifest_sha256"]})
    if pub.get("huggingFaceRevision"):
        pins.append({"name": "Hugging Face revision", "value": pub["huggingFaceRevision"]})
    if pub.get("publishedTasks"):
        published = len(pub["publishedTasks"])
        queued = len(all_tasks) - published
        pins.append({
            "name": "Published",
            "value": f"{published} of {len(all_tasks)} released tasks in v{pub['version']} ({', '.join(pub['publishedFamilies'])})"
            + (f"; {queued} newer tasks queued for the next tagged release" if queued else ""),
        })
    families_meta = [
        {"key": entry["slug"], "label": entry["family"].name, "count": len(entry["tasks"])}
        for entry in entries
    ]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "benchmark": {
            "name": BENCHMARK,
            "version": receipt.get("version", DEFAULT_VERSION),
            "tagline": "Thirteen oracle-proven professional-domain families inspired by the Harbor Hub inventory, with stateful worlds reachable as MCP servers, a REST API, a web console, and a terminal CLI. Source-specific adaptations are tracked separately.",
            "question": "Can an agent work a real employee decision across five to eleven connected systems — evidence, quantities, calendars, vendors, alternatives, a controlled write, its readback, and the exact answer — without a lookup shortcut?",
            "taskCount": len(all_tasks),
            "categoryNoun": "family",
            "categories": families_meta,
            "world": {
                "tools": len(tools),
                "tables": sum(entry["tables"] for entry in entries),
                "documents": sum(len(task["assets"]) for task in all_tasks),
            },
            "referenceCalls": {
                "min": reference_calls[0],
                "median": int(statistics.median(reference_calls)),
                "max": reference_calls[-1],
            },
            "checksPerTask": int(round(statistics.fmean(criteria))),
            "deterministicVerifier": True,
            "contractPins": pins,
            "links": live_links(pub),
        },
        "scoring": {"categories": categories, "strictPassTracked": True},
        "leaderboard": leaderboard,
        "evaluationControls": evaluation_controls(entries, len(all_tasks)),
        "tasks": tasks,
        "samples": samples,
        "tools": tools,
        "trajectories": trajectories,
        "methodology": methodology_sections(entries, pub, receipt),
        "_meta": {
            "families": [
                {
                    "slug": entry["slug"],
                    "name": entry["family"].name,
                    "cluster": entry["family"].cluster,
                    "tasks": len(entry["tasks"]),
                    "tools": len(entry["tools"]),
                    "servers": len(entry["family"].servers) + 1,
                    "tables": entry["tables"],
                    "oracle": entry["qualification"]["oracle"]["passes"],
                    "falseAccepts": entry["qualification"]["false_accepts"],
                    "chainPass": entry["chain"]["passingTasks"],
                }
                for entry in entries
            ],
            "criteriaPerTask": bounds(criteria),
            "assetFilesPerTask": bounds([len(task["assets"]) for task in all_tasks]),
            "nativeFormatsPerTask": bounds([len({asset["media_type"] for asset in task["assets"]}) for task in all_tasks]),
            "evidenceReadsPerTask": bounds([len(task["required_investigations"]) for task in all_tasks]),
            "gradedAnswerFieldsPerTask": bounds([len(task["expected"]["answer"]) for task in all_tasks]),
            "publication": pub,
            "modelRuns": model_run_summaries(),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--import-gate", type=Path, default=None, help="Harbor job directory whose oracle trials become reference trajectories")
    parser.add_argument("--frozen", type=Path, help="frozen harbor/ directory against which imported trials are verified")
    parser.add_argument("--import-only", action="store_true", help="import validated evidence without rebuilding public page data")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.import_only and args.import_gate is None:
        parser.error("--import-only requires --import-gate")
    if args.import_gate is not None:
        if args.frozen is None:
            parser.error("--import-gate requires --frozen")
        print(f"imported {import_gate(args.import_gate, args.frozen)} reference trajectories -> {REFERENCE_TRAJECTORIES.relative_to(REPO_ROOT)}")
        if args.import_only:
            return 0
    payload = build()
    write_json(args.output, payload)
    print(
        f"wrote {args.output.relative_to(REPO_ROOT) if args.output.is_relative_to(REPO_ROOT) else args.output}: "
        f"{payload['benchmark']['taskCount']} tasks, {len(payload['tools'])} tools, {len(payload['evaluationControls'])} controls, "
        f"{len(payload['leaderboard'])} leaderboard rows, {len(payload['trajectories'])} trajectories, "
        f"{args.output.stat().st_size // 1024} KB"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
