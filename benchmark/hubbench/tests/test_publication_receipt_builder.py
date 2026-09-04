"""Fail-closed checks for Harbor job evidence used by publication receipts."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from hubbench.engine.distribution import harbor_task_digest, tree_digest
from hubbench.publication_receipt import validated_frozen_release, validated_job, validated_oracle_job, validated_release_gate, validated_registry_roundtrip, validated_source_checkout


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


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _frozen(tmp_path: Path, count: int = 1) -> Path:
    frozen = tmp_path / "release" / "harbor"
    rows = []
    for index in range(1, count + 1):
        name = f"blobfishai/hubbench-hostops-{index:03d}"
        task = frozen / "tasks" / name.split("/")[1]
        task.mkdir(parents=True)
        (task / "task.toml").write_text(f'[task]\nname = "{name}"\nversion = "1.4.0"\n')
        (task / "instruction.md").write_text("An independently frozen task.\n")
        digest, _, _ = harbor_task_digest(task)
        rows.append(f'[[tasks]]\nname = "{name}"\ndigest = "{digest}"\n')
    (frozen / "dataset.toml").write_text(
        '[dataset]\nname = "blobfishai/hubbench"\nversion = "1.4.0"\n' + "\n".join(rows)
    )
    root, _, _ = tree_digest(frozen)
    _json(frozen.parent / "reports" / "release.json", {"version": "1.4.0", "harbor_root_sha256": root})
    return frozen


def _bound_job(tmp_path: Path, frozen: Path, *, registry: bool = False) -> Path:
    release = validated_frozen_release(frozen)
    job = _job(tmp_path)
    for name, digest in release["digests"].items():
        short = name.split("/")[1]
        trial = job / f"{short}__trial"
        local_path = str(frozen / "tasks" / short)
        configured_task = {"name": name, "ref": digest} if registry else {"path": local_path}
        config = {
            "trial_name": trial.name, "task": configured_task, "install_only": False,
            "agent": {"name": "oracle"}, "environment": {"type": "docker"},
            "verifier": {"disable": False},
        }
        lock = {
            **config, "schema_version": 2,
            "task": {"name": name if registry else short, "version": "1.4.0", "digest": digest,
                     "type": "package" if registry else "local", "source": "blobfishai/hubbench" if registry else "tasks"},
            "verifier": {"disable": False, "environment_mode": "shared"},
        }
        if not registry:
            lock["task"]["path"] = local_path
        _json(trial / "lock.json", lock)
        _json(trial / "result.json", {
            "task_name": name, "trial_name": trial.name, "config": config,
            "task_id": {"org": "blobfishai", "name": short, "ref": digest} if registry else {"path": local_path},
            "source": "blobfishai/hubbench" if registry else "tasks",
            "finished_at": "2026-09-05T00:00:00Z", "exception_info": None,
            "agent_info": {"name": "oracle"}, "verifier_result": {"rewards": {"reward": 1.0}},
            "task_checksum": "a deliberately different deprecated hash",
        })
        task_id = short.removeprefix("hubbench-")
        _json(trial / "verifier" / "trace.json", {
            "task_id": task_id,
            "trace": [{"index": 0, "tool": "hubbench.task.submit", "arguments": {}, "result": {"ok": True}, "success": True}],
        })
        _json(trial / "verifier" / "verdict.json", {"task_id": task_id, "score": 100.0, "strict_pass": True})
        (trial / "verifier" / "reward.txt").write_text("1.0\n")
    result = json.loads((job / "result.json").read_text())
    result["n_total_trials"] = result["stats"]["n_completed_trials"] = len(release["digests"])
    _json(job / "result.json", result)
    return job


def _change(path: Path, key: str, value: object) -> None:
    data = json.loads(path.read_text())
    target = data
    fields = key.split(".")
    for field in fields[:-1]:
        target = target.setdefault(field, {})
    target[fields[-1]] = value
    _json(path, data)


@pytest.mark.parametrize("registry", [False, True])
def test_bound_gate_accepts_durable_identity_not_deprecated_checksum(tmp_path: Path, registry: bool):
    frozen = _frozen(tmp_path)
    release = validated_frozen_release(frozen)
    rewards, stats, evidence = validated_oracle_job(_bound_job(tmp_path, frozen, registry=registry), release, registry=registry)
    assert rewards == {"hubbench-hostops-001": 1.0}
    assert stats["n_completed_trials"] == 1
    assert evidence["hubbench-hostops-001"]["task_digest"] == release["digests"]["blobfishai/hubbench-hostops-001"]


@pytest.mark.parametrize(("file", "field", "value"), [
    ("lock.json", "task.digest", "sha256:" + "0" * 64),
    ("lock.json", "task.version", "1.3.0"),
    ("lock.json", "task.name", "hubbench-hostops-002"),
    ("lock.json", "schema_version", 1),
    ("lock.json", "source_trial", {"action": "regrade"}),
    ("lock.json", "extra_instructions", [{"path": "extra.md"}]),
    ("lock.json", "agent.name", "model-agent"),
    ("lock.json", "agent.skills", ["hidden-solution"]),
    ("lock.json", "environment.type", "remote"),
    ("lock.json", "environment.extra_docker_compose", ["override.yaml"]),
    ("lock.json", "verifier.disable", True),
    ("lock.json", "verifier.environment_mode", "fresh"),
    ("lock.json", "install_only", True),
    ("result.json", "finished_at", None),
    ("result.json", "exception_info", {"type": "ExecutionError"}),
    ("result.json", "task_name", "blobfishai/hubbench-hostops-002"),
    ("result.json", "trial_name", "hubbench-hostops-001__another"),
    ("result.json", "config.trial_name", "hubbench-hostops-001__another"),
    ("result.json", "config.source_trial", {"action": "regrade"}),
    ("result.json", "config.extra_instruction_paths", ["extra.md"]),
    ("result.json", "config.environment.mounts", ["/solution"]),
    ("result.json", "config.verifier.disable", True),
    ("result.json", "task_id.path", "/somewhere/else"),
    ("result.json", "agent_info.name", "model-agent"),
    ("result.json", "verifier_result.rewards.reward", 0.99),
    ("result.json", "verifier_result.rewards.reward", True),
    ("verifier/verdict.json", "task_id", "hostops-002"),
    ("verifier/verdict.json", "strict_pass", False),
    ("verifier/verdict.json", "score", 99),
    ("verifier/trace.json", "task_id", "hostops-002"),
    ("verifier/trace.json", "trace", []),
])
def test_bound_gate_rejects_mismatched_or_noncanonical_evidence(tmp_path: Path, file: str, field: str, value: object):
    frozen = _frozen(tmp_path)
    job = _bound_job(tmp_path, frozen)
    _change(job / "hubbench-hostops-001__trial" / file, field, value)
    with pytest.raises(ValueError):
        validated_oracle_job(job, validated_frozen_release(frozen))


@pytest.mark.parametrize("file", ["lock.json", "result.json", "verifier/trace.json", "verifier/verdict.json"])
def test_bound_gate_requires_all_trial_evidence(tmp_path: Path, file: str):
    frozen = _frozen(tmp_path)
    job = _bound_job(tmp_path, frozen)
    (job / "hubbench-hostops-001__trial" / file).unlink()
    with pytest.raises(ValueError, match="missing trial evidence"):
        validated_oracle_job(job, validated_frozen_release(frozen))


def test_local_gate_is_not_a_registry_round_trip(tmp_path: Path):
    frozen = _frozen(tmp_path)
    with pytest.raises(ValueError, match="requires a registry package"):
        validated_oracle_job(_bound_job(tmp_path, frozen), validated_frozen_release(frozen), registry=True)


@pytest.mark.parametrize("field", ["source", "task_id.ref", "config.task.ref", "config.task.name"])
def test_registry_gate_must_be_digest_pinned(tmp_path: Path, field: str):
    frozen = _frozen(tmp_path)
    job = _bound_job(tmp_path, frozen, registry=True)
    _change(job / "hubbench-hostops-001__trial" / "result.json", field, "wrong")
    with pytest.raises(ValueError, match="digest-pinned"):
        validated_oracle_job(job, validated_frozen_release(frozen), registry=True)


@pytest.mark.parametrize("change", ["package", "root", "duplicate", "extra-task", "ignore", "symlink", "report-version"])
def test_frozen_release_rejects_changed_or_ambiguous_bytes(tmp_path: Path, change: str):
    frozen = _frozen(tmp_path)
    task = frozen / "tasks" / "hubbench-hostops-001"
    if change == "package":
        (task / "instruction.md").write_text("Changed since freezing.\n")
    elif change == "root":
        (frozen / "README.md").write_text("Changed outside a task.\n")
    elif change == "duplicate":
        path = frozen / "dataset.toml"
        path.write_text(path.read_text() + '\n[[tasks]]\nname="blobfishai/hubbench-hostops-001"\ndigest="duplicate"\n')
    elif change == "extra-task":
        (frozen / "tasks" / "hubbench-extra-001").mkdir()
    elif change == "ignore":
        (task / ".gitignore").write_text("instruction.md\n")
    elif change == "symlink":
        (task / "linked.md").symlink_to(task / "instruction.md")
    else:
        _change(frozen.parent / "reports" / "release.json", "version", "1.3.0")
    with pytest.raises(ValueError):
        validated_frozen_release(frozen)


def test_imported_reference_version_requires_its_admitted_digest_bound_proof(tmp_path: Path, monkeypatch):
    from hubbench import site_data
    from hubbench.engine import distribution

    frozen = _frozen(tmp_path)
    job = _bound_job(tmp_path, frozen)
    reports = tmp_path / "reports"
    monkeypatch.setattr(site_data, "REPORTS", reports)
    monkeypatch.setattr(site_data, "REFERENCE_TRAJECTORIES", reports / "reference-trajectories")
    monkeypatch.setattr(distribution, "REPORTS_DIR", reports)
    assert site_data.import_gate(job, frozen) == 1
    record_path = reports / "reference-trajectories" / "hostops-001.json"
    record = json.loads(record_path.read_text())
    assert distribution.reference_source_version(record) == "1.4.0"
    for key, value in (("benchmark_version", "9.0.0"), ("task_digest", "wrong"), ("trace", [])):
        with pytest.raises(ValueError, match="admitted gate proof"):
            distribution.reference_source_version({**record, key: value})
    assert site_data.import_gate(job, frozen) == 1  # Exact reimports are idempotent.
    (reports / "gates" / "job.json").unlink()
    with pytest.raises(ValueError, match="no admitted gate proof"):
        distribution.reference_source_version(record)


def test_gate_import_validates_entire_batch_before_writing(tmp_path: Path, monkeypatch):
    from hubbench import site_data

    frozen = _frozen(tmp_path, count=2)
    job = _bound_job(tmp_path, frozen)
    reports = tmp_path / "reports"
    monkeypatch.setattr(site_data, "REPORTS", reports)
    monkeypatch.setattr(site_data, "REFERENCE_TRAJECTORIES", reports / "reference-trajectories")
    _change(job / "hubbench-hostops-002__trial" / "verifier" / "verdict.json", "score", 0)
    with pytest.raises(ValueError, match="missing strict reference trajectory"):
        site_data.import_gate(job, frozen)
    assert not reports.exists()


@pytest.mark.parametrize("case", ["clean", "dirty", "wrong-origin", "unmerged", "wrong-bytes"])
def test_source_checkout_must_be_clean_published_and_identical(tmp_path: Path, monkeypatch, case: str):
    from hubbench import publication_receipt

    frozen = validated_frozen_release(_frozen(tmp_path))
    source = tmp_path / "source"
    source_frozen = _frozen(source / "benchmark" / "hubbench")
    if case == "wrong-bytes":
        (source_frozen / "tasks" / "hubbench-hostops-001" / "instruction.md").write_text("Different source package.\n")

    def git(command: list[str], **kwargs):
        arguments = command[3:]
        outputs = {
            ("status", "--porcelain", "--untracked-files=all"): " M dirty.py" if case == "dirty" else "",
            ("rev-parse", "HEAD"): "a" * 40,
            ("remote", "get-url", "origin"): "https://github.com/other/repo.git" if case == "wrong-origin" else publication_receipt.SOURCE_REPOSITORY + ".git",
            ("ls-remote", "origin", "refs/heads/main"): ("b" if case == "unmerged" else "a") * 40 + "\trefs/heads/main\n",
        }
        return SimpleNamespace(stdout=outputs[tuple(arguments)])

    monkeypatch.setattr(publication_receipt.subprocess, "run", git)
    if case == "clean":
        commit, url, report = validated_source_checkout(source, frozen)
        assert commit == "a" * 40 and url == publication_receipt.SOURCE_REPOSITORY
        assert report["harbor_root_sha256"] == frozen["root"]
    else:
        with pytest.raises(ValueError):
            validated_source_checkout(source, frozen)


def test_release_gate_requires_exactly_once_complete_coverage(tmp_path: Path):
    frozen = _frozen(tmp_path)
    release = validated_frozen_release(frozen)
    job = _bound_job(tmp_path, frozen)
    assert len(validated_release_gate([job], release)[0]) == 1
    with pytest.raises(ValueError, match="more than one job"):
        validated_release_gate([job, job], release)
    larger = validated_frozen_release(_frozen(tmp_path / "larger", count=2))
    with pytest.raises(ValueError, match="gate coverage differs"):
        validated_release_gate([job], larger)


def test_registry_roundtrip_requires_every_frozen_family(tmp_path: Path):
    frozen = _frozen(tmp_path)
    release = validated_frozen_release(frozen)
    job = _bound_job(tmp_path, frozen, registry=True)
    assert len(validated_registry_roundtrip(job, release)[0]) == 1
    release["digests"]["blobfishai/hubbench-datadesk-001"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="missing families"):
        validated_registry_roundtrip(job, release)


def test_check_gate_cli_does_not_require_publication_or_write_files(tmp_path: Path, monkeypatch, capsys):
    from hubbench import publication_receipt

    frozen = _frozen(tmp_path)
    job = _bound_job(tmp_path, frozen)
    output = tmp_path / "must-not-write.json"
    monkeypatch.setattr(publication_receipt.sys, "argv", [
        "publication_receipt.py", "--frozen", str(frozen), "--gate-job", str(job),
        "--check-gate", "--output", str(output),
    ])
    assert publication_receipt.main() == 0
    assert json.loads(capsys.readouterr().out)["exactGateTasks"] == 1
    assert not output.exists()
