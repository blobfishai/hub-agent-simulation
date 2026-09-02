"""MCP stdio server and terminal ``tool`` CLI round-trips."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from hubbench.engine.server import handle_request
from hubbench.engine.world import World

HUBBENCH_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = HUBBENCH_ROOT.parent


def test_mcp_handshake_and_tool_call_in_process(family, released_tasks, tmp_path):
    task = released_tasks[2]  # clinicops-003
    with World.fresh(family, task, tmp_path / "mcp.db") as world:
        init = handle_request(world, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert init["result"]["serverInfo"] == {"name": "hubbench-clinicops", "version": family.version}
        assert handle_request(world, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
        listing = handle_request(world, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [tool["name"] for tool in listing["result"]["tools"]]
        assert "hubbench.submit_answer" in names and "scheduling.slots.list" in names
        hints = {tool["name"]: tool["annotations"]["readOnlyHint"] for tool in listing["result"]["tools"]}
        assert hints["scheduling.appointments.update"] is False and hints["ehr.patients.get"] is True
        call = handle_request(world, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "scheduling.appointments.get", "arguments": {"appointment_id": "APPT-24507"}}})
        body = json.loads(call["result"]["content"][0]["text"])
        assert body["status"] == "pending" and call["result"]["isError"] is False
        missing = handle_request(world, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "scheduling.appointments.get", "arguments": {"appointment_id": "APPT-99999"}}})
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
        [sys.executable, "-m", "hubbench.engine.server", "--family", "clinicops", "--task", "clinicops-001", "--db", str(tmp_path / "server.db"), "--fresh"],
        input=requests, capture_output=True, text=True, cwd=BENCHMARK_ROOT, timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    by_id = {response["id"]: response for response in responses}
    assert by_id[1]["result"]["protocolVersion"] == "2025-03-26"
    assert len(by_id[2]["result"]["tools"]) == 34
    context = json.loads(by_id[3]["result"]["content"][0]["text"])
    assert context["reference_records"]["case_reference"] == "CLIN-0001"


def test_tool_cli_round_trip_with_persistent_state(tmp_path):
    env = {**os.environ, "HUBBENCH_FAMILY": "clinicops", "HUBBENCH_TASK": "clinicops-004", "HUBBENCH_DB": str(tmp_path / "cli.db")}
    tool = str(HUBBENCH_ROOT / "bin" / "tool")

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, tool, *args], capture_output=True, text=True, env=env, cwd=tmp_path, timeout=120)

    listing = run("list")
    assert listing.returncode == 0 and "pharmacy.orders.create\twrite" in listing.stdout
    schema = run("schema", "pharmacy.orders.create")
    assert "delivery_option" in schema.stdout
    write = run("pharmacy.orders.create", json.dumps({"supplier_id": "SUP-MERIDIAN", "confirmation_id": "CONF-MER-55207", "medication_code": "IVIG-10G", "quantity": 2, "delivery_option": "expedited"}))
    assert write.returncode == 0, write.stdout + write.stderr
    assert json.loads(write.stdout)["po_id"] == "PO-5101"
    read = run("pharmacy.orders.get", json.dumps({"po_id": "PO-5101"}))
    assert read.returncode == 0 and json.loads(read.stdout)["expected_delivery_date"] == "2026-03-12"
    bad = run("pharmacy.orders.get", json.dumps({"po_id": "PO-9999"}))
    assert bad.returncode == 1
    trace = run("trace")
    assert len(json.loads(trace.stdout)) == 3
