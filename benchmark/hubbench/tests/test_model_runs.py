"""Imported model runs: fail-closed receipts, published-task binding, and never-ranked partials."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

HUBBENCH_ROOT = Path(__file__).resolve().parents[1]
MODEL_RUNS = HUBBENCH_ROOT / "model_runs"
PUBLICATION = HUBBENCH_ROOT / "reports" / "publication.json"
PUBLICATIONS = HUBBENCH_ROOT / "reports" / "publications"
RUNS = sorted(path for path in MODEL_RUNS.iterdir() if (path / "run.json").is_file()) if MODEL_RUNS.is_dir() else []

pytestmark = pytest.mark.skipif(not RUNS or not PUBLICATION.is_file(), reason="no imported model runs")


@pytest.mark.parametrize("run_dir", RUNS, ids=[path.name for path in RUNS])
def test_model_run_receipt_is_bound_and_honest(run_dir):
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    latest = json.loads(PUBLICATION.read_text(encoding="utf-8"))
    publication = json.loads((PUBLICATIONS / f"v{run['version']}.json").read_text(encoding="utf-8"))
    assert run["schema_version"] == "hubbench.model-run.v1"
    assert run["version"] == publication["version"]
    assert run["harbor_tag"] == publication["harborTag"]
    assert run["dataset"] == publication["harborDataset"]
    assert run["published_tasks"] == publication["harborTaskCount"]
    assert tuple(map(int, run["version"].split("."))) <= tuple(map(int, latest["version"].split(".")))
    assert run["trials_completed"] == len(run["trials"]) == len(list((run_dir / "trials").glob("*.json")))
    complete = run["trials_completed"] == run["published_tasks"] and run["errors"] == 0 and run["retries"] == 0
    assert run["ranked"] == complete
    assert run["kind"] == ("ranked" if complete else "disclosed-partial")
    if run["version"] != latest["version"]:
        assert not (run["ranked"] and run["published_tasks"] == latest["harborTaskCount"]), "historical runs cannot enter the current-release leaderboard"
    if not complete:
        assert "never ranked" in run["note"].lower()
    scores = []
    for trial in run["trials"]:
        assert trial["harbor_task"] in publication["publishedTasks"]
        assert trial["published_digest"] == publication["publishedTaskDigests"][f"{publication['harborDataset'].split('/')[0]}/{trial['harbor_task']}"]
        record = json.loads((run_dir / "trials" / f"{trial['task_id']}.json").read_text(encoding="utf-8"))
        assert record["score"] == trial["score"]
        assert record["tool_calls"] == trial["tool_calls"] == len(record["trace"])
        assert 0.0 <= trial["score"] <= 100.0
        assert trial["strict_pass"] == (trial["score"] == 100.0) or not trial["strict_pass"]
        scores.append(trial["score"])
    assert run["mean_score"] == round(sum(scores) / len(scores), 2)
    assert run["strict_passes"] == sum(1 for trial in run["trials"] if trial["strict_pass"])
