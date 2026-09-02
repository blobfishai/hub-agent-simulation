"""HTTP surfaces over one world: MCP over streamable HTTP, REST, website, remote CLI, stdio — one durable trace."""

from __future__ import annotations

import html
import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from types import SimpleNamespace
from typing import Any

import pytest

from hubbench.engine.families import CONTEXT_TOOL, SUBMIT_TOOL
from hubbench.engine.http import Catalog, build_server, coerce_arguments
from hubbench.engine.server import PROTOCOL_VERSION, handle_message, handle_request
from hubbench.engine.world import World

from .test_surfaces import BENCHMARK_ROOT, HUBBENCH_ROOT

ORDER = {"supplier_id": "SUP-MERIDIAN", "confirmation_id": "CONF-MER-55207", "medication_code": "IVIG-10G", "quantity": 2, "delivery_option": "expedited"}


def http(base: str, method: str, path: str, body: Any = None, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
    data = None
    sent = dict(headers or {})
    if isinstance(body, (dict, list)):
        data = json.dumps(body).encode("utf-8")
        sent.setdefault("Content-Type", "application/json")
    elif isinstance(body, str):
        data = body.encode("utf-8")
        sent.setdefault("Content-Type", "application/x-www-form-urlencoded")
    request = urllib.request.Request(base + path, data=data, method=method, headers=sent)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, {key: value for key, value in response.headers.items()}, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, {key: value for key, value in exc.headers.items()}, exc.read()


def http_json(base: str, method: str, path: str, body: Any = None, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], Any]:
    status, response_headers, raw = http(base, method, path, body, headers)
    return status, response_headers, json.loads(raw) if raw else None


def rpc(base: str, path: str, method: str, params: dict[str, Any] | None = None, request_id: int = 1) -> tuple[int, dict[str, str], Any]:
    message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return http_json(base, "POST", path, message)


def tool_text(response: dict[str, Any]) -> dict[str, Any]:
    return json.loads(response["result"]["content"][0]["text"])


@pytest.fixture(scope="module")
def site(family, released_tasks, tmp_path_factory):
    task = released_tasks[3]  # clinicops-004: the pharmacy order write with a known readback
    database = tmp_path_factory.mktemp("http-surfaces") / "world.db"
    server = build_server(family, task, database, host="127.0.0.1", port=0, fresh=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield SimpleNamespace(url=server.url, task=task, database=database, catalog=server.catalog)
    finally:
        server.shutdown()
        server.server_close()
        server.session.close()
        thread.join(timeout=5)


# --------------------------------------------------------------------------- #
# Pure pieces
# --------------------------------------------------------------------------- #


def test_catalog_routes_tools_by_server_resource_operation(family, released_tasks):
    catalog = Catalog(family, released_tasks[3])
    assert len(catalog.tools) == 34
    orders_get = catalog.tools["pharmacy.orders.get"]
    assert (orders_get.server, orders_get.resource, orders_get.operation, orders_get.id_parameter) == ("pharmacy", "orders", "get", "po_id")
    assert catalog.collection("pharmacy", "orders").name == "pharmacy.orders.list"
    assert catalog.collection("ehr", "patients").name == "ehr.patients.search"
    assert catalog.item("notes", "drafts") is None and catalog.collection("notes", "drafts") is None
    approvals_get = catalog.tools["approvals.get"]
    assert (approvals_get.resource, approvals_get.id_parameter) == ("approvals", "approval_id")
    route, identifier = catalog.item_shorthand("approvals", "AP-CO-0090")
    assert route.name == "approvals.get" and identifier == "AP-CO-0090"
    assert catalog.item_shorthand("pharmacy", "orders") is None
    assert catalog.tools[SUBMIT_TOOL].server == "hubbench" and catalog.tools[CONTEXT_TOOL].resource == "context"
    assert catalog.server_order[-1] == "hubbench" and catalog.server_order[:3] == ["ehr", "pharmacy", "scheduling"]
    entry = orders_get.catalog_entry()
    assert entry["endpoints"]["item"] == "GET /api/v1/pharmacy/orders/<po_id>"
    assert entry["input_schema"]["required"] == ["po_id"] and entry["hint"] == "read"


def test_coerce_arguments_follows_the_input_schema():
    schema = {
        "type": "object",
        "properties": {
            "count": {"type": "integer"},
            "ratio": {"type": "number"},
            "flag": {"type": "boolean"},
            "ids": {"type": "array", "items": {"type": "string"}},
            "meta": {"type": "object"},
            "name": {"type": "string"},
        },
    }
    coerced = coerce_arguments(
        {"count": ["3"], "ratio": ["12.50"], "flag": ["true"], "ids": ["A", "B"], "meta": ['{"k": 1}'], "name": ["x"], "blank": [""], "extra": ["kept"]},
        schema,
    )
    assert coerced == {"count": 3, "ratio": 12.5, "flag": True, "ids": ["A", "B"], "meta": {"k": 1}, "name": "x", "extra": "kept"}
    assert coerce_arguments({"ids": ['["A","B"]'], "count": ["nope"]}, schema) == {"ids": ["A", "B"], "count": "nope"}
    assert coerce_arguments({"ratio": "7"}, schema) == {"ratio": 7}


def test_json_rpc_core_scoped_to_one_server(family, released_tasks, tmp_path):
    with World.fresh(family, released_tasks[3], tmp_path / "scoped.db") as world:
        init = handle_request(world, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, "pharmacy")
        assert init["result"]["serverInfo"]["name"] == "hubbench-clinicops-pharmacy"
        assert "'pharmacy' server only" in init["result"]["instructions"]
        listing = handle_request(world, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, "pharmacy")
        names = [tool["name"] for tool in listing["result"]["tools"]]
        assert names and all(name.startswith("pharmacy.") for name in names)
        controls = handle_request(world, {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}, "hubbench")
        assert [tool["name"] for tool in controls["result"]["tools"]] == [CONTEXT_TOOL, SUBMIT_TOOL]
        blocked = handle_request(world, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "ehr.patients.get", "arguments": {"patient_id": "x"}}}, "pharmacy")
        assert blocked["result"]["isError"] is True and "not exposed by server 'pharmacy'" in tool_text(blocked)["error"]
        assert world.trace == []  # an unexposed call never reaches the world
        allowed = handle_request(world, {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "pharmacy.orders.get", "arguments": {"po_id": "PO-5100"}}}, "pharmacy")
        assert tool_text(allowed)["status"] == "RECEIVED" and len(world.trace) == 1
        contract = handle_request(world, {"jsonrpc": "2.0", "id": 6, "method": "resources/read", "params": {"uri": "hubbench://clinicops/tasks/clinicops-004/tool-contract"}}, "pharmacy")
        assert all(tool["name"].startswith("pharmacy.") for tool in json.loads(contract["result"]["contents"][0]["text"])["tools"])
        batch = handle_message(world, [{"jsonrpc": "2.0", "id": 7, "method": "ping"}, {"jsonrpc": "2.0", "method": "notifications/initialized"}])
        assert batch == [{"jsonrpc": "2.0", "id": 7, "result": {}}]
        assert handle_message(world, [{"jsonrpc": "2.0", "method": "notifications/initialized"}]) is None
        assert handle_message(world, [])["error"]["code"] == -32600
        assert handle_request(world, ["not", "an", "object"])["error"]["code"] == -32600


# --------------------------------------------------------------------------- #
# In-process HTTP server
# --------------------------------------------------------------------------- #


def test_mcp_over_streamable_http(site):
    status, headers, init = rpc(site.url, "/mcp", "initialize", {})
    assert status == 200 and headers["Content-Type"].startswith("application/json")
    assert headers["MCP-Protocol-Version"] == PROTOCOL_VERSION and headers["Mcp-Session-Id"]
    assert init["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert init["result"]["serverInfo"] == {"name": "hubbench-clinicops", "version": site.catalog.family.version}
    status, _, raw = http(site.url, "POST", "/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert status == 202 and raw == b""
    status, _, listing = rpc(site.url, "/mcp/pharmacy", "tools/list")
    names = [tool["name"] for tool in listing["result"]["tools"]]
    assert status == 200 and names and all(name.startswith("pharmacy.") for name in names)
    _, _, controls = rpc(site.url, "/mcp/hubbench", "tools/list")
    assert [tool["name"] for tool in controls["result"]["tools"]] == [CONTEXT_TOOL, SUBMIT_TOOL]
    _, _, everything = rpc(site.url, "/mcp", "tools/list")
    assert len(everything["result"]["tools"]) == 34
    _, _, per_server = rpc(site.url, "/mcp/pharmacy", "initialize", {})
    assert per_server["result"]["serverInfo"]["name"] == "hubbench-clinicops-pharmacy"
    _, _, read = rpc(site.url, "/mcp/pharmacy", "tools/call", {"name": "pharmacy.orders.get", "arguments": {"po_id": "PO-5100"}})
    assert read["result"]["isError"] is False and tool_text(read)["status"] == "RECEIVED"
    _, _, blocked = rpc(site.url, "/mcp/pharmacy", "tools/call", {"name": "ehr.patients.get", "arguments": {"patient_id": "x"}})
    assert blocked["result"]["isError"] is True and "not exposed" in tool_text(blocked)["error"]
    status, _, batch = http_json(site.url, "POST", "/mcp", [{"jsonrpc": "2.0", "id": 9, "method": "ping"}, {"jsonrpc": "2.0", "method": "notifications/initialized"}])
    assert status == 200 and batch == [{"jsonrpc": "2.0", "id": 9, "result": {}}]
    status, headers, _ = http(site.url, "GET", "/mcp")
    assert status == 405 and headers["Allow"] == "POST"
    status, _, parse_error = http_json(site.url, "POST", "/mcp", "{nope", {"Content-Type": "application/json"})
    assert status == 400 and parse_error["error"]["code"] == -32700
    status, _, unknown = http_json(site.url, "POST", "/mcp/nope", {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert status == 404 and "/mcp/pharmacy" in unknown["servers"]


def test_rest_catalog_tool_calls_and_error_bodies(site):
    status, _, catalog = http_json(site.url, "GET", "/api/v1/tools")
    assert status == 200 and len(catalog["tools"]) == 34
    entry = next(tool for tool in catalog["tools"] if tool["name"] == "pharmacy.orders.create")
    assert entry["server"] == "pharmacy" and entry["hint"] == "write" and entry["description"]
    assert "delivery_option" in entry["input_schema"]["properties"] and entry["endpoints"]["call"] == "POST /api/v1/tools/pharmacy.orders.create"
    status, _, schema = http_json(site.url, "GET", "/api/v1/tools/pharmacy.orders.get")
    assert status == 200 and schema["input_schema"]["required"] == ["po_id"]
    status, _, unknown = http_json(site.url, "GET", "/api/v1/tools/nope")
    assert status == 404 and unknown["error"] == "unknown tool: nope"
    status, _, bad_json = http_json(site.url, "POST", "/api/v1/tools/pharmacy.orders.get", "{", {"Content-Type": "application/json"})
    assert status == 400 and bad_json["error"].startswith("request body must be valid JSON")
    status, _, bad_arguments = http_json(site.url, "POST", "/api/v1/tools/pharmacy.orders.get", {"nope": 1})
    assert status == 400 and "missing required properties: ['po_id']" in bad_arguments["error"]
    status, _, rejected = http_json(site.url, "POST", "/api/v1/tools/pharmacy.orders.get", {"po_id": "PO-9999"})
    assert status == 422 and rejected == {"error": "purchase order PO-9999 not found"}
    status, headers, _ = http(site.url, "PUT", "/api/v1/tools/pharmacy.orders.get", {})
    assert status == 405 and headers["Allow"] == "GET, POST"
    status, headers, _ = http(site.url, "GET", "/api/v1/pharmacy/orders/create")
    assert status == 405 and headers["Allow"] == "POST"
    status, _, read = http_json(site.url, "POST", "/api/v1/tools/pharmacy.orders.get", {"po_id": "PO-5100"})
    assert status == 200 and read["status"] == "RECEIVED"
    for path in ("/api/v1/nothing", "/api/v1/pharmacy/nothing", "/api/v1/pharmacy/orders/get/extra", "/nothing"):
        assert http(site.url, "GET", path)[0] == 404


def test_rest_resources_and_benchmark_controls(site):
    status, _, index = http_json(site.url, "GET", "/api/v1")
    assert status == 200 and [server["server"] for server in index["servers"]][-1] == "hubbench"
    status, _, orders = http_json(site.url, "GET", "/api/v1/pharmacy/orders")
    assert status == 200 and [order["po_id"] for order in orders["orders"]] == ["PO-5100"]
    status, _, order = http_json(site.url, "GET", "/api/v1/pharmacy/orders/PO-5100")
    assert status == 200 and order["status"] == "RECEIVED"
    assert http(site.url, "GET", "/api/v1/pharmacy/orders/PO-9999")[0] == 404
    status, _, lots = http_json(site.url, "GET", "/api/v1/pharmacy/lots?medication_code=IVIG-10G")
    assert status == 200 and lots["lots"] and all(lot["medication_code"] == "IVIG-10G" for lot in lots["lots"])
    status, _, messages = http_json(site.url, "GET", "/api/v1/messages/messages?q=IVIG&max_results=1")
    assert status == 200 and len(messages["messages"]) == 1  # max_results coerced to an integer
    status, _, approvals = http_json(site.url, "GET", "/api/v1/approvals/approvals")
    approval_id = approvals["approvals"][0]["approval_id"]
    status, _, approval = http_json(site.url, "GET", f"/api/v1/approvals/{approval_id}")
    assert status == 200 and approval["approval_id"] == approval_id
    assert http_json(site.url, "GET", f"/api/v1/approvals/approvals/{approval_id}")[2]["approval_id"] == approval_id
    status, _, export = http_json(site.url, "GET", "/api/v1/drive/files/export")
    assert status == 400 and "file_id" in export["error"]
    status, _, context = http_json(site.url, "GET", "/api/v1/task")
    assert status == 200 and context["task"]["task_id"] == "clinicops-004"
    assert {server["name"] for server in context["tool_servers"]} >= {"pharmacy", "hubbench"}
    assert not {"expected", "oracle_steps", "rubric_milestones", "trace"} & set(context)
    status, _, submit = http_json(site.url, "POST", "/api/v1/submit", {"decision_timing_status": "ON_TIME"})
    assert status == 400 and "missing required properties" in submit["error"]
    assert http(site.url, "GET", "/api/v1/submit")[0] == 405
    assert http(site.url, "GET", "/health")[0] == 200


def test_website_pages_and_schema_generated_forms(site):
    status, headers, raw = http(site.url, "GET", "/")
    page = raw.decode("utf-8")
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    assert html.escape(site.task["instruction"][:60]) in page and 'href="/app/pharmacy"' in page and "<script" not in page
    _, _, raw = http(site.url, "GET", "/app/pharmacy")
    page = raw.decode("utf-8")
    assert 'href="/app/pharmacy/orders"' in page and 'href="/app/pharmacy/orders/create"' in page
    _, _, raw = http(site.url, "GET", "/app/pharmacy/orders")
    assert 'href="/app/pharmacy/orders/PO-5100"' in raw.decode("utf-8")
    status, _, raw = http(site.url, "GET", "/app/messages/messages")
    assert status == 200 and "Provide <code>q</code>" in raw.decode("utf-8")
    _, _, raw = http(site.url, "GET", "/app/messages/messages?q=IVIG")
    assert "<table>" in raw.decode("utf-8")
    _, _, raw = http(site.url, "GET", "/app/pharmacy/orders/create")
    form = raw.decode("utf-8")
    assert '<form method="post" action="/app/pharmacy/orders/create">' in form
    assert 'name="quantity"' in form and 'type="number"' in form and 'name="delivery_option"' in form
    status, _, raw = http(site.url, "POST", "/app/pharmacy/orders/create", urllib.parse.urlencode(ORDER))
    result = raw.decode("utf-8")
    assert status == 200 and "PO-5101" in result and 'href="/app/pharmacy/orders/PO-5101"' in result
    status, _, raw = http(site.url, "GET", "/app/pharmacy/orders/PO-5101")
    assert status == 200 and "2026-03-12" in raw.decode("utf-8")
    assert http(site.url, "GET", "/app/pharmacy/orders/PO-9999")[0] == 404
    status, _, raw = http(site.url, "POST", "/app/pharmacy/orders/create", urllib.parse.urlencode({"supplier_id": "SUP-MERIDIAN"}))
    assert status == 400 and "missing required properties" in raw.decode("utf-8")
    _, _, raw = http(site.url, "GET", "/app/task")
    assert "hubbench.context.get" in raw.decode("utf-8")
    _, _, raw = http(site.url, "GET", "/app/submit")
    assert '<form method="post" action="/app/submit">' in raw.decode("utf-8") and 'name="decision_timing_status"' in raw.decode("utf-8")
    status, headers, _ = http(site.url, "GET", "/app/nope")
    assert status == 404 and headers["Content-Type"].startswith("text/html")
    assert http(site.url, "POST", "/app/pharmacy/orders", "")[0] == 405
    _, _, orders = http_json(site.url, "GET", "/api/v1/pharmacy/orders")
    assert [order["po_id"] for order in orders["orders"]] == ["PO-5100", "PO-5101"]  # the form write is visible over REST


# --------------------------------------------------------------------------- #
# One subprocess: the frozen CLI contract and cross-surface visibility
# --------------------------------------------------------------------------- #


def test_served_world_is_one_episode_across_every_surface(tmp_path):
    database = tmp_path / "served.db"
    command = [sys.executable, "-m", "hubbench.engine.http", "--family", "clinicops", "--task", "clinicops-004", "--db", str(database), "--fresh", "--host", "127.0.0.1", "--port", "0"]
    process = subprocess.Popen(command, cwd=BENCHMARK_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        announce = json.loads(process.stdout.readline())
        base = announce["url"]
        assert announce["task_id"] == "clinicops-004" and "/mcp/pharmacy" in announce["mcp"]

        # MCP over HTTP: initialize → tools/list per server → tools/call read + write.
        _, _, init = rpc(base, "/mcp/pharmacy", "initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}})
        assert init["result"]["serverInfo"]["name"] == "hubbench-clinicops-pharmacy"
        assert http(base, "POST", "/mcp/pharmacy", {"jsonrpc": "2.0", "method": "notifications/initialized"})[0] == 202
        _, _, listing = rpc(base, "/mcp/pharmacy", "tools/list")
        assert all(tool["name"].startswith("pharmacy.") for tool in listing["result"]["tools"])
        _, _, notes = rpc(base, "/mcp/notes", "tools/list")
        assert [tool["name"] for tool in notes["result"]["tools"]] == ["notes.drafts.create"]
        _, _, read = rpc(base, "/mcp/pharmacy", "tools/call", {"name": "pharmacy.orders.list", "arguments": {}})
        assert [order["po_id"] for order in tool_text(read)["orders"]] == ["PO-5100"]
        _, _, draft = rpc(base, "/mcp/notes", "tools/call", {"name": "notes.drafts.create", "arguments": {"recipient": "care coordinator", "subject": "IVIG", "body": "draft"}})
        assert draft["result"]["isError"] is False and tool_text(draft)["draft_id"] == "DRAFT-1"

        # REST: catalog, a write, a resource read.
        status, _, catalog = http_json(base, "GET", "/api/v1/tools")
        assert status == 200 and len(catalog["tools"]) == 34
        status, _, created = http_json(base, "POST", "/api/v1/tools/pharmacy.orders.create", ORDER)
        assert status == 200 and created["po_id"] == "PO-5101"
        status, _, order = http_json(base, "GET", "/api/v1/pharmacy/orders/PO-5101")
        assert status == 200 and order["expected_delivery_date"] == "2026-03-12"

        # Website: brief, a listing, a form GET + POST.
        status, _, raw = http(base, "GET", "/")
        assert status == 200 and 'href="/app/pharmacy"' in raw.decode("utf-8")
        _, _, raw = http(base, "GET", "/app/pharmacy/orders")
        assert 'href="/app/pharmacy/orders/PO-5101"' in raw.decode("utf-8")
        _, _, raw = http(base, "GET", "/app/notes/drafts/create")
        assert '<form method="post" action="/app/notes/drafts/create">' in raw.decode("utf-8")
        status, _, raw = http(base, "POST", "/app/notes/drafts/create", urllib.parse.urlencode({"recipient": "family", "subject": "date", "body": "draft"}))
        assert status == 200 and "DRAFT-2" in raw.decode("utf-8")

        # Terminal CLI against the served world (no local SQLite file involved).
        tool = str(HUBBENCH_ROOT / "bin" / "tool")
        remote = {**os.environ, "HUBBENCH_URL": base}
        remote.pop("HUBBENCH_DB", None)

        def run(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, tool, *args], capture_output=True, text=True, env=env, cwd=tmp_path, timeout=120)

        listing = run("list", env=remote)
        assert listing.returncode == 0 and "pharmacy.orders.create\twrite" in listing.stdout
        schema = run("schema", "pharmacy.orders.create", env=remote)
        assert schema.returncode == 0 and "delivery_option" in schema.stdout
        read = run("pharmacy.orders.get", json.dumps({"po_id": "PO-5101"}), env=remote)
        assert read.returncode == 0 and json.loads(read.stdout)["expected_delivery_date"] == "2026-03-12"
        assert run("pharmacy.orders.get", json.dumps({"po_id": "PO-9999"}), env=remote).returncode == 1
        assert run("nope", "{}", env=remote).returncode != 0
        assert run("trace", env=remote).returncode != 0

        # MCP over stdio against the same --db sees the HTTP writes ...
        stdio = subprocess.run(
            [sys.executable, "-m", "hubbench.engine.server", "--family", "clinicops", "--task", "clinicops-004", "--db", str(database)],
            input=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "pharmacy.orders.get", "arguments": {"po_id": "PO-5101"}}}) + "\n",
            capture_output=True, text=True, cwd=BENCHMARK_ROOT, timeout=120,
        )
        assert stdio.returncode == 0, stdio.stderr
        assert tool_text(json.loads(stdio.stdout.splitlines()[0]))["status"] == "SUBMITTED"
        # ... and the served world keeps recording after another process extended the trace.
        status, _, later = http_json(base, "POST", "/api/v1/tools/notes.drafts.create", {"recipient": "pharmacy director", "subject": "escalation", "body": "draft"})
        assert status == 200 and later["draft_id"] == "DRAFT-3"

        local = {**os.environ, "HUBBENCH_FAMILY": "clinicops", "HUBBENCH_TASK": "clinicops-004", "HUBBENCH_DB": str(database)}
        local.pop("HUBBENCH_URL", None)
        trace = json.loads(run("trace", env=local).stdout)
        tools = [entry["tool"] for entry in trace]
        assert [entry["index"] for entry in trace] == list(range(len(trace)))
        assert tools.count("notes.drafts.create") == 3 and tools.count("pharmacy.orders.create") == 1
        assert tools.count("pharmacy.orders.get") == 4  # REST item, CLI ×2, stdio
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    assert process.returncode == 0, process.stderr.read()
