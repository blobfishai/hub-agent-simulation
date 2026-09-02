#!/usr/bin/env python3
"""Build the APEX-style explorer data for blobfish.ai/benchmarks/hubbench.

    python3 benchmark/hubbench/site_data.py                      # write the explorer JSON
    python3 benchmark/hubbench/site_data.py --import-gate <job>  # import Harbor oracle-gate traces first

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


def asset_url(pub: dict[str, Any], hf_task_id: str, path: str) -> str | None:
    if not pub.get("huggingFaceUrl"):
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
    if pub.get("huggingFaceUrl"):
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
    tools: dict[str, dict[str, Any]] = {}
    for entry in entries:
        for tool in entry["tools"]:
            name = tool["name"]
            record = tools.get(name)
            if record is None:
                meta = (tool.get("_meta") or {}).get("hubbench") or {}
                record = {
                    "name": name,
                    "title": (tool.get("annotations") or {}).get("title") or name,
                    "description": tool.get("description", ""),
                    "inputSchema": tool.get("inputSchema", {}),
                    "server": meta.get("server") or name.split(".", 1)[0],
                    "annotations": tool.get("annotations") or {},
                    "_meta": {"hubbench": {**meta, "families": [entry["slug"]]}},
                }
                tools[name] = record
            else:
                record["_meta"]["hubbench"]["families"].append(entry["slug"])
    return [tools[name] for name in sorted(tools)]


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


def trajectory_from_trace(task: dict[str, Any], family_tools: list[dict[str, Any]], trace: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, Any]:
    write_tools = {tool["name"] for tool in family_tools if not (tool.get("annotations") or {}).get("readOnlyHint", True)}
    events: list[dict[str, Any]] = [
        {"index": 0, "kind": "message", "role": "employee-request", "stage": "context", "text": task["instruction"]},
    ]
    seen_write = False
    calls = 0
    for record in trace:
        tool = record["tool"]
        stage = stage_for(tool, write_tools, seen_write)
        if stage == "write":
            seen_write = True
        calls += 1
        events.append({
            "index": len(events),
            "kind": "tool",
            "stage": stage,
            "call": calls,
            "tool": tool,
            "server": tool.split(".", 1)[0],
            "arguments": record.get("arguments") or {},
            "outcome": "ok" if record.get("success", True) else "error",
            "result": compact(record.get("result")),
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
        "stages": [stage for stage in stages if stage["key"] in used],
        "events": events,
    }


def import_gate(job_dir: Path) -> int:
    """Import Harbor oracle-gate trials as compact reference trajectories under reports/."""

    imported = 0
    for trial in sorted(job_dir.iterdir()):
        verifier = trial / "verifier"
        if not (verifier / "trace.json").is_file() or not (verifier / "verdict.json").is_file():
            continue
        trace = read_json(verifier / "trace.json")
        verdict = read_json(verifier / "verdict.json")
        task_id = trace["task_id"]
        config = read_json(trial / "config.json") if (trial / "config.json").is_file() else {}
        record = {
            "schema_version": "hubbench.reference-trajectory.v1",
            "task_id": task_id,
            "harbor_task": trial.name.split("__", 1)[0],
            "job": job_dir.name,
            "trial": trial.name,
            "agent": (config.get("agent") or {}).get("name") or "oracle",
            "score": verdict.get("score"),
            "strict_pass": verdict.get("strict_pass"),
            "reward": round(float(verdict.get("score", 0.0)) / 100.0, 6),
            "trace": [
                {"index": item["index"], "tool": item["tool"], "arguments": item.get("arguments") or {}, "success": item.get("success", True), "result": json.loads(compact(item.get("result"), 4000)) if isinstance(item.get("result"), (dict, list)) and len(json.dumps(item.get("result"))) <= 4000 else compact(item.get("result"), 4000)}
                for item in trace["trace"]
            ],
        }
        write_json(REFERENCE_TRAJECTORIES / f"{task_id}.json", record)
        imported += 1
    return imported


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
            trajectory = trajectory_from_trace(task, entry["tools"], trace["trace"], meta)
            if trial.get("cost_usd") is not None:
                trajectory["costUsd"] = trial["cost_usd"]
            if trial.get("tokens"):
                trajectory["tokens"] = trial["tokens"]
            trajectories.append(trajectory)
    rows.sort(key=lambda row: -float(row["score"]))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows, trajectories


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
    families_meta = [
        {"key": entry["slug"], "label": entry["family"].name, "count": len(entry["tasks"])}
        for entry in entries
    ]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "benchmark": {
            "name": BENCHMARK,
            "version": receipt.get("version", DEFAULT_VERSION),
            "tagline": "One oracle-proven Blobfish family per Harbor Hub professional-domain cluster, each a stateful multi-system world reachable as MCP servers, a REST API, a web console, and a terminal CLI.",
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
        "methodology": [],
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
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--import-gate", type=Path, default=None, help="Harbor job directory whose oracle trials become reference trajectories")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.import_gate is not None:
        print(f"imported {import_gate(args.import_gate)} reference trajectories -> {REFERENCE_TRAJECTORIES.relative_to(REPO_ROOT)}")
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
