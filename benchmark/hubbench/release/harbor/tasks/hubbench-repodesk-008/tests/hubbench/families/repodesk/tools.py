"""RepoDesk provider-shaped tools over the family's SQLite world.

Read tools return GitHub-shaped repository records, Jira-shaped issues, CI
evidence-register and pipeline records, deploy-lane calendars and change
records, customer commitments, certification-partner confirmations, and
reviewer availability; write tools persist to the domain tables, refresh the
affected records, and record the exact payload for the sealed contract.
There is no LLM anywhere here.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from ...engine.families import ToolSpec
from ...engine.validation import integer, obj, string
from ...engine.world import World

RUN_UNIT = "CHECK_RUN"
COMMIT_UNIT = "COMMIT"


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #


def _component(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "component_id": row["component_id"],
        "code": row["code"],
        "name": row["name"],
        "tier": row["tier"],
        "owner_team": row["owner_team"],
        "repository": f"Repository/{row['repo_id']}",
        "primary_engineer": f"Engineer/{row['primary_engineer_id']}" if row.get("primary_engineer_id") else None,
    }


def _impact(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_id": row["report_id"],
        "component": f"Component/{row['component_id']}",
        "metric": row["metric"],
        "value": row["value"],
        "unit": row["unit"],
        "generated_at": row["generated_at"],
        "status": row["status"],
    }


def _issue(row: dict[str, Any], cls: dict[str, Any]) -> dict[str, Any]:
    return {
        "issue_key": row["issue_key"],
        "title": row["title"],
        "status": row["status"],
        "severity": row["severity"],
        "kind": row["kind"],
        "component": f"Component/{row['component_id']}",
        "verification_class": {"code": row["verification_class"], "display": cls["display"], "runs_per_module": cls["runs_per_module"]},
        "basis": row["basis"],
        "fixed_modules": row["fixed_modules"],
        "gated_modules": row["gated_modules"],
        "environments_in_scope": row["environments_in_scope"],
        "scope_note": row["scope_note"],
        "build_minutes": row["build_minutes"],
        "bake_minutes": row["bake_minutes"],
        "customer": f"Customer/{row['customer_id']}" if row.get("customer_id") else None,
        "commitment": f"Commitment/{row['commitment_id']}" if row.get("commitment_id") else None,
        "regression_range": {"from": row.get("regression_from"), "to": row.get("regression_to")},
        "opened_at": row["opened_at"],
        "requested_by": f"Engineer/{row['requested_by']}",
        "duplicate_of": row.get("duplicate_of"),
        "fix_version": row.get("fix_version"),
        "note": row.get("note") or "",
    }


def _change(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["change_id"],
        "status": row["status"],
        "description": row.get("description"),
        "start": row.get("start_time"),
        "end": row.get("end_time"),
        "lane": row.get("lane_id"),
        "component": f"Component/{row['component_id']}",
        "issue": f"Issue/{row['issue_key']}" if row.get("issue_key") else None,
        "meta": {"versionId": str(row["revision"]), "lastUpdated": row["last_updated"]},
    }


def _window(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["window_id"],
        "lane": row["lane_id"],
        "serviceDate": row["service_date"],
        "session": row["session"],
        "start": f"{row['service_date']}T{row['start_time']}",
        "end": f"{row['service_date']}T{row['end_time']}",
        "status": row["status"],
        "holdReason": row.get("hold_reason"),
        "change": row.get("change_id"),
    }


def _run(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "pipeline": f"Pipeline/{row['pipeline_id']}",
        "head_sha": row.get("head_sha"),
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "status": row["status"],
        "exit_code": row["exit_code"],
        "summary": row["summary"],
    }


def _commit(world: World, row: dict[str, Any]) -> dict[str, Any]:
    modules = [item["module_id"] for item in world.all("SELECT module_id FROM commit_modules WHERE sha = ? ORDER BY module_id", (row["sha"],))]
    return {
        "sha": row["sha"],
        "repository": f"Repository/{row['repo_id']}",
        "branch": row["branch"],
        "authored_at": row["authored_at"],
        "author": f"Engineer/{row['author_id']}" if row.get("author_id") else None,
        "message": row["message"],
        "pull_request_number": row.get("pr_number"),
        "status": row["status"],
        "backported_to": row.get("backported_to"),
        "fix_for": row.get("fix_for"),
        "touched_modules": modules,
    }


def _pull(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "pr_id": row["pr_id"],
        "number": row["number"],
        "title": row["title"],
        "repository": f"Repository/{row['repo_id']}",
        "head_sha": row["head_sha"],
        "base_branch": row["base_branch"],
        "status": row["status"],
        "issue": f"Issue/{row['issue_key']}" if row.get("issue_key") else None,
        "author": f"Engineer/{row['author_id']}" if row.get("author_id") else None,
        "opened_at": row["opened_at"],
        "superseded_by": row.get("superseded_by"),
    }


def _classes_by_code(world: World) -> dict[str, dict[str, Any]]:
    return {row["verification_class"]: row for row in world.all("SELECT * FROM verification_classes")}


# --------------------------------------------------------------------------- #
# SCM reads
# --------------------------------------------------------------------------- #


def repos_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM repositories WHERE repo_id = ?", (args["repo_id"],), missing=f"Repository/{args['repo_id']} not found"))


def components_search(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("identifier"):
        rows = world.all("SELECT * FROM components WHERE code = ? ORDER BY component_id", (args["identifier"],))
    elif args.get("name"):
        rows = world.all("SELECT * FROM components WHERE instr(lower(name), lower(?)) > 0 OR instr(lower(code), lower(?)) > 0 ORDER BY component_id", (args["name"], args["name"]))
    else:
        raise ValueError("identifier or name is required")
    return {"total": len(rows), "components": [_component(row) for row in rows]}


def components_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _component(world.one("SELECT * FROM components WHERE component_id = ?", (args["component_id"],), missing=f"Component/{args['component_id']} not found"))


def impact_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT component_id FROM components WHERE component_id = ?", (args["component_id"],), missing=f"Component/{args['component_id']} not found")
    if args.get("metric"):
        rows = world.all("SELECT * FROM impact_reports WHERE component_id = ? AND metric = ? ORDER BY generated_at DESC, report_id", (args["component_id"], args["metric"]))
    else:
        rows = world.all("SELECT * FROM impact_reports WHERE component_id = ? ORDER BY generated_at DESC, report_id", (args["component_id"],))
    return {"total": len(rows), "impact_reports": [_impact(row) for row in rows]}


def modules_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("component_id", "verification_class", "repo_id"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    if not clauses:
        raise ValueError("at least one of component_id, verification_class, repo_id is required")
    rows = world.all(f"SELECT * FROM modules WHERE {' AND '.join(clauses)} ORDER BY module_id", params)
    return {"total": len(rows), "modules": rows}


def modules_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM modules WHERE module_id = ?", (args["module_id"],), missing=f"Module/{args['module_id']} not found")
    owner = world.one("SELECT * FROM engineers WHERE engineer_id = ?", (row["codeowner_id"],), missing="codeowner not found") if row.get("codeowner_id") else None
    return {**row, "codeowner": {"engineer_id": owner["engineer_id"], "name": owner["name"]} if owner else None}


def commits_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = ["repo_id = ?"], [args["repo_id"]]
    if args.get("branch"):
        clauses.append("branch = ?")
        params.append(args["branch"])
    if args.get("issue_key"):
        clauses.append("fix_for = ?")
        params.append(args["issue_key"])
    if args.get("since"):
        clauses.append("substr(authored_at, 1, 10) >= ?")
        params.append(args["since"])
    if args.get("until"):
        clauses.append("substr(authored_at, 1, 10) <= ?")
        params.append(args["until"])
    rows = world.all(f"SELECT * FROM commits WHERE {' AND '.join(clauses)} ORDER BY authored_at, sha", params)
    return {"total": len(rows), "commits": [_commit(world, row) for row in rows]}


def commits_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _commit(world, world.one("SELECT * FROM commits WHERE sha = ?", (args["sha"],), missing=f"Commit/{args['sha']} not found"))


def pulls_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("repo_id", "issue_key", "status", "base_branch"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    if not clauses:
        raise ValueError("at least one of repo_id, issue_key, status, base_branch is required")
    rows = world.all(f"SELECT * FROM pull_requests WHERE {' AND '.join(clauses)} ORDER BY number", params)
    return {"total": len(rows), "pull_requests": [_pull(row) for row in rows]}


def pulls_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _pull(world.one("SELECT * FROM pull_requests WHERE pr_id = ?", (args["pr_id"],), missing=f"PullRequest/{args['pr_id']} not found"))


def reviews_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT pr_id FROM pull_requests WHERE pr_id = ?", (args["pr_id"],), missing=f"PullRequest/{args['pr_id']} not found")
    rows = world.all("SELECT * FROM reviews WHERE pr_id = ? ORDER BY submitted_at, review_id", (args["pr_id"],))
    return {"total": len(rows), "reviews": rows}


def branch_rules_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM branch_rules WHERE repo_id = ? AND branch = ?", (args["repo_id"], args["branch"]), missing=f"no protected-branch rule for {args['repo_id']}:{args['branch']}")
    return {**row, "required_checks": json.loads(row["required_checks_json"])}


def backports_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM backport_requests WHERE backport_id = ?", (args["backport_id"],), missing=f"backport {args['backport_id']} not found"))


def eligible_commits(world: World, repo_id: str, from_ref: str, to_ref: str) -> int:
    row = world.one(
        "SELECT COUNT(*) AS quantity FROM commits WHERE repo_id = ? AND branch = ? AND status = 'merged' AND (backported_to IS NULL OR backported_to != ?)",
        (repo_id, from_ref, to_ref),
    )
    return int(row["quantity"])


def backports_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "scm.backports.create"
    world.one("SELECT repo_id FROM repositories WHERE repo_id = ?", (args["repo_id"],), missing=f"Repository/{args['repo_id']} not found")
    if args["from_ref"] == args["to_ref"]:
        raise ValueError("a backport needs two different refs")
    date.fromisoformat(args["scheduled_date"])
    eligible = eligible_commits(world, args["repo_id"], args["from_ref"], args["to_ref"])
    if args["commit_count"] > eligible:
        raise ValueError(f"{args['from_ref']} holds only {eligible} eligible {COMMIT_UNIT} for {args['to_ref']}; reverted, embargoed, docs-only, and already-backported commits cannot ride a backport")
    backport_id = world.next_id("backport_requests", "backport_id", "BPR-")
    row = {
        "backport_id": backport_id,
        "repo_id": args["repo_id"],
        "from_ref": args["from_ref"],
        "to_ref": args["to_ref"],
        "commit_count": args["commit_count"],
        "unit": COMMIT_UNIT,
        "scheduled_date": args["scheduled_date"],
        "status": "SCHEDULED",
        "requested_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO backport_requests (backport_id, repo_id, from_ref, to_ref, commit_count, unit, scheduled_date, status, requested_by, created_at, revision) "
        "VALUES (:backport_id, :repo_id, :from_ref, :to_ref, :commit_count, :unit, :scheduled_date, :status, :requested_by, :created_at, :revision)",
        row,
    )
    world.audit(tool, "backport_requests", backport_id, "insert", row)
    world.record_mutation(tool, "backport_requests", backport_id, "SCHEDULED", args)
    return dict(row)


# --------------------------------------------------------------------------- #
# Issue tracker
# --------------------------------------------------------------------------- #


def issues_search(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("key"):
        rows = world.all("SELECT * FROM issues WHERE issue_key = ? ORDER BY issue_key", (args["key"],))
    elif args.get("text"):
        rows = world.all("SELECT * FROM issues WHERE instr(lower(title), lower(?)) > 0 OR instr(lower(scope_note), lower(?)) > 0 ORDER BY issue_key", (args["text"], args["text"]))
    else:
        raise ValueError("key or text is required")
    classes = _classes_by_code(world)
    return {"total": len(rows), "issues": [_issue(row, classes[row["verification_class"]]) for row in rows]}


def issues_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM issues WHERE issue_key = ?", (args["issue_key"],), missing=f"Issue/{args['issue_key']} not found")
    return _issue(row, _classes_by_code(world)[row["verification_class"]])


def issues_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("component_id", "verification_class", "status", "customer_id", "kind"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    if not clauses:
        raise ValueError("at least one of component_id, verification_class, status, customer_id, kind is required")
    rows = world.all(f"SELECT * FROM issues WHERE {' AND '.join(clauses)} ORDER BY issue_key", params)
    classes = _classes_by_code(world)
    return {"total": len(rows), "issues": [_issue(row, classes[row["verification_class"]]) for row in rows]}


def issues_update(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "tracker.issues.update"
    current = world.one("SELECT * FROM issues WHERE issue_key = ?", (args["issue_key"],), missing=f"Issue/{args['issue_key']} not found")
    if current["status"] in {"closed", "duplicate", "superseded"}:
        raise ValueError(f"Issue/{args['issue_key']} is {current['status']} and cannot be transitioned")
    changes = {key: args[key] for key in ("status", "fix_version") if key in args}
    if not changes:
        raise ValueError("no change requested")
    updated = {**current, **changes}
    world.connection.execute("UPDATE issues SET status = :status, fix_version = :fix_version WHERE issue_key = :issue_key", updated)
    world.audit(tool, "issues", current["issue_key"], "update", changes)
    world.record_mutation(tool, "issues", current["issue_key"], updated["status"], args)
    return _issue(updated, _classes_by_code(world)[updated["verification_class"]])


# --------------------------------------------------------------------------- #
# CI evidence register, pipelines, flaky tests, coverage, runner pools
# --------------------------------------------------------------------------- #


def classes_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM verification_classes WHERE verification_class = ?", (args["verification_class"],), missing=f"verification class {args['verification_class']} not found")
    return {**row, "required_checks": json.loads(row["required_checks_json"])}


def results_summary(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("verification_class", "source_id"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = world.all(
        f"SELECT verification_class, source_id, SUM(run_count) AS run_count, COUNT(*) AS result_sets FROM verification_results {where} "
        "GROUP BY verification_class, source_id ORDER BY verification_class, source_id",
        params,
    )
    return {"balances": rows, "note": "Gross registered runs including failed, quarantined, held, and expiring result sets; see ci.results.list for set status."}


def results_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = ["verification_class = ?"], [args["verification_class"]]
    for key in ("source_id", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    rows = world.all(f"SELECT * FROM verification_results WHERE {' AND '.join(clauses)} ORDER BY valid_until, result_id", params)
    return {"verification_class": args["verification_class"], "results": rows}


def pipelines_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("component_id", "kind", "repo_id"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"pipelines": world.all(f"SELECT * FROM pipelines {where} ORDER BY pipeline_id", params)}


def pipelines_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM pipelines WHERE pipeline_id = ?", (args["pipeline_id"],), missing=f"Pipeline/{args['pipeline_id']} not found"))


def runs_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("pipeline_id", "status", "head_sha"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    if args.get("start_date"):
        clauses.append("substr(started_at, 1, 10) >= ?")
        params.append(args["start_date"])
    if args.get("end_date"):
        clauses.append("substr(started_at, 1, 10) <= ?")
        params.append(args["end_date"])
    if not clauses:
        raise ValueError("at least one filter is required")
    rows = world.all(f"SELECT * FROM pipeline_runs WHERE {' AND '.join(clauses)} ORDER BY started_at, run_id", params)
    return {"total": len(rows), "runs": [_run(row) for row in rows]}


def runs_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _run(world.one("SELECT * FROM pipeline_runs WHERE run_id = ?", (args["run_id"],), missing=f"PipelineRun/{args['run_id']} not found"))


def flaky_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("module_id", "status", "check_name"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = world.all(f"SELECT * FROM flaky_tests {where} ORDER BY flaky_id", params)
    return {"total": len(rows), "flaky_tests": rows}


def coverage_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    rows = world.all("SELECT * FROM coverage_reports WHERE module_id = ? ORDER BY generated_at DESC, report_id", (args["module_id"],))
    if not rows:
        raise ValueError(f"no coverage report for Module/{args['module_id']}")
    return {"module_id": args["module_id"], "reports": rows}


def pools_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("pool_id"):
        rows = world.all("SELECT * FROM runner_pools WHERE pool_id = ? ORDER BY pool_id", (args["pool_id"],))
    else:
        rows = world.all("SELECT * FROM runner_pools ORDER BY pool_id")
    return {"pools": rows}


# --------------------------------------------------------------------------- #
# Deploy pipeline: lanes, windows, change records, feature flags
# --------------------------------------------------------------------------- #


def lanes_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("cluster"):
        rows = world.all("SELECT * FROM lanes WHERE cluster = ? ORDER BY lane_id", (args["cluster"],))
    else:
        rows = world.all("SELECT * FROM lanes ORDER BY lane_id")
    return {"lanes": rows}


def windows_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses = ["service_date >= ?", "service_date <= ?"]
    params: list[Any] = [args["start_date"], args["end_date"]]
    if args.get("lane_id"):
        clauses.append("lane_id = ?")
        params.append(args["lane_id"])
    if args.get("status"):
        clauses.append("status = ?")
        params.append(args["status"])
    rows = world.all(f"SELECT * FROM release_windows WHERE {' AND '.join(clauses)} ORDER BY service_date, lane_id, session DESC", params)
    return {"windows": [_window(row) for row in rows]}


def changes_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("issue_key", "lane_id", "status", "component_id"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    if args.get("start_date"):
        clauses.append("substr(start_time, 1, 10) >= ?")
        params.append(args["start_date"])
    if args.get("end_date"):
        clauses.append("substr(start_time, 1, 10) <= ?")
        params.append(args["end_date"])
    if not clauses:
        raise ValueError("at least one filter is required")
    rows = world.all(f"SELECT * FROM change_records WHERE {' AND '.join(clauses)} ORDER BY start_time, change_id", params)
    return {"total": len(rows), "changes": [_change(row) for row in rows]}


def changes_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _change(world.one("SELECT * FROM change_records WHERE change_id = ?", (args["change_id"],), missing=f"Change/{args['change_id']} not found"))


def _split_datetime(value: str, label: str) -> tuple[str, str]:
    if len(value) != 19 or value[10] != "T":
        raise ValueError(f"{label} must be YYYY-MM-DDTHH:MM:SS")
    date.fromisoformat(value[:10])
    return value[:10], value[11:]


def _windows_for_interval(world: World, lane_id: str, start: str, end: str) -> list[dict[str, Any]]:
    start_date, start_time = _split_datetime(start, "start_time")
    end_date, end_time = _split_datetime(end, "end_time")
    if start_date != end_date:
        raise ValueError("a change must start and end on the same service date")
    if start_time >= end_time:
        raise ValueError("start_time must precede end_time")
    rows = world.all("SELECT * FROM release_windows WHERE lane_id = ? AND service_date = ? ORDER BY start_time", (lane_id, start_date))
    covering = [row for row in rows if row["start_time"] < end_time and row["end_time"] > start_time]
    if not covering:
        raise ValueError(f"no {lane_id} window covers {start} - {end}")
    if start_time < min(row["start_time"] for row in covering) or end_time > max(row["end_time"] for row in covering):
        raise ValueError(f"{start} - {end} falls outside the {lane_id} release windows")
    return covering


def _require_free(windows: list[dict[str, Any]], *, holder: str | None = None) -> None:
    for row in windows:
        if row["status"] == "free":
            continue
        if holder and row.get("change_id") == holder:
            continue
        raise ValueError(f"{row['window_id']} is {row['status']}: {row.get('hold_reason') or 'not available'}; protected and blocked windows cannot be displaced")


def _claim(world: World, tool: str, windows: list[dict[str, Any]], change_id: str) -> None:
    for row in windows:
        world.connection.execute("UPDATE release_windows SET status = 'busy', hold_reason = 'change booked', change_id = ? WHERE window_id = ?", (change_id, row["window_id"]))
        world.audit(tool, "release_windows", row["window_id"], "update", {"status": "busy", "change_id": change_id})


def _release(world: World, tool: str, change_id: str) -> None:
    for row in world.all("SELECT window_id FROM release_windows WHERE change_id = ?", (change_id,)):
        world.connection.execute("UPDATE release_windows SET status = 'free', hold_reason = NULL, change_id = NULL WHERE window_id = ?", (row["window_id"],))
        world.audit(tool, "release_windows", row["window_id"], "update", {"status": "free", "change_id": None})


def changes_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "deploy.changes.create"
    issue = world.one("SELECT * FROM issues WHERE issue_key = ?", (args["issue_key"],), missing=f"Issue/{args['issue_key']} not found")
    if issue["status"] not in {"open", "active"}:
        raise ValueError(f"Issue/{args['issue_key']} is {issue['status']} and cannot be booked")
    lane = world.one("SELECT * FROM lanes WHERE lane_id = ?", (args["lane_id"],), missing=f"lane {args['lane_id']} not found")
    if lane["status"] != "ACTIVE":
        raise ValueError(f"{args['lane_id']} is {lane['status']}: {lane.get('status_note') or ''}".strip())
    windows = _windows_for_interval(world, args["lane_id"], args["start_time"], args["end_time"])
    _require_free(windows)
    change_id = world.next_id("change_records", "change_id", "CHG-")
    row = {
        "change_id": change_id,
        "component_id": issue["component_id"],
        "issue_key": args["issue_key"],
        "lane_id": args["lane_id"],
        "start_time": args["start_time"],
        "end_time": args["end_time"],
        "status": "booked",
        "description": args.get("description"),
        "revision": 1,
        "last_updated": world.clock(),
    }
    world.connection.execute(
        "INSERT INTO change_records (change_id, component_id, issue_key, lane_id, start_time, end_time, status, description, revision, last_updated) "
        "VALUES (:change_id, :component_id, :issue_key, :lane_id, :start_time, :end_time, :status, :description, :revision, :last_updated)",
        row,
    )
    world.audit(tool, "change_records", change_id, "insert", row)
    _claim(world, tool, windows, change_id)
    world.record_mutation(tool, "change_records", change_id, "booked", args)
    return _change(row)


def changes_update(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "deploy.changes.update"
    current = world.one("SELECT * FROM change_records WHERE change_id = ?", (args["change_id"],), missing=f"Change/{args['change_id']} not found")
    if current["status"] in {"cancelled", "deployed"}:
        raise ValueError(f"Change/{args['change_id']} is {current['status']} and cannot be changed")
    changes = {key: args[key] for key in ("lane_id", "start_time", "end_time", "status", "description") if key in args}
    if not changes:
        raise ValueError("no change requested")
    updated = {**current, **changes}
    new_status = updated["status"]
    if new_status == "cancelled":
        _release(world, tool, current["change_id"])
    else:
        if any(key in changes for key in ("lane_id", "start_time", "end_time")) or current["status"] != "booked":
            if not (updated.get("lane_id") and updated.get("start_time") and updated.get("end_time")):
                raise ValueError("booking a change needs lane_id, start_time, and end_time")
            lane = world.one("SELECT * FROM lanes WHERE lane_id = ?", (updated["lane_id"],), missing=f"lane {updated['lane_id']} not found")
            if lane["status"] != "ACTIVE":
                raise ValueError(f"{updated['lane_id']} is {lane['status']}: {lane.get('status_note') or ''}".strip())
            windows = _windows_for_interval(world, updated["lane_id"], updated["start_time"], updated["end_time"])
            _require_free(windows, holder=current["change_id"])
            _release(world, tool, current["change_id"])
            _claim(world, tool, windows, current["change_id"])
            if new_status not in {"booked", "pending"}:
                raise ValueError(f"unsupported status transition to {new_status}")
    updated["revision"] = int(current["revision"]) + 1
    updated["last_updated"] = world.clock()
    world.connection.execute(
        "UPDATE change_records SET lane_id = :lane_id, start_time = :start_time, end_time = :end_time, status = :status, description = :description, revision = :revision, last_updated = :last_updated WHERE change_id = :change_id",
        updated,
    )
    world.audit(tool, "change_records", current["change_id"], "update", changes)
    world.record_mutation(tool, "change_records", current["change_id"], new_status, args, revision=updated["revision"])
    return _change(updated)


def flags_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    rows = world.all("SELECT * FROM feature_flags WHERE flag_key = ? ORDER BY environment_id", (args["flag_key"],))
    if not rows:
        raise ValueError(f"flag {args['flag_key']} not found")
    return {"flag_key": args["flag_key"], "environments": rows}


def flags_update(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "deploy.flags.update"
    current = world.one(
        "SELECT * FROM feature_flags WHERE flag_key = ? AND environment_id = ?",
        (args["flag_key"], args["environment_id"]),
        missing=f"flag {args['flag_key']} is not configured for {args['environment_id']}",
    )
    protected = world.all(
        "SELECT window_id FROM release_windows WHERE status = 'protected' AND service_date = ? AND instr(lower(COALESCE(hold_reason, '')), 'blackout') > 0",
        (world.as_of.isoformat(),),
    )
    if protected and args["state"] != "off":
        raise ValueError(f"{args['environment_id']} is inside a customer blackout on {world.as_of.isoformat()}; flag changes other than a kill switch need the change advisory board")
    updated = {**current, "state": args["state"], "scope": args.get("scope", current["scope"]), "revision": int(current["revision"]) + 1, "last_updated": world.clock()}
    world.connection.execute(
        "UPDATE feature_flags SET state = :state, scope = :scope, revision = :revision, last_updated = :last_updated WHERE flag_key = :flag_key AND environment_id = :environment_id",
        updated,
    )
    world.audit(tool, "feature_flags", f"{args['flag_key']}@{args['environment_id']}", "update", {"state": args["state"], "scope": updated["scope"]})
    world.record_mutation(tool, "feature_flags", f"{args['flag_key']}@{args['environment_id']}", args["state"], args, revision=updated["revision"])
    return dict(updated)


# --------------------------------------------------------------------------- #
# Customer success, certification partners, reviewer availability
# --------------------------------------------------------------------------- #


def customers_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM customers WHERE customer_id = ?", (args["customer_id"],), missing=f"Customer/{args['customer_id']} not found"))


def commitments_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("customer_id", "issue_key", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    if not clauses:
        raise ValueError("at least one of customer_id, issue_key, status is required")
    return {"commitments": world.all(f"SELECT * FROM commitments WHERE {' AND '.join(clauses)} ORDER BY cutover_date, commitment_id", params)}


def commitments_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM commitments WHERE commitment_id = ?", (args["commitment_id"],), missing=f"Commitment/{args['commitment_id']} not found")
    customer = world.one("SELECT * FROM customers WHERE customer_id = ?", (row["customer_id"],))
    return {**row, "customer_name": customer["name"], "customer_tier": customer["tier"]}


def confirmations_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("verification_class", "partner_id", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"confirmations": world.all(f"SELECT * FROM partner_confirmations {where} ORDER BY confirmation_id", params)}


def confirmations_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM partner_confirmations WHERE confirmation_id = ?", (args["confirmation_id"],), missing=f"confirmation {args['confirmation_id']} not found")
    partner = world.one("SELECT * FROM partners WHERE partner_id = ?", (row["partner_id"],))
    return {**row, "partner_name": partner["name"]}


def orders_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("status", "verification_class", "partner_id"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"orders": world.all(f"SELECT * FROM certification_orders {where} ORDER BY order_id", params)}


def orders_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM certification_orders WHERE order_id = ?", (args["order_id"],), missing=f"certification order {args['order_id']} not found"))


def orders_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "partners.orders.create"
    partner = world.one("SELECT * FROM partners WHERE partner_id = ?", (args["partner_id"],), missing=f"partner {args['partner_id']} not found")
    world.one("SELECT verification_class FROM verification_classes WHERE verification_class = ?", (args["verification_class"],), missing=f"verification class {args['verification_class']} not found")
    confirmation = world.one(
        "SELECT * FROM partner_confirmations WHERE confirmation_id = ?",
        (args["confirmation_id"],),
        missing=f"confirmation {args['confirmation_id']} not found",
    )
    if confirmation["partner_id"] != partner["partner_id"] or confirmation["verification_class"] != args["verification_class"]:
        raise ValueError(f"confirmation {args['confirmation_id']} does not cover {args['verification_class']} from {args['partner_id']}")
    if confirmation["status"] != "OPEN":
        raise ValueError(f"confirmation {args['confirmation_id']} is {confirmation['status']}")
    if args["run_count"] > confirmation["runs_available"]:
        raise ValueError(f"confirmation {args['confirmation_id']} covers at most {confirmation['runs_available']} {RUN_UNIT}")
    expected = confirmation["standard_ready_date"] if args["service_option"] == "standard" else confirmation["expedited_ready_date"]
    order_id = world.next_id("certification_orders", "order_id", "ORD-")
    row = {
        "order_id": order_id,
        "partner_id": partner["partner_id"],
        "confirmation_id": confirmation["confirmation_id"],
        "verification_class": args["verification_class"],
        "run_count": args["run_count"],
        "unit": RUN_UNIT,
        "service_option": args["service_option"],
        "expected_ready_date": expected,
        "status": "SUBMITTED",
        "requested_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO certification_orders (order_id, partner_id, confirmation_id, verification_class, run_count, unit, service_option, expected_ready_date, status, requested_by, created_at, revision) "
        "VALUES (:order_id, :partner_id, :confirmation_id, :verification_class, :run_count, :unit, :service_option, :expected_ready_date, :status, :requested_by, :created_at, :revision)",
        row,
    )
    world.audit(tool, "certification_orders", order_id, "insert", row)
    world.record_mutation(tool, "certification_orders", order_id, "SUBMITTED", args)
    return dict(row)


def availability_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses = ["service_date >= ?", "service_date <= ?"]
    params: list[Any] = [args["start_date"], args["end_date"]]
    if args.get("engineer_id"):
        clauses.append("engineer_id = ?")
        params.append(args["engineer_id"])
    if args.get("status"):
        clauses.append("status = ?")
        params.append(args["status"])
    rows = world.all(f"SELECT * FROM reviewer_availability WHERE {' AND '.join(clauses)} ORDER BY service_date, engineer_id, session DESC", params)
    return {"total": len(rows), "availability": rows}


# --------------------------------------------------------------------------- #
# Approvals and collaboration surfaces
# --------------------------------------------------------------------------- #


def approvals_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("q"):
        rows = world.all("SELECT * FROM approvals WHERE instr(lower(subject), lower(?)) > 0 OR instr(lower(scope_json), lower(?)) > 0 ORDER BY approval_id", (args["q"], args["q"]))
    else:
        rows = world.all("SELECT * FROM approvals ORDER BY approval_id")
    return {"approvals": [{**row, "scope": json.loads(row["scope_json"])} for row in rows]}


def approvals_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM approvals WHERE approval_id = ?", (args["approval_id"],), missing=f"approval {args['approval_id']} not found")
    approver = world.one("SELECT * FROM users WHERE user_id = ?", (row["approver_id"],), missing="approver not found")
    return {**row, "scope": json.loads(row["scope_json"]), "approver": {"user_id": approver["user_id"], "display_name": approver["display_name"], "role": approver["role"]}}


def messages_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    query = args["q"].strip().strip('"')
    rows = world.all(
        "SELECT message_id, thread_id, channel, sender, subject, sent_at, labels FROM messages WHERE instr(subject, ?) > 0 OR instr(body, ?) > 0 OR instr(labels, ?) > 0 ORDER BY sent_at, message_id",
        (query, query, query),
    )
    limit = int(args.get("max_results", 20))
    return {"messages": [{"id": row["message_id"], "thread_id": row["thread_id"], "channel": row["channel"], "from": row["sender"], "subject": row["subject"], "sent_at": row["sent_at"], "labels": row["labels"]} for row in rows[:limit]]}


def messages_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM messages WHERE message_id = ?", (args["message_id"],), missing=f"message {args['message_id']} not found")
    return {
        "id": row["message_id"],
        "thread_id": row["thread_id"],
        "channel": row["channel"],
        "from": row["sender"],
        "to": row["recipients"],
        "subject": row["subject"],
        "sent_at": row["sent_at"],
        "body": row["body"],
        "attachments": json.loads(row["attachments_json"]),
        "labels": row["labels"],
    }


def chat_threads_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    query = args["q"].strip().strip('"')
    rows = world.all("SELECT thread_id, channel, title FROM chat_threads WHERE instr(title, ?) > 0 OR instr(messages_json, ?) > 0 ORDER BY thread_id", (query, query))
    return {"threads": rows}


def chat_threads_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM chat_threads WHERE thread_id = ?", (args["thread_id"],), missing=f"thread {args['thread_id']} not found")
    return {"thread_id": row["thread_id"], "channel": row["channel"], "title": row["title"], "messages": json.loads(row["messages_json"])}


def drive_files_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    query = args["q"].strip().strip('"')
    rows = world.all(
        "SELECT file_id, name, mime_type, modified_time, folder FROM drive_files WHERE instr(name, ?) > 0 OR instr(folder, ?) > 0 OR instr(content, ?) > 0 ORDER BY folder, name",
        (query, query, query),
    )
    return {"files": [{"id": row["file_id"], "name": row["name"], "mimeType": row["mime_type"], "modifiedTime": row["modified_time"], "folder": row["folder"]} for row in rows]}


def drive_files_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT file_id, name, mime_type, modified_time, folder, sha256 FROM drive_files WHERE file_id = ?", (args["file_id"],), missing=f"file {args['file_id']} not found")
    return {"id": row["file_id"], "name": row["name"], "mimeType": row["mime_type"], "modifiedTime": row["modified_time"], "folder": row["folder"], "sha256": row["sha256"]}


def drive_files_export(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM drive_files WHERE file_id = ?", (args["file_id"],), missing=f"file {args['file_id']} not found")
    return {"file_id": row["file_id"], "name": row["name"], "mime_type": row["mime_type"], "content": row["content"]}


def drafts_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "notes.drafts.create"
    if not args["recipient"].strip() or not args["body"].strip():
        raise ValueError("recipient and body are required")
    draft_id = world.next_id("note_drafts", "draft_id", "DRAFT-")
    row = {
        "draft_id": draft_id,
        "recipient": args["recipient"],
        "subject": args["subject"],
        "body": args["body"],
        "related_issue_key": args.get("related_issue_key"),
        "related_component_id": args.get("related_component_id"),
        "created_at": world.clock(),
        "status": "DRAFT",
    }
    world.connection.execute(
        "INSERT INTO note_drafts (draft_id, recipient, subject, body, related_issue_key, related_component_id, created_at, status) "
        "VALUES (:draft_id, :recipient, :subject, :body, :related_issue_key, :related_component_id, :created_at, :status)",
        row,
    )
    world.audit(tool, "note_drafts", draft_id, "insert", row)
    world.record_mutation(tool, "note_drafts", draft_id, "DRAFT", args)
    return dict(row)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

DATETIME = "ISO local date-time, YYYY-MM-DDTHH:MM:SS"

TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec("scm.repos.get", "Read one repository record: name, default branch, visibility.", obj({"repo_id": string()}, ["repo_id"]), "read", repos_get, "repository record"),
    ToolSpec("scm.components.search", "Search deployable components by immutable component code or by name.", obj({"identifier": string("component code"), "name": string("name fragment")}), "read", components_search, "component search"),
    ToolSpec("scm.components.get", "Read one component record by id.", obj({"component_id": string()}, ["component_id"]), "read", components_get, "component record"),
    ToolSpec("scm.impact.list", "List impact analyses for a component, optionally by metric (TOUCHED-MODULES, DATASET-GB), newest first.", obj({"component_id": string(), "metric": string("metric code")}, ["component_id"]), "read", impact_list, "impact analysis register"),
    ToolSpec("scm.modules.list", "List modules (path, codeowner, gate class, revert / flag gate) by component, gate class, or repository.", obj({"component_id": string(), "verification_class": string(), "repo_id": string()}), "read", modules_list, "module registry"),
    ToolSpec("scm.modules.get", "Read one module with its codeowner.", obj({"module_id": string()}, ["module_id"]), "read", modules_get, "module record"),
    ToolSpec("scm.commits.list", "List commits on a repository branch by date range or fix issue, with the modules each commit touched.", obj({"repo_id": string(), "branch": string(), "issue_key": string(), "since": string("ISO date"), "until": string("ISO date")}, ["repo_id"]), "read", commits_list, "commit history"),
    ToolSpec("scm.commits.get", "Read one commit with its touched modules.", obj({"sha": string()}, ["sha"]), "read", commits_get, "commit record"),
    ToolSpec("scm.pulls.list", "List pull requests by repository, fix issue, status, or base branch.", obj({"repo_id": string(), "issue_key": string(), "status": string(), "base_branch": string()}), "read", pulls_list, "pull request search"),
    ToolSpec("scm.pulls.get", "Read one pull request.", obj({"pr_id": string()}, ["pr_id"]), "read", pulls_get, "pull request record"),
    ToolSpec("scm.reviews.list", "List the reviews on one pull request.", obj({"pr_id": string()}, ["pr_id"]), "read", reviews_list, "pull request reviews"),
    ToolSpec("scm.branch_rules.get", "Read the protected-branch rule for a repository branch: required checks, approvals, codeowner review.", obj({"repo_id": string(), "branch": string()}, ["repo_id", "branch"]), "read", branch_rules_get, "protected-branch rule"),
    ToolSpec("scm.backports.get", "Read one backport request.", obj({"backport_id": string()}, ["backport_id"]), "read", backports_get, "backport request"),
    ToolSpec(
        "scm.backports.create",
        "Schedule a backport of commits from one ref to another on the merge queue. Only eligible commits (merged, not reverted, not embargoed, not docs-only, not already on the target) may ride.",
        obj(
            {"repo_id": string(), "from_ref": string(), "to_ref": string(), "commit_count": integer(minimum=1), "scheduled_date": string("ISO date")},
            ["repo_id", "from_ref", "to_ref", "commit_count", "scheduled_date"],
        ),
        "write",
        backports_create,
        "backport request",
        idempotent=False,
    ),
    ToolSpec("tracker.issues.search", "Search issues by immutable key or by text.", obj({"key": string("issue key"), "text": string("text fragment")}), "read", issues_search, "issue search"),
    ToolSpec("tracker.issues.get", "Read one issue with its gate class, scope basis, environments in scope, customer commitment, and durations.", obj({"issue_key": string()}, ["issue_key"]), "read", issues_get, "issue record"),
    ToolSpec("tracker.issues.list", "List issues by component, gate class, status, customer, or kind.", obj({"component_id": string(), "verification_class": string(), "status": string(), "customer_id": string(), "kind": string()}), "read", issues_list, "issue search"),
    ToolSpec(
        "tracker.issues.update",
        "Transition an issue or set its fix version. Closed, duplicate, and superseded issues cannot be transitioned.",
        obj({"issue_key": string(), "status": {"type": "string", "enum": ["open", "active", "in_review", "resolved"]}, "fix_version": string()}, ["issue_key"]),
        "write",
        issues_update,
        "issue transition",
        idempotent=False,
    ),
    ToolSpec("ci.classes.get", "Read a gate class: runs per module, required checks, evidence tier, and minimum remaining validity.", obj({"verification_class": string()}, ["verification_class"]), "read", classes_get, "gate class record"),
    ToolSpec("ci.results.summary", "Gross registered run balances by gate class and source (no netting of status, hold, or validity).", obj({"verification_class": string(), "source_id": string()}), "read", results_summary, "evidence register balance"),
    ToolSpec("ci.results.list", "List verification-result sets for a gate class with run count, validity, status, and holds.", obj({"verification_class": string(), "source_id": string(), "status": string()}, ["verification_class"]), "read", results_list, "evidence register"),
    ToolSpec("ci.pipelines.list", "List pipelines, optionally by component, kind, or repository.", obj({"component_id": string(), "kind": string(), "repo_id": string()}), "read", pipelines_list, "pipeline list"),
    ToolSpec("ci.pipelines.get", "Read one pipeline definition with its base duration.", obj({"pipeline_id": string()}, ["pipeline_id"]), "read", pipelines_get, "pipeline record"),
    ToolSpec("ci.runs.list", "List pipeline runs by pipeline, status, head sha, or start-date window.", obj({"pipeline_id": string(), "status": string(), "head_sha": string(), "start_date": string("ISO date"), "end_date": string("ISO date")}), "read", runs_list, "pipeline run history"),
    ToolSpec("ci.runs.get", "Read one pipeline run with exit code and summary.", obj({"run_id": string()}, ["run_id"]), "read", runs_get, "pipeline run record"),
    ToolSpec("ci.flaky.list", "List the flaky-test registry, optionally by module, status, or check.", obj({"module_id": string(), "status": string(), "check_name": string()}), "read", flaky_list, "flaky-test registry"),
    ToolSpec("ci.coverage.get", "Read the coverage reports for a module, newest first.", obj({"module_id": string()}, ["module_id"]), "read", coverage_get, "coverage report"),
    ToolSpec("ci.pools.list", "List runner pools with capacity, queue time, and status.", obj({"pool_id": string()}), "read", pools_list, "runner pool capacity"),
    ToolSpec("deploy.lanes.list", "List release lanes with status and tenant-isolation capability.", obj({"cluster": string()}), "read", lanes_list, "release lane roster"),
    ToolSpec("deploy.windows.list", "List lane release windows between two dates with free / busy / protected / blocked status.", obj({"start_date": string("ISO date"), "end_date": string("ISO date"), "lane_id": string(), "status": string()}, ["start_date", "end_date"]), "read", windows_list, "release window calendar"),
    ToolSpec("deploy.changes.list", "List change records by issue, lane, component, status, or date window.", obj({"issue_key": string(), "lane_id": string(), "component_id": string(), "status": string(), "start_date": string("ISO date"), "end_date": string("ISO date")}), "read", changes_list, "change record search"),
    ToolSpec("deploy.changes.get", "Read one change record.", obj({"change_id": string()}, ["change_id"]), "read", changes_get, "change record"),
    ToolSpec(
        "deploy.changes.create",
        "Book a change record for an issue on a release lane. Every window the interval touches must be free; protected and blocked windows are never displaced.",
        obj(
            {"issue_key": string(), "lane_id": string(), "start_time": string(DATETIME), "end_time": string(DATETIME), "description": string()},
            ["issue_key", "lane_id", "start_time", "end_time"],
        ),
        "write",
        changes_create,
        "change record create",
        idempotent=False,
    ),
    ToolSpec(
        "deploy.changes.update",
        "Move, book, or cancel an existing change record. Moving re-validates the target windows; the record revision increments.",
        obj(
            {"change_id": string(), "lane_id": string(), "start_time": string(DATETIME), "end_time": string(DATETIME), "status": {"type": "string", "enum": ["booked", "pending", "cancelled"]}, "description": string()},
            ["change_id"],
        ),
        "write",
        changes_update,
        "change record update",
        idempotent=False,
    ),
    ToolSpec("deploy.flags.get", "Read a feature flag's state per environment.", obj({"flag_key": string()}, ["flag_key"]), "read", flags_get, "feature flag"),
    ToolSpec(
        "deploy.flags.update",
        "Set a feature flag's state for one environment. Inside a customer blackout only a kill switch (off) is allowed.",
        obj({"flag_key": string(), "environment_id": string(), "state": {"type": "string", "enum": ["on", "off", "cohort"]}, "scope": string()}, ["flag_key", "environment_id", "state"]),
        "write",
        flags_update,
        "feature flag update",
        idempotent=False,
    ),
    ToolSpec("success.customers.get", "Read one customer account with its environment and tier.", obj({"customer_id": string()}, ["customer_id"]), "read", customers_get, "customer account"),
    ToolSpec("success.commitments.list", "List contracted commitments (cutover dates, penalties) by customer, issue, or status.", obj({"customer_id": string(), "issue_key": string(), "status": string()}), "read", commitments_list, "customer commitment search"),
    ToolSpec("success.commitments.get", "Read one contracted commitment: cutover date, penalty, contract reference.", obj({"commitment_id": string()}, ["commitment_id"]), "read", commitments_get, "customer commitment"),
    ToolSpec("partners.confirmations.list", "List external certification confirmations.", obj({"verification_class": string(), "partner_id": string(), "status": string()}), "read", confirmations_list, "certification confirmation"),
    ToolSpec("partners.confirmations.get", "Read one certification confirmation: runs, standard and expedited ready dates, fee, validity.", obj({"confirmation_id": string()}, ["confirmation_id"]), "read", confirmations_get, "certification confirmation"),
    ToolSpec("partners.orders.list", "List certification orders.", obj({"status": string(), "verification_class": string(), "partner_id": string()}), "read", orders_list, "certification order"),
    ToolSpec("partners.orders.get", "Read one certification order.", obj({"order_id": string()}, ["order_id"]), "read", orders_get, "certification order"),
    ToolSpec(
        "partners.orders.create",
        "Order certified check runs against an open partner confirmation. The expected ready date is taken from the confirmation for the chosen service option.",
        obj(
            {
                "partner_id": string(),
                "confirmation_id": string(),
                "verification_class": string(),
                "run_count": integer(minimum=1),
                "service_option": {"type": "string", "enum": ["standard", "expedited"]},
            },
            ["partner_id", "confirmation_id", "verification_class", "run_count", "service_option"],
        ),
        "write",
        orders_create,
        "certification order",
        idempotent=False,
    ),
    ToolSpec("oncall.availability.list", "List reviewer and on-call availability between two dates, optionally for one engineer.", obj({"start_date": string("ISO date"), "end_date": string("ISO date"), "engineer_id": string(), "status": string()}, ["start_date", "end_date"]), "read", availability_list, "reviewer availability calendar"),
    ToolSpec("approvals.list", "List approval records, optionally by keyword.", obj({"q": string()}), "read", approvals_list, "approval workflow record"),
    ToolSpec("approvals.get", "Read one approval record with its exact scope and approver.", obj({"approval_id": string()}, ["approval_id"]), "read", approvals_get, "approval workflow record"),
    ToolSpec("messages.list", "Search release-engineering mail by keyword (subject, body, labels).", obj({"q": string(), "max_results": integer(minimum=1)}, ["q"]), "read", messages_list, "mailbox search"),
    ToolSpec("messages.get", "Read one message with body and attachment list.", obj({"message_id": string()}, ["message_id"]), "read", messages_get, "mailbox message"),
    ToolSpec("chat.threads.list", "Search team chat threads by keyword.", obj({"q": string()}, ["q"]), "read", chat_threads_list, "team chat search"),
    ToolSpec("chat.threads.get", "Read one team chat thread.", obj({"thread_id": string()}, ["thread_id"]), "read", chat_threads_get, "team chat thread"),
    ToolSpec("drive.files.list", "Search shared-drive files by keyword (name, folder, content).", obj({"q": string()}, ["q"]), "read", drive_files_list, "shared drive search"),
    ToolSpec("drive.files.get", "Read shared-drive file metadata.", obj({"file_id": string()}, ["file_id"]), "read", drive_files_get, "shared drive file"),
    ToolSpec("drive.files.export", "Export a shared-drive file as text (spreadsheets as CSV, PDFs as extracted text).", obj({"file_id": string()}, ["file_id"]), "read", drive_files_export, "shared drive export"),
    ToolSpec(
        "notes.drafts.create",
        "Create, but do not send, a stakeholder draft note.",
        obj({"recipient": string(), "subject": string(), "body": string(), "related_issue_key": string(), "related_component_id": string()}, ["recipient", "subject", "body"]),
        "write",
        drafts_create,
        "collaboration draft",
        idempotent=False,
    ),
)

SERVERS = {
    "scm": "Source control: repositories, components, impact analyses, modules with codeowners and gates, commits, pull requests, reviews, protected-branch rules, and backport requests.",
    "tracker": "Issue tracker: regressions and remediation issues with gate class, scope basis, customer links, and durations.",
    "ci": "CI service: gate classes, the verification-evidence register, pipelines and run history, the flaky-test registry, coverage reports, and runner pools.",
    "deploy": "Deploy pipeline: release lanes, the lane window calendar, change records, and feature flags.",
    "success": "Customer success: customer accounts and contracted commitments (cutover dates, penalties).",
    "partners": "External certification partners: confirmations and certification orders.",
    "oncall": "Reviewer and on-call availability calendar.",
    "approvals": "Approval workflow records with exact scope.",
    "messages": "Release-engineering mailbox.",
    "chat": "Release-engineering chat threads.",
    "drive": "Shared drive holding the playbook, registers, calendars, and exports.",
    "notes": "Stakeholder draft notes (never sent by the benchmark).",
}

__all__ = ["SERVERS", "TOOLS", "eligible_commits"]
