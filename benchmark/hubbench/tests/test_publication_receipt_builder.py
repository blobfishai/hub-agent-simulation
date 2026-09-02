"""Fail-closed checks for Harbor job evidence used by publication receipts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hubbench.publication_receipt import validated_job


def _job(tmp_path: Path, **stats_overrides: int) -> Path:
    job = tmp_path / "job"
    trial = job / "hubbench-hostops-001__trial" / "verifier"
    trial.mkdir(parents=True)
    (trial / "reward.txt").write_text("1.0\n", encoding="utf-8")
    stats = {
        "n_completed_trials": 1,
        "n_errored_trials": 0,
        "n_running_trials": 0,
        "n_pending_trials": 0,
        "n_cancelled_trials": 0,
        "n_retries": 0,
    }
    stats.update(stats_overrides)
    (job / "result.json").write_text(
        json.dumps({"finished_at": "2026-09-02T00:00:00Z", "n_total_trials": 1, "stats": stats}),
        encoding="utf-8",
    )
    return job


def test_validated_job_accepts_exactly_one_clean_reward(tmp_path: Path):
    job_rewards, stats = validated_job(_job(tmp_path))
    assert job_rewards == {"hubbench-hostops-001": 1.0}
    assert stats["n_retries"] == 0


@pytest.mark.parametrize(
    "field",
    ["n_errored_trials", "n_running_trials", "n_pending_trials", "n_cancelled_trials", "n_retries"],
)
def test_validated_job_rejects_any_nonzero_failure_state(tmp_path: Path, field: str):
    with pytest.raises(ValueError, match="not clean"):
        validated_job(_job(tmp_path, **{field: 1}))


def test_validated_job_rejects_an_unfinished_or_incomplete_job(tmp_path: Path):
    job = _job(tmp_path, n_completed_trials=0)
    with pytest.raises(ValueError, match="completed 0 of 1"):
        validated_job(job)

    result_path = job / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["finished_at"] = None
    result_path.write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(ValueError, match="not finished"):
        validated_job(job)
