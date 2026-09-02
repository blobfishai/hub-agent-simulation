"""The publication receipt must describe exactly what was published — and the committed
release must still carry every published package byte-for-byte, even after newer
families were added on top of it."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

HUBBENCH_ROOT = Path(__file__).resolve().parents[1]
PUBLICATION = HUBBENCH_ROOT / "reports" / "publication.json"
RELEASE_RECEIPT = HUBBENCH_ROOT / "release" / "reports" / "release.json"
DATASET_TOML = HUBBENCH_ROOT / "release" / "harbor" / "dataset.toml"

pytestmark = pytest.mark.skipif(not PUBLICATION.is_file(), reason="HubBench has not been published yet")


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_publication_receipt_describes_the_published_release():
    publication = json.loads(PUBLICATION.read_text(encoding="utf-8"))
    receipt = json.loads(RELEASE_RECEIPT.read_text(encoding="utf-8"))
    assert publication["schema_version"] == "hubbench.publication.v1"
    assert _version(publication["version"]) <= _version(receipt["version"])
    assert publication["harborDataset"] == receipt["harbor"]["dataset"]
    assert publication["harborDatasetUrl"] == f"https://hub.harborframework.com/datasets/{publication['harborDataset']}"
    assert publication["harborTag"] == f"v{publication['version']}"
    assert re.fullmatch(r"[0-9a-f]{64}", publication["harborRootSha256"])
    assert re.fullmatch(r"[0-9a-f]{40}", publication["huggingFaceRevision"])
    assert publication["huggingFaceUrl"] == f"https://huggingface.co/datasets/{publication['huggingFaceDataset']}"
    verification = publication["huggingFaceVerification"]
    assert verification["exactObjectIdentity"] is True
    assert verification["files"] == verification["gitBlobsVerified"] + verification["lfsObjectsVerified"]
    assert re.fullmatch(r"[0-9a-f]{64}", publication["huggingFacePayloadManifestSha256"])
    assert publication["sourceRepositoryUrl"].startswith("https://github.com/blobfishai/")
    assert re.fullmatch(r"[0-9a-f]{7,40}", publication["sourceRepositoryCommit"])
    gate = publication["harborGate"]
    assert gate["trials"] == gate["rewardOne"] == publication["harborTaskCount"]
    assert gate["errors"] == gate["retries"] == gate["cancelled"] == 0
    round_trip = publication["registryRoundTrip"]
    assert round_trip["rewards"] and all(reward == 1.0 for reward in round_trip["rewards"])
    assert round_trip["errors"] == round_trip["retries"] == round_trip["cancelled"] == 0
    assert set(round_trip["tasks"]) <= set(publication["publishedTaskDigests"])


def test_every_published_package_is_still_in_the_committed_release_byte_for_byte():
    publication = json.loads(PUBLICATION.read_text(encoding="utf-8"))
    published = publication["publishedTaskDigests"]
    assert len(published) == publication["harborTaskCount"] == len(publication["publishedTasks"])
    assert set(publication["publishedTasks"]) == {name.split("/", 1)[1] for name in published}
    dataset = tomllib.loads(DATASET_TOML.read_text(encoding="utf-8"))
    current = {row["name"]: row["digest"] for row in dataset["tasks"]}
    assert set(published) <= set(current), "published packages vanished from the committed release"
    if dataset["dataset"]["version"] == publication["version"]:
        drifted = sorted(name for name, digest in published.items() if current.get(name) != digest)
        assert drifted == [], f"published packages changed under the same version: {drifted}"
    else:
        # The tree moved to the next tagged release; the published packages stay immutable in the registry.
        assert _version(dataset["dataset"]["version"]) > _version(publication["version"])
    families = {task_id.split("-")[1] for task_id in publication["publishedTasks"]}
    assert families == set(publication["publishedFamilies"])
