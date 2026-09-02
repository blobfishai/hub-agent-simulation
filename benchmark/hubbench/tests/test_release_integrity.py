"""Release integrity: committed tree equals a fresh build and meets the standard."""

from __future__ import annotations

import json
from pathlib import Path

from hubbench.engine.catalog import (
    read_standard,
    sealed_contract,
    sha256_json,
    shingle_jaccard,
    validate_tasks,
    word_count,
)

HUBBENCH_ROOT = Path(__file__).resolve().parents[1]


def test_committed_release_matches_fresh_build(
    family, released_tasks, released_contracts
):
    fresh = family.build_tasks()
    assert [task["task_id"] for task in fresh] == [
        task["task_id"] for task in released_tasks
    ]
    for built, released in zip(fresh, released_tasks):
        assert sha256_json(built) == sha256_json(released), (
            f"{released['task_id']} release is stale; rerun build_release.py"
        )
        assert sha256_json(sealed_contract(built)) == sha256_json(
            released_contracts[released["task_id"]]
        )


def test_release_meets_realism_standard(released_tasks):
    validate_tasks(released_tasks)
    standard = read_standard()["requirements"]
    for task in released_tasks:
        assert (
            standard["employeeRequest"]["minimumWords"]
            <= word_count(task["instruction"])
            <= standard["employeeRequest"]["maximumWords"]
        )
        assert (
            len(task["assets"])
            >= standard["assetRoom"]["minimumAgentVisibleFilesPerTask"]
        )
        assert (
            len({asset["media_type"] for asset in task["assets"]})
            >= standard["assetRoom"]["minimumNativeFormatsPerTask"]
        )
        assert (
            sum(len(m["criterion_ids"]) for m in task["rubric_milestones"])
            >= standard["rubric"]["minimumSpecificCriteriaPerTask"]
        )
        assert (
            len(task["required_investigations"])
            >= standard["workflow"]["minimumProviderEvidenceReadsPerTask"]
        )
        assert (
            len(task["expected"]["answer"])
            >= standard["reasoningChain"]["minimumGradedAnswerFields"]
        )


def test_prompts_and_sequences_are_distinct(released_tasks):
    instructions = [task["instruction"] for task in released_tasks]
    assert len(set(instructions)) == len(instructions)
    for index, left in enumerate(instructions):
        for right in instructions[index + 1 :]:
            assert shingle_jaccard(left, right) <= 0.8
    signatures = [task["sequence_signature"] for task in released_tasks]
    assert len(set(signatures)) == len(signatures)


def test_modes_cover_plan_quantity_schedule(released_tasks):
    modes = {task["mode"] for task in released_tasks}
    assert modes == {"plan", "quantity", "schedule"}


def test_reports_are_diff_stable(released_tasks):
    for name in (
        "reports/clinicops-qualification.json",
        "reports/reasoning-chain/clinicops.json",
    ):
        text = (HUBBENCH_ROOT / name).read_text(encoding="utf-8")
        assert "/Users/" not in text and "/home/" not in text
        payload = json.loads(text)
        assert text == json.dumps(payload, indent=2, sort_keys=True) + "\n"
