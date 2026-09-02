"""Provider-shaped ResearchDesk tools over a deterministic SQLite world."""

from __future__ import annotations

import json
from typing import Any

from ...engine.families import ToolSpec
from ...engine.validation import integer, obj, string
from ...engine.world import World


def articles_search(world: World, args: dict[str, Any]) -> dict[str, Any]:
    query = args["q"].strip().casefold()
    rows = world.all(
        "SELECT * FROM knowledge_articles WHERE instr(lower(title), ?) > 0 OR instr(lower(slug), ?) > 0 OR instr(lower(summary), ?) > 0 ORDER BY article_id",
        (query, query, query),
    )
    if args.get("status"):
        rows = [row for row in rows if row["status"] == args["status"]]
    return {"articles": rows, "total": len(rows)}


def articles_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(
        world.one(
            "SELECT * FROM knowledge_articles WHERE article_id = ?",
            (args["article_id"],),
            missing=f"article {args['article_id']} not found",
        )
    )


def revisions_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    rows = world.all(
        "SELECT * FROM knowledge_revisions WHERE article_id = ? ORDER BY effective_from, revision_id",
        (args["article_id"],),
    )
    return {"article_id": args["article_id"], "revisions": rows}


def revisions_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(
        world.one(
            "SELECT * FROM knowledge_revisions WHERE revision_id = ?",
            (args["revision_id"],),
            missing=f"revision {args['revision_id']} not found",
        )
    )


def definitions_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    rows = world.all(
        "SELECT * FROM metric_definitions WHERE metric_key = ? ORDER BY effective_from, definition_id",
        (args["metric_key"],),
    )
    return {"metric_key": args["metric_key"], "definitions": rows}


def definitions_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(
        world.one(
            "SELECT * FROM metric_definitions WHERE definition_id = ?",
            (args["definition_id"],),
            missing=f"definition {args['definition_id']} not found",
        )
    )


def snapshots_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = ["metric_key = ?"], [args["metric_key"]]
    for key in ("period_start", "period_end", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    rows = world.all(
        f"SELECT * FROM metric_snapshots WHERE {' AND '.join(clauses)} ORDER BY period_start, snapshot_id",
        params,
    )
    return {"metric_key": args["metric_key"], "snapshots": rows}


def snapshots_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(
        world.one(
            "SELECT * FROM metric_snapshots WHERE snapshot_id = ?",
            (args["snapshot_id"],),
            missing=f"snapshot {args['snapshot_id']} not found",
        )
    )


def source_sets_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one(
        "SELECT * FROM source_sets WHERE source_set_id = ?",
        (args["source_set_id"],),
        missing=f"source set {args['source_set_id']} not found",
    )
    counts = world.one(
        "SELECT COUNT(*) AS total, SUM(CASE WHEN status = 'VERIFIED' THEN 1 ELSE 0 END) AS verified FROM source_records WHERE source_set_id = ?",
        (args["source_set_id"],),
    )
    return {
        **row,
        "record_count": counts["total"],
        "verified_count": counts["verified"] or 0,
    }


def source_records_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = ["source_set_id = ?"], [args["source_set_id"]]
    if args.get("status"):
        clauses.append("status = ?")
        params.append(args["status"])
    rows = world.all(
        f"SELECT * FROM source_records WHERE {' AND '.join(clauses)} ORDER BY source_id",
        params,
    )
    return {"source_set_id": args["source_set_id"], "records": rows}


def source_records_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(
        world.one(
            "SELECT * FROM source_records WHERE source_id = ?",
            (args["source_id"],),
            missing=f"source {args['source_id']} not found",
        )
    )


def indexes_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    rows = world.all("SELECT * FROM search_indexes ORDER BY index_id")
    if args.get("status"):
        rows = [row for row in rows if row["status"] == args["status"]]
    return {"indexes": rows}


def search_query(world: World, args: dict[str, Any]) -> dict[str, Any]:
    index = world.one(
        "SELECT * FROM search_indexes WHERE index_id = ?",
        (args["index_id"],),
        missing=f"index {args['index_id']} not found",
    )
    rows = world.all(
        "SELECT * FROM search_hits WHERE index_id = ? AND query_key = ? ORDER BY rank, hit_id",
        (args["index_id"], args["query_key"]),
    )
    return {
        "index": index,
        "query_key": args["query_key"],
        "hits": rows,
        "total": len(rows),
    }


def slots_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = (
        ["review_date >= ?", "review_date <= ?"],
        [args["start_date"], args["end_date"]],
    )
    for key in ("expertise", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    rows = world.all(
        f"SELECT * FROM review_slots WHERE {' AND '.join(clauses)} ORDER BY review_date, start_time, slot_id",
        params,
    )
    return {"slots": rows}


def approvals_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("q"):
        query = args["q"].casefold()
        rows = world.all(
            "SELECT * FROM approvals WHERE instr(lower(subject), ?) > 0 OR instr(lower(scope_json), ?) > 0 ORDER BY approval_id",
            (query, query),
        )
    else:
        rows = world.all("SELECT * FROM approvals ORDER BY approval_id")
    return {
        "approvals": [{**row, "scope": json.loads(row["scope_json"])} for row in rows]
    }


def approvals_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one(
        "SELECT * FROM approvals WHERE approval_id = ?",
        (args["approval_id"],),
        missing=f"approval {args['approval_id']} not found",
    )
    approver = world.one(
        "SELECT * FROM users WHERE user_id = ?",
        (row["approver_id"],),
        missing="approver not found",
    )
    return {**row, "scope": json.loads(row["scope_json"]), "approver": approver}


def messages_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    query = args["q"].strip().strip('"')
    rows = world.all(
        "SELECT message_id, thread_id, channel, sender, subject, sent_at, labels FROM messages WHERE instr(subject, ?) > 0 OR instr(body, ?) > 0 OR instr(labels, ?) > 0 ORDER BY sent_at, message_id",
        (query, query, query),
    )
    limit = int(args.get("max_results", 20))
    return {
        "messages": [
            {
                "id": row["message_id"],
                "thread_id": row["thread_id"],
                "channel": row["channel"],
                "from": row["sender"],
                "subject": row["subject"],
                "sent_at": row["sent_at"],
                "labels": row["labels"],
            }
            for row in rows[:limit]
        ]
    }


def messages_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one(
        "SELECT * FROM messages WHERE message_id = ?",
        (args["message_id"],),
        missing=f"message {args['message_id']} not found",
    )
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
    rows = world.all(
        "SELECT thread_id, channel, title FROM chat_threads WHERE instr(title, ?) > 0 OR instr(messages_json, ?) > 0 ORDER BY thread_id",
        (query, query),
    )
    return {"threads": rows}


def chat_threads_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one(
        "SELECT * FROM chat_threads WHERE thread_id = ?",
        (args["thread_id"],),
        missing=f"thread {args['thread_id']} not found",
    )
    return {
        "thread_id": row["thread_id"],
        "channel": row["channel"],
        "title": row["title"],
        "messages": json.loads(row["messages_json"]),
    }


def drive_files_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    query = args["q"].strip().strip('"')
    rows = world.all(
        "SELECT file_id, name, mime_type, modified_time, folder FROM drive_files WHERE instr(name, ?) > 0 OR instr(folder, ?) > 0 OR instr(content, ?) > 0 ORDER BY folder, name",
        (query, query, query),
    )
    return {
        "files": [
            {
                "id": row["file_id"],
                "name": row["name"],
                "mimeType": row["mime_type"],
                "modifiedTime": row["modified_time"],
                "folder": row["folder"],
            }
            for row in rows
        ]
    }


def drive_files_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one(
        "SELECT file_id, name, mime_type, modified_time, folder, sha256 FROM drive_files WHERE file_id = ?",
        (args["file_id"],),
        missing=f"file {args['file_id']} not found",
    )
    return {
        "id": row["file_id"],
        "name": row["name"],
        "mimeType": row["mime_type"],
        "modifiedTime": row["modified_time"],
        "folder": row["folder"],
        "sha256": row["sha256"],
    }


def drive_files_export(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one(
        "SELECT * FROM drive_files WHERE file_id = ?",
        (args["file_id"],),
        missing=f"file {args['file_id']} not found",
    )
    return {
        "file_id": row["file_id"],
        "name": row["name"],
        "mime_type": row["mime_type"],
        "content": row["content"],
    }


def _approval_scope(world: World, approval_id: str, action: str) -> dict[str, Any]:
    row = world.one(
        "SELECT * FROM approvals WHERE approval_id = ?",
        (approval_id,),
        missing=f"approval {approval_id} not found",
    )
    if row["status"] != "APPROVED":
        raise ValueError(f"approval {approval_id} is {row['status']}")
    if row["valid_until"] < world.task["as_of"]:
        raise ValueError(f"approval {approval_id} expired {row['valid_until']}")
    scope = json.loads(row["scope_json"])
    if scope.get("action") != action:
        raise ValueError(
            f"approval {approval_id} covers {scope.get('action')}, not {action}"
        )
    return scope


def _require_scope(
    scope: dict[str, Any],
    args: dict[str, Any],
    fields: tuple[str, ...],
    approval_id: str,
) -> None:
    for field in fields:
        if scope.get(field) != args.get(field):
            raise ValueError(
                f"approval {approval_id} covers {field}={scope.get(field)!r}, not {args.get(field)!r}"
            )


def _current_snapshot(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return world.one(
        "SELECT * FROM metric_snapshots WHERE metric_key = ? AND period_start = ? AND period_end = ? AND status = 'PUBLISHED' ORDER BY snapshot_id",
        (args["metric_key"], args["period_start"], args["period_end"]),
        missing=f"no published snapshot for {args['metric_key']} {args['period_start']}..{args['period_end']}",
    )


def _require_verified_source_set(
    world: World, source_set_id: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source_set = world.one(
        "SELECT * FROM source_sets WHERE source_set_id = ?",
        (source_set_id,),
        missing=f"source set {source_set_id} not found",
    )
    if source_set["status"] != "CURRENT":
        raise ValueError(f"source set {source_set_id} is {source_set['status']}")
    records = world.all(
        "SELECT * FROM source_records WHERE source_set_id = ? ORDER BY source_id",
        (source_set_id,),
    )
    verified = [row for row in records if row["status"] == "VERIFIED"]
    if len(verified) < int(source_set["required_sources"]):
        raise ValueError(
            f"source set {source_set_id} has {len(verified)} verified records; {source_set['required_sources']} required"
        )
    return source_set, records


def claims_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(
        world.one(
            "SELECT * FROM research_claims WHERE claim_id = ?",
            (args["claim_id"],),
            missing=f"claim {args['claim_id']} not found",
        )
    )


def claims_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "research.claims.create"
    scope = _approval_scope(world, args["approval_id"], "publish_claim")
    _require_scope(
        scope,
        args,
        ("article_id", "metric_key", "definition_id", "source_set_id"),
        args["approval_id"],
    )
    article = world.one(
        "SELECT * FROM knowledge_articles WHERE article_id = ?",
        (args["article_id"],),
        missing=f"article {args['article_id']} not found",
    )
    if article["status"] != "ACTIVE":
        raise ValueError(f"article {args['article_id']} is {article['status']}")
    definition = world.one(
        "SELECT * FROM metric_definitions WHERE definition_id = ?",
        (args["definition_id"],),
        missing=f"definition {args['definition_id']} not found",
    )
    if definition["status"] != "CURRENT":
        raise ValueError(
            f"definition {args['definition_id']} is {definition['status']}; stale definitions cannot be published"
        )
    snapshot = _current_snapshot(world, args)
    if (
        snapshot["definition_id"] != args["definition_id"]
        or snapshot["source_set_id"] != args["source_set_id"]
    ):
        raise ValueError(
            "claim definition and source set do not match the published snapshot"
        )
    if (
        snapshot["unit"] != args["unit"]
        or int(snapshot["supported_value"]) != args["value"]
    ):
        raise ValueError(
            f"claim must use supported {snapshot['supported_value']} {snapshot['unit']}, not {args['value']} {args['unit']}"
        )
    if args["value"] > int(scope["max_value"]):
        raise ValueError(
            f"claim value {args['value']} exceeds signed maximum {scope['max_value']}"
        )
    _require_verified_source_set(world, args["source_set_id"])
    if not args["note"].strip():
        raise ValueError("claim note is required")
    claim_id = world.next_id("research_claims", "claim_id", "CLM-")
    row = {
        "claim_id": claim_id,
        **args,
        "status": "PUBLISHED",
        "created_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO research_claims (claim_id, article_id, metric_key, period_start, period_end, value, unit, definition_id, source_set_id, approval_id, note, status, created_by, created_at, revision) "
        "VALUES (:claim_id, :article_id, :metric_key, :period_start, :period_end, :value, :unit, :definition_id, :source_set_id, :approval_id, :note, :status, :created_by, :created_at, :revision)",
        row,
    )
    world.audit(tool, "research_claims", claim_id, "insert", row)
    world.record_mutation(tool, "research_claims", claim_id, "PUBLISHED", args)
    return dict(row)


def packets_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one(
        "SELECT * FROM evidence_packets WHERE packet_id = ?",
        (args["packet_id"],),
        missing=f"packet {args['packet_id']} not found",
    )
    return {
        **row,
        "included_source_ids": json.loads(row["included_sources_json"]),
        "excluded_source_ids": json.loads(row["excluded_sources_json"]),
    }


def packets_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "research.packets.create"
    scope = _approval_scope(world, args["approval_id"], "create_packet")
    _require_scope(
        scope, args, ("article_id", "metric_key", "source_set_id"), args["approval_id"]
    )
    world.one(
        "SELECT article_id FROM knowledge_articles WHERE article_id = ? AND status = 'ACTIVE'",
        (args["article_id"],),
        missing=f"active article {args['article_id']} not found",
    )
    _, records = _require_verified_source_set(world, args["source_set_id"])
    expected_included = {
        row["source_id"] for row in records if row["status"] == "VERIFIED"
    }
    expected_excluded = {
        row["source_id"] for row in records if row["status"] != "VERIFIED"
    }
    included = list(args["included_source_ids"])
    excluded = list(args["excluded_source_ids"])
    if len(included) != len(set(included)) or set(included) != expected_included:
        raise ValueError(
            f"packet must include exactly the verified sources {sorted(expected_included)}"
        )
    if len(excluded) != len(set(excluded)) or set(excluded) != expected_excluded:
        raise ValueError(
            f"packet must exclude exactly the stale or conflicting sources {sorted(expected_excluded)}"
        )
    if (
        not args["summary"].strip()
        or world.task["reference_records"]["case_reference"] not in args["summary"]
    ):
        raise ValueError("packet summary must carry the task case reference")
    packet_id = world.next_id("evidence_packets", "packet_id", "PKT-")
    row = {
        "packet_id": packet_id,
        "article_id": args["article_id"],
        "metric_key": args["metric_key"],
        "source_set_id": args["source_set_id"],
        "included_sources_json": json.dumps(included, sort_keys=True),
        "excluded_sources_json": json.dumps(excluded, sort_keys=True),
        "approval_id": args["approval_id"],
        "summary": args["summary"],
        "status": "READY_FOR_REVIEW",
        "created_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO evidence_packets (packet_id, article_id, metric_key, source_set_id, included_sources_json, excluded_sources_json, approval_id, summary, status, created_by, created_at, revision) "
        "VALUES (:packet_id, :article_id, :metric_key, :source_set_id, :included_sources_json, :excluded_sources_json, :approval_id, :summary, :status, :created_by, :created_at, :revision)",
        row,
    )
    world.audit(tool, "evidence_packets", packet_id, "insert", row)
    world.record_mutation(tool, "evidence_packets", packet_id, "READY_FOR_REVIEW", args)
    return packets_get(world, {"packet_id": packet_id})


def reservations_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(
        world.one(
            "SELECT * FROM review_reservations WHERE reservation_id = ?",
            (args["reservation_id"],),
            missing=f"reservation {args['reservation_id']} not found",
        )
    )


def reservations_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "reviews.reservations.create"
    scope = _approval_scope(world, args["approval_id"], "reserve_review")
    _require_scope(
        scope, args, ("article_id", "metric_key", "slot_id"), args["approval_id"]
    )
    slot = world.one(
        "SELECT * FROM review_slots WHERE slot_id = ?",
        (args["slot_id"],),
        missing=f"review slot {args['slot_id']} not found",
    )
    if slot["status"] == "protected":
        raise ValueError(
            f"review slot {args['slot_id']} is protected: {slot['hold_reason'] or 'reserved control work'}"
        )
    if slot["status"] != "free":
        raise ValueError(f"review slot {args['slot_id']} is {slot['status']}")
    if args["minutes"] > int(slot["duration_minutes"]) or args["minutes"] > int(
        scope["max_minutes"]
    ):
        raise ValueError(
            f"review needs {args['minutes']} minutes but the authorized slot permits {min(int(slot['duration_minutes']), int(scope['max_minutes']))}"
        )
    if not args["purpose"].strip():
        raise ValueError("review purpose is required")
    reservation_id = world.next_id("review_reservations", "reservation_id", "RSV-")
    row = {
        "reservation_id": reservation_id,
        "article_id": args["article_id"],
        "metric_key": args["metric_key"],
        "slot_id": args["slot_id"],
        "reviewer_id": slot["reviewer_id"],
        "minutes": args["minutes"],
        "approval_id": args["approval_id"],
        "purpose": args["purpose"],
        "status": "RESERVED",
        "created_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO review_reservations (reservation_id, article_id, metric_key, slot_id, reviewer_id, minutes, approval_id, purpose, status, created_by, created_at, revision) "
        "VALUES (:reservation_id, :article_id, :metric_key, :slot_id, :reviewer_id, :minutes, :approval_id, :purpose, :status, :created_by, :created_at, :revision)",
        row,
    )
    world.connection.execute(
        "UPDATE review_slots SET status = 'reserved', reservation_id = ? WHERE slot_id = ?",
        (reservation_id, args["slot_id"]),
    )
    world.audit(tool, "review_reservations", reservation_id, "insert", row)
    world.audit(
        tool,
        "review_slots",
        args["slot_id"],
        "update",
        {"status": "reserved", "reservation_id": reservation_id},
    )
    world.record_mutation(tool, "review_reservations", reservation_id, "RESERVED", args)
    return dict(row)


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
        "related_article_id": args.get("related_article_id"),
        "related_case": args.get("related_case"),
        "created_at": world.clock(),
        "status": "DRAFT",
    }
    world.connection.execute(
        "INSERT INTO note_drafts (draft_id, recipient, subject, body, related_article_id, related_case, created_at, status) "
        "VALUES (:draft_id, :recipient, :subject, :body, :related_article_id, :related_case, :created_at, :status)",
        row,
    )
    world.audit(tool, "note_drafts", draft_id, "insert", row)
    world.record_mutation(tool, "note_drafts", draft_id, "DRAFT", args)
    return dict(row)


STRING_ARRAY = {"type": "array", "items": string()}

TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "knowledge.articles.search",
        "Search active and archived internal knowledge articles by title, slug, or summary.",
        obj({"q": string(), "status": string()}, ["q"]),
        "read",
        articles_search,
        "knowledge article search",
    ),
    ToolSpec(
        "knowledge.articles.get",
        "Read one knowledge article and its current revision pointer.",
        obj({"article_id": string()}, ["article_id"]),
        "read",
        articles_get,
        "knowledge article",
    ),
    ToolSpec(
        "knowledge.revisions.list",
        "List all current and retired revisions of one article.",
        obj({"article_id": string()}, ["article_id"]),
        "read",
        revisions_list,
        "article revision history",
    ),
    ToolSpec(
        "knowledge.revisions.get",
        "Read one immutable article revision.",
        obj({"revision_id": string()}, ["revision_id"]),
        "read",
        revisions_get,
        "article revision",
    ),
    ToolSpec(
        "metrics.definitions.list",
        "List metric definitions by metric key, including retired revisions.",
        obj({"metric_key": string()}, ["metric_key"]),
        "read",
        definitions_list,
        "metric definition registry",
    ),
    ToolSpec(
        "metrics.definitions.get",
        "Read one metric definition with numerator, denominator, exclusions, and effective status.",
        obj({"definition_id": string()}, ["definition_id"]),
        "read",
        definitions_get,
        "metric definition",
    ),
    ToolSpec(
        "metrics.snapshots.list",
        "List published metric snapshots for an exact period and status.",
        obj(
            {
                "metric_key": string(),
                "period_start": string(),
                "period_end": string(),
                "status": string(),
            },
            ["metric_key"],
        ),
        "read",
        snapshots_list,
        "metric snapshot registry",
    ),
    ToolSpec(
        "metrics.snapshots.get",
        "Read one metric snapshot with gross, excluded, and supported values.",
        obj({"snapshot_id": string()}, ["snapshot_id"]),
        "read",
        snapshots_get,
        "metric snapshot",
    ),
    ToolSpec(
        "sources.sets.get",
        "Read a source-set contract and its verified-record count.",
        obj({"source_set_id": string()}, ["source_set_id"]),
        "read",
        source_sets_get,
        "source-set contract",
    ),
    ToolSpec(
        "sources.records.list",
        "List independently identified source records, optionally filtered by verification status.",
        obj({"source_set_id": string(), "status": string()}, ["source_set_id"]),
        "read",
        source_records_list,
        "source registry",
    ),
    ToolSpec(
        "sources.records.get",
        "Read one source record with value, status, reliability, and capture time.",
        obj({"source_id": string()}, ["source_id"]),
        "read",
        source_records_get,
        "source record",
    ),
    ToolSpec(
        "search.indexes.list",
        "List knowledge-search indexes with revision and refresh state.",
        obj({"status": string()}),
        "read",
        indexes_list,
        "search index registry",
    ),
    ToolSpec(
        "search.query",
        "Query one index by stable query key; results include rank and current or stale status but do not confer authority.",
        obj({"index_id": string(), "query_key": string()}, ["index_id", "query_key"]),
        "read",
        search_query,
        "ranked knowledge search",
    ),
    ToolSpec(
        "reviews.slots.list",
        "List specialist review capacity by date, expertise, and free or protected status.",
        obj(
            {
                "start_date": string(),
                "end_date": string(),
                "expertise": string(),
                "status": string(),
            },
            ["start_date", "end_date"],
        ),
        "read",
        slots_list,
        "review capacity calendar",
    ),
    ToolSpec(
        "reviews.reservations.get",
        "Read one persisted methodology-review reservation.",
        obj({"reservation_id": string()}, ["reservation_id"]),
        "read",
        reservations_get,
        "review reservation",
    ),
    ToolSpec(
        "reviews.reservations.create",
        "Reserve an approved qualified review slot. Protected capacity cannot be displaced.",
        obj(
            {
                "article_id": string(),
                "metric_key": string(),
                "slot_id": string(),
                "approval_id": string(),
                "minutes": integer(minimum=1),
                "purpose": string(),
            },
            [
                "article_id",
                "metric_key",
                "slot_id",
                "approval_id",
                "minutes",
                "purpose",
            ],
        ),
        "write",
        reservations_create,
        "review reservation",
        idempotent=False,
    ),
    ToolSpec(
        "research.claims.get",
        "Read one persisted research claim.",
        obj({"claim_id": string()}, ["claim_id"]),
        "read",
        claims_get,
        "research claim",
    ),
    ToolSpec(
        "research.claims.create",
        "Publish a task-scoped claim only when its current definition, snapshot, source set, value, unit, and approval all agree.",
        obj(
            {
                "article_id": string(),
                "metric_key": string(),
                "period_start": string(),
                "period_end": string(),
                "value": integer(minimum=0),
                "unit": string(),
                "definition_id": string(),
                "source_set_id": string(),
                "approval_id": string(),
                "note": string(),
            },
            [
                "article_id",
                "metric_key",
                "period_start",
                "period_end",
                "value",
                "unit",
                "definition_id",
                "source_set_id",
                "approval_id",
                "note",
            ],
        ),
        "write",
        claims_create,
        "research claim",
        idempotent=False,
    ),
    ToolSpec(
        "research.packets.get",
        "Read one persisted evidence packet and its included and excluded source identifiers.",
        obj({"packet_id": string()}, ["packet_id"]),
        "read",
        packets_get,
        "evidence packet",
    ),
    ToolSpec(
        "research.packets.create",
        "Create a task-scoped packet containing exactly the verified sources and explicitly excluding every stale or conflicting source.",
        obj(
            {
                "article_id": string(),
                "metric_key": string(),
                "source_set_id": string(),
                "included_source_ids": STRING_ARRAY,
                "excluded_source_ids": STRING_ARRAY,
                "approval_id": string(),
                "summary": string(),
            },
            [
                "article_id",
                "metric_key",
                "source_set_id",
                "included_source_ids",
                "excluded_source_ids",
                "approval_id",
                "summary",
            ],
        ),
        "write",
        packets_create,
        "evidence packet",
        idempotent=False,
    ),
    ToolSpec(
        "approvals.list",
        "List approval records, optionally by subject or scope keyword.",
        obj({"q": string()}),
        "read",
        approvals_list,
        "approval workflow record",
    ),
    ToolSpec(
        "approvals.get",
        "Read one approval with exact action, identity, value, source, and capacity scope.",
        obj({"approval_id": string()}, ["approval_id"]),
        "read",
        approvals_get,
        "approval workflow record",
    ),
    ToolSpec(
        "messages.list",
        "Search research-team mailbox messages by subject, body, or labels.",
        obj({"q": string(), "max_results": integer(minimum=1)}, ["q"]),
        "read",
        messages_list,
        "mailbox search",
    ),
    ToolSpec(
        "messages.get",
        "Read one mailbox message with body and attachments.",
        obj({"message_id": string()}, ["message_id"]),
        "read",
        messages_get,
        "mailbox message",
    ),
    ToolSpec(
        "chat.threads.list",
        "Search research-team chat threads by title or message body.",
        obj({"q": string()}, ["q"]),
        "read",
        chat_threads_list,
        "team chat search",
    ),
    ToolSpec(
        "chat.threads.get",
        "Read one research-team chat thread.",
        obj({"thread_id": string()}, ["thread_id"]),
        "read",
        chat_threads_get,
        "team chat thread",
    ),
    ToolSpec(
        "drive.files.list",
        "Search the research evidence drive by name, folder, or extracted content.",
        obj({"q": string()}, ["q"]),
        "read",
        drive_files_list,
        "shared drive search",
    ),
    ToolSpec(
        "drive.files.get",
        "Read evidence-file metadata and digest.",
        obj({"file_id": string()}, ["file_id"]),
        "read",
        drive_files_get,
        "shared drive file",
    ),
    ToolSpec(
        "drive.files.export",
        "Export an evidence file as text; spreadsheets are CSV renderings and PDFs are extracted text.",
        obj({"file_id": string()}, ["file_id"]),
        "read",
        drive_files_export,
        "shared drive export",
    ),
    ToolSpec(
        "notes.drafts.create",
        "Create, but do not send, a stakeholder draft tied to an article and case.",
        obj(
            {
                "recipient": string(),
                "subject": string(),
                "body": string(),
                "related_article_id": string(),
                "related_case": string(),
            },
            ["recipient", "subject", "body"],
        ),
        "write",
        drafts_create,
        "collaboration draft",
        idempotent=False,
    ),
)

SERVERS = {
    "knowledge": "Versioned internal knowledge articles and immutable revision history.",
    "metrics": "Metric definitions and period snapshots with gross, excluded, and supported values.",
    "sources": "Independent source-set contracts and source records with verification state.",
    "search": "Ranked internal search indexes; rank is never treated as authority.",
    "reviews": "Specialist review capacity and persistent reservations with protected-slot controls.",
    "research": "Published claims and evidence packets with exact source and definition contracts.",
    "approvals": "Signed task-scoped research approvals.",
    "messages": "Research-team mailbox.",
    "chat": "Research-team collaboration threads.",
    "drive": "Evidence-room documents, workbooks, exports, and provenance.",
    "notes": "Stakeholder drafts that are never sent by the benchmark.",
}

__all__ = ["SERVERS", "TOOLS"]
