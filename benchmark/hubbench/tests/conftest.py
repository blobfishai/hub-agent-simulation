"""Test fixtures: put ``benchmark/`` on sys.path so ``hubbench`` imports."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BENCHMARK_ROOT = Path(__file__).resolve().parents[2]
if str(BENCHMARK_ROOT) not in sys.path:
    sys.path.insert(0, str(BENCHMARK_ROOT))

from hubbench.engine.families import load_family  # noqa: E402
from hubbench.engine.tasks import load_release_contract, load_release_tasks  # noqa: E402


@pytest.fixture(scope="session")
def family():
    return load_family("clinicops")


@pytest.fixture(scope="session")
def released_tasks(family):
    tasks = load_release_tasks(family)
    assert len(tasks) == 8, "the committed clinicops release must hold 8 tasks"
    return tasks


@pytest.fixture(scope="session")
def released_contracts(family, released_tasks):
    return {task["task_id"]: load_release_contract(family, task["task_id"]) for task in released_tasks}
