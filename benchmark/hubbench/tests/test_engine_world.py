"""World mechanics: seeding, stateful writes, containment, transient faults."""

from __future__ import annotations

import copy

from hubbench.engine.world import World


def test_world_builds_and_seeds_every_task(family, released_tasks, tmp_path):
    for task in released_tasks:
        with World.fresh(family, task, tmp_path / f"{task['task_id']}.db") as world:
            tables = {row["name"] for row in world.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for expected in ("patients", "inventory_lots", "slots", "appointments", "mutations", "answers", "call_trace"):
                assert expected in tables
            assert world.connection.execute("SELECT COUNT(*) FROM slots").fetchone()[0] > 0
            assert world.connection.execute("PRAGMA foreign_key_check").fetchall() == []
            context = world.call_tool("hubbench.context.get", {})
            assert context["reference_records"]["case_reference"] == f"CLIN-{task['task_id'].rsplit('-', 1)[1].zfill(4)}"
            assert len(context["evidence_index"]) == len(task["assets"])


def test_writes_persist_and_readbacks_reflect_them(family, released_tasks, tmp_path):
    task = released_tasks[0]  # clinicops-001: appointment create
    with World.fresh(family, task, tmp_path / "write.db") as world:
        create = next(step for step in task["oracle_steps"] if step["phase"] == "primary_mutation")
        result = world.call_tool(create["tool"], create["arguments"])
        assert result.get("error") is None and result["id"] == "APPT-24601"
        readback = world.call_tool("scheduling.appointments.get", {"appointment_id": "APPT-24601"})
        assert readback["status"] == "booked" and readback["chair"] == "CHAIR-2"
        slot = world.one("SELECT status, appointment_id FROM slots WHERE slot_id = 'SLOT-2-20260319-PM'")
        assert slot == {"status": "busy", "appointment_id": "APPT-24601"}
        mutation = world.one("SELECT mutation_id, table_name FROM mutations WHERE task_id = ?", (task["task_id"],))
        assert mutation == {"mutation_id": f"{task['task_id']}-mutation-01", "table_name": "appointments"}


def test_protected_sessions_reject_displacement(family, released_tasks, tmp_path):
    task = released_tasks[0]
    with World.fresh(family, task, tmp_path / "protected.db") as world:
        result = world.call_tool(task["negative_controls"]["unauthorized_write"]["tool"], task["negative_controls"]["unauthorized_write"]["arguments"])
        assert "error" in result and "protected" in result["error"]


def test_unknown_tool_and_bad_arguments_fail_closed(family, released_tasks, tmp_path):
    task = released_tasks[0]
    with World.fresh(family, task, tmp_path / "bad.db") as world:
        assert "error" in world.call_tool("ehr.patients.destroy", {})
        assert "error" in world.call_tool("ehr.patients.get", {"identifier": "nope"})
        assert "error" in world.call_tool("pharmacy.orders.create", {"supplier_id": "SUP-MERIDIAN", "confirmation_id": "CONF-MER-55120", "medication_code": "PEMBRO-100", "quantity": 0, "delivery_option": "standard"})


def test_transient_faults_are_deterministic_and_retryable(family, released_tasks, tmp_path):
    task = copy.deepcopy(released_tasks[0])
    task["transient_faults"] = [{"tool": "pharmacy.lots.list", "error": "upstream inventory service unavailable (503)", "failures": 1}]
    with World.fresh(family, task, tmp_path / "fault.db") as world:
        first = world.call_tool("pharmacy.lots.list", {"medication_code": "INFLIX-100"})
        assert first == {"error": "upstream inventory service unavailable (503)", "retryable": True}
        second = world.call_tool("pharmacy.lots.list", {"medication_code": "INFLIX-100"})
        assert "lots" in second
