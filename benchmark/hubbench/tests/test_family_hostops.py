"""HostOps family: world build, surfaces, oracle, controls, chain audit, release integrity."""

from __future__ import annotations

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
from hubbench.engine.world import World

HUBBENCH_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = HUBBENCH_ROOT.parent


@pytest.fixture(scope="module")
def hostops_family():
    return load_family("hostops")


@pytest.fixture(scope="module")
def hostops_tasks(hostops_family):
    tasks = load_release_tasks(hostops_family)
    assert len(tasks) == 8, "the committed hostops release must hold 8 tasks"
    return tasks


@pytest.fixture(scope="module")
def hostops_contracts(hostops_family, hostops_tasks):
    return {
        task["task_id"]: load_release_contract(hostops_family, task["task_id"])
        for task in hostops_tasks
    }


def test_world_builds_and_seeds_every_task(hostops_family, hostops_tasks, tmp_path):
    for task in hostops_tasks:
        with World.fresh(
            hostops_family, task, tmp_path / f"{task['task_id']}.db"
        ) as world:
            tables = {
                row["name"]
                for row in world.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            for expected in (
                "services",
                "backup_sets",
                "farm_windows",
                "reservations",
                "job_runs",
                "mutations",
                "answers",
                "call_trace",
            ):
                assert expected in tables
            assert (
                world.connection.execute(
                    "SELECT COUNT(*) FROM farm_windows"
                ).fetchone()[0]
                > 0
            )
            assert world.connection.execute("PRAGMA foreign_key_check").fetchall() == []
            context = world.call_tool("hubbench.context.get", {})
            assert (
                context["reference_records"]["case_reference"]
                == f"HOST-{task['task_id'].rsplit('-', 1)[1].zfill(4)}"
            )
            assert len(context["evidence_index"]) == len(task["assets"])


def test_writes_persist_and_readbacks_reflect_them(
    hostops_family, hostops_tasks, tmp_path
):
    task = hostops_tasks[0]  # hostops-001: reservation create
    with World.fresh(hostops_family, task, tmp_path / "write.db") as world:
        create = next(
            step for step in task["oracle_steps"] if step["phase"] == "primary_mutation"
        )
        result = world.call_tool(create["tool"], create["arguments"])
        assert result.get("error") is None and result["id"] == "RES-70901"
        readback = world.call_tool(
            "buildfarm.reservations.get", {"reservation_id": "RES-70901"}
        )
        assert readback["status"] == "booked" and readback["runner"] == "RUNNER-2"
        window = world.one(
            "SELECT status, reservation_id FROM farm_windows WHERE window_id = 'WIN-2-20260422-PM'"
        )
        assert window == {"status": "busy", "reservation_id": "RES-70901"}
        mutation = world.one(
            "SELECT mutation_id, table_name FROM mutations WHERE task_id = ?",
            (task["task_id"],),
        )
        assert mutation == {
            "mutation_id": f"{task['task_id']}-mutation-01",
            "table_name": "reservations",
        }


def test_protected_windows_reject_displacement(hostops_family, hostops_tasks, tmp_path):
    task = hostops_tasks[0]
    with World.fresh(hostops_family, task, tmp_path / "protected.db") as world:
        control = task["negative_controls"]["unauthorized_write"]
        result = world.call_tool(control["tool"], control["arguments"])
        assert "error" in result and "protected" in result["error"]


def test_copy_rejects_unreleasable_segments(hostops_family, hostops_tasks, tmp_path):
    task = hostops_tasks[4]  # hostops-005: DR copy
    with World.fresh(hostops_family, task, tmp_path / "copy.db") as world:
        control = task["negative_controls"]["unauthorized_write"]
        result = world.call_tool(control["tool"], control["arguments"])
        assert "error" in result and "releasable" in result["error"]


def test_mcp_handshake_and_tool_call_in_process(
    hostops_family, hostops_tasks, tmp_path
):
    task = hostops_tasks[2]  # hostops-003
    with World.fresh(hostops_family, task, tmp_path / "mcp.db") as world:
        init = handle_request(
            world, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        )
        assert init["result"]["serverInfo"] == {
            "name": "hubbench-hostops",
            "version": hostops_family.version,
        }
        listing = handle_request(
            world, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        )
        names = [tool["name"] for tool in listing["result"]["tools"]]
        assert "hubbench.submit_answer" in names and "buildfarm.windows.list" in names
        hints = {
            tool["name"]: tool["annotations"]["readOnlyHint"]
            for tool in listing["result"]["tools"]
        }
        assert (
            hints["buildfarm.reservations.update"] is False
            and hints["cmdb.services.get"] is True
        )
        call = handle_request(
            world,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "buildfarm.reservations.get",
                    "arguments": {"reservation_id": "RES-70877"},
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
                    "name": "buildfarm.reservations.get",
                    "arguments": {"reservation_id": "RES-99999"},
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
            "hostops",
            "--task",
            "hostops-001",
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
    assert len(by_id[2]["result"]["tools"]) == 39
    context = json.loads(by_id[3]["result"]["content"][0]["text"])
    assert context["reference_records"]["case_reference"] == "HOST-0001"


def test_tool_cli_round_trip_with_persistent_state(tmp_path):
    env = {
        **os.environ,
        "HUBBENCH_FAMILY": "hostops",
        "HUBBENCH_TASK": "hostops-004",
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
    assert listing.returncode == 0 and "backup.restores.create\twrite" in listing.stdout
    schema = run("schema", "backup.restores.create")
    assert "retrieval_option" in schema.stdout
    write = run(
        "backup.restores.create",
        json.dumps(
            {
                "vendor_id": "VND-IRONHOLD",
                "confirmation_id": "CONF-IRH-66207",
                "artifact_class": "LOG-AUDIT-10",
                "segment_count": 2,
                "retrieval_option": "expedited",
            }
        ),
    )
    assert write.returncode == 0, write.stdout + write.stderr
    assert json.loads(write.stdout)["restore_id"] == "RST-3401"
    read = run("backup.restores.get", json.dumps({"restore_id": "RST-3401"}))
    assert (
        read.returncode == 0
        and json.loads(read.stdout)["expected_ready_date"] == "2026-04-16"
    )
    bad = run("backup.restores.get", json.dumps({"restore_id": "RST-9999"}))
    assert bad.returncode == 1
    trace = run("trace")
    assert len(json.loads(trace.stdout)) == 3


def test_oracle_passes_every_released_task(hostops_family, hostops_tasks, tmp_path):
    for task in hostops_tasks:
        episode = run_episode(
            hostops_family, task, "oracle", tmp_path / f"oracle-{task['task_id']}.db"
        )
        assert episode["strict_pass"], {
            check["id"]: check["evidence"]
            for check in episode["checks"]
            if not check["passed"]
        }
        assert episode["score"] == 100.0


def test_unauthorized_write_control_is_rejected(
    hostops_family, hostops_tasks, tmp_path
):
    for task in (hostops_tasks[1], hostops_tasks[5]):
        episode = run_episode(
            hostops_family,
            task,
            "unauthorized_write",
            tmp_path / f"unauth-{task['task_id']}.db",
        )
        assert not episode["strict_pass"], task["task_id"]


def _load_chain_adapter():
    spec = importlib.util.spec_from_file_location(
        "hubbench_chain_adapter_hostops", HUBBENCH_ROOT / "chain_adapter.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_chain_audit_passes_all_tasks_and_report_is_current():
    adapter = _load_chain_adapter()
    report = adapter.measure_family("hostops")
    assert report["measuredTasks"] == 8
    assert report["passingTasks"] == 8, report["failures"]
    assert report["meetsStandard"] is True
    assert report["chainDepth"] == {"min": 8, "max": 8}
    for hop in (f"H{i}" for i in range(1, 14)):
        assert report["hopCoverage"][hop] == 8, hop
    committed = json.loads(
        (HUBBENCH_ROOT / "reports" / "reasoning-chain" / "hostops.json").read_text(
            encoding="utf-8"
        )
    )
    assert committed == report, (
        "committed chain report is stale; rerun chain_adapter.py --family hostops --write"
    )


def test_committed_release_matches_fresh_build(
    hostops_family, hostops_tasks, hostops_contracts
):
    fresh = hostops_family.build_tasks()
    assert [task["task_id"] for task in fresh] == [
        task["task_id"] for task in hostops_tasks
    ]
    for built, released in zip(fresh, hostops_tasks):
        assert sha256_json(built) == sha256_json(released), (
            f"{released['task_id']} release is stale; rerun build_release.py --family hostops"
        )
        assert sha256_json(sealed_contract(built)) == sha256_json(
            hostops_contracts[released["task_id"]]
        )


def test_release_meets_realism_standard_and_modes(hostops_tasks):
    validate_tasks(hostops_tasks)
    standard = read_standard()["requirements"]
    for task in hostops_tasks:
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
            len(task["expected"]["answer"])
            >= standard["reasoningChain"]["minimumGradedAnswerFields"]
        )
        assert (
            len(task["required_investigations"])
            >= standard["workflow"]["minimumProviderEvidenceReadsPerTask"]
        )
    assert sorted(task["mode"] for task in hostops_tasks) == sorted(
        ["plan"] * 3 + ["quantity"] * 3 + ["schedule"] * 2
    )
    instructions = [task["instruction"] for task in hostops_tasks]
    assert len(set(instructions)) == len(instructions)
    for index, left in enumerate(instructions):
        for right in instructions[index + 1 :]:
            assert shingle_jaccard(left, right) <= 0.8
    signatures = [task["sequence_signature"] for task in hostops_tasks]
    assert len(set(signatures)) == len(signatures)


def test_hostops_reports_are_diff_stable():
    for name in (
        "reports/hostops-qualification.json",
        "reports/reasoning-chain/hostops.json",
    ):
        text = (HUBBENCH_ROOT / name).read_text(encoding="utf-8")
        assert "/Users/" not in text and "/home/" not in text
        payload = json.loads(text)
        assert text == json.dumps(payload, indent=2, sort_keys=True) + "\n"
    qualification = json.loads(
        (HUBBENCH_ROOT / "reports" / "hostops-qualification.json").read_text(
            encoding="utf-8"
        )
    )
    assert qualification["qualification_passed"] is True
    assert qualification["false_accepts"] == 0
    assert qualification["oracle"]["mean_score"] == 100.0
    assert qualification["mutation_omissions"]["all_detected"] is True
