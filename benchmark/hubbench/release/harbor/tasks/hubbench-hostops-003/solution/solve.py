#!/usr/bin/env python3
"""HubBench oracle: replay the reference policy THROUGH the public surfaces.

Context and investigation reads go over MCP streamable HTTP (one endpoint per
server), the primary state change and its readback over the REST API, the
stakeholder draft through the `tool` CLI, and the structured answer through
POST /api/v1/submit, so a reward of 1.0 proves every surface end to end — not
just the world.  Set HUBBENCH_SOLVE_SURFACE=mcp|rest|cli to force one surface.
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = os.environ.get("HUBBENCH_URL", "http://world:8765").rstrip("/")
TOOL = os.environ.get("HUBBENCH_TOOL", "tool")
SURFACE = os.environ.get("HUBBENCH_SOLVE_SURFACE", "mixed")
ROUTES = {
    "context": "mcp",
    "investigation": "mcp",
    "primary_mutation": "rest",
    "collaboration": "cli",
    "post_write_verification": "rest",
    "answer": "submit",
}
PROTOCOL_VERSION = "2025-03-26"


def request(method: str, path: str, payload=None, headers=None, timeout: float = 60.0):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    base_headers = {"Accept": "application/json, text/event-stream"}
    if data is not None:
        base_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={**base_headers, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, response.headers, response.read().decode("utf-8")


def wait_ready(attempts: int = 120) -> dict:
    last = None
    for attempt in range(attempts):
        try:
            _, _, body = request("GET", "/api/v1/task")
            return json.loads(body)
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(min(2.0, 0.25 * (attempt + 1)))
    raise SystemExit(f"world not reachable at {BASE}: {last}")


def parse_message(body: str, content_type: str, request_id):
    if "text/event-stream" in content_type:
        messages = [json.loads(line[5:].strip()) for line in body.splitlines() if line.startswith("data:") and line[5:].strip()]
        for message in messages:
            if isinstance(message, dict) and message.get("id") == request_id:
                return message
        return messages[-1] if messages else None
    return json.loads(body) if body.strip() else None


class Mcp:
    def __init__(self) -> None:
        self.sessions: dict[str, str | None] = {}
        self.counter = 0

    def send(self, server: str, method: str, params=None, *, notification: bool = False):
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notification:
            self.counter += 1
            payload["id"] = self.counter
        headers = {}
        if self.sessions.get(server):
            headers["Mcp-Session-Id"] = self.sessions[server]
        status, response_headers, body = request("POST", f"/mcp/{server}", payload, headers)
        session = response_headers.get("Mcp-Session-Id")
        if session:
            self.sessions[server] = session
        if notification:
            return None
        return parse_message(body, response_headers.get("Content-Type", ""), payload["id"])

    def initialize(self, server: str) -> None:
        if server in self.sessions:
            return
        self.sessions[server] = None
        self.send(server, "initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": "hubbench-oracle", "version": "1.0.0"}})
        self.send(server, "notifications/initialized", notification=True)

    def call(self, name: str, arguments: dict) -> dict:
        server = name.split(".", 1)[0]
        self.initialize(server)
        message = self.send(server, "tools/call", {"name": name, "arguments": arguments})
        if message is None or "error" in message:
            raise SystemExit(f"MCP tools/call failed for {name}: {message}")
        result = message["result"]
        content = result.get("content") or []
        text = next((item.get("text") for item in content if item.get("type") == "text"), None)
        return json.loads(text) if text is not None else result.get("structuredContent", {})


def rest_call(name: str, arguments: dict) -> dict:
    try:
        _, _, body = request("POST", f"/api/v1/tools/{name}", arguments)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
    payload = json.loads(body) if body.strip() else {}
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict) and "tool" in payload:
        return payload["result"]
    return payload


def rest_submit(fields: dict) -> dict:
    try:
        _, _, body = request("POST", "/api/v1/submit", fields)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
    payload = json.loads(body) if body.strip() else {}
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict) and "tool" in payload:
        return payload["result"]
    return payload


def cli_call(name: str, arguments: dict) -> dict:
    env = {**os.environ, "HUBBENCH_URL": BASE}
    completed = subprocess.run([TOOL, name, json.dumps(arguments)], capture_output=True, text=True, env=env, timeout=120)
    if completed.returncode not in (0, 1) or not completed.stdout.strip():
        raise SystemExit(f"tool CLI failed for {name}: rc={completed.returncode} {completed.stderr.strip()}")
    return json.loads(completed.stdout)


def main() -> int:
    oracle = json.loads((HERE / "oracle.json").read_text(encoding="utf-8"))
    task = wait_ready()
    served = task.get("task_id") or (task.get("task") or {}).get("task_id")
    if served and served != oracle["task_id"]:
        raise SystemExit(f"world serves {served}, oracle is for {oracle['task_id']}")
    _, _, listing = request("GET", "/api/v1/tools")
    if oracle["submit_tool"] not in listing:
        raise SystemExit("REST tool listing does not expose the answer control")
    _, headers, page = request("GET", "/")
    if "html" not in (headers.get("Content-Type", "") + page[:200]).lower():
        raise SystemExit("web console did not answer with HTML")
    mcp = Mcp()
    outcomes = []
    for index, step in enumerate(oracle["steps"], start=1):
        surface = ROUTES.get(step["phase"], "mcp") if SURFACE == "mixed" else SURFACE
        if step["tool"] == oracle["submit_tool"] and surface in ("submit", "rest"):
            result = rest_submit(step["arguments"])
        elif surface == "submit":
            result = rest_call(step["tool"], step["arguments"])
        elif surface == "rest":
            result = rest_call(step["tool"], step["arguments"])
        elif surface == "cli":
            result = cli_call(step["tool"], step["arguments"])
        else:
            result = mcp.call(step["tool"], step["arguments"])
        outcomes.append({"index": index, "tool": step["tool"], "surface": surface, "error": result.get("error") if isinstance(result, dict) else None})
    errors = [outcome for outcome in outcomes if outcome["error"]]
    print(json.dumps({"task_id": oracle["task_id"], "steps": len(outcomes), "surfaces": sorted({o["surface"] for o in outcomes}), "tool_errors": errors}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
