"""WebStudio family: world build, surfaces, oracle, controls, chain audit, release integrity."""

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
def ws_family():
    return load_family("webstudio")


@pytest.fixture(scope="module")
def ws_tasks(ws_family):
    tasks = load_release_tasks(ws_family)
    assert len(tasks) == 8, "the committed webstudio release must hold 8 tasks"
    return tasks


@pytest.fixture(scope="module")
def ws_contracts(ws_family, ws_tasks):
    return {task["task_id"]: load_release_contract(ws_family, task["task_id"]) for task in ws_tasks}


def _primary_step(task):
    return next(step for step in task["oracle_steps"] if step["phase"] == "primary_mutation")


# --------------------------------------------------------------------------- #
# World build and family shape
# --------------------------------------------------------------------------- #


def test_world_builds_and_seeds_every_task(ws_family, ws_tasks, tmp_path):
    for task in ws_tasks:
        with World.fresh(ws_family, task, tmp_path / f"{task['task_id']}.db") as world:
            tables = {row["name"] for row in world.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for expected in ("pages", "entries", "change_requests", "token_versions", "consumers", "licences", "licence_quotes", "checklist_gates", "deploy_windows", "releases", "mutations", "answers", "call_trace"):
                assert expected in tables
            assert world.connection.execute("SELECT COUNT(*) FROM deploy_windows").fetchone()[0] > 0
            assert world.connection.execute("SELECT COUNT(*) FROM design_files WHERE status = 'SUPERSEDED'").fetchone()[0] >= 1
            assert world.connection.execute("PRAGMA foreign_key_check").fetchall() == []
            context = world.call_tool("hubbench.context.get", {})
            assert context["reference_records"]["case_reference"] == f"WEB-{task['task_id'].rsplit('-', 1)[1].zfill(4)}"
            assert len(context["evidence_index"]) == len(task["assets"])
            assert not {"expected", "oracle_steps", "rubric_milestones"} & set(context)


def test_family_world_shape(ws_family, ws_tasks):
    servers = {tool.server for tool in ws_family.tools}
    assert servers == {"cms", "tokens", "design", "dam", "checklist", "cdn", "vendors", "approvals", "messages", "chat", "drive", "notes"}
    assert len(ws_family.tools) == 42
    assert {tool.name for tool in ws_family.tools if tool.hint == "write"} == {
        "cms.releases.create", "cms.releases.update", "tokens.pins.create", "dam.licence_requests.create", "checklist.waivers.create", "notes.drafts.create",
    }
    domain_tables = [line.split()[2] for line in ws_family.schema_sql.splitlines() if line.startswith("CREATE TABLE ")]
    assert len(domain_tables) == 28
    for required in ("approvals", "messages", "chat_threads", "drive_files", "note_drafts", "pages", "entries", "change_requests", "token_versions", "consumers", "licences", "checklist_gates", "deploy_windows", "releases"):
        assert required in domain_tables
    for task in ws_tasks:
        assert len(task["assets"]) >= 28
        assert len({asset["media_type"] for asset in task["assets"]}) >= 7
        assert len(task["expected"]["answer"]) >= 24
        assert sum(len(m["criterion_ids"]) for m in task["rubric_milestones"]) >= 60
        calls = [item["any_of"][0] for item in task["required_investigations"]]
        assert len(calls) >= 26
        assert sum(call["tool"] != "hubbench.context.get" for call in calls) >= 17
        assert len({call["tool"].split(".", 1)[0] for call in calls}) >= 5
        assert len(task["decision_model"]["options"]) == 3
        assert sum(1 for step in task["oracle_steps"] if step["tool"] in ws_family.write_tools and step["tool"] != "hubbench.submit_answer") == 2


# --------------------------------------------------------------------------- #
# Provider mechanics
# --------------------------------------------------------------------------- #


def test_release_create_persists_and_holds_the_window(ws_family, ws_tasks, tmp_path):
    task = ws_tasks[0]  # webstudio-001: release create
    with World.fresh(ws_family, task, tmp_path / "write.db") as world:
        create = _primary_step(task)
        result = world.call_tool(create["tool"], create["arguments"])
        assert result.get("error") is None and result["id"] == "REL-88901"
        readback = world.call_tool("cms.releases.get", {"release_id": "REL-88901"})
        assert readback["status"] == "scheduled" and readback["lane"] == "LANE-WEB-2"
        window = world.one("SELECT status, release_id FROM deploy_windows WHERE window_id = 'DW-2-20260520-PM'")
        assert window == {"status": "busy", "release_id": "REL-88901"}
        mutation = world.one("SELECT mutation_id, table_name FROM mutations WHERE task_id = ?", (task["task_id"],))
        assert mutation == {"mutation_id": f"{task['task_id']}-mutation-01", "table_name": "releases"}


def test_protected_windows_reject_displacement(ws_family, ws_tasks, tmp_path):
    for index in (0, 2, 5, 6):
        task = ws_tasks[index]
        with World.fresh(ws_family, task, tmp_path / f"protected-{index}.db") as world:
            control = task["negative_controls"]["unauthorized_write"]
            result = world.call_tool(control["tool"], control["arguments"])
            assert "error" in result and "protected" in result["error"], task["task_id"]


def test_licence_request_rejects_more_territories_than_the_quote(ws_family, ws_tasks, tmp_path):
    for index in (1, 3):
        task = ws_tasks[index]
        with World.fresh(ws_family, task, tmp_path / f"quote-{index}.db") as world:
            control = task["negative_controls"]["unauthorized_write"]
            result = world.call_tool(control["tool"], control["arguments"])
            assert "error" in result and "covers at most" in result["error"], task["task_id"]
            assert "error" in world.call_tool("dam.licence_requests.create", {**control["arguments"], "territory_count": 1, "quote_id": "QT-NOPE"})


def test_pin_rejects_deprecated_migrated_and_on_page_consumers(ws_family, ws_tasks, tmp_path):
    task = ws_tasks[4]  # webstudio-005: token pin
    with World.fresh(ws_family, task, tmp_path / "pin.db") as world:
        control = task["negative_controls"]["unauthorized_write"]
        result = world.call_tool(control["tool"], control["arguments"])
        assert "error" in result and "4 active consumers outside PAGE-3520" in result["error"]
        create = _primary_step(task)
        pinned = world.call_tool(create["tool"], create["arguments"])
        assert pinned.get("error") is None and pinned["pin_id"] == "PIN-5101" and pinned["consumer_count"] == 4
        duplicate = world.call_tool(create["tool"], create["arguments"])
        assert "error" in duplicate and "already pinned" in duplicate["error"]


def test_subset_release_and_legal_waiver_rules(ws_family, ws_tasks, tmp_path):
    task = ws_tasks[7]  # webstudio-008: subset release
    with World.fresh(ws_family, task, tmp_path / "subset.db") as world:
        control = task["negative_controls"]["unauthorized_write"]
        result = world.call_tool(control["tool"], control["arguments"])
        assert "error" in result and "never waived" in result["error"]
        create = _primary_step(task)
        too_many = world.call_tool(create["tool"], {**create["arguments"], "entry_count": 9})
        assert "error" in too_many and "only 5 of CR-4488's 9 entries are shippable" in too_many["error"]
        scheduled = world.call_tool(create["tool"], create["arguments"])
        assert scheduled.get("error") is None and scheduled["id"] == "REL-88961" and scheduled["entry_count"] == 5
        assert world.call_tool("cms.releases.get", {"release_id": "REL-88961"})["entry_count"] == 5


def test_release_update_re_validates_lanes_and_windows(ws_family, ws_tasks, tmp_path):
    task = ws_tasks[5]  # webstudio-006: lane 1 fenced
    with World.fresh(ws_family, task, tmp_path / "lane.db") as world:
        fenced = world.call_tool("cms.releases.update", {"release_id": "REL-88940", "lane_id": "LANE-WEB-1", "start_time": "2026-05-25T09:00:00", "end_time": "2026-05-25T11:00:00", "status": "scheduled"})
        assert "error" in fenced and "OUT_OF_SERVICE" in fenced["error"]
        moved = world.call_tool(*(lambda step: (step["tool"], step["arguments"]))(_primary_step(task)))
        assert moved.get("error") is None and moved["meta"]["versionId"] == "2" and moved["lane"] == "LANE-EDGE-3"
        assert world.one("SELECT status, release_id FROM deploy_windows WHERE window_id = 'DW-3-20260513-PM'") == {"status": "busy", "release_id": "REL-88940"}


# --------------------------------------------------------------------------- #
# Surfaces
# --------------------------------------------------------------------------- #


def test_mcp_handshake_and_tool_call_in_process(ws_family, ws_tasks, tmp_path):
    task = ws_tasks[2]  # webstudio-003
    with World.fresh(ws_family, task, tmp_path / "mcp.db") as world:
        init = handle_request(world, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert init["result"]["serverInfo"] == {"name": "hubbench-webstudio", "version": ws_family.version}
        listing = handle_request(world, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [tool["name"] for tool in listing["result"]["tools"]]
        assert "hubbench.submit_answer" in names and "cdn.windows.list" in names and "tokens.consumers.list" in names and len(names) == 44
        hints = {tool["name"]: tool["annotations"]["readOnlyHint"] for tool in listing["result"]["tools"]}
        assert hints["cms.releases.update"] is False and hints["cms.pages.get"] is True
        call = handle_request(world, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "cms.releases.get", "arguments": {"release_id": "REL-88922"}}})
        body = json.loads(call["result"]["content"][0]["text"])
        assert body["status"] == "pending" and call["result"]["isError"] is False
        scoped = handle_request(world, {"jsonrpc": "2.0", "id": 4, "method": "tools/list"}, "dam")
        assert [tool["name"] for tool in scoped["result"]["tools"]] and all(tool["name"].startswith("dam.") for tool in scoped["result"]["tools"])
        missing = handle_request(world, {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "cms.releases.get", "arguments": {"release_id": "REL-99999"}}})
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
        [sys.executable, "-m", "hubbench.engine.server", "--family", "webstudio", "--task", "webstudio-001", "--db", str(tmp_path / "server.db"), "--fresh"],
        input=requests, capture_output=True, text=True, cwd=BENCHMARK_ROOT, timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    by_id = {response["id"]: response for response in responses}
    assert by_id[1]["result"]["protocolVersion"] == "2025-03-26"
    assert len(by_id[2]["result"]["tools"]) == 44
    context = json.loads(by_id[3]["result"]["content"][0]["text"])
    assert context["reference_records"]["case_reference"] == "WEB-0001"


def test_tool_cli_round_trip_with_persistent_state(tmp_path):
    env = {**os.environ, "HUBBENCH_FAMILY": "webstudio", "HUBBENCH_TASK": "webstudio-004", "HUBBENCH_DB": str(tmp_path / "cli.db")}
    env.pop("HUBBENCH_URL", None)
    tool = str(HUBBENCH_ROOT / "bin" / "tool")

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, tool, *args], capture_output=True, text=True, env=env, cwd=tmp_path, timeout=120)

    listing = run("list")
    assert listing.returncode == 0 and "dam.licence_requests.create\twrite" in listing.stdout
    schema = run("schema", "dam.licence_requests.create")
    assert "issuance_option" in schema.stdout
    write = run("dam.licence_requests.create", json.dumps({"vendor_id": "VND-GLYPHWORKS", "quote_id": "QT-GW-31902", "asset_id": "AST-FONT-5162", "territory_count": 2, "issuance_option": "expedited"}))
    assert write.returncode == 0, write.stdout + write.stderr
    assert json.loads(write.stdout)["request_id"] == "LR-6201"
    read = run("dam.licence_requests.get", json.dumps({"request_id": "LR-6201"}))
    assert read.returncode == 0 and json.loads(read.stdout)["expected_licence_date"] == "2026-05-14"
    bad = run("dam.licence_requests.get", json.dumps({"request_id": "LR-9999"}))
    assert bad.returncode == 1
    trace = run("trace")
    assert len(json.loads(trace.stdout)) == 3


# --------------------------------------------------------------------------- #
# Verifier and controls
# --------------------------------------------------------------------------- #


def test_oracle_passes_every_released_task(ws_family, ws_tasks, tmp_path):
    for task in ws_tasks:
        episode = run_episode(ws_family, task, "oracle", tmp_path / f"oracle-{task['task_id']}.db")
        assert episode["strict_pass"], {check["id"]: check["evidence"] for check in episode["checks"] if not check["passed"]}
        assert episode["score"] == 100.0


def test_unauthorized_write_control_is_rejected(ws_family, ws_tasks, tmp_path):
    for task in (ws_tasks[1], ws_tasks[4], ws_tasks[7]):
        episode = run_episode(ws_family, task, "unauthorized_write", tmp_path / f"unauth-{task['task_id']}.db")
        assert not episode["strict_pass"], task["task_id"]


def test_wrong_evidence_and_wrong_value_controls_are_rejected(ws_family, ws_tasks, tmp_path):
    for task in (ws_tasks[0], ws_tasks[6]):
        episode = run_episode(ws_family, task, "wrong_evidence", tmp_path / f"decoy-{task['task_id']}.db")
        assert not episode["strict_pass"], task["task_id"]
    episode = run_episode(ws_family, ws_tasks[7], "wrong_value", tmp_path / "wrong-value.db")
    assert not episode["strict_pass"] and episode["score"] < 100.0


def test_noop_scores_near_zero(ws_family, ws_tasks, tmp_path):
    episode = run_episode(ws_family, ws_tasks[3], "noop", tmp_path / "noop.db")
    assert episode["score"] < 10.0


# --------------------------------------------------------------------------- #
# Reasoning-chain audit (unmodified portfolio adapter path) and release integrity
# --------------------------------------------------------------------------- #


def _load_chain_adapter():
    spec = importlib.util.spec_from_file_location("hubbench_chain_adapter_webstudio", HUBBENCH_ROOT / "chain_adapter.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_chain_audit_passes_all_tasks_and_report_is_current():
    adapter = _load_chain_adapter()
    report = adapter.measure_family("webstudio")
    assert report["measuredTasks"] == 8
    assert report["passingTasks"] == 8, report["failures"]
    assert report["meetsStandard"] is True
    assert report["chainDepth"] == {"min": 8, "max": 8}
    for hop in (f"H{i}" for i in range(1, 14)):
        assert report["hopCoverage"][hop] == 8, hop
    committed = json.loads((HUBBENCH_ROOT / "reports" / "reasoning-chain" / "webstudio.json").read_text(encoding="utf-8"))
    assert committed == report, "committed chain report is stale; rerun chain_adapter.py --family webstudio --write"


def test_committed_release_matches_fresh_build(ws_family, ws_tasks, ws_contracts):
    fresh = ws_family.build_tasks()
    assert [task["task_id"] for task in fresh] == [task["task_id"] for task in ws_tasks]
    for built, released in zip(fresh, ws_tasks):
        assert sha256_json(built) == sha256_json(released), f"{released['task_id']} release is stale; rerun build_release.py --family webstudio"
        assert sha256_json(sealed_contract(built)) == sha256_json(ws_contracts[released["task_id"]])


def test_release_meets_realism_standard_and_modes(ws_tasks):
    validate_tasks(ws_tasks)
    standard = read_standard()["requirements"]
    for task in ws_tasks:
        assert standard["employeeRequest"]["minimumWords"] <= word_count(task["instruction"]) <= standard["employeeRequest"]["maximumWords"]
        assert len(task["assets"]) >= standard["assetRoom"]["minimumAgentVisibleFilesPerTask"]
        assert len({asset["media_type"] for asset in task["assets"]}) >= standard["assetRoom"]["minimumNativeFormatsPerTask"]
        assert sum(len(m["criterion_ids"]) for m in task["rubric_milestones"]) >= standard["rubric"]["minimumSpecificCriteriaPerTask"]
        assert len(task["expected"]["answer"]) >= standard["reasoningChain"]["minimumGradedAnswerFields"]
        assert len(task["required_investigations"]) >= standard["workflow"]["minimumProviderEvidenceReadsPerTask"]
    assert sorted(task["mode"] for task in ws_tasks) == sorted(["plan"] * 3 + ["quantity"] * 3 + ["schedule"] * 2)
    instructions = [task["instruction"] for task in ws_tasks]
    assert len(set(instructions)) == len(instructions)
    for index, left in enumerate(instructions):
        for right in instructions[index + 1 :]:
            assert shingle_jaccard(left, right) <= 0.8
    signatures = [task["sequence_signature"] for task in ws_tasks]
    assert len(set(signatures)) == len(signatures)


def test_decoys_are_stale_and_distinct_from_current_evidence(ws_tasks):
    kinds = {task["task_id"]: {asset["kind"] for asset in task["assets"]} for task in ws_tasks}
    assert "policy_superseded" in kinds["webstudio-001"]
    assert "stale_token_export" in kinds["webstudio-002"] and "stale_token_export" in kinds["webstudio-005"]
    assert "decoy_change_request" in kinds["webstudio-003"] and "decoy_change_request" in kinds["webstudio-007"]
    assert "superseded_frame" in kinds["webstudio-006"]
    assert "stale_licence_letter" in kinds["webstudio-008"]
    for task in ws_tasks:
        decoy_file = task["negative_controls"]["wrong_evidence"]["arguments"]["file_id"]
        drive = {row["file_id"]: row for row in task["seed_tables"]["drive_files"]}
        assert decoy_file in drive
        required_exports = {call["arguments"]["file_id"] for call in task["required_read_calls"] if call["tool"] == "drive.files.export"}
        assert decoy_file not in required_exports
        assert any(row["status"] == "SUPERSEDED" for row in task["seed_tables"]["design_frames"])


def test_webstudio_reports_are_diff_stable():
    for name in ("reports/webstudio-qualification.json", "reports/reasoning-chain/webstudio.json"):
        text = (HUBBENCH_ROOT / name).read_text(encoding="utf-8")
        assert "/Users/" not in text and "/home/" not in text
        payload = json.loads(text)
        assert text == json.dumps(payload, indent=2, sort_keys=True) + "\n"
    qualification = json.loads((HUBBENCH_ROOT / "reports" / "webstudio-qualification.json").read_text(encoding="utf-8"))
    assert qualification["qualification_passed"] is True
    assert qualification["false_accepts"] == 0
    assert qualification["oracle"]["mean_score"] == 100.0
    assert qualification["determinism"]["deterministic"] is True
    assert qualification["mutation_omissions"] == {**qualification["mutation_omissions"], "total": 16, "detected": 16, "all_detected": True}
