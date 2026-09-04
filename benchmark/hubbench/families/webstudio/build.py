"""Assemble WebStudio tasks: seed tables, scattered evidence, decision model, sealed contract.

Every declared number in a scenario is recomputed from the seeded world
(licence grants, consumer registry, CMS entries, deploy-window calendar,
change requests, vendor quotes) and the build fails on any disagreement, so
the answer contract can never drift from the data the agent actually sees.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from ...engine.assets import CSV, EML, JSON, MARKDOWN, PDF, XLSX, YAML, asset, eml, yaml_lines
from ...engine.catalog import answer_checks, build_rubric_milestones, milestone_descriptions, sequence_signature
from ...engine.decision import DecisionInputs, answer_schema, build_decision_model
from ...engine.families import CONTEXT_TOOL, SUBMIT_TOOL
from ...engine.grading_contracts import fact_text_contract
from ...engine.quality_assets import quality_support_assets, quality_support_investigations, scoped_csv, scoped_markdown
from . import tools as web_tools
from .policy import SUPERSEDED_PLAYBOOK, effective_playbook
from .scenarios import scenarios
from .specs import (
    AS_OF,
    PEOPLE,
    ORGANIZATION,
    USERS,
    VENDORS,
    WINDOW_HOURS,
    WINDOW_TIMES,
    ChangeRequest,
    Licence,
    Page,
    Scenario,
    business_days,
    next_business_day,
    renewal_horizon,
    window_id,
)

BENCHMARK = "HubBench"
FAMILY_SLUG = "webstudio"
FAMILY_VERSION = "1.0.1"
PRIMARY_KEYS = {"releases": "release_id", "licence_requests": "request_id", "token_pins": "pin_id"}
ITEM_FIELD = {"plan": "coverage_item_or_resource", "quantity": "controlled_item_or_record", "schedule": "affected_resource_or_operation"}
GAP_FIELD = {"plan": "shortage_quantity", "quantity": "transaction_quantity", "schedule": "capacity_gap"}
CASE_FOLDER = "Web Studio/Cases/{case}"
OPEN_SOURCE_ANCHORS = (
    {
        "name": "WebGen-Bench",
        "harbor_dataset": "webgen-bench/webgen-bench",
        "harbor_url": "https://hub.harborframework.com/datasets/webgen-bench/webgen-bench/latest",
        "upstream_url": "https://github.com/mnluzimu/WebGen-Bench",
        "license": "per the upstream repository",
        "evaluation_shape": "website generation from a brief with functional and appearance verification",
    },
    {
        "name": "Open Design",
        "harbor_dataset": "open-design/open-design",
        "harbor_url": "https://hub.harborframework.com/datasets/open-design/open-design/latest",
        "upstream_url": "https://hub.harborframework.com/datasets/open-design/open-design/latest",
        "license": "per the Harbor dataset listing",
        "evaluation_shape": "product-surface design tasks with verifiable output",
    },
    {
        "name": "Vector Edit Gym",
        "harbor_dataset": "thetalab/vector-edit-gym",
        "harbor_url": "https://hub.harborframework.com/datasets/thetalab/vector-edit-gym/latest",
        "upstream_url": "https://hub.harborframework.com/datasets/thetalab/vector-edit-gym/latest",
        "license": "per the Harbor dataset listing",
        "evaluation_shape": "vector design edits checked against a reference rendering",
    },
)
PLAN_SELECTED_OPTIONS = {"standard_licence_plan": "standard", "expedite_licence_issuance": "expedited"}
BREAKING_PREFIXES = ("token:", "component:")


# --------------------------------------------------------------------------- #
# Derivations and cross-checks
# --------------------------------------------------------------------------- #


def _pages(scenario: Scenario) -> tuple[Page, ...]:
    return (scenario.page, *scenario.other_pages)


def _crs_by_id(scenario: Scenario) -> dict[str, ChangeRequest]:
    return {cr.cr_id: cr for cr in scenario.change_requests}


def entries_of(scenario: Scenario, cr_id: str) -> list[Any]:
    return [entry for entry in scenario.entries if entry.cr_id == cr_id]


def in_scope_releases(scenario: Scenario) -> list[Any]:
    """Scheduled releases inside the in-scope window whose change request binds the primary item."""

    window = scenario.numbers.get("in_scope_window")
    if not window:
        return []
    selected = []
    for release in scenario.releases:
        if release.status != "scheduled" or release.start is None or release.cr_id is None:
            continue
        if not window[0] <= release.start[:10] <= window[1]:
            continue
        if any(scenario.item in (entry.bound_asset_id, entry.bound_token_id) for entry in entries_of(scenario, release.cr_id)):
            selected.append(release)
    return sorted(selected, key=lambda item: (item.start, item.release_id))


def launch_territories(scenario: Scenario) -> set[str]:
    if scenario.numbers.get("coverage_basis") == "licence_union":
        crs = _crs_by_id(scenario)
        union: set[str] = set()
        for release in in_scope_releases(scenario):
            union |= set(crs[release.cr_id].territories)
        return union
    return set(scenario.primary_cr.territories)


def _licence_excluded(item: Licence) -> bool:
    return (
        item.status != "ACTIVE"
        or item.reserved_for is not None
        or item.usage_scope != "web"
        or item.register_excluded
        or item.expires_on <= renewal_horizon()
    )


def scoped_licences(scenario: Scenario, launch: set[str]) -> list[Licence]:
    return [item for item in scenario.licences if item.asset_id == scenario.primary_asset.asset_id and set(item.territories) <= launch]


def licensable_assets_in_scope(scenario: Scenario) -> set[str]:
    licensable = {item.asset_id for item in scenario.assets if item.licence_required}
    return {entry.bound_asset_id for entry in entries_of(scenario, scenario.primary_cr.cr_id) if entry.bound_asset_id in licensable}


def consumers_of(scenario: Scenario, token_id: str) -> list[Any]:
    return [item for item in scenario.consumers if item.token_id == token_id]


def calendar(scenario: Scenario) -> dict[tuple[str, str, str], dict[str, Any]]:
    overrides = {(item.day, item.lane, item.session): item for item in scenario.windows}
    grid: dict[tuple[str, str, str], dict[str, Any]] = {}
    for day in business_days():
        for lane in scenario.lanes:
            for session in ("AM", "PM"):
                key = (day, lane.lane_id, session)
                override = overrides.get(key)
                if override is None:
                    entry = {"status": "busy", "hold_reason": "rolling deploy train", "release_id": None}
                elif override.status == "busy" and override.reason.startswith("REL-"):
                    entry = {"status": "busy", "hold_reason": "scheduled release", "release_id": override.reason}
                elif override.status == "free":
                    entry = {"status": "free", "hold_reason": None, "release_id": None}
                else:
                    entry = {"status": override.status, "hold_reason": override.reason or override.status, "release_id": None}
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


def _session_of(start: str) -> str:
    return "AM" if start[11:] < WINDOW_TIMES["PM"][0] else "PM"


def _page_weight_headroom(scenario: Scenario) -> Any:
    budget = next(item for item in scenario.budgets if item.page_id == scenario.page.page_id and item.metric == "page_weight_kb")
    value = budget.budget_value - budget.measured_value
    return int(value) if float(value).is_integer() else round(value, 2)


def verify_numbers(scenario: Scenario) -> None:
    numbers = scenario.numbers
    extra = scenario.extra_answer
    basis = numbers["coverage_basis"]
    problems: list[str] = []

    def check(label: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            problems.append(f"{label}: computed {actual!r} but scenario declares {expected!r}")

    def intish(value: float) -> Any:
        return int(value) if float(value).is_integer() else value

    selected = next(option for option in scenario.options if option.recommended)
    primary_cr = scenario.primary_cr
    if primary_cr.status != "open":
        problems.append(f"primary change request {primary_cr.cr_id} is {primary_cr.status}")
    if scenario.approved_frame.file_id != scenario.current_design_file.file_id:
        problems.append("approved frame is not on the current design file")

    if basis in {"licence", "licence_union"}:
        launch = launch_territories(scenario)
        scoped = scoped_licences(scenario, launch)
        observed = sum(item.territory_count for item in scoped)
        excluded = sum(item.territory_count for item in scoped if _licence_excluded(item))
        check("observed", observed, numbers["observed"])
        check("excluded", excluded, numbers["excluded"])
        check("eligible", observed - excluded, numbers["eligible"])
        if "pending_countersign_territories" in extra:
            check("pending_countersign_territories", sum(item.territory_count for item in scoped if item.status == "PENDING_COUNTERSIGN"), extra["pending_countersign_territories"])
    if basis == "licence":
        assets = licensable_assets_in_scope(scenario)
        check("assets_in_scope", len(assets), numbers["assets_in_scope"])
        check("licensed_assets_in_scope", len(assets), extra["licensed_assets_in_scope"])
        check("launch_territory_count", len(set(primary_cr.territories)), extra["launch_territory_count"])
        check("scope", len(set(primary_cr.territories)) * numbers["assets_in_scope"], numbers["scope"])
    if basis == "licence_union":
        releases = in_scope_releases(scenario)
        launch = launch_territories(scenario)
        check("scope", len(launch), numbers["scope"])
        check("scheduled_releases", len(releases), extra["scheduled_releases"])
        check("transaction_quantity", numbers["gap"] + numbers["margin"], numbers["transaction_quantity"])
        check("margin_territories", numbers["margin"], extra["margin_territories"])
        check("renewal_horizon_date", renewal_horizon(), extra["renewal_horizon_date"])
        check("per_territory_fee_usd", intish(scenario.quote.per_unit_fee), extra["per_territory_fee_usd"])
    if basis == "consumer":
        rows = consumers_of(scenario, scenario.primary_token.token_id)
        on_page = [item for item in rows if item.page_id == primary_cr.page_id and item.status == "ACTIVE"]
        deprecated = [item for item in rows if item.status == "DEPRECATED"]
        migrated = [item for item in rows if item.status == "MIGRATED"]
        excluded = [item for item in rows if item.status != "ACTIVE" or item.page_id == primary_cr.page_id]
        check("scope", primary_cr.impact_consumers, numbers["scope"])
        check("observed", len(rows), numbers["observed"])
        check("excluded", len(excluded), numbers["excluded"])
        check("eligible", len(rows) - len(excluded), numbers["eligible"])
        check("transaction_quantity", len(rows) - len(excluded), numbers["transaction_quantity"])
        check("on_page_consumers", len(on_page), extra["on_page_consumers"])
        check("deprecated_consumers", len(deprecated), extra["deprecated_consumers"])
        check("migrated_consumers", len(migrated), extra["migrated_consumers"])
        check("token_current_version", scenario.primary_token.current.version, extra["token_current_version"])
        proposed = scenario.primary_token.proposed
        check("token_proposed_version", proposed.version if proposed else None, extra["token_proposed_version"])
        if proposed is None or not proposed.breaking:
            problems.append("consumer basis needs a proposed breaking token version")
        check("pin version", scenario.primary_token.current.version, scenario.primary_write.arguments["version"])
    if basis == "entry":
        rows = entries_of(scenario, primary_cr.cr_id)
        reviewed = [item for item in rows if item.status == "REVIEWED"]
        blocked = [item for item in reviewed if item.blocked_reason]
        check("scope", primary_cr.entries_in_scope, numbers["scope"])
        check("entries listed", len(rows), numbers["scope"])
        check("observed", len(reviewed), numbers["observed"])
        check("excluded", len(blocked), numbers["excluded"])
        check("eligible", len(reviewed) - len(blocked), numbers["eligible"])
        check("transaction_quantity", len(reviewed) - len(blocked), numbers["transaction_quantity"])
        check("entry_count", numbers["transaction_quantity"], scenario.primary_write.arguments.get("entry_count"))
        check("draft_entries", sum(1 for item in rows if item.status == "DRAFT"), extra["draft_entries"])
        check("entries_blocked_by_breaking_changes", sum(1 for item in blocked if item.blocked_reason.startswith(BREAKING_PREFIXES)), extra["entries_blocked_by_breaking_changes"])
        check("entries_blocked_by_licence", sum(1 for item in blocked if item.blocked_reason.startswith("licence:")), extra["entries_blocked_by_licence"])
    if basis in {"licence_union", "consumer"}:
        releases = in_scope_releases(scenario)
        first = releases[0]
        check("first_release_window", f"{first.lane_id}/{first.start[:10]}/{_session_of(first.start)}", extra["first_release_window"])
        check("business_need", first.start[:10], scenario.business_need)
        # The licence plan completes when the standard issuance registers; the pin completes with the scheduled release.
        check("selected completion", scenario.standard_readiness if basis == "licence_union" else first.start[:10], selected.completion)
    if basis == "entry":
        slot = first_window_on_or_after(scenario, numbers["earliest_start"], 1, numbers["eligible_lanes"])
        check("first_release_window", f"{slot[1]}/{slot[0]}/{slot[2]}" if slot else None, extra["first_release_window"])
        check("selected completion", slot[0] if slot else None, selected.completion)
    if basis == "capacity":
        grid = calendar(scenario)
        start, end = numbers["capacity_window"]
        days = [day for day in business_days() if start <= day <= end]
        keys = [(day, lane, session) for day in days for lane in numbers["eligible_lanes"] for session in ("AM", "PM")]
        candidate = len(keys) * WINDOW_HOURS
        free_count = sum(1 for key in keys if grid[key]["status"] == "free")
        check("candidate", candidate, numbers["observed"])
        check("excluded", candidate - free_count * WINDOW_HOURS, numbers["excluded"])
        check("eligible", free_count * WINDOW_HOURS, numbers["eligible"])
        if numbers.get("scope_source") == "primary":
            hours = (primary_cr.deploy_minutes + primary_cr.verify_minutes) / 60
            affected_crs = [primary_cr]
        else:
            stranded = {lane.lane_id for lane in scenario.lanes if lane.status != "ACTIVE"}
            affected_releases = [release for release in scenario.releases if release.lane_id in stranded and release.status == "scheduled"]
            crs = _crs_by_id(scenario)
            affected_crs = [crs[release.cr_id] for release in affected_releases]
            hours = sum((cr.deploy_minutes + cr.verify_minutes) / 60 for cr in affected_crs)
            if "affected_releases" in extra:
                check("affected_releases", len(affected_releases), extra["affected_releases"])
            if "stranded_lane" in extra:
                check("stranded_lane", sorted(stranded)[0] if stranded else None, extra["stranded_lane"])
            if "releases_per_window" in extra:
                check("releases_per_window", len(affected_releases) // int(numbers["sessions_needed"]), extra["releases_per_window"])
        check("scope", int(hours), numbers["scope"])
        if "windows_required" in extra:
            check("windows_required", int(numbers["sessions_needed"]), extra["windows_required"])
        if "requested_day" in extra:
            check("requested_day", start, extra["requested_day"])
        if "snapshot_capable_lanes" in extra:
            check("snapshot_capable_lanes", sum(1 for lane in scenario.lanes if lane.rollback_capable), extra["snapshot_capable_lanes"])
        if "protected_windows_in_week" in extra:
            check("protected_windows_in_week", sum(1 for key in keys if grid[key]["status"] == "protected"), extra["protected_windows_in_week"])
        selected_date = selected.completion
        if numbers.get("full_day_needed"):
            full_day = first_window_on_or_after(scenario, start, 2, numbers["eligible_lanes"])
            check("selected_resource", f"{full_day[1]}/{full_day[0]}/{full_day[2]}" if full_day else None, numbers["selected_resource"])
            check("selected completion", full_day[0] if full_day else None, selected_date)
        else:
            free_windows = [key for key in sorted(grid) if key[1] in numbers["eligible_lanes"] and grid[key]["status"] == "free" and key[0] >= start]
            check("selected_resource", f"{free_windows[0][1]}/{free_windows[0][0]}/{free_windows[0][2]}" if free_windows else None, numbers["selected_resource"])
            sessions_needed = int(numbers["sessions_needed"])
            check("selected completion", free_windows[sessions_needed - 1][0] if len(free_windows) >= sessions_needed else None, selected_date)

    if "token_consumers_active" in extra:
        check("token_consumers_active", sum(1 for item in consumers_of(scenario, scenario.primary_token.token_id) if item.status == "ACTIVE"), extra["token_consumers_active"])
    if "token_consumers_deprecated" in extra:
        check("token_consumers_deprecated", sum(1 for item in consumers_of(scenario, scenario.primary_token.token_id) if item.status == "DEPRECATED"), extra["token_consumers_deprecated"])
    if "checklist_gates_failed" in extra:
        check("checklist_gates_failed", sum(1 for gate in scenario.gates if gate.cr_id == primary_cr.cr_id and gate.status == "FAILED"), extra["checklist_gates_failed"])
    if "perf_budget_headroom_kb" in extra:
        check("perf_budget_headroom_kb", _page_weight_headroom(scenario), extra["perf_budget_headroom_kb"])

    gap = max(0, numbers["scope"] - numbers["eligible"])
    check("gap", gap, numbers["gap"])
    check("standard_readiness", next_business_day(scenario.quote.standard_date), scenario.standard_readiness)
    check("expedited_readiness", next_business_day(scenario.quote.expedited_date), scenario.expedited_readiness)
    windows_needed = 2 if scenario.mode == "schedule" and numbers.get("full_day_needed") else 1
    slot_lanes = numbers["eligible_lanes"]
    standard_slot = first_window_on_or_after(scenario, scenario.standard_readiness, windows_needed, slot_lanes)
    expedited_slot = first_window_on_or_after(scenario, scenario.expedited_readiness, windows_needed, slot_lanes)
    check("standard_slot_date", standard_slot[0] if standard_slot else None, numbers["standard_slot_date"])
    check("expedited_slot_date", expedited_slot[0] if expedited_slot else None, numbers["expedited_slot_date"])
    if scenario.mode == "plan":
        check("earliest_qualified_base_window", numbers["standard_slot_date"], extra["earliest_qualified_base_window"])
        check("expedited option date", expedited_slot[0] if expedited_slot else None, scenario.options[1].completion)
        check("expedite_completion_days_saved", (date.fromisoformat(numbers["standard_slot_date"]) - date.fromisoformat(numbers["expedited_slot_date"])).days, extra["expedite_completion_days_saved"])
        readiness = scenario.standard_readiness if PLAN_SELECTED_OPTIONS[selected.id] == "standard" else scenario.expedited_readiness
        slot = first_window_on_or_after(scenario, readiness, 1, slot_lanes)
        check("selected_lane_window", f"{slot[1]}/{slot[0]}/{slot[2]}" if slot else None, extra["selected_lane_window"])
        check("selected completion", slot[0] if slot else None, selected.completion)
    if scenario.selected_window_id not in {window_id(lane, day, session) for (day, lane, session) in calendar(scenario)}:
        problems.append(f"selected window {scenario.selected_window_id} is not on the calendar")
    if problems:
        raise ValueError(f"{scenario.task_id} scenario data disagrees with its declared numbers:\n  " + "\n  ".join(problems))


# --------------------------------------------------------------------------- #
# Seed tables
# --------------------------------------------------------------------------- #


def _cr_row(cr: ChangeRequest) -> dict[str, Any]:
    return {
        "cr_id": cr.cr_id,
        "page_id": cr.page_id,
        "title": cr.title,
        "kind": cr.kind,
        "territories_json": json.dumps(list(cr.territories)),
        "entries_in_scope": cr.entries_in_scope,
        "scope_note": cr.scope_note,
        "deploy_minutes": cr.deploy_minutes,
        "verify_minutes": cr.verify_minutes,
        "status": cr.status,
        "priority": cr.priority,
        "duplicate_of": cr.duplicate_of,
        "impact_consumers": cr.impact_consumers,
        "opened_at": cr.opened_at,
        "requested_by": cr.requested_by,
        "note": cr.note or None,
    }


def _page_row(page: Page) -> dict[str, Any]:
    return {"page_id": page.page_id, "slug": page.slug, "title": page.title, "owner_team": page.owner_team, "owner_person_id": page.owner_person_id, "markets_json": json.dumps(list(page.markets)), "status": page.status}


def seed_tables(scenario: Scenario, drive_files: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grid = calendar(scenario)
    windows = [
        {"window_id": window_id(lane, day, session), "lane_id": lane, "service_date": day, "session": session, "start_time": WINDOW_TIMES[session][0], "end_time": WINDOW_TIMES[session][1], **entry}
        for (day, lane, session), entry in sorted(grid.items())
    ]
    return {
        "users": [dict(row) for row in USERS],
        "people": [dict(row) for row in PEOPLE],
        "vendors": [dict(row) for row in VENDORS],
        "pages": [_page_row(page) for page in _pages(scenario)],
        "change_requests": [_cr_row(cr) for cr in scenario.change_requests],
        "entries": [
            {"entry_id": e.entry_id, "page_id": e.page_id, "cr_id": e.cr_id, "content_type": e.content_type, "title": e.title, "status": e.status, "revision": e.revision,
             "bound_token_id": e.bound_token_id, "bound_component_id": e.bound_component_id, "bound_asset_id": e.bound_asset_id, "blocked_reason": e.blocked_reason}
            for e in scenario.entries
        ],
        "token_sets": [{"set_id": s.set_id, "name": s.name, "current_version": s.current_version} for s in scenario.token_sets],
        "tokens": [{"token_id": t.token_id, "set_id": t.set_id, "name": t.name, "kind": t.kind} for t in scenario.tokens],
        "token_versions": [
            {"token_id": t.token_id, "version": v.version, "value": v.value, "status": v.status, "breaking": int(v.breaking), "released_on": v.released_on, "note": v.note or None}
            for t in scenario.tokens
            for v in t.versions
        ],
        "components": [
            {"component_id": c.component_id, "name": c.name, "library": c.library, "version": c.version, "allowed_variants_json": json.dumps(list(c.allowed_variants)), "status": c.status,
             "deprecated": int(c.deprecated), "breaking_change_pending": int(c.breaking_change_pending), "note": c.note or None}
            for c in scenario.components
        ],
        "consumers": [
            {"consumer_id": c.consumer_id, "token_id": c.token_id, "component_id": c.component_id, "page_id": c.page_id, "surface": c.surface, "status": c.status, "note": c.note or None}
            for c in scenario.consumers
        ],
        "token_pins": [
            {"pin_id": p.pin_id, "token_id": p.token_id, "version": p.version, "cr_id": p.cr_id, "consumer_count": p.consumer_count, "unit": web_tools.CONSUMER_UNIT, "status": p.status,
             "requested_by": "web_release_coordinator", "created_at": p.created_at, "revision": 1}
            for p in scenario.pins
        ],
        "design_files": [
            {"file_id": f.file_id, "name": f.name, "page_id": f.page_id, "version": f.version, "status": f.status, "superseded_by": f.superseded_by, "review_status": f.review_status}
            for f in scenario.design_files
        ],
        "design_frames": [
            {"frame_id": f.frame_id, "file_id": f.file_id, "name": f.name, "status": f.status, "components_json": json.dumps(list(f.components)), "note": f.note or None}
            for f in scenario.frames
        ],
        "assets": [
            {"asset_id": a.asset_id, "kind": a.kind, "name": a.name, "vendor_id": a.vendor_id, "page_id": a.page_id, "usage_count": a.usage_count, "licence_required": int(a.licence_required), "status": a.status}
            for a in scenario.assets
        ],
        "licences": [
            {"licence_id": l.licence_id, "asset_id": l.asset_id, "vendor_id": l.vendor_id, "reference": l.reference, "territories_json": json.dumps(list(l.territories)), "territory_count": l.territory_count,
             "usage_scope": l.usage_scope, "expires_on": l.expires_on, "status": l.status, "status_reason": l.reason, "reserved_for_cr": l.reserved_for}
            for l in scenario.licences
        ],
        "licence_quotes": [
            {"quote_id": q.quote_id, "vendor_id": q.vendor_id, "asset_id": q.asset_id, "reference": q.reference, "kind": q.kind, "units_available": q.units_available,
             "standard_issue_date": q.standard_date, "expedited_issue_date": q.expedited_date, "rush_fee_usd": q.rush_fee, "per_unit_fee_usd": q.per_unit_fee, "valid_until": q.valid_until, "status": q.status, "note": q.note}
            for q in (scenario.quote, *scenario.other_quotes)
        ],
        "licence_requests": [
            {"request_id": "LR-6200", "vendor_id": "VND-STILLFRAME", "quote_id": None, "asset_id": "AST-IMG-7601", "territory_count": 2, "unit": web_tools.TERRITORY_UNIT, "issuance_option": "standard",
             "expected_licence_date": "2026-04-20", "status": "ISSUED", "requested_by": "web_release_coordinator", "created_at": "2026-04-13T09:30:00", "revision": 1},
        ],
        "checklist_gates": [
            {"gate_id": g.gate_id, "cr_id": g.cr_id, "name": g.name, "category": g.category, "status": g.status, "authority_role": g.authority_role, "measured": g.measured or None, "budget": g.budget or None, "note": g.note or None}
            for g in scenario.gates
        ],
        "perf_budgets": [
            {"budget_id": b.budget_id, "page_id": b.page_id, "metric": b.metric, "budget_value": b.budget_value, "measured_value": b.measured_value, "unit": b.unit, "measured_at": b.measured_at, "status": b.status}
            for b in scenario.budgets
        ],
        "waivers": [],
        "lanes": [{"lane_id": l.lane_id, "pool": "web-pool", "name": l.name, "status": l.status, "rollback_capable": int(l.rollback_capable), "status_note": l.note} for l in scenario.lanes],
        "deploy_windows": windows,
        "releases": [
            {"release_id": r.release_id, "page_id": r.page_id, "cr_id": r.cr_id, "lane_id": r.lane_id, "start_time": r.start, "end_time": r.end, "status": r.status, "description": r.description,
             "entry_count": r.entry_count, "revision": 1, "last_updated": "2026-05-08T12:00:00"}
            for r in scenario.releases
        ],
        "approvals": [
            {"approval_id": scenario.approval.approval_id, "subject": scenario.approval.subject, "approver_id": scenario.approval.approver_id, "approver_role": scenario.approval.approver_role,
             "status": "APPROVED", "granted_on": scenario.approval.granted_on, "scope_json": json.dumps(scenario.approval.scope, sort_keys=True)},
            {"approval_id": "AP-WS-0090", "subject": "Annual stock-imagery subscription renewal (standing order)", "approver_id": "U-AURBAKKEN", "approver_role": "web_release_manager",
             "status": "APPROVED", "granted_on": "2026-02-06", "scope_json": json.dumps({"category": "SUBSCRIPTIONS", "max_spend_usd": 9000}, sort_keys=True)},
        ],
        "messages": [
            {"message_id": scenario.email.message_id, "thread_id": scenario.email.thread_id, "channel": "email", "sender": scenario.email.sender, "recipients": scenario.email.recipients,
             "subject": scenario.email.subject, "sent_at": scenario.email.sent_at, "body": scenario.email.body,
             "attachments_json": json.dumps([{"name": name, "mime_type": "application/pdf"} for name in scenario.email.attachments]), "labels": f"{scenario.email.labels},{scenario.case_reference}"},
            {"message_id": f"MSG-{scenario.ordinal:04d}-00", "thread_id": f"THR-{scenario.ordinal:04d}-OPS", "channel": "email", "sender": "helene.aurbakken@larkspur.example", "recipients": "web-releases@larkspur.example",
             "subject": "Weekly release note", "sent_at": "2026-05-08T08:00:00", "body": "Release engineering rota for the week of 2026-05-11 is posted. Lane capability flags are on the shared drive roster; no changes to protected blocks.",
             "attachments_json": "[]", "labels": "operations"},
        ],
        "chat_threads": [
            {"thread_id": scenario.chat.thread_id, "channel": scenario.chat.channel, "title": scenario.chat.title, "messages_json": json.dumps([{"author": a, "ts": t, "text": x} for a, t, x in scenario.chat.messages])},
            {"thread_id": f"CHAT-{scenario.ordinal:04d}-GEN", "channel": "#web-releases", "title": "General — token naming and lane etiquette",
             "messages_json": json.dumps([{"author": "Priya Raghunathan", "ts": "2026-05-07T16:40:00", "text": "Reminder: every token version bump goes through the registry, not a spreadsheet."}])},
        ],
        "drive_files": drive_files,
        "evidence_files": evidence,
    }


# --------------------------------------------------------------------------- #
# Evidence room
# --------------------------------------------------------------------------- #


def _cr_json(scenario: Scenario, cr: ChangeRequest) -> str:
    rendered = web_tools._change_request(_cr_row(cr))
    return json.dumps({"export": "cms.change_requests.get", "case_reference": scenario.case_reference, "record": rendered}, indent=2, sort_keys=True) + "\n"


def _page_entries_json(scenario: Scenario) -> str:
    rows = [web_tools._entry({"entry_id": e.entry_id, "page_id": e.page_id, "cr_id": e.cr_id, "content_type": e.content_type, "title": e.title, "status": e.status, "revision": e.revision,
                              "bound_token_id": e.bound_token_id, "bound_component_id": e.bound_component_id, "bound_asset_id": e.bound_asset_id, "blocked_reason": e.blocked_reason})
            for e in scenario.entries if e.page_id == scenario.page.page_id]
    return json.dumps({"export": "cms.pages.get + cms.entries.list", "case_reference": scenario.case_reference, "page": web_tools._page(_page_row(scenario.page)), "entries": rows}, indent=2, sort_keys=True) + "\n"


def _quote_text(scenario: Scenario) -> str:
    q = scenario.quote
    vendor = next(row for row in VENDORS if row["vendor_id"] == q.vendor_id)
    unit = {"licence": "territories", "agency_delivery": "components", "lane_recertification": "lanes"}[q.kind]
    return (
        f"{vendor['name']}\nQuote {q.reference} (system reference {q.quote_id}) — {q.kind.replace('_', ' ')}\nCustomer: Larkspur Commerce Web Platform Studio, account {vendor['account_number']}\n"
        f"Case reference: {scenario.case_reference}\nSubject: {q.asset_id}\nUnits available on this quote: {q.units_available} {unit}\nPer-unit fee: USD {q.per_unit_fee:.2f}\n"
        f"Standard issue date: {q.standard_date}\nExpedited issue date: {q.expedited_date} (rush fee USD {q.rush_fee}, flat)\nValid until: {q.valid_until}\nNotes: {q.note}\n"
        "Issued items register with the customer on the next business day after the issue date; the customer's countersign and registration are its own responsibility.\n"
    )


def _with_case(rows: list[list[Any]], case: str) -> list[list[Any]]:
    return [[*rows[0], "hubbench_case_reference"], *[[*row, case] for row in rows[1:]]]


def _doc_asset(scenario: Scenario, doc: Any, source: str = "drive") -> dict[str, Any]:
    case = scenario.case_reference
    if doc.media_type == XLSX:
        return asset(doc.path, kind=doc.kind, title=doc.title, source=source, media_type=XLSX, rows=_with_case([list(row) for row in doc.rows or ()], case), preview=doc.title)
    content = doc.content
    if doc.media_type == MARKDOWN:
        content = scoped_markdown(content, task_id=scenario.task_id, case_reference=case)
    elif doc.media_type == CSV:
        content = scoped_csv(content, task_id=scenario.task_id, case_reference=case)
    elif doc.media_type == PDF:
        content = content.rstrip() + f"\nCase reference: {case}\n"
    return asset(doc.path, kind=doc.kind, title=doc.title, source=source, media_type=doc.media_type, content=content, preview=doc.title)


def _decoy_asset(scenario: Scenario) -> dict[str, Any]:
    doc = scenario.decoy_doc
    case = scenario.case_reference
    if doc.kind == "policy_superseded":
        return asset(doc.path, kind=doc.kind, title=doc.title, source="drive", media_type=MARKDOWN, content=scoped_markdown(SUPERSEDED_PLAYBOOK, task_id=scenario.task_id, case_reference=case),
                     preview="2024 playbook retained for audit only; superseded by v3.")
    if doc.kind == "decoy_change_request":
        cr_id = doc.path.rsplit("/", 1)[-1].removeprefix("change-request-").removesuffix(".json")
        cr = next(item for item in scenario.change_requests if item.cr_id == cr_id)
        return asset(doc.path, kind=doc.kind, title=doc.title, source="cms_export", media_type=JSON, content=_cr_json(scenario, cr), preview="A closed, duplicate, or unrelated change request that must not drive the requirement.")
    if doc.kind == "superseded_frame":
        frame_id = doc.path.rsplit("/", 1)[-1].removeprefix("frame-").removesuffix("-superseded.json")
        frame = next(item for item in scenario.frames if item.frame_id == frame_id)
        payload = {"export": "design.frames.list", "case_reference": case, "frame": {"frame_id": frame.frame_id, "file_id": frame.file_id, "name": frame.name, "status": frame.status, "components": list(frame.components), "note": frame.note}}
        return asset(doc.path, kind=doc.kind, title=doc.title, source="design_export", media_type=JSON, content=json.dumps(payload, indent=2, sort_keys=True) + "\n", preview="A superseded design frame whose copy and components are no longer current.")
    return _doc_asset(scenario, doc)


def build_assets(scenario: Scenario) -> list[dict[str, Any]]:
    case = scenario.case_reference
    grid = calendar(scenario)
    cr = scenario.primary_cr
    assets: list[dict[str, Any]] = [
        asset("playbook/web-release-playbook.md", kind="policy", title="Web release playbook v3 (effective)", source="drive", media_type=MARKDOWN,
              content=scoped_markdown(effective_playbook(AS_OF), task_id=scenario.task_id, case_reference=case), preview="Scope, licence, token, window, and authority rules in force."),
    ]
    if scenario.decoy_doc.kind != "policy_superseded":
        assets.append(asset("playbook/superseded-web-release-playbook-2024.md", kind="policy_superseded", title="Web release playbook 2024 (superseded)", source="drive", media_type=MARKDOWN,
                            content=scoped_markdown(SUPERSEDED_PLAYBOOK, task_id=scenario.task_id, case_reference=case), preview="2024 playbook retained for audit only; superseded by v3."))
    assets.append(_decoy_asset(scenario))
    token = scenario.primary_token
    assets.extend(
        [
            asset(f"cms/change-request-{cr.cr_id}.json", kind="change_request_export", title=f"Change request {cr.cr_id} (CMS export)", source="cms_export", media_type=JSON, content=_cr_json(scenario, cr),
                  preview="The active change request: launch territories, entries in scope, and durations."),
            asset(f"cms/page-{scenario.page.slug}-entries.json", kind="page_entries_export", title=f"Page {scenario.page.slug} with entries and bindings (CMS export)", source="cms_export", media_type=JSON,
                  content=_page_entries_json(scenario), preview="Page identity plus every entry with its token, component, and asset bindings."),
            asset("tokens/token-register.csv", kind="token_register", title="Design-token register: versions, status, breaking flags", source="tokens_export", media_type=CSV,
                  content=scoped_csv("token_id,set_id,name,version,value,status,breaking,released_on,note\n" + "".join(f'{t.token_id},{t.set_id},{t.name},{v.version},{v.value},{v.status},{"yes" if v.breaking else "no"},{v.released_on},"{v.note}"\n' for t in scenario.tokens for v in t.versions),
                                     task_id=scenario.task_id, case_reference=case), preview="Current, proposed, and deprecated token versions with breaking flags."),
            asset("tokens/consumer-registry.xlsx", kind="consumer_workbook", title="Token and component consumer registry (gross)", source="tokens_workbook", media_type=XLSX,
                  rows=_with_case([["consumer_id", "token_id", "component_id", "page_id", "surface", "status", "note"], *[[c.consumer_id, c.token_id or "", c.component_id or "", c.page_id, c.surface, c.status, c.note] for c in scenario.consumers]], case),
                  preview="Every registry consumer row including DEPRECATED and MIGRATED entries."),
            asset("tokens/component-register.csv", kind="component_register", title="Component register: versions, variants, deprecations", source="tokens_export", media_type=CSV,
                  content=scoped_csv("component_id,name,library,version,allowed_variants,status,deprecated,breaking_change_pending,note\n" + "".join(f'{c.component_id},{c.name},{c.library},{c.version},{"|".join(c.allowed_variants)},{c.status},{"yes" if c.deprecated else "no"},{"yes" if c.breaking_change_pending else "no"},"{c.note}"\n' for c in scenario.components),
                                     task_id=scenario.task_id, case_reference=case), preview="Allowed variants, deprecations, and pending breaking changes."),
            asset("design/design-file-index.csv", kind="design_index", title="Design-file index with frame review status", source="design_export", media_type=CSV,
                  content=scoped_csv("file_id,file_name,file_status,superseded_by,frame_id,frame_name,frame_status,components\n" + "".join(f'{f.file_id},{f.name},{f.status},{f.superseded_by or ""},{fr.frame_id},{fr.name},{fr.status},{"|".join(fr.components)}\n' for f in scenario.design_files for fr in scenario.frames if fr.file_id == f.file_id),
                                     task_id=scenario.task_id, case_reference=case), preview="Which design file and frames are current, in review, or superseded."),
            asset("dam/licence-grants.xlsx", kind="grants_workbook", title="Licence grants by asset (gross territories)", source="dam_workbook", media_type=XLSX,
                  rows=_with_case([["reference", "asset_id", "vendor_id", "territories", "territory_count", "expires_on"], *[[l.reference, l.asset_id, l.vendor_id, "|".join(l.territories), l.territory_count, l.expires_on] for l in scenario.licences]], case),
                  preview="Gross territory counts by grant; status, scope, and reservations live in the status register."),
            asset("dam/licence-status-register.csv", kind="verification_register", title="Licence-grant status register (countersign, scope, reservations)", source="dam_export", media_type=CSV,
                  content=scoped_csv("reference,asset_id,status,usage_scope,status_reason,reserved_for_change_request,register_note\n" + "".join(f"{l.reference},{l.asset_id},{l.status},{l.usage_scope},{l.reason or ''},{l.reserved_for or ''},{l.register_note}\n" for l in scenario.licences),
                                     task_id=scenario.task_id, case_reference=case), preview="Which grants are pending, suspended, print-only, or reserved."),
            asset(f"checklist/release-checklist-{cr.cr_id}.csv", kind="checklist_export", title=f"Release checklist for {cr.cr_id}", source="checklist_export", media_type=CSV,
                  content=scoped_csv("gate_id,name,category,status,authority_role,measured,budget,note\n" + "".join(f'{g.gate_id},{g.name},{g.category},{g.status},{g.authority_role},{g.measured},{g.budget},"{g.note}"\n' for g in scenario.gates if g.cr_id == cr.cr_id),
                                     task_id=scenario.task_id, case_reference=case), preview="QA, accessibility, legal, and performance gate states."),
            asset(f"checklist/perf-budgets-{scenario.page.slug}.csv", kind="perf_budgets", title=f"Performance budgets for {scenario.page.slug}", source="checklist_export", media_type=CSV,
                  content=scoped_csv("budget_id,metric,budget_value,measured_value,unit,measured_at,status\n" + "".join(f"{b.budget_id},{b.metric},{b.budget_value:g},{b.measured_value:g},{b.unit},{b.measured_at},{b.status}\n" for b in scenario.budgets),
                                     task_id=scenario.task_id, case_reference=case), preview="Budgets with the latest measured values."),
            asset("cdn/deploy-window-calendar-2026-05-11.xlsx", kind="window_calendar", title="Deploy-window calendar, three weeks from 2026-05-11", source="cdn_workbook", media_type=XLSX,
                  rows=_with_case([["service_date", "lane_id", "session", "start", "end", "status", "hold_reason"], *[[day, lane, session, WINDOW_TIMES[session][0], WINDOW_TIMES[session][1], entry["status"], entry["hold_reason"] or ""] for (day, lane, session), entry in sorted(grid.items())]], case),
                  preview="Every deploy window with free / busy / protected / blocked status."),
            asset("cdn/lane-roster-and-capabilities.csv", kind="lane_roster", title="Deploy-lane roster and rollback capability", source="cdn_export", media_type=CSV,
                  content=scoped_csv("lane_id,name,status,rollback_capable,note\n" + "".join(f"{l.lane_id},{l.name},{l.status},{'yes' if l.rollback_capable else 'no'},{l.note or ''}\n" for l in scenario.lanes), task_id=scenario.task_id, case_reference=case),
                  preview="Lane status and instant-rollback capability flags for the sprint."),
            asset(f"vendors/vendor-quote-{scenario.quote.reference}.pdf", kind="vendor_quote", title=f"Vendor quote {scenario.quote.reference}", source="email_attachment", media_type=PDF, content=_quote_text(scenario),
                  preview="Standard and expedited issue dates, rush fee, and validity."),
            asset(f"messages/{scenario.email.thread_id}.eml", kind="email", title=scenario.email.subject, source="messages", media_type=EML,
                  content=eml(from_addr=scenario.email.sender, to_addr=scenario.email.recipients, subject=scenario.email.subject, date=scenario.email.sent_at, message_id=f"{scenario.email.message_id}@larkspur.example", body=scenario.email.body, attachments=list(scenario.email.attachments)),
                  preview="The request and the control date, in the requester's words."),
            asset(f"chat/{scenario.chat.thread_id}.json", kind="chat_thread", title=scenario.chat.title, source="chat", media_type=JSON,
                  content=json.dumps({"thread_id": scenario.chat.thread_id, "channel": scenario.chat.channel, "title": scenario.chat.title, "messages": [{"author": a, "ts": t, "text": x} for a, t, x in scenario.chat.messages]}, indent=2, sort_keys=True) + "\n",
                  preview="Team chat with grant, token, window, and authority remarks."),
            asset(f"approvals/approval-{scenario.approval.approval_id}.json", kind="approval", title=f"Approval record {scenario.approval.approval_id}", source="approvals_export", media_type=JSON,
                  content=json.dumps({"approval_id": scenario.approval.approval_id, "case_reference": case, "subject": scenario.approval.subject, "approver_id": scenario.approval.approver_id, "approver_role": scenario.approval.approver_role, "status": "APPROVED", "granted_on": scenario.approval.granted_on, "scope": scenario.approval.scope}, indent=2, sort_keys=True) + "\n",
                  preview="Exactly what is approved, for which record, and what is not."),
            asset(f"exports/starting-state-{scenario.task_id}.json", kind="starting_state", title="Starting-state export (releases, pins, licence requests)", source="cms_export", media_type=JSON,
                  content=json.dumps({"case_reference": case, "as_of": AS_OF,
                                      "releases": [{"release_id": r.release_id, "page_id": r.page_id, "change_request_id": r.cr_id, "lane_id": r.lane_id, "start": r.start, "end": r.end, "status": r.status} for r in scenario.releases],
                                      "token_pins": [{"pin_id": p.pin_id, "token_id": p.token_id, "version": p.version, "change_request_id": p.cr_id, "consumer_count": p.consumer_count, "status": p.status} for p in scenario.pins],
                                      "licence_requests": [{"request_id": "LR-6200", "status": "ISSUED"}],
                                      "note": "Snapshot before any action; row order does not indicate applicability."}, indent=2, sort_keys=True) + "\n",
                  preview="Snapshot of CMS, registry, and asset-library state before any action."),
        ]
    )
    for doc in scenario.docs:
        assets.append(_doc_asset(scenario, doc))
    assets.extend(
        quality_support_assets(task_id=scenario.task_id, ordinal=scenario.ordinal, case_reference=case, family_slug=FAMILY_SLUG, family_name="WebStudio", organization_name=ORGANIZATION["name"],
                               subject_id=scenario.item, as_of=AS_OF, current_revision=scenario.revision, anchors=OPEN_SOURCE_ANCHORS)
    )
    index = {"case_reference": case, "as_of": AS_OF, "files": [{"path": a["path"], "kind": a["kind"], "media_type": a["media_type"], "sha256": a["sha256"]} for a in assets]}
    assets.append(asset("audit/evidence-index.yaml", kind="evidence_index", title="Evidence index", source="drive", media_type=YAML, content=yaml_lines(index) + "\n", preview="Digest index of every evidence file in the room."))
    for position, record in enumerate(assets, start=1):
        record["asset_id"] = f"{scenario.task_id}-{position:02d}"
    return assets


def _folder(scenario: Scenario, record: dict[str, Any]) -> str:
    if record["kind"] == "policy":
        return "Web Studio/Playbooks"
    if record["kind"] == "policy_superseded":
        return "Web Studio/Playbooks/Archive"
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
        files.append({"file_id": file_id, "name": record["path"].rsplit("/", 1)[-1], "mime_type": record["media_type"], "modified_time": "2026-05-08T17:30:00", "folder": _folder(scenario, record), "content": record["content"], "sha256": record["sha256"]})
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
        {"id": "authoritative_identity", "sources": ["cms", "messages"],
         "statement": f"{scenario.case_reference}: {notes['identity']}; the effective revision is {scenario.revision}.",
         "rubric": f"Located {scenario.item} using immutable identifiers and preserved effective revision {scenario.revision}: {notes['identity']}."},
        {"id": "effective_requirement", "sources": ["cms", "drive"],
         "statement": f"The effective change request and playbook establish {labels.scope_label} = {numbers['scope']} {labels.unit}: {notes['requirement']}. The control date is {scenario.business_need} ({scenario.business_need_reason}).",
         "rubric": f"Applied the effective change request and playbook to establish {numbers['scope']} {labels.unit} for {labels.scope_label}, with control date {scenario.business_need}."},
        {"id": "eligible_coverage", "sources": ["dam", "tokens", "checklist", "drive"],
         "statement": f"{notes['coverage']}; eligibility requires netting the exclusions rather than trusting a header total.",
         "rubric": f"Reconciled {numbers['observed']} observed less {numbers['excluded']} excluded to {numbers['eligible']} supported {labels.unit} for {labels.eligible_label}."},
        {"id": "conditional_external_recovery", "sources": ["vendors", "messages"],
         "statement": f"{labels.external_label}: {notes['external']}; a vendor quote alone proves neither eligibility nor approval.",
         "rubric": f"Used the independently confirmed {scenario.expedited_readiness} expedited readiness input for {accelerated.id}, then separately derived its {accelerated.completion} operating outcome under {labels.constraint_label} instead of treating a vendor promise as authorization or a completion date."},
        {"id": "finite_capacity", "sources": ["cdn", "drive"],
         "statement": f"{labels.capacity_label}: {notes['capacity']}; protected and blocked windows cannot be displaced.",
         "rubric": f"Applied {labels.capacity_label} to derive the three option outcomes without using protected or blocked windows."},
        {"id": "approval_scope", "sources": ["approvals", "chat"],
         "statement": f"{notes['approval']}. The approval does not select an option in advance and does not authorize {unauthorized.id}.",
         "rubric": f"Applied {scenario.approval.approval_id} only to {selected.id} and {scenario.item}; kept {unauthorized.id} outside current authority."},
        {"id": "business_impact", "sources": ["messages", "chat"],
         "statement": f"{notes['impact']}; a faster or broader action has value only if it remains inside {labels.constraint_label}.",
         "rubric": f"Compared all three alternatives and selected {selected.id}: it is the best currently authorized response that satisfies {labels.constraint_label}."},
    )


def build_model(scenario: Scenario) -> dict[str, Any]:
    numbers = scenario.numbers
    inputs = DecisionInputs(
        mode=scenario.mode, labels=scenario.labels, item=scenario.item, record=scenario.item, revision=scenario.revision,
        scope=int(numbers["scope"]), observed=int(numbers["observed"]), excluded=int(numbers["excluded"]), eligible=int(numbers["eligible"]), gap=int(numbers["gap"]),
        business_need=scenario.business_need, standard_readiness=scenario.standard_readiness, expedited_readiness=scenario.expedited_readiness, options=scenario.options,
        transaction_quantity=int(numbers["transaction_quantity"]) if "transaction_quantity" in numbers else None,
        selected_resource=str(numbers["selected_resource"]) if "selected_resource" in numbers else None,
        extra_answer=dict(scenario.extra_answer), extra_descriptions=dict(scenario.extra_descriptions), extra_calculations=scenario.extra_calculations, facts=build_facts(scenario),
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
    page = scenario.page
    cr = scenario.primary_cr
    token = scenario.primary_token
    asset_id = scenario.primary_asset.asset_id
    playbook_id = file_ids["playbook/web-release-playbook.md"]
    approval_id = file_ids[f"approvals/approval-{scenario.approval.approval_id}.json"]
    cr_file_id = file_ids[f"cms/change-request-{cr.cr_id}.json"]
    releases = in_scope_releases(scenario)
    first_entry = entries_of(scenario, cr.cr_id)[0]
    first_gate = next(gate for gate in scenario.gates if gate.cr_id == cr.cr_id)
    first_licence = next(item for item in scenario.licences if item.asset_id == asset_id)
    first_consumer = consumers_of(scenario, token.token_id)[0]
    first_budget = next(item for item in scenario.budgets if item.page_id == page.page_id)
    if scenario.numbers.get("coverage_basis") == "licence_union":
        cr_list_args: dict[str, Any] = {"status": "open"}
        cr_list_expected = {"change_requests": [{"change_request_id": release.cr_id} for release in releases]}
    else:
        cr_list_args = {"page_id": page.page_id}
        cr_list_expected = {"change_requests": [{"change_request_id": cr.cr_id}]}
    if releases:
        release_args: dict[str, Any] = {"start_date": scenario.numbers["in_scope_window"][0], "end_date": scenario.numbers["in_scope_window"][1], "status": "scheduled"}
        release_expected = {"releases": [{"id": release.release_id} for release in releases]}
    else:
        own = [release for release in scenario.releases if release.page_id == page.page_id]
        release_args = {"page_id": page.page_id}
        release_expected = {"releases": [{"id": release.release_id} for release in own]} if own else {"total": 0}
    investigations = [
        _investigation(1, "investigation.scope", f"Established the isolated {case} scope, immutable handles, mounted systems, and evidence index before investigating {scenario.item}.", CONTEXT_TOOL, {}, {"reference_records": {"case_reference": case}}),
        _investigation(2, "investigation.scope", f"Located the task-scoped correspondence for {case} by searching the mailbox before opening any message; did not rely on a guessed sender or filename.", "messages.list", {"q": case}, {"messages": [{"id": scenario.email.message_id}]}),
        _investigation(3, "investigation.scope", f"Resolved slug {page.slug} to the immutable page record through a slug search rather than a title match against a similarly named page.", "cms.pages.search", {"slug": page.slug}, {"pages": [{"page_id": page.page_id}]}),
        _investigation(4, "investigation.scope", f"Listed the {case} case folder on the shared drive and identified the approval record and the change-request export by immutable file id.", "drive.files.list", {"q": case}, {"files": [{"id": approval_id}, {"id": cr_file_id}]}),
        _investigation(5, "investigation.scope", "Listed the playbook folder and distinguished the effective v3 playbook from the superseded 2024 edition by file identity, not title.", "drive.files.list", {"q": "playbook"}, {"files": [{"id": playbook_id}]}),
        _investigation(6, "investigation.requirements", f"Read the active change request {cr.cr_id}: launch territories, entries in scope, durations, and impact notes.", "cms.change_requests.get", {"change_request_id": cr.cr_id}, {"change_request_id": cr.cr_id, "status": cr.status}),
        _investigation(7, "investigation.requirements", f"Listed the entries of {cr.cr_id} with their token, component, and asset bindings and blocking reasons.", "cms.entries.list", {"change_request_id": cr.cr_id}, {"entries": [{"entry_id": first_entry.entry_id}]}),
        _investigation(8, "investigation.requirements", "Exported the effective v3 playbook for the scope, licence-eligibility, breaking-token, window, and authority rules; did not apply the superseded 2024 edition.", "drive.files.export", {"file_id": playbook_id}, {"file_id": playbook_id}),
        _investigation(9, "investigation.requirements", f"Read design token {token.token_id}: its current version and any proposed version with its breaking flag.", "tokens.tokens.get", {"token_id": token.token_id}, {"token_id": token.token_id}),
        _investigation(10, "investigation.requirements", f"Listed the change requests that define the requirement ({', '.join(sorted({release.cr_id for release in releases}) if releases else [cr.cr_id])}) and excluded duplicate, superseded, or out-of-scope requests.", "cms.change_requests.list", cr_list_args, cr_list_expected),
        _investigation(11, "investigation.requirements", f"Read the release checklist for {cr.cr_id} to ground which gates passed, which failed, and who can waive what.", "checklist.gates.list", {"change_request_id": cr.cr_id}, {"gates": [{"gate_id": first_gate.gate_id}]}),
        _investigation(12, "investigation.constraints", f"Listed every {asset_id} licence grant with territories, expiry, countersign status, scope, and reservations before netting the coverage.", "dam.licences.list", {"asset_id": asset_id}, {"licences": [{"licence_id": first_licence.licence_id}]}),
        _investigation(13, "investigation.constraints", f"Read the deploy-window calendar for {scenario.windows_query['start_date']} onward to find the first free window that displaces no protected or blocked block.", "cdn.windows.list", dict(scenario.windows_query), {"windows": [{"id": scenario.selected_window_id}]}),
        _investigation(14, "investigation.constraints", f"Read the vendor quote {scenario.quote.quote_id} for the independently confirmed standard and expedited issue dates and the rush fee.", "vendors.quotes.get", {"quote_id": scenario.quote.quote_id}, {"quote_id": scenario.quote.quote_id, "standard_issue_date": scenario.quote.standard_date}),
        _investigation(15, "investigation.constraints", f"Listed the gross registry consumers of {token.token_id} so deprecated, migrated, and on-page rows could be excluded from the impact count.", "tokens.consumers.list", {"token_id": token.token_id}, {"consumers": [{"consumer_id": first_consumer.consumer_id}]}),
        _investigation(16, "investigation.constraints", f"Listed the frames of the current design file {scenario.current_design_file.file_id} and distinguished the approved frame from superseded and in-review frames.", "design.frames.list", {"file_id": scenario.current_design_file.file_id}, {"frames": [{"frame_id": scenario.approved_frame.frame_id}]}),
        _investigation(17, "investigation.constraints", f"Read the performance budgets for {page.page_id} with their measured values and headroom.", "checklist.budgets.list", {"page_id": page.page_id}, {"budgets": [{"budget_id": first_budget.budget_id}]}),
        _investigation(18, "investigation.constraints", "Read the deploy-lane roster for lane status and instant-rollback capability before choosing a lane for the release window.", "cdn.lanes.list", {}, {"lanes": [{"lane_id": "LANE-WEB-1"}]}),
        _investigation(19, "investigation.authority", f"Read approval {scenario.approval.approval_id} for its exact scope: record, quantity, vendor, fee allowance, and what it does not cover.", "approvals.get", {"approval_id": scenario.approval.approval_id}, {"approval_id": scenario.approval.approval_id}),
        _investigation(20, "investigation.authority", "Exported the approval record on the drive and confirmed it matches the workflow record before relying on it.", "drive.files.export", {"file_id": approval_id}, {"file_id": approval_id}),
        _investigation(21, "investigation.erp_correlation", f"Read the request message {scenario.email.message_id} for the documented control date and the business need in the requester's words.", "messages.get", {"message_id": scenario.email.message_id}, {"id": scenario.email.message_id}),
        _investigation(22, "investigation.erp_correlation", f"Read the team chat thread {scenario.chat.thread_id} for grant, token, window, and authority remarks that qualify the system records.", "chat.threads.get", {"thread_id": scenario.chat.thread_id}, {"thread_id": scenario.chat.thread_id}),
        _investigation(23, "investigation.erp_correlation", "Correlated the scheduled releases that fix the deploy scope by immutable id.", "cms.releases.list", release_args, release_expected),
    ]
    investigations.extend(quality_support_investigations(start_number=len(investigations) + 1, file_ids=file_ids, make_investigation=_investigation, case_reference=case, subject_id=scenario.item))
    return investigations


def build_oracle_steps(scenario: Scenario, investigations: list[dict[str, Any]], model: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [{"phase": "context", "tool": CONTEXT_TOOL, "arguments": {}, "control": True}]
    order = [2, 21, 3, 10, 6, 7, 11, 4, 5, 8, 9, 12, 15, 16, 17, 23, 13, 18, 14, 19, 20, 22]
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
                "related_change_request_id": scenario.primary_cr.cr_id,
                "related_page_id": scenario.page.page_id,
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
            "payload_text_any_of": [[scenario.case_reference, scenario.page.slug, scenario.primary_cr.cr_id]],
            "weight": 1.5,
        },
        {
            "id": "containment_01",
            "milestone_id": "containment.scope",
            "description": f"Made exactly two state changes for {scenario.case_reference}: the primary change and the stakeholder draft; no additional release, pin, licence request, or waiver.",
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
    evidence = [{"asset_id": a["asset_id"], "task_id": scenario.task_id, "path": a["path"], "title": a["title"], "kind": a["kind"], "source": a["source"], "media_type": a["media_type"], "sha256": a["sha256"]} for a in assets]
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
        case_reference=scenario.case_reference, record=scenario.item, revision=scenario.revision, subject=scenario.labels.subject, selected_option=model["selected_option"],
        selected_completion=model["selected_completion"], facts=model["facts"], primary_outcome=primary.outcome_label,
        correlated_systems=["cms", "tokens", "dam", "checklist", "cdn", "messages", "chat"],
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
        "expected": {"answer": answer, "answer_checks": checks, "calculations": model["calculations"], "assertions": assertions, "investigations": investigations, "post_write_verifications": [readback]},
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
            "cms": {"page_slug": scenario.page.slug, "page_search": {"tool": "cms.pages.search", "arguments": {"slug": scenario.page.slug}}, "change_request_id": scenario.primary_cr.cr_id},
            "messages": {"search_query": scenario.case_reference},
            "drive": {"case_folder_query": scenario.case_reference, "playbook_query": "playbook"},
            "tokens": {"token_id": scenario.primary_token.token_id},
            "dam": {"asset_id": scenario.primary_asset.asset_id},
            "design": {"file_id": scenario.current_design_file.file_id},
            "checklist": {"change_request_id": scenario.primary_cr.cr_id, "page_id": scenario.page.page_id},
            "cdn": {"pool": "web-pool", "calendar_window": scenario.windows_query},
            "vendors": {"quote_id": scenario.quote.quote_id},
            "approvals": {"approval_id": scenario.approval.approval_id},
            "chat": {"thread_id": scenario.chat.thread_id},
        },
        "starting_records": [
            *[{"system": "cms", "resource_type": "Release", "resource_id": r.release_id, "status": r.status} for r in scenario.releases],
            *[{"system": "tokens", "resource_type": "TokenPin", "resource_id": p.pin_id, "status": p.status} for p in scenario.pins],
            {"system": "dam", "resource_type": "LicenceRequest", "resource_id": "LR-6200", "status": "ISSUED"},
        ],
        "evaluation": {"metric": "HubScore", "strict_pass": "every rubric milestone passes", "llm_judge_calls": 0},
        "workflow": {"reads": len([s for s in steps if s["phase"] in {"context", "investigation"}]), "writes": 2, "readbacks": 1, "answer_fields": len(answer)},
    }


def build_tasks() -> list[dict[str, Any]]:
    return [build_task(scenario) for scenario in scenarios()]


__all__ = ["BENCHMARK", "FAMILY_SLUG", "FAMILY_VERSION", "build_task", "build_tasks", "calendar", "first_window_on_or_after", "verify_numbers"]
