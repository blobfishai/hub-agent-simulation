#!/usr/bin/env python3
"""HubBench verifier: pull the finished world over the root-only channel and grade it (HubScore).

Runs as root after the episode.  The raw channel token ships only with this
tests/ tree; the world container holds its SHA-256 alone.  Reward = score / 100.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from hubbench.engine.families import load_family  # noqa: E402
from hubbench.engine.verifier import verify_episode  # noqa: E402
from hubbench.engine.world import World  # noqa: E402

TOKEN_HEADER = "X-HubBench-Verifier-Token"


def fetch(url: str, token: str, attempts: int = 30) -> bytes:
    request = urllib.request.Request(url, headers={TOKEN_HEADER: token})
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403, 404, 405):
                raise SystemExit(f"verifier channel refused {url}: HTTP {exc.code}") from exc
            last = exc
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
            last = exc
        time.sleep(min(2.0, 0.25 * (attempt + 1)))
    raise SystemExit(f"verifier channel unreachable at {url}: {last}")


def main() -> int:
    task = json.loads((HERE / "task.json").read_text(encoding="utf-8"))
    token = (HERE / "verifier-token").read_text(encoding="utf-8").strip()
    base = os.environ.get("HUBBENCH_VERIFIER_URL", "http://world:8766").rstrip("/")
    logs = Path(os.environ.get("HUBBENCH_LOGS_DIR", "/logs/verifier"))
    logs.mkdir(parents=True, exist_ok=True)
    database = logs / "world.db"
    database.write_bytes(fetch(f"{base}/verifier/world.db", token))
    family = load_family(task["family"])
    with World(family, task, database) as world:
        verdict = verify_episode(task, world)
        trace = world.trace
    reward = round(verdict["score"] / 100.0, 6)
    (logs / "reward.txt").write_text(f"{reward:.6f}\n", encoding="utf-8")
    (logs / "verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (logs / "trace.json").write_text(json.dumps({"task_id": task["task_id"], "trace": trace}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"task_id": task["task_id"], "metric": verdict["metric"], "score": verdict["score"], "strict_pass": verdict["strict_pass"], "reward": reward}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
