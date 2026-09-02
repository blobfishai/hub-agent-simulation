"""DesignOps family: world build, provider rules, surfaces, oracle, controls, chain audit, release integrity."""

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
def designops_family():
    return load_family("designops")


@pytest.fixture(scope="module")
def designops_tasks(designops_family):
    tasks = load_release_tasks(designops_family)
    assert len(tasks) == 8, "the committed designops release must hold 8 tasks"
    return tasks


@pytest.fixture(scope="module")
def designops_contracts(designops_family, designops_tasks):
    return {task["task_id"]: load_release_contract(designops_family, task["task_id"]) for task in designops_tasks}


def _primary(task):
    return next(step for step in task["oracle_steps"] if step["phase"] == "primary_mutation")


# --------------------------------------------------------------------------- #
# World build and shape
# --------------------------------------------------------------------------- #


def test_world_builds_and_seeds_every_task(designops_family, designops_tasks, tmp_path):
    for task in designops_tasks:
        with World.fresh(designops_family, task, tmp_path / f"{task['task_id']}.db") as world:
            tables = {row["name"] for row in world.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for expected in (
                "parts",
                "part_revisions",
                "cad_documents",
                "checkins",
                "change_orders",
                "affected_items",
                "bom_lines",
                "certifications",
                "fixture_families",
                "fixture_sets",
                "lines",
                "release_windows",
                "cutin_reservations",
                "supplier_quotes",
                "supplier_orders",
                "mutations",
                "answers",
                "call_trace",
            ):
                assert expected in tables
            assert world.connection.execute("SELECT COUNT(*) FROM release_windows").fetchone()[0] > 0
            assert world.connection.execute("SELECT COUNT(*) FROM part_revisions WHERE status IN ('SUPERSEDED', 'OBSOLETE')").fetchone()[0] >= 1
            assert world.connection.execute("SELECT COUNT(*) FROM bom_lines").fetchone()[0] >= 2
            assert world.connection.execute("PRAGMA foreign_key_check").fetchall() == []
            context = world.call_tool("hubbench.context.get", {})
            assert context["reference_records"]["case_reference"] == f"DSGN-{task['task_id'].rsplit('-', 1)[1].zfill(4)}"
            assert len(context["evidence_index"]) == len(task["assets"])


def test_family_world_shape(designops_family, designops_tasks):
    servers = {tool.server for tool in designops_family.tools}
    assert servers == {"plm", "eco", "bom", "cert", "tooling", "supplier", "calendar", "approvals", "messages", "chat", "drive", "notes"}
    assert len(designops_family.tools) == 40
    domain_tables = [line.split()[2] for line in designops_family.schema_sql.splitlines() if line.startswith("CREATE TABLE ")]
    assert len(domain_tables) == 24
    for required in ("approvals", "messages", "chat_threads", "drive_files", "note_drafts", "change_orders", "bom_lines", "certifications", "fixture_sets", "release_windows"):
        assert required in domain_tables
    for task in designops_tasks:
        assert len(task["assets"]) >= 28
        assert len({asset["media_type"] for asset in task["assets"]}) >= 7
        assert len(task["expected"]["answer"]) >= 24
        assert sum(len(m["criterion_ids"]) for m in task["rubric_milestones"]) >= 60
        calls = [item["any_of"][0] for item in task["required_investigations"]]
        assert len(calls) >= 26
        assert sum(call["tool"] != "hubbench.context.get" for call in calls) >= 17
        assert len({call["tool"].split(".", 1)[0] for call in calls}) >= 5
        assert len(task["decision_model"]["options"]) == 3


# --------------------------------------------------------------------------- #
# Provider rules and persisted writes
# --------------------------------------------------------------------------- #


def test_release_persists_effectivity_and_readback_reflects_it(designops_family, designops_tasks, tmp_path):
    task = designops_tasks[0]  # designops-001: change-order release with effectivity
    with World.fresh(designops_family, task, tmp_path / "release.db") as world:
        create = _primary(task)
        result = world.call_tool(create["tool"], create["arguments"])
        assert result.get("error") is None
        assert result["state"] == "RELEASED" and result["effectivity_date"] == "2026-05-20" and result["meta"]["versionId"] == "2"
        readback = world.call_tool("eco.changes.get", {"change_id": "ECO-24117"})
        assert readback["state"] == "RELEASED" and readback["effectivity_date"] == "2026-05-20"
        row = world.one("SELECT state, effectivity_date, revision FROM change_orders WHERE change_id = 'ECO-24117'")
        assert row == {"state": "RELEASED", "effectivity_date": "2026-05-20", "revision": 2}
        mutation = world.one("SELECT mutation_id, table_name FROM mutations WHERE task_id = ?", (task["task_id"],))
        assert mutation == {"mutation_id": f"{task['task_id']}-mutation-01", "table_name": "change_orders"}
        again = world.call_tool("eco.changes.update", {"change_id": "ECO-24117", "effectivity_date": "2026-05-21"})
        assert "error" in again and "cannot be changed" in again["error"]


def test_freeze_days_and_unapproved_changes_reject_release(designops_family, designops_tasks, tmp_path):
    task = designops_tasks[0]
    with World.fresh(designops_family, task, tmp_path / "freeze.db") as world:
        control = task["negative_controls"]["unauthorized_write"]
        result = world.call_tool(control["tool"], control["arguments"])
        assert "error" in result and "freeze" in result["error"]
        released = world.call_tool("eco.changes.update", {"change_id": "ECO-24088", "state": "RELEASED", "effectivity_date": "2026-05-20"})
        assert "error" in released and "cannot be changed" in released["error"]
        world.connection.execute("UPDATE change_orders SET state = 'SUBMITTED' WHERE change_id = 'ECO-24117'")
        world.connection.commit()
        submitted = world.call_tool("eco.changes.update", {"change_id": "ECO-24117", "state": "RELEASED", "effectivity_date": "2026-05-20"})
        assert "error" in submitted and "CCB_APPROVED" in submitted["error"]
        assert world.one("SELECT revision FROM change_orders WHERE change_id = 'ECO-24117'")["revision"] == 1


def test_protected_windows_reject_displacement(designops_family, designops_tasks, tmp_path):
    for index in (2, 5):  # designops-003 and designops-006: cut-in reservation moves
        task = designops_tasks[index]
        with World.fresh(designops_family, task, tmp_path / f"protected-{index}.db") as world:
            control = task["negative_controls"]["unauthorized_write"]
            result = world.call_tool(control["tool"], control["arguments"])
            assert "error" in result and "protected" in result["error"], task["task_id"]


def test_booking_holds_and_releases_calendar_windows(designops_family, designops_tasks, tmp_path):
    fai = designops_tasks[2]  # designops-003: full-day first-article run
    with World.fresh(designops_family, fai, tmp_path / "fai.db") as world:
        result = world.call_tool(_primary(fai)["tool"], _primary(fai)["arguments"])
        assert result.get("error") is None and result["meta"]["versionId"] == "2"
        for session in ("AM", "PM"):
            window = world.one(f"SELECT status, reservation_id FROM release_windows WHERE window_id = 'WIN-2-20260515-{session}'")
            assert window == {"status": "busy", "reservation_id": "RES-33118"}
        assert world.one("SELECT status FROM release_windows WHERE window_id = 'WIN-1-20260514-AM'")["status"] == "protected"
    advance = designops_tasks[6]  # designops-007: reservation moved earlier
    with World.fresh(designops_family, advance, tmp_path / "advance.db") as world:
        result = world.call_tool(_primary(advance)["tool"], _primary(advance)["arguments"])
        assert result.get("error") is None and result["line"] == "LINE-1"
        assert world.one("SELECT status, reservation_id FROM release_windows WHERE window_id = 'WIN-1-20260522-AM'") == {"status": "busy", "reservation_id": "RES-33160"}
        assert world.one("SELECT status, reservation_id FROM release_windows WHERE window_id = 'WIN-2-20260529-AM'") == {"status": "free", "reservation_id": None}


def test_transfer_rejects_unreleasable_sets(designops_family, designops_tasks, tmp_path):
    task = designops_tasks[4]  # designops-005: Kelbrook transfer
    with World.fresh(designops_family, task, tmp_path / "transfer.db") as world:
        control = task["negative_controls"]["unauthorized_write"]
        result = world.call_tool(control["tool"], control["arguments"])
        assert "error" in result and "releasable" in result["error"]
        ok = world.call_tool(_primary(task)["tool"], _primary(task)["arguments"])
        assert ok.get("error") is None and ok["transfer_id"] == "TRF-2201" and ok["status"] == "SCHEDULED"


def test_supplier_orders_are_bounded_by_the_quote(designops_family, designops_tasks, tmp_path):
    task = designops_tasks[3]  # designops-004: expedited laboratory order
    with World.fresh(designops_family, task, tmp_path / "quote.db") as world:
        control = task["negative_controls"]["unauthorized_write"]
        result = world.call_tool(control["tool"], control["arguments"])
        assert "error" in result and "covers at most" in result["error"]
        mismatch = world.call_tool("supplier.orders.create", {"supplier_id": "SUP-BRAMWELL", "quote_id": "QT-NB-3322", "item_code": "RECERT-PRG-SNS7", "quantity": 1, "service_option": "standard"})
        assert "error" in mismatch and "does not cover" in mismatch["error"]
        expired = world.call_tool("supplier.orders.create", {"supplier_id": "LAB-NORTHBANK", "quote_id": "QT-NB-3301", "item_code": "RECERT-PRG-SNS7", "quantity": 1, "service_option": "standard"})
        assert "error" in expired and "EXPIRED" in expired["error"]
        ok = world.call_tool(_primary(task)["tool"], _primary(task)["arguments"])
        assert ok.get("error") is None and ok["order_id"] == "SO-8801" and ok["unit"] == "CONFIGURATION" and ok["total_cost_usd"] == 4500.0
        assert world.call_tool("supplier.orders.get", {"order_id": "SO-8801"})["expected_ready_date"] == "2026-05-15"


def test_where_used_and_certification_reads_expose_the_scope_rule(designops_family, designops_tasks, tmp_path):
    task = designops_tasks[0]
    with World.fresh(designops_family, task, tmp_path / "scope.db") as world:
        where_used = world.call_tool("bom.whereused.list", {"component_part_id": "PRT-4471"})
        statuses = {line["line_id"]: line["parent_revision_status"] for line in where_used["lines"]}
        assert statuses["BL-9020D-12"] == "RELEASED" and statuses["BL-9020C-12"] == "SUPERSEDED" and statuses["BL-9068A-05"] == "OBSOLETE"
        assert next(line for line in where_used["lines"] if line["line_id"] == "BL-9055A-21")["line_kind"] == "alternate"
        certs = world.call_tool("cert.configurations.list", {"component_part_id": "PRT-4471"})
        assert {cert["cert_id"] for cert in certs["certifications"]} == {"CERT-7710", "CERT-7702", "CERT-7725", "CERT-7690"}
        surviving = world.call_tool("cert.configurations.list", {"assembly_part_id": "PRT-9042", "status": "ACTIVE"})
        assert [cert["cert_id"] for cert in surviving["certifications"]] == ["CERT-7731"]
        assert "PRT-4471" not in surviving["certifications"][0]["covered_components"]


# --------------------------------------------------------------------------- #
# Surfaces
# --------------------------------------------------------------------------- #


def test_mcp_handshake_and_tool_call_in_process(designops_family, designops_tasks, tmp_path):
    task = designops_tasks[2]  # designops-003
    with World.fresh(designops_family, task, tmp_path / "mcp.db") as world:
        init = handle_request(world, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert init["result"]["serverInfo"] == {"name": "hubbench-designops", "version": designops_family.version}
        listing = handle_request(world, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [tool["name"] for tool in listing["result"]["tools"]]
        assert "hubbench.submit_answer" in names and "calendar.windows.list" in names and "cert.configurations.list" in names
        hints = {tool["name"]: tool["annotations"]["readOnlyHint"] for tool in listing["result"]["tools"]}
        assert hints["calendar.reservations.update"] is False and hints["plm.parts.get"] is True and hints["eco.changes.update"] is False
        call = handle_request(
            world,
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "calendar.reservations.get", "arguments": {"reservation_id": "RES-33118"}}},
        )
        body = json.loads(call["result"]["content"][0]["text"])
        assert body["status"] == "pending" and call["result"]["isError"] is False
        missing = handle_request(
            world,
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "calendar.reservations.get", "arguments": {"reservation_id": "RES-99999"}}},
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
        [sys.executable, "-m", "hubbench.engine.server", "--family", "designops", "--task", "designops-001", "--db", str(tmp_path / "server.db"), "--fresh"],
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
    assert len(by_id[2]["result"]["tools"]) == 42
    context = json.loads(by_id[3]["result"]["content"][0]["text"])
    assert context["reference_records"]["case_reference"] == "DSGN-0001"


def test_tool_cli_round_trip_with_persistent_state(tmp_path):
    env = {**os.environ, "HUBBENCH_FAMILY": "designops", "HUBBENCH_TASK": "designops-002", "HUBBENCH_DB": str(tmp_path / "cli.db")}
    tool = str(HUBBENCH_ROOT / "bin" / "tool")

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, tool, *args], capture_output=True, text=True, env=env, cwd=tmp_path, timeout=120)

    listing = run("list")
    assert listing.returncode == 0 and "supplier.orders.create\twrite" in listing.stdout
    schema = run("schema", "supplier.orders.create")
    assert "service_option" in schema.stdout
    write = run(
        "supplier.orders.create",
        json.dumps({"supplier_id": "SUP-BRAMWELL", "quote_id": "QT-BR-5520", "item_code": "FIX-CLMP-2260", "quantity": 6, "service_option": "standard"}),
    )
    assert write.returncode == 0, write.stdout + write.stderr
    assert json.loads(write.stdout)["order_id"] == "SO-8801"
    read = run("supplier.orders.get", json.dumps({"order_id": "SO-8801"}))
    assert read.returncode == 0 and json.loads(read.stdout)["expected_ready_date"] == "2026-05-15"
    bad = run("supplier.orders.get", json.dumps({"order_id": "SO-9999"}))
    assert bad.returncode == 1
    trace = run("trace")
    assert len(json.loads(trace.stdout)) == 3


# --------------------------------------------------------------------------- #
# Verifier and controls
# --------------------------------------------------------------------------- #


def test_oracle_passes_every_released_task(designops_family, designops_tasks, tmp_path):
    for task in designops_tasks:
        episode = run_episode(designops_family, task, "oracle", tmp_path / f"oracle-{task['task_id']}.db")
        assert episode["strict_pass"], {check["id"]: check["evidence"] for check in episode["checks"] if not check["passed"]}
        assert episode["score"] == 100.0


def test_unauthorized_write_control_is_rejected(designops_family, designops_tasks, tmp_path):
    for task in (designops_tasks[1], designops_tasks[5]):
        episode = run_episode(designops_family, task, "unauthorized_write", tmp_path / f"unauth-{task['task_id']}.db")
        assert not episode["strict_pass"], task["task_id"]


def test_wrong_evidence_control_is_rejected(designops_family, designops_tasks, tmp_path):
    for task in (designops_tasks[0], designops_tasks[7]):
        episode = run_episode(designops_family, task, "wrong_evidence", tmp_path / f"decoy-{task['task_id']}.db")
        assert not episode["strict_pass"], task["task_id"]


def test_noop_scores_near_zero(designops_family, designops_tasks, tmp_path):
    episode = run_episode(designops_family, designops_tasks[6], "noop", tmp_path / "noop.db")
    assert episode["score"] < 10.0


# --------------------------------------------------------------------------- #
# Reasoning-chain audit and release integrity
# --------------------------------------------------------------------------- #


def _load_chain_adapter():
    spec = importlib.util.spec_from_file_location("hubbench_chain_adapter_designops", HUBBENCH_ROOT / "chain_adapter.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_chain_audit_passes_all_tasks_and_report_is_current():
    adapter = _load_chain_adapter()
    report = adapter.measure_family("designops")
    assert report["measuredTasks"] == 8
    assert report["passingTasks"] == 8, report["failures"]
    assert report["meetsStandard"] is True
    assert report["chainDepth"] == {"min": 8, "max": 8}
    for hop in (f"H{i}" for i in range(1, 14)):
        assert report["hopCoverage"][hop] == 8, hop
    committed = json.loads((HUBBENCH_ROOT / "reports" / "reasoning-chain" / "designops.json").read_text(encoding="utf-8"))
    assert committed == report, "committed chain report is stale; rerun chain_adapter.py --family designops --write"


def test_committed_release_matches_fresh_build(designops_family, designops_tasks, designops_contracts):
    fresh = designops_family.build_tasks()
    assert [task["task_id"] for task in fresh] == [task["task_id"] for task in designops_tasks]
    for built, released in zip(fresh, designops_tasks):
        assert sha256_json(built) == sha256_json(released), f"{released['task_id']} release is stale; rerun build_release.py --family designops"
        assert sha256_json(sealed_contract(built)) == sha256_json(designops_contracts[released["task_id"]])


def test_release_meets_realism_standard_and_modes(designops_tasks):
    validate_tasks(designops_tasks)
    standard = read_standard()["requirements"]
    for task in designops_tasks:
        assert standard["employeeRequest"]["minimumWords"] <= word_count(task["instruction"]) <= standard["employeeRequest"]["maximumWords"]
        assert len(task["assets"]) >= standard["assetRoom"]["minimumAgentVisibleFilesPerTask"]
        assert len({asset["media_type"] for asset in task["assets"]}) >= standard["assetRoom"]["minimumNativeFormatsPerTask"]
        assert sum(len(m["criterion_ids"]) for m in task["rubric_milestones"]) >= standard["rubric"]["minimumSpecificCriteriaPerTask"]
        assert len(task["expected"]["answer"]) >= standard["reasoningChain"]["minimumGradedAnswerFields"]
        assert len(task["required_investigations"]) >= standard["workflow"]["minimumProviderEvidenceReadsPerTask"]
    assert sorted(task["mode"] for task in designops_tasks) == sorted(["plan"] * 3 + ["quantity"] * 3 + ["schedule"] * 2)
    instructions = [task["instruction"] for task in designops_tasks]
    assert len(set(instructions)) == len(instructions)
    for index, left in enumerate(instructions):
        for right in instructions[index + 1 :]:
            assert shingle_jaccard(left, right) <= 0.72
    signatures = [task["sequence_signature"] for task in designops_tasks]
    assert len(set(signatures)) == len(signatures)


def test_decoys_are_stale_and_distinct_from_current_evidence(designops_tasks):
    kinds = {task["task_id"]: {asset["kind"] for asset in task["assets"]} for task in designops_tasks}
    assert {"policy_superseded", "stale_whereused_export"} <= kinds["designops-001"]
    assert "duplicate_change_order" in kinds["designops-003"]
    assert "stale_fixture_count" in kinds["designops-005"]
    assert "stale_notice" in kinds["designops-006"]
    assert "superseded_change_order" in kinds["designops-007"]
    assert "stale_bulletin" in kinds["designops-008"]
    for task in designops_tasks:
        assert "policy" in kinds[task["task_id"]] and "policy_superseded" in kinds[task["task_id"]]
        decoy_file = task["negative_controls"]["wrong_evidence"]["arguments"]["file_id"]
        drive = {row["file_id"]: row for row in task["seed_tables"]["drive_files"]}
        assert decoy_file in drive
        required_exports = {call["arguments"]["file_id"] for call in task["required_read_calls"] if call["tool"] == "drive.files.export"}
        assert decoy_file not in required_exports
        superseded_documents = [row for row in task["seed_tables"]["cad_documents"] if row["status"] in {"SUPERSEDED", "RELEASED"} and row["revision"] != task["seed_tables"]["change_orders"][0]["to_revision"]]
        assert superseded_documents, task["task_id"]


def test_designops_reports_are_diff_stable():
    for name in ("reports/designops-qualification.json", "reports/reasoning-chain/designops.json"):
        text = (HUBBENCH_ROOT / name).read_text(encoding="utf-8")
        assert "/Users/" not in text and "/home/" not in text
        payload = json.loads(text)
        assert text == json.dumps(payload, indent=2, sort_keys=True) + "\n"
    qualification = json.loads((HUBBENCH_ROOT / "reports" / "designops-qualification.json").read_text(encoding="utf-8"))
    assert qualification["qualification_passed"] is True
    assert qualification["false_accepts"] == 0
    assert qualification["oracle"]["mean_score"] == 100.0
    assert qualification["mutation_omissions"]["all_detected"] is True
    assert qualification["mutation_omissions"]["total"] == 16
