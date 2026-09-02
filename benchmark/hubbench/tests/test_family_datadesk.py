"""DataDesk family: release integrity, world mechanics, verifier, surfaces, chain audit."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
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
from hubbench.engine.evaluation import run_episode
from hubbench.engine.families import load_family
from hubbench.engine.server import handle_request
from hubbench.engine.tasks import load_release_contract, load_release_tasks
from hubbench.engine.verifier import verify_episode
from hubbench.engine.world import World

HUBBENCH_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = HUBBENCH_ROOT.parent


@pytest.fixture(scope="module")
def dd_family():
    return load_family("datadesk")


@pytest.fixture(scope="module")
def dd_tasks(dd_family):
    tasks = load_release_tasks(dd_family)
    assert len(tasks) == 8, "the committed datadesk release must hold 8 tasks"
    return tasks


@pytest.fixture(scope="module")
def dd_contracts(dd_family, dd_tasks):
    return {
        task["task_id"]: load_release_contract(dd_family, task["task_id"])
        for task in dd_tasks
    }


# --------------------------------------------------------------------------- #
# Release integrity and realism standard
# --------------------------------------------------------------------------- #


def test_committed_release_matches_fresh_build(dd_family, dd_tasks, dd_contracts):
    fresh = dd_family.build_tasks()
    assert [task["task_id"] for task in fresh] == [task["task_id"] for task in dd_tasks]
    for built, released in zip(fresh, dd_tasks):
        assert sha256_json(built) == sha256_json(released), (
            f"{released['task_id']} release is stale; rerun build_release.py"
        )
        assert sha256_json(sealed_contract(built)) == sha256_json(
            dd_contracts[released["task_id"]]
        )


def test_release_meets_realism_standard(dd_tasks):
    validate_tasks(dd_tasks)
    standard = read_standard()["requirements"]
    for task in dd_tasks:
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


def test_prompts_and_sequences_are_distinct(dd_tasks):
    instructions = [task["instruction"] for task in dd_tasks]
    assert len(set(instructions)) == len(instructions)
    for index, left in enumerate(instructions):
        for right in instructions[index + 1 :]:
            assert shingle_jaccard(left, right) <= 0.8
    signatures = [task["sequence_signature"] for task in dd_tasks]
    assert len(set(signatures)) == len(signatures)


def test_modes_cover_quantity_plan_schedule(dd_tasks):
    modes = [task["mode"] for task in dd_tasks]
    assert {"plan", "quantity", "schedule"} == set(modes)
    assert (
        modes.count("quantity") == 3
        and modes.count("plan") == 3
        and modes.count("schedule") == 2
    )


def test_reports_are_diff_stable():
    for name in (
        "reports/datadesk-qualification.json",
        "reports/reasoning-chain/datadesk.json",
    ):
        text = (HUBBENCH_ROOT / name).read_text(encoding="utf-8")
        assert "/Users/" not in text and "/home/" not in text
        payload = json.loads(text)
        assert text == json.dumps(payload, indent=2, sort_keys=True) + "\n"


def test_committed_qualification_report_passes():
    report = json.loads(
        (HUBBENCH_ROOT / "reports" / "datadesk-qualification.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["family"] == "datadesk" and report["task_count"] == 8
    assert report["qualification_passed"] is True
    assert report["oracle"]["passes"] == 8 and report["oracle"]["mean_score"] == 100.0
    assert report["determinism"]["deterministic"] is True
    assert report["false_accepts"] == 0
    assert report["mutation_omissions"] == {
        **report["mutation_omissions"],
        "total": 16,
        "detected": 16,
        "all_detected": True,
    }


# --------------------------------------------------------------------------- #
# World mechanics
# --------------------------------------------------------------------------- #


def test_world_builds_and_seeds_every_task(dd_family, dd_tasks, tmp_path):
    for task in dd_tasks:
        with World.fresh(dd_family, task, tmp_path / f"{task['task_id']}.db") as world:
            tables = {
                row["name"]
                for row in world.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            for expected in (
                "models",
                "model_lineage",
                "pipeline_runs",
                "feed_deliveries",
                "warehouse_slots",
                "run_schedules",
                "mutations",
                "answers",
                "call_trace",
            ):
                assert expected in tables
            assert (
                world.connection.execute(
                    "SELECT COUNT(*) FROM warehouse_slots"
                ).fetchone()[0]
                > 0
            )
            assert world.connection.execute("PRAGMA foreign_key_check").fetchall() == []
            context = world.call_tool("hubbench.context.get", {})
            assert (
                context["reference_records"]["case_reference"]
                == f"DATA-{task['task_id'].rsplit('-', 1)[1].zfill(4)}"
            )
            assert len(context["evidence_index"]) == len(task["assets"])


def test_writes_persist_and_readbacks_reflect_them(dd_family, dd_tasks, tmp_path):
    task = dd_tasks[1]  # datadesk-002: backfill create
    with World.fresh(dd_family, task, tmp_path / "write.db") as world:
        create = next(
            step for step in task["oracle_steps"] if step["phase"] == "primary_mutation"
        )
        result = world.call_tool(create["tool"], create["arguments"])
        assert result.get("error") is None and result["job_id"] == "BF-7101"
        readback = world.call_tool("pipelines.backfills.get", {"job_id": "BF-7101"})
        assert (
            readback["status"] == "SCHEDULED"
            and readback["cluster_id"] == "WH-STD"
            and readback["partitions"] == 4
        )
        slot = world.one(
            "SELECT status, job_id FROM warehouse_slots WHERE slot_id = 'SLOT-STD-20260312-DAY'"
        )
        assert slot == {"status": "busy", "job_id": "BF-7101"}
        mutation = world.one(
            "SELECT mutation_id, table_name FROM mutations WHERE task_id = ?",
            (task["task_id"],),
        )
        assert mutation == {
            "mutation_id": f"{task['task_id']}-mutation-01",
            "table_name": "backfill_jobs",
        }


def test_provider_rules_reject_unauthorized_writes(dd_family, dd_tasks, tmp_path):
    protected = dd_tasks[1]  # backfill into a protected close window
    with World.fresh(dd_family, protected, tmp_path / "protected.db") as world:
        result = world.call_tool(
            protected["negative_controls"]["unauthorized_write"]["tool"],
            protected["negative_controls"]["unauthorized_write"]["arguments"],
        )
        assert "error" in result and "protected" in result["error"]
    over_cap = dd_tasks[0]  # adjustment above the signed row maximum
    with World.fresh(dd_family, over_cap, tmp_path / "overcap.db") as world:
        result = world.call_tool(
            over_cap["negative_controls"]["unauthorized_write"]["tool"],
            over_cap["negative_controls"]["unauthorized_write"]["arguments"],
        )
        assert "error" in result and "exceeds the signed scope" in result["error"]
    sandbox = dd_tasks[4]  # backfill on the non-capable sandbox cluster
    with World.fresh(dd_family, sandbox, tmp_path / "sandbox.db") as world:
        result = world.call_tool(
            sandbox["negative_controls"]["unauthorized_write"]["tool"],
            sandbox["negative_controls"]["unauthorized_write"]["arguments"],
        )
        assert "error" in result and "not backfill-capable" in result["error"]


def test_adjustments_without_covering_control_fail_closed(
    dd_family, dd_tasks, tmp_path
):
    task = dd_tasks[0]
    with World.fresh(dd_family, task, tmp_path / "nocontrol.db") as world:
        arguments = dict(
            next(
                step
                for step in task["oracle_steps"]
                if step["phase"] == "primary_mutation"
            )["arguments"]
        )
        arguments.update({"period_start": "2026-02-02", "period_end": "2026-02-06"})
        result = world.call_tool("recon.adjustments.create", arguments)
        assert "error" in result and "no published control total" in result["error"]
        assert "error" in world.call_tool(
            "warehouse.models.get", {"model_id": "MDL-NOPE"}
        )
        assert "error" in world.call_tool("warehouse.models.destroy", {})


def test_transient_faults_are_deterministic_and_retryable(
    dd_family, dd_tasks, tmp_path
):
    task = copy.deepcopy(dd_tasks[0])
    task["transient_faults"] = [
        {
            "tool": "feeds.deliveries.list",
            "error": "ingestion metadata service unavailable (503)",
            "failures": 1,
        }
    ]
    with World.fresh(dd_family, task, tmp_path / "fault.db") as world:
        first = world.call_tool("feeds.deliveries.list", {"feed_id": "FEED-SKY-ORD"})
        assert first == {
            "error": "ingestion metadata service unavailable (503)",
            "retryable": True,
        }
        second = world.call_tool("feeds.deliveries.list", {"feed_id": "FEED-SKY-ORD"})
        assert "deliveries" in second


# --------------------------------------------------------------------------- #
# Verifier and controls
# --------------------------------------------------------------------------- #


def test_oracle_passes_every_released_task(dd_family, dd_tasks, tmp_path):
    for task in dd_tasks:
        episode = run_episode(
            dd_family, task, "oracle", tmp_path / f"oracle-{task['task_id']}.db"
        )
        assert episode["strict_pass"], {
            check["id"]: check["evidence"]
            for check in episode["checks"]
            if not check["passed"]
        }
        assert episode["score"] == 100.0


def test_wrong_value_control_is_rejected(dd_family, dd_tasks, tmp_path):
    episode = run_episode(
        dd_family, dd_tasks[0], "wrong_value", tmp_path / "wrong-value.db"
    )
    assert not episode["strict_pass"] and episode["score"] < 100.0
    failed = {check["id"] for check in episode["checks"] if not check["passed"]}
    assert "analysis.inputs" in failed or "answer.insights" in failed


def test_unauthorized_write_control_is_rejected(dd_family, dd_tasks, tmp_path):
    for task in (dd_tasks[0], dd_tasks[2]):
        episode = run_episode(
            dd_family,
            task,
            "unauthorized_write",
            tmp_path / f"unauth-{task['task_id']}.db",
        )
        assert not episode["strict_pass"], task["task_id"]


def test_noop_scores_near_zero(dd_family, dd_tasks, tmp_path):
    episode = run_episode(dd_family, dd_tasks[5], "noop", tmp_path / "noop.db")
    assert episode["score"] < 10.0


def test_verifier_never_reachable_through_tools(dd_family, dd_tasks, tmp_path):
    task = dd_tasks[0]
    with World.fresh(dd_family, task, tmp_path / "sealed.db") as world:
        names = {tool["name"] for tool in world.tool_definitions()}
        assert not any(
            "verify" in name or "expected" in name or "contract" in name
            for name in names
        )
        result = world.call_tool("hubbench.context.get", {})
        rendered = str(result)
        assert "expected" not in rendered and "oracle_steps" not in rendered
        verification = verify_episode(task, world)
        assert verification["strict_pass"] is False  # nothing done yet


# --------------------------------------------------------------------------- #
# Surfaces
# --------------------------------------------------------------------------- #


def test_mcp_handshake_and_tool_call_in_process(dd_family, dd_tasks, tmp_path):
    task = dd_tasks[2]  # datadesk-003
    with World.fresh(dd_family, task, tmp_path / "mcp.db") as world:
        init = handle_request(
            world, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        )
        assert init["result"]["serverInfo"] == {
            "name": "hubbench-datadesk",
            "version": dd_family.version,
        }
        listing = handle_request(
            world, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        )
        names = [tool["name"] for tool in listing["result"]["tools"]]
        assert (
            "hubbench.submit_answer" in names
            and "warehouse.slots.list" in names
            and len(names) == 33
        )
        hints = {
            tool["name"]: tool["annotations"]["readOnlyHint"]
            for tool in listing["result"]["tools"]
        }
        assert (
            hints["pipelines.schedules.update"] is False
            and hints["warehouse.models.get"] is True
        )
        call = handle_request(
            world,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "pipelines.schedules.get",
                    "arguments": {"schedule_id": "SCH-4407"},
                },
            },
        )
        body = json.loads(call["result"]["content"][0]["text"])
        assert body["status"] == "pending" and call["result"]["isError"] is False
        missing = handle_request(
            world,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "pipelines.schedules.get",
                    "arguments": {"schedule_id": "SCH-9999"},
                },
            },
        )
        assert missing["result"]["isError"] is True


def test_mcp_server_subprocess_round_trip(tmp_path):
    requests = "\n".join(
        [
            json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
            ),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "hubbench.context.get", "arguments": {}},
                }
            ),
        ]
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "hubbench.engine.server",
            "--family",
            "datadesk",
            "--task",
            "datadesk-001",
            "--db",
            str(tmp_path / "server.db"),
            "--fresh",
        ],
        input=requests,
        capture_output=True,
        text=True,
        cwd=BENCHMARK_ROOT,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    responses = [
        json.loads(line) for line in completed.stdout.splitlines() if line.strip()
    ]
    by_id = {response["id"]: response for response in responses}
    assert by_id[1]["result"]["protocolVersion"] == "2025-03-26"
    assert len(by_id[2]["result"]["tools"]) == 33
    context = json.loads(by_id[3]["result"]["content"][0]["text"])
    assert context["reference_records"]["case_reference"] == "DATA-0001"


def test_tool_cli_round_trip_with_persistent_state(tmp_path):
    env = {
        **os.environ,
        "HUBBENCH_FAMILY": "datadesk",
        "HUBBENCH_TASK": "datadesk-002",
        "HUBBENCH_DB": str(tmp_path / "cli.db"),
    }
    tool = str(HUBBENCH_ROOT / "bin" / "tool")

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, tool, *args],
            capture_output=True,
            text=True,
            env=env,
            cwd=tmp_path,
            timeout=120,
        )

    listing = run("list")
    assert (
        listing.returncode == 0
        and "pipelines.backfills.create\twrite" in listing.stdout
    )
    schema = run("schema", "pipelines.backfills.create")
    assert "partition_start" in schema.stdout
    write = run(
        "pipelines.backfills.create",
        json.dumps(
            {
                "model_id": "MDL-MARGIN-D",
                "partition_start": "2026-03-03",
                "partition_end": "2026-03-06",
                "cluster_id": "WH-STD",
                "start_time": "2026-03-12T13:00:00",
                "end_time": "2026-03-12T17:00:00",
                "description": "cli session",
            }
        ),
    )
    assert write.returncode == 0, write.stdout + write.stderr
    assert json.loads(write.stdout)["job_id"] == "BF-7101"
    read = run("pipelines.backfills.get", json.dumps({"job_id": "BF-7101"}))
    assert read.returncode == 0 and json.loads(read.stdout)["partitions"] == 4
    bad = run("pipelines.backfills.get", json.dumps({"job_id": "BF-9999"}))
    assert bad.returncode == 1
    trace = run("trace")
    assert len(json.loads(trace.stdout)) == 3


# --------------------------------------------------------------------------- #
# Reasoning-chain audit (unmodified portfolio adapter path)
# --------------------------------------------------------------------------- #


def _load_chain_adapter():
    spec = importlib.util.spec_from_file_location(
        "hubbench_chain_adapter_datadesk", HUBBENCH_ROOT / "chain_adapter.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_chain_audit_passes_all_tasks_and_report_is_current():
    adapter = _load_chain_adapter()
    report = adapter.measure_family("datadesk")
    assert report["measuredTasks"] == 8
    assert report["passingTasks"] == 8, report["failures"]
    assert report["meetsStandard"] is True
    assert report["chainDepth"] == {"min": 8, "max": 8}
    for hop in (f"H{i}" for i in range(1, 14)):
        assert report["hopCoverage"][hop] == 8, hop
    committed = json.loads(
        (HUBBENCH_ROOT / "reports" / "reasoning-chain" / "datadesk.json").read_text(
            encoding="utf-8"
        )
    )
    assert committed == report, (
        "committed chain report is stale; rerun chain_adapter.py --write"
    )
