"""World service for distributed HubBench task packages.

Thin wrapper around ``hubbench.engine.http`` (the public agent surfaces: MCP over
streamable HTTP, the REST API, and the web console) that adds ONE private,
token-gated, read-only channel for the verifier::

    python3 -m hubbench.engine.world_service --family clinicops --task /opt/hubbench/task.json \
        --db /var/lib/hubbench/world.db --fresh --host 0.0.0.0 --port 8765 --private-port 8766

The public server is started exactly as ``hubbench.engine.http`` would start it
(every unknown option is passed through).  The private listener answers

    GET /health                   -> {"status": "ok"}            (no token)
    GET /verifier/world.db        -> the finished SQLite world     (token required)
    GET /verifier/trace           -> {"task_id", "trace": [...]}  (token required)

where the token travels in the ``X-HubBench-Verifier-Token`` header and only its
SHA-256 (``--token-sha256`` / ``HUBBENCH_VERIFIER_TOKEN_SHA256``) exists inside the
world container.  The raw token ships only with the task's ``tests/`` tree, which
Harbor mounts for the root verifier after the agent has finished; the agent user
never holds it.  The channel never mutates state and never exposes the sealed
verifier contract: the expected answer does not exist in this container at all.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import inspect
import json
import os
import sqlite3
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

TOKEN_HEADER = "X-HubBench-Verifier-Token"
DEFAULT_PRIVATE_PORT = 8766
_SNAPSHOT_ATTEMPTS = 20


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def snapshot_database(path: Path) -> bytes:
    """Serialize a consistent, read-only copy of the world database."""

    last_error: Exception | None = None
    for attempt in range(_SNAPSHOT_ATTEMPTS):
        try:
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
            try:
                return connection.serialize()
            finally:
                connection.close()
        except sqlite3.OperationalError as exc:  # locked by an in-flight write; retry
            last_error = exc
            time.sleep(0.05 * (attempt + 1))
    raise RuntimeError(f"could not snapshot {path}: {last_error}")


def snapshot_trace(path: Path) -> list[dict[str, Any]]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
    try:
        rows = connection.execute(
            "SELECT trace_index, tool, arguments_json, success, result_json FROM call_trace ORDER BY trace_index"
        ).fetchall()
    finally:
        connection.close()
    return [
        {"index": row[0], "tool": row[1], "arguments": json.loads(row[2]), "success": bool(row[3]), "result": json.loads(row[4])}
        for row in rows
    ]


class PrivateChannel(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    database: Path
    token_sha256: str
    task_id: str


class PrivateHandler(BaseHTTPRequestHandler):
    server: PrivateChannel
    server_version = "HubBenchVerifierChannel/1.0"

    def log_message(self, *_: Any) -> None:  # quiet by design
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: Any) -> None:
        self._send(status, json.dumps(payload, sort_keys=True).encode("utf-8"), "application/json")

    def _authorized(self) -> bool:
        presented = self.headers.get(TOKEN_HEADER, "")
        if not presented or not self.server.token_sha256:
            return False
        return hmac.compare_digest(token_digest(presented), self.server.token_sha256)

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/health":
            self._json(HTTPStatus.OK, {"status": "ok", "task_id": self.server.task_id, "channel": "verifier"})
            return
        if path not in {"/verifier/world.db", "/verifier/trace"}:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        if not self._authorized():
            self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
            return
        try:
            if path == "/verifier/world.db":
                self._send(HTTPStatus.OK, snapshot_database(self.server.database), "application/vnd.sqlite3")
            else:
                self._json(HTTPStatus.OK, {"task_id": self.server.task_id, "trace": snapshot_trace(self.server.database)})
        except (RuntimeError, sqlite3.Error) as exc:
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802  (read-only channel)
        self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "read_only"})

    do_PUT = do_DELETE = do_PATCH = do_POST


def start_private_channel(*, host: str, port: int, database: Path, token_sha256: str, task_id: str) -> PrivateChannel:
    server = PrivateChannel((host, port), PrivateHandler)
    server.database = database
    server.token_sha256 = token_sha256
    server.task_id = task_id
    thread = threading.Thread(target=server.serve_forever, name="hubbench-verifier-channel", daemon=True)
    thread.start()
    return server


def _task_id(reference: str) -> str:
    path = Path(reference)
    if path.is_file():
        try:
            return str(json.loads(path.read_text(encoding="utf-8")).get("task_id", path.stem))
        except (OSError, json.JSONDecodeError):
            return path.stem
    return reference


def _run_public_surface(argv: list[str]) -> None:
    from . import http as public_http  # B's module: MCP streamable HTTP + REST + website

    main = getattr(public_http, "main")
    try:
        accepts_argv = bool(inspect.signature(main).parameters)
    except (TypeError, ValueError):
        accepts_argv = False
    if accepts_argv:
        main(argv)
    else:
        sys.argv = ["hubbench.engine.http", *argv]
        main()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Serve one distributed HubBench world plus the root-only verifier channel")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--task", required=True, help="task id or task JSON path")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--private-host", default=None, help="verifier channel bind host (default: --host)")
    parser.add_argument("--private-port", type=int, default=int(os.environ.get("HUBBENCH_PRIVATE_PORT", DEFAULT_PRIVATE_PORT)))
    parser.add_argument("--token-sha256", default=os.environ.get("HUBBENCH_VERIFIER_TOKEN_SHA256", ""))
    args, passthrough = parser.parse_known_args(argv)
    if not args.token_sha256:
        raise SystemExit("a verifier token digest is required (--token-sha256 or HUBBENCH_VERIFIER_TOKEN_SHA256)")
    os.umask(0o077)
    args.db.parent.mkdir(parents=True, exist_ok=True)
    channel = start_private_channel(
        host=args.private_host or args.host,
        port=args.private_port,
        database=args.db,
        token_sha256=args.token_sha256.strip().lower(),
        task_id=_task_id(args.task),
    )
    try:
        _run_public_surface([*passthrough, "--task", args.task, "--db", str(args.db), "--host", args.host])
    finally:
        channel.shutdown()
        channel.server_close()


if __name__ == "__main__":
    main()
