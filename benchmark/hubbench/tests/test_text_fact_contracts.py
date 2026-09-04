"""Alternate prose is accepted without erasing business or evidence controls."""

from __future__ import annotations

import copy
import importlib
import json

import pytest

from hubbench.engine.families import load_family
from hubbench.engine.grading_contracts import (
    AUDITED_PROSE_FIELDS,
    TEXT_CONTRACT_POLICY,
    apply_fact_text_contract,
)
from hubbench.engine.verifier import (
    missing_required_investigations,
    payload_assertion_mismatches,
    verify_episode,
)
from hubbench.engine.world import World
from hubbench.engine.catalog import sealed_contract
from chain_adapters.factorybench_100 import measure_factorybench_task

FAMILIES = (
    "clinicops", "datadesk", "designops", "deskops", "hostops", "itsmdesk",
    "policydesk", "repodesk", "researchdesk", "scilab", "secops", "webstudio", "workplace",
)
TASK_IDS = tuple(f"{slug}-{ordinal:03d}" for slug in FAMILIES for ordinal in range(1, 9))


@pytest.fixture(scope="module")
def tasks():
    return {
        task["task_id"]: task
        for slug in FAMILIES
        for task in load_family(slug).build_tasks()
    }


def _assertion(task, assertion_id):
    return next(item for item in task["expected"]["assertions"] if item["id"] == assertion_id)


def _row(tool, arguments):
    return {"payload_json": json.dumps({"tool": tool, "arguments": arguments})}


def _replay(task, db_path, edit=None, omit_phase=None):
    family = load_family(task["family"])
    with World.fresh(family, task, db_path) as world:
        for step in copy.deepcopy(task["oracle_steps"]):
            if step["phase"] == omit_phase:
                continue
            if edit:
                edit(step)
            world.call_tool(step["tool"], step["arguments"])
        return verify_episode(task, world)


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_different_sentences_and_human_handoff_pass(tasks, task_id, tmp_path):
    task = tasks[task_id]
    primary = _assertion(task, "mutation_01")
    selected = task["expected"]["answer"]["recommended_option"]

    def edit(step):
        if step["phase"] == "primary_mutation":
            for field, facts in primary.get("payload_argument_text", {}).items():
                step["arguments"][field] = "Documented for the approved work. " + "; ".join(reversed(facts))
        if step["phase"] == "collaboration":
            for field in ("subject", "body"):
                step["arguments"][field] = step["arguments"][field].replace(selected, "the approved route")
            assert selected not in json.dumps(step["arguments"])

    verdict = _replay(task, tmp_path / f"{task_id}.db", edit)
    assert verdict["strict_pass"], [check for check in verdict["checks"] if not check["passed"]]
    assert verdict["score"] == 100.0


@pytest.mark.parametrize("slug", FAMILIES)
def test_policy_preserves_business_checks_and_does_not_mutate_builder_inputs(slug):
    module = importlib.import_module(f"hubbench.families.{slug}.build")
    for scenario in module.scenarios():
        original = module.build_task.__wrapped__(scenario)
        before = copy.deepcopy(original)
        revised = apply_fact_text_contract(original)
        assert original == before
        assert revised["evaluation"]["text_contract_policy"] == TEXT_CONTRACT_POLICY
        assert revised["benchmark_version"] == "1.0.1"
        for key in original.keys() - {"expected", "rubric_milestones", "world", "evaluation"}:
            assert revised[key] == original[key], key
        for key in original["expected"].keys() - {"assertions"}:
            assert revised["expected"][key] == original["expected"][key], key
        for old, new in zip(original["expected"]["assertions"], revised["expected"]["assertions"], strict=True):
            if old["id"] not in {"mutation_01", "mutation_02"}:
                assert old == new
            for key in ("values", "where", "weight", "payload_allowed_argument_paths", "payload_text_any_of"):
                assert old.get(key) == new.get(key), (old["id"], key)
        for old, new in zip(original["rubric_milestones"], revised["rubric_milestones"], strict=True):
            assert {k: v for k, v in old.items() if k != "description"} == {
                k: v for k, v in new.items() if k != "description"
            }


@pytest.mark.parametrize("task_id", sorted(AUDITED_PROSE_FIELDS))
def test_every_remaining_structured_argument_stays_exact(tasks, task_id):
    task = tasks[task_id]
    assertion = _assertion(task, "mutation_01")
    step = next(step for step in task["oracle_steps"] if step["phase"] == "primary_mutation")
    assert not payload_assertion_mismatches(_row(step["tool"], step["arguments"]), assertion)
    for field, value in assertion["payload_contains"]["arguments"].items():
        changed = copy.deepcopy(step["arguments"])
        changed[field] = value + 1 if isinstance(value, (int, float)) else f"{value}-WRONG"
        mismatches = payload_assertion_mismatches(_row(step["tool"], changed), assertion)
        assert "payload_mismatches" in mismatches, (task_id, field)


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_subject_or_related_fields_cannot_replace_body_facts(tasks, task_id):
    task = tasks[task_id]
    assertion = _assertion(task, "mutation_02")
    step = next(step for step in task["oracle_steps"] if step["phase"] == "collaboration")
    arguments = copy.deepcopy(step["arguments"])
    arguments["subject"] += " " + arguments["body"]
    arguments["body"] = "The requested work is complete."
    mismatches = payload_assertion_mismatches(_row(step["tool"], arguments), assertion)
    assert "body" in mismatches["argument_text_mismatches"]


@pytest.mark.parametrize("task_id", ("researchdesk-003", "researchdesk-007"))
def test_review_purpose_requires_both_current_definition_and_source_set(tasks, task_id):
    task = tasks[task_id]
    assertion = _assertion(task, "mutation_01")
    step = next(step for step in task["oracle_steps"] if step["phase"] == "primary_mutation")
    definition, source_set = assertion["payload_argument_text"]["purpose"]
    for purpose in ("Review requested", definition, source_set, f"{definition} {source_set}0"):
        arguments = {**step["arguments"], "purpose": purpose}
        mismatches = payload_assertion_mismatches(_row(step["tool"], arguments), assertion)
        assert "purpose" in mismatches["argument_text_mismatches"]


@pytest.mark.parametrize("task_id", (
    "datadesk-001", "datadesk-004", "datadesk-007", "deskops-002", "deskops-008",
    "designops-001", "policydesk-004", "policydesk-005",
    "researchdesk-002", "researchdesk-005", "researchdesk-008", "deskops-001", "deskops-006",
))
def test_unaudited_narratives_and_venue_labels_keep_exact_contract(tasks, task_id):
    task = tasks[task_id]
    assertion = _assertion(task, "mutation_01")
    step = next(step for step in task["oracle_steps"] if step["phase"] == "primary_mutation")
    assert assertion["payload_contains"]["arguments"] == step["arguments"]
    assert "payload_argument_text" not in assertion


@pytest.mark.parametrize("field,value", (
    ("recipient", "wrong-owner@example.test"),
    ("body", "Complete, without the record or outcome date."),
))
def test_invalid_handoff_still_fails_end_to_end(tasks, tmp_path, field, value):
    def edit(step):
        if step["phase"] == "collaboration":
            step["arguments"][field] = value

    verdict = _replay(tasks["datadesk-005"], tmp_path / f"bad-{field}.db", edit)
    assert not verdict["strict_pass"]
    assert any(check["id"] == "state.collaboration" and not check["passed"] for check in verdict["checks"])


@pytest.mark.parametrize("phase", ("investigation", "verification", "collaboration"))
def test_omitted_work_does_not_become_a_pass(tasks, tmp_path, phase):
    task = tasks["datadesk-005"]
    if phase == "verification":
        phase = next(step["phase"] for step in task["oracle_steps"] if step["tool"] == "pipelines.backfills.get")
    verdict = _replay(task, tmp_path / f"omitted-{phase}.db", omit_phase=phase)
    assert not verdict["strict_pass"]


def test_wrong_end_time_still_fails(tasks, tmp_path):
    def edit(step):
        if step["phase"] == "primary_mutation":
            step["arguments"]["end_time"] = "2026-03-11T16:30:00"

    verdict = _replay(tasks["datadesk-005"], tmp_path / "wrong-end.db", edit)
    assert not verdict["strict_pass"]


def test_direct_evidence_reads_are_explicitly_not_credited(tasks, tmp_path):
    task = tasks["datadesk-005"]
    with World.fresh(load_family("datadesk"), task, tmp_path / "evidence.db") as world:
        assert missing_required_investigations(task, world.trace) == task["required_investigations"]
        context = world.call_tool("hubbench.context.get", {})
        requirement = context["organization"]["interaction_contract"]["investigation_evidence"]
        assert "filesystem reads are not recorded" in requirement
        missing = missing_required_investigations(task, world.trace)
        assert len(missing) == len(task["required_investigations"]) - 1
        assert all(item["id"] != "investigation_01" for item in missing)


@pytest.mark.parametrize("value", (None, "", " \t\n", 42, [], {}))
def test_prose_must_be_a_nonempty_string(value):
    row = _row("example.write", {"description": value})
    assert payload_assertion_mismatches(row, {"payload_argument_text": {"description": []}})


@pytest.mark.parametrize("body,passed", (
    ("BF-7101 completes 2026-03-11.", True),
    ("bf 7101 completes 2026/03/11!", True),
    ("BF-71010 completes 2026-03-11.", False),
    ("BF-7101 completes 2026-03-111.", False),
    ("BF-7101 completes 2026-03-12.", False),
))
def test_fact_matching_uses_token_boundaries(body, passed):
    mismatches = payload_assertion_mismatches(
        _row("notes.drafts.create", {"body": body}),
        {"payload_argument_text": {"body": ["BF-7101", "2026-03-11"]}},
    )
    assert bool(mismatches) is not passed


@pytest.mark.parametrize("contract", (None, [], {"body": "reference"}, {"body": [""]}, {"body": ["---"]}))
def test_malformed_text_contract_fails_closed(contract):
    assert payload_assertion_mismatches(
        _row("notes.drafts.create", {"body": "Any content"}),
        {"payload_argument_text": contract},
    )


def test_legacy_contracts_keep_literal_semantics():
    assertion = {"payload_contains": {"arguments": {"description": "Original exact sentence"}}}
    assert not payload_assertion_mismatches(_row("tool.write", {"description": "Original exact sentence"}), assertion)
    assert payload_assertion_mismatches(_row("tool.write", {"description": "Different valid wording"}), assertion)


def test_chain_audit_recognizes_body_facts_without_counting_unrelated_fields(tasks):
    task = tasks["datadesk-005"]
    contract = sealed_contract(task)
    assert measure_factorybench_task(task, contract)["hops"]["H12"]
    contract = copy.deepcopy(contract)
    draft = next(item for item in contract["assertions"] if item["id"] == "mutation_02")
    draft["payload_argument_text"] = {"subject": draft["payload_argument_text"]["body"]}
    assert not measure_factorybench_task(task, contract)["hops"]["H12"]
    draft["payload_text_contains"] = [task["expected"]["answer"]["recommended_outcome_date"]]
    assert measure_factorybench_task(task, contract)["hops"]["H12"]
