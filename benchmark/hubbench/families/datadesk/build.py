"""Assemble DataDesk tasks: seed tables, scattered evidence, decision model, sealed contract.

Every declared number in a scenario is recomputed from the seeded world (delivery
logs, run history, window calendar, control totals, schedules) and the build
fails on any disagreement, so the answer contract can never drift from the data
the agent actually sees.
"""

from __future__ import annotations

import json
import math
from typing import Any

from ...engine.assets import (
    CSV,
    EML,
    JSON,
    MARKDOWN,
    PDF,
    XLSX,
    YAML,
    asset,
    eml,
    yaml_lines,
)
from ...engine.catalog import (
    answer_checks,
    build_rubric_milestones,
    milestone_descriptions,
    sequence_signature,
)
from ...engine.decision import (
    UNAUTHORIZED,
    DecisionInputs,
    answer_schema,
    build_decision_model,
)
from ...engine.families import CONTEXT_TOOL, SUBMIT_TOOL
from ...engine.grading_contracts import fact_text_contract
from ...engine.quality_assets import (
    quality_support_assets,
    quality_support_investigations,
    scoped_csv,
    scoped_markdown,
)
from .policy import SUPERSEDED_POLICY, effective_policy
from .scenarios import scenarios
from .specs import (
    AS_OF,
    ORGANIZATION,
    USERS,
    VENDORS,
    WINDOW_ORDER,
    WINDOW_TIMES,
    Scenario,
    batch_days,
    next_batch_day,
    slot_id,
    weekdays_between,
)

BENCHMARK = "HubBench"
FAMILY_SLUG = "datadesk"
FAMILY_VERSION = "1.0.1"
PRIMARY_KEYS = {
    "backfill_jobs": "job_id",
    "run_schedules": "schedule_id",
    "adjustment_entries": "entry_id",
}
ITEM_FIELD = {
    "plan": "coverage_item_or_resource",
    "quantity": "controlled_item_or_record",
    "schedule": "affected_resource_or_operation",
}
GAP_FIELD = {
    "plan": "shortage_quantity",
    "quantity": "transaction_quantity",
    "schedule": "capacity_gap",
}
CASE_FOLDER = "Data Platform/Cases/{case}"
OPEN_SOURCE_ANCHORS = (
    {
        "name": "DataEngBench",
        "harbor_dataset": "snowflake-labs/data-eng-bench",
        "harbor_url": "https://hub.harborframework.com/datasets/snowflake-labs/data-eng-bench/latest",
        "upstream_url": "https://github.com/Snowflake-Labs/data-eng-bench",
        "license": "Apache-2.0",
        "evaluation_shape": "hermetic dbt data-engineering tasks with row-level deterministic verification",
    },
    {
        "name": "ADE-Bench",
        "harbor_dataset": "dbt-labs/ade-bench",
        "harbor_url": "https://hub.harborframework.com/datasets/dbt-labs/ade-bench/latest",
        "upstream_url": "https://github.com/dbt-labs/ade-bench",
        "license": "Apache-2.0",
        "evaluation_shape": "sandboxed analytics-engineering tasks with project and database state checks",
    },
)
WINDOW_HOURS = 4
WINDOW_MINUTES = WINDOW_HOURS * 60
SEED_JOB = {
    "job_id": "BF-7100",
    "partition_start": "2026-02-09",
    "partition_end": "2026-02-13",
    "partitions": 5,
    "cluster_id": "WH-STD",
    "start_time": "2026-02-13T01:00:00",
    "end_time": "2026-02-13T05:00:00",
    "status": "COMPLETED",
    "description": "January volume re-tier backfill",
    "requested_by": "data_platform_lead",
    "created_at": "2026-02-12T09:00:00",
    "revision": 1,
}
SEED_ADJUSTMENT = {
    "entry_id": "ADJ-3100",
    "period_start": "2026-01-05",
    "period_end": "2026-01-09",
    "direction": "add",
    "rows": 12,
    "reason": "January freight rebill timing correction",
    "approval_id": "AP-DD-0164",
    "status": "POSTED",
    "created_by": "finance_ops",
    "created_at": "2026-01-12T10:00:00",
    "revision": 1,
}


# --------------------------------------------------------------------------- #
# Calendar and cross-checks
# --------------------------------------------------------------------------- #


def calendar(scenario: Scenario) -> dict[tuple[str, str, str], dict[str, Any]]:
    overrides = {
        (item.day, item.cluster, item.window): item for item in scenario.windows
    }
    grid: dict[tuple[str, str, str], dict[str, Any]] = {}
    for day in batch_days():
        for cluster in scenario.clusters:
            for window in WINDOW_ORDER:
                key = (day, cluster.cluster_id, window)
                override = overrides.get(key)
                if override is None:
                    entry = {
                        "status": "busy",
                        "hold_reason": "scheduled load",
                        "job_id": None,
                    }
                elif override.status == "busy" and (
                    override.reason.startswith("SCH-")
                    or override.reason.startswith("BF-")
                ):
                    entry = {
                        "status": "busy",
                        "hold_reason": "reserved",
                        "job_id": override.reason,
                    }
                elif override.status == "free":
                    entry = {"status": "free", "hold_reason": None, "job_id": None}
                else:
                    entry = {
                        "status": override.status,
                        "hold_reason": override.reason or override.status,
                        "job_id": None,
                    }
                grid[key] = entry
    return grid


def _chronological(keys: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    order = {window: index for index, window in enumerate(WINDOW_ORDER)}
    return sorted(keys, key=lambda key: (key[0], order[key[2]], key[1]))


def free_windows(
    scenario: Scenario, clusters: list[str], start: str
) -> list[tuple[str, str, str]]:
    grid = calendar(scenario)
    keys = [
        key
        for key, entry in grid.items()
        if key[1] in clusters and entry["status"] == "free" and key[0] >= start
    ]
    return _chronological(keys)


def first_window_on_or_after(
    scenario: Scenario,
    start: str,
    windows_needed: int,
    clusters: list[str],
    *,
    full_day: bool,
) -> tuple[str, str, str] | None:
    grid = calendar(scenario)
    if full_day and windows_needed == 2:
        for day in batch_days():
            if day < start:
                continue
            for cluster in clusters:
                if all(
                    grid[(day, cluster, window)]["status"] == "free"
                    for window in WINDOW_ORDER
                ):
                    return day, cluster, "NIGHT+DAY"
        return None
    frees = free_windows(scenario, clusters, start)
    return frees[0] if frees else None


def _scoped_deliveries(scenario: Scenario, *, staged: bool) -> list[Any]:
    window = scenario.numbers["in_scope_window"]
    feed = scenario.primary_feed
    return [
        row
        for row in scenario.deliveries
        if row.feed_id == feed.feed_id
        and window[0] <= row.business_date <= window[1]
        and (row.status == "STAGED") == staged
    ]


def _partition_state(
    scenario: Scenario,
) -> tuple[list[str], set[str], set[str], set[str]]:
    window = scenario.numbers["partition_window"]
    days = weekdays_between(window[0], window[1])
    subject = scenario.model.model_id
    in_window = [
        run
        for run in scenario.runs
        if run.model_id == subject and window[0] <= run.partition_date <= window[1]
    ]
    success = {run.partition_date for run in in_window if run.status == "SUCCESS"}
    bad = {
        run.partition_date
        for run in in_window
        if run.status == "SUCCESS"
        and run.source_version == scenario.numbers["bad_source_version"]
    }
    attempted = {run.partition_date for run in in_window}
    return days, success, bad, attempted


def _schedule_runtime(scenario: Scenario) -> int:
    source = scenario.numbers["runtime_source"]
    if source == "full_refresh_run":
        candidates = [
            run
            for run in scenario.runs
            if run.model_id == scenario.model.model_id and run.trigger == "full_refresh"
        ]
        return max(candidates, key=lambda run: run.partition_date).duration_minutes
    if source == "displaced_schedules":
        return sum(
            schedule.duration_minutes
            for schedule in scenario.schedules
            if schedule.displaced
        )
    raise ValueError(f"unknown runtime source {source!r}")


def verify_numbers(scenario: Scenario) -> None:
    numbers = scenario.numbers
    problems: list[str] = []

    def check(label: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            problems.append(
                f"{label}: computed {actual!r} but scenario declares {expected!r}"
            )

    extra = scenario.extra_answer
    clusters = [str(value) for value in numbers["eligible_clusters"]]

    if scenario.mode == "quantity":
        loaded = _scoped_deliveries(scenario, staged=False)
        staged_rows = _scoped_deliveries(scenario, staged=True)
        observed = sum(row.rows_received for row in loaded)
        excluded = sum(
            row.rows_invalid + row.rows_duplicate + row.rows_late for row in loaded
        )
        for row in loaded:
            if row.late_duplicate > row.rows_late:
                problems.append(f"{row.delivery_id}: late_duplicate exceeds rows_late")
        check("observed", observed, numbers["observed"])
        check("excluded", excluded, numbers["excluded"])
        check("eligible", observed - excluded, numbers["eligible"])
        control = scenario.primary_control
        if control is None:
            problems.append("quantity scenario has no control total")
        else:
            check("scope", control.control_total_rows, numbers["scope"])
        staged_recoverable = sum(
            row.rows_received - row.rows_invalid - row.rows_duplicate - row.rows_late
            for row in staged_rows
        )
        rule = numbers["transaction_rule"]
        if rule == "gap":
            check(
                "transaction_quantity", numbers["gap"], numbers["transaction_quantity"]
            )
        elif rule == "duplicates":
            check(
                "transaction_quantity",
                sum(row.rows_duplicate for row in loaded),
                numbers["transaction_quantity"],
            )
        elif rule == "gap_minus_staged":
            check(
                "transaction_quantity",
                numbers["gap"] - staged_recoverable,
                numbers["transaction_quantity"],
            )
        else:
            problems.append(f"unknown transaction rule {rule!r}")
        if "late_file_rows" in extra:
            check(
                "late_file_rows",
                sum(row.rows_late for row in loaded),
                extra["late_file_rows"],
            )
        if "late_file_duplicate_rows" in extra:
            check(
                "late_file_duplicate_rows",
                sum(row.late_duplicate for row in loaded),
                extra["late_file_duplicate_rows"],
            )
        if "invalid_rows_excluded" in extra:
            check(
                "invalid_rows_excluded",
                sum(row.rows_invalid for row in loaded),
                extra["invalid_rows_excluded"],
            )
        if "in_scope_delivery_days" in extra:
            check(
                "in_scope_delivery_days", len(loaded), extra["in_scope_delivery_days"]
            )
        if "published_snapshot_rows" in extra:
            check(
                "published_snapshot_rows",
                numbers["eligible"] + sum(row.rows_duplicate for row in loaded),
                extra["published_snapshot_rows"],
            )
        if "failed_dedup_run_id" in extra:
            failed = [run.run_id for run in scenario.runs if run.status == "FAILED"]
            check("failed_dedup_run_id", failed, [extra["failed_dedup_run_id"]])
        if "duplicate_source_batch" in extra:
            noted = any(
                extra["duplicate_source_batch"] in row.note
                for row in loaded
                if row.rows_duplicate
            )
            if not noted:
                problems.append(
                    f"duplicate_source_batch {extra['duplicate_source_batch']!r} is not documented on a duplicate delivery"
                )
        if "snapshot_files_expected" in extra:
            check(
                "snapshot_files_expected",
                sum(row.files_expected for row in loaded),
                extra["snapshot_files_expected"],
            )
        if "snapshot_files_received" in extra:
            check(
                "snapshot_files_received",
                sum(row.files_received for row in loaded),
                extra["snapshot_files_received"],
            )
        if "missing_region_files" in extra:
            check(
                "missing_region_files",
                sum(row.files_expected - row.files_received for row in loaded),
                extra["missing_region_files"],
            )
        if "staged_recoverable_rows" in extra:
            check(
                "staged_recoverable_rows",
                staged_recoverable,
                extra["staged_recoverable_rows"],
            )
        check(
            "option1_completion",
            scenario.options[0].completion,
            numbers["standard_slot_date"],
        )
        check(
            "option3_completion",
            scenario.options[2].completion,
            numbers["expedited_slot_date"],
        )

    if scenario.mode == "plan":
        days, success, bad, attempted = _partition_state(scenario)
        check("scope", len(days), numbers["scope"])
        check("observed", len(success), numbers["observed"])
        check("excluded", len(bad), numbers["excluded"])
        check("eligible", len(success - bad), numbers["eligible"])
        minutes = max(
            run.duration_minutes
            for run in scenario.runs
            if run.model_id == scenario.model.model_id
            and run.status == "SUCCESS"
            and days[0] <= run.partition_date <= days[-1]
        )
        check("partition_minutes", minutes, numbers["partition_minutes"])
        for field in (
            "backfill_minutes_per_partition",
            "rebuild_minutes_per_partition",
        ):
            if field in extra:
                check(field, minutes, extra[field])
        if "partitions_per_window" in extra:
            check(
                "partitions_per_window",
                WINDOW_MINUTES // minutes,
                extra["partitions_per_window"],
            )
        if "windows_required" in extra:
            check(
                "windows_required",
                math.ceil(numbers["gap"] * minutes / WINDOW_MINUTES),
                extra["windows_required"],
            )
        for field in ("first_contaminated_partition", "first_affected_partition"):
            if field in extra:
                check(field, min(bad), extra[field])
        if "failed_partition_date" in extra:
            check(
                "failed_partition_date",
                sorted(attempted - success),
                [extra["failed_partition_date"]],
            )
        if "downstream_certified_dashboards" in extra:
            check(
                "downstream_certified_dashboards",
                sum(
                    1
                    for edge in scenario.lineage
                    if edge.parent == scenario.model.model_id
                ),
                extra["downstream_certified_dashboards"],
            )
        if "clean_reference_partitions" in extra:
            check(
                "clean_reference_partitions",
                len(success - bad),
                extra["clean_reference_partitions"],
            )
        check(
            "primary_partitions",
            len(
                weekdays_between(
                    scenario.primary_write.arguments["partition_start"],
                    scenario.primary_write.arguments["partition_end"],
                )
            ),
            numbers["gap"],
        )
        check(
            "option1_completion",
            scenario.options[0].completion,
            numbers["standard_slot_date"],
        )
        check(
            "option2_completion",
            scenario.options[1].completion,
            numbers["expedited_slot_date"],
        )

    if scenario.mode == "schedule":
        window = numbers["capacity_window"]
        days = weekdays_between(window[0], window[1])
        grid = calendar(scenario)
        keys = [
            (day, cluster, window_name)
            for day in days
            for cluster in clusters
            for window_name in WINDOW_ORDER
        ]
        candidate = len(keys) * WINDOW_HOURS
        free = sum(1 for key in keys if grid[key]["status"] == "free")
        check("observed", candidate, numbers["observed"])
        check("eligible", free * WINDOW_HOURS, numbers["eligible"])
        check("excluded", candidate - free * WINDOW_HOURS, numbers["excluded"])
        runtime = _schedule_runtime(scenario)
        check("scope", math.ceil(runtime / 60), numbers["scope"])
        if numbers.get("full_day"):
            slot = first_window_on_or_after(
                scenario, window[0], 2, clusters, full_day=True
            )
            check(
                "selected_resource",
                f"{slot[1]}/{slot[0]}/{slot[2]}" if slot else None,
                numbers["selected_resource"],
            )
            selected = next(option for option in scenario.options if option.recommended)
            check("selected completion", slot[0] if slot else None, selected.completion)
        else:
            frees = free_windows(scenario, clusters, window[0])
            check(
                "selected_resource",
                f"{frees[0][1]}/{frees[0][0]}/{frees[0][2]}" if frees else None,
                numbers["selected_resource"],
            )
            selected = next(option for option in scenario.options if option.recommended)
            needed = int(numbers["windows_needed"])
            check(
                "selected completion",
                frees[needed - 1][0] if len(frees) >= needed else None,
                selected.completion,
            )
        if "alternate_cluster_first_free" in numbers:
            alt_cluster, alt_date = numbers["alternate_cluster_first_free"]
            alt_frees = free_windows(scenario, [str(alt_cluster)], window[0])
            check(
                "alternate_cluster_first_free",
                alt_frees[0][0] if alt_frees else None,
                alt_date,
            )
        if "displaced_load_count" in extra:
            check(
                "displaced_load_count",
                sum(1 for schedule in scenario.schedules if schedule.displaced),
                extra["displaced_load_count"],
            )
        if "load_minutes_each" in extra:
            durations = {
                schedule.duration_minutes
                for schedule in scenario.schedules
                if schedule.displaced
            }
            check("load_minutes_each", sorted(durations), [extra["load_minutes_each"]])
        if "loads_per_window" in extra:
            check(
                "loads_per_window",
                WINDOW_MINUTES // extra["load_minutes_each"],
                extra["loads_per_window"],
            )
        if "xl_return_date" in extra:
            noted = any(
                cluster.note and extra["xl_return_date"] in cluster.note
                for cluster in scenario.clusters
            )
            if not noted:
                problems.append(
                    f"xl_return_date {extra['xl_return_date']!r} is not documented on a cluster status note"
                )
        if "refresh_runtime_minutes" in extra:
            check("refresh_runtime_minutes", runtime, extra["refresh_runtime_minutes"])
        if "windows_required" in extra:
            check(
                "windows_required",
                math.ceil(runtime / WINDOW_MINUTES),
                extra["windows_required"],
            )
        if "requested_day" in extra:
            check("requested_day", window[0], extra["requested_day"])
        if "last_full_refresh_date" in extra:
            reference = max(
                (run for run in scenario.runs if run.trigger == "full_refresh"),
                key=lambda run: run.partition_date,
            )
            check(
                "last_full_refresh_date",
                reference.partition_date,
                extra["last_full_refresh_date"],
            )

    gap = max(0, numbers["scope"] - numbers["eligible"])
    check("gap", gap, numbers["gap"])
    check(
        "standard_readiness",
        next_batch_day(scenario.confirmation.standard_date),
        scenario.standard_readiness,
    )
    check(
        "expedited_readiness",
        next_batch_day(scenario.confirmation.expedited_date),
        scenario.expedited_readiness,
    )
    readiness_windows = int(numbers.get("readiness_windows_needed", 1))
    for label, readiness in (
        ("standard_slot_date", scenario.standard_readiness),
        ("expedited_slot_date", scenario.expedited_readiness),
    ):
        slot = first_window_on_or_after(
            scenario,
            readiness,
            readiness_windows,
            clusters,
            full_day=readiness_windows == 2,
        )
        check(label, slot[0] if slot else None, numbers[label])
    if scenario.selected_slot_id not in {
        slot_id(cluster, day, window) for (day, cluster, window) in calendar(scenario)
    }:
        problems.append(
            f"selected slot {scenario.selected_slot_id} is not on the calendar"
        )
    if problems:
        raise ValueError(
            f"{scenario.task_id} scenario data disagrees with its declared numbers:\n  "
            + "\n  ".join(problems)
        )


# --------------------------------------------------------------------------- #
# Seed tables
# --------------------------------------------------------------------------- #


def _models_rows(scenario: Scenario) -> list[dict[str, Any]]:
    rows = []
    seen: set[str] = set()
    for model in (scenario.model, *scenario.other_models):
        if model.model_id in seen:
            continue
        seen.add(model.model_id)
        rows.append(
            {
                "model_id": model.model_id,
                "name": model.name,
                "layer": model.layer,
                "schema_name": model.schema_name,
                "materialization": model.materialization,
                "owner": model.owner,
                "status": model.status,
                "description": model.description or None,
            }
        )
    return rows


def seed_tables(
    scenario: Scenario,
    drive_files: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grid = calendar(scenario)
    slots = [
        {
            "slot_id": slot_id(cluster, day, window),
            "cluster_id": cluster,
            "service_date": day,
            "window_name": window,
            "start_time": WINDOW_TIMES[window][0],
            "end_time": WINDOW_TIMES[window][1],
            **entry,
        }
        for (day, cluster, window), entry in sorted(grid.items())
    ]
    return {
        "users": [dict(row) for row in USERS],
        "clusters": [
            {
                "cluster_id": c.cluster_id,
                "name": c.name,
                "status": c.status,
                "backfill_capable": int(c.backfill_capable),
                "status_note": c.note,
            }
            for c in scenario.clusters
        ],
        "models": _models_rows(scenario),
        "model_lineage": [
            {
                "parent_model_id": edge.parent,
                "child_model_id": edge.child,
                "relationship": edge.relationship,
            }
            for edge in scenario.lineage
        ],
        "sla_targets": [
            {
                "sla_id": s.sla_id,
                "model_id": s.model_id,
                "max_staleness_hours": s.max_staleness_hours,
                "refresh_deadline": s.refresh_deadline,
                "breach_escalation": s.breach_escalation,
                "business_reference": s.business_reference,
                "effective_from": s.effective_from,
                "status": s.status,
            }
            for s in scenario.slas
        ],
        "pipeline_runs": [
            {
                "run_id": r.run_id,
                "model_id": r.model_id,
                "partition_date": r.partition_date,
                "started_at": r.started_at,
                "duration_minutes": r.duration_minutes,
                "status": r.status,
                "rows_processed": r.rows_processed,
                "trigger": r.trigger,
                "source_version": r.source_version,
                "note": r.note or None,
            }
            for r in scenario.runs
        ],
        "run_schedules": [
            {
                "schedule_id": s.schedule_id,
                "model_id": s.model_id,
                "description": s.description,
                "duration_minutes": s.duration_minutes,
                "cluster_id": s.cluster_id,
                "start_time": s.start,
                "end_time": s.end,
                "status": s.status,
                "revision": 1,
                "last_updated": "2026-03-08T20:00:00",
            }
            for s in scenario.schedules
        ],
        "backfill_jobs": [
            {**SEED_JOB, "model_id": scenario.lineage[0].parent},
            *[
                {
                    "job_id": j.job_id,
                    "model_id": j.model_id,
                    "partition_start": j.partition_start,
                    "partition_end": j.partition_end,
                    "partitions": j.partitions,
                    "cluster_id": j.cluster_id,
                    "start_time": j.start,
                    "end_time": j.end,
                    "status": j.status,
                    "description": j.description or None,
                    "requested_by": "data_platform_lead",
                    "created_at": "2026-03-06T09:00:00",
                    "revision": 1,
                }
                for j in scenario.jobs
            ],
        ],
        "warehouse_slots": slots,
        "vendors": [dict(row) for row in VENDORS],
        "feeds": [
            {
                "feed_id": f.feed_id,
                "vendor_id": f.vendor_id,
                "name": f.name,
                "dataset": f.dataset,
                "cadence": f.cadence,
                "status": f.status,
            }
            for f in scenario.feeds
        ],
        "feed_deliveries": [
            {
                "delivery_id": d.delivery_id,
                "feed_id": d.feed_id,
                "business_date": d.business_date,
                "files_expected": d.files_expected,
                "files_received": d.files_received,
                "rows_received": d.rows_received,
                "rows_invalid": d.rows_invalid,
                "rows_duplicate": d.rows_duplicate,
                "rows_late": d.rows_late,
                "status": d.status,
                "received_at": d.received_at,
                "note": d.note or None,
            }
            for d in scenario.deliveries
        ],
        "vendor_confirmations": [
            {
                "confirmation_id": c.confirmation_id,
                "vendor_id": c.vendor_id,
                "feed_id": c.feed_id,
                "reference": c.reference,
                "scope_note": c.scope_note,
                "standard_redelivery_date": c.standard_date,
                "expedited_redelivery_date": c.expedited_date,
                "expedite_fee_usd": c.fee,
                "valid_until": c.valid_until,
                "status": c.status,
                "note": c.note,
            }
            for c in (scenario.confirmation, *scenario.other_confirmations)
        ],
        "recon_controls": [
            {
                "control_id": c.control_id,
                "model_id": c.model_id,
                "metric": c.metric,
                "period_start": c.period_start,
                "period_end": c.period_end,
                "control_total_rows": c.control_total_rows,
                "source": c.source,
                "published_at": c.published_at,
                "status": c.status,
                "note": c.note,
            }
            for c in scenario.controls
        ],
        "adjustment_entries": [
            {**SEED_ADJUSTMENT, "model_id": scenario.model.model_id}
        ],
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
                "approval_id": "AP-DD-0190",
                "subject": "Quarterly warehouse credit true-up",
                "approver_id": "U-VOSS",
                "approver_role": "data_platform_lead",
                "status": "APPROVED",
                "granted_on": "2026-01-15",
                "scope_json": json.dumps(
                    {"budget_usd": 18000, "quarter": "2026-Q1"}, sort_keys=True
                ),
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
                "attachments_json": json.dumps(
                    [
                        {"name": name, "mime_type": "application/pdf"}
                        for name in scenario.email.attachments
                    ]
                ),
                "labels": f"{scenario.email.labels},{scenario.case_reference}",
            },
            {
                "message_id": f"MSG-{scenario.ordinal:04d}-00",
                "thread_id": f"THR-{scenario.ordinal:04d}-OPS",
                "channel": "email",
                "sender": "rei.tanaka@tidewater.example",
                "recipients": "data-platform@tidewater.example",
                "subject": "Weekly platform ops note",
                "sent_at": "2026-03-08T18:30:00",
                "body": "Window calendar for the week of 2026-03-09 is posted on the shared drive. Protected close and replication windows are unchanged.",
                "attachments_json": "[]",
                "labels": "platform-ops",
            },
        ],
        "chat_threads": [
            {
                "thread_id": scenario.chat.thread_id,
                "channel": scenario.chat.channel,
                "title": scenario.chat.title,
                "messages_json": json.dumps(
                    [
                        {"author": author, "ts": ts, "text": text}
                        for author, ts, text in scenario.chat.messages
                    ]
                ),
            },
            {
                "thread_id": f"CHAT-{scenario.ordinal:04d}-GEN",
                "channel": "#data-platform",
                "title": "General — cost alerts and access requests",
                "messages_json": json.dumps(
                    [
                        {
                            "author": "Ingrid Voss",
                            "ts": "2026-03-06T16:20:00",
                            "text": "Reminder: file warehouse cost alerts in the tracker, not here.",
                        }
                    ]
                ),
            },
        ],
        "drive_files": drive_files,
        "evidence_files": evidence,
    }


# --------------------------------------------------------------------------- #
# Evidence room
# --------------------------------------------------------------------------- #


def _manifest_json(scenario: Scenario, model_id: str) -> str:
    models = {m.model_id: m for m in (scenario.model, *scenario.other_models)}
    model = models[model_id]
    parents = [
        models[edge.parent].name
        for edge in scenario.lineage
        if edge.child == model_id and edge.parent in models
    ]
    children = [
        models[edge.child].name
        for edge in scenario.lineage
        if edge.parent == model_id and edge.child in models
    ]
    payload = {
        "model_id": model.model_id,
        "unique_id": f"model.tidewater.{model.name}",
        "name": model.name,
        "layer": model.layer,
        "schema": model.schema_name,
        "materialization": model.materialization,
        "owner": model.owner,
        "status": model.status,
        "description": model.description,
        "depends_on": sorted(parents),
        "referenced_by": sorted(children),
        "generated_at": "2026-03-08T18:00:00",
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _confirmation_text(scenario: Scenario) -> str:
    c = scenario.confirmation
    vendor = next(row for row in VENDORS if row["vendor_id"] == c.vendor_id)
    return (
        f"{vendor['name']}\nRedelivery confirmation {c.reference} (system reference {c.confirmation_id})\n"
        f"Customer: Tidewater Supply Co. Data Platform, account {vendor['account_number']}\n"
        f"Case reference: {scenario.case_reference}\nFeed: {c.feed_id} — {scenario.primary_feed.name}\nScope: {c.scope_note}\n"
        f"Standard redelivery date: {c.standard_date}\nExpedited redelivery date: {c.expedited_date} (expedite fee USD {c.fee}, flat)\n"
        f"Valid until: {c.valid_until}\nNotes: {c.note}\n"
        "Delivery is to the ingestion bucket; certified load is subject to the customer's overnight validation.\n"
    )


def _decoy_asset(scenario: Scenario) -> dict[str, Any]:
    doc = scenario.decoy_doc
    if doc.kind == "policy_superseded":
        return asset(
            doc.path,
            kind=doc.kind,
            title=doc.title,
            source="drive",
            media_type=MARKDOWN,
            content=scoped_markdown(
                SUPERSEDED_POLICY,
                task_id=scenario.task_id,
                case_reference=scenario.case_reference,
            ),
            preview="2025 policy retained for audit only; superseded by v4.",
        )
    if doc.kind == "decoy_model":
        model_id = (
            doc.path.rsplit("/", 1)[-1].removeprefix("model-").removesuffix(".json")
        )
        return asset(
            doc.path,
            kind=doc.kind,
            title=doc.title,
            source="warehouse_export",
            media_type=JSON,
            content=_manifest_json(scenario, model_id),
            preview="A similarly named deprecated model that must not drive the decision.",
        )
    if doc.kind == "control_superseded":
        payload = {
            "statement": "Bluecrest processor statement",
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "settled_transaction_rows": 149882,
            "published_at": "2026-02-03T18:00:00",
            "status": "SUPERSEDED_PERIOD",
            "note": "January statement retained for audit; not the week-10 control.",
        }
        return asset(
            doc.path,
            kind=doc.kind,
            title=doc.title,
            source="drive",
            media_type=JSON,
            content=json.dumps(payload, indent=2, sort_keys=True) + "\n",
            preview="A prior-period statement that must not drive the reconciliation.",
        )
    if doc.media_type == XLSX:
        return asset(
            doc.path,
            kind=doc.kind,
            title=doc.title,
            source="drive",
            media_type=XLSX,
            rows=[list(row) for row in doc.rows or ()],
            preview=doc.title,
        )
    return asset(
        doc.path,
        kind=doc.kind,
        title=doc.title,
        source="drive",
        media_type=doc.media_type,
        content=doc.content,
        preview=doc.title,
    )


def _certification_rows(scenario: Scenario) -> list[list[Any]]:
    if scenario.mode == "quantity":
        rows: list[list[Any]] = [
            [
                "business_date",
                "rows_received",
                "rows_invalid",
                "rows_duplicate",
                "rows_late",
                "supported_rows",
                "status",
            ]
        ]
        for d in sorted(
            scenario.deliveries, key=lambda d: (d.business_date, d.delivery_id)
        ):
            supported = (
                d.rows_received - d.rows_invalid - d.rows_duplicate - d.rows_late
            )
            rows.append(
                [
                    d.business_date,
                    d.rows_received,
                    d.rows_invalid,
                    d.rows_duplicate,
                    d.rows_late,
                    supported,
                    d.status,
                ]
            )
        control = scenario.primary_control
        if control is not None:
            rows.append(
                [
                    "control_total",
                    "",
                    "",
                    "",
                    "",
                    control.control_total_rows,
                    control.control_id,
                ]
            )
        return rows
    if scenario.mode == "plan":
        days, success, bad, _ = _partition_state(scenario)
        rows = [["partition_date", "loaded", "source_version_state", "certified"]]
        by_partition = {
            run.partition_date: run
            for run in scenario.runs
            if run.model_id == scenario.model.model_id and run.status == "SUCCESS"
        }
        for day in days:
            run = by_partition.get(day)
            state = (
                "no successful load"
                if day not in success
                else ("contaminated" if day in bad else "clean")
            )
            rows.append(
                [
                    day,
                    "yes" if day in success else "no",
                    run.source_version if run else "",
                    "yes" if day in success and day not in bad else "no",
                ]
            )
            del state
        return rows
    rows = [["schedule_id", "model_id", "description", "duration_minutes", "status"]]
    for s in scenario.schedules:
        rows.append(
            [s.schedule_id, s.model_id, s.description, s.duration_minutes, s.status]
        )
    return rows


def build_assets(scenario: Scenario) -> list[dict[str, Any]]:
    case = scenario.case_reference
    grid = calendar(scenario)
    assets: list[dict[str, Any]] = [
        asset(
            "policy/data-platform-operations-policy.md",
            kind="policy",
            title="Data Platform Operations Policy v4 (effective)",
            source="drive",
            media_type=MARKDOWN,
            content=scoped_markdown(
                effective_policy(AS_OF), task_id=scenario.task_id, case_reference=case
            ),
            preview="Reconciliation, ingestion validation, window, backfill, and authority rules in force.",
        ),
    ]
    if scenario.decoy_doc.kind != "policy_superseded":
        assets.append(
            asset(
                "policy/superseded-data-platform-policy-2025.md",
                kind="policy_superseded",
                title="Data Platform Operations Policy 2025 (superseded)",
                source="drive",
                media_type=MARKDOWN,
                content=scoped_markdown(
                    SUPERSEDED_POLICY, task_id=scenario.task_id, case_reference=case
                ),
                preview="2025 policy retained for audit only; superseded by v4.",
            )
        )
    assets.append(_decoy_asset(scenario))
    assets.extend(
        [
            asset(
                f"catalog/model-{scenario.model.model_id}.json",
                kind="model_manifest",
                title=f"Catalog manifest — {scenario.model.name}",
                source="warehouse_export",
                media_type=JSON,
                content=_manifest_json(scenario, scenario.model.model_id),
                preview="The subject model with its lineage, owner, and materialization.",
            ),
            asset(
                "sla/freshness-sla-register.csv",
                kind="sla_register",
                title="Freshness SLA register",
                source="warehouse_export",
                media_type=CSV,
                content=scoped_csv(
                    "sla_id,model_id,max_staleness_hours,refresh_deadline,breach_escalation,business_reference,status\n"
                    + "".join(
                        f"{s.sla_id},{s.model_id},{s.max_staleness_hours},{s.refresh_deadline},{s.breach_escalation},{s.business_reference},{s.status}\n"
                        for s in scenario.slas
                    ),
                    task_id=scenario.task_id,
                    case_reference=case,
                ),
                preview="Freshness targets and escalation paths for the certified models.",
            ),
            asset(
                f"pipelines/run-history-{scenario.model.model_id}.xlsx",
                kind="run_history_workbook",
                title=f"Run history — {scenario.model.name}",
                source="pipeline_export",
                media_type=XLSX,
                rows=[
                    [
                        "run_id",
                        "model_id",
                        "partition_date",
                        "started_at",
                        "duration_minutes",
                        "status",
                        "rows_processed",
                        "trigger",
                        "source_version",
                        "note",
                    ],
                    *[
                        [
                            r.run_id,
                            r.model_id,
                            r.partition_date,
                            r.started_at,
                            r.duration_minutes,
                            r.status,
                            r.rows_processed,
                            r.trigger,
                            r.source_version or "",
                            r.note,
                        ]
                        for r in scenario.runs
                    ],
                ],
                preview="Durations, statuses, source versions, and rows processed for the relevant runs.",
            ),
            asset(
                f"feeds/delivery-log-{scenario.primary_feed.feed_id}.csv",
                kind="delivery_log",
                title=f"Delivery log — {scenario.primary_feed.name}",
                source="ingestion_export",
                media_type=CSV,
                content="delivery_id,feed_id,business_date,files_expected,files_received,rows_received,rows_invalid,rows_duplicate,rows_late,status,received_at,note\n"
                + "".join(
                    f'{d.delivery_id},{d.feed_id},{d.business_date},{d.files_expected},{d.files_received},{d.rows_received},{d.rows_invalid},{d.rows_duplicate},{d.rows_late},{d.status},{d.received_at},"{d.note}"\n'
                    for d in scenario.deliveries
                ),
                preview="Files and row counts per business date with invalid, duplicate, and late buckets.",
            ),
            asset(
                f"feeds/redelivery-confirmation-{scenario.confirmation.reference}.pdf",
                kind="vendor_confirmation",
                title=f"Vendor redelivery confirmation {scenario.confirmation.reference}",
                source="email_attachment",
                media_type=PDF,
                content=_confirmation_text(scenario),
                preview="Standard and expedited redelivery dates, fee, and validity.",
            ),
            asset(
                "warehouse/window-calendar-2026-03-09.xlsx",
                kind="window_calendar",
                title="Warehouse window calendar, three weeks from 2026-03-09",
                source="warehouse_export",
                media_type=XLSX,
                rows=[
                    [
                        "service_date",
                        "cluster_id",
                        "window",
                        "start",
                        "end",
                        "status",
                        "hold_reason",
                    ],
                    *[
                        [
                            day,
                            cluster,
                            window,
                            WINDOW_TIMES[window][0],
                            WINDOW_TIMES[window][1],
                            entry["status"],
                            entry["hold_reason"] or "",
                        ]
                        for (day, cluster, window), entry in sorted(grid.items())
                    ],
                ],
                preview="Every batch window with free / busy / protected / blocked status.",
            ),
            asset(
                "warehouse/cluster-roster.csv",
                kind="cluster_roster",
                title="Cluster roster and backfill capability",
                source="warehouse_export",
                media_type=CSV,
                content=scoped_csv(
                    "cluster_id,name,status,backfill_capable,note\n"
                    + "".join(
                        f"{c.cluster_id},{c.name},{c.status},{'yes' if c.backfill_capable else 'no'},{c.note or ''}\n"
                        for c in scenario.clusters
                    ),
                    task_id=scenario.task_id,
                    case_reference=case,
                ),
                preview="Cluster status, write grants, and backfill capability.",
            ),
            asset(
                f"recon/certification-workbook-{case}.xlsx",
                kind="certification_workbook",
                title=f"Certification workbook — {case}",
                source="recon_export",
                media_type=XLSX,
                rows=_certification_rows(scenario),
                preview="Per-record certification state reconciled against the controlling evidence.",
            ),
            asset(
                "pipelines/schedule-register.csv",
                kind="schedule_register",
                title="Run schedule register",
                source="pipeline_export",
                media_type=CSV,
                content=scoped_csv(
                    "schedule_id,model_id,description,duration_minutes,cluster_id,start_time,end_time,status\n"
                    + "".join(
                        f"{s.schedule_id},{s.model_id},{s.description},{s.duration_minutes},{s.cluster_id or ''},{s.start or ''},{s.end or ''},{s.status}\n"
                        for s in scenario.schedules
                    ),
                    task_id=scenario.task_id,
                    case_reference=case,
                ),
                preview="Recurring and pending schedules with durations and windows.",
            ),
            asset(
                f"messages/{scenario.email.thread_id}.eml",
                kind="email",
                title=scenario.email.subject,
                source="messages",
                media_type=EML,
                content=eml(
                    from_addr=scenario.email.sender,
                    to_addr=scenario.email.recipients,
                    subject=scenario.email.subject,
                    date=scenario.email.sent_at,
                    message_id=f"{scenario.email.message_id}@tidewater.example",
                    body=scenario.email.body,
                    attachments=list(scenario.email.attachments),
                ),
                preview="The request and the control date, in the requester's words.",
            ),
            asset(
                f"chat/{scenario.chat.thread_id}.json",
                kind="chat_thread",
                title=scenario.chat.title,
                source="chat",
                media_type=JSON,
                content=json.dumps(
                    {
                        "thread_id": scenario.chat.thread_id,
                        "channel": scenario.chat.channel,
                        "title": scenario.chat.title,
                        "messages": [
                            {"author": a, "ts": t, "text": x}
                            for a, t, x in scenario.chat.messages
                        ],
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                preview="Team chat with exclusion, window, and authority remarks.",
            ),
            asset(
                f"approvals/approval-{scenario.approval.approval_id}.json",
                kind="approval",
                title=f"Approval record {scenario.approval.approval_id}",
                source="approvals_export",
                media_type=JSON,
                content=json.dumps(
                    {
                        "approval_id": scenario.approval.approval_id,
                        "case_reference": case,
                        "subject": scenario.approval.subject,
                        "approver_id": scenario.approval.approver_id,
                        "approver_role": scenario.approval.approver_role,
                        "status": "APPROVED",
                        "granted_on": scenario.approval.granted_on,
                        "scope": scenario.approval.scope,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                preview="Exactly what is approved, for which record, and what is not.",
            ),
            asset(
                f"exports/starting-state-{scenario.task_id}.json",
                kind="starting_state",
                title="Starting-state export (schedules, backfills, adjustments)",
                source="pipeline_export",
                media_type=JSON,
                content=json.dumps(
                    {
                        "case_reference": case,
                        "as_of": AS_OF,
                        "run_schedules": [
                            {
                                "schedule_id": s.schedule_id,
                                "model_id": s.model_id,
                                "status": s.status,
                                "cluster_id": s.cluster_id,
                            }
                            for s in scenario.schedules
                        ],
                        "backfill_jobs": [
                            {"job_id": SEED_JOB["job_id"], "status": SEED_JOB["status"]}
                        ],
                        "adjustment_entries": [
                            {
                                "entry_id": SEED_ADJUSTMENT["entry_id"],
                                "status": SEED_ADJUSTMENT["status"],
                            }
                        ],
                        "note": "Snapshot before any action; row order does not indicate applicability.",
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                preview="Snapshot of pipeline and reconciliation state before any action.",
            ),
        ]
    )
    if scenario.controls:
        control = scenario.controls[0]
        assets.append(
            asset(
                f"recon/finance-control-{control.control_id}.json",
                kind="control_total",
                title=f"Published control total {control.control_id}",
                source="recon_export",
                media_type=JSON,
                content=json.dumps(
                    {
                        "control_id": control.control_id,
                        "model_id": control.model_id,
                        "metric": control.metric,
                        "period_start": control.period_start,
                        "period_end": control.period_end,
                        "control_total_rows": control.control_total_rows,
                        "source": control.source,
                        "published_at": control.published_at,
                        "status": control.status,
                        "note": control.note,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                preview="The independently published control total the certified mart must tie to.",
            )
        )
    for doc in scenario.docs:
        if doc.media_type == XLSX:
            assets.append(
                asset(
                    doc.path,
                    kind=doc.kind,
                    title=doc.title,
                    source="drive",
                    media_type=XLSX,
                    rows=[list(row) for row in doc.rows or ()],
                    preview=doc.title,
                )
            )
        else:
            assets.append(
                asset(
                    doc.path,
                    kind=doc.kind,
                    title=doc.title,
                    source="drive",
                    media_type=doc.media_type,
                    content=doc.content,
                    preview=doc.title,
                )
            )
    assets.extend(
        quality_support_assets(
            task_id=scenario.task_id,
            ordinal=scenario.ordinal,
            case_reference=case,
            family_slug=FAMILY_SLUG,
            family_name="DataDesk",
            organization_name=ORGANIZATION["name"],
            subject_id=scenario.item,
            as_of=AS_OF,
            current_revision=scenario.revision,
            anchors=OPEN_SOURCE_ANCHORS,
        )
    )
    index = {
        "case_reference": case,
        "as_of": AS_OF,
        "files": [
            {
                "path": a["path"],
                "kind": a["kind"],
                "media_type": a["media_type"],
                "sha256": a["sha256"],
            }
            for a in assets
        ],
    }
    assets.append(
        asset(
            "audit/evidence-index.yaml",
            kind="evidence_index",
            title="Evidence index",
            source="drive",
            media_type=YAML,
            content=yaml_lines(index) + "\n",
            preview="Digest index of every evidence file in the room.",
        )
    )
    for position, record in enumerate(assets, start=1):
        record["asset_id"] = f"{scenario.task_id}-{position:02d}"
    return assets


def _folder(scenario: Scenario, record: dict[str, Any]) -> str:
    if record["kind"] == "policy":
        return "Data Platform/Policies"
    if record["kind"] == "policy_superseded":
        return "Data Platform/Policies/Archive"
    return CASE_FOLDER.format(case=scenario.case_reference)


def mount_drive(
    scenario: Scenario, assets: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    files: list[dict[str, Any]] = []
    ids: dict[str, str] = {}
    counter = 0
    for record in assets:
        if record["media_type"] == EML or record["kind"] == "chat_thread":
            continue
        counter += 1
        file_id = f"DRV-{scenario.ordinal:03d}-{counter:02d}"
        files.append(
            {
                "file_id": file_id,
                "name": record["path"].rsplit("/", 1)[-1],
                "mime_type": record["media_type"],
                "modified_time": "2026-03-08T19:30:00",
                "folder": _folder(scenario, record),
                "content": record["content"],
                "sha256": record["sha256"],
            }
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
    unauthorized = next(
        option for option in scenario.options if option.approval == UNAUTHORIZED
    )
    accelerated = scenario.options[1]
    return (
        {
            "id": "authoritative_identity",
            "sources": ["warehouse", "messages"],
            "statement": f"{scenario.case_reference}: {notes['identity']}; the effective policy revision is {scenario.revision}.",
            "rubric": f"Located {scenario.item} using immutable identifiers and preserved effective policy revision {scenario.revision}: {notes['identity']}.",
        },
        {
            "id": "effective_requirement",
            "sources": ["recon", "drive"],
            "statement": f"The controlling evidence and effective policy establish {labels.scope_label} = {numbers['scope']} {labels.unit}: {notes['requirement']}. The control date is {scenario.business_need} ({scenario.business_need_reason}).",
            "rubric": f"Applied the controlling evidence and the effective policy to establish {numbers['scope']} {labels.unit} for {labels.scope_label}, with control date {scenario.business_need}.",
        },
        {
            "id": "eligible_coverage",
            "sources": ["feeds", "pipelines", "drive"],
            "statement": f"{notes['coverage']}; eligibility requires netting the exclusions rather than trusting a header total.",
            "rubric": f"Reconciled {numbers['observed']} observed less {numbers['excluded']} excluded to {numbers['eligible']} supported {labels.unit} for {labels.eligible_label}.",
        },
        {
            "id": "conditional_external_recovery",
            "sources": ["feeds", "messages"],
            "statement": f"{labels.external_label}: {notes['external']}; a vendor confirmation alone proves neither validation nor load.",
            "rubric": f"Used the independently confirmed {scenario.expedited_readiness} expedited readiness input for {accelerated.id}, then separately derived its {accelerated.completion} operating outcome under {labels.constraint_label} instead of treating a vendor promise as authorization or a completion date.",
        },
        {
            "id": "finite_capacity",
            "sources": ["warehouse", "drive"],
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
            "sources": ["messages", "chat"],
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
        transaction_quantity=int(numbers["transaction_quantity"])
        if "transaction_quantity" in numbers
        else None,
        selected_resource=str(numbers["selected_resource"])
        if "selected_resource" in numbers
        else None,
        extra_answer=dict(scenario.extra_answer),
        extra_descriptions=dict(scenario.extra_descriptions),
        extra_calculations=scenario.extra_calculations,
        facts=build_facts(scenario),
    )
    return build_decision_model(inputs)


# --------------------------------------------------------------------------- #
# Investigations, oracle steps, contract
# --------------------------------------------------------------------------- #


def _investigation(
    number: int,
    milestone: str,
    description: str,
    tool: str,
    arguments: dict[str, Any],
    expected: dict[str, Any],
    weight: float = 1.0,
) -> dict[str, Any]:
    return {
        "id": f"investigation_{number:02d}",
        "milestone_id": milestone,
        "description": description,
        "weight": weight,
        "before_primary_mutation": True,
        "any_of": [
            {
                "tool": tool,
                "arguments": arguments,
                "match": "result_contains",
                "expected_result_contains": expected,
            }
        ],
    }


def _requirement_read(
    scenario: Scenario,
) -> tuple[str, dict[str, Any], dict[str, Any], str]:
    subject = scenario.model.model_id
    if scenario.mode == "quantity":
        control = scenario.primary_control
        return (
            "recon.controls.get",
            {"control_id": control.control_id},
            {
                "control_id": control.control_id,
                "control_total_rows": control.control_total_rows,
            },
            f"Read the published control total {control.control_id} that fixes the requirement the certified mart must tie to; did not infer the requirement from the dashboard headline.",
        )
    if scenario.mode == "plan":
        window = scenario.numbers["partition_window"]
        first = min(
            (
                run
                for run in scenario.runs
                if run.model_id == subject
                and window[0] <= run.partition_date <= window[1]
            ),
            key=lambda run: (run.partition_date, run.run_id),
        )
        return (
            "pipelines.runs.list",
            {
                "model_id": subject,
                "partition_start": window[0],
                "partition_end": window[1],
            },
            {"runs": [{"run_id": first.run_id}]},
            f"Listed the {subject} load runs across the certification window to establish which partitions loaded, from which source version, and how long each took.",
        )
    return (
        "pipelines.schedules.get",
        {"schedule_id": scenario.item},
        {"schedule_id": scenario.item, "status": "pending"},
        f"Read the displaced schedule record {scenario.item} for its runtime, model, and pending state before promising any window.",
    )


def _correlation_runs_read(
    scenario: Scenario,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    subject = scenario.model.model_id
    failed = [
        run
        for run in scenario.runs
        if run.status == "FAILED" and run.model_id != subject
    ]
    if scenario.mode == "quantity" and failed:
        return (
            {"model_id": failed[0].model_id, "status": "FAILED"},
            {"runs": [{"run_id": failed[0].run_id}]},
            f"Correlated the failed staging run {failed[0].run_id} that let the exception through, by immutable run id.",
        )
    if scenario.mode == "plan":
        parent = scenario.lineage[0].parent
        parent_runs = sorted(
            (run for run in scenario.runs if run.model_id == parent),
            key=lambda run: (run.partition_date, run.run_id),
        )
        args = {
            "model_id": parent,
            "partition_start": parent_runs[0].partition_date,
            "partition_end": parent_runs[-1].partition_date,
        }
        return (
            args,
            {"runs": [{"run_id": parent_runs[0].run_id}]},
            f"Correlated the {parent} source loads that carried the vendor file versions into the affected partitions, by immutable run id.",
        )
    if scenario.mode == "schedule":
        refresh = [
            run
            for run in scenario.runs
            if run.model_id == subject and run.trigger == "full_refresh"
        ]
        if refresh:
            newest = max(refresh, key=lambda run: run.partition_date)
            return (
                {"model_id": subject, "trigger": "full_refresh"},
                {"runs": [{"run_id": newest.run_id}]},
                f"Correlated the completed reference refresh {newest.run_id} whose measured runtime sizes this job, by immutable run id.",
            )
    subject_runs = sorted(
        (run for run in scenario.runs if run.model_id == subject),
        key=lambda run: (run.partition_date, run.run_id),
    )
    args = {
        "model_id": subject,
        "partition_start": subject_runs[0].partition_date,
        "partition_end": subject_runs[-1].partition_date,
    }
    return (
        args,
        {"runs": [{"run_id": subject_runs[0].run_id}]},
        f"Correlated the recent {subject} load runs that fix the record's current certified state, by immutable run id.",
    )


def build_investigations(
    scenario: Scenario, file_ids: dict[str, str]
) -> list[dict[str, Any]]:
    case = scenario.case_reference
    model = scenario.model
    policy_id = file_ids["policy/data-platform-operations-policy.md"]
    approval_id = file_ids[f"approvals/approval-{scenario.approval.approval_id}.json"]
    manifest_id = file_ids[f"catalog/model-{model.model_id}.json"]
    parent_id = scenario.lineage[0].parent
    subject_sla = next(s for s in scenario.slas if s.model_id == model.model_id)
    deliveries = sorted(
        scenario.deliveries, key=lambda d: (d.business_date, d.delivery_id)
    )
    (
        requirement_tool,
        requirement_args,
        requirement_expected,
        requirement_description,
    ) = _requirement_read(scenario)
    correlation_args, correlation_expected, correlation_description = (
        _correlation_runs_read(scenario)
    )
    investigations = [
        _investigation(
            1,
            "investigation.scope",
            f"Established the isolated {case} scope, immutable handles, mounted systems, and evidence index before investigating {scenario.item}.",
            CONTEXT_TOOL,
            {},
            {"reference_records": {"case_reference": case}},
        ),
        _investigation(
            2,
            "investigation.scope",
            f"Located the task-scoped correspondence for {case} by searching the mailbox before opening any message; did not rely on a guessed sender or filename.",
            "messages.list",
            {"q": case},
            {"messages": [{"id": scenario.email.message_id}]},
        ),
        _investigation(
            3,
            "investigation.scope",
            f"Resolved {model.name} to the immutable catalog record {model.model_id} through a catalog search rather than assuming a similarly named or deprecated model.",
            "warehouse.models.search",
            {"name": model.name},
            {"models": [{"model_id": model.model_id}]},
        ),
        _investigation(
            4,
            "investigation.scope",
            f"Listed the {case} case folder on the shared drive and identified the approval record and the catalog manifest by immutable file id.",
            "drive.files.list",
            {"q": case},
            {"files": [{"id": approval_id}, {"id": manifest_id}]},
        ),
        _investigation(
            5,
            "investigation.scope",
            "Listed the policy folder and distinguished the effective v4 policy from the superseded 2025 edition by file identity, not title.",
            "drive.files.list",
            {"q": "policy"},
            {"files": [{"id": policy_id}]},
        ),
        _investigation(
            6,
            "investigation.requirements",
            f"Read the catalog record for {model.model_id}: layer, schema, materialization, owner, and active status.",
            "warehouse.models.get",
            {"model_id": model.model_id},
            {"model_id": model.model_id, "status": "ACTIVE"},
        ),
        _investigation(
            7,
            "investigation.requirements",
            f"Read the lineage of {model.model_id} and fixed its actual source ({parent_id}) and certified consumers before blaming or rebuilding anything.",
            "warehouse.lineage.get",
            {"model_id": model.model_id},
            {"model_id": model.model_id, "parents": [{"model_id": parent_id}]},
        ),
        _investigation(
            8,
            "investigation.requirements",
            "Exported the effective v4 policy for the reconciliation, validation, window, and authority rules; did not apply the superseded 2025 edition.",
            "drive.files.export",
            {"file_id": policy_id},
            {"file_id": policy_id},
        ),
        _investigation(
            9,
            "investigation.requirements",
            f"Read the active freshness SLA for {model.model_id}: staleness limit, refresh deadline, and the business surface it protects.",
            "warehouse.sla.get",
            {"model_id": model.model_id},
            {"sla_id": subject_sla.sla_id, "model_id": model.model_id},
        ),
        _investigation(
            10,
            "investigation.requirements",
            requirement_description,
            requirement_tool,
            requirement_args,
            requirement_expected,
        ),
        _investigation(
            11,
            "investigation.constraints",
            f"Listed the {scenario.primary_feed.feed_id} delivery log with files, rows, and the invalid / duplicate / late buckets before netting the supported coverage.",
            "feeds.deliveries.list",
            {
                "feed_id": scenario.primary_feed.feed_id,
                "start_date": deliveries[0].business_date,
                "end_date": deliveries[-1].business_date,
            },
            {"deliveries": [{"delivery_id": deliveries[0].delivery_id}]},
        ),
        _investigation(
            12,
            "investigation.constraints",
            f"Read the warehouse window calendar across the {scenario.slots_query['start_date']} capacity window to find usable free windows that displace no protected or blocked load.",
            "warehouse.slots.list",
            {**scenario.slots_query},
            {"slots": [{"id": scenario.selected_slot_id}]},
        ),
        _investigation(
            13,
            "investigation.constraints",
            f"Read the vendor redelivery confirmation {scenario.confirmation.confirmation_id} for the independently confirmed standard and expedited dates and the expedite fee.",
            "feeds.confirmations.get",
            {"confirmation_id": scenario.confirmation.confirmation_id},
            {
                "confirmation_id": scenario.confirmation.confirmation_id,
                "standard_redelivery_date": scenario.confirmation.standard_date,
            },
        ),
        _investigation(
            14,
            "investigation.authority",
            f"Read approval {scenario.approval.approval_id} for its exact scope: model or schedule, period, row or window limits, fees, and what it does not cover.",
            "approvals.get",
            {"approval_id": scenario.approval.approval_id},
            {"approval_id": scenario.approval.approval_id},
        ),
        _investigation(
            15,
            "investigation.authority",
            "Exported the approval record on the drive and confirmed it matches the workflow record before relying on it.",
            "drive.files.export",
            {"file_id": approval_id},
            {"file_id": approval_id},
        ),
        _investigation(
            16,
            "investigation.erp_correlation",
            f"Read the request message {scenario.email.message_id} for the documented control date and the business need in the requester's words.",
            "messages.get",
            {"message_id": scenario.email.message_id},
            {"id": scenario.email.message_id},
        ),
        _investigation(
            17,
            "investigation.erp_correlation",
            f"Read the team chat thread {scenario.chat.thread_id} for exclusion, window, and authority remarks that qualify the system records.",
            "chat.threads.get",
            {"thread_id": scenario.chat.thread_id},
            {"thread_id": scenario.chat.thread_id},
        ),
        _investigation(
            18,
            "investigation.erp_correlation",
            correlation_description,
            "pipelines.runs.list",
            correlation_args,
            correlation_expected,
        ),
    ]
    investigations.extend(
        quality_support_investigations(
            start_number=len(investigations) + 1,
            file_ids=file_ids,
            make_investigation=_investigation,
            case_reference=case,
            subject_id=scenario.item,
        )
    )
    return investigations


def build_oracle_steps(
    scenario: Scenario, investigations: list[dict[str, Any]], model: dict[str, Any]
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [
        {"phase": "context", "tool": CONTEXT_TOOL, "arguments": {}, "control": True}
    ]
    order = [2, 16, 3, 10, 6, 7, 4, 5, 8, 9, 11, 18, 12, 13, 14, 15, 17]
    by_number = {int(item["id"].rsplit("_", 1)[1]): item for item in investigations}
    order.extend(number for number in sorted(by_number) if number not in order)
    for number in order:
        call = by_number[number]["any_of"][0]
        steps.append(
            {
                "phase": "investigation",
                "tool": call["tool"],
                "arguments": call["arguments"],
                "control": True,
            }
        )
    primary = scenario.primary_write
    steps.append(
        {
            "phase": "primary_mutation",
            "tool": primary.tool,
            "arguments": primary.arguments,
            "control": False,
        }
    )
    steps.append(
        {
            "phase": "post_write_verification",
            "tool": primary.readback_tool,
            "arguments": primary.readback_arguments,
            "control": True,
        }
    )
    steps.append(
        {
            "phase": "collaboration",
            "tool": "notes.drafts.create",
            "arguments": {
                "recipient": scenario.collaboration["recipient"],
                "subject": scenario.collaboration["subject"],
                "body": scenario.collaboration["body"],
                "related_model_id": scenario.model.model_id,
                "related_case": scenario.case_reference,
            },
            "control": False,
        }
    )
    steps.append(
        {
            "phase": "answer",
            "tool": SUBMIT_TOOL,
            "arguments": dict(model["answer"]),
            "control": False,
        }
    )
    return steps


def build_assertions(scenario: Scenario, model: dict[str, Any]) -> list[dict[str, Any]]:
    primary = scenario.primary_write
    task_id = scenario.task_id
    selected = model["selected_option"]
    completion = model["selected_completion"]
    payload_values = ", ".join(
        f"{key}={value!r}" for key, value in primary.arguments.items()
    )
    return [
        {
            "id": "mutation_01",
            "milestone_id": "state.primary",
            "description": f"Required {scenario.item} to reach business outcome {primary.outcome_label!r} through {primary.tool} with exact provider-critical values {payload_values}. The audited change binds selected option {selected}, approval {scenario.approval.approval_id}, and constraint {scenario.labels.constraint_label}; no other record satisfies this state criterion.",
            "table": "mutations",
            "where": {"task_id": task_id, "mutation_id": f"{task_id}-mutation-01"},
            "values": {
                "tool": primary.tool,
                "table_name": primary.table,
                "record_id": primary.record_id,
                "status": primary.status,
            },
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
            "values": {
                "tool": "notes.drafts.create",
                "table_name": "note_drafts",
                "status": "DRAFT",
            },
            "payload_contains": {
                "tool": "notes.drafts.create",
                "arguments": {"recipient": scenario.collaboration["recipient"]},
            },
            "payload_text_contains": [selected, completion],
            "payload_text_any_of": [
                [scenario.case_reference, scenario.model.model_id, scenario.item]
            ],
            "weight": 1.5,
        },
        {
            "id": "containment_01",
            "milestone_id": "containment.scope",
            "description": f"Made exactly two state changes for {scenario.case_reference}: the primary change and the stakeholder draft; no additional backfill, schedule change, or adjustment.",
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
        {
            "asset_id": a["asset_id"],
            "task_id": scenario.task_id,
            "path": a["path"],
            "title": a["title"],
            "kind": a["kind"],
            "source": a["source"],
            "media_type": a["media_type"],
            "sha256": a["sha256"],
        }
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
        "any_of": [
            {
                "tool": primary.readback_tool,
                "arguments": primary.readback_arguments,
                "match": "result_contains",
                "expected_result_contains": primary.readback_expected,
            }
        ],
        "expected_result_contains": primary.readback_expected,
        "target_identity": primary.readback_arguments,
        "materializes_new_record": primary.tool.endswith(".create"),
        "description": f"Read {primary.record_id} back through {primary.readback_tool} after the change and confirmed the persisted provider values ({', '.join(f'{k}={v!r}' for k, v in primary.readback_expected.items())}) rather than relying on the write acknowledgement.",
        "weight": 2.0,
    }
    answer = model["answer"]
    checks = answer_checks(
        answer,
        [
            "recommended_option",
            "recommended_outcome_date",
            ITEM_FIELD[scenario.mode],
            GAP_FIELD[scenario.mode],
            "decision_timing_status",
        ],
        f"{scenario.item}, policy revision {scenario.revision}, and the selected {model['selected_option']} outcome",
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
        correlated_systems=["warehouse", "pipelines", "feeds", "messages", "chat"],
    )
    rubric = build_rubric_milestones(
        descriptions=descriptions,
        investigations=investigations,
        calculations=model["calculations"],
        assertions=assertions,
        answer_checks=checks,
        post_write_verifications=[readback],
    )
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
        "decision_model": {
            key: value
            for key, value in model.items()
            if key not in {"answer", "answer_descriptions"}
        },
        "answer_schema": answer_schema(
            answer, model["answer_descriptions"], option_ids
        ),
        "expected": {
            "answer": answer,
            "answer_checks": checks,
            "calculations": model["calculations"],
            "assertions": assertions,
            "investigations": investigations,
            "post_write_verifications": [readback],
        },
        "required_investigations": investigations,
        "required_reads": [
            step["tool"]
            for step in steps
            if step["control"] and step["phase"] in {"context", "investigation"}
        ],
        "required_read_calls": [item["any_of"][0] for item in investigations],
        "post_write_verifications": [readback],
        "oracle_steps": steps,
        "sequence_signature": sequence_signature(steps),
        "allowed_write_tables": sorted(
            {
                primary.table,
                *primary.extra_tables,
                "note_drafts",
                "mutations",
                "answers",
                "audit_log",
            }
        ),
        "rubric_milestones": rubric,
        "negative_controls": {
            "unauthorized_write": dict(scenario.unauthorized_write),
            "wrong_evidence": {
                "tool": "drive.files.export",
                "arguments": {"file_id": file_ids[decoy_path]},
            },
        },
        "reference_records": {
            "case_reference": scenario.case_reference,
            "warehouse": {
                "model_id": scenario.model.model_id,
                "model_search": {
                    "tool": "warehouse.models.search",
                    "arguments": {"name": scenario.model.name},
                },
            },
            "messages": {"search_query": scenario.case_reference},
            "drive": {
                "case_folder_query": scenario.case_reference,
                "policy_query": "policy",
            },
            "feeds": {
                "feed_id": scenario.primary_feed.feed_id,
                "confirmation_id": scenario.confirmation.confirmation_id,
            },
            "pipelines": {"models": sorted({run.model_id for run in scenario.runs})},
            "recon": {"control_id": scenario.primary_control.control_id}
            if scenario.primary_control
            else {"controls": "none published for this case"},
            "warehouse_calendar": {"window": scenario.slots_query},
            "approvals": {"approval_id": scenario.approval.approval_id},
            "chat": {"thread_id": scenario.chat.thread_id},
        },
        "starting_records": [
            *[
                {
                    "system": "pipelines",
                    "resource_type": "RunSchedule",
                    "resource_id": s.schedule_id,
                    "status": s.status,
                }
                for s in scenario.schedules
            ],
            {
                "system": "pipelines",
                "resource_type": "BackfillJob",
                "resource_id": SEED_JOB["job_id"],
                "status": SEED_JOB["status"],
            },
            {
                "system": "recon",
                "resource_type": "AdjustmentEntry",
                "resource_id": SEED_ADJUSTMENT["entry_id"],
                "status": SEED_ADJUSTMENT["status"],
            },
        ],
        "evaluation": {
            "metric": "HubScore",
            "strict_pass": "every rubric milestone passes",
            "llm_judge_calls": 0,
        },
        "workflow": {
            "reads": len(
                [s for s in steps if s["phase"] in {"context", "investigation"}]
            ),
            "writes": 2,
            "readbacks": 1,
            "answer_fields": len(answer),
        },
    }


def build_tasks() -> list[dict[str, Any]]:
    return [build_task(scenario) for scenario in scenarios()]


__all__ = [
    "BENCHMARK",
    "FAMILY_SLUG",
    "FAMILY_VERSION",
    "build_task",
    "build_tasks",
    "calendar",
    "first_window_on_or_after",
    "verify_numbers",
]
