"""Assemble RepoDesk tasks: seed tables, scattered evidence, decision model, sealed contract.

Every declared number in a scenario is recomputed from the seeded world
(impact analyses, commit-touched modules, gated modules, the evidence
register, the lane calendar, change records, commits on the release branch,
partner confirmations, customer commitments) and the build fails on any
disagreement, so the answer contract can never drift from the data the agent
actually sees.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from ...engine.assets import CSV, EML, JSON, MARKDOWN, PDF, XLSX, YAML, asset, eml, yaml_lines
from ...engine.catalog import answer_checks, build_rubric_milestones, milestone_descriptions, sequence_signature
from ...engine.decision import DecisionInputs, answer_schema, build_decision_model
from ...engine.families import CONTEXT_TOOL, SUBMIT_TOOL
from ...engine.grading_contracts import fact_text_contract
from ...engine.quality_assets import quality_support_assets, quality_support_investigations, scoped_csv, scoped_markdown
from . import tools as repo_tools
from .policy import SUPERSEDED_PLAYBOOK, effective_playbook
from .scenarios import scenarios
from .specs import (
    AS_OF,
    ENGINEERS,
    ENVIRONMENTS,
    ORGANIZATION,
    PARTNERS,
    REPOSITORIES,
    RESULT_SOURCES,
    USERS,
    WINDOW_HOURS,
    WINDOW_TIMES,
    Change,
    Component,
    Issue,
    Result,
    Scenario,
    affected_modules,
    business_days,
    components_by_id,
    issue_runs,
    next_business_day,
    window_id,
)

BENCHMARK = "HubBench"
FAMILY_SLUG = "repodesk"
FAMILY_VERSION = "1.0.1"
PRIMARY_KEYS = {
    "change_records": "change_id",
    "certification_orders": "order_id",
    "backport_requests": "backport_id",
}
ITEM_FIELD = {"plan": "coverage_item_or_resource", "quantity": "controlled_item_or_record", "schedule": "affected_resource_or_operation"}
GAP_FIELD = {"plan": "shortage_quantity", "quantity": "transaction_quantity", "schedule": "capacity_gap"}
CASE_FOLDER = "Release Engineering/Cases/{case}"
OPEN_SOURCE_ANCHORS = (
    {
        "name": "SWE-bench Verified",
        "harbor_dataset": "swe-bench/swe-bench-verified",
        "harbor_url": "https://hub.harborframework.com/datasets/swe-bench/swe-bench-verified/latest",
        "upstream_url": "https://github.com/SWE-bench/SWE-bench",
        "license": "MIT",
        "evaluation_shape": "issue-to-patch tasks in real repositories graded by executable tests",
        "distribution_note": "no upstream tasks, repositories, patches, or scores redistributed; this family covers the release-engineering decision around a fix that patch grading does not",
    },
    {
        "name": "SWE-bench Pro",
        "harbor_dataset": "scale-ai/swe-bench-pro",
        "harbor_url": "https://hub.harborframework.com/datasets/scale-ai/swe-bench-pro/latest",
        "upstream_url": "https://github.com/scaleapi/SWE-bench_Pro-os",
        "evaluation_shape": "long-horizon repository tasks with hidden executable tests",
        "distribution_note": "no upstream tasks or scores redistributed",
    },
    {
        "name": "Aider Polyglot",
        "harbor_dataset": "aider/aider-polyglot",
        "harbor_url": "https://hub.harborframework.com/datasets/aider/aider-polyglot/latest",
        "upstream_url": "https://github.com/Aider-AI/polyglot-benchmark",
        "evaluation_shape": "multi-language coding exercises graded by unit tests",
        "distribution_note": "no upstream exercises or scores redistributed",
    },
)
PLAN_SELECTED_OPTIONS = {"standard_certification_plan": "standard", "expedite_lab_certification": "expedited"}
CORRELATED_SYSTEMS = ["scm", "tracker", "ci", "deploy", "success", "partners", "messages", "chat"]


# --------------------------------------------------------------------------- #
# Derivations and cross-checks
# --------------------------------------------------------------------------- #


def _issues_by_key(scenario: Scenario) -> dict[str, Issue]:
    return {issue.key: issue for issue in scenario.issues}


def _class(scenario: Scenario, code: str):
    return next(item for item in scenario.classes if item.code == code)


def _validity_horizon(scenario: Scenario) -> str:
    return (date.fromisoformat(AS_OF) + timedelta(days=scenario.primary_class.min_validity_days)).isoformat()


def _result_excluded(item: Result, scenario: Scenario) -> bool:
    return item.status != "PASSED" or item.held_for is not None or item.register_excluded or item.valid_until <= _validity_horizon(scenario)


def _scoped_results(scenario: Scenario) -> list[Result]:
    cls = scenario.primary_class
    return [item for item in scenario.results if item.verification_class == cls.code and item.source_id == scenario.numbers.get("coverage_source")]


def calendar(scenario: Scenario) -> dict[tuple[str, str, str], dict[str, Any]]:
    overrides = {(item.day, item.lane, item.session): item for item in scenario.windows}
    grid: dict[tuple[str, str, str], dict[str, Any]] = {}
    for day in business_days():
        for lane in scenario.lanes:
            for session in ("AM", "PM"):
                key = (day, lane.lane_id, session)
                override = overrides.get(key)
                if override is None:
                    entry = {"status": "busy", "hold_reason": "scheduled release load", "change_id": None}
                elif override.status == "busy" and override.reason.startswith("CHG-"):
                    entry = {"status": "busy", "hold_reason": "change booked", "change_id": override.reason}
                elif override.status == "free":
                    entry = {"status": "free", "hold_reason": None, "change_id": None}
                else:
                    entry = {"status": override.status, "hold_reason": override.reason or override.status, "change_id": None}
                grid[key] = entry
    return grid


def first_window_on_or_after(scenario: Scenario, start: str, windows_needed: int, lanes: list[str]) -> tuple[str, str, str] | None:
    grid = calendar(scenario)
    active = {lane.lane_id for lane in scenario.lanes if lane.status == "ACTIVE"}
    for day in business_days():
        if day < start:
            continue
        for lane in lanes:
            if lane not in active:
                continue
            free = [session for session in ("AM", "PM") if grid[(day, lane, session)]["status"] == "free"]
            if windows_needed == 1 and free:
                return day, lane, free[0]
            if windows_needed == 2 and len(free) == 2:
                return day, lane, "AM+PM"
    return None


def in_scope_changes(scenario: Scenario) -> list[tuple[Change, Issue]]:
    window = scenario.numbers.get("in_scope_window")
    if not window:
        return []
    issues = _issues_by_key(scenario)
    code = scenario.primary_class.code
    selected = []
    for change in scenario.changes:
        if change.status != "booked" or change.start is None:
            continue
        issue = issues.get(change.issue_key or "")
        if issue is None or issue.verification_class != code:
            continue
        if window[0] <= change.start[:10] <= window[1]:
            selected.append((change, issue))
    return sorted(selected, key=lambda item: (item[0].start, item[0].change_id))


def _component_modules(scenario: Scenario, issue: Issue) -> list[str]:
    return [module.module_id for module in scenario.modules if module.component_id == issue.component_id and module.gate is None]


def touched_modules_from_commits(scenario: Scenario, issue: Issue) -> int:
    """Distinct modules touched by the commits inside the issue's regression range on the branch the impact analysis covers."""

    if not issue.regression_from or not issue.regression_to:
        return 0
    branch = scenario.commits_query.get("branch")
    ordered = sorted((commit for commit in scenario.commits if commit.branch == branch), key=lambda commit: (commit.authored_at, commit.sha))
    shas = [commit.sha for commit in ordered]
    start, end = shas.index(issue.regression_from), shas.index(issue.regression_to)
    touched: set[str] = set()
    for commit in ordered[start : end + 1]:
        touched.update(commit.modules)
    return len(touched)


def expected_ci_minutes(scenario: Scenario) -> int:
    pipeline = next(item for item in scenario.pipelines if item.pipeline_id == scenario.numbers["ci_pipeline"])
    affected = set(_component_modules(scenario, scenario.primary_issue))
    retries = sum(item.retry_minutes for item in scenario.flaky if item.status == "QUARANTINED" and item.module_id in affected)
    return pipeline.base_minutes + scenario.pool.queue_minutes + retries


def _commit_register(scenario: Scenario) -> dict[str, int]:
    numbers = scenario.numbers
    source, target = numbers["coverage_source"], numbers["receiving_ref"]
    keys = {issue.key for _, issue in in_scope_changes(scenario)}
    observed = [commit for commit in scenario.commits if commit.branch == source and commit.backported_to != target]
    excluded = [commit for commit in observed if commit.status != "merged"]
    fixes = [commit for commit in scenario.commits if commit.fix_for in keys]
    receiving = [commit for commit in fixes if commit.backported_to == target]
    return {
        "observed": len(observed),
        "excluded": len(excluded),
        "eligible": len(observed) - len(excluded),
        "scope": len(fixes),
        "receiving_usable": len(receiving),
        "fix_pull_requests": len({commit.pr_number for commit in fixes}),
    }


def verify_numbers(scenario: Scenario) -> None:
    numbers = scenario.numbers
    extra = scenario.extra_answer
    cls = scenario.primary_class
    components = components_by_id(scenario)
    issue = scenario.primary_issue
    problems: list[str] = []

    def check(label: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            problems.append(f"{label}: computed {actual!r} but scenario declares {expected!r}")

    def intish(value: float) -> Any:
        return int(value) if float(value).is_integer() else value

    scoped = _scoped_results(scenario)
    if scenario.mode in {"plan", "quantity"} and numbers.get("register") != "commits":
        observed = sum(item.runs for item in scoped)
        excluded = sum(item.runs for item in scoped if _result_excluded(item, scenario))
        check("observed", observed, numbers["observed"])
        check("excluded", excluded, numbers["excluded"])
        check("eligible", observed - excluded, numbers["eligible"])
    if issue.basis == "impact":
        component = components[issue.component_id]
        check("impact touched modules from commits", touched_modules_from_commits(scenario, issue), int(component.impact_value))
        check("gated modules on the component", sum(1 for module in scenario.modules if module.component_id == issue.component_id and module.gate is not None), issue.gated_modules)
    if "contracted_penalty_usd" in extra:
        check("contracted_penalty_usd", scenario.commitment.penalty_usd, extra["contracted_penalty_usd"])
        check("commitment issue", scenario.commitment.issue_key, issue.key)
    if numbers.get("need_source") == "commitment":
        check("business_need", scenario.commitment.cutover_date, scenario.business_need)
    if scenario.mode == "plan":
        component = components[issue.component_id]
        check("impact_measure", intish(component.impact_value), extra["impact_measure"])
        check("impact_unit", "MODULE" if component.impact_metric == "TOUCHED-MODULES" else "GB", extra["impact_unit"])
        check("gated_modules", issue.gated_modules, extra["gated_modules"])
        check("affected_modules", affected_modules(issue, components), extra["affected_modules"])
        check("required_checks_per_module", cls.runs_per_module, extra["required_checks_per_module"])
        check("environments_in_scope", issue.environments_in_scope, extra["environments_in_scope"])
        check("expected_ci_minutes", expected_ci_minutes(scenario), extra["expected_ci_minutes"])
        check("scope", issue_runs(scenario, issue), numbers["scope"])
    if scenario.mode == "quantity":
        changes = in_scope_changes(scenario)
        check("scheduled_changes", len(changes), extra["scheduled_changes"])
        first = changes[0][0] if changes else None
        if first is not None:
            session = "AM" if first.start[11:] < WINDOW_TIMES["PM"][0] else "PM"
            check("first_change_window", f"{first.lane_id}/{first.start[:10]}/{session}", extra["first_change_window"])
            check("business_need", first.start[:10], scenario.business_need)
        if numbers.get("register") == "commits":
            register = _commit_register(scenario)
            for key in ("observed", "excluded", "eligible", "scope", "receiving_usable"):
                check(key, register[key], numbers[key])
            check("fix_pull_requests", register["fix_pull_requests"], extra["fix_pull_requests"])
            check("receiving_branch_present", register["receiving_usable"], extra["receiving_branch_present"])
            check("merge_queue_date", scenario.primary_write.arguments["scheduled_date"], extra["merge_queue_date"])
            check("transaction_quantity", min(numbers["scope"] - numbers["receiving_usable"], numbers["eligible"]), numbers["transaction_quantity"])
            check("selected completion", next_business_day(extra["merge_queue_date"]), next(option for option in scenario.options if option.recommended).completion)
        else:
            check("scope", sum(issue_runs(scenario, item) for _, item in changes), numbers["scope"])
            impact_issue = [item for _, item in changes if item.basis == "impact"]
            if impact_issue and "impact_touched_modules" in extra:
                check("impact_touched_modules", intish(components[impact_issue[0].component_id].impact_value), extra["impact_touched_modules"])
                check("gated_modules", impact_issue[0].gated_modules, extra["gated_modules"])
            check("required_checks_per_module", cls.runs_per_module, extra["required_checks_per_module"])
            check("margin_runs", numbers["margin"], extra["margin_runs"])
            check("transaction_quantity", numbers["gap"] + numbers["margin"], numbers["transaction_quantity"])
    if scenario.mode == "schedule":
        grid = calendar(scenario)
        start, end = numbers["capacity_window"]
        days = [day for day in business_days() if start <= day <= end]
        keys = [(day, lane, session) for day in days for lane in numbers["eligible_lanes"] for session in ("AM", "PM")]
        candidate = len(keys) * WINDOW_HOURS
        free = sum(1 for key in keys if grid[key]["status"] == "free")
        check("candidate", candidate, numbers["observed"])
        check("excluded", candidate - free * WINDOW_HOURS, numbers["excluded"])
        check("eligible", free * WINDOW_HOURS, numbers["eligible"])
        affected = [item for item in scenario.issues if item.verification_class == cls.code]
        if numbers.get("scope_source") == "primary":
            hours = (issue.build_minutes + issue.bake_minutes) / 60
            required_runs = issue_runs(scenario, issue)
        else:
            hours = sum((item.build_minutes + item.bake_minutes) / 60 for item in affected)
            required_runs = sum(issue_runs(scenario, item) for item in affected)
        check("scope", int(hours), numbers["scope"])
        usable = sum(item.runs for item in scoped if not _result_excluded(item, scenario))
        check("gate_results_usable", usable, extra["gate_results_usable"])
        check("gate_results_required", required_runs, extra["gate_results_required"])
        check("windows_required", int(numbers["sessions_needed"]), extra["windows_required"])
        if "requested_day" in extra:
            check("requested_day", numbers["capacity_window"][0], extra["requested_day"])
        if "affected_changes" in extra:
            issues = _issues_by_key(scenario)
            stranded = [change for change in scenario.changes if issues.get(change.issue_key or "") in affected]
            check("affected_changes", len(stranded), extra["affected_changes"])
        if "changes_per_window" in extra:
            check("changes_per_window", extra["affected_changes"] // extra["windows_required"], extra["changes_per_window"])
    gap = max(0, numbers["scope"] - numbers["eligible"])
    check("gap", gap, numbers["gap"])
    check("standard_readiness", next_business_day(scenario.confirmation.standard_date), scenario.standard_readiness)
    check("expedited_readiness", next_business_day(scenario.confirmation.expedited_date), scenario.expedited_readiness)
    check("confirmation class", scenario.confirmation.verification_class, cls.code)
    windows_needed = 2 if scenario.mode == "schedule" and numbers.get("full_day_needed") else 1
    slot_lanes = numbers["eligible_lanes"]
    standard_slot = first_window_on_or_after(scenario, scenario.standard_readiness, windows_needed, slot_lanes)
    expedited_slot = first_window_on_or_after(scenario, scenario.expedited_readiness, windows_needed, slot_lanes)
    check("standard_slot_date", standard_slot[0] if standard_slot else None, numbers["standard_slot_date"])
    check("expedited_slot_date", expedited_slot[0] if expedited_slot else None, numbers["expedited_slot_date"])
    if scenario.mode == "plan":
        check("earliest_qualified_base_window", numbers["standard_slot_date"], extra["earliest_qualified_base_window"])
        expedited_option = scenario.options[1]
        check("expedited option date", expedited_slot[0] if expedited_slot else None, expedited_option.completion)
        check(
            "expedite_completion_days_saved",
            (date.fromisoformat(numbers["standard_slot_date"]) - date.fromisoformat(numbers["expedited_slot_date"])).days,
            extra["expedite_completion_days_saved"],
        )
        selected = next(option for option in scenario.options if option.recommended)
        if selected.id in PLAN_SELECTED_OPTIONS:
            readiness = scenario.standard_readiness if PLAN_SELECTED_OPTIONS[selected.id] == "standard" else scenario.expedited_readiness
            slot = first_window_on_or_after(scenario, readiness, 1, slot_lanes)
            if slot is not None:
                check("selected_lane_window", f"{slot[1]}/{slot[0]}/{slot[2]}", extra["selected_lane_window"])
                check("selected completion", slot[0], selected.completion)
    if scenario.mode == "schedule":
        selected_date = next(option for option in scenario.options if option.recommended).completion
        if numbers.get("full_day_needed"):
            full_day = first_window_on_or_after(scenario, numbers["capacity_window"][0], 2, numbers["eligible_lanes"])
            check("selected_resource", f"{full_day[1]}/{full_day[0]}/{full_day[2]}" if full_day else None, numbers["selected_resource"])
            check("selected completion", full_day[0] if full_day else None, selected_date)
        else:
            grid = calendar(scenario)
            free_windows = [key for key in sorted(grid) if key[1] in numbers["eligible_lanes"] and grid[key]["status"] == "free" and key[0] >= numbers["capacity_window"][0]]
            check("selected_resource", f"{free_windows[0][1]}/{free_windows[0][0]}/{free_windows[0][2]}" if free_windows else None, numbers["selected_resource"])
            sessions_needed = int(numbers["sessions_needed"])
            check("selected completion", free_windows[sessions_needed - 1][0] if len(free_windows) >= sessions_needed else None, selected_date)
    if scenario.selected_window_id not in {window_id(lane, day, session) for (day, lane, session) in calendar(scenario)}:
        problems.append(f"selected window {scenario.selected_window_id} is not on the calendar")
    if problems:
        raise ValueError(f"{scenario.task_id} scenario data disagrees with its declared numbers:\n  " + "\n  ".join(problems))


# --------------------------------------------------------------------------- #
# Seed tables
# --------------------------------------------------------------------------- #


def _impact_rows(component: Component) -> list[dict[str, Any]]:
    unit = "MODULE" if component.impact_metric == "TOUCHED-MODULES" else "GB"
    rows = [
        {"report_id": component.impact_id, "component_id": component.component_id, "metric": component.impact_metric, "value": component.impact_value, "unit": unit, "generated_at": component.impact_date, "status": "final"},
    ]
    if component.stale_value:
        rows.append(
            {"report_id": component.stale_impact_id, "component_id": component.component_id, "metric": component.impact_metric, "value": component.stale_value, "unit": unit, "generated_at": component.stale_date, "status": "final"}
        )
    return rows


def seed_tables(scenario: Scenario, drive_files: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grid = calendar(scenario)
    windows = [
        {"window_id": window_id(lane, day, session), "lane_id": lane, "service_date": day, "session": session, "start_time": WINDOW_TIMES[session][0], "end_time": WINDOW_TIMES[session][1], **entry}
        for (day, lane, session), entry in sorted(grid.items())
    ]
    components = [scenario.component, *scenario.other_components]
    return {
        "users": [dict(row) for row in USERS],
        "repositories": [dict(row) for row in REPOSITORIES],
        "environments": [dict(row) for row in ENVIRONMENTS],
        "engineers": [dict(row) for row in ENGINEERS],
        "components": [
            {"component_id": c.component_id, "code": c.code, "name": c.name, "tier": c.tier, "owner_team": c.owner_team, "repo_id": c.repo_id, "primary_engineer_id": c.engineer_id}
            for c in components
        ],
        "impact_reports": [row for c in components for row in _impact_rows(c)],
        "verification_classes": [
            {
                "verification_class": c.code,
                "display": c.display,
                "runs_per_module": c.runs_per_module,
                "required_checks_json": json.dumps(list(c.required_checks)),
                "evidence_tier": c.evidence_tier,
                "minimum_validity_days": c.min_validity_days,
                "release_eligible": int(c.release_eligible),
                "interchangeable_with": c.interchangeable_with,
            }
            for c in scenario.classes
        ],
        "modules": [
            {"module_id": m.module_id, "repo_id": m.repo_id, "path": m.path, "component_id": m.component_id, "owner_team": m.owner_team, "codeowner_id": m.codeowner_id, "verification_class": m.verification_class, "gate": m.gate, "gate_note": m.gate_note or None}
            for m in scenario.modules
        ],
        "commits": [
            {"sha": c.sha, "repo_id": c.repo_id, "branch": c.branch, "authored_at": c.authored_at, "author_id": c.author_id, "message": c.message, "pr_number": c.pr_number, "status": c.status, "backported_to": c.backported_to, "fix_for": c.fix_for}
            for c in scenario.commits
        ],
        "commit_modules": [{"sha": c.sha, "module_id": module} for c in scenario.commits for module in c.modules],
        "pull_requests": [
            {"pr_id": p.pr_id, "repo_id": p.repo_id, "number": p.number, "title": p.title, "head_sha": p.head_sha, "base_branch": p.base_branch, "status": p.status, "issue_key": p.issue_key, "author_id": p.author_id, "opened_at": p.opened_at, "superseded_by": p.superseded_by}
            for p in scenario.pulls
        ],
        "reviews": [{"review_id": r.review_id, "pr_id": r.pr_id, "reviewer_id": r.reviewer_id, "state": r.state, "submitted_at": r.submitted_at} for r in scenario.reviews],
        "branch_rules": [
            {
                "rule_id": scenario.branch_rule.rule_id,
                "repo_id": scenario.branch_rule.repo_id,
                "branch": scenario.branch_rule.branch,
                "required_checks_json": json.dumps(list(scenario.branch_rule.required_checks)),
                "required_approvals": scenario.branch_rule.required_approvals,
                "codeowner_review_required": int(scenario.branch_rule.codeowner_review_required),
                "status": scenario.branch_rule.status,
            }
        ],
        "customers": [{"customer_id": scenario.customer.customer_id, "name": scenario.customer.name, "tier": scenario.customer.tier, "environment_id": scenario.customer.environment_id, "account_owner": scenario.customer.account_owner}],
        "issues": [
            {
                "issue_key": i.key,
                "component_id": i.component_id,
                "title": i.title or i.scope_note,
                "verification_class": i.verification_class,
                "basis": i.basis,
                "fixed_modules": i.fixed_modules,
                "gated_modules": i.gated_modules,
                "environments_in_scope": i.environments_in_scope,
                "scope_note": i.scope_note,
                "build_minutes": i.build_minutes,
                "bake_minutes": i.bake_minutes,
                "status": i.status,
                "severity": i.severity,
                "kind": i.kind,
                "customer_id": i.customer_id,
                "commitment_id": i.commitment_id,
                "regression_from": i.regression_from,
                "regression_to": i.regression_to,
                "opened_at": i.opened_at,
                "requested_by": i.requested_by,
                "duplicate_of": i.duplicate_of,
                "fix_version": i.fix_version,
                "note": i.note or None,
            }
            for i in scenario.issues
        ],
        "commitments": [
            {
                "commitment_id": scenario.commitment.commitment_id,
                "customer_id": scenario.commitment.customer_id,
                "issue_key": scenario.commitment.issue_key,
                "kind": scenario.commitment.kind,
                "cutover_date": scenario.commitment.cutover_date,
                "penalty_usd": scenario.commitment.penalty_usd,
                "contract_ref": scenario.commitment.contract_ref,
                "status": scenario.commitment.status,
                "note": scenario.commitment.note,
            }
        ],
        "result_sources": [dict(row) for row in RESULT_SOURCES],
        "verification_results": [
            {"result_id": r.result_id, "verification_class": r.verification_class, "result_label": r.label, "source_id": r.source_id, "run_count": r.runs, "valid_until": r.valid_until, "status": r.status, "status_reason": r.reason, "held_for_issue": r.held_for}
            for r in scenario.results
        ],
        "flaky_tests": [{"flaky_id": f.flaky_id, "check_name": f.check_name, "module_id": f.module_id, "quarantined_since": f.quarantined_since, "retry_minutes": f.retry_minutes, "status": f.status, "note": f.note or None} for f in scenario.flaky],
        "coverage_reports": [{"report_id": c.report_id, "module_id": c.module_id, "build_sha": c.build_sha, "line_coverage": c.line_coverage, "threshold": c.threshold, "generated_at": c.generated_at, "status": c.status} for c in scenario.coverage],
        "runner_pools": [{"pool_id": scenario.pool.pool_id, "name": scenario.pool.name, "capacity": scenario.pool.capacity, "queue_minutes": scenario.pool.queue_minutes, "status": scenario.pool.status, "note": scenario.pool.note or None}],
        "pipelines": [
            {"pipeline_id": p.pipeline_id, "name": p.name, "repo_id": p.repo_id, "component_id": p.component_id, "kind": p.kind, "trigger": p.trigger, "base_minutes": p.base_minutes, "status": p.status}
            for p in scenario.pipelines
        ],
        "pipeline_runs": [
            {"run_id": r.run_id, "pipeline_id": r.pipeline_id, "head_sha": r.head_sha or None, "started_at": r.started_at, "finished_at": r.finished_at, "status": r.status, "exit_code": r.exit_code, "summary": r.summary}
            for r in scenario.pipeline_runs
        ],
        "lanes": [{"lane_id": lane.lane_id, "name": lane.name, "cluster": lane.cluster, "status": lane.status, "isolation_capable": int(lane.isolation_capable), "status_note": lane.note} for lane in scenario.lanes],
        "release_windows": windows,
        "change_records": [
            {"change_id": c.change_id, "component_id": c.component_id, "issue_key": c.issue_key, "lane_id": c.lane_id, "start_time": c.start, "end_time": c.end, "status": c.status, "description": c.description, "revision": 1, "last_updated": "2026-05-01T12:00:00"}
            for c in scenario.changes
        ],
        "feature_flags": [{"flag_key": f.flag_key, "environment_id": f.environment_id, "state": f.state, "scope": f.scope, "note": f.note or None, "revision": 1, "last_updated": "2026-05-01T12:00:00"} for f in scenario.flags],
        "partners": [dict(row) for row in PARTNERS],
        "partner_confirmations": [
            {
                "confirmation_id": c.confirmation_id,
                "partner_id": c.partner_id,
                "verification_class": c.verification_class,
                "reference": c.reference,
                "runs_available": c.runs_available,
                "standard_ready_date": c.standard_date,
                "expedited_ready_date": c.expedited_date,
                "expedite_fee_usd": c.fee,
                "per_run_fee_usd": c.per_run_fee,
                "valid_until": c.valid_until,
                "status": c.status,
                "note": c.note,
            }
            for c in (scenario.confirmation, *scenario.other_confirmations)
        ],
        "certification_orders": [
            {
                "order_id": "ORD-3400",
                "partner_id": "PRT-BRIGHTWATER",
                "confirmation_id": None,
                "verification_class": scenario.classes[-1].code,
                "run_count": 2,
                "unit": "CHECK_RUN",
                "service_option": "standard",
                "expected_ready_date": "2026-04-22",
                "status": "RECEIVED",
                "requested_by": "release_engineering_coordinator",
                "created_at": "2026-04-17T09:30:00",
                "revision": 1,
            },
        ],
        "backport_requests": [dict(row) for row in scenario.seed.get("backports", ())],
        "reviewer_availability": [{"availability_id": a.availability_id, "engineer_id": a.engineer_id, "service_date": a.day, "session": a.session, "status": a.status, "note": a.note or None} for a in scenario.availability],
        "approvals": [
            {
                "approval_id": scenario.approval.approval_id,
                "subject": scenario.approval.subject,
                "approver_id": scenario.approval.approver_id,
                "approver_role": scenario.approval.approver_role,
                "status": "APPROVED",
                "granted_on": scenario.approval.granted_on,
                "scope_json": json.dumps(scenario.approval.scope, sort_keys=True),
            },
            {
                "approval_id": "AP-RD-0090",
                "subject": "Quarterly CI runner capacity standing order",
                "approver_id": "U-RAGHUNATHAN",
                "approver_role": "release_engineering_manager",
                "status": "APPROVED",
                "granted_on": "2026-02-09",
                "scope_json": json.dumps({"category": "RUNNER_CAPACITY", "max_spend_usd": 9000}, sort_keys=True),
            },
        ],
        "messages": [
            {
                "message_id": scenario.email.message_id,
                "thread_id": scenario.email.thread_id,
                "channel": "email",
                "sender": scenario.email.sender,
                "recipients": scenario.email.recipients,
                "subject": scenario.email.subject,
                "sent_at": scenario.email.sent_at,
                "body": scenario.email.body,
                "attachments_json": json.dumps([{"name": name, "mime_type": "application/pdf"} for name in scenario.email.attachments]),
                "labels": f"{scenario.email.labels},{scenario.case_reference}",
            },
            {
                "message_id": f"MSG-{scenario.ordinal:04d}-00",
                "thread_id": f"THR-{scenario.ordinal:04d}-OPS",
                "channel": "email",
                "sender": "hanna.solberg@larkspur.example",
                "recipients": "release-eng@larkspur.example",
                "subject": "Weekly release note",
                "sent_at": "2026-05-01T08:00:00",
                "body": "On-call rota for the week of 2026-05-04 is posted. Lane capability flags are on the shared drive roster; no changes to protected blocks.",
                "attachments_json": "[]",
                "labels": "operations",
            },
        ],
        "chat_threads": [
            {
                "thread_id": scenario.chat.thread_id,
                "channel": scenario.chat.channel,
                "title": scenario.chat.title,
                "messages_json": json.dumps([{"author": author, "ts": ts, "text": text} for author, ts, text in scenario.chat.messages]),
            },
            {
                "thread_id": f"CHAT-{scenario.ordinal:04d}-GEN",
                "channel": "#release-eng",
                "title": "General — flag hygiene and lane access",
                "messages_json": json.dumps([{"author": "Hanna Solberg", "ts": "2026-04-30T16:40:00", "text": "Reminder: log every feature-flag change in the change tracker."}]),
            },
        ],
        "drive_files": drive_files,
        "evidence_files": evidence,
    }


# --------------------------------------------------------------------------- #
# Evidence room
# --------------------------------------------------------------------------- #


def _issue_json(scenario: Scenario, issue: Issue) -> str:
    cls = _class(scenario, issue.verification_class)
    row = {
        "issue_key": issue.key,
        "component_id": issue.component_id,
        "title": issue.title or issue.scope_note,
        "verification_class": issue.verification_class,
        "basis": issue.basis,
        "fixed_modules": issue.fixed_modules,
        "gated_modules": issue.gated_modules,
        "environments_in_scope": issue.environments_in_scope,
        "scope_note": issue.scope_note,
        "build_minutes": issue.build_minutes,
        "bake_minutes": issue.bake_minutes,
        "status": issue.status,
        "severity": issue.severity,
        "kind": issue.kind,
        "customer_id": issue.customer_id,
        "commitment_id": issue.commitment_id,
        "regression_from": issue.regression_from,
        "regression_to": issue.regression_to,
        "opened_at": issue.opened_at,
        "requested_by": issue.requested_by,
        "duplicate_of": issue.duplicate_of,
        "fix_version": issue.fix_version,
        "note": issue.note,
    }
    rendered = repo_tools._issue(row, {"display": cls.display, "runs_per_module": cls.runs_per_module})
    return json.dumps({"export": "tracker.issues.get", "record": rendered}, indent=2, sort_keys=True) + "\n"


def _component_summary_json(scenario: Scenario) -> str:
    component = scenario.component
    rendered = repo_tools._component(
        {"component_id": component.component_id, "code": component.code, "name": component.name, "tier": component.tier, "owner_team": component.owner_team, "repo_id": component.repo_id, "primary_engineer_id": component.engineer_id}
    )
    reports = [repo_tools._impact(row) for row in _impact_rows(component)]
    return json.dumps({"export": "scm.components.get + scm.impact.list", "component": rendered, "impact_reports": reports}, indent=2, sort_keys=True) + "\n"


def _confirmation_text(scenario: Scenario) -> str:
    c = scenario.confirmation
    partner = next(row["name"] for row in PARTNERS if row["partner_id"] == c.partner_id)
    account = next(row["account_number"] for row in PARTNERS if row["partner_id"] == c.partner_id)
    return (
        f"{partner}\nCertification confirmation {c.reference} (system reference {c.confirmation_id})\nCustomer: Larkspur Systems Release Engineering, account {account}\n"
        f"Case reference: {scenario.case_reference}\nGate class: {c.verification_class} — {scenario.primary_class.display}\nCertified runs available for this confirmation: {c.runs_available}\nPer-run certification fee: USD {c.per_run_fee:.2f}\n"
        f"Standard ready date: {c.standard_date}\nExpedited ready date: {c.expedited_date} (expedite fee USD {c.fee}, flat)\nValid until: {c.valid_until}\nNotes: {c.note}\n"
        "Certified results are delivered to the customer's evidence import endpoint; release use is subject to the customer's re-verification.\n"
    )


def _decoy_asset(scenario: Scenario) -> dict[str, Any]:
    doc = scenario.decoy_doc
    if doc.kind == "policy_superseded":
        return asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=MARKDOWN,
                     content=scoped_markdown(SUPERSEDED_PLAYBOOK, task_id=scenario.task_id, case_reference=scenario.case_reference),
                     preview="2024 playbook retained for audit only; superseded by v5.")
    if doc.kind == "decoy_issue":
        key = doc.path.rsplit("/", 1)[-1].removeprefix("issue-").removesuffix(".json")
        issue = next(item for item in scenario.issues if item.key == key)
        return asset(doc.path, kind=doc.kind, title=doc.title, source="tracker_export", media_type=JSON, content=_issue_json(scenario, issue),
                     preview="A similarly named or superseded issue that must not drive the requirement.")
    if doc.media_type == XLSX:
        return asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=XLSX, rows=[list(row) for row in doc.rows or ()], preview=doc.title)
    content = scoped_csv(doc.content, task_id=scenario.task_id, case_reference=scenario.case_reference) if doc.kind == "margin_policy" else doc.content
    return asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=doc.media_type, content=content, preview=doc.title)


def build_assets(scenario: Scenario) -> list[dict[str, Any]]:
    case = scenario.case_reference
    grid = calendar(scenario)
    issue = scenario.primary_issue
    branch = str(scenario.commits_query.get("branch", "main")).replace("/", "-")
    engineer_names = {row["engineer_id"]: row["name"] for row in ENGINEERS}
    assets: list[dict[str, Any]] = [
        asset("playbook/release-engineering-playbook.md", kind="policy", title="Release engineering playbook v5 (effective)", source="drive", media_type=MARKDOWN,
              content=scoped_markdown(effective_playbook(AS_OF), task_id=scenario.task_id, case_reference=case),
              preview="Fix-requirement, usable-evidence, lane-window, and authority rules in force."),
    ]
    if scenario.decoy_doc.kind != "policy_superseded":
        assets.append(
            asset("playbook/superseded-release-playbook-2024.md", kind="policy_superseded", title="Release engineering playbook 2024 (superseded)", source="drive", media_type=MARKDOWN,
                  content=scoped_markdown(SUPERSEDED_PLAYBOOK, task_id=scenario.task_id, case_reference=case),
                  preview="2024 playbook retained for audit only; superseded by v5.")
        )
    assets.append(_decoy_asset(scenario))
    assets.extend(
        [
            asset(f"tracker/issue-{issue.key}.json", kind="issue_export", title=f"Issue {issue.key} (tracker export)", source="tracker_export", media_type=JSON,
                  content=_issue_json(scenario, issue), preview="The active issue: scope basis, gate class, environments, and durations."),
            asset(f"scm/component-{scenario.component.code}-impact.json", kind="component_summary", title=f"Component {scenario.component.code} summary with impact analyses (SCM export)", source="scm_export", media_type=JSON,
                  content=_component_summary_json(scenario), preview="Component identity plus current and historical impact analyses."),
            asset(f"scm/commits-{branch}-fix-range.csv", kind="commit_range", title=f"Commits on {scenario.commits_query.get('branch', 'main')} around the fix range (SCM export)", source="scm_export", media_type=CSV,
                  content="sha,branch,authored_at,author,message,pull_request,status,backported_to,fix_for,touched_modules\n"
                  + "".join(
                      f'{c.sha},{c.branch},{c.authored_at},{engineer_names.get(c.author_id, c.author_id)},"{c.message}",{c.pr_number or ""},{c.status},{c.backported_to or ""},{c.fix_for or ""},{"|".join(c.modules)}\n'
                      for c in scenario.commits
                  ),
                  preview="Every commit in the range with its status, backport state, and touched modules."),
            asset("scm/pull-requests-and-reviews.json", kind="pull_requests", title="Pull requests and reviews linked to the case (SCM export)", source="scm_export", media_type=JSON,
                  content=json.dumps(
                      {
                          "case_reference": case,
                          "pull_requests": [
                              {"pr_id": p.pr_id, "number": p.number, "title": p.title, "head_sha": p.head_sha, "base_branch": p.base_branch, "status": p.status, "issue_key": p.issue_key, "superseded_by": p.superseded_by, "opened_at": p.opened_at}
                              for p in scenario.pulls
                          ],
                          "reviews": [{"review_id": r.review_id, "pr_id": r.pr_id, "reviewer": engineer_names.get(r.reviewer_id, r.reviewer_id), "state": r.state, "submitted_at": r.submitted_at} for r in scenario.reviews],
                          "branch_rule": {"rule_id": scenario.branch_rule.rule_id, "branch": scenario.branch_rule.branch, "required_checks": list(scenario.branch_rule.required_checks), "required_approvals": scenario.branch_rule.required_approvals},
                      },
                      indent=2,
                      sort_keys=True,
                  )
                  + "\n",
                  preview="Open, merged, and superseded pull requests with their reviews and the protected-branch rule."),
            asset("scm/module-registry.csv", kind="module_registry", title="Module registry: codeowners, gate class, revert / flag gates", source="scm_export", media_type=CSV,
                  content="module_id,path,component_id,owner_team,codeowner,verification_class,gate,gate_note\n"
                  + "".join(f"{m.module_id},{m.path},{m.component_id},{m.owner_team},{engineer_names.get(m.codeowner_id, m.codeowner_id)},{m.verification_class},{m.gate or ''},{m.gate_note}\n" for m in scenario.modules),
                  preview="Which touched modules are gated by a revert or a disabled flag."),
            asset("ci/gate-class-catalog.csv", kind="class_catalog", title="Gate class catalog: runs per module and minimum validity", source="ci_export", media_type=CSV,
                  content="verification_class,display,runs_per_module,required_checks,evidence_tier,minimum_validity_days,release_eligible,interchangeable_with\n"
                  + "".join(f"{c.code},{c.display},{c.runs_per_module},{'|'.join(c.required_checks)},{c.evidence_tier},{c.min_validity_days},{'yes' if c.release_eligible else 'no'},{c.interchangeable_with or ''}\n" for c in scenario.classes),
                  preview="Runs per module used for the requirement and the 14-day minimum validity."),
            asset("ci/verification-results-by-set.xlsx", kind="evidence_workbook", title="Registered verification results by set (gross)", source="ci_workbook", media_type=XLSX,
                  rows=[["result_label", "verification_class", "source_id", "run_count", "valid_until"], *[[r.label, r.verification_class, r.source_id, r.runs, r.valid_until] for r in scenario.results]],
                  preview="Gross run counts by result set; status and holds live in the set register."),
            asset("ci/result-status-register.csv", kind="verification_register", title="Result-set status register (status, holds, incident notes)", source="ci_export", media_type=CSV,
                  content="result_label,verification_class,source_id,status,status_reason,held_for_issue,register_note\n"
                  + "".join(f"{r.label},{r.verification_class},{r.source_id},{r.status},{r.reason or ''},{r.held_for or ''},{r.register_note}\n" for r in scenario.results),
                  preview="Which result sets are failed, quarantined, held, or flagged."),
            asset("ci/pipeline-runs.csv", kind="pipeline_runs", title="Pipelines and recent runs", source="ci_export", media_type=CSV,
                  content="run_id,pipeline_id,pipeline_name,kind,trigger,head_sha,started_at,finished_at,status,exit_code,summary\n"
                  + "".join(
                      f'{r.run_id},{r.pipeline_id},{next(p.name for p in scenario.pipelines if p.pipeline_id == r.pipeline_id)},{next(p.kind for p in scenario.pipelines if p.pipeline_id == r.pipeline_id)},{next(p.trigger for p in scenario.pipelines if p.pipeline_id == r.pipeline_id)},{r.head_sha},{r.started_at},{r.finished_at},{r.status},{r.exit_code},"{r.summary}"\n'
                      for r in scenario.pipeline_runs
                  ),
                  preview="The pipelines and the runs that triggered the case."),
            asset("ci/flaky-test-registry.csv", kind="flaky_registry", title="Flaky-test registry (quarantine and retry exposure)", source="ci_export", media_type=CSV,
                  content=scoped_csv(
                      "flaky_id,check_name,module_id,quarantined_since,retry_minutes,status,note\n" + "".join(f"{f.flaky_id},{f.check_name},{f.module_id},{f.quarantined_since},{f.retry_minutes},{f.status},{f.note}\n" for f in scenario.flaky),
                      task_id=scenario.task_id, case_reference=case,
                  ),
                  preview="Quarantined checks and the retry minutes they add to a pipeline."),
            asset("ci/runner-pool-capacity.json", kind="pool_capacity", title=f"Runner pool capacity and queue — {case}", source="ci_export", media_type=JSON,
                  content=json.dumps(
                      {"case_reference": case, "pool": {"pool_id": scenario.pool.pool_id, "name": scenario.pool.name, "capacity": scenario.pool.capacity, "queue_minutes": scenario.pool.queue_minutes, "status": scenario.pool.status, "note": scenario.pool.note},
                       "pipelines": [{"pipeline_id": p.pipeline_id, "name": p.name, "base_minutes": p.base_minutes, "kind": p.kind} for p in scenario.pipelines]},
                      indent=2, sort_keys=True,
                  ) + "\n",
                  preview="Pool queue minutes and pipeline base durations used for the CI estimate."),
            asset("deploy/lane-calendar-2026-05-04.xlsx", kind="lane_calendar", title="Lane window calendar, three weeks from 2026-05-04", source="deploy_workbook", media_type=XLSX,
                  rows=[["service_date", "lane_id", "session", "start", "end", "status", "hold_reason"],
                        *[[day, lane, session, WINDOW_TIMES[session][0], WINDOW_TIMES[session][1], entry["status"], entry["hold_reason"] or ""] for (day, lane, session), entry in sorted(grid.items())]],
                  preview="Every lane window with free / busy / protected / blocked status."),
            asset("deploy/lane-roster-and-capabilities.csv", kind="lane_roster", title="Lane roster and tenant-isolation capability", source="deploy_export", media_type=CSV,
                  content=scoped_csv("lane_id,name,cluster,status,isolation_capable,note\n" + "".join(f"{lane.lane_id},{lane.name},{lane.cluster},{lane.status},{'yes' if lane.isolation_capable else 'no'},{lane.note or ''}\n" for lane in scenario.lanes),
                                     task_id=scenario.task_id, case_reference=case),
                  preview="Lane status and tenant-isolation capability flags for the week."),
            asset(f"partners/certification-confirmation-{scenario.confirmation.reference}.pdf", kind="partner_confirmation", title=f"Certification confirmation {scenario.confirmation.reference}", source="email_attachment", media_type=PDF,
                  content=_confirmation_text(scenario), preview="Standard and expedited ready dates, fee, and validity."),
            asset(f"success/commitment-{scenario.commitment.commitment_id}.json", kind="customer_commitment", title=f"Customer commitment {scenario.commitment.commitment_id} (customer-success export)", source="success_export", media_type=JSON,
                  content=json.dumps(
                      {"export": "success.commitments.get", "commitment": {"commitment_id": scenario.commitment.commitment_id, "customer_id": scenario.commitment.customer_id, "customer_name": scenario.customer.name, "issue_key": scenario.commitment.issue_key, "kind": scenario.commitment.kind,
                                                                            "cutover_date": scenario.commitment.cutover_date, "penalty_usd": scenario.commitment.penalty_usd, "contract_ref": scenario.commitment.contract_ref, "status": scenario.commitment.status, "note": scenario.commitment.note}},
                      indent=2, sort_keys=True,
                  ) + "\n",
                  preview="The contracted control date and the slip penalty, in the contract's words."),
            asset(f"messages/{scenario.email.thread_id}.eml", kind="email", title=scenario.email.subject, source="messages", media_type=EML,
                  content=eml(from_addr=scenario.email.sender, to_addr=scenario.email.recipients, subject=scenario.email.subject, date=scenario.email.sent_at,
                              message_id=f"{scenario.email.message_id}@larkspur.example", body=scenario.email.body, attachments=list(scenario.email.attachments)),
                  preview="The request and the control date, in the requester's words."),
            asset(f"chat/{scenario.chat.thread_id}.json", kind="chat_thread", title=scenario.chat.title, source="chat", media_type=JSON,
                  content=json.dumps({"thread_id": scenario.chat.thread_id, "channel": scenario.chat.channel, "title": scenario.chat.title, "messages": [{"author": a, "ts": t, "text": x} for a, t, x in scenario.chat.messages]}, indent=2, sort_keys=True) + "\n",
                  preview="Team chat with evidence, lane, and authority remarks."),
            asset(f"approvals/approval-{scenario.approval.approval_id}.json", kind="approval", title=f"Approval record {scenario.approval.approval_id}", source="approvals_export", media_type=JSON,
                  content=json.dumps({"approval_id": scenario.approval.approval_id, "case_reference": case, "subject": scenario.approval.subject, "approver_id": scenario.approval.approver_id, "approver_role": scenario.approval.approver_role, "status": "APPROVED", "granted_on": scenario.approval.granted_on, "scope": scenario.approval.scope}, indent=2, sort_keys=True) + "\n",
                  preview="Exactly what is approved, for which record, and what is not."),
            asset(f"exports/starting-state-{scenario.task_id}.json", kind="starting_state", title="Starting-state export (changes, certification orders, backports)", source="deploy_export", media_type=JSON,
                  content=json.dumps(
                      {
                          "case_reference": case,
                          "as_of": AS_OF,
                          "changes": [{"change_id": c.change_id, "component_id": c.component_id, "issue_key": c.issue_key, "lane_id": c.lane_id, "start": c.start, "end": c.end, "status": c.status} for c in scenario.changes],
                          "certification_orders": [{"order_id": "ORD-3400", "status": "RECEIVED"}],
                          "backport_requests": [dict(row) for row in scenario.seed.get("backports", ())],
                          "note": "Snapshot before any action; row order does not indicate applicability.",
                      },
                      indent=2, sort_keys=True,
                  ) + "\n",
                  preview="Snapshot of lane and register state before any action."),
            asset("oncall/reviewer-availability.csv", kind="reviewer_availability", title="Reviewer and on-call availability", source="oncall_export", media_type=CSV,
                  content=scoped_csv("availability_id,engineer,service_date,session,status,note\n" + "".join(f"{a.availability_id},{engineer_names.get(a.engineer_id, a.engineer_id)},{a.day},{a.session},{a.status},{a.note}\n" for a in scenario.availability),
                                     task_id=scenario.task_id, case_reference=case),
                  preview="Codeowner and on-call availability around the candidate windows."),
        ]
    )
    for doc in scenario.docs:
        if doc.media_type == XLSX:
            assets.append(asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=XLSX, rows=[list(row) for row in doc.rows or ()], preview=doc.title))
        else:
            content = scoped_csv(doc.content, task_id=scenario.task_id, case_reference=case) if doc.kind == "margin_policy" else doc.content
            assets.append(asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=doc.media_type, content=content, preview=doc.title))
    assets.extend(
        quality_support_assets(
            task_id=scenario.task_id, ordinal=scenario.ordinal, case_reference=case, family_slug=FAMILY_SLUG, family_name="RepoDesk",
            organization_name=ORGANIZATION["name"], subject_id=scenario.item, as_of=AS_OF, current_revision=scenario.revision, anchors=OPEN_SOURCE_ANCHORS,
        )
    )
    index = {"case_reference": case, "as_of": AS_OF, "files": [{"path": a["path"], "kind": a["kind"], "media_type": a["media_type"], "sha256": a["sha256"]} for a in assets]}
    assets.append(asset("audit/evidence-index.yaml", kind="evidence_index", title="Evidence index", source="drive", media_type=YAML, content=yaml_lines(index) + "\n", preview="Digest index of every evidence file in the room."))
    for position, record in enumerate(assets, start=1):
        record["asset_id"] = f"{scenario.task_id}-{position:02d}"
    return assets


def _folder(scenario: Scenario, record: dict[str, Any]) -> str:
    if record["kind"] == "policy":
        return "Release Engineering/Playbooks"
    if record["kind"] == "policy_superseded":
        return "Release Engineering/Playbooks/Archive"
    return CASE_FOLDER.format(case=scenario.case_reference)


def mount_drive(scenario: Scenario, assets: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    files: list[dict[str, Any]] = []
    ids: dict[str, str] = {}
    counter = 0
    for record in assets:
        if record["media_type"] == EML or record["kind"] == "chat_thread":
            continue
        counter += 1
        file_id = f"DRV-{scenario.ordinal:03d}-{counter:02d}"
        files.append(
            {"file_id": file_id, "name": record["path"].rsplit("/", 1)[-1], "mime_type": record["media_type"], "modified_time": "2026-05-01T17:30:00", "folder": _folder(scenario, record), "content": record["content"], "sha256": record["sha256"]}
        )
        ids[record["path"]] = file_id
    return files, ids


# --------------------------------------------------------------------------- #
# Decision model
# --------------------------------------------------------------------------- #


def build_facts(scenario: Scenario) -> tuple[dict[str, Any], ...]:
    notes = scenario.fact_notes
    labels = scenario.labels
    numbers = scenario.numbers
    selected = next(option for option in scenario.options if option.recommended)
    unauthorized = next(option for option in scenario.options if option.approval == "ADDITIONAL_APPROVAL_REQUIRED")
    accelerated = scenario.options[1]
    return (
        {
            "id": "authoritative_identity",
            "sources": ["tracker", "scm", "messages"],
            "statement": f"{scenario.case_reference}: {notes['identity']}; the effective revision is {scenario.revision}.",
            "rubric": f"Located {scenario.item} using immutable identifiers and preserved effective revision {scenario.revision}: {notes['identity']}.",
        },
        {
            "id": "effective_requirement",
            "sources": ["tracker", "scm", "success", "drive"],
            "statement": f"The effective issue, impact analysis, and playbook establish {labels.scope_label} = {numbers['scope']} {labels.unit}: {notes['requirement']}. The control date is {scenario.business_need} ({scenario.business_need_reason}).",
            "rubric": f"Applied the effective issue, impact analysis, and playbook to establish {numbers['scope']} {labels.unit} for {labels.scope_label}, with control date {scenario.business_need}.",
        },
        {
            "id": "eligible_coverage",
            "sources": ["ci", "scm", "deploy", "drive"],
            "statement": f"{notes['coverage']}; eligibility requires netting the exclusions rather than trusting a header total.",
            "rubric": f"Reconciled {numbers['observed']} observed less {numbers['excluded']} excluded to {numbers['eligible']} supported {labels.unit} for {labels.eligible_label}.",
        },
        {
            "id": "conditional_external_recovery",
            "sources": ["partners", "messages"],
            "statement": f"{labels.external_label}: {notes['external']}; an external partner confirmation alone proves neither eligibility nor approval.",
            "rubric": f"Used the independently confirmed {scenario.expedited_readiness} expedited readiness input for {accelerated.id}, then separately derived its {accelerated.completion} operating outcome under {labels.constraint_label} instead of treating a partner promise as authorization or a completion date.",
        },
        {
            "id": "finite_capacity",
            "sources": ["deploy", "ci", "drive"],
            "statement": f"{labels.capacity_label}: {notes['capacity']}; protected and blocked windows cannot be displaced.",
            "rubric": f"Applied {labels.capacity_label} to derive the three option outcomes without using protected or blocked windows.",
        },
        {
            "id": "approval_scope",
            "sources": ["approvals", "chat"],
            "statement": f"{notes['approval']}. The approval does not select an option in advance and does not authorize {unauthorized.id}.",
            "rubric": f"Applied {scenario.approval.approval_id} only to {selected.id} and {scenario.item}; kept {unauthorized.id} outside current authority.",
        },
        {
            "id": "business_impact",
            "sources": ["success", "messages", "chat"],
            "statement": f"{notes['impact']}; a faster or broader action has value only if it remains inside {labels.constraint_label}.",
            "rubric": f"Compared all three alternatives and selected {selected.id}: it is the best currently authorized response that satisfies {labels.constraint_label}.",
        },
    )


def build_model(scenario: Scenario) -> dict[str, Any]:
    numbers = scenario.numbers
    inputs = DecisionInputs(
        mode=scenario.mode,
        labels=scenario.labels,
        item=scenario.item,
        record=scenario.item,
        revision=scenario.revision,
        scope=int(numbers["scope"]),
        observed=int(numbers["observed"]),
        excluded=int(numbers["excluded"]),
        eligible=int(numbers["eligible"]),
        gap=int(numbers["gap"]),
        business_need=scenario.business_need,
        standard_readiness=scenario.standard_readiness,
        expedited_readiness=scenario.expedited_readiness,
        options=scenario.options,
        transaction_quantity=int(numbers["transaction_quantity"]) if "transaction_quantity" in numbers else None,
        selected_resource=str(numbers["selected_resource"]) if "selected_resource" in numbers else None,
        extra_answer=dict(scenario.extra_answer),
        extra_descriptions=dict(scenario.extra_descriptions),
        extra_calculations=scenario.extra_calculations,
        facts=build_facts(scenario),
    )
    return build_decision_model(inputs)


# --------------------------------------------------------------------------- #
# Investigations, oracle steps, contract
# --------------------------------------------------------------------------- #


def _investigation(number: int, milestone: str, description: str, tool: str, arguments: dict[str, Any], expected: dict[str, Any], weight: float = 1.0) -> dict[str, Any]:
    return {
        "id": f"investigation_{number:02d}",
        "milestone_id": milestone,
        "description": description,
        "weight": weight,
        "before_primary_mutation": True,
        "any_of": [{"tool": tool, "arguments": arguments, "match": "result_contains", "expected_result_contains": expected}],
    }


def build_investigations(scenario: Scenario, file_ids: dict[str, str]) -> list[dict[str, Any]]:
    case = scenario.case_reference
    component = scenario.component
    issue = scenario.primary_issue
    cls = scenario.primary_class
    playbook_id = file_ids["playbook/release-engineering-playbook.md"]
    approval_id = file_ids[f"approvals/approval-{scenario.approval.approval_id}.json"]
    issue_file_id = file_ids[f"tracker/issue-{issue.key}.json"]
    first_result = next(item for item in scenario.results if item.verification_class == cls.code)
    changes = in_scope_changes(scenario)
    fix_pull = next(pull for pull in scenario.pulls if pull.issue_key == issue.key)
    availability = next(item for item in scenario.availability if item.engineer_id == component.engineer_id)
    if scenario.mode == "quantity":
        issue_list_args = {"verification_class": cls.code, "status": "open"}
        issue_list_expected = {"issues": [{"issue_key": item.key} for _, item in changes]}
        change_args = {"start_date": scenario.numbers["in_scope_window"][0], "end_date": scenario.numbers["in_scope_window"][1], "status": "booked"}
        change_expected = {"changes": [{"id": change.change_id} for change, _ in changes]}
    else:
        issue_list_args = {"component_id": component.component_id}
        issue_list_expected = {"issues": [{"issue_key": issue.key}]}
        own = [change for change in scenario.changes if change.component_id == component.component_id]
        change_args = {"component_id": component.component_id}
        change_expected = {"changes": [{"id": change.change_id} for change in own]} if own else {"total": 0}
    investigations = [
        _investigation(1, "investigation.scope", f"Established the isolated {case} scope, immutable handles, mounted systems, and evidence index before investigating {scenario.item}.", CONTEXT_TOOL, {}, {"reference_records": {"case_reference": case}}),
        _investigation(2, "investigation.scope", f"Located the task-scoped correspondence for {case} by searching the mailbox before opening any message; did not rely on a guessed sender or filename.", "messages.list", {"q": case}, {"messages": [{"id": scenario.email.message_id}]}),
        _investigation(3, "investigation.scope", f"Resolved issue key {issue.key} to the immutable issue record through a key search rather than a title match against a duplicate or superseded issue.", "tracker.issues.search", {"key": issue.key}, {"issues": [{"issue_key": issue.key}]}),
        _investigation(4, "investigation.scope", f"Listed the {case} case folder on the shared drive and identified the approval record and the issue export by immutable file id.", "drive.files.list", {"q": case}, {"files": [{"id": approval_id}, {"id": issue_file_id}]}),
        _investigation(5, "investigation.scope", "Listed the playbook folder and distinguished the effective v5 playbook from the superseded 2024 edition by file identity, not title.", "drive.files.list", {"q": "playbook"}, {"files": [{"id": playbook_id}]}),
        _investigation(6, "investigation.requirements", f"Read the active issue {issue.key}: scope basis, gate class, gated modules, environments in scope, and durations.", "tracker.issues.get", {"issue_key": issue.key}, {"issue_key": issue.key, "status": issue.status}),
        _investigation(7, "investigation.requirements", f"Read the current final impact analysis for {component.component_id} ({component.impact_metric}) and ignored the stale earlier analysis.", "scm.impact.list", {"component_id": component.component_id, "metric": component.impact_metric}, {"impact_reports": [{"report_id": component.impact_id}]}),
        _investigation(8, "investigation.requirements", "Exported the effective v5 playbook for the fix-requirement, usable-evidence, lane-window, and authority rules; did not apply the superseded 2024 edition.", "drive.files.export", {"file_id": playbook_id}, {"file_id": playbook_id}),
        _investigation(9, "investigation.requirements", f"Read the gate class record for {cls.code}: runs per module, required checks, and minimum remaining validity.", "ci.classes.get", {"verification_class": cls.code}, {"verification_class": cls.code}),
        _investigation(10, "investigation.requirements", f"Listed the issues that define the requirement ({', '.join(sorted({item.key for _, item in changes}) if changes else [issue.key])}) and excluded duplicate, superseded, or out-of-scope issues.", "tracker.issues.list", issue_list_args, issue_list_expected),
        _investigation(11, "investigation.requirements", f"Read the run history for {scenario.run_query.get('pipeline_id')} to ground what actually ran, what failed, and what the pipeline does next.", "ci.runs.list", dict(scenario.run_query), dict(scenario.run_expected)),
        _investigation(12, "investigation.constraints", f"Listed every {cls.code} result set with run count, validity, status, and holds before netting the coverage.", "ci.results.list", {"verification_class": cls.code}, {"results": [{"result_id": first_result.result_id}]}),
        _investigation(13, "investigation.constraints", f"Read the lane window calendar for {scenario.windows_query['start_date']} onward to find the first free window that displaces no protected or blocked block.", "deploy.windows.list", dict(scenario.windows_query), {"windows": [{"id": scenario.selected_window_id}]}),
        _investigation(14, "investigation.constraints", f"Read the external certification partner's confirmation {scenario.confirmation.confirmation_id} for the independently confirmed standard and expedited ready dates and the expedite fee.", "partners.confirmations.get", {"confirmation_id": scenario.confirmation.confirmation_id}, {"confirmation_id": scenario.confirmation.confirmation_id, "standard_ready_date": scenario.confirmation.standard_date}),
        _investigation(15, "investigation.authority", f"Read approval {scenario.approval.approval_id} for its exact scope: record, quantity, partner, fee allowance, and what it does not cover.", "approvals.get", {"approval_id": scenario.approval.approval_id}, {"approval_id": scenario.approval.approval_id}),
        _investigation(16, "investigation.authority", "Exported the approval record on the drive and confirmed it matches the workflow record before relying on it.", "drive.files.export", {"file_id": approval_id}, {"file_id": approval_id}),
        _investigation(17, "investigation.erp_correlation", f"Read the request message {scenario.email.message_id} for the documented control date and the business need in the requester's words.", "messages.get", {"message_id": scenario.email.message_id}, {"id": scenario.email.message_id}),
        _investigation(18, "investigation.erp_correlation", f"Read the team chat thread {scenario.chat.thread_id} for evidence, lane, and authority remarks that qualify the system records.", "chat.threads.get", {"thread_id": scenario.chat.thread_id}, {"thread_id": scenario.chat.thread_id}),
        _investigation(19, "investigation.erp_correlation", "Correlated the change records that fix the deploy scope by immutable id.", "deploy.changes.list", change_args, change_expected),
        _investigation(20, "investigation.requirements", f"Read the customer commitment {scenario.commitment.commitment_id} for the contracted control date and the slip penalty in the contract's words.", "success.commitments.get", {"commitment_id": scenario.commitment.commitment_id}, {"commitment_id": scenario.commitment.commitment_id, "cutover_date": scenario.commitment.cutover_date}),
        _investigation(21, "investigation.requirements", f"Read the protected-branch rule for {scenario.branch_rule.repo_id}:{scenario.branch_rule.branch} to confirm the required checks and codeowner review behind the gate class.", "scm.branch_rules.get", {"repo_id": scenario.branch_rule.repo_id, "branch": scenario.branch_rule.branch}, {"rule_id": scenario.branch_rule.rule_id}),
        _investigation(22, "investigation.erp_correlation", f"Correlated the commits on {scenario.commits_query.get('branch')} around the fix range by immutable sha to the modules they touched and their revert, embargo, and backport state.", "scm.commits.list", dict(scenario.commits_query), dict(scenario.commits_expected)),
        _investigation(23, "investigation.erp_correlation", f"Correlated the fix pull request for {issue.key} by immutable number and set the superseded attempt aside.", "scm.pulls.list", {"issue_key": issue.key}, {"pull_requests": [{"pr_id": fix_pull.pr_id}]}),
        _investigation(24, "investigation.constraints", "Read the flaky-test registry to size the quarantined-check retry exposure and to keep quarantined output out of the usable coverage.", "ci.flaky.list", {}, {"flaky_tests": [{"flaky_id": scenario.flaky[0].flaky_id}]}),
        _investigation(25, "investigation.constraints", f"Read runner pool {scenario.pool.pool_id} for its capacity and queue minutes before estimating the verification pipeline duration.", "ci.pools.list", {"pool_id": scenario.pool.pool_id}, {"pools": [{"pool_id": scenario.pool.pool_id}]}),
        _investigation(26, "investigation.constraints", f"Read the reviewer availability calendar for codeowner {component.engineer_id} around the candidate windows; did not assume an expedited-review exception.", "oncall.availability.list", {"start_date": AS_OF, "end_date": business_days()[-1], "engineer_id": component.engineer_id}, {"availability": [{"availability_id": availability.availability_id}]}),
    ]
    investigations.extend(quality_support_investigations(start_number=len(investigations) + 1, file_ids=file_ids, make_investigation=_investigation, case_reference=case, subject_id=scenario.item))
    return investigations


def build_oracle_steps(scenario: Scenario, investigations: list[dict[str, Any]], model: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [{"phase": "context", "tool": CONTEXT_TOOL, "arguments": {}, "control": True}]
    order = [2, 17, 3, 6, 20, 10, 7, 22, 23, 21, 11, 4, 5, 8, 9, 12, 24, 25, 19, 13, 26, 14, 15, 16, 18]
    by_number = {int(item["id"].rsplit("_", 1)[1]): item for item in investigations}
    order.extend(number for number in sorted(by_number) if number not in order)
    for number in order:
        call = by_number[number]["any_of"][0]
        steps.append({"phase": "investigation", "tool": call["tool"], "arguments": call["arguments"], "control": True})
    primary = scenario.primary_write
    steps.append({"phase": "primary_mutation", "tool": primary.tool, "arguments": primary.arguments, "control": False})
    steps.append({"phase": "post_write_verification", "tool": primary.readback_tool, "arguments": primary.readback_arguments, "control": True})
    steps.append(
        {
            "phase": "collaboration",
            "tool": "notes.drafts.create",
            "arguments": {
                "recipient": scenario.collaboration["recipient"],
                "subject": scenario.collaboration["subject"],
                "body": scenario.collaboration["body"],
                "related_issue_key": scenario.primary_issue.key,
                "related_component_id": scenario.component.component_id,
            },
            "control": False,
        }
    )
    steps.append({"phase": "answer", "tool": SUBMIT_TOOL, "arguments": dict(model["answer"]), "control": False})
    return steps


def build_assertions(scenario: Scenario, model: dict[str, Any]) -> list[dict[str, Any]]:
    primary = scenario.primary_write
    task_id = scenario.task_id
    selected = model["selected_option"]
    completion = model["selected_completion"]
    payload_values = ", ".join(f"{key}={value!r}" for key, value in primary.arguments.items())
    return [
        {
            "id": "mutation_01",
            "milestone_id": "state.primary",
            "description": f"Required {scenario.item} to reach business outcome {primary.outcome_label!r} through {primary.tool} with exact provider-critical values {payload_values}. The audited change binds selected option {selected}, approval {scenario.approval.approval_id}, and constraint {scenario.labels.constraint_label}; no other record satisfies this state criterion.",
            "table": "mutations",
            "where": {"task_id": task_id, "mutation_id": f"{task_id}-mutation-01"},
            "values": {"tool": primary.tool, "table_name": primary.table, "record_id": primary.record_id, "status": primary.status},
            "payload_contains": {"tool": primary.tool, "arguments": primary.arguments},
            "payload_allowed_argument_paths": list(primary.allowed_paths),
            "weight": 3.0,
        },
        {
            "id": "state_01",
            "milestone_id": "state.primary",
            "description": f"Persisted {primary.record_id} in {primary.table} with the supported values ({', '.join(f'{k}={v!r}' for k, v in primary.domain_values.items())}) so a later reader sees the change, not just the acknowledgement.",
            "table": primary.table,
            "where": {PRIMARY_KEYS[primary.table]: primary.record_id},
            "values": dict(primary.domain_values),
            "weight": 2.0,
        },
        *[dict(item) for item in primary.extra_assertions],
        {
            "id": "mutation_02",
            "milestone_id": "state.collaboration",
            "description": f"Created — but did not send — the stakeholder draft carrying {selected}, the {completion} outcome, the binding constraint, and the {scenario.case_reference} business reference.",
            "table": "mutations",
            "where": {"task_id": task_id, "mutation_id": f"{task_id}-mutation-02"},
            "values": {"tool": "notes.drafts.create", "table_name": "note_drafts", "status": "DRAFT"},
            "payload_contains": {"tool": "notes.drafts.create", "arguments": {"recipient": scenario.collaboration["recipient"]}},
            "payload_text_contains": [selected, completion],
            "payload_text_any_of": [[scenario.case_reference, scenario.component.code, scenario.primary_issue.key]],
            "weight": 1.5,
        },
        {
            "id": "containment_01",
            "milestone_id": "containment.scope",
            "description": f"Made exactly two state changes for {scenario.case_reference}: the primary change and the stakeholder draft; no additional order, backport, flag change, or booking.",
            "table": "mutations",
            "where": {"task_id": task_id},
            "count": 2,
            "weight": 1.0,
        },
    ]


@fact_text_contract
def build_task(scenario: Scenario) -> dict[str, Any]:
    verify_numbers(scenario)
    assets = build_assets(scenario)
    drive_files, file_ids = mount_drive(scenario, assets)
    evidence = [
        {"asset_id": a["asset_id"], "task_id": scenario.task_id, "path": a["path"], "title": a["title"], "kind": a["kind"], "source": a["source"], "media_type": a["media_type"], "sha256": a["sha256"]}
        for a in assets
    ]
    model = build_model(scenario)
    investigations = build_investigations(scenario, file_ids)
    steps = build_oracle_steps(scenario, investigations, model)
    assertions = build_assertions(scenario, model)
    primary = scenario.primary_write
    readback = {
        "id": "verify_primary_state",
        "milestone_id": "verification.readback",
        "after_tool": primary.tool,
        "any_of": [{"tool": primary.readback_tool, "arguments": primary.readback_arguments, "match": "result_contains", "expected_result_contains": primary.readback_expected}],
        "expected_result_contains": primary.readback_expected,
        "target_identity": primary.readback_arguments,
        "materializes_new_record": primary.tool.endswith(".create"),
        "description": f"Read {primary.record_id} back through {primary.readback_tool} after the change and confirmed the persisted provider values ({', '.join(f'{k}={v!r}' for k, v in primary.readback_expected.items())}) rather than relying on the write acknowledgement.",
        "weight": 2.0,
    }
    answer = model["answer"]
    checks = answer_checks(
        answer,
        ["recommended_option", "recommended_outcome_date", ITEM_FIELD[scenario.mode], GAP_FIELD[scenario.mode], "decision_timing_status"],
        f"{scenario.item}, revision {scenario.revision}, and the selected {model['selected_option']} outcome",
    )
    descriptions = milestone_descriptions(
        case_reference=scenario.case_reference,
        record=scenario.item,
        revision=scenario.revision,
        subject=scenario.labels.subject,
        selected_option=model["selected_option"],
        selected_completion=model["selected_completion"],
        facts=model["facts"],
        primary_outcome=primary.outcome_label,
        correlated_systems=CORRELATED_SYSTEMS,
    )
    rubric = build_rubric_milestones(descriptions=descriptions, investigations=investigations, calculations=model["calculations"], assertions=assertions, answer_checks=checks, post_write_verifications=[readback])
    option_ids = [option["id"] for option in model["options"]]
    decoy_path = scenario.decoy_doc.path
    return {
        "task_id": scenario.task_id,
        "benchmark": BENCHMARK,
        "family": FAMILY_SLUG,
        "benchmark_version": FAMILY_VERSION,
        "mode": scenario.mode,
        "level": "employee-decision",
        "title": scenario.title,
        "role": scenario.role,
        "instruction": scenario.instruction,
        "as_of": AS_OF,
        "world": dict(ORGANIZATION),
        "seed_tables": seed_tables(scenario, drive_files, evidence),
        "assets": assets,
        "decision_model": {key: value for key, value in model.items() if key not in {"answer", "answer_descriptions"}},
        "answer_schema": answer_schema(answer, model["answer_descriptions"], option_ids),
        "expected": {
            "answer": answer,
            "answer_checks": checks,
            "calculations": model["calculations"],
            "assertions": assertions,
            "investigations": investigations,
            "post_write_verifications": [readback],
        },
        "required_investigations": investigations,
        "required_reads": [step["tool"] for step in steps if step["control"] and step["phase"] in {"context", "investigation"}],
        "required_read_calls": [item["any_of"][0] for item in investigations],
        "post_write_verifications": [readback],
        "oracle_steps": steps,
        "sequence_signature": sequence_signature(steps),
        "allowed_write_tables": sorted({primary.table, *primary.extra_tables, "note_drafts", "mutations", "answers", "audit_log"}),
        "rubric_milestones": rubric,
        "negative_controls": {
            "unauthorized_write": dict(scenario.unauthorized_write),
            "wrong_evidence": {"tool": "drive.files.export", "arguments": {"file_id": file_ids[decoy_path]}},
        },
        "reference_records": {
            "case_reference": scenario.case_reference,
            "tracker": {"issue_key": scenario.primary_issue.key, "issue_search": {"tool": "tracker.issues.search", "arguments": {"key": scenario.primary_issue.key}}},
            "scm": {"repo_id": scenario.component.repo_id, "component_code": scenario.component.code, "branch": scenario.commits_query.get("branch"), "fix_pull_request": next(pull.pr_id for pull in scenario.pulls if pull.issue_key == scenario.primary_issue.key)},
            "messages": {"search_query": scenario.case_reference},
            "drive": {"case_folder_query": scenario.case_reference, "playbook_query": "playbook"},
            "ci": {"verification_class": scenario.primary_class.code, "sources": sorted({item.source_id for item in scenario.results}), "pipeline_id": scenario.run_query.get("pipeline_id"), "pool_id": scenario.pool.pool_id},
            "deploy": {"lanes": [lane.lane_id for lane in scenario.lanes], "calendar_window": scenario.windows_query},
            "success": {"customer_id": scenario.customer.customer_id, "commitment_id": scenario.commitment.commitment_id},
            "partners": {"confirmation_id": scenario.confirmation.confirmation_id},
            "approvals": {"approval_id": scenario.approval.approval_id},
            "chat": {"thread_id": scenario.chat.thread_id},
        },
        "starting_records": [
            *[{"system": "deploy", "resource_type": "ChangeRecord", "resource_id": c.change_id, "status": c.status} for c in scenario.changes],
            {"system": "partners", "resource_type": "CertificationOrder", "resource_id": "ORD-3400", "status": "RECEIVED"},
            *[{"system": "scm", "resource_type": "BackportRequest", "resource_id": row["backport_id"], "status": row["status"]} for row in scenario.seed.get("backports", ())],
        ],
        "evaluation": {"metric": "HubScore", "strict_pass": "every rubric milestone passes", "llm_judge_calls": 0},
        "workflow": {"reads": len([s for s in steps if s["phase"] in {"context", "investigation"}]), "writes": 2, "readbacks": 1, "answer_fields": len(answer)},
    }


def build_tasks() -> list[dict[str, Any]]:
    return [build_task(scenario) for scenario in scenarios()]


__all__ = ["BENCHMARK", "FAMILY_SLUG", "FAMILY_VERSION", "build_task", "build_tasks", "calendar", "first_window_on_or_after", "verify_numbers"]
