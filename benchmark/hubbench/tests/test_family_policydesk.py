"""PolicyDesk family: world build, surfaces, oracle, controls, chain audit, release integrity."""

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
def pd_family():
    return load_family("policydesk")


@pytest.fixture(scope="module")
def pd_tasks(pd_family):
    tasks = load_release_tasks(pd_family)
    assert len(tasks) == 8, "the committed policydesk release must hold 8 tasks"
    return tasks


@pytest.fixture(scope="module")
def pd_contracts(pd_family, pd_tasks):
    return {task["task_id"]: load_release_contract(pd_family, task["task_id"]) for task in pd_tasks}


def test_world_builds_and_seeds_every_task(pd_family, pd_tasks, tmp_path):
    for task in pd_tasks:
        with World.fresh(pd_family, task, tmp_path / f"{task['task_id']}.db") as world:
            tables = {row["name"] for row in world.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for expected in ("access_requests", "grants", "exceptions_register", "review_windows", "policy_clauses", "training_records", "mutations", "answers", "call_trace"):
                assert expected in tables
            assert world.connection.execute("SELECT COUNT(*) FROM review_windows").fetchone()[0] > 0
            assert world.connection.execute("PRAGMA foreign_key_check").fetchall() == []
            context = world.call_tool("hubbench.context.get", {})
            assert context["reference_records"]["case_reference"] == f"AGR-{task['task_id'].rsplit('-', 1)[1].zfill(4)}"
            assert len(context["evidence_index"]) == len(task["assets"])


def test_writes_persist_and_readbacks_reflect_them(pd_family, pd_tasks, tmp_path):
    task = pd_tasks[0]  # policydesk-001: grants.create
    with World.fresh(pd_family, task, tmp_path / "write.db") as world:
        create = next(step for step in task["oracle_steps"] if step["phase"] == "primary_mutation")
        result = world.call_tool(create["tool"], create["arguments"])
        assert result.get("error") is None and result["grant_id"] == "GRANT-5003"
        readback = world.call_tool("grants.get", {"grant_id": "GRANT-5003"})
        assert readback["status"] == "ACTIVE" and readback["covers_request_count"] == 3
        row = world.one("SELECT resource_id, expires_on FROM grants WHERE grant_id = 'GRANT-5003'")
        assert row == {"resource_id": "RES-PAY-APV", "expires_on": "2026-06-10"}
        mutation = world.one("SELECT mutation_id, table_name FROM mutations WHERE task_id = ?", (task["task_id"],))
        assert mutation == {"mutation_id": f"{task['task_id']}-mutation-01", "table_name": "grants"}


def test_grant_over_cap_is_rejected(pd_family, pd_tasks, tmp_path):
    task = pd_tasks[0]  # policydesk-001: covers_request_count beyond the approval scope
    with World.fresh(pd_family, task, tmp_path / "overcap.db") as world:
        control = task["negative_controls"]["unauthorized_write"]
        result = world.call_tool(control["tool"], control["arguments"])
        assert "error" in result and "covers at most" in result["error"]


def test_exception_below_required_tier_is_rejected(pd_family, pd_tasks, tmp_path):
    task = pd_tasks[3]  # policydesk-004: exceptions.create at an insufficient approver tier
    with World.fresh(pd_family, task, tmp_path / "tier.db") as world:
        control = task["negative_controls"]["unauthorized_write"]
        result = world.call_tool(control["tool"], control["arguments"])
        assert "error" in result and "tier-2" in result["error"]


def test_protected_review_window_rejects_displacement(pd_family, pd_tasks, tmp_path):
    task = pd_tasks[2]  # policydesk-003: booking a review into a protected window
    with World.fresh(pd_family, task, tmp_path / "protected.db") as world:
        control = task["negative_controls"]["unauthorized_write"]
        result = world.call_tool(control["tool"], control["arguments"])
        assert "error" in result and "protected" in result["error"]


def test_mcp_handshake_and_tool_call_in_process(pd_family, pd_tasks, tmp_path):
    task = pd_tasks[2]  # policydesk-003
    with World.fresh(pd_family, task, tmp_path / "mcp.db") as world:
        init = handle_request(world, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert init["result"]["serverInfo"] == {"name": "hubbench-policydesk", "version": pd_family.version}
        assert handle_request(world, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
        listing = handle_request(world, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [tool["name"] for tool in listing["result"]["tools"]]
        assert "hubbench.submit_answer" in names and "reviews.windows.list" in names
        hints = {tool["name"]: tool["annotations"]["readOnlyHint"] for tool in listing["result"]["tools"]}
        assert hints["reviews.sessions.update"] is False and hints["resources.get"] is True
        call = handle_request(world, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "reviews.sessions.get", "arguments": {"session_id": "REV-8201"}}})
        body = json.loads(call["result"]["content"][0]["text"])
        assert body["status"] == "completed" and call["result"]["isError"] is False
        missing = handle_request(world, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "reviews.sessions.get", "arguments": {"session_id": "REV-99999"}}})
        assert missing["result"]["isError"] is True


def test_mcp_server_subprocess_round_trip(tmp_path):
    requests = "\n".join(
        [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "hubbench.context.get", "arguments": {}}}),
        ]
    )
    completed = subprocess.run(
        [sys.executable, "-m", "hubbench.engine.server", "--family", "policydesk", "--task", "policydesk-001", "--db", str(tmp_path / "server.db"), "--fresh"],
        input=requests, capture_output=True, text=True, cwd=BENCHMARK_ROOT, timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    by_id = {response["id"]: response for response in responses}
    assert by_id[1]["result"]["protocolVersion"] == "2025-03-26"
    assert len(by_id[2]["result"]["tools"]) == 41
    context = json.loads(by_id[3]["result"]["content"][0]["text"])
    assert context["reference_records"]["case_reference"] == "AGR-0001"


def test_tool_cli_round_trip_with_persistent_state(tmp_path):
    env = {**os.environ, "HUBBENCH_FAMILY": "policydesk", "HUBBENCH_TASK": "policydesk-002", "HUBBENCH_DB": str(tmp_path / "cli.db")}
    tool = str(HUBBENCH_ROOT / "bin" / "tool")

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, tool, *args], capture_output=True, text=True, env=env, cwd=tmp_path, timeout=120)

    listing = run("list")
    assert listing.returncode == 0 and "grants.create\twrite" in listing.stdout
    schema = run("schema", "grants.create")
    assert "covers_request_count" in schema.stdout
    write = run("grants.create", json.dumps({"resource_id": "RES-WH-READ", "role": "warehouse-reader", "covers_request_count": 4, "duration_days": 60, "expires_on": "2026-07-10", "approval_id": "AP-AG-0102"}))
    assert write.returncode == 0, write.stdout + write.stderr
    assert json.loads(write.stdout)["grant_id"] == "GRANT-6003"
    read = run("grants.get", json.dumps({"grant_id": "GRANT-6003"}))
    assert read.returncode == 0 and json.loads(read.stdout)["expires_on"] == "2026-07-10"
    bad = run("grants.get", json.dumps({"grant_id": "GRANT-9999"}))
    assert bad.returncode == 1
    trace = run("trace")
    assert len(json.loads(trace.stdout)) == 3


def test_oracle_passes_every_released_task(pd_family, pd_tasks, tmp_path):
    for task in pd_tasks:
        episode = run_episode(pd_family, task, "oracle", tmp_path / f"oracle-{task['task_id']}.db")
        assert episode["strict_pass"], {check["id"]: check["evidence"] for check in episode["checks"] if not check["passed"]}
        assert episode["score"] == 100.0


def test_negative_controls_are_rejected(pd_family, pd_tasks, tmp_path):
    for task in (pd_tasks[1], pd_tasks[5]):
        episode = run_episode(pd_family, task, "unauthorized_write", tmp_path / f"unauth-{task['task_id']}.db")
        assert not episode["strict_pass"], task["task_id"]
        wrong = run_episode(pd_family, task, "wrong_decision", tmp_path / f"wrong-{task['task_id']}.db")
        assert not wrong["strict_pass"], task["task_id"]


def _load_chain_adapter():
    spec = importlib.util.spec_from_file_location("hubbench_chain_adapter_policydesk", HUBBENCH_ROOT / "chain_adapter.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_chain_audit_passes_all_tasks_and_report_is_current():
    adapter = _load_chain_adapter()
    report = adapter.measure_family("policydesk")
    assert report["measuredTasks"] == 8
    assert report["passingTasks"] == 8, report["failures"]
    assert report["meetsStandard"] is True
    assert report["chainDepth"] == {"min": 8, "max": 8}
    for hop in (f"H{i}" for i in range(1, 14)):
        assert report["hopCoverage"][hop] == 8, hop
    committed = json.loads((HUBBENCH_ROOT / "reports" / "reasoning-chain" / "policydesk.json").read_text(encoding="utf-8"))
    assert committed == report, "committed chain report is stale; rerun chain_adapter.py --family policydesk --write"


def test_committed_release_matches_fresh_build(pd_family, pd_tasks, pd_contracts):
    fresh = pd_family.build_tasks()
    assert [task["task_id"] for task in fresh] == [task["task_id"] for task in pd_tasks]
    for built, released in zip(fresh, pd_tasks):
        assert sha256_json(built) == sha256_json(released), f"{released['task_id']} release is stale; rerun build_release.py --family policydesk"
        assert sha256_json(sealed_contract(built)) == sha256_json(pd_contracts[released["task_id"]])


def test_release_meets_realism_standard_and_modes(pd_tasks):
    validate_tasks(pd_tasks)
    standard = read_standard()["requirements"]
    for task in pd_tasks:
        assert standard["employeeRequest"]["minimumWords"] <= word_count(task["instruction"]) <= standard["employeeRequest"]["maximumWords"]
        assert len(task["assets"]) >= standard["assetRoom"]["minimumAgentVisibleFilesPerTask"]
        assert len({asset["media_type"] for asset in task["assets"]}) >= standard["assetRoom"]["minimumNativeFormatsPerTask"]
        assert sum(len(m["criterion_ids"]) for m in task["rubric_milestones"]) >= standard["rubric"]["minimumSpecificCriteriaPerTask"]
        assert len(task["expected"]["answer"]) >= standard["reasoningChain"]["minimumGradedAnswerFields"]
        assert len(task["required_investigations"]) >= standard["workflow"]["minimumProviderEvidenceReadsPerTask"]
    assert sorted(task["mode"] for task in pd_tasks) == sorted(["plan"] * 3 + ["quantity"] * 3 + ["schedule"] * 2)
    instructions = [task["instruction"] for task in pd_tasks]
    assert len(set(instructions)) == len(instructions)
    for index, left in enumerate(instructions):
        for right in instructions[index + 1 :]:
            assert shingle_jaccard(left, right) <= 0.8
    signatures = [task["sequence_signature"] for task in pd_tasks]
    assert len(set(signatures)) == len(signatures)


def test_policydesk_reports_are_diff_stable():
    for name in ("reports/policydesk-qualification.json", "reports/reasoning-chain/policydesk.json"):
        text = (HUBBENCH_ROOT / name).read_text(encoding="utf-8")
        assert "/Users/" not in text and "/home/" not in text
        payload = json.loads(text)
        assert text == json.dumps(payload, indent=2, sort_keys=True) + "\n"
    qualification = json.loads((HUBBENCH_ROOT / "reports" / "policydesk-qualification.json").read_text(encoding="utf-8"))
    assert qualification["qualification_passed"] is True
    assert qualification["false_accepts"] == 0
    assert qualification["oracle"]["mean_score"] == 100.0
    assert qualification["mutation_omissions"]["all_detected"] is True
