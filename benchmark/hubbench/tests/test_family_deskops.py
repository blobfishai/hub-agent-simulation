"""DeskOps family: office-suite world, provider rules, surfaces, controls, and release integrity."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
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
from hubbench.engine.families import SUBMIT_TOOL, load_family
from hubbench.engine.http import build_server
from hubbench.engine.server import handle_request
from hubbench.engine.tasks import load_release_contract, load_release_tasks
from hubbench.engine.world import World

HUBBENCH_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = HUBBENCH_ROOT.parent


@pytest.fixture(scope="module")
def deskops_family():
    return load_family("deskops")


@pytest.fixture(scope="module")
def deskops_tasks(deskops_family):
    tasks = load_release_tasks(deskops_family)
    assert len(tasks) == 8, "the committed DeskOps release must hold eight tasks"
    return tasks


@pytest.fixture(scope="module")
def deskops_contracts(deskops_family, deskops_tasks):
    return {task["task_id"]: load_release_contract(deskops_family, task["task_id"]) for task in deskops_tasks}


def _primary(task):
    return next(step for step in task["oracle_steps"] if step["phase"] == "primary_mutation")


def _http_json(base: str, method: str, path: str, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"null")


def test_world_builds_and_seeds_every_task(deskops_family, deskops_tasks, tmp_path):
    required_tables = {
        "offices", "people", "rooms", "venues", "budget_lines", "documents", "document_revisions",
        "events", "event_attendees", "busy_blocks", "venue_weeks", "venue_quotes", "venue_holds",
        "travel_policies", "bookings", "ticketing_confirmations", "booking_changes", "budget_adjustments",
        "spreadsheets", "spreadsheet_versions", "mutations", "answers", "call_trace",
    }
    for task in deskops_tasks:
        with World.fresh(deskops_family, task, tmp_path / f"{task['task_id']}.db") as world:
            tables = {row["name"] for row in world.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            assert required_tables <= tables
            assert world.connection.execute("SELECT COUNT(*) FROM venue_weeks").fetchone()[0] > 0
            assert world.connection.execute("SELECT COUNT(*) FROM document_revisions WHERE status = 'superseded'").fetchone()[0] >= 1
            assert world.connection.execute("SELECT COUNT(*) FROM spreadsheet_versions").fetchone()[0] >= 2
            assert world.connection.execute("PRAGMA foreign_key_check").fetchall() == []
            context = world.call_tool("hubbench.context.get", {})
            suffix = task["task_id"].rsplit("-", 1)[1].zfill(4)
            assert context["reference_records"]["case_reference"] == f"DESK-{suffix}"
            assert len(context["evidence_index"]) == len(task["assets"])


def test_family_world_shape(deskops_family, deskops_tasks):
    assert set(deskops_family.servers) == {
        "approvals", "calendar", "chat", "directory", "docs", "drive", "expense", "mail", "notes",
        "sheets", "travel", "venues",
    }
    assert len(deskops_family.tools) == 49
    domain_tables = [line.split()[2] for line in deskops_family.schema_sql.splitlines() if line.startswith("CREATE TABLE ")]
    assert len(domain_tables) == 26
    assert {tool.name for tool in deskops_family.tools if tool.hint == "write"} == {
        "calendar.events.update", "expense.adjustments.create", "notes.drafts.create",
        "travel.changes.create", "venues.holds.create",
    }
    for task in deskops_tasks:
        calls = [item["any_of"][0] for item in task["required_investigations"]]
        assert len(task["assets"]) >= 35
        assert len({asset["media_type"] for asset in task["assets"]}) >= 7
        assert len(task["expected"]["answer"]) >= 27
        assert sum(len(milestone["criterion_ids"]) for milestone in task["rubric_milestones"]) >= 71
        assert len(calls) >= 26
        assert sum(call["tool"] != "hubbench.context.get" for call in calls) >= 20
        assert len({call["tool"].split(".", 1)[0] for call in calls}) >= 10
        assert len(task["decision_model"]["options"]) == 3


def test_calendar_rejects_hard_conflicts_and_persists_valid_move(deskops_family, deskops_tasks, tmp_path):
    task = deskops_tasks[0]
    with World.fresh(deskops_family, task, tmp_path / "calendar.db") as world:
        bad = task["negative_controls"]["unauthorized_write"]
        rejected = world.call_tool(bad["tool"], bad["arguments"])
        assert "error" in rejected and "protected customer_commitment" in rejected["error"]
        result = world.call_tool(_primary(task)["tool"], _primary(task)["arguments"])
        assert result.get("error") is None
        assert result["start"] == "2026-07-21" and result["end"] == "2026-07-23"
        assert result["venue"] == "VEN-HARROW" and result["meta"]["versionId"] == "2"
        assert world.call_tool("calendar.events.get", {"event_id": "EVT-PRD-Q3"}) == result


def test_venue_holds_never_displace_blackouts(deskops_family, deskops_tasks, tmp_path):
    task = deskops_tasks[2]
    with World.fresh(deskops_family, task, tmp_path / "venue.db") as world:
        bad = task["negative_controls"]["unauthorized_write"]
        rejected = world.call_tool(bad["tool"], bad["arguments"])
        assert "error" in rejected and "blackout" in rejected["error"] and "cannot be displaced" in rejected["error"]
        held = world.call_tool(_primary(task)["tool"], _primary(task)["arguments"])
        assert held.get("error") is None
        assert held["id"] == "HOLD-4401" and held["status"] == "HELD" and held["deposit_usd"] == 4050.0
        week = world.one(
            "SELECT status, hold_id FROM venue_weeks WHERE venue_id = ? AND week_start = ?",
            ("VEN-KESTREL", "2026-07-13"),
        )
        assert week == {"status": "held", "hold_id": "HOLD-4401"}


def test_travel_change_rejects_nonchangeable_fares(deskops_family, deskops_tasks, tmp_path):
    task = deskops_tasks[3]
    with World.fresh(deskops_family, task, tmp_path / "travel.db") as world:
        bad = task["negative_controls"]["unauthorized_write"]
        rejected = world.call_tool(bad["tool"], bad["arguments"])
        assert "error" in rejected and "not changeable" in rejected["error"]
        change = world.call_tool(_primary(task)["tool"], _primary(task)["arguments"])
        assert change.get("error") is None
        assert change["change_id"] == "CHG-8801" and change["booking_count"] == 4
        assert change["ticketing_option"] == "rush" and change["expected_ticketing_date"] == "2026-06-12"
        assert world.call_tool("travel.changes.get", {"change_id": "CHG-8801"})["status"] == "SUBMITTED"


def test_expense_adjustment_enforces_ceiling(deskops_family, deskops_tasks, tmp_path):
    task = deskops_tasks[1]
    with World.fresh(deskops_family, task, tmp_path / "expense.db") as world:
        bad = task["negative_controls"]["unauthorized_write"]
        rejected = world.call_tool(bad["tool"], bad["arguments"])
        assert "error" in rejected and "exceeds" in rejected["error"] and "ceiling" in rejected["error"]
        adjustment = world.call_tool(_primary(task)["tool"], _primary(task)["arguments"])
        assert adjustment.get("error") is None
        assert adjustment["adjustment_id"] == "ADJ-2201" and adjustment["amount_usd"] == 1250
        line = world.call_tool("expense.budget_lines.get", {"line_id": "BL-EXEC-TRV-26H2"})
        assert line["reserved_usd"] >= 1250 and line["meta"]["versionId"] == "2"


def test_mcp_handshake_and_provider_scoping(deskops_family, deskops_tasks, tmp_path):
    with World.fresh(deskops_family, deskops_tasks[2], tmp_path / "mcp.db") as world:
        init = handle_request(world, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert init["result"]["serverInfo"] == {"name": "hubbench-deskops", "version": deskops_family.version}
        listing = handle_request(world, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {tool["name"] for tool in listing["result"]["tools"]}
        assert len(names) == 51
        assert {"calendar.freebusy.query", "venues.holds.create", "travel.changes.create", "hubbench.submit_answer"} <= names
        call = handle_request(
            world,
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "venues.quotes.get", "arguments": {"quote_id": "QT-KES-5522"}}},
        )
        quote = json.loads(call["result"]["content"][0]["text"])
        assert quote["quote_id"] == "QT-KES-5522" and call["result"]["isError"] is False


def test_mcp_server_subprocess_round_trip(tmp_path):
    requests = "\n".join(
        [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "hubbench.context.get", "arguments": {}}}),
        ]
    )
    completed = subprocess.run(
        [sys.executable, "-m", "hubbench.engine.server", "--family", "deskops", "--task", "deskops-001", "--db", str(tmp_path / "server.db"), "--fresh"],
        input=requests,
        capture_output=True,
        text=True,
        cwd=BENCHMARK_ROOT,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    responses = {response["id"]: response for response in map(json.loads, completed.stdout.splitlines()) if response.get("id") is not None}
    assert responses[1]["result"]["protocolVersion"] == "2025-03-26"
    assert len(responses[2]["result"]["tools"]) == 51
    context = json.loads(responses[3]["result"]["content"][0]["text"])
    assert context["reference_records"]["case_reference"] == "DESK-0001"


def test_tool_cli_round_trip_with_persistent_state(tmp_path):
    env = {
        **os.environ,
        "HUBBENCH_FAMILY": "deskops",
        "HUBBENCH_TASK": "deskops-003",
        "HUBBENCH_DB": str(tmp_path / "cli.db"),
    }
    tool = str(HUBBENCH_ROOT / "bin" / "tool")

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, tool, *args], capture_output=True, text=True, env=env, cwd=tmp_path, timeout=120)

    listing = run("list")
    assert listing.returncode == 0 and "venues.holds.create\twrite" in listing.stdout
    schema = run("schema", "venues.holds.create")
    assert schema.returncode == 0 and "week_start" in schema.stdout
    created = run(
        "venues.holds.create",
        json.dumps({"venue_id": "VEN-KESTREL", "week_start": "2026-07-13", "quote_id": "QT-KES-5522", "event_id": "EVT-SKO"}),
    )
    assert created.returncode == 0, created.stdout + created.stderr
    assert json.loads(created.stdout)["id"] == "HOLD-4401"
    read = run("venues.holds.get", json.dumps({"hold_id": "HOLD-4401"}))
    assert read.returncode == 0 and json.loads(read.stdout)["status"] == "HELD"
    assert len(json.loads(run("trace").stdout)) == 2


def test_http_rest_mcp_and_website_share_one_world(deskops_family, deskops_tasks, tmp_path):
    task = deskops_tasks[1]
    server = build_server(deskops_family, task, tmp_path / "http.db", host="127.0.0.1", port=0, fresh=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = server.url
        status, context = _http_json(base, "GET", "/api/v1/task")
        assert status == 200 and context["task"]["task_id"] == "deskops-002"
        assert {"calendar", "docs", "sheets", "venues", "travel", "expense", "hubbench"} <= {
            item["name"] for item in context["tool_servers"]
        }
        status, listing = _http_json(base, "POST", "/mcp/calendar", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert status == 200 and all(tool["name"].startswith("calendar.") for tool in listing["result"]["tools"])
        status, created = _http_json(base, "POST", "/api/v1/tools/expense.adjustments.create", _primary(task)["arguments"])
        assert status == 200 and created["adjustment_id"] == "ADJ-2201"
        status, readback = _http_json(base, "GET", "/api/v1/expense/adjustments/ADJ-2201")
        assert status == 200 and readback["amount_usd"] == 1250.0
        with urllib.request.urlopen(base + "/app/expense/adjustments/ADJ-2201", timeout=30) as response:
            page_status = response.status
            page = response.read().decode("utf-8")
        assert page_status == 200 and "ADJ-2201" in page and "SUBMITTED" in page
    finally:
        server.shutdown()
        server.server_close()
        server.session.close()
        thread.join(timeout=5)


def test_oracle_and_invalid_solutions(deskops_family, deskops_tasks, tmp_path):
    for task in deskops_tasks:
        oracle = run_episode(deskops_family, task, "oracle", tmp_path / f"oracle-{task['task_id']}.db")
        assert oracle["strict_pass"] and oracle["score"] == 100.0
    for policy, indexes in {"unauthorized_write": (0, 3, 7), "wrong_evidence": (1, 4, 6), "noop": (2,)}.items():
        for index in indexes:
            episode = run_episode(deskops_family, deskops_tasks[index], policy, tmp_path / f"{policy}-{index}.db")
            assert not episode["strict_pass"], (policy, deskops_tasks[index]["task_id"])


def test_every_task_requires_cross_application_evidence_and_one_primary_write(deskops_tasks):
    common = {
        "approvals.get",
        "calendar.attendees.list",
        "calendar.events.get",
        "calendar.freebusy.query",
        "docs.revisions.get",
        "drive.files.export",
        "expense.budget_lines.get",
        "mail.messages.get",
        "sheets.values.get",
        "travel.bookings.list",
        "travel.confirmations.get",
        "travel.policies.get",
        "venues.availability.list",
        "venues.quotes.get",
    }
    for task in deskops_tasks:
        investigations = [item for item in task["required_investigations"] if item.get("before_primary_mutation")]
        assert common <= {item["any_of"][0]["tool"] for item in investigations}, task["task_id"]
        mutations = [step for step in task["oracle_steps"] if step["phase"] == "primary_mutation"]
        assert len(mutations) == 1
        submit = next(step for step in task["oracle_steps"] if step["tool"] == SUBMIT_TOOL)
        assert submit["arguments"]["recommended_option"] == task["decision_model"]["selected_option"]


def _load_chain_adapter():
    spec = importlib.util.spec_from_file_location("hubbench_chain_adapter_deskops", HUBBENCH_ROOT / "chain_adapter.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_chain_audit_and_committed_report_are_current():
    report = _load_chain_adapter().measure_family("deskops")
    assert report["measuredTasks"] == report["passingTasks"] == 8
    assert report["meetsStandard"] is True and report["chainDepth"] == {"min": 8, "max": 8}
    assert all(report["hopCoverage"][f"H{index}"] == 8 for index in range(1, 14))
    committed = json.loads((HUBBENCH_ROOT / "reports" / "reasoning-chain" / "deskops.json").read_text(encoding="utf-8"))
    assert committed == report


def test_committed_release_matches_fresh_build(deskops_family, deskops_tasks, deskops_contracts):
    fresh = deskops_family.build_tasks()
    assert [task["task_id"] for task in fresh] == [task["task_id"] for task in deskops_tasks]
    for built, released in zip(fresh, deskops_tasks):
        assert sha256_json(built) == sha256_json(released)
        assert sha256_json(sealed_contract(built)) == sha256_json(deskops_contracts[released["task_id"]])


def test_release_meets_realism_standard_and_is_nonduplicative(deskops_tasks):
    validate_tasks(deskops_tasks)
    standard = read_standard()["requirements"]
    for task in deskops_tasks:
        assert standard["employeeRequest"]["minimumWords"] <= word_count(task["instruction"]) <= standard["employeeRequest"]["maximumWords"]
        assert len(task["assets"]) >= standard["assetRoom"]["minimumAgentVisibleFilesPerTask"]
        assert len({asset["media_type"] for asset in task["assets"]}) >= standard["assetRoom"]["minimumNativeFormatsPerTask"]
        assert len(task["required_investigations"]) >= standard["workflow"]["minimumProviderEvidenceReadsPerTask"]
        assert len(task["expected"]["answer"]) >= standard["reasoningChain"]["minimumGradedAnswerFields"]
    assert sorted(task["mode"] for task in deskops_tasks) == sorted(["plan"] * 3 + ["quantity"] * 3 + ["schedule"] * 2)
    instructions = [task["instruction"] for task in deskops_tasks]
    for index, left in enumerate(instructions):
        for right in instructions[index + 1 :]:
            assert shingle_jaccard(left, right) <= 0.72
    assert len({task["sequence_signature"] for task in deskops_tasks}) == 8


def test_decoys_are_mounted_but_never_required(deskops_tasks):
    for task in deskops_tasks:
        kinds = {asset["kind"] for asset in task["assets"]}
        assert {"policy", "policy_superseded", "authority_current", "authority_superseded"} <= kinds
        decoy_file = task["negative_controls"]["wrong_evidence"]["arguments"]["file_id"]
        drive = {row["file_id"]: row for row in task["seed_tables"]["drive_files"]}
        assert decoy_file in drive
        required_exports = {
            call["arguments"]["file_id"]
            for call in task["required_read_calls"]
            if call["tool"] == "drive.files.export"
        }
        assert decoy_file not in required_exports


def test_deskops_reports_are_diff_stable():
    for name in ("reports/deskops-qualification.json", "reports/reasoning-chain/deskops.json"):
        text = (HUBBENCH_ROOT / name).read_text(encoding="utf-8")
        assert "/Users/" not in text and "/home/" not in text
        payload = json.loads(text)
        assert text == json.dumps(payload, indent=2, sort_keys=True) + "\n"
    qualification = json.loads((HUBBENCH_ROOT / "reports" / "deskops-qualification.json").read_text(encoding="utf-8"))
    assert qualification["qualification_passed"] is True
    assert qualification["false_accepts"] == 0
    assert qualification["oracle"]["mean_score"] == 100.0
    assert qualification["determinism"]["exact_episode_matches"] == 8
    assert qualification["mutation_omissions"]["all_detected"] is True
    assert qualification["mutation_omissions"]["total"] == 16
