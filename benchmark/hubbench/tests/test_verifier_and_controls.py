"""Oracle replay, negative controls, and the sealed verifier."""

from __future__ import annotations

from hubbench.engine.evaluation import run_episode
from hubbench.engine.verifier import verify_episode
from hubbench.engine.world import World


def test_oracle_passes_every_released_task(family, released_tasks, tmp_path):
    for task in released_tasks:
        episode = run_episode(family, task, "oracle", tmp_path / f"oracle-{task['task_id']}.db")
        assert episode["strict_pass"], {check["id"]: check["evidence"] for check in episode["checks"] if not check["passed"]}
        assert episode["score"] == 100.0


def test_wrong_value_control_is_rejected(family, released_tasks, tmp_path):
    task = released_tasks[0]
    episode = run_episode(family, task, "wrong_value", tmp_path / "wrong-value.db")
    assert not episode["strict_pass"] and episode["score"] < 100.0
    failed = {check["id"] for check in episode["checks"] if not check["passed"]}
    assert "analysis.inputs" in failed or "answer.insights" in failed


def test_unauthorized_write_control_is_rejected(family, released_tasks, tmp_path):
    for task in (released_tasks[0], released_tasks[1]):
        episode = run_episode(family, task, "unauthorized_write", tmp_path / f"unauth-{task['task_id']}.db")
        assert not episode["strict_pass"], task["task_id"]


def test_noop_scores_near_zero(family, released_tasks, tmp_path):
    episode = run_episode(family, released_tasks[3], "noop", tmp_path / "noop.db")
    assert episode["score"] < 10.0


def test_verifier_never_reachable_through_tools(family, released_tasks, tmp_path):
    task = released_tasks[0]
    with World.fresh(family, task, tmp_path / "sealed.db") as world:
        names = {tool["name"] for tool in world.tool_definitions()}
        assert not any("verify" in name or "expected" in name or "contract" in name for name in names)
        result = world.call_tool("hubbench.context.get", {})
        rendered = str(result)
        assert "expected" not in rendered and "oracle_steps" not in rendered
        verification = verify_episode(task, world)
        assert verification["strict_pass"] is False  # nothing done yet
