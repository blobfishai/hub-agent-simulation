"""ResearchDesk release, stateful provider rules, surfaces, and qualification."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from hubbench.engine.catalog import (
    read_standard,
    sealed_contract,
    sha256_json,
    shingle_jaccard,
    validate_tasks,
    word_count,
)
from hubbench.engine.evaluation import NEGATIVE_POLICIES, qualify
from hubbench.engine.families import load_family
from hubbench.engine.server import handle_request
from hubbench.engine.tasks import load_release_contract, load_release_tasks
from hubbench.engine.verifier import verify_episode
from hubbench.engine.world import World

HUBBENCH_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def research_family():
    return load_family("researchdesk")


@pytest.fixture(scope="module")
def research_tasks(research_family):
    tasks = load_release_tasks(research_family)
    assert len(tasks) == 8
    return tasks


@pytest.fixture(scope="module")
def research_contracts(research_family, research_tasks):
    return {
        task["task_id"]: load_release_contract(research_family, task["task_id"])
        for task in research_tasks
    }


def test_committed_release_matches_fresh_build(
    research_family, research_tasks, research_contracts
):
    fresh = research_family.build_tasks()
    assert [task["task_id"] for task in fresh] == [
        task["task_id"] for task in research_tasks
    ]
    for built, released in zip(fresh, research_tasks, strict=True):
        assert sha256_json(built) == sha256_json(released)
        assert sha256_json(sealed_contract(built)) == sha256_json(
            research_contracts[released["task_id"]]
        )


def test_release_meets_current_quality_bar(research_family, research_tasks):
    validate_tasks(research_tasks)
    requirements = read_standard()["requirements"]
    assert len(research_family.servers) == 11
    assert len(research_family.tools) == 30
    assert sorted(task["mode"] for task in research_tasks) == sorted(
        ["quantity"] * 3 + ["plan"] * 3 + ["schedule"] * 2
    )

    instructions = [task["instruction"] for task in research_tasks]
    signatures = [task["sequence_signature"] for task in research_tasks]
    assert len(instructions) == len(set(instructions))
    assert len(signatures) == len(set(signatures))
    for index, left in enumerate(instructions):
        for right in instructions[index + 1 :]:
            assert (
                shingle_jaccard(left, right)
                <= requirements["employeeRequest"]["maximumPairwiseFiveShingleJaccard"]
            )

    for task in research_tasks:
        assert (
            requirements["employeeRequest"]["minimumWords"]
            <= word_count(task["instruction"])
            <= requirements["employeeRequest"]["maximumWords"]
        )
        assert len(task["assets"]) == 30
        assert len({asset["media_type"] for asset in task["assets"]}) == 8
        assert len(task["required_investigations"]) == 26
        assert (
            60
            <= sum(len(item["criterion_ids"]) for item in task["rubric_milestones"])
            <= 62
        )
        assert len(task["expected"]["answer"]) >= 27


def test_open_source_anchors_are_exact_and_do_not_redistribute_upstream(research_tasks):
    expected = {"gaia/gaia", "kgmon/deepsearchqa", "openai/simpleqa"}
    for task in research_tasks:
        record = next(
            asset
            for asset in task["assets"]
            if asset["kind"] == "open_source_provenance"
        )
        payload = json.loads(record["content"])
        assert {anchor["harbor_dataset"] for anchor in payload["anchors"]} == expected
        assert payload["clean_room"] is True
        assert payload["upstream_tasks_copied"] is False
        assert payload["upstream_scores_claimed"] is False
        gaia = next(
            anchor
            for anchor in payload["anchors"]
            if anchor["harbor_dataset"] == "gaia/gaia"
        )
        assert gaia["distribution_note"].startswith("gated upstream")
        assert "license" not in gaia


def test_world_seeds_all_mock_systems(research_family, research_tasks, tmp_path):
    required_tables = {
        "knowledge_articles",
        "metric_definitions",
        "metric_snapshots",
        "source_sets",
        "source_records",
        "search_indexes",
        "search_hits",
        "review_slots",
        "approvals",
        "messages",
        "chat_threads",
        "drive_files",
        "research_claims",
        "evidence_packets",
        "review_reservations",
        "note_drafts",
    }
    for task in research_tasks:
        with World.fresh(
            research_family, task, tmp_path / f"{task['task_id']}.db"
        ) as world:
            tables = {
                row["name"]
                for row in world.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            assert required_tables <= tables
            assert world.connection.execute("PRAGMA foreign_key_check").fetchall() == []
            context = world.call_tool("hubbench.context.get", {})
            assert (
                context["reference_records"]["case_reference"]
                == f"RSH-{task['task_id'].rsplit('-', 1)[1].zfill(4)}"
            )
            assert len(context["evidence_index"]) == 30


def test_each_primary_write_shape_persists_and_reads_back(
    research_family, research_tasks, tmp_path
):
    for task in research_tasks[:3]:
        with World.fresh(
            research_family, task, tmp_path / f"write-{task['task_id']}.db"
        ) as world:
            create = next(
                step
                for step in task["oracle_steps"]
                if step["phase"] == "primary_mutation"
            )
            result = world.call_tool(create["tool"], create["arguments"])
            assert "error" not in result
            verification = task["post_write_verifications"][0]["any_of"][0]
            persisted = world.call_tool(verification["tool"], verification["arguments"])
            assert all(
                persisted[key] == value
                for key, value in verification["expected_result_contains"].items()
            )
            mutation = world.one(
                "SELECT table_name, status FROM mutations WHERE task_id = ?",
                (task["task_id"],),
            )
            assert (
                mutation["status"] == verification["expected_result_contains"]["status"]
            )


def test_provider_rules_fail_closed_on_stale_or_unauthorized_state(
    research_family, research_tasks, tmp_path
):
    expectations = (
        (research_tasks[0], "covers definition_id='logo_churn_v3'"),
        (research_tasks[1], "exactly the verified sources"),
        (research_tasks[2], "covers slot_id='SLOT-RSH-0003-QUALIFIED'"),
    )
    for task, message in expectations:
        with World.fresh(
            research_family, task, tmp_path / f"guard-{task['task_id']}.db"
        ) as world:
            control = task["negative_controls"]["unauthorized_write"]
            result = world.call_tool(control["tool"], control["arguments"])
            assert message in result["error"]
            assert (
                world.connection.execute("SELECT COUNT(*) FROM mutations").fetchone()[0]
                == 0
            )

    task = research_tasks[0]
    with World.fresh(research_family, task, tmp_path / "stale-definition.db") as world:
        control = task["negative_controls"]["unauthorized_write"]
        approval = world.one(
            "SELECT scope_json FROM approvals WHERE approval_id = ?",
            (control["arguments"]["approval_id"],),
        )
        scope = json.loads(approval["scope_json"])
        scope["definition_id"] = control["arguments"]["definition_id"]
        world.connection.execute(
            "UPDATE approvals SET scope_json = ? WHERE approval_id = ?",
            (json.dumps(scope, sort_keys=True), control["arguments"]["approval_id"]),
        )
        result = world.call_tool(control["tool"], control["arguments"])
        assert "stale definitions cannot be published" in result["error"]
        assert (
            world.connection.execute("SELECT COUNT(*) FROM mutations").fetchone()[0]
            == 0
        )

    task = research_tasks[2]
    with World.fresh(research_family, task, tmp_path / "protected-slot.db") as world:
        control = task["negative_controls"]["unauthorized_write"]
        approval = world.one(
            "SELECT scope_json FROM approvals WHERE approval_id = ?",
            (control["arguments"]["approval_id"],),
        )
        scope = json.loads(approval["scope_json"])
        scope["slot_id"] = control["arguments"]["slot_id"]
        world.connection.execute(
            "UPDATE approvals SET scope_json = ? WHERE approval_id = ?",
            (json.dumps(scope, sort_keys=True), control["arguments"]["approval_id"]),
        )
        result = world.call_tool(control["tool"], control["arguments"])
        assert "is protected" in result["error"]
        assert (
            world.connection.execute("SELECT COUNT(*) FROM mutations").fetchone()[0]
            == 0
        )


def test_mcp_surface_exposes_11_provider_servers_and_hides_verifier(
    research_family, research_tasks, tmp_path
):
    task = research_tasks[2]
    with World.fresh(research_family, task, tmp_path / "mcp.db") as world:
        init = handle_request(
            world, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        )
        assert init["result"]["serverInfo"] == {
            "name": "hubbench-researchdesk",
            "version": "1.0.0",
        }
        listing = handle_request(
            world, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        )
        tools = listing["result"]["tools"]
        names = {tool["name"] for tool in tools}
        assert len(tools) == 32
        assert {
            "research.claims.create",
            "research.packets.create",
            "reviews.reservations.create",
            "hubbench.submit_answer",
        } <= names
        assert not any(
            "verify" in name or "expected" in name or "contract" in name
            for name in names
        )
        contracts = research_family.server_contracts()
        assert len(contracts) == 12 and set(contracts) == {
            *research_family.servers,
            "hubbench",
        }
        assert sum(len(contract["tools"]) for contract in contracts.values()) == 32
        assert verify_episode(task, world)["strict_pass"] is False


def test_fresh_qualification_matches_committed_report(research_family, research_tasks):
    measured = qualify(research_family, research_tasks)
    committed = json.loads(
        (HUBBENCH_ROOT / "reports" / "researchdesk-qualification.json").read_text(
            encoding="utf-8"
        )
    )
    assert measured == committed
    assert measured["qualification_passed"] is True
    assert (
        measured["oracle"]["passes"] == 8 and measured["oracle"]["mean_score"] == 100.0
    )
    assert measured["determinism"]["exact_episode_matches"] == 8
    assert measured["mutation_omissions"]["all_detected"] is True
    assert set(measured["negative_controls"]) == set(NEGATIVE_POLICIES)
    assert measured["false_accepts"] == 0


def _load_chain_adapter():
    spec = importlib.util.spec_from_file_location(
        "hubbench_chain_adapter_researchdesk", HUBBENCH_ROOT / "chain_adapter.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_chain_report_is_current_and_covers_every_task():
    measured = _load_chain_adapter().measure_family("researchdesk")
    committed = json.loads(
        (HUBBENCH_ROOT / "reports" / "reasoning-chain" / "researchdesk.json").read_text(
            encoding="utf-8"
        )
    )
    assert measured == committed
    assert measured["passingTasks"] == measured["measuredTasks"] == 8
    assert measured["meetsStandard"] is True
    assert measured["chainDepth"] == {"min": 7, "max": 8}
    for hop in (f"H{i}" for i in range(1, 14)):
        assert measured["hopCoverage"][hop] >= 3
