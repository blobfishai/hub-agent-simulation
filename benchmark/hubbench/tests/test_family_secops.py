"""SecOps family: world build, surfaces, oracle, controls, chain audit, release integrity."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
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
EXTERNAL_WORDS = re.compile(r"external|supplier|vendor|attachment|counterpart", re.I)
CAPACITY_WORDS = re.compile(r"calendar|capacity|window|schedule|shift|slot|dispatch", re.I)


@pytest.fixture(scope="module")
def secops_family():
    return load_family("secops")


@pytest.fixture(scope="module")
def secops_tasks(secops_family):
    tasks = load_release_tasks(secops_family)
    assert len(tasks) == 8, "the committed secops release must hold 8 tasks"
    return tasks


@pytest.fixture(scope="module")
def secops_contracts(secops_family, secops_tasks):
    return {task["task_id"]: load_release_contract(secops_family, task["task_id"]) for task in secops_tasks}


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


def test_world_builds_and_seeds_every_task(secops_family, secops_tasks, tmp_path):
    for task in secops_tasks:
        with World.fresh(secops_family, task, tmp_path / f"{task['task_id']}.db") as world:
            tables = {row["name"] for row in world.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for expected in (
                "identities",
                "grant_inventory",
                "grant_sets",
                "alerts",
                "alert_events",
                "detection_rules",
                "hosts",
                "sessions",
                "mfa_factors",
                "oncall_windows",
                "bridges",
                "invalidation_confirmations",
                "revocations",
                "mutations",
                "answers",
                "call_trace",
            ):
                assert expected in tables
            assert world.connection.execute("SELECT COUNT(*) FROM oncall_windows").fetchone()[0] > 0
            assert world.connection.execute("SELECT COUNT(*) FROM detection_rules WHERE status = 'retired'").fetchone()[0] >= 1
            assert world.connection.execute("SELECT COUNT(*) FROM alerts WHERE status = 'suppressed'").fetchone()[0] >= 1
            assert world.connection.execute("PRAGMA foreign_key_check").fetchall() == []
            context = world.call_tool("hubbench.context.get", {})
            assert context["reference_records"]["case_reference"] == f"SEC-{task['task_id'].rsplit('-', 1)[1].zfill(4)}"
            assert len(context["evidence_index"]) == len(task["assets"])


def test_family_world_shape(secops_family, secops_tasks):
    servers = {tool.server for tool in secops_family.tools}
    assert servers == {"siem", "edr", "iam", "cloudiam", "servicedesk", "playbooks", "oncall", "idpvendor", "approvals", "messages", "chat", "drive", "notes"}
    assert len(secops_family.tools) == 46
    domain_tables = [line.split()[2] for line in secops_family.schema_sql.splitlines() if line.startswith("CREATE TABLE ")]
    assert len(domain_tables) == 26
    for required in ("approvals", "messages", "chat_threads", "drive_files", "note_drafts", "alerts", "detection_rules", "grant_sets", "oncall_windows", "invalidation_confirmations"):
        assert required in domain_tables
    for task in secops_tasks:
        assert len(task["assets"]) >= 28
        assert len({asset["media_type"] for asset in task["assets"]}) >= 7
        assert len(task["expected"]["answer"]) >= 24
        assert sum(len(m["criterion_ids"]) for m in task["rubric_milestones"]) >= 60
        calls = [item["any_of"][0] for item in task["required_investigations"]]
        assert len(calls) >= 26
        assert sum(call["tool"] != "hubbench.context.get" for call in calls) >= 17
        assert len({call["tool"].split(".", 1)[0] for call in calls}) >= 5


def test_world_is_defensive_containment_only(secops_family):
    writes = {tool.name for tool in secops_family.tools if tool.hint == "write"}
    assert writes == {"iam.revocations.create", "oncall.bridges.create", "oncall.bridges.update", "idpvendor.orders.create", "notes.drafts.create"}
    for tool in secops_family.tools:
        assert not re.search(r"exploit|attack|payload|malware|implant", tool.name + " " + tool.description, re.I)


def test_writes_persist_and_readbacks_reflect_them(secops_family, secops_tasks, tmp_path):
    task = secops_tasks[0]  # secops-001: bridge create
    with World.fresh(secops_family, task, tmp_path / "write.db") as world:
        create = next(step for step in task["oracle_steps"] if step["phase"] == "primary_mutation")
        result = world.call_tool(create["tool"], create["arguments"])
        assert result.get("error") is None and result["id"] == "BRG-70901"
        readback = world.call_tool("oncall.bridges.get", {"bridge_id": "BRG-70901"})
        assert readback["status"] == "booked" and readback["responder"] == "RESP-2"
        window = world.one("SELECT status, bridge_id FROM oncall_windows WHERE window_id = 'OCW-2-20260617-PM'")
        assert window == {"status": "busy", "bridge_id": "BRG-70901"}
        mutation = world.one("SELECT mutation_id, table_name FROM mutations WHERE task_id = ?", (task["task_id"],))
        assert mutation == {"mutation_id": f"{task['task_id']}-mutation-01", "table_name": "bridges"}


def test_protected_windows_reject_displacement(secops_family, secops_tasks, tmp_path):
    task = secops_tasks[0]
    with World.fresh(secops_family, task, tmp_path / "protected.db") as world:
        control = task["negative_controls"]["unauthorized_write"]
        result = world.call_tool(control["tool"], control["arguments"])
        assert "error" in result and "protected" in result["error"]


def test_tenant_revocation_rejects_unrevocable_objects(secops_family, secops_tasks, tmp_path):
    task = secops_tasks[4]  # secops-005: partner-key revocation
    with World.fresh(secops_family, task, tmp_path / "revoke.db") as world:
        control = task["negative_controls"]["unauthorized_write"]
        result = world.call_tool(control["tool"], control["arguments"])
        assert "error" in result and "tenant-revocable" in result["error"]
        primary = next(step for step in task["oracle_steps"] if step["phase"] == "primary_mutation")
        accepted = world.call_tool(primary["tool"], primary["arguments"])
        assert accepted["revocation_id"] == "RVK-3401" and accepted["object_count"] == 3


def test_vendor_order_rejects_over_allocation_and_closed_confirmations(secops_family, secops_tasks, tmp_path):
    task = secops_tasks[0]
    with World.fresh(secops_family, task, tmp_path / "order.db") as world:
        over = world.call_tool("idpvendor.orders.create", {"vendor_id": "VND-HALYARD", "confirmation_id": "CONF-HAL-88214", "credential_class": "GRANT-SSO-APP", "object_count": 13, "service_option": "standard"})
        assert "error" in over and "covers at most" in over["error"]
        expired = world.call_tool("idpvendor.orders.create", {"vendor_id": "VND-HALYARD", "confirmation_id": "CONF-HAL-88102", "credential_class": "GRANT-SSO-APP", "object_count": 1, "service_option": "standard"})
        assert "error" in expired and "EXPIRED" in expired["error"]
        assert world.connection.execute("SELECT COUNT(*) FROM mutations").fetchone()[0] == 0


def test_mcp_handshake_and_tool_call_in_process(secops_family, secops_tasks, tmp_path):
    task = secops_tasks[2]  # secops-003
    with World.fresh(secops_family, task, tmp_path / "mcp.db") as world:
        init = handle_request(world, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert init["result"]["serverInfo"] == {"name": "hubbench-secops", "version": secops_family.version}
        listing = handle_request(world, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [tool["name"] for tool in listing["result"]["tools"]]
        assert "hubbench.submit_answer" in names and "oncall.windows.list" in names and "siem.rules.get" in names
        hints = {tool["name"]: tool["annotations"]["readOnlyHint"] for tool in listing["result"]["tools"]}
        assert hints["oncall.bridges.update"] is False and hints["iam.identities.get"] is True
        scoped = handle_request(world, {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}, "siem")
        assert [tool["name"] for tool in scoped["result"]["tools"]] and all(tool["name"].startswith("siem.") for tool in scoped["result"]["tools"])
        call = handle_request(world, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "oncall.bridges.get", "arguments": {"bridge_id": "BRG-70877"}}})
        body = json.loads(call["result"]["content"][0]["text"])
        assert body["status"] == "pending" and call["result"]["isError"] is False
        missing = handle_request(world, {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "oncall.bridges.get", "arguments": {"bridge_id": "BRG-99999"}}})
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
        [sys.executable, "-m", "hubbench.engine.server", "--family", "secops", "--task", "secops-001", "--db", str(tmp_path / "server.db"), "--fresh"],
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
    assert len(by_id[2]["result"]["tools"]) == 48
    context = json.loads(by_id[3]["result"]["content"][0]["text"])
    assert context["reference_records"]["case_reference"] == "SEC-0001"


def test_tool_cli_round_trip_with_persistent_state(tmp_path):
    env = {**os.environ, "HUBBENCH_FAMILY": "secops", "HUBBENCH_TASK": "secops-004", "HUBBENCH_DB": str(tmp_path / "cli.db")}
    env.pop("HUBBENCH_URL", None)
    tool = str(HUBBENCH_ROOT / "bin" / "tool")

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, tool, *args], capture_output=True, text=True, env=env, cwd=tmp_path, timeout=120)

    listing = run("list")
    assert listing.returncode == 0 and "idpvendor.orders.create\twrite" in listing.stdout
    schema = run("schema", "idpvendor.orders.create")
    assert "service_option" in schema.stdout
    write = run(
        "idpvendor.orders.create",
        json.dumps({"vendor_id": "VND-HALYARD", "confirmation_id": "CONF-HAL-66207", "credential_class": "SESSION-FED", "object_count": 2, "service_option": "expedited"}),
    )
    assert write.returncode == 0, write.stdout + write.stderr
    assert json.loads(write.stdout)["order_id"] == "IVO-3401"
    read = run("idpvendor.orders.get", json.dumps({"order_id": "IVO-3401"}))
    assert read.returncode == 0 and json.loads(read.stdout)["expected_ready_date"] == "2026-06-11"
    bad = run("idpvendor.orders.get", json.dumps({"order_id": "IVO-9999"}))
    assert bad.returncode == 1
    trace = run("trace")
    assert len(json.loads(trace.stdout)) == 3


def test_http_surfaces_share_one_world(secops_family, secops_tasks, tmp_path):
    task = secops_tasks[3]  # secops-004: expedited invalidation order
    server = build_server(secops_family, task, tmp_path / "http.db", host="127.0.0.1", port=0, fresh=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = server.url
        status, context = _http_json(base, "GET", "/api/v1/task")
        assert status == 200 and context["task"]["task_id"] == "secops-004"
        assert {"siem", "edr", "iam", "idpvendor", "hubbench"} <= {item["name"] for item in context["tool_servers"]}
        status, listing = _http_json(base, "POST", "/mcp/siem", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert status == 200 and all(tool["name"].startswith("siem.") for tool in listing["result"]["tools"])
        status, created = _http_json(base, "POST", "/api/v1/tools/idpvendor.orders.create", {"vendor_id": "VND-HALYARD", "confirmation_id": "CONF-HAL-66207", "credential_class": "SESSION-FED", "object_count": 2, "service_option": "expedited"})
        assert status == 200 and created["order_id"] == "IVO-3401"
        status, order = _http_json(base, "GET", "/api/v1/idpvendor/orders/IVO-3401")
        assert status == 200 and order["expected_ready_date"] == "2026-06-11"
        status, rejected = _http_json(base, "POST", "/api/v1/tools/iam.revocations.create", {"credential_class": "SESSION-FED", "object_count": 9, "identity_id": "ID-41050", "system": "iam", "effective_date": "2026-06-10"})
        assert status == 422 and "tenant-revocable" in rejected["error"]
    finally:
        server.shutdown()
        server.server_close()
        server.session.close()
        thread.join(timeout=5)
    with World(secops_family, task, tmp_path / "http.db") as world:
        assert [entry["tool"] for entry in world.trace if entry["success"]].count("idpvendor.orders.create") == 1


def test_oracle_passes_every_released_task(secops_family, secops_tasks, tmp_path):
    for task in secops_tasks:
        episode = run_episode(secops_family, task, "oracle", tmp_path / f"oracle-{task['task_id']}.db")
        assert episode["strict_pass"], {check["id"]: check["evidence"] for check in episode["checks"] if not check["passed"]}
        assert episode["score"] == 100.0


def test_unauthorized_write_control_is_rejected(secops_family, secops_tasks, tmp_path):
    for task in (secops_tasks[1], secops_tasks[5]):
        episode = run_episode(secops_family, task, "unauthorized_write", tmp_path / f"unauth-{task['task_id']}.db")
        assert not episode["strict_pass"], task["task_id"]


def test_wrong_evidence_control_is_rejected(secops_family, secops_tasks, tmp_path):
    for task in (secops_tasks[0], secops_tasks[7]):
        episode = run_episode(secops_family, task, "wrong_evidence", tmp_path / f"decoy-{task['task_id']}.db")
        assert not episode["strict_pass"], task["task_id"]


def test_external_and_capacity_evidence_are_read_before_the_decision(secops_tasks):
    for task in secops_tasks:
        investigations = [item for item in task["required_investigations"] if item.get("before_primary_mutation")]
        assert any(EXTERNAL_WORDS.search(item["description"]) and item["any_of"][0]["tool"] == "idpvendor.confirmations.get" for item in investigations), task["task_id"]
        assert any(item["milestone_id"] == "investigation.constraints" and CAPACITY_WORDS.search(item["description"]) and item["any_of"][0]["tool"] == "oncall.windows.list" for item in investigations), task["task_id"]
        tools = {item["any_of"][0]["tool"] for item in investigations}
        assert {"siem.alerts.get", "siem.events.list", "siem.rules.get", "iam.sessions.list", "iam.factors.list", "iam.grants.list", "playbooks.tiers.get", "approvals.get"} <= tools, task["task_id"]
        mutating = [step for step in task["oracle_steps"] if step["tool"] in {"iam.revocations.create", "oncall.bridges.create", "oncall.bridges.update", "idpvendor.orders.create"}]
        assert len(mutating) == 1, task["task_id"]
        submit = next(step for step in task["oracle_steps"] if step["tool"] == SUBMIT_TOOL)
        assert submit["arguments"]["recommended_option"] == task["decision_model"]["selected_option"]


def _load_chain_adapter():
    spec = importlib.util.spec_from_file_location("hubbench_chain_adapter_secops", HUBBENCH_ROOT / "chain_adapter.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_chain_audit_passes_all_tasks_and_report_is_current():
    adapter = _load_chain_adapter()
    report = adapter.measure_family("secops")
    assert report["measuredTasks"] == 8
    assert report["passingTasks"] == 8, report["failures"]
    assert report["meetsStandard"] is True
    assert report["chainDepth"] == {"min": 8, "max": 8}
    for hop in (f"H{i}" for i in range(1, 14)):
        assert report["hopCoverage"][hop] == 8, hop
    committed = json.loads((HUBBENCH_ROOT / "reports" / "reasoning-chain" / "secops.json").read_text(encoding="utf-8"))
    assert committed == report, "committed chain report is stale; rerun chain_adapter.py --family secops --write"


def test_committed_release_matches_fresh_build(secops_family, secops_tasks, secops_contracts):
    fresh = secops_family.build_tasks()
    assert [task["task_id"] for task in fresh] == [task["task_id"] for task in secops_tasks]
    for built, released in zip(fresh, secops_tasks):
        assert sha256_json(built) == sha256_json(released), f"{released['task_id']} release is stale; rerun build_release.py --family secops"
        assert sha256_json(sealed_contract(built)) == sha256_json(secops_contracts[released["task_id"]])


def test_release_meets_realism_standard_and_modes(secops_tasks):
    validate_tasks(secops_tasks)
    standard = read_standard()["requirements"]
    for task in secops_tasks:
        assert standard["employeeRequest"]["minimumWords"] <= word_count(task["instruction"]) <= standard["employeeRequest"]["maximumWords"]
        assert len(task["assets"]) >= standard["assetRoom"]["minimumAgentVisibleFilesPerTask"]
        assert len({asset["media_type"] for asset in task["assets"]}) >= standard["assetRoom"]["minimumNativeFormatsPerTask"]
        assert sum(len(m["criterion_ids"]) for m in task["rubric_milestones"]) >= standard["rubric"]["minimumSpecificCriteriaPerTask"]
        assert len(task["expected"]["answer"]) >= standard["reasoningChain"]["minimumGradedAnswerFields"]
        assert len(task["required_investigations"]) >= standard["workflow"]["minimumProviderEvidenceReadsPerTask"]
    assert sorted(task["mode"] for task in secops_tasks) == sorted(["plan"] * 3 + ["quantity"] * 3 + ["schedule"] * 2)
    instructions = [task["instruction"] for task in secops_tasks]
    assert len(set(instructions)) == len(instructions)
    for index, left in enumerate(instructions):
        for right in instructions[index + 1 :]:
            assert shingle_jaccard(left, right) <= 0.72
    signatures = [task["sequence_signature"] for task in secops_tasks]
    assert len(set(signatures)) == len(signatures)


def test_decoys_are_stale_and_distinct_from_current_evidence(secops_tasks):
    kinds = {task["task_id"]: {asset["kind"] for asset in task["assets"]} for task in secops_tasks}
    assert "policy_superseded" in kinds["secops-001"]
    assert "decoy_ticket" in kinds["secops-003"]
    assert "decoy_alert" in kinds["secops-006"]
    for task in secops_tasks:
        assert "policy_superseded" in kinds[task["task_id"]] and "authority_superseded" in kinds[task["task_id"]]
        decoy_file = task["negative_controls"]["wrong_evidence"]["arguments"]["file_id"]
        drive = {row["file_id"]: row for row in task["seed_tables"]["drive_files"]}
        assert decoy_file in drive
        required_exports = {call["arguments"]["file_id"] for call in task["required_read_calls"] if call["tool"] == "drive.files.export"}
        assert decoy_file not in required_exports
        assert any(rule["status"] == "retired" for rule in task["seed_tables"]["detection_rules"])
        assert any(row["status"] in {"ROTATED", "EXPIRED", "REVOKED", "DISABLED"} or row["deferred_for_ticket"] or row["register_flag"] for row in task["seed_tables"]["grant_sets"])


def test_secops_reports_are_diff_stable():
    for name in ("reports/secops-qualification.json", "reports/reasoning-chain/secops.json"):
        text = (HUBBENCH_ROOT / name).read_text(encoding="utf-8")
        assert "/Users/" not in text and "/home/" not in text
        payload = json.loads(text)
        assert text == json.dumps(payload, indent=2, sort_keys=True) + "\n"
    qualification = json.loads((HUBBENCH_ROOT / "reports" / "secops-qualification.json").read_text(encoding="utf-8"))
    assert qualification["qualification_passed"] is True
    assert qualification["false_accepts"] == 0
    assert qualification["oracle"]["mean_score"] == 100.0
    assert qualification["determinism"]["exact_episode_matches"] == 8
    assert qualification["mutation_omissions"]["all_detected"] is True
    assert qualification["mutation_omissions"]["total"] == 16
