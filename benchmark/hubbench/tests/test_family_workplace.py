"""Workplace family: world build, surfaces, oracle, controls, chain audit, release integrity."""

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
def workplace_family():
    return load_family("workplace")


@pytest.fixture(scope="module")
def workplace_tasks(workplace_family):
    tasks = load_release_tasks(workplace_family)
    assert len(tasks) == 8, "the committed workplace release must hold 8 tasks"
    return tasks


@pytest.fixture(scope="module")
def workplace_contracts(workplace_family, workplace_tasks):
    return {task["task_id"]: load_release_contract(workplace_family, task["task_id"]) for task in workplace_tasks}


def test_world_builds_and_seeds_every_task(workplace_family, workplace_tasks, tmp_path):
    for task in workplace_tasks:
        with World.fresh(workplace_family, task, tmp_path / f"{task['task_id']}.db") as world:
            tables = {row["name"] for row in world.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for expected in ("customers", "escalations", "issues", "sprint_capacity", "calendar_blocks", "bookings", "credits", "confirmations", "wiki_pages", "mutations", "answers", "call_trace"):
                assert expected in tables
            assert world.connection.execute("SELECT COUNT(*) FROM calendar_blocks").fetchone()[0] > 0
            assert world.connection.execute("PRAGMA foreign_key_check").fetchall() == []
            context = world.call_tool("hubbench.context.get", {})
            assert context["reference_records"]["case_reference"] == f"WORK-{task['task_id'].rsplit('-', 1)[1].zfill(4)}"
            assert len(context["evidence_index"]) == len(task["assets"])
            assert {server["name"] for server in context["tool_servers"]} >= {"helpdesk", "tracker", "wiki", "calendar", "hris", "contracts", "portal", "hubbench"}


def test_writes_persist_and_readbacks_reflect_them(workplace_family, workplace_tasks, tmp_path):
    task = workplace_tasks[0]  # workplace-001: partner assignment in the tracker
    with World.fresh(workplace_family, task, tmp_path / "write.db") as world:
        update = next(step for step in task["oracle_steps"] if step["phase"] == "primary_mutation")
        result = world.call_tool(update["tool"], update["arguments"])
        assert result.get("error") is None and result["key"] == "BILL-2418"
        readback = world.call_tool("tracker.issues.get", {"issue_key": "BILL-2418"})
        assert readback["sprint"] == "SPR-28" and readback["assignee"] == "CTR-WRN-07" and readback["meta"]["versionId"] == "2"
        row = world.one("SELECT sprint_id, assignee_id, revision FROM issues WHERE issue_key = 'BILL-2418'")
        assert row == {"sprint_id": "SPR-28", "assignee_id": "CTR-WRN-07", "revision": 2}
        mutation = world.one("SELECT mutation_id, table_name FROM mutations WHERE task_id = ?", (task["task_id"],))
        assert mutation == {"mutation_id": f"{task['task_id']}-mutation-01", "table_name": "issues"}


def test_capacity_guard_rejects_pull_in_beyond_usable_capacity(workplace_family, workplace_tasks, tmp_path):
    task = workplace_tasks[0]
    with World.fresh(workplace_family, task, tmp_path / "guard.db") as world:
        control = task["negative_controls"]["unauthorized_write"]
        result = world.call_tool(control["tool"], control["arguments"])
        assert "error" in result and "scope-change" in result["error"]
        assert world.one("SELECT sprint_id FROM issues WHERE issue_key = 'BILL-2418'")["sprint_id"] is None


def test_leave_blocks_reject_bookings(workplace_family, workplace_tasks, tmp_path):
    task = workplace_tasks[2]  # workplace-003: rehearsal hold
    with World.fresh(workplace_family, task, tmp_path / "leave.db") as world:
        control = task["negative_controls"]["unauthorized_write"]
        result = world.call_tool(control["tool"], control["arguments"])
        assert "error" in result and "leave" in result["error"]
        assert world.one("SELECT status FROM bookings WHERE booking_id = 'BKG-5207'")["status"] == "pending"


def test_credit_cap_rejects_gross_claim(workplace_family, workplace_tasks, tmp_path):
    task = workplace_tasks[1]  # workplace-002: SLA credit
    with World.fresh(workplace_family, task, tmp_path / "cap.db") as world:
        control = task["negative_controls"]["unauthorized_write"]
        result = world.call_tool(control["tool"], control["arguments"])
        assert "error" in result and "cap" in result["error"]
        assert world.connection.execute("SELECT COUNT(*) FROM credits WHERE status = 'SUBMITTED'").fetchone()[0] == 0


def test_commitment_guard_rejects_later_target_date(workplace_family, workplace_tasks, tmp_path):
    task = workplace_tasks[3]  # workplace-004: escalation commit
    with World.fresh(workplace_family, task, tmp_path / "commit.db") as world:
        control = task["negative_controls"]["unauthorized_write"]
        result = world.call_tool(control["tool"], control["arguments"])
        assert "error" in result and "support director" in result["error"]
        assert world.one("SELECT status, revision FROM escalations WHERE escalation_id = 'ESC-3134'") == {"status": "open", "revision": 1}


def test_mcp_handshake_and_tool_call_in_process(workplace_family, workplace_tasks, tmp_path):
    task = workplace_tasks[2]  # workplace-003
    with World.fresh(workplace_family, task, tmp_path / "mcp.db") as world:
        init = handle_request(world, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert init["result"]["serverInfo"] == {"name": "hubbench-workplace", "version": workplace_family.version}
        assert handle_request(world, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
        listing = handle_request(world, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [tool["name"] for tool in listing["result"]["tools"]]
        assert "hubbench.submit_answer" in names and "calendar.blocks.list" in names
        hints = {tool["name"]: tool["annotations"]["readOnlyHint"] for tool in listing["result"]["tools"]}
        assert hints["calendar.bookings.update"] is False and hints["helpdesk.escalations.get"] is True
        call = handle_request(world, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "calendar.bookings.get", "arguments": {"booking_id": "BKG-5207"}}})
        body = json.loads(call["result"]["content"][0]["text"])
        assert body["status"] == "pending" and call["result"]["isError"] is False
        missing = handle_request(world, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "calendar.bookings.get", "arguments": {"booking_id": "BKG-9999"}}})
        assert missing["result"]["isError"] is True


def test_mcp_server_subprocess_round_trip(workplace_family, tmp_path):
    requests = "\n".join(
        [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "hubbench.context.get", "arguments": {}}}),
        ]
    )
    completed = subprocess.run(
        [sys.executable, "-m", "hubbench.engine.server", "--family", "workplace", "--task", "workplace-001", "--db", str(tmp_path / "server.db"), "--fresh"],
        input=requests,
        capture_output=True,
        text=True,
        cwd=BENCHMARK_ROOT,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    by_id = {response["id"]: response for response in responses}
    assert by_id[1]["result"]["protocolVersion"] == "2025-03-26"
    assert len(by_id[2]["result"]["tools"]) == len(workplace_family.tools) + 2
    context = json.loads(by_id[3]["result"]["content"][0]["text"])
    assert context["reference_records"]["case_reference"] == "WORK-0001"


def test_tool_cli_round_trip_with_persistent_state(tmp_path):
    env = {**os.environ, "HUBBENCH_FAMILY": "workplace", "HUBBENCH_TASK": "workplace-006", "HUBBENCH_DB": str(tmp_path / "cli.db")}
    tool = str(HUBBENCH_ROOT / "bin" / "tool")

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, tool, *args], capture_output=True, text=True, env=env, cwd=tmp_path, timeout=120)

    listing = run("list")
    assert listing.returncode == 0 and "calendar.bookings.create\twrite" in listing.stdout
    schema = run("schema", "calendar.bookings.create")
    assert "escalation_id" in schema.stdout
    write = run(
        "calendar.bookings.create",
        json.dumps({"employee_id": "EMP-1041", "escalation_id": "ESC-3155", "start": "2026-04-16T13:30:00", "end": "2026-04-16T16:30:00", "description": "Mireille tax-rounding hotfix pairing (WORK-0006)"}),
    )
    assert write.returncode == 0, write.stdout + write.stderr
    assert json.loads(write.stdout)["id"] == "BKG-5289"
    read = run("calendar.bookings.get", json.dumps({"booking_id": "BKG-5289"}))
    assert read.returncode == 0 and json.loads(read.stdout)["status"] == "booked"
    bad = run("calendar.bookings.get", json.dumps({"booking_id": "BKG-9999"}))
    assert bad.returncode == 1
    trace = run("trace")
    assert len(json.loads(trace.stdout)) == 3


def test_oracle_passes_every_released_task(workplace_family, workplace_tasks, tmp_path):
    for task in workplace_tasks:
        episode = run_episode(workplace_family, task, "oracle", tmp_path / f"oracle-{task['task_id']}.db")
        assert episode["strict_pass"], {check["id"]: check["evidence"] for check in episode["checks"] if not check["passed"]}
        assert episode["score"] == 100.0


def test_unauthorized_write_control_is_rejected(workplace_family, workplace_tasks, tmp_path):
    for task in (workplace_tasks[1], workplace_tasks[5]):
        episode = run_episode(workplace_family, task, "unauthorized_write", tmp_path / f"unauth-{task['task_id']}.db")
        assert not episode["strict_pass"], task["task_id"]


def _load_chain_adapter():
    spec = importlib.util.spec_from_file_location("hubbench_chain_adapter_workplace", HUBBENCH_ROOT / "chain_adapter.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_chain_audit_passes_all_tasks_and_report_is_current():
    adapter = _load_chain_adapter()
    report = adapter.measure_family("workplace")
    assert report["measuredTasks"] == 8
    assert report["passingTasks"] == 8, report["failures"]
    assert report["meetsStandard"] is True
    assert report["chainDepth"] == {"min": 8, "max": 8}
    for hop in (f"H{i}" for i in range(1, 14)):
        assert report["hopCoverage"][hop] == 8, hop
    committed = json.loads((HUBBENCH_ROOT / "reports" / "reasoning-chain" / "workplace.json").read_text(encoding="utf-8"))
    assert committed == report, "committed chain report is stale; rerun chain_adapter.py --family workplace --write"


def test_committed_release_matches_fresh_build(workplace_family, workplace_tasks, workplace_contracts):
    fresh = workplace_family.build_tasks()
    assert [task["task_id"] for task in fresh] == [task["task_id"] for task in workplace_tasks]
    for built, released in zip(fresh, workplace_tasks):
        assert sha256_json(built) == sha256_json(released), f"{released['task_id']} release is stale; rerun build_release.py --family workplace"
        assert sha256_json(sealed_contract(built)) == sha256_json(workplace_contracts[released["task_id"]])


def test_release_meets_realism_standard_and_modes(workplace_tasks):
    validate_tasks(workplace_tasks)
    standard = read_standard()["requirements"]
    for task in workplace_tasks:
        assert standard["employeeRequest"]["minimumWords"] <= word_count(task["instruction"]) <= standard["employeeRequest"]["maximumWords"]
        assert len(task["assets"]) >= standard["assetRoom"]["minimumAgentVisibleFilesPerTask"]
        assert len({asset["media_type"] for asset in task["assets"]}) >= standard["assetRoom"]["minimumNativeFormatsPerTask"]
        assert sum(len(m["criterion_ids"]) for m in task["rubric_milestones"]) >= standard["rubric"]["minimumSpecificCriteriaPerTask"]
        assert len(task["expected"]["answer"]) >= standard["reasoningChain"]["minimumGradedAnswerFields"]
        assert len(task["required_investigations"]) >= standard["workflow"]["minimumProviderEvidenceReadsPerTask"]
        assert len({call["tool"].split(".", 1)[0] for call in task["required_read_calls"]}) >= standard["workflow"]["minimumIndependentEvidenceSources"]
    assert sorted(task["mode"] for task in workplace_tasks) == sorted(["plan"] * 3 + ["quantity"] * 3 + ["schedule"] * 2)
    instructions = [task["instruction"] for task in workplace_tasks]
    assert len(set(instructions)) == len(instructions)
    for index, left in enumerate(instructions):
        for right in instructions[index + 1 :]:
            assert shingle_jaccard(left, right) <= 0.72
    signatures = [task["sequence_signature"] for task in workplace_tasks]
    assert len(set(signatures)) == len(signatures)


def test_workplace_reports_are_diff_stable():
    for name in ("reports/workplace-qualification.json", "reports/reasoning-chain/workplace.json"):
        text = (HUBBENCH_ROOT / name).read_text(encoding="utf-8")
        assert "/Users/" not in text and "/home/" not in text
        payload = json.loads(text)
        assert text == json.dumps(payload, indent=2, sort_keys=True) + "\n"
    qualification = json.loads((HUBBENCH_ROOT / "reports" / "workplace-qualification.json").read_text(encoding="utf-8"))
    assert qualification["qualification_passed"] is True
    assert qualification["false_accepts"] == 0
    assert qualification["oracle"]["mean_score"] == 100.0
    assert qualification["mutation_omissions"]["all_detected"] is True
    assert qualification["mutation_omissions"]["total"] == 16
