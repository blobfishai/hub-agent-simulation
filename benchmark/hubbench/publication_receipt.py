#!/usr/bin/env python3
"""Write the latest and versioned publication receipts from actual artifacts — nothing typed by hand.

    python3 benchmark/hubbench/publication_receipt.py \
        --frozen ~/.cache/hubbench/v1.1.0/harbor \
        --gate-job ~/.cache/hubbench/jobs/hubbench-oracle-v1.1.0-full \
        --roundtrip-job ~/.cache/hubbench/jobs/hubbench-oracle-registry-roundtrip-v1.1.0 \
        --hf-api-json /path/to/api-datasets-SamuelChien821-hubbench-blobs.json \
        --hf-payload ~/.cache/hubbench/v1.1.0/huggingface \
        --source-repo ~/dev/hub-agent-simulation \
        --dataset-digest-prefix 210a56290f72 --published-at 2026-09-02

Inputs are the frozen tree that was published (its ``dataset.toml`` gives the
version and every task digest), the Docker oracle-gate job(s) that covered every
published task, the registry round-trip job, the Hugging Face ``?blobs=true`` API
listing (verified byte-for-byte against the frozen payload with
``benchmark/huggingface_receipts``), and the public source repository checkout.
The receipt refuses to be written unless every gate trial scored reward 1.0, every
published task was gated, the round-trip rewards are 1.0, and the Hugging Face
payload verifies exactly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

HUBBENCH_ROOT = Path(__file__).resolve().parent
BENCHMARK_ROOT = HUBBENCH_ROOT.parent
sys.path.insert(0, str(BENCHMARK_ROOT))

from huggingface_receipts import verify_hugging_face_publication  # noqa: E402
from hubbench.engine.distribution import harbor_task_digest, tree_digest  # noqa: E402

PUBLICATION = HUBBENCH_ROOT / "reports" / "publication.json"
PUBLICATIONS = HUBBENCH_ROOT / "reports" / "publications"
HARBOR_HUB = "https://hub.harborframework.com/datasets"
HF_DATASET = "SamuelChien821/hubbench"
SOURCE_REPOSITORY = "https://github.com/blobfishai/hub-agent-simulation"


def rewards(job_dir: Path) -> dict[str, float]:
    """``harbor task id -> reward`` for every finished trial in a Harbor job directory."""
    out: dict[str, float] = {}
    for path in sorted(job_dir.glob("*/verifier/reward.txt")):
        task = path.parent.parent.name.split("__", 1)[0]
        if task in out:
            raise ValueError(f"{job_dir.name}: task {task} appears twice; gate jobs must be one trial per task")
        out[task] = float(path.read_text(encoding="utf-8").strip())
    if not out:
        raise ValueError(f"{job_dir}: no finished trials")
    return out


def validated_job(job_dir: Path) -> tuple[dict[str, float], dict[str, Any]]:
    """Return rewards and Harbor stats only for a finished, zero-error, zero-retry job."""

    result_path = job_dir / "result.json"
    if not result_path.is_file():
        raise ValueError(f"{job_dir}: missing Harbor result.json")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if not result.get("finished_at"):
        raise ValueError(f"{job_dir.name}: Harbor job is not finished")
    stats = result.get("stats") or {}
    total = int(result.get("n_total_trials", -1))
    required_zero = (
        "n_errored_trials",
        "n_running_trials",
        "n_pending_trials",
        "n_cancelled_trials",
        "n_retries",
    )
    nonzero = {key: stats.get(key) for key in required_zero if stats.get(key) != 0}
    if nonzero:
        raise ValueError(f"{job_dir.name}: Harbor job is not clean: {nonzero}")
    if total < 1 or stats.get("n_completed_trials") != total:
        raise ValueError(
            f"{job_dir.name}: completed {stats.get('n_completed_trials')} of {total} scheduled trials"
        )
    job_rewards = rewards(job_dir)
    if len(job_rewards) != total:
        raise ValueError(f"{job_dir.name}: found {len(job_rewards)} rewards for {total} scheduled trials")
    return job_rewards, stats


def validated_frozen_release(frozen: Path, expected_root: str | None = None) -> dict[str, Any]:
    """Recompute package identities; a manifest's claimed digests are not evidence."""

    dataset = tomllib.loads((frozen / "dataset.toml").read_text(encoding="utf-8"))
    name, version = dataset["dataset"]["name"], dataset["dataset"]["version"]
    if name != "blobfishai/hubbench" or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("unexpected HubBench dataset identity or version")
    digests: dict[str, str] = {}
    for row in dataset["tasks"]:
        task = row["name"]
        if not re.fullmatch(r"blobfishai/hubbench-[a-z0-9]+-\d{3}", task) or task in digests:
            raise ValueError(f"invalid or duplicate frozen task: {task}")
        digests[task] = row["digest"]
    expected_tasks = {task.split("/", 1)[1] for task in digests}
    actual_tasks = {path.name for path in (frozen / "tasks").iterdir()}
    if not digests or expected_tasks != actual_tasks:
        raise ValueError("frozen task directories do not match the manifest")
    if any(path.is_symlink() for path in frozen.rglob("*")):
        raise ValueError("frozen releases must not contain symlinks")
    for task, expected in digests.items():
        directory = frozen / "tasks" / task.split("/", 1)[1]
        if (directory / ".gitignore").exists():
            raise ValueError(f"{task}: custom package ignore rules are not supported")
        digest, _, _ = harbor_task_digest(directory)
        if digest != expected:
            raise ValueError(f"{task}: frozen package digest mismatch")
        package = tomllib.loads((directory / "task.toml").read_text(encoding="utf-8"))
        if package["task"]["name"] != task or package["task"]["version"] != version:
            raise ValueError(f"{task}: package identity does not match the dataset")
    report_path = frozen.parent / "reports" / "release.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else None
    root, _, _ = tree_digest(frozen)
    if report is not None:
        if report.get("version") != version or report.get("harbor_root_sha256") != root:
            raise ValueError("frozen Harbor root does not match the release report")
    if expected_root is not None and root != expected_root:
        raise ValueError("frozen Harbor root does not match the expected digest")
    if report is None and expected_root is None:
        raise ValueError("a frozen release report or expected root digest is required")
    return {"name": name, "version": version, "digests": digests, "root": root, "report": report}


def _evidence_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        raise ValueError(f"missing trial evidence: {path}")
    raw = path.read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"expected an evidence object: {path}")
    return data, hashlib.sha256(raw).hexdigest()


def _canonical_oracle_config(config: dict[str, Any], trial: str) -> None:
    agent, environment, verifier = (config.get(key) or {} for key in ("agent", "environment", "verifier"))
    if agent.get("name") != "oracle" or environment.get("type") != "docker":
        raise ValueError(f"{trial}: requires the oracle agent and Docker environment")
    if verifier.get("disable") is not False or config.get("install_only") is not False:
        raise ValueError(f"{trial}: verifier must be enabled for an executed trial")
    forbidden = (
        (config, ("source_trial", "extra_instructions", "extra_instruction_paths", "extra_docker_compose", "skills")),
        (agent, ("import_path", "model_name", "skills", "resume_trajectory", "load_trajectory", "kwargs", "mcp_servers", "extra_allowed_hosts")),
        (environment, ("import_path", "mounts", "extra_docker_compose", "kwargs", "extra_allowed_hosts")),
    )
    for section, keys in forbidden:
        for key in keys:
            if section.get(key):
                raise ValueError(f"{trial}: noncanonical oracle configuration: {key}")


def validated_oracle_job(
    job_dir: Path, release: dict[str, Any], *, registry: bool = False
) -> tuple[dict[str, float], dict[str, Any], dict[str, Any]]:
    """Bind completed strict passes to frozen bytes using Harbor's durable task lock.

    ``task_checksum`` uses a different, deprecated directory hash. The lock's
    ``task.digest`` is the registry content identity, independently recomputed
    by ``validated_frozen_release`` before this function is called.
    """

    job_rewards, stats = validated_job(job_dir)
    evidence: dict[str, Any] = {}
    trial_dirs = sorted(path for path in job_dir.iterdir() if path.is_dir() and "__" in path.name)
    if len(trial_dirs) != len(job_rewards):
        raise ValueError(f"{job_dir.name}: unexpected or unfinished trial directories")
    for trial in trial_dirs:
        short_name = trial.name.split("__", 1)[0]
        name = f"blobfishai/{short_name}"
        digest = release["digests"].get(name)
        if digest is None or short_name in evidence:
            raise ValueError(f"{trial.name}: unknown or repeated frozen task")
        result, result_sha = _evidence_json(trial / "result.json")
        lock, lock_sha = _evidence_json(trial / "lock.json")
        trace, trace_sha = _evidence_json(trial / "verifier" / "trace.json")
        verdict, verdict_sha = _evidence_json(trial / "verifier" / "verdict.json")
        config, task = result.get("config") or {}, lock.get("task") or {}
        if not result.get("finished_at") or "exception_info" not in result or result["exception_info"] is not None:
            raise ValueError(f"{trial.name}: trial is unfinished or has an exception")
        if result.get("task_name") != name or result.get("trial_name") != trial.name or config.get("trial_name") != trial.name:
            raise ValueError(f"{trial.name}: trial/task identity mismatch")
        if lock.get("schema_version") != 2 or task.get("digest") != digest or task.get("version") != release["version"]:
            raise ValueError(f"{trial.name}: task lock does not match the frozen version and digest")
        kind = task.get("type")
        if kind not in ("local", "package") or task.get("name") != (name if kind == "package" else short_name):
            raise ValueError(f"{trial.name}: invalid task lock identity")
        if registry and (kind != "package" or task.get("source") != release["name"]):
            raise ValueError(f"{trial.name}: registry round-trip requires a registry package")
        if kind == "package":
            task_id = result.get("task_id") or {}
            configured_task = config.get("task") or {}
            if (
                task_id != {"org": "blobfishai", "name": short_name, "ref": digest}
                or configured_task.get("name") != name or configured_task.get("ref") != digest
                or result.get("source") != release["name"]
            ):
                raise ValueError(f"{trial.name}: registry result is not digest-pinned to the dataset")
        else:
            local_path = task.get("path")
            if (
                not local_path or Path(local_path).name != short_name
                or (result.get("task_id") or {}).get("path") != local_path
                or (config.get("task") or {}).get("path") != local_path
            ):
                raise ValueError(f"{trial.name}: local task path identity mismatch")
        _canonical_oracle_config(lock, trial.name)
        _canonical_oracle_config(config, trial.name)
        if (result.get("agent_info") or {}).get("name") != "oracle" or lock["verifier"].get("environment_mode") != "shared":
            raise ValueError(f"{trial.name}: missing canonical oracle/verifier identity")
        result_reward = (result.get("verifier_result") or {}).get("rewards", {}).get("reward")
        if isinstance(result_reward, bool) or result_reward != 1.0 or job_rewards.get(short_name) != 1.0:
            raise ValueError(f"{trial.name}: oracle reward is not exactly 1.0")
        task_id = short_name.removeprefix("hubbench-")
        if trace.get("task_id") != task_id or verdict.get("task_id") != task_id:
            raise ValueError(f"{trial.name}: trace/verdict task identity mismatch")
        if verdict.get("strict_pass") is not True or verdict.get("score") != 100.0 or not isinstance(trace.get("trace"), list) or not trace["trace"]:
            raise ValueError(f"{trial.name}: missing strict reference trajectory")
        evidence[short_name] = {
            "trial": trial.name, "task_id": task_id, "task_digest": digest,
            "result_sha256": result_sha, "lock_sha256": lock_sha,
            "trace_sha256": trace_sha, "verdict_sha256": verdict_sha,
            "trace": trace, "verdict": verdict,
        }
    return job_rewards, stats, evidence


def validated_release_gate(jobs: list[Path], release: dict[str, Any]) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """Admit exactly one successful trial for every frozen package across jobs."""

    gate: dict[str, float] = {}
    all_stats = []
    for job in jobs:
        job_rewards, stats, _ = validated_oracle_job(job, release)
        overlap = sorted(set(gate) & set(job_rewards))
        if overlap:
            raise ValueError(f"gate tasks appear in more than one job: {overlap}")
        gate.update(job_rewards)
        all_stats.append(stats)
    expected = {name.split("/", 1)[1] for name in release["digests"]}
    if set(gate) != expected:
        raise ValueError(f"gate coverage differs from frozen dataset: missing={sorted(expected - set(gate))}, extra={sorted(set(gate) - expected)}")
    return gate, all_stats


def validated_registry_roundtrip(job: Path, release: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
    rewards, stats, _ = validated_oracle_job(job, release, registry=True)
    expected_families = {name.split("-")[1] for name in release["digests"]}
    actual_families = {name.split("-")[1] for name in rewards}
    if actual_families != expected_families:
        raise ValueError(f"registry round-trip is missing families: {sorted(expected_families - actual_families)}")
    return rewards, stats


def hf_siblings(api: dict[str, Any]) -> list[dict[str, Any]]:
    """Map the raw REST listing (camelCase) onto the attribute names the receipt helper reads."""
    return [
        {**s, "blob_id": s.get("blobId"), "lfs": ({"sha256": s["lfs"].get("sha256") or s["lfs"].get("oid")} if s.get("lfs") else None)}
        for s in api["siblings"]
    ]


def validated_source_checkout(source: Path, frozen: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """Require the exact gated release in a clean, merged public source checkout."""

    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", "-C", str(source), *arguments], capture_output=True, text=True, check=True
        ).stdout.strip()

    if git("status", "--porcelain", "--untracked-files=all"):
        raise ValueError("source repository checkout is not clean")
    commit = git("rev-parse", "HEAD")
    url = git("remote", "get-url", "origin").removesuffix(".git")
    if url != SOURCE_REPOSITORY:
        raise ValueError("source repository origin is not the public HubBench repository")
    remote = git("ls-remote", "origin", "refs/heads/main").split()
    if len(remote) != 2 or remote[0] != commit or remote[1] != "refs/heads/main":
        raise ValueError("source commit is not the published main revision")
    release = validated_frozen_release(source / "benchmark" / "hubbench" / "release" / "harbor", frozen["root"])
    if release["version"] != frozen["version"] or release["report"] is None:
        raise ValueError("source release version/report differs from the frozen release")
    return commit, url, release["report"]


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    frozen = validated_frozen_release(args.frozen, args.harbor_root_sha256)
    name, version, digests = frozen["name"], frozen["version"], frozen["digests"]
    published_tasks = sorted(task.split("/", 1)[1] for task in digests)
    receipt = frozen["report"]

    gate, gate_stats = validated_release_gate(args.gate_job, frozen)
    round_trip, round_trip_stats = validated_registry_roundtrip(args.roundtrip_job, frozen)

    api = json.loads(args.hf_api_json.read_text(encoding="utf-8"))
    if api.get("id") != HF_DATASET:
        raise ValueError(f"Hugging Face listing is for {api.get('id')!r}, expected {HF_DATASET!r}")
    verification = verify_hugging_face_publication(args.hf_payload, hf_siblings(api), commit=api["sha"])

    source_commit, source_url, source_report = validated_source_checkout(args.source_repo, frozen)
    if not source_report or source_report.get("huggingface_manifest_sha256") != verification["payloadManifestSha256"]:
        raise ValueError("the source repository does not carry the verified Hugging Face release manifest")

    families = sorted({task.split("-")[1] for task in published_tasks})
    publication = {
        "schema_version": "hubbench.publication.v1",
        "publishedAt": args.published_at,
        "version": version,
        "harborDataset": name,
        "harborTag": f"v{version}",
        "harborDatasetUrl": f"{HARBOR_HUB}/{name}",
        "harborDatasetDigestPrefix": args.dataset_digest_prefix,
        "harborTaskCount": len(published_tasks),
        "harborTaskNamePattern": f"{name.split('/')[0]}/hubbench-<family>-NNN",
        "harborRootSha256": frozen["root"],
        "harborGate": {
            "jobs": [job.name for job in args.gate_job],
            "agent": "oracle",
            "environment": "docker (Colima)",
            "trials": len(published_tasks),
            "rewardOne": sum(1 for task in published_tasks if gate[task] == 1.0),
            "errors": sum(int(stats["n_errored_trials"]) for stats in gate_stats),
            "retries": sum(int(stats["n_retries"]) for stats in gate_stats),
            "cancelled": sum(int(stats["n_cancelled_trials"]) for stats in gate_stats),
            "exactTaskDigestsVerified": True,
            "method": "trial lock.task.digest compared with independently hashed frozen packages",
        },
        "registryRoundTrip": {
            "job": args.roundtrip_job.name,
            "tasks": [f"{name.split('/')[0]}/{task}" for task in sorted(round_trip)],
            "rewards": [round_trip[task] for task in sorted(round_trip)],
            "errors": int(round_trip_stats["n_errored_trials"]),
            "retries": int(round_trip_stats["n_retries"]),
            "cancelled": int(round_trip_stats["n_cancelled_trials"]),
            "exactTaskDigestsVerified": True,
        },
        "huggingFaceDataset": HF_DATASET,
        "huggingFaceUrl": f"https://huggingface.co/datasets/{HF_DATASET}",
        "huggingFaceRevision": api["sha"],
        "huggingFacePayloadManifestSha256": verification["payloadManifestSha256"],
        "huggingFaceVerification": {
            "files": verification["payloadFiles"],
            "bytes": verification["payloadBytes"],
            "gitBlobsVerified": verification["gitBlobsVerified"],
            "lfsObjectsVerified": verification["lfsObjectsVerified"],
            "exactObjectIdentity": verification["exactObjectIdentity"],
            "method": "benchmark/huggingface_receipts.verify_hugging_face_publication",
        },
        "sourceRepositoryUrl": source_url,
        "sourceRepositoryCommit": source_commit,
        "sourceRepositoryVerification": {
            "cleanCheckout": True, "publishedMainRevision": True, "exactHarborPackageIdentity": True,
        },
        "blobfishPage": "https://blobfish.ai/benchmarks/hubbench",
        "publishedFamilies": families,
        "publishedTasks": published_tasks,
        "publishedTaskDigests": dict(sorted(digests.items())),
    }
    if receipt and receipt["huggingface_manifest_sha256"] != verification["payloadManifestSha256"]:
        raise ValueError("the verified Hugging Face payload is not the frozen release payload")
    return publication


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--frozen", type=Path, required=True, help="frozen harbor/ directory that was published (holds dataset.toml)")
    parser.add_argument("--gate-job", type=Path, action="append", required=True, help="Docker oracle gate job directory (repeatable)")
    parser.add_argument("--check-gate", action="store_true", help="validate complete gate evidence (and round-trip if supplied), without writing or publishing")
    parser.add_argument("--roundtrip-job", type=Path)
    parser.add_argument("--hf-api-json", type=Path, help="saved https://huggingface.co/api/datasets/<id>?blobs=true listing")
    parser.add_argument("--hf-payload", type=Path, help="frozen huggingface/ payload that was uploaded")
    parser.add_argument("--source-repo", type=Path)
    parser.add_argument("--dataset-digest-prefix", help="digest prefix printed by `harbor publish` for the dataset")
    parser.add_argument("--published-at")
    parser.add_argument("--harbor-root-sha256", default=None, help="only when the frozen tree has no reports/release.json")
    parser.add_argument("--output", type=Path, default=PUBLICATION)
    args = parser.parse_args()
    if args.check_gate:
        frozen = validated_frozen_release(args.frozen, args.harbor_root_sha256)
        gate, _ = validated_release_gate(args.gate_job, frozen)
        round_trip = validated_registry_roundtrip(args.roundtrip_job, frozen)[0] if args.roundtrip_job else {}
        print(json.dumps({"version": frozen["version"], "harborRootSha256": frozen["root"], "exactGateTasks": len(gate), "exactRegistryTasks": len(round_trip)}, sort_keys=True))
        return 0
    required = ("roundtrip_job", "hf_api_json", "hf_payload", "source_repo", "dataset_digest_prefix", "published_at")
    missing = ["--" + field.replace("_", "-") for field in required if getattr(args, field) is None]
    if missing:
        parser.error("publication receipt requires " + ", ".join(missing))
    publication = build_receipt(args)
    rendered = json.dumps(publication, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    if args.output.resolve() == PUBLICATION.resolve():
        versioned = PUBLICATIONS / f"v{publication['version']}.json"
        versioned.parent.mkdir(parents=True, exist_ok=True)
        versioned.write_text(rendered, encoding="utf-8")
    print(f"wrote {args.output}: {publication['harborDataset']} v{publication['version']}, {publication['harborTaskCount']} tasks, HF {publication['huggingFaceRevision'][:12]}, source {publication['sourceRepositoryCommit'][:9]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
