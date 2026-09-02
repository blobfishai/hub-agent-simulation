"""Distribution emitter: Harbor packages, the Hugging Face payload, and receipts.

The committed ``benchmark/hubbench/release/`` tree must be byte-stable, every
Harbor package must be well formed and sealed (no verifier contract, expected
answer, oracle, or raw verifier token on an agent-visible surface), the
aggregate receipt must reconcile with the per-family reports, and the oracle
must score full marks THROUGH the public surfaces (MCP over HTTP, REST, the
``tool`` CLI, and the answer submission endpoint) of a locally started world
service — proving the package end to end without Docker.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import tomllib
import urllib.request
from pathlib import Path

import pytest

from hubbench.engine import distribution as dist
from hubbench.engine.families import load_family
from hubbench.engine.tasks import load_release_tasks

HUBBENCH_ROOT = Path(__file__).resolve().parents[1]
RELEASE = HUBBENCH_ROOT / "release"
HARBOR = RELEASE / "harbor"
TASK_DIRS = sorted(path for path in (HARBOR / "tasks").iterdir() if path.is_dir()) if (HARBOR / "tasks").is_dir() else []
REQUIRED_PACKAGE_FILES = (
    "task.toml",
    "instruction.md",
    "README.md",
    "environment/Dockerfile",
    "environment/Dockerfile.world",
    "environment/docker-compose.yaml",
    "environment/task.json",
    "environment/tools.json",
    "environment/tool",
    "environment/verifier-token.sha256",
    "tests/test.sh",
    "tests/verify.py",
    "tests/task.json",
    "tests/contract.json",
    "tests/verifier-token",
    "solution/solve.sh",
    "solution/solve.py",
)
TEXT_SUFFIXES = {".py", ".json", ".toml", ".md", ".yaml", ".yml", ".sha256", ".txt", ".csv", ".sql", ""}

pytestmark = pytest.mark.skipif(not TASK_DIRS, reason="benchmark/hubbench/release has not been built")


def _release_receipt() -> dict:
    return json.loads((RELEASE / "reports" / "release.json").read_text(encoding="utf-8"))


def _files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


def test_committed_distribution_is_byte_stable(tmp_path):
    rebuilt = tmp_path / "release"
    dist.build_distribution(rebuilt)
    committed = _files(RELEASE)
    fresh = _files(rebuilt)
    assert set(committed) == set(fresh)
    mismatched = sorted(name for name in committed if committed[name] != fresh[name])
    assert mismatched == []


def test_task_packages_are_well_formed_and_digests_reconcile():
    dataset = tomllib.loads((HARBOR / "dataset.toml").read_text(encoding="utf-8"))
    assert dataset["dataset"]["name"] == dist.HARBOR_DATASET
    assert dataset["dataset"]["version"] == _release_receipt()["version"]
    digests = {row["name"]: row["digest"] for row in dataset["tasks"]}
    names: set[str] = set()
    for task_dir in TASK_DIRS:
        toml = tomllib.loads((task_dir / "task.toml").read_text(encoding="utf-8"))
        name = toml["task"]["name"]
        names.add(name)
        assert toml["schema_version"] == "1.4"
        assert name == f"{dist.HARBOR_ORG}/{task_dir.name}", name
        assert toml["task"]["description"].strip()
        assert toml["agent"]["user"] == "agent"
        assert toml["verifier"]["user"] == "root"
        servers = [server["name"] for server in toml["environment"]["mcp_servers"]]
        assert dist.ENGINE_SERVER in servers, name
        assert all(server["transport"] == "streamable-http" for server in toml["environment"]["mcp_servers"])
        assert toml["metadata"]["benchmark"] == dist.BENCHMARK
        assert toml["metadata"]["synthetic"] is True
        for relative in REQUIRED_PACKAGE_FILES:
            assert (task_dir / relative).is_file(), f"{name}: missing {relative}"
        assert os.access(task_dir / "environment" / "tool", os.X_OK)
        assert os.access(task_dir / "tests" / "test.sh", os.X_OK)
        assert os.access(task_dir / "solution" / "solve.sh", os.X_OK)
        digest, _, _ = dist.harbor_task_digest(task_dir)
        assert digests[name] == digest, name
    assert names == set(digests)
    assert len(names) == len(TASK_DIRS) == _release_receipt()["totals"]["tasks"]
    # The registry treats a dataset whose name equals a task package name as a collision.
    assert dist.HARBOR_DATASET not in names


def test_agent_visible_surfaces_are_sealed():
    sealed_keys = set(dist.SEALED_TASK_KEYS)
    for task_dir in TASK_DIRS:
        public = json.loads((task_dir / "environment" / "task.json").read_text(encoding="utf-8"))
        assert not (set(public) & sealed_keys), task_dir.name
        engine = task_dir / "environment" / "hubbench" / "engine"
        present = {path.stem for path in engine.glob("*.py")}
        assert not (present & dist.SEALED_ENGINE_MODULES), task_dir.name
        assert "verifier" not in present, task_dir.name
        assert {"http", "world_service", "cli", "server", "world"} <= present, task_dir.name
        assert not (task_dir / "environment" / "hubbench" / "families" / task_dir.name.split("-")[1] / "release").exists()
        token = (task_dir / "tests" / "verifier-token").read_text(encoding="utf-8").strip()
        digest = (task_dir / "environment" / "verifier-token.sha256").read_text(encoding="utf-8").strip()
        assert hashlib.sha256(token.encode("utf-8")).hexdigest() == digest, task_dir.name
        for root in (task_dir / "environment", task_dir / "solution"):
            for path in root.rglob("*"):
                if path.is_file() and path.suffix in TEXT_SUFFIXES:
                    assert token not in path.read_text(encoding="utf-8", errors="ignore"), path
        contract = json.loads((task_dir / "tests" / "contract.json").read_text(encoding="utf-8"))
        assert contract, task_dir.name
    for path in (RELEASE / "huggingface" / "data").rglob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            assert not (set(row) & sealed_keys), path


def test_release_receipt_reconciles_with_family_reports():
    receipt = _release_receipt()
    families = dist.discover_families()
    totals = receipt["totals"]
    assert totals["families"] == len(families)
    assert totals["tasks"] == sum(len(load_release_tasks(load_family(slug))) for slug in families)
    for slug in families:
        for relative in (f"{slug}-qualification.json", f"reasoning-chain/{slug}.json"):
            shipped = json.loads((RELEASE / "reports" / relative).read_text(encoding="utf-8"))
            committed = json.loads((HUBBENCH_ROOT / "reports" / relative).read_text(encoding="utf-8"))
            assert shipped == committed, relative
    qualification = totals["qualification"]
    assert qualification["oracle_passes"] == totals["tasks"]
    assert qualification["false_accepts"] == 0
    assert qualification["qualification_passed"] is True
    assert totals["reasoning_chain"]["passing_tasks"] == totals["tasks"]
    assert receipt["harbor"]["task_count"] == totals["tasks"]
    harbor_root, root_files, root_bytes = dist.tree_digest(HARBOR)
    assert receipt["harbor_root_sha256"] == harbor_root
    assert receipt["harbor"]["root_files"] == root_files
    assert receipt["harbor"]["root_bytes"] == root_bytes
    manifest, _, _ = dist.payload_manifest(RELEASE / "huggingface")
    assert receipt["huggingface_manifest_sha256"] == manifest


def test_harbor_dataset_manifest_is_already_in_publisher_canonical_form():
    manifest = (HARBOR / "dataset.toml").read_text(encoding="utf-8")
    assert 'keywords = [ "hubbench",' in manifest
    assert ',]\n[[dataset.authors]]' in manifest
    assert 'name = "Blobfish AI"\n\n\n[[tasks]]' in manifest
    assert manifest.endswith("\n\n")


def test_hugging_face_payload_has_strict_reference_samples_for_published_and_candidate_families():
    index = json.loads((RELEASE / "huggingface" / "trajectories" / "index.json").read_text(encoding="utf-8"))
    publication = json.loads((HUBBENCH_ROOT / "reports" / "publication.json").read_text(encoding="utf-8"))
    assert index["schema_version"] == "hubbench.trajectory-index.v1"
    assert index["version"] == _release_receipt()["version"]
    samples = index["reference"]
    sample_families = {sample["family"] for sample in samples}
    published_families = set(publication["publishedFamilies"])
    discovered_families = set(dist.discover_families())
    assert published_families <= sample_families <= discovered_families
    if publication["version"] == index["version"]:
        assert sample_families == published_families
    for sample in samples:
        path = RELEASE / "huggingface" / "trajectories" / sample["path"]
        public = json.loads(path.read_text(encoding="utf-8"))
        assert public["task_id"] == sample["task_id"]
        assert public["strict_pass"] is True
        assert public["reward"] == 1.0
        assert public["score"] == 100.0
        assert public["sample_only"] is True
        assert public["leaderboard_eligible"] is False
        assert sample["sha256"] == dist.sha256_json(public)


def _free_ports() -> tuple[int, int]:
    """Choose distinct public/private ports before releasing either reservation."""

    with socket.socket() as public, socket.socket() as private:
        public.bind(("127.0.0.1", 0))
        private.bind(("127.0.0.1", 0))
        return public.getsockname()[1], private.getsockname()[1]


def _wait_ready(url: str, attempts: int = 120) -> None:
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.25)
    raise AssertionError(f"world service never became ready at {url}")


@pytest.mark.parametrize("slug", dist.discover_families())
def test_oracle_scores_full_marks_through_the_public_surfaces(slug, tmp_path):
    task_dir = next(path for path in TASK_DIRS if path.name.startswith(f"hubbench-{slug}-"))
    environment = task_dir / "environment"
    public_port, private_port = _free_ports()
    token_digest = (environment / "verifier-token.sha256").read_text(encoding="utf-8").strip()
    world = subprocess.Popen(
        [
            sys.executable, "-m", "hubbench.engine.world_service", "--family", slug, "--task", str(environment / "task.json"),
            "--db", str(tmp_path / "world.db"), "--fresh", "--host", "127.0.0.1", "--port", str(public_port), "--private-port", str(private_port),
        ],
        cwd=environment,
        env={**os.environ, "PYTHONPATH": str(environment), "HUBBENCH_VERIFIER_TOKEN_SHA256": token_digest, "PYTHONDONTWRITEBYTECODE": "1"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_ready(f"http://127.0.0.1:{public_port}/api/v1/task")
        solve = subprocess.run(
            [sys.executable, str(task_dir / "solution" / "solve.py")],
            cwd=task_dir / "solution",
            env={**os.environ, "HUBBENCH_URL": f"http://127.0.0.1:{public_port}", "HUBBENCH_TOOL": str(environment / "tool"), "HUBBENCH_RUNTIME": str(environment), "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert solve.returncode == 0, solve.stderr[-2000:]
        report = json.loads(solve.stdout.strip().splitlines()[-1])
        assert report["tool_errors"] == []
        assert {"mcp", "rest", "cli", "submit"} <= set(report["surfaces"])
        logs = tmp_path / "logs"
        verify = subprocess.run(
            [sys.executable, str(task_dir / "tests" / "verify.py")],
            cwd=task_dir / "tests",
            env={**os.environ, "HUBBENCH_VERIFIER_URL": f"http://127.0.0.1:{private_port}", "HUBBENCH_LOGS_DIR": str(logs), "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert verify.returncode == 0, verify.stderr[-2000:]
        assert (logs / "reward.txt").read_text(encoding="utf-8").strip() == "1.000000"
        verdict = json.loads((logs / "verdict.json").read_text(encoding="utf-8"))
        assert verdict["strict_pass"] is True
        # The private channel refuses the agent: no token, wrong token.
        for headers in ({}, {dist.TOKEN_HEADER if hasattr(dist, "TOKEN_HEADER") else "X-HubBench-Verifier-Token": "not-the-token"}):
            request = urllib.request.Request(f"http://127.0.0.1:{private_port}/verifier/trace", headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=5):
                    raise AssertionError("verifier channel answered without the token")
            except urllib.error.HTTPError as exc:
                assert exc.code in (401, 403)
    finally:
        world.terminate()
        try:
            world.wait(timeout=10)
        except subprocess.TimeoutExpired:
            world.kill()
