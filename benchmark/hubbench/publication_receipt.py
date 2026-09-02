#!/usr/bin/env python3
"""Write ``reports/publication.json`` from the artifacts of an actual publication — nothing typed by hand.

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
import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

HUBBENCH_ROOT = Path(__file__).resolve().parent
BENCHMARK_ROOT = HUBBENCH_ROOT.parent
sys.path.insert(0, str(BENCHMARK_ROOT))

from huggingface_receipts import verify_hugging_face_publication  # noqa: E402

PUBLICATION = HUBBENCH_ROOT / "reports" / "publication.json"
HARBOR_HUB = "https://hub.harborframework.com/datasets"
HF_DATASET = "SamuelChien821/hubbench"


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


def hf_siblings(api: dict[str, Any]) -> list[dict[str, Any]]:
    """Map the raw REST listing (camelCase) onto the attribute names the receipt helper reads."""
    return [
        {**s, "blob_id": s.get("blobId"), "lfs": ({"sha256": s["lfs"].get("sha256") or s["lfs"].get("oid")} if s.get("lfs") else None)}
        for s in api["siblings"]
    ]


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    dataset = tomllib.loads((args.frozen / "dataset.toml").read_text(encoding="utf-8"))
    name = dataset["dataset"]["name"]
    version = dataset["dataset"]["version"]
    digests = {row["name"]: row["digest"] for row in dataset["tasks"]}
    published_tasks = sorted(task.split("/", 1)[1] for task in digests)
    receipt = json.loads((args.frozen.parent / "reports" / "release.json").read_text(encoding="utf-8")) if (args.frozen.parent / "reports" / "release.json").is_file() else None

    gate: dict[str, float] = {}
    gate_stats: list[dict[str, Any]] = []
    for job in args.gate_job:
        job_rewards, stats = validated_job(job)
        overlap = sorted(set(gate) & set(job_rewards))
        if overlap:
            raise ValueError(f"gate tasks appear in more than one job: {overlap}")
        gate.update(job_rewards)
        gate_stats.append(stats)
    missing = sorted(set(published_tasks) - set(gate))
    if missing:
        raise ValueError(f"published tasks without a Docker oracle gate trial: {missing}")
    unknown_gate = sorted(set(gate) - set(published_tasks))
    if unknown_gate:
        raise ValueError(f"gate jobs contain tasks outside the frozen dataset: {unknown_gate}")
    failed = sorted(task for task in published_tasks if gate[task] != 1.0)
    if failed:
        raise ValueError(f"gate trials below reward 1.0: {failed}")

    round_trip, round_trip_stats = validated_job(args.roundtrip_job)
    if any(value != 1.0 for value in round_trip.values()):
        raise ValueError(f"registry round-trip below 1.0: {round_trip}")
    unknown = sorted(set(round_trip) - set(published_tasks))
    if unknown:
        raise ValueError(f"round-trip ran unpublished tasks: {unknown}")

    api = json.loads(args.hf_api_json.read_text(encoding="utf-8"))
    if api.get("id") != HF_DATASET:
        raise ValueError(f"Hugging Face listing is for {api.get('id')!r}, expected {HF_DATASET!r}")
    verification = verify_hugging_face_publication(args.hf_payload, hf_siblings(api), commit=api["sha"])

    source_commit = subprocess.run(["git", "-C", str(args.source_repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    source_url = subprocess.run(["git", "-C", str(args.source_repo), "remote", "get-url", "origin"], capture_output=True, text=True, check=True).stdout.strip()
    source_url = source_url.removesuffix(".git")

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
        "harborRootSha256": receipt["harbor_root_sha256"] if receipt else args.harbor_root_sha256,
        "harborGate": {
            "jobs": [job.name for job in args.gate_job],
            "agent": "oracle",
            "environment": "docker (Colima)",
            "trials": len(published_tasks),
            "rewardOne": sum(1 for task in published_tasks if gate[task] == 1.0),
            "errors": sum(int(stats["n_errored_trials"]) for stats in gate_stats),
            "retries": sum(int(stats["n_retries"]) for stats in gate_stats),
            "cancelled": sum(int(stats["n_cancelled_trials"]) for stats in gate_stats),
        },
        "registryRoundTrip": {
            "job": args.roundtrip_job.name,
            "tasks": [f"{name.split('/')[0]}/{task}" for task in sorted(round_trip)],
            "rewards": [round_trip[task] for task in sorted(round_trip)],
            "errors": int(round_trip_stats["n_errored_trials"]),
            "retries": int(round_trip_stats["n_retries"]),
            "cancelled": int(round_trip_stats["n_cancelled_trials"]),
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
    parser.add_argument("--roundtrip-job", type=Path, required=True)
    parser.add_argument("--hf-api-json", type=Path, required=True, help="saved https://huggingface.co/api/datasets/<id>?blobs=true listing")
    parser.add_argument("--hf-payload", type=Path, required=True, help="frozen huggingface/ payload that was uploaded")
    parser.add_argument("--source-repo", type=Path, required=True)
    parser.add_argument("--dataset-digest-prefix", required=True, help="digest prefix printed by `harbor publish` for the dataset")
    parser.add_argument("--published-at", required=True)
    parser.add_argument("--harbor-root-sha256", default=None, help="only when the frozen tree has no reports/release.json")
    parser.add_argument("--output", type=Path, default=PUBLICATION)
    args = parser.parse_args()
    publication = build_receipt(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(publication, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.output}: {publication['harborDataset']} v{publication['version']}, {publication['harborTaskCount']} tasks, HF {publication['huggingFaceRevision'][:12]}, source {publication['sourceRepositoryCommit'][:9]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
