"""ITSMDesk family: world build, surfaces, oracle, controls, chain audit, release integrity."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hubbench.engine.catalog import read_standard, sealed_contract, sha256_json, shingle_jaccard, validate_tasks, word_count
from hubbench.engine.evaluation import run_episode
from hubbench.engine.families import load_family
from hubbench.engine.server import handle_request
from hubbench.engine.tasks import load_release_contract, load_release_tasks
from hubbench.engine.world import World

HUBBENCH_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = HUBBENCH_ROOT.parent


@pytest.fixture(scope="module")
def itsmdesk_family():
    return load_family("itsmdesk")


@pytest.fixture(scope="module")
def itsmdesk_tasks(itsmdesk_family):
    tasks = load_release_tasks(itsmdesk_family)
    assert len(tasks) == 8, "the committed itsmdesk release must hold 8 tasks"
    return tasks


@pytest.fixture(scope="module")
def itsmdesk_contracts(itsmdesk_family, itsmdesk_tasks):
    return {task["task_id"]: load_release_contract(itsmdesk_family, task["task_id"]) for task in itsmdesk_tasks}


def test_world_builds_and_seeds_every_task(itsmdesk_family, itsmdesk_tasks, tmp_path):
    for task in itsmdesk_tasks:
        with World.fresh(itsmdesk_family, task, tmp_path / f"{task['task_id']}.db") as world:
            tables = {row["name"] for row in world.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for expected in ("services", "incidents", "slos", "change_requests", "maintenance_windows", "freeze_windows", "oncall_shifts", "vendor_advisories", "approvals", "messages", "chat_threads", "drive_files", "note_drafts", "mutations", "answers", "call_trace"):
                assert expected in tables
            assert world.connection.execute("SELECT COUNT(*) FROM maintenance_windows").fetchone()[0] > 0
            assert world.connection.execute("SELECT COUNT(*) FROM oncall_shifts").fetchone()[0] > 0
            assert world.connection.execute("PRAGMA foreign_key_check").fetchall() == []
            context = world.call_tool("hubbench.context.get", {})
            assert context["reference_records"]["case_reference"] == f"SVCOPS-{task['task_id'].rsplit('-', 1)[1].zfill(4)}"
            assert len(context["evidence_index"]) == len(task["assets"])


def test_writes_persist_and_readbacks_reflect_them(itsmdesk_family, itsmdesk_tasks, tmp_path):
    task = itsmdesk_tasks[0]  # itsmdesk-001: schedule the change into the Sunday window
    with World.fresh(itsmdesk_family, task, tmp_path / "write.db") as world:
        update = next(step for step in task["oracle_steps"] if step["phase"] == "primary_mutation")
        result = world.call_tool(update["tool"], update["arguments"])
        assert result.get("error") is None and result["state"] == "scheduled" and result["window"] == "MW-PAY-20260419-NIGHT"
        readback = world.call_tool("itsm.changes.get", {"change_id": "CHG-40311"})
        assert readback["state"] == "scheduled" and readback["lane"] == "LANE-PAY" and readback["meta"]["versionId"] == "2"
        window = world.one("SELECT status, change_id FROM maintenance_windows WHERE window_id = 'MW-PAY-20260419-NIGHT'")
        assert window == {"status": "busy", "change_id": "CHG-40311"}
        mutation = world.one("SELECT mutation_id, table_name FROM mutations WHERE task_id = ?", (task["task_id"],))
        assert mutation == {"mutation_id": f"{task['task_id']}-mutation-01", "table_name": "change_requests"}


def test_embargoed_windows_reject_displacement(itsmdesk_family, itsmdesk_tasks, tmp_path):
    task = itsmdesk_tasks[0]
    with World.fresh(itsmdesk_family, task, tmp_path / "protected.db") as world:
        control = task["negative_controls"]["unauthorized_write"]
        result = world.call_tool(control["tool"], control["arguments"])
        assert "error" in result and "protected" in result["error"]


def test_error_budget_gate_rejects_an_unaffordable_date(itsmdesk_family, itsmdesk_tasks, tmp_path):
    task = itsmdesk_tasks[0]
    with World.fresh(itsmdesk_family, task, tmp_path / "budget.db") as world:
        result = world.call_tool("itsm.changes.update", {"change_id": "CHG-40311", "lane_id": "LANE-PAY", "start_time": "2026-04-19T01:00:00", "end_time": "2026-04-19T01:45:00", "state": "scheduled", "downtime_minutes": 40})
        assert "error" in result and "error budget policy" in result["error"] and "spendable" in result["error"]


def test_batch_cap_and_suspended_lane_and_certification_are_enforced(itsmdesk_family, itsmdesk_tasks, tmp_path):
    expectations = {1: "cap", 5: "SUSPENDED", 7: "does not hold"}
    for index, fragment in expectations.items():
        task = itsmdesk_tasks[index]
        with World.fresh(itsmdesk_family, task, tmp_path / f"reject-{index}.db") as world:
            control = task["negative_controls"]["unauthorized_write"]
            result = world.call_tool(control["tool"], control["arguments"])
            assert "error" in result and fragment in result["error"], (task["task_id"], result)


def test_secondary_coverage_gate_blocks_an_uncertified_block(itsmdesk_family, itsmdesk_tasks, tmp_path):
    task = itsmdesk_tasks[7]  # itsmdesk-008: Sunday's rostered secondary is uncertified
    with World.fresh(itsmdesk_family, task, tmp_path / "coverage.db") as world:
        blocked = world.call_tool("itsm.changes.update", {"change_id": "CHG-40381", "lane_id": "LANE-CORE", "start_time": "2026-04-19T01:00:00", "end_time": "2026-04-19T05:00:00", "state": "scheduled"})
        assert "error" in blocked and "certified secondary" in blocked["error"]
        override = next(step for step in task["oracle_steps"] if step["phase"] == "primary_mutation")
        created = world.call_tool(override["tool"], override["arguments"])
        assert created.get("error") is None and created["override_id"] == "OVR-5101" and created["hours"] == 5
        rebooked = world.call_tool("itsm.changes.update", {"change_id": "CHG-40381", "lane_id": "LANE-CORE", "start_time": "2026-04-19T01:00:00", "end_time": "2026-04-19T05:00:00", "state": "scheduled"})
        assert rebooked.get("error") is None and rebooked["state"] == "scheduled"


def test_mcp_handshake_and_tool_call_in_process(itsmdesk_family, itsmdesk_tasks, tmp_path):
    task = itsmdesk_tasks[2]  # itsmdesk-003
    with World.fresh(itsmdesk_family, task, tmp_path / "mcp.db") as world:
        init = handle_request(world, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert init["result"]["serverInfo"] == {"name": "hubbench-itsmdesk", "version": itsmdesk_family.version}
        listing = handle_request(world, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [tool["name"] for tool in listing["result"]["tools"]]
        assert "hubbench.submit_answer" in names and "calendar.windows.list" in names and "telemetry.budget.get" in names
        hints = {tool["name"]: tool["annotations"]["readOnlyHint"] for tool in listing["result"]["tools"]}
        assert hints["itsm.changes.update"] is False and hints["itsm.cis.get"] is True
        call = handle_request(world, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "itsm.changes.get", "arguments": {"change_id": "CHG-40331"}}})
        body = json.loads(call["result"]["content"][0]["text"])
        assert body["state"] == "authorize" and call["result"]["isError"] is False
        missing = handle_request(world, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "itsm.changes.get", "arguments": {"change_id": "CHG-99999"}}})
        assert missing["result"]["isError"] is True
        scoped = handle_request(world, {"jsonrpc": "2.0", "id": 5, "method": "tools/list"}, "oncall")
        assert all(tool["name"].startswith("oncall.") for tool in scoped["result"]["tools"]) and scoped["result"]["tools"]


def test_mcp_server_subprocess_round_trip(tmp_path):
    requests = "\n".join(
        [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "hubbench.context.get", "arguments": {}}}),
        ]
    )
    completed = subprocess.run(
        [sys.executable, "-m", "hubbench.engine.server", "--family", "itsmdesk", "--task", "itsmdesk-001", "--db", str(tmp_path / "server.db"), "--fresh"],
        input=requests, capture_output=True, text=True, cwd=BENCHMARK_ROOT, timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    by_id = {response["id"]: response for response in responses}
    assert by_id[1]["result"]["protocolVersion"] == "2025-03-26"
    assert len(by_id[2]["result"]["tools"]) == 43
    context = json.loads(by_id[3]["result"]["content"][0]["text"])
    assert context["reference_records"]["case_reference"] == "SVCOPS-0001"


def test_tool_cli_round_trip_with_persistent_state(tmp_path):
    env = {**os.environ, "HUBBENCH_FAMILY": "itsmdesk", "HUBBENCH_TASK": "itsmdesk-008", "HUBBENCH_DB": str(tmp_path / "cli.db")}
    env.pop("HUBBENCH_URL", None)
    tool = str(HUBBENCH_ROOT / "bin" / "tool")

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, tool, *args], capture_output=True, text=True, env=env, cwd=tmp_path, timeout=120)

    listing = run("list")
    assert listing.returncode == 0 and "oncall.overrides.create\twrite" in listing.stdout
    schema = run("schema", "oncall.overrides.create")
    assert "engineer_id" in schema.stdout
    write = run("oncall.overrides.create", json.dumps({"schedule_id": "SCHED-SRCH-SEC", "engineer_id": "ENG-RAMAN", "start_time": "2026-04-19T01:00:00", "end_time": "2026-04-19T06:00:00"}))
    assert write.returncode == 0, write.stdout + write.stderr
    assert json.loads(write.stdout)["override_id"] == "OVR-5101"
    read = run("oncall.overrides.get", json.dumps({"override_id": "OVR-5101"}))
    assert read.returncode == 0 and json.loads(read.stdout)["hours"] == 5
    bad = run("oncall.overrides.get", json.dumps({"override_id": "OVR-9999"}))
    assert bad.returncode == 1
    trace = run("trace")
    assert len(json.loads(trace.stdout)) == 3


def test_oracle_passes_every_released_task(itsmdesk_family, itsmdesk_tasks, tmp_path):
    for task in itsmdesk_tasks:
        episode = run_episode(itsmdesk_family, task, "oracle", tmp_path / f"oracle-{task['task_id']}.db")
        assert episode["strict_pass"], {check["id"]: check["evidence"] for check in episode["checks"] if not check["passed"]}
        assert episode["score"] == 100.0


def test_negative_controls_are_rejected(itsmdesk_family, itsmdesk_tasks, tmp_path):
    for task in (itsmdesk_tasks[1], itsmdesk_tasks[5], itsmdesk_tasks[7]):
        for policy in ("unauthorized_write", "wrong_value", "wrong_evidence"):
            episode = run_episode(itsmdesk_family, task, policy, tmp_path / f"{policy}-{task['task_id']}.db")
            assert not episode["strict_pass"], (task["task_id"], policy)


def _load_chain_adapter():
    spec = importlib.util.spec_from_file_location("hubbench_chain_adapter_itsmdesk", HUBBENCH_ROOT / "chain_adapter.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_chain_audit_passes_all_tasks_and_report_is_current():
    adapter = _load_chain_adapter()
    report = adapter.measure_family("itsmdesk")
    assert report["measuredTasks"] == 8
    assert report["passingTasks"] == 8, report["failures"]
    assert report["meetsStandard"] is True
    assert report["chainDepth"] == {"min": 8, "max": 8}
    for hop in (f"H{i}" for i in range(1, 14)):
        assert report["hopCoverage"][hop] == 8, hop
    committed = json.loads((HUBBENCH_ROOT / "reports" / "reasoning-chain" / "itsmdesk.json").read_text(encoding="utf-8"))
    assert committed == report, "committed chain report is stale; rerun chain_adapter.py --family itsmdesk --write"


def test_committed_release_matches_fresh_build(itsmdesk_family, itsmdesk_tasks, itsmdesk_contracts):
    fresh = itsmdesk_family.build_tasks()
    assert [task["task_id"] for task in fresh] == [task["task_id"] for task in itsmdesk_tasks]
    for built, released in zip(fresh, itsmdesk_tasks):
        assert sha256_json(built) == sha256_json(released), f"{released['task_id']} release is stale; rerun build_release.py --family itsmdesk"
        assert sha256_json(sealed_contract(built)) == sha256_json(itsmdesk_contracts[released["task_id"]])


def test_release_meets_realism_standard_and_modes(itsmdesk_tasks):
    validate_tasks(itsmdesk_tasks)
    standard = read_standard()["requirements"]
    for task in itsmdesk_tasks:
        assert standard["employeeRequest"]["minimumWords"] <= word_count(task["instruction"]) <= standard["employeeRequest"]["maximumWords"]
        assert len(task["assets"]) >= standard["assetRoom"]["minimumAgentVisibleFilesPerTask"]
        assert len({asset["media_type"] for asset in task["assets"]}) >= standard["assetRoom"]["minimumNativeFormatsPerTask"]
        assert sum(len(m["criterion_ids"]) for m in task["rubric_milestones"]) >= standard["rubric"]["minimumSpecificCriteriaPerTask"]
        assert len(task["expected"]["answer"]) >= standard["reasoningChain"]["minimumGradedAnswerFields"]
        assert len(task["required_investigations"]) >= standard["workflow"]["minimumProviderEvidenceReadsPerTask"]
        calls = [item["any_of"][0] for item in task["required_investigations"]]
        assert len({call["tool"].split(".", 1)[0] for call in calls}) >= standard["workflow"]["minimumIndependentEvidenceSources"]
    assert sorted(task["mode"] for task in itsmdesk_tasks) == sorted(["plan"] * 3 + ["quantity"] * 3 + ["schedule"] * 2)
    instructions = [task["instruction"] for task in itsmdesk_tasks]
    assert len(set(instructions)) == len(instructions)
    for index, left in enumerate(instructions):
        for right in instructions[index + 1 :]:
            assert shingle_jaccard(left, right) <= 0.8
    signatures = [task["sequence_signature"] for task in itsmdesk_tasks]
    assert len(set(signatures)) == len(signatures)


def test_itsmdesk_reports_are_diff_stable():
    for name in ("reports/itsmdesk-qualification.json", "reports/reasoning-chain/itsmdesk.json"):
        text = (HUBBENCH_ROOT / name).read_text(encoding="utf-8")
        assert "/Users/" not in text and "/home/" not in text
        payload = json.loads(text)
        assert text == json.dumps(payload, indent=2, sort_keys=True) + "\n"
    qualification = json.loads((HUBBENCH_ROOT / "reports" / "itsmdesk-qualification.json").read_text(encoding="utf-8"))
    assert qualification["qualification_passed"] is True
    assert qualification["false_accepts"] == 0
    assert qualification["oracle"]["mean_score"] == 100.0
    assert qualification["mutation_omissions"]["all_detected"] is True
