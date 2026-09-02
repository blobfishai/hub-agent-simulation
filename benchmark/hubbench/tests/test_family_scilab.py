"""SciLab family: world build, surfaces, oracle, controls, chain audit, release integrity."""

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
def scilab_family():
    return load_family("scilab")


@pytest.fixture(scope="module")
def scilab_tasks(scilab_family):
    tasks = load_release_tasks(scilab_family)
    assert len(tasks) == 8, "the committed scilab release must hold 8 tasks"
    return tasks


@pytest.fixture(scope="module")
def scilab_contracts(scilab_family, scilab_tasks):
    return {task["task_id"]: load_release_contract(scilab_family, task["task_id"]) for task in scilab_tasks}


def test_world_builds_and_seeds_every_task(scilab_family, scilab_tasks, tmp_path):
    for task in scilab_tasks:
        with World.fresh(scilab_family, task, tmp_path / f"{task['task_id']}.db") as world:
            tables = {row["name"] for row in world.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for expected in (
                "assays",
                "protocols",
                "reagent_lots",
                "instrument_windows",
                "calibration_certificates",
                "bookings",
                "assay_runs",
                "qc_results",
                "method_notes",
                "mutations",
                "answers",
                "call_trace",
            ):
                assert expected in tables
            assert world.connection.execute("SELECT COUNT(*) FROM instrument_windows").fetchone()[0] > 0
            assert world.connection.execute("SELECT COUNT(*) FROM protocols WHERE status = 'superseded'").fetchone()[0] >= 1
            assert world.connection.execute("PRAGMA foreign_key_check").fetchall() == []
            context = world.call_tool("hubbench.context.get", {})
            assert context["reference_records"]["case_reference"] == f"LAB-{task['task_id'].rsplit('-', 1)[1].zfill(4)}"
            assert len(context["evidence_index"]) == len(task["assets"])


def test_family_world_shape(scilab_family, scilab_tasks):
    servers = {tool.server for tool in scilab_family.tools}
    assert servers == {"lims", "instruments", "inventory", "supplier", "eln", "approvals", "messages", "chat", "drive", "notes"}
    assert len(scilab_family.tools) == 41
    domain_tables = [line.split()[2] for line in scilab_family.schema_sql.splitlines() if line.startswith("CREATE TABLE ")]
    assert len(domain_tables) == 24
    for required in ("approvals", "messages", "chat_threads", "drive_files", "note_drafts", "protocols", "reagent_lots", "calibration_certificates"):
        assert required in domain_tables
    for task in scilab_tasks:
        assert len(task["assets"]) >= 28
        assert len({asset["media_type"] for asset in task["assets"]}) >= 7
        assert len(task["expected"]["answer"]) >= 24
        assert sum(len(m["criterion_ids"]) for m in task["rubric_milestones"]) >= 60
        calls = [item["any_of"][0] for item in task["required_investigations"]]
        assert len(calls) >= 26
        assert sum(call["tool"] != "hubbench.context.get" for call in calls) >= 17
        assert len({call["tool"].split(".", 1)[0] for call in calls}) >= 5


def test_writes_persist_and_readbacks_reflect_them(scilab_family, scilab_tasks, tmp_path):
    task = scilab_tasks[0]  # scilab-001: booking create
    with World.fresh(scilab_family, task, tmp_path / "write.db") as world:
        create = next(step for step in task["oracle_steps"] if step["phase"] == "primary_mutation")
        result = world.call_tool(create["tool"], create["arguments"])
        assert result.get("error") is None and result["id"] == "BK-70901"
        readback = world.call_tool("instruments.bookings.get", {"booking_id": "BK-70901"})
        assert readback["status"] == "booked" and readback["instrument"] == "INST-2"
        window = world.one("SELECT status, booking_id FROM instrument_windows WHERE window_id = 'WIN-2-20260520-PM'")
        assert window == {"status": "busy", "booking_id": "BK-70901"}
        mutation = world.one("SELECT mutation_id, table_name FROM mutations WHERE task_id = ?", (task["task_id"],))
        assert mutation == {"mutation_id": f"{task['task_id']}-mutation-01", "table_name": "bookings"}


def test_protected_windows_reject_displacement(scilab_family, scilab_tasks, tmp_path):
    task = scilab_tasks[0]
    with World.fresh(scilab_family, task, tmp_path / "protected.db") as world:
        control = task["negative_controls"]["unauthorized_write"]
        result = world.call_tool(control["tool"], control["arguments"])
        assert "error" in result and "protected" in result["error"]


def test_uncalibrated_analyser_rejects_booking(scilab_family, scilab_tasks, tmp_path):
    task = scilab_tasks[2]  # scilab-003: pending validation run
    with World.fresh(scilab_family, task, tmp_path / "calibration.db") as world:
        world.connection.execute("UPDATE calibration_certificates SET expires_on = '2026-05-12' WHERE instrument_id = 'INST-2'")
        world.connection.commit()
        primary = next(step for step in task["oracle_steps"] if step["phase"] == "primary_mutation")
        result = world.call_tool(primary["tool"], primary["arguments"])
        assert "error" in result and "calibration certificate" in result["error"]
        booking = world.call_tool("instruments.bookings.get", {"booking_id": "BK-70877"})
        assert booking["status"] == "pending" and booking["meta"]["versionId"] == "1"


def test_transfer_rejects_unusable_vials(scilab_family, scilab_tasks, tmp_path):
    task = scilab_tasks[4]  # scilab-005: annex transfer
    with World.fresh(scilab_family, task, tmp_path / "transfer.db") as world:
        control = task["negative_controls"]["unauthorized_write"]
        result = world.call_tool(control["tool"], control["arguments"])
        assert "error" in result and "usable" in result["error"]


def test_mcp_handshake_and_tool_call_in_process(scilab_family, scilab_tasks, tmp_path):
    task = scilab_tasks[2]  # scilab-003
    with World.fresh(scilab_family, task, tmp_path / "mcp.db") as world:
        init = handle_request(world, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert init["result"]["serverInfo"] == {"name": "hubbench-scilab", "version": scilab_family.version}
        listing = handle_request(world, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [tool["name"] for tool in listing["result"]["tools"]]
        assert "hubbench.submit_answer" in names and "instruments.windows.list" in names and "eln.notes.get" in names
        hints = {tool["name"]: tool["annotations"]["readOnlyHint"] for tool in listing["result"]["tools"]}
        assert hints["instruments.bookings.update"] is False and hints["lims.assays.get"] is True
        call = handle_request(
            world,
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "instruments.bookings.get", "arguments": {"booking_id": "BK-70877"}}},
        )
        body = json.loads(call["result"]["content"][0]["text"])
        assert body["status"] == "pending" and call["result"]["isError"] is False
        missing = handle_request(
            world,
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "instruments.bookings.get", "arguments": {"booking_id": "BK-99999"}}},
        )
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
        [sys.executable, "-m", "hubbench.engine.server", "--family", "scilab", "--task", "scilab-001", "--db", str(tmp_path / "server.db"), "--fresh"],
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
    assert len(by_id[2]["result"]["tools"]) == 43
    context = json.loads(by_id[3]["result"]["content"][0]["text"])
    assert context["reference_records"]["case_reference"] == "LAB-0001"


def test_tool_cli_round_trip_with_persistent_state(tmp_path):
    env = {**os.environ, "HUBBENCH_FAMILY": "scilab", "HUBBENCH_TASK": "scilab-004", "HUBBENCH_DB": str(tmp_path / "cli.db")}
    tool = str(HUBBENCH_ROOT / "bin" / "tool")

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, tool, *args], capture_output=True, text=True, env=env, cwd=tmp_path, timeout=120)

    listing = run("list")
    assert listing.returncode == 0 and "supplier.orders.create\twrite" in listing.stdout
    schema = run("schema", "supplier.orders.create")
    assert "delivery_option" in schema.stdout
    write = run(
        "supplier.orders.create",
        json.dumps({"supplier_id": "SUP-CALDER", "confirmation_id": "CONF-CAL-66207", "reagent_code": "CTRL-STAB-1L", "quantity": 2, "delivery_option": "expedited"}),
    )
    assert write.returncode == 0, write.stdout + write.stderr
    assert json.loads(write.stdout)["order_id"] == "ORD-3401"
    read = run("supplier.orders.get", json.dumps({"order_id": "ORD-3401"}))
    assert read.returncode == 0 and json.loads(read.stdout)["expected_delivery_date"] == "2026-05-14"
    bad = run("supplier.orders.get", json.dumps({"order_id": "ORD-9999"}))
    assert bad.returncode == 1
    trace = run("trace")
    assert len(json.loads(trace.stdout)) == 3


def test_oracle_passes_every_released_task(scilab_family, scilab_tasks, tmp_path):
    for task in scilab_tasks:
        episode = run_episode(scilab_family, task, "oracle", tmp_path / f"oracle-{task['task_id']}.db")
        assert episode["strict_pass"], {check["id"]: check["evidence"] for check in episode["checks"] if not check["passed"]}
        assert episode["score"] == 100.0


def test_unauthorized_write_control_is_rejected(scilab_family, scilab_tasks, tmp_path):
    for task in (scilab_tasks[1], scilab_tasks[5]):
        episode = run_episode(scilab_family, task, "unauthorized_write", tmp_path / f"unauth-{task['task_id']}.db")
        assert not episode["strict_pass"], task["task_id"]


def test_wrong_evidence_control_is_rejected(scilab_family, scilab_tasks, tmp_path):
    for task in (scilab_tasks[0], scilab_tasks[7]):
        episode = run_episode(scilab_family, task, "wrong_evidence", tmp_path / f"decoy-{task['task_id']}.db")
        assert not episode["strict_pass"], task["task_id"]


def _load_chain_adapter():
    spec = importlib.util.spec_from_file_location("hubbench_chain_adapter_scilab", HUBBENCH_ROOT / "chain_adapter.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_chain_audit_passes_all_tasks_and_report_is_current():
    adapter = _load_chain_adapter()
    report = adapter.measure_family("scilab")
    assert report["measuredTasks"] == 8
    assert report["passingTasks"] == 8, report["failures"]
    assert report["meetsStandard"] is True
    assert report["chainDepth"] == {"min": 8, "max": 8}
    for hop in (f"H{i}" for i in range(1, 14)):
        assert report["hopCoverage"][hop] == 8, hop
    committed = json.loads((HUBBENCH_ROOT / "reports" / "reasoning-chain" / "scilab.json").read_text(encoding="utf-8"))
    assert committed == report, "committed chain report is stale; rerun chain_adapter.py --family scilab --write"


def test_committed_release_matches_fresh_build(scilab_family, scilab_tasks, scilab_contracts):
    fresh = scilab_family.build_tasks()
    assert [task["task_id"] for task in fresh] == [task["task_id"] for task in scilab_tasks]
    for built, released in zip(fresh, scilab_tasks):
        assert sha256_json(built) == sha256_json(released), f"{released['task_id']} release is stale; rerun build_release.py --family scilab"
        assert sha256_json(sealed_contract(built)) == sha256_json(scilab_contracts[released["task_id"]])


def test_release_meets_realism_standard_and_modes(scilab_tasks):
    validate_tasks(scilab_tasks)
    standard = read_standard()["requirements"]
    for task in scilab_tasks:
        assert standard["employeeRequest"]["minimumWords"] <= word_count(task["instruction"]) <= standard["employeeRequest"]["maximumWords"]
        assert len(task["assets"]) >= standard["assetRoom"]["minimumAgentVisibleFilesPerTask"]
        assert len({asset["media_type"] for asset in task["assets"]}) >= standard["assetRoom"]["minimumNativeFormatsPerTask"]
        assert sum(len(m["criterion_ids"]) for m in task["rubric_milestones"]) >= standard["rubric"]["minimumSpecificCriteriaPerTask"]
        assert len(task["expected"]["answer"]) >= standard["reasoningChain"]["minimumGradedAnswerFields"]
        assert len(task["required_investigations"]) >= standard["workflow"]["minimumProviderEvidenceReadsPerTask"]
    assert sorted(task["mode"] for task in scilab_tasks) == sorted(["plan"] * 3 + ["quantity"] * 3 + ["schedule"] * 2)
    instructions = [task["instruction"] for task in scilab_tasks]
    assert len(set(instructions)) == len(instructions)
    for index, left in enumerate(instructions):
        for right in instructions[index + 1 :]:
            assert shingle_jaccard(left, right) <= 0.8
    signatures = [task["sequence_signature"] for task in scilab_tasks]
    assert len(set(signatures)) == len(signatures)


def test_decoys_are_stale_and_distinct_from_current_evidence(scilab_tasks):
    kinds = {task["task_id"]: {asset["kind"] for asset in task["assets"]} for task in scilab_tasks}
    assert "protocol_superseded" in kinds["scilab-001"]
    assert "stale_certificate" in kinds["scilab-006"]
    assert "duplicate_lot_record" in kinds["scilab-008"]
    for task in scilab_tasks:
        decoy_file = task["negative_controls"]["wrong_evidence"]["arguments"]["file_id"]
        drive = {row["file_id"]: row for row in task["seed_tables"]["drive_files"]}
        assert decoy_file in drive
        required_exports = {call["arguments"]["file_id"] for call in task["required_read_calls"] if call["tool"] == "drive.files.export"}
        assert decoy_file not in required_exports


def test_scilab_reports_are_diff_stable():
    for name in ("reports/scilab-qualification.json", "reports/reasoning-chain/scilab.json"):
        text = (HUBBENCH_ROOT / name).read_text(encoding="utf-8")
        assert "/Users/" not in text and "/home/" not in text
        payload = json.loads(text)
        assert text == json.dumps(payload, indent=2, sort_keys=True) + "\n"
    qualification = json.loads((HUBBENCH_ROOT / "reports" / "scilab-qualification.json").read_text(encoding="utf-8"))
    assert qualification["qualification_passed"] is True
    assert qualification["false_accepts"] == 0
    assert qualification["oracle"]["mean_score"] == 100.0
    assert qualification["mutation_omissions"]["all_detected"] is True
    assert qualification["mutation_omissions"]["total"] == 16
