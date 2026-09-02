"""Write a family release tree: tasks, sealed contracts, evidence files, tools."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from .assets import asset_bytes
from .catalog import sealed_contract, sha256_json, validate_tasks
from .families import Family, public_tool_definitions
from .tasks import release_dir


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_release(family: Family, output: Path | None = None, tasks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build (or rebuild) the release tree and return its manifest."""

    output = output or release_dir(family)
    tasks = tasks if tasks is not None else family.build_tasks()
    validate_tasks(tasks)
    if output.exists():
        shutil.rmtree(output)
    entries = []
    for task in tasks:
        task_path = output / "tasks" / f"{task['task_id']}.json"
        contract = sealed_contract(task)
        _write_json(task_path, task)
        _write_json(output / "verifiers" / "contracts" / f"{task['task_id']}.json", contract)
        asset_digests = {}
        for record in task["assets"]:
            payload = asset_bytes(record)
            path = output / "assets" / task["task_id"] / record["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            asset_digests[record["path"]] = hashlib.sha256(payload).hexdigest()
        entries.append(
            {
                "task_id": task["task_id"],
                "mode": task["mode"],
                "title": task["title"],
                "role": task["role"],
                "task_sha256": sha256_json(task),
                "contract_sha256": sha256_json(contract),
                "asset_count": len(task["assets"]),
                "asset_kinds": sorted({record["kind"] for record in task["assets"]}),
                "assets": asset_digests,
                "atomic_criteria": sum(len(m["criterion_ids"]) for m in task["rubric_milestones"]),
                "graded_answer_fields": len(task["expected"]["answer"]),
                "reference_tool_calls": len(task["oracle_steps"]),
            }
        )
    tools = public_tool_definitions(family)
    _write_json(output / "tools.json", tools)
    manifest = {
        "schema_version": "hubbench.release.v1",
        "benchmark": "HubBench",
        "family": family.slug,
        "name": family.name,
        "version": family.version,
        "cluster": family.cluster,
        "description": family.description,
        "as_of": family.as_of,
        "task_count": len(tasks),
        "modes": dict(sorted(((mode, sum(1 for task in tasks if task["mode"] == mode)) for mode in {task["mode"] for task in tasks}))),
        "tool_count": len(tools),
        "tools": sorted(tool["name"] for tool in tools),
        "servers": sorted(family.servers),
        "tasks": entries,
        "fingerprint": sha256_json([entry["task_sha256"] for entry in entries]),
    }
    _write_json(output / "manifest.json", manifest)
    return manifest


__all__ = ["build_release"]
