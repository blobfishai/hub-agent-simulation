"""RepoDesk family: world build, provider rules, surfaces, oracle, controls, chain audit, release integrity."""

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
def repodesk_family():
    return load_family("repodesk")


@pytest.fixture(scope="module")
def repodesk_tasks(repodesk_family):
    tasks = load_release_tasks(repodesk_family)
    assert len(tasks) == 8, "the committed repodesk release must hold 8 tasks"
    return tasks


@pytest.fixture(scope="module")
def repodesk_contracts(repodesk_family, repodesk_tasks):
    return {task["task_id"]: load_release_contract(repodesk_family, task["task_id"]) for task in repodesk_tasks}


def test_family_world_shape(repodesk_family):
    servers = {tool.server for tool in repodesk_family.tools}
    assert servers == {"scm", "tracker", "ci", "deploy", "success", "partners", "oncall", "approvals", "messages", "chat", "drive", "notes"}
    assert len(repodesk_family.tools) >= 30
    writes = {tool.name for tool in repodesk_family.tools if tool.hint == "write"}
    assert writes == {"scm.backports.create", "tracker.issues.update", "deploy.changes.create", "deploy.changes.update", "deploy.flags.update", "partners.orders.create", "notes.drafts.create"}
    for tool in repodesk_family.tools:
        assert tool.name.split(".")[0] in repodesk_family.servers
    assert "CREATE TABLE approvals" in repodesk_family.schema_sql and "CREATE TABLE note_drafts" in repodesk_family.schema_sql


def test_world_builds_and_seeds_every_task(repodesk_family, repodesk_tasks, tmp_path):
    for task in repodesk_tasks:
        with World.fresh(repodesk_family, task, tmp_path / f"{task['task_id']}.db") as world:
            tables = {row["name"] for row in world.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for expected in ("issues", "commits", "commit_modules", "verification_results", "release_windows", "change_records", "commitments", "partner_confirmations", "mutations", "answers", "call_trace"):
                assert expected in tables
            domain_tables = {name for name in tables if name not in {"users", "evidence_files", "mutations", "audit_log", "answers", "call_trace"}}
            assert len(domain_tables) >= 15
            assert world.connection.execute("SELECT COUNT(*) FROM release_windows").fetchone()[0] > 0
            assert world.connection.execute("PRAGMA foreign_key_check").fetchall() == []
            context = world.call_tool("hubbench.context.get", {})
            assert context["reference_records"]["case_reference"] == f"SHIP-{task['task_id'].rsplit('-', 1)[1].zfill(4)}"
            assert len(context["evidence_index"]) == len(task["assets"])


def test_change_booking_persists_and_readback_reflects_it(repodesk_family, repodesk_tasks, tmp_path):
    task = repodesk_tasks[0]  # repodesk-001: change record create
    with World.fresh(repodesk_family, task, tmp_path / "write.db") as world:
        create = next(step for step in task["oracle_steps"] if step["phase"] == "primary_mutation")
        result = world.call_tool(create["tool"], create["arguments"])
        assert result.get("error") is None and result["id"] == "CHG-70901"
        readback = world.call_tool("deploy.changes.get", {"change_id": "CHG-70901"})
        assert readback["status"] == "booked" and readback["lane"] == "LANE-2"
        window = world.one("SELECT status, change_id FROM release_windows WHERE window_id = 'RW-2-20260513-PM'")
        assert window == {"status": "busy", "change_id": "CHG-70901"}
        mutation = world.one("SELECT mutation_id, table_name FROM mutations WHERE task_id = ?", (task["task_id"],))
        assert mutation == {"mutation_id": f"{task['task_id']}-mutation-01", "table_name": "change_records"}


def test_protected_windows_reject_displacement(repodesk_family, repodesk_tasks, tmp_path):
    for index in (0, 2, 5):
        task = repodesk_tasks[index]
        with World.fresh(repodesk_family, task, tmp_path / f"protected-{index}.db") as world:
            control = task["negative_controls"]["unauthorized_write"]
            result = world.call_tool(control["tool"], control["arguments"])
            assert "error" in result and "protected" in result["error"], task["task_id"]


def test_backport_rejects_ineligible_commits(repodesk_family, repodesk_tasks, tmp_path):
    task = repodesk_tasks[4]  # repodesk-005: backport
    with World.fresh(repodesk_family, task, tmp_path / "backport.db") as world:
        control = task["negative_controls"]["unauthorized_write"]
        result = world.call_tool(control["tool"], control["arguments"])
        assert "error" in result and "eligible" in result["error"]
        eligible = world.call_tool("scm.commits.list", {"repo_id": "REPO-PLATFORM", "branch": "release/26.1", "since": "2026-04-29", "until": "2026-05-02"})
        statuses = {commit["sha"]: commit["status"] for commit in eligible["commits"]}
        assert statuses["5e6f7a8"] == "reverted" and statuses["6f7a8b9"] == "embargoed" and statuses["7a8b9c0"] == "docs_only"
        ok = world.call_tool("scm.backports.create", {"repo_id": "REPO-PLATFORM", "from_ref": "release/26.1", "to_ref": "hotfix/26.1.3", "commit_count": 3, "scheduled_date": "2026-05-05"})
        assert ok["backport_id"] == "BPR-2201" and ok["status"] == "SCHEDULED"


def test_certification_orders_are_bounded_by_the_confirmation(repodesk_family, repodesk_tasks, tmp_path):
    task = repodesk_tasks[1]  # repodesk-002
    with World.fresh(repodesk_family, task, tmp_path / "orders.db") as world:
        too_many = world.call_tool("partners.orders.create", {"partner_id": "PRT-CORVANE", "confirmation_id": "CONF-CRV-66120", "verification_class": "GATE-PAY-2", "run_count": 11, "service_option": "standard"})
        assert "covers at most" in too_many["error"]
        expired = world.call_tool("partners.orders.create", {"partner_id": "PRT-CORVANE", "confirmation_id": "CONF-CRV-66008", "verification_class": "GATE-PAY-2", "run_count": 2, "service_option": "standard"})
        assert "EXPIRED" in expired["error"]
        closed = world.call_tool("tracker.issues.update", {"issue_key": "LKS-4484", "status": "resolved"})
        assert closed["status"] == "resolved"


def test_duplicate_issues_cannot_be_transitioned_or_booked(repodesk_family, repodesk_tasks, tmp_path):
    task = repodesk_tasks[0]
    with World.fresh(repodesk_family, task, tmp_path / "duplicate.db") as world:
        result = world.call_tool("tracker.issues.update", {"issue_key": "LKS-4468", "status": "active"})
        assert "duplicate" in result["error"]
        booking = world.call_tool("deploy.changes.create", {"issue_key": "LKS-4468", "lane_id": "LANE-2", "start_time": "2026-05-13T13:00:00", "end_time": "2026-05-13T16:00:00"})
        assert "duplicate" in booking["error"]


def test_impact_gates_and_evidence_reads_expose_the_scope_rule(repodesk_family, repodesk_tasks, tmp_path):
    task = repodesk_tasks[0]
    with World.fresh(repodesk_family, task, tmp_path / "scope.db") as world:
        impact = world.call_tool("scm.impact.list", {"component_id": "CMP-30411", "metric": "TOUCHED-MODULES"})
        assert [report["value"] for report in impact["impact_reports"]] == [6, 4]
        modules = world.call_tool("scm.modules.list", {"component_id": "CMP-30411"})
        gated = {module["module_id"]: module["gate"] for module in modules["modules"] if module["gate"]}
        assert gated == {"MOD-CHK-RCPT": "reverted"}
        commits = world.call_tool("scm.commits.list", {"repo_id": "REPO-PLATFORM", "branch": "release/26.1", "since": "2026-04-27", "until": "2026-05-01"})
        touched = {module for commit in commits["commits"] for module in commit["touched_modules"]}
        assert len(touched) == 6
        results = world.call_tool("ci.results.list", {"verification_class": "GATE-CHECKOUT-1"})
        statuses = {row["result_label"]: row["status"] for row in results["results"]}
        assert statuses["9077"] == "QUARANTINED" and sum(row["run_count"] for row in results["results"]) == 12
        summary = world.call_tool("ci.results.summary", {"verification_class": "GATE-CHECKOUT-1"})
        assert summary["balances"][0]["run_count"] == 12


def test_mcp_handshake_and_tool_call_in_process(repodesk_family, repodesk_tasks, tmp_path):
    task = repodesk_tasks[2]  # repodesk-003
    with World.fresh(repodesk_family, task, tmp_path / "mcp.db") as world:
        init = handle_request(world, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert init["result"]["serverInfo"] == {"name": "hubbench-repodesk", "version": repodesk_family.version}
        listing = handle_request(world, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [tool["name"] for tool in listing["result"]["tools"]]
        assert "hubbench.submit_answer" in names and "deploy.windows.list" in names
        hints = {tool["name"]: tool["annotations"]["readOnlyHint"] for tool in listing["result"]["tools"]}
        assert hints["deploy.changes.update"] is False and hints["scm.components.get"] is True
        call = handle_request(world, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "deploy.changes.get", "arguments": {"change_id": "CHG-70877"}}})
        body = json.loads(call["result"]["content"][0]["text"])
        assert body["status"] == "pending" and call["result"]["isError"] is False
        missing = handle_request(world, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "deploy.changes.get", "arguments": {"change_id": "CHG-99999"}}})
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
        [sys.executable, "-m", "hubbench.engine.server", "--family", "repodesk", "--task", "repodesk-001", "--db", str(tmp_path / "server.db"), "--fresh"],
        input=requests, capture_output=True, text=True, cwd=BENCHMARK_ROOT, timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    by_id = {response["id"]: response for response in responses}
    assert by_id[1]["result"]["protocolVersion"] == "2025-03-26"
    assert len(by_id[2]["result"]["tools"]) == 57
    context = json.loads(by_id[3]["result"]["content"][0]["text"])
    assert context["reference_records"]["case_reference"] == "SHIP-0001"


def test_tool_cli_round_trip_with_persistent_state(tmp_path):
    env = {**os.environ, "HUBBENCH_FAMILY": "repodesk", "HUBBENCH_TASK": "repodesk-004", "HUBBENCH_DB": str(tmp_path / "cli.db")}
    env.pop("HUBBENCH_URL", None)
    tool = str(HUBBENCH_ROOT / "bin" / "tool")

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, tool, *args], capture_output=True, text=True, env=env, cwd=tmp_path, timeout=120)

    listing = run("list")
    assert listing.returncode == 0 and "partners.orders.create\twrite" in listing.stdout
    schema = run("schema", "partners.orders.create")
    assert "service_option" in schema.stdout
    write = run("partners.orders.create", json.dumps({"partner_id": "PRT-BRIGHTWATER", "confirmation_id": "CONF-BRW-66207", "verification_class": "GATE-AUDIT-1", "run_count": 2, "service_option": "expedited"}))
    assert write.returncode == 0, write.stdout + write.stderr
    assert json.loads(write.stdout)["order_id"] == "ORD-3401"
    read = run("partners.orders.get", json.dumps({"order_id": "ORD-3401"}))
    assert read.returncode == 0 and json.loads(read.stdout)["expected_ready_date"] == "2026-05-07"
    bad = run("partners.orders.get", json.dumps({"order_id": "ORD-9999"}))
    assert bad.returncode == 1
    trace = run("trace")
    assert len(json.loads(trace.stdout)) == 3


def test_oracle_passes_every_released_task(repodesk_family, repodesk_tasks, tmp_path):
    for task in repodesk_tasks:
        episode = run_episode(repodesk_family, task, "oracle", tmp_path / f"oracle-{task['task_id']}.db")
        assert episode["strict_pass"], {check["id"]: check["evidence"] for check in episode["checks"] if not check["passed"]}
        assert episode["score"] == 100.0


def test_unauthorized_write_control_is_rejected(repodesk_family, repodesk_tasks, tmp_path):
    for task in (repodesk_tasks[1], repodesk_tasks[6]):
        episode = run_episode(repodesk_family, task, "unauthorized_write", tmp_path / f"unauth-{task['task_id']}.db")
        assert not episode["strict_pass"], task["task_id"]


def test_wrong_evidence_and_noop_controls_are_rejected(repodesk_family, repodesk_tasks, tmp_path):
    task = repodesk_tasks[3]
    wrong = run_episode(repodesk_family, task, "wrong_evidence", tmp_path / "wrong-evidence.db")
    assert not wrong["strict_pass"]
    noop = run_episode(repodesk_family, task, "noop", tmp_path / "noop.db")
    assert noop["score"] < 10


def _load_chain_adapter():
    spec = importlib.util.spec_from_file_location("hubbench_chain_adapter_repodesk", HUBBENCH_ROOT / "chain_adapter.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_chain_audit_passes_all_tasks_and_report_is_current():
    adapter = _load_chain_adapter()
    report = adapter.measure_family("repodesk")
    assert report["measuredTasks"] == 8
    assert report["passingTasks"] == 8, report["failures"]
    assert report["meetsStandard"] is True
    assert report["chainDepth"] == {"min": 8, "max": 8}
    for hop in (f"H{i}" for i in range(1, 14)):
        assert report["hopCoverage"][hop] == 8, hop
    committed = json.loads((HUBBENCH_ROOT / "reports" / "reasoning-chain" / "repodesk.json").read_text(encoding="utf-8"))
    assert committed == report, "committed chain report is stale; rerun chain_adapter.py --family repodesk --write"


def test_committed_release_matches_fresh_build(repodesk_family, repodesk_tasks, repodesk_contracts):
    fresh = repodesk_family.build_tasks()
    assert [task["task_id"] for task in fresh] == [task["task_id"] for task in repodesk_tasks]
    for built, released in zip(fresh, repodesk_tasks):
        assert sha256_json(built) == sha256_json(released), f"{released['task_id']} release is stale; rerun build_release.py --family repodesk"
        assert sha256_json(sealed_contract(built)) == sha256_json(repodesk_contracts[released["task_id"]])


def test_release_meets_realism_standard_and_modes(repodesk_tasks):
    validate_tasks(repodesk_tasks)
    standard = read_standard()["requirements"]
    for task in repodesk_tasks:
        assert standard["employeeRequest"]["minimumWords"] <= word_count(task["instruction"]) <= standard["employeeRequest"]["maximumWords"]
        assert len(task["assets"]) >= standard["assetRoom"]["minimumAgentVisibleFilesPerTask"]
        assert len({asset["media_type"] for asset in task["assets"]}) >= standard["assetRoom"]["minimumNativeFormatsPerTask"]
        assert sum(len(m["criterion_ids"]) for m in task["rubric_milestones"]) >= standard["rubric"]["minimumSpecificCriteriaPerTask"]
        assert len(task["expected"]["answer"]) >= 24
        assert len(task["required_investigations"]) >= standard["workflow"]["minimumProviderEvidenceReadsPerTask"]
        assert len({call["tool"].split(".")[0] for call in task["required_read_calls"]}) >= 5
    assert sorted(task["mode"] for task in repodesk_tasks) == sorted(["plan"] * 3 + ["quantity"] * 3 + ["schedule"] * 2)
    instructions = [task["instruction"] for task in repodesk_tasks]
    assert len(set(instructions)) == len(instructions)
    for index, left in enumerate(instructions):
        for right in instructions[index + 1 :]:
            assert shingle_jaccard(left, right) <= 0.72
    signatures = [task["sequence_signature"] for task in repodesk_tasks]
    assert len(set(signatures)) == len(signatures)


def test_decoys_are_stale_and_distinct_from_current_evidence(repodesk_tasks):
    stale_markers = ("superseded", "decoy", "stale", "retired")
    for task in repodesk_tasks:
        decoy_file = task["negative_controls"]["wrong_evidence"]["arguments"]["file_id"]
        required_files = {call["arguments"].get("file_id") for call in task["required_read_calls"] if call["tool"] == "drive.files.export"}
        assert decoy_file not in required_files, task["task_id"]
        decoy_row = next(row for row in task["seed_tables"]["drive_files"] if row["file_id"] == decoy_file)
        decoy_asset = next(asset for asset in task["assets"] if asset["path"].rsplit("/", 1)[-1] == decoy_row["name"] and asset["sha256"] == decoy_row["sha256"])
        assert any(marker in decoy_asset["kind"] for marker in stale_markers) or decoy_asset["kind"] in {"decoy_issue", "stale_commit_count", "stale_letter", "stale_notice"}
        kinds = {asset["kind"] for asset in task["assets"]}
        assert "authority_current" in kinds and "policy" in kinds and "customer_commitment" in kinds and "commit_range" in kinds


def test_repodesk_reports_are_diff_stable():
    for name in ("reports/repodesk-qualification.json", "reports/reasoning-chain/repodesk.json"):
        text = (HUBBENCH_ROOT / name).read_text(encoding="utf-8")
        assert "/Users/" not in text and "/home/" not in text
        payload = json.loads(text)
        assert text == json.dumps(payload, indent=2, sort_keys=True) + "\n"
    qualification = json.loads((HUBBENCH_ROOT / "reports" / "repodesk-qualification.json").read_text(encoding="utf-8"))
    assert qualification["qualification_passed"] is True
    assert qualification["false_accepts"] == 0
    assert qualification["oracle"]["mean_score"] == 100.0
    assert qualification["mutation_omissions"]["all_detected"] is True
    assert qualification["mutation_omissions"]["total"] == 16
