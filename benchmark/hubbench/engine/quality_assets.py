"""Shared evidence-room depth for every HubBench family.

The family builders provide the domain records.  This module adds the
cross-system evidence that makes an enterprise decision auditable: provenance,
lineage, authority revisions, provider contracts, review capacity, source
integrity, collaboration context, and a live state snapshot.  Every record is
task-scoped and deterministic; no upstream benchmark examples or answers are
copied into a HubBench release.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Callable, Iterable

from .assets import CSV, EML, JSON, MARKDOWN, PDF, XLSX, YAML, asset, eml, yaml_lines

TEXT = "text/plain"


def scoped_markdown(content: str, *, task_id: str, case_reference: str) -> str:
    """Mount a shared control into one task room without recycling its bytes."""

    return (
        content.rstrip()
        + f"\n\n---\nEvidence-room mount: {task_id} / {case_reference}.\n"
    )


def scoped_csv(content: str, *, task_id: str, case_reference: str) -> str:
    """Add explicit task-mount metadata to every row of a shared CSV export."""

    rows = [row for row in csv.reader(io.StringIO(content)) if row]
    if not rows:
        raise ValueError("CSV evidence cannot be empty")
    scoped_rows = [
        [*rows[0], "hubbench_task_scope", "hubbench_case_reference"],
        *[[*row, task_id, case_reference] for row in rows[1:]],
    ]
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows(scoped_rows)
    return buffer.getvalue()


def _anchor_payload(anchors: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    records = []
    for anchor in anchors:
        record = dict(anchor)
        record.setdefault(
            "relationship",
            "evaluation-shape inspiration only; clean-room task, state, tools, and answer",
        )
        records.append(record)
    if not records:
        raise ValueError("at least one open-source anchor is required")
    return records


def quality_support_assets(
    *,
    task_id: str,
    ordinal: int,
    case_reference: str,
    family_slug: str,
    family_name: str,
    organization_name: str,
    subject_id: str,
    as_of: str,
    current_revision: str,
    anchors: Iterable[dict[str, str]],
) -> list[dict[str, Any]]:
    """Return task-unique evidence that every released family must expose."""

    anchor_records = _anchor_payload(anchors)
    current_authority = (
        f"# Current execution authority — {case_reference}\n\n"
        f"Effective {as_of}. Applies only to {subject_id} in {family_name}. "
        f"The signed approval record and provider contract jointly bound any write. "
        "A source record, search result, or prior decision never grants authority.\n\n"
        f"Release revision: {current_revision}. Task scope: {task_id}.\n"
    )
    retired_authority = (
        f"# Retired authority — {case_reference}\n\n"
        f"Status: SUPERSEDED. This historical {family_name} delegation ended before {as_of}. "
        f"It references {subject_id} but cannot authorize a current action for {task_id}.\n"
    )
    decision = {
        "approval_record": f"DEC-{family_slug.upper()}-{ordinal:04d}",
        "case_reference": case_reference,
        "subject_id": subject_id,
        "status": "REVIEW_REQUIRED",
        "effective_revision": current_revision,
        "authority_source": "signed family approval plus provider contract",
        "prohibited_basis": ["retired authority", "search ranking", "request urgency"],
    }
    provider_contract = {
        "schema_version": "hubbench.provider-contract.v1",
        "task_id": task_id,
        "case_reference": case_reference,
        "subject_id": subject_id,
        "state_scope": "isolated SQLite episode",
        "read_semantics": "provider-shaped records backed by the seeded task world",
        "write_semantics": "task-scoped, schema-validated, transactionally persisted and audited",
        "network": "closed benchmark world",
        "verifier_visibility": "hidden from the agent",
        "unsupported_claims": [
            "byte parity with upstream providers",
            "conversion of upstream benchmark tasks",
            "upstream score comparability",
        ],
    }
    snapshot = {
        "schema_version": "hubbench.live-snapshot.v1",
        "captured_as_of": as_of,
        "organization": organization_name,
        "family": family_slug,
        "task_id": task_id,
        "case_reference": case_reference,
        "subject_id": subject_id,
        "state": "PRE_ACTION",
        "expected_mutation_count": 2,
        "note": "Live provider state remains authoritative; this export is a correlation aid, not a write instruction.",
    }
    status = {
        "task_id": task_id,
        "case_reference": case_reference,
        "as_of": as_of,
        "checks": [
            {"name": "identity_linked", "status": "PASS", "record": subject_id},
            {"name": "revision_current", "status": "PASS", "record": current_revision},
            {
                "name": "authority_requires_live_read",
                "status": "OPEN",
                "record": f"DEC-{family_slug.upper()}-{ordinal:04d}",
            },
            {"name": "outcome_precomputed", "status": "NO", "record": task_id},
        ],
    }
    audit_log = (
        f"{as_of}T08:55:00Z INFO scope_created task={task_id} case={case_reference}\n"
        f"{as_of}T08:56:00Z INFO subject_linked family={family_slug} subject={subject_id}\n"
        f"{as_of}T08:57:00Z WARN retired_authority_present case={case_reference} action=ignore_until_current_scope_verified\n"
        f"{as_of}T08:58:00Z INFO provider_state_ready task={task_id} expected_mutations=2\n"
    )
    thread = {
        "thread_id": f"OPS-{family_slug.upper()}-{ordinal:04d}",
        "case_reference": case_reference,
        "messages": [
            {
                "author": "operations",
                "sent_at": f"{as_of}T08:35:00",
                "text": f"Use immutable subject {subject_id}; the similarly named archived record is not in scope.",
            },
            {
                "author": "governance",
                "sent_at": f"{as_of}T08:41:00",
                "text": f"Current revision is {current_revision}. Confirm the signed approval before any state change.",
            },
            {
                "author": "requester",
                "sent_at": f"{as_of}T08:47:00",
                "text": "Please leave the stakeholder communication as a draft for human review.",
            },
        ],
    }
    source_request = eml(
        from_addr=f"records@{family_slug}.example",
        to_addr="benchmark-operator@blobfish.example",
        subject=f"Source integrity request for {case_reference}",
        date=f"{as_of}T08:30:00",
        message_id=f"source-{task_id}@{family_slug}.example",
        body=(
            f"Confirm the live provider record for {subject_id}, the current {current_revision} authority, "
            f"and the task-scoped case {case_reference}. Do not rely on the retired authority or infer the final outcome from this request."
        ),
    )
    return [
        asset(
            "provenance/harbor-open-source-anchors.json",
            kind="open_source_provenance",
            title=f"Open-source benchmark provenance — {family_name}",
            source="release_metadata",
            media_type=JSON,
            content=json.dumps(
                {
                    "schema_version": "hubbench.provenance.v1",
                    "task_id": task_id,
                    "family": family_slug,
                    "clean_room": True,
                    "upstream_tasks_copied": False,
                    "upstream_scores_claimed": False,
                    "anchors": anchor_records,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            preview="Exact Harbor datasets and upstream libraries that anchor the clean-room family design.",
        ),
        asset(
            "lineage/record-lineage.csv",
            kind="record_lineage",
            title=f"Cross-system record lineage — {case_reference}",
            source="lineage_export",
            media_type=CSV,
            content=(
                "task_id,case_reference,subject_id,source_system,record_role,effective_revision\n"
                f"{task_id},{case_reference},{subject_id},domain,authoritative_subject,{current_revision}\n"
                f"{task_id},{case_reference},{subject_id},approvals,execution_authority,{current_revision}\n"
                f"{task_id},{case_reference},{subject_id},drive,supporting_evidence,{current_revision}\n"
            ),
            preview="Immutable identifiers joining the case, subject, authority, and supporting evidence.",
        ),
        asset(
            "controls/current-authority.md",
            kind="authority_current",
            title=f"Current authority — {case_reference}",
            source="governance",
            media_type=MARKDOWN,
            content=current_authority,
            preview="Current task-scoped authority and its limits.",
        ),
        asset(
            "controls/retired-authority.md",
            kind="authority_superseded",
            title=f"Retired authority — {case_reference}",
            source="governance_archive",
            media_type=MARKDOWN,
            content=retired_authority,
            preview="A deliberately stale authority record that must not drive execution.",
        ),
        asset(
            "approvals/decision-record.json",
            kind="approval_decision",
            title=f"Decision control record — {case_reference}",
            source="approvals_export",
            media_type=JSON,
            content=json.dumps(decision, indent=2, sort_keys=True) + "\n",
            preview="Decision status and the records that can establish authority.",
        ),
        asset(
            "workbooks/review-capacity.xlsx",
            kind="review_capacity_workbook",
            title=f"Review capacity — {case_reference}",
            source="operations_workbook",
            media_type=XLSX,
            rows=[
                [
                    "task_id",
                    "case_reference",
                    "review_lane",
                    "available_units",
                    "protected_units",
                    "effective_date",
                ],
                [task_id, case_reference, "standard", 8 + ordinal, 2, as_of],
                [task_id, case_reference, "expedited", 4 + ordinal, 1, as_of],
            ],
            preview="Task-specific review capacity with protected load separated from availability.",
        ),
        asset(
            "controls/source-integrity.pdf",
            kind="source_integrity_control",
            title=f"Source integrity control — {case_reference}",
            source="governance",
            media_type=PDF,
            content=(
                f"Source integrity control\nTask: {task_id}\nCase: {case_reference}\nSubject: {subject_id}\n"
                f"Effective revision: {current_revision}\n"
                "Rule: current provider state plus the signed approval govern. Search rank, filenames, request urgency, and archived authority do not.\n"
            ),
            preview="Signed source-selection rule for current versus stale evidence.",
        ),
        asset(
            "audit/evidence-status.yaml",
            kind="evidence_status",
            title=f"Evidence readiness — {case_reference}",
            source="audit_export",
            media_type=YAML,
            content=yaml_lines(status) + "\n",
            preview="Readiness state without a precomputed benchmark outcome.",
        ),
        asset(
            "audit/system-audit.log",
            kind="system_audit",
            title=f"System audit log — {case_reference}",
            source="audit_export",
            media_type=TEXT,
            content=audit_log,
            preview="Task-scoped state and authority correlation events.",
        ),
        asset(
            "communications/source-request.eml",
            kind="source_request",
            title=f"Source integrity request — {case_reference}",
            source="messages",
            media_type=EML,
            content=source_request,
            preview="A request for evidence correlation, not an answer or execution instruction.",
        ),
        asset(
            "collaboration/operations-thread.json",
            kind="operations_thread",
            title=f"Operations thread — {case_reference}",
            source="chat",
            media_type=JSON,
            content=json.dumps(thread, indent=2, sort_keys=True) + "\n",
            preview="Identity, revision, and draft-only communication constraints.",
        ),
        asset(
            "contracts/provider-contracts.json",
            kind="provider_contract",
            title=f"Provider contract — {case_reference}",
            source="release_metadata",
            media_type=JSON,
            content=json.dumps(provider_contract, indent=2, sort_keys=True) + "\n",
            preview="What the mock provider world guarantees and explicitly does not claim.",
        ),
        asset(
            "exports/live-snapshot.json",
            kind="live_snapshot",
            title=f"Live pre-action snapshot — {case_reference}",
            source="provider_export",
            media_type=JSON,
            content=json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
            preview="Pre-action state marker tied to the live task world.",
        ),
    ]


def quality_support_investigations(
    *,
    start_number: int,
    file_ids: dict[str, str],
    make_investigation: Callable[
        [int, str, str, str, dict[str, Any], dict[str, Any]], dict[str, Any]
    ],
    case_reference: str,
    subject_id: str,
) -> list[dict[str, Any]]:
    """Eight causal reads shared by every family before its first mutation."""

    records = (
        (
            "investigation.scope",
            "contracts/provider-contracts.json",
            f"Read the task-scoped provider contract for {case_reference} and confirmed that {subject_id} is backed by an isolated persistent world; did not infer upstream-provider parity.",
        ),
        (
            "investigation.scope",
            "lineage/record-lineage.csv",
            f"Read the cross-system lineage for {case_reference} and joined {subject_id} to the current authority and evidence records by immutable identity.",
        ),
        (
            "investigation.requirements",
            "controls/current-authority.md",
            f"Read the current authority control for {case_reference}; distinguished task-scoped execution authority from the retired delegation in the same room.",
        ),
        (
            "investigation.constraints",
            "controls/source-integrity.pdf",
            f"Read the signed source-integrity rule for {case_reference} and applied its current-provider-state requirement before accepting any headline, filename, or search rank.",
        ),
        (
            "investigation.constraints",
            "exports/live-snapshot.json",
            f"Read the live pre-action snapshot for {subject_id} and confirmed its PRE_ACTION state and expected mutation boundary before changing the provider world.",
        ),
        (
            "investigation.authority",
            "approvals/decision-record.json",
            f"Read the decision control record for {case_reference} and confirmed that review remains required until the signed family approval and provider contract agree.",
        ),
        (
            "investigation.constraints",
            "workbooks/review-capacity.xlsx",
            f"Read task-specific review capacity for {case_reference}, separating protected units from available units rather than treating gross capacity as usable.",
        ),
        (
            "investigation.erp_correlation",
            "audit/evidence-status.yaml",
            f"Correlated the evidence-readiness record for {case_reference}: identity and revision are linked, authority still requires a live read, and no outcome is precomputed.",
        ),
    )
    investigations = []
    for offset, (milestone, path, description) in enumerate(records):
        file_id = file_ids[path]
        investigations.append(
            make_investigation(
                start_number + offset,
                milestone,
                description,
                "drive.files.export",
                {"file_id": file_id},
                {"file_id": file_id},
            )
        )
    return investigations


__all__ = [
    "TEXT",
    "quality_support_assets",
    "quality_support_investigations",
    "scoped_csv",
    "scoped_markdown",
]
