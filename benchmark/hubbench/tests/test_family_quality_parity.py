"""Portfolio-level quality parity for every released HubBench family.

Families are discovered from the committed release manifests
(``families/<slug>/release/manifest.json``): every family with a committed
release is held to the same contract without editing this file.
"""

from __future__ import annotations

import json
from pathlib import Path

from hubbench.engine.catalog import read_standard, validate_tasks
from hubbench.engine.evaluation import NEGATIVE_POLICIES
from hubbench.engine.families import CONTEXT_TOOL, SUBMIT_TOOL, load_family
from hubbench.engine.tasks import load_release_tasks

HUBBENCH_ROOT = Path(__file__).resolve().parents[1]
MINIMUM_TASKS_PER_FAMILY = 8
RELEASED_FAMILIES = tuple(
    sorted(path.parent.parent.name for path in (HUBBENCH_ROOT / "families").glob("*/release/manifest.json"))
)


def _released_portfolio():
    return {slug: load_release_tasks(load_family(slug)) for slug in RELEASED_FAMILIES}


def test_released_families_are_discovered_from_committed_manifests():
    assert {"clinicops", "hostops", "datadesk", "researchdesk"} <= set(RELEASED_FAMILIES)
    for slug in RELEASED_FAMILIES:
        manifest = json.loads((HUBBENCH_ROOT / "families" / slug / "release" / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["family"] == slug
        assert manifest["task_count"] >= MINIMUM_TASKS_PER_FAMILY


def test_all_released_families_clear_one_realism_contract():
    portfolio = _released_portfolio()
    for slug, tasks in portfolio.items():
        manifest = json.loads((HUBBENCH_ROOT / "families" / slug / "release" / "manifest.json").read_text(encoding="utf-8"))
        assert len(tasks) == manifest["task_count"] >= MINIMUM_TASKS_PER_FAMILY, slug
    all_tasks = [task for tasks in portfolio.values() for task in tasks]
    validate_tasks(all_tasks)

    requirements = read_standard()["requirements"]
    asset_rules = requirements["assetRoom"]
    workflow_rules = requirements["workflow"]
    rubric_rules = requirements["rubric"]
    chain_rules = requirements["reasoningChain"]
    for task in all_tasks:
        investigations = task["required_investigations"]
        calls = [item["any_of"][0] for item in investigations]
        assert len(task["assets"]) >= asset_rules["minimumAgentVisibleFilesPerTask"]
        assert (
            len({asset["media_type"] for asset in task["assets"]})
            >= asset_rules["minimumNativeFormatsPerTask"]
        )
        assert len(investigations) >= workflow_rules["minimumEvidenceReadsPerTask"]
        assert len(calls) >= workflow_rules["minimumProviderEvidenceReadsPerTask"]
        assert (
            sum(call["tool"] != CONTEXT_TOOL for call in calls)
            >= workflow_rules["minimumLiveDomainReadsPerTask"]
        )
        assert (
            len({call["tool"].split(".", 1)[0] for call in calls})
            >= workflow_rules["minimumIndependentEvidenceSources"]
        )
        assert (
            sum(len(item["criterion_ids"]) for item in task["rubric_milestones"])
            >= rubric_rules["minimumSpecificCriteriaPerTask"]
        )
        assert (
            len(task["expected"]["answer"]) >= chain_rules["minimumGradedAnswerFields"]
        )


def test_visible_artifacts_are_globally_unique_and_clean_room():
    all_tasks = [task for tasks in _released_portfolio().values() for task in tasks]
    ids = [asset["asset_id"] for task in all_tasks for asset in task["assets"]]
    digests = [asset["sha256"] for task in all_tasks for asset in task["assets"]]
    assert len(ids) == len(set(ids))
    assert len(digests) == len(set(digests))

    for task in all_tasks:
        provenance = next(
            asset
            for asset in task["assets"]
            if asset["kind"] == "open_source_provenance"
        )
        payload = json.loads(provenance["content"])
        assert payload["clean_room"] is True
        assert payload["upstream_tasks_copied"] is False
        assert payload["upstream_scores_claimed"] is False
        assert payload["anchors"]
        for anchor in payload["anchors"]:
            assert anchor["harbor_url"].startswith(
                "https://hub.harborframework.com/datasets/"
            )
            assert anchor["upstream_url"].startswith("https://")


def test_every_family_has_the_same_qualification_proof_shape():
    for slug, tasks in _released_portfolio().items():
        family = load_family(slug)
        task_count = len(tasks)
        mutating = family.write_tools - {SUBMIT_TOOL}
        reference_mutations = sum(
            1 for task in tasks for step in task["oracle_steps"] if step["tool"] in mutating
        )
        path = HUBBENCH_ROOT / "reports" / f"{slug}-qualification.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["qualification_passed"] is True
        assert report["task_count"] == task_count
        assert report["oracle"]["passes"] == task_count
        assert report["oracle"]["mean_score"] == 100.0
        assert report["determinism"]["exact_episode_matches"] == task_count
        assert report["false_accepts"] == 0
        assert report["mutation_omissions"]["total"] == reference_mutations
        assert report["mutation_omissions"]["detected"] == reference_mutations
        assert set(report["negative_controls"]) == set(NEGATIVE_POLICIES)
        assert all(
            control["executions"] == task_count
            for control in report["negative_controls"].values()
        )
        assert all(
            control["false_accepts"] == 0
            for control in report["negative_controls"].values()
        )
