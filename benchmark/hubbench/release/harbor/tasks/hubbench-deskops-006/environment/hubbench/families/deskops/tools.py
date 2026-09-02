"""DeskOps provider-shaped tools over the family's SQLite world.

The office applications a GUI benchmark would drive through pixels are exposed
here as stateful APIs: a mailbox, a calendar (events, attendees, free/busy,
rooms), a people directory, a documents service with revisions, a spreadsheet
service with versions, a shared drive, a venue portal (availability, quotes,
holds), a corporate travel desk (policies, bookings, group-ticketing
confirmations, booking changes), and a budget system (lines, adjustments).
Read tools return provider-shaped records; write tools persist to the domain
tables, refresh the affected records, and record the exact payload for the
sealed contract.  There is no LLM anywhere here, and this module imports only
the engine and the standard library so the Harbor runtime can ship it alone.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from ...engine.families import ToolSpec
from ...engine.validation import integer, obj, string
from ...engine.world import World

HARD_KINDS = frozenset({"board_meeting", "customer_commitment", "leave", "conference"})
SOFT_KINDS = frozenset({"focus_time", "tentative", "recurring", "travel"})
WEEK_DAYS = 7


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _iso(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO date (YYYY-MM-DD)") from exc


def _monday(value: str, label: str) -> date:
    day = _iso(value, label)
    if day.weekday() != 0:
        raise ValueError(f"{label} must be a Monday (venue weeks run Monday to Sunday)")
    return day


def add_business_days(start: str, count: int) -> str:
    day = date.fromisoformat(start)
    remaining = count
    while remaining > 0:
        day += timedelta(days=1)
        if day.weekday() < 5:
            remaining -= 1
    return day.isoformat()


def _overlaps(start_a: str, end_a: str, start_b: str, end_b: str) -> bool:
    return start_a <= end_b and start_b <= end_a


def _bool(value: Any) -> bool:
    return bool(int(value)) if value is not None else False


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #


def _person(row: dict[str, Any], office: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "person_id": row["person_id"],
        "name": row["name"],
        "email": row["email"],
        "title": row["title"],
        "team": row["team"],
        "office_id": row["office_id"],
        "timezone": office["timezone"] if office else None,
        "employment": row["employment"],
    }


def _event(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["event_id"],
        "title": row["title"],
        "organizer": f"Person/{row['organizer_id']}",
        "start": row["start_date"],
        "end": row["end_date"],
        "session_days": row["session_days"],
        "venue": row.get("venue_id"),
        "location": row.get("location"),
        "status": row["status"],
        "agenda_doc": row.get("agenda_doc_id"),
        "budget_line": row.get("budget_line_id"),
        "cost_center": row.get("cost_center"),
        "description": row.get("description") or "",
        "meta": {"versionId": str(row["revision"]), "lastUpdated": row["last_updated"]},
    }


def _attendee(row: dict[str, Any], person: dict[str, Any], office: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "attendee_id": row["attendee_id"],
        "person_id": row["person_id"],
        "name": person["name"],
        "email": person["email"],
        "title": person["title"],
        "team": person["team"],
        "office_id": person["office_id"],
        "timezone": office["timezone"] if office else None,
        "required": _bool(row["required"]),
        "response": row["response"],
        "note": row.get("note") or "",
    }


def _block(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "block_id": row["block_id"],
        "person": f"Person/{row['person_id']}",
        "start": row["start_date"],
        "end": row["end_date"],
        "kind": row["kind"],
        "title": row["title"],
        "transparency": row["transparency"],
        "hard": row["kind"] in HARD_KINDS,
    }


def _venue(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "venue_id": row["venue_id"],
        "name": row["name"],
        "city": row["city"],
        "country": row["country"],
        "local_office_id": row.get("local_office_id"),
        "capacity": row["capacity"],
        "hold_business_days": row["hold_business_days"],
        "deposit_pct": row["deposit_pct"],
        "events_director": row["events_director"],
        "note": row.get("note") or "",
    }


def _week(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["week_id"],
        "venue": row["venue_id"],
        "week_start": row["week_start"],
        "status": row["status"],
        "note": row.get("note") or "",
        "hold": row.get("hold_id"),
    }


def _quote(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "quote_id": row["quote_id"],
        "venue": row["venue_id"],
        "event": row.get("event_id"),
        "reference": row["reference"],
        "week_start": row["week_start"],
        "days": row["days"],
        "total_usd": row["total_usd"],
        "deposit_usd": row["deposit_usd"],
        "issued_on": row["issued_on"],
        "valid_until": row["valid_until"],
        "status": row["status"],
        "note": row.get("note") or "",
    }


def _hold(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["hold_id"],
        "venue": row["venue_id"],
        "event": row["event_id"],
        "quote": row.get("quote_id"),
        "week_start": row["week_start"],
        "deposit_usd": row["deposit_usd"],
        "expires_on": row["expires_on"],
        "status": row["status"],
        "requested_by": row["requested_by"],
        "meta": {"versionId": str(row["revision"]), "created": row["created_at"]},
    }


def _booking(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "booking_id": row["booking_id"],
        "person": f"Person/{row['person_id']}",
        "event": row["event_id"],
        "kind": row["kind"],
        "tmc": row["tmc_id"],
        "record_locator": row["record_locator"],
        "origin_office": row["origin_office_id"],
        "destination_city": row["destination_city"],
        "travel_date": row["travel_date"],
        "return_date": row["return_date"],
        "fare_class": row["fare_class"],
        "fare_usd": row["fare_usd"],
        "changeable": _bool(row["changeable"]),
        "change_fee_usd": row["change_fee_usd"],
        "refundable": _bool(row["refundable"]),
        "status": row["status"],
        "note": row.get("note") or "",
    }


def _confirmation(row: dict[str, Any], tmc: dict[str, Any] | None = None) -> dict[str, Any]:
    record = {
        "confirmation_id": row["confirmation_id"],
        "tmc_id": row["tmc_id"],
        "event": row["event_id"],
        "reference": row["reference"],
        "seats_available": row["seats_available"],
        "group_fare_usd": row["group_fare_usd"],
        "standard_ticketing_date": row["standard_ticketing_date"],
        "rush_ticketing_date": row["rush_ticketing_date"],
        "rush_fee_usd": row["rush_fee_usd"],
        "valid_until": row["valid_until"],
        "status": row["status"],
        "note": row.get("note") or "",
    }
    if tmc:
        record["tmc_name"] = tmc["name"]
    return record


def _change(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "change_id": row["change_id"],
        "confirmation": row["confirmation_id"],
        "event": row["event_id"],
        "booking_ids": json.loads(row["booking_ids_json"]),
        "booking_count": row["booking_count"],
        "new_travel_date": row["new_travel_date"],
        "ticketing_option": row["ticketing_option"],
        "change_fees_usd": row["change_fees_usd"],
        "rush_fee_usd": row["rush_fee_usd"],
        "expected_ticketing_date": row["expected_ticketing_date"],
        "status": row["status"],
        "requested_by": row["requested_by"],
        "meta": {"versionId": str(row["revision"]), "created": row["created_at"]},
    }


def _line(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "line_id": row["line_id"],
        "cost_center": row["cost_center"],
        "name": row["name"],
        "fiscal_period": row["fiscal_period"],
        "owner": f"User/{row['owner_id']}",
        "approved_usd": row["approved_usd"],
        "committed_usd": row["committed_usd"],
        "reserved_usd": row["reserved_usd"],
        "remaining_usd": row["approved_usd"] - row["committed_usd"],
        "adjustment_ceiling_usd": row["adjustment_ceiling_usd"],
        "status": row["status"],
        "note": row.get("note") or "",
        "meta": {"versionId": str(row["revision"]), "lastUpdated": row["last_updated"]},
    }


def _adjustment(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "adjustment_id": row["adjustment_id"],
        "line": row["line_id"],
        "amount_usd": row["amount_usd"],
        "reason": row["reason"],
        "related_event": row.get("related_event_id"),
        "status": row["status"],
        "requested_by": row["requested_by"],
        "meta": {"versionId": str(row["revision"]), "created": row["created_at"]},
    }


# --------------------------------------------------------------------------- #
# Mail
# --------------------------------------------------------------------------- #


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


def threads_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    rows = world.all("SELECT * FROM messages WHERE thread_id = ? ORDER BY sent_at, message_id", (args["thread_id"],))
    if not rows:
        raise ValueError(f"thread {args['thread_id']} not found")
    return {"thread_id": args["thread_id"], "messages": [{"id": row["message_id"], "from": row["sender"], "to": row["recipients"], "subject": row["subject"], "sent_at": row["sent_at"], "body": row["body"]} for row in rows]}


# --------------------------------------------------------------------------- #
# Calendar and directory
# --------------------------------------------------------------------------- #


def _offices(world: World) -> dict[str, dict[str, Any]]:
    return {row["office_id"]: row for row in world.all("SELECT * FROM offices")}


def events_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    if args.get("q"):
        query = args["q"].strip().strip('"')
        clauses.append("(instr(title, ?) > 0 OR instr(COALESCE(description, ''), ?) > 0 OR event_id = ?)")
        params.extend([query, query, query])
    if args.get("organizer_id"):
        clauses.append("organizer_id = ?")
        params.append(args["organizer_id"])
    if args.get("start_date"):
        clauses.append("end_date >= ?")
        params.append(args["start_date"])
    if args.get("end_date"):
        clauses.append("start_date <= ?")
        params.append(args["end_date"])
    if not clauses:
        raise ValueError("at least one of q, organizer_id, start_date, end_date is required")
    rows = world.all(f"SELECT * FROM events WHERE {' AND '.join(clauses)} ORDER BY start_date, event_id", params)
    return {"total": len(rows), "events": [_event(row) for row in rows]}


def events_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _event(world.one("SELECT * FROM events WHERE event_id = ?", (args["event_id"],), missing=f"Event/{args['event_id']} not found"))


def attendees_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT event_id FROM events WHERE event_id = ?", (args["event_id"],), missing=f"Event/{args['event_id']} not found")
    clauses, params = ["a.event_id = ?"], [args["event_id"]]
    if "required" in args:
        clauses.append("a.required = ?")
        params.append(int(bool(args["required"])))
    rows = world.all(
        f"SELECT a.*, p.name, p.email, p.title, p.team, p.office_id, p.employment FROM event_attendees a JOIN people p ON p.person_id = a.person_id WHERE {' AND '.join(clauses)} ORDER BY a.required DESC, a.attendee_id",
        params,
    )
    offices = _offices(world)
    return {"event": args["event_id"], "total": len(rows), "attendees": [_attendee(row, row, offices.get(row["office_id"])) for row in rows]}


def freebusy_query(world: World, args: dict[str, Any]) -> dict[str, Any]:
    start = _iso(args["start_date"], "start_date").isoformat()
    end = _iso(args["end_date"], "end_date").isoformat()
    if start > end:
        raise ValueError("start_date must not be after end_date")
    if args.get("event_id"):
        world.one("SELECT event_id FROM events WHERE event_id = ?", (args["event_id"],), missing=f"Event/{args['event_id']} not found")
        people = world.all(
            "SELECT p.*, a.required FROM event_attendees a JOIN people p ON p.person_id = a.person_id WHERE a.event_id = ? ORDER BY a.required DESC, a.attendee_id",
            (args["event_id"],),
        )
    elif args.get("person_ids"):
        people = []
        for person_id in args["person_ids"]:
            row = world.one("SELECT * FROM people WHERE person_id = ?", (person_id,), missing=f"Person/{person_id} not found")
            people.append({**row, "required": None})
    else:
        raise ValueError("event_id or person_ids is required")
    offices = _offices(world)
    calendars = []
    for person in people:
        blocks = world.all(
            "SELECT * FROM busy_blocks WHERE person_id = ? AND start_date <= ? AND end_date >= ? ORDER BY start_date, block_id",
            (person["person_id"], end, start),
        )
        office = offices.get(person["office_id"])
        calendars.append(
            {
                "person_id": person["person_id"],
                "name": person["name"],
                "office_id": person["office_id"],
                "timezone": office["timezone"] if office else None,
                "required": _bool(person["required"]) if person.get("required") is not None else None,
                "busy": [_block(block) for block in blocks],
            }
        )
    return {"event": args.get("event_id"), "range": {"start": start, "end": end}, "hard_kinds": sorted(HARD_KINDS), "calendars": calendars}


def rooms_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("office_id"):
        rows = world.all("SELECT * FROM rooms WHERE office_id = ? ORDER BY room_id", (args["office_id"],))
    else:
        rows = world.all("SELECT * FROM rooms ORDER BY room_id")
    return {"rooms": rows}


def _hard_conflicts(world: World, event_id: str, start: str, end: str) -> list[dict[str, Any]]:
    required = world.all(
        "SELECT p.person_id, p.name FROM event_attendees a JOIN people p ON p.person_id = a.person_id WHERE a.event_id = ? AND a.required = 1 ORDER BY a.attendee_id",
        (event_id,),
    )
    conflicts = []
    for person in required:
        blocks = world.all(
            "SELECT * FROM busy_blocks WHERE person_id = ? AND start_date <= ? AND end_date >= ? ORDER BY start_date, block_id",
            (person["person_id"], end, start),
        )
        for block in blocks:
            if block["kind"] in HARD_KINDS:
                conflicts.append({"person_id": person["person_id"], "name": person["name"], **_block(block)})
    return conflicts


def events_update(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "calendar.events.update"
    current = world.one("SELECT * FROM events WHERE event_id = ?", (args["event_id"],), missing=f"Event/{args['event_id']} not found")
    if current["status"] not in {"confirmed", "tentative"}:
        raise ValueError(f"Event/{args['event_id']} is {current['status']} and cannot be changed")
    changes = {key: args[key] for key in ("start_date", "end_date", "venue_id", "location", "description") if key in args}
    if not changes:
        raise ValueError("no change requested")
    updated = {**current, **changes}
    start = _iso(updated["start_date"], "start_date")
    end = _iso(updated["end_date"], "end_date")
    if start > end:
        raise ValueError("start_date must not be after end_date")
    if updated.get("venue_id"):
        world.one("SELECT venue_id FROM venues WHERE venue_id = ?", (updated["venue_id"],), missing=f"venue {updated['venue_id']} not found")
    conflicts = _hard_conflicts(world, current["event_id"], start.isoformat(), end.isoformat())
    if conflicts:
        first = conflicts[0]
        raise ValueError(
            f"required attendee {first['name']} ({first['person_id']}) has a protected {first['kind']} '{first['title']}' {first['start']} to {first['end']}; "
            "the required-attendee conflict guard blocks the move (chief of staff override only)"
        )
    updated["revision"] = int(current["revision"]) + 1
    updated["last_updated"] = world.clock()
    world.connection.execute(
        "UPDATE events SET start_date = :start_date, end_date = :end_date, venue_id = :venue_id, location = :location, description = :description, revision = :revision, last_updated = :last_updated WHERE event_id = :event_id",
        updated,
    )
    world.audit(tool, "events", current["event_id"], "update", changes)
    world.record_mutation(tool, "events", current["event_id"], updated["status"], args, revision=updated["revision"])
    return _event(updated)


def people_search(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    if args.get("q"):
        query = args["q"].strip().strip('"')
        clauses.append("(instr(lower(name), lower(?)) > 0 OR instr(lower(email), lower(?)) > 0 OR instr(lower(team), lower(?)) > 0 OR instr(lower(title), lower(?)) > 0)")
        params.extend([query, query, query, query])
    if args.get("team"):
        clauses.append("team = ?")
        params.append(args["team"])
    if args.get("office_id"):
        clauses.append("office_id = ?")
        params.append(args["office_id"])
    if not clauses:
        raise ValueError("at least one of q, team, office_id is required")
    rows = world.all(f"SELECT * FROM people WHERE {' AND '.join(clauses)} ORDER BY person_id", params)
    offices = _offices(world)
    return {"total": len(rows), "people": [_person(row, offices.get(row["office_id"])) for row in rows]}


def people_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM people WHERE person_id = ?", (args["person_id"],), missing=f"Person/{args['person_id']} not found")
    return _person(row, _offices(world).get(row["office_id"]))


def offices_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return {"offices": world.all("SELECT * FROM offices ORDER BY office_id")}


# --------------------------------------------------------------------------- #
# Docs, sheets, drive
# --------------------------------------------------------------------------- #


def documents_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    query = args["q"].strip().strip('"')
    rows = world.all("SELECT * FROM documents WHERE instr(title, ?) > 0 OR instr(folder, ?) > 0 OR doc_id = ? ORDER BY doc_id", (query, query, query))
    return {"documents": rows}


def documents_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM documents WHERE doc_id = ?", (args["doc_id"],), missing=f"document {args['doc_id']} not found"))


def revisions_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT doc_id FROM documents WHERE doc_id = ?", (args["doc_id"],), missing=f"document {args['doc_id']} not found")
    rows = world.all("SELECT revision_id, doc_id, revision, status, modified_time, modified_by FROM document_revisions WHERE doc_id = ? ORDER BY revision DESC, revision_id", (args["doc_id"],))
    return {"doc_id": args["doc_id"], "revisions": rows}


def revisions_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM document_revisions WHERE revision_id = ?", (args["revision_id"],), missing=f"revision {args['revision_id']} not found")
    return {**{key: value for key, value in row.items() if key != "metadata_json"}, "metadata": json.loads(row["metadata_json"])}


def spreadsheets_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    query = args["q"].strip().strip('"')
    rows = world.all("SELECT * FROM spreadsheets WHERE instr(title, ?) > 0 OR instr(folder, ?) > 0 OR spreadsheet_id = ? ORDER BY spreadsheet_id", (query, query, query))
    return {"spreadsheets": rows}


def spreadsheets_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM spreadsheets WHERE spreadsheet_id = ?", (args["spreadsheet_id"],), missing=f"spreadsheet {args['spreadsheet_id']} not found")
    versions = world.all("SELECT version_id, version, status, modified_time, modified_by FROM spreadsheet_versions WHERE spreadsheet_id = ? ORDER BY version DESC", (args["spreadsheet_id"],))
    return {**row, "versions": versions}


def values_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    sheet = world.one("SELECT * FROM spreadsheets WHERE spreadsheet_id = ?", (args["spreadsheet_id"],), missing=f"spreadsheet {args['spreadsheet_id']} not found")
    version = int(args.get("version") or sheet["current_version"])
    row = world.one(
        "SELECT * FROM spreadsheet_versions WHERE spreadsheet_id = ? AND version = ?",
        (args["spreadsheet_id"], version),
        missing=f"spreadsheet {args['spreadsheet_id']} has no version {version}",
    )
    return {"spreadsheet_id": args["spreadsheet_id"], "version": row["version"], "status": row["status"], "modified_time": row["modified_time"], "rows": json.loads(row["rows_json"])}


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


# --------------------------------------------------------------------------- #
# Venue portal
# --------------------------------------------------------------------------- #


def venues_search(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    if args.get("q"):
        query = args["q"].strip().strip('"')
        clauses.append("(instr(lower(name), lower(?)) > 0 OR venue_id = ?)")
        params.extend([query, args["q"]])
    if args.get("city"):
        clauses.append("lower(city) = lower(?)")
        params.append(args["city"])
    if not clauses:
        raise ValueError("q or city is required")
    rows = world.all(f"SELECT * FROM venues WHERE {' AND '.join(clauses)} ORDER BY venue_id", params)
    return {"total": len(rows), "venues": [_venue(row) for row in rows]}


def venues_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _venue(world.one("SELECT * FROM venues WHERE venue_id = ?", (args["venue_id"],), missing=f"venue {args['venue_id']} not found"))


def availability_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT venue_id FROM venues WHERE venue_id = ?", (args["venue_id"],), missing=f"venue {args['venue_id']} not found")
    start = _monday(args["start_week"], "start_week").isoformat()
    end = _monday(args["end_week"], "end_week").isoformat()
    clauses, params = ["venue_id = ?", "week_start >= ?", "week_start <= ?"], [args["venue_id"], start, end]
    if args.get("status"):
        clauses.append("status = ?")
        params.append(args["status"])
    rows = world.all(f"SELECT * FROM venue_weeks WHERE {' AND '.join(clauses)} ORDER BY week_start", params)
    return {"venue": args["venue_id"], "weeks": [_week(row) for row in rows]}


def quotes_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("venue_id", "event_id", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"quotes": [_quote(row) for row in world.all(f"SELECT * FROM venue_quotes {where} ORDER BY issued_on, quote_id", params)]}


def quotes_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM venue_quotes WHERE quote_id = ?", (args["quote_id"],), missing=f"quote {args['quote_id']} not found")
    venue = world.one("SELECT * FROM venues WHERE venue_id = ?", (row["venue_id"],))
    return {**_quote(row), "venue_name": venue["name"], "hold_business_days": venue["hold_business_days"]}


def holds_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("event_id", "venue_id", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = world.all(f"SELECT * FROM venue_holds {where} ORDER BY hold_id", params)
    return {"total": len(rows), "holds": [_hold(row) for row in rows]}


def holds_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _hold(world.one("SELECT * FROM venue_holds WHERE hold_id = ?", (args["hold_id"],), missing=f"hold {args['hold_id']} not found"))


def holds_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "venues.holds.create"
    venue = world.one("SELECT * FROM venues WHERE venue_id = ?", (args["venue_id"],), missing=f"venue {args['venue_id']} not found")
    event = world.one("SELECT * FROM events WHERE event_id = ?", (args["event_id"],), missing=f"Event/{args['event_id']} not found")
    week_start = _monday(args["week_start"], "week_start").isoformat()
    week = world.one(
        "SELECT * FROM venue_weeks WHERE venue_id = ? AND week_start = ?",
        (args["venue_id"], week_start),
        missing=f"{venue['name']} publishes no week starting {week_start}",
    )
    if week["status"] != "open":
        raise ValueError(f"{venue['name']} week of {week_start} is {week['status']} ({week.get('note') or 'not available'}); held, booked, and blackout weeks cannot be displaced")
    quote = world.one("SELECT * FROM venue_quotes WHERE quote_id = ?", (args["quote_id"],), missing=f"quote {args['quote_id']} not found")
    if quote["venue_id"] != args["venue_id"] or quote["week_start"] != week_start:
        raise ValueError(f"quote {args['quote_id']} covers {quote['venue_id']} week of {quote['week_start']}, not {args['venue_id']} week of {week_start}")
    if quote["status"] != "current":
        raise ValueError(f"quote {args['quote_id']} is {quote['status']}; only a current quote can back a hold")
    if quote["valid_until"] < world.as_of.isoformat():
        raise ValueError(f"quote {args['quote_id']} expired on {quote['valid_until']}")
    headcount = world.one("SELECT COUNT(*) AS n FROM event_attendees WHERE event_id = ?", (args["event_id"],))["n"]
    if headcount > int(venue["capacity"]):
        raise ValueError(f"{venue['name']} capacity {venue['capacity']} is below the {headcount} attendees on Event/{args['event_id']}")
    hold_id = world.next_id("venue_holds", "hold_id", "HOLD-")
    row = {
        "hold_id": hold_id,
        "venue_id": args["venue_id"],
        "event_id": event["event_id"],
        "quote_id": quote["quote_id"],
        "week_start": week_start,
        "deposit_usd": quote["deposit_usd"],
        "expires_on": add_business_days(world.as_of.isoformat(), int(venue["hold_business_days"])),
        "status": "HELD",
        "requested_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO venue_holds (hold_id, venue_id, event_id, quote_id, week_start, deposit_usd, expires_on, status, requested_by, created_at, revision) "
        "VALUES (:hold_id, :venue_id, :event_id, :quote_id, :week_start, :deposit_usd, :expires_on, :status, :requested_by, :created_at, :revision)",
        row,
    )
    world.audit(tool, "venue_holds", hold_id, "insert", row)
    world.connection.execute("UPDATE venue_weeks SET status = 'held', hold_id = ?, note = ? WHERE week_id = ?", (hold_id, f"held for {event['event_id']}", week["week_id"]))
    world.audit(tool, "venue_weeks", week["week_id"], "update", {"status": "held", "hold_id": hold_id})
    world.record_mutation(tool, "venue_holds", hold_id, "HELD", args)
    return _hold(row)


# --------------------------------------------------------------------------- #
# Travel desk
# --------------------------------------------------------------------------- #


def policies_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    rows = world.all("SELECT policy_id, code, version, status, effective_from, title FROM travel_policies ORDER BY effective_from DESC, policy_id")
    return {"policies": rows}


def policies_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM travel_policies WHERE policy_id = ?", (args["policy_id"],), missing=f"policy {args['policy_id']} not found")
    return {**{key: value for key, value in row.items() if key != "parameters_json"}, "parameters": json.loads(row["parameters_json"])}


def bookings_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT event_id FROM events WHERE event_id = ?", (args["event_id"],), missing=f"Event/{args['event_id']} not found")
    clauses, params = ["event_id = ?"], [args["event_id"]]
    for key in ("person_id", "status", "kind"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    rows = world.all(f"SELECT * FROM bookings WHERE {' AND '.join(clauses)} ORDER BY booking_id", params)
    return {"event": args["event_id"], "total": len(rows), "bookings": [_booking(row) for row in rows]}


def bookings_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _booking(world.one("SELECT * FROM bookings WHERE booking_id = ?", (args["booking_id"],), missing=f"booking {args['booking_id']} not found"))


def confirmations_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("event_id", "tmc_id", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"confirmations": [_confirmation(row) for row in world.all(f"SELECT * FROM ticketing_confirmations {where} ORDER BY confirmation_id", params)]}


def confirmations_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM ticketing_confirmations WHERE confirmation_id = ?", (args["confirmation_id"],), missing=f"confirmation {args['confirmation_id']} not found")
    tmc = world.one("SELECT * FROM tmcs WHERE tmc_id = ?", (row["tmc_id"],))
    return _confirmation(row, tmc)


def changes_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("event_id", "status", "confirmation_id"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = world.all(f"SELECT * FROM booking_changes {where} ORDER BY change_id", params)
    return {"total": len(rows), "changes": [_change(row) for row in rows]}


def changes_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _change(world.one("SELECT * FROM booking_changes WHERE change_id = ?", (args["change_id"],), missing=f"change {args['change_id']} not found"))


def changes_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "travel.changes.create"
    confirmation = world.one("SELECT * FROM ticketing_confirmations WHERE confirmation_id = ?", (args["confirmation_id"],), missing=f"confirmation {args['confirmation_id']} not found")
    if confirmation["status"] != "OPEN":
        raise ValueError(f"confirmation {args['confirmation_id']} is {confirmation['status']}")
    if confirmation["valid_until"] < world.as_of.isoformat():
        raise ValueError(f"confirmation {args['confirmation_id']} expired on {confirmation['valid_until']}")
    booking_ids = list(args["booking_ids"])
    if not booking_ids:
        raise ValueError("booking_ids must name at least one ticketed booking")
    if len(set(booking_ids)) != len(booking_ids):
        raise ValueError("booking_ids must be unique")
    if len(booking_ids) > int(confirmation["seats_available"]):
        raise ValueError(f"confirmation {args['confirmation_id']} holds {confirmation['seats_available']} seats; {len(booking_ids)} changes requested")
    new_travel_date = _iso(args["new_travel_date"], "new_travel_date").isoformat()
    option = args["ticketing_option"]
    expected = confirmation["standard_ticketing_date"] if option == "standard" else confirmation["rush_ticketing_date"]
    if new_travel_date <= expected:
        raise ValueError(f"tickets on {args['confirmation_id']} issue on {expected} under {option} ticketing; a {new_travel_date} departure cannot precede issue")
    fees = 0.0
    for booking_id in booking_ids:
        booking = world.one("SELECT * FROM bookings WHERE booking_id = ?", (booking_id,), missing=f"booking {booking_id} not found")
        if booking["event_id"] != confirmation["event_id"]:
            raise ValueError(f"booking {booking_id} belongs to {booking['event_id']}, not {confirmation['event_id']}")
        if booking["status"] != "ticketed":
            raise ValueError(f"booking {booking_id} is {booking['status']} and cannot be changed")
        if not _bool(booking["changeable"]):
            raise ValueError(f"booking {booking_id} ({booking['fare_class']}) is not changeable; a basic fare is forfeited and re-issued at the group fare, not changed")
        fees += float(booking["change_fee_usd"])
    change_id = world.next_id("booking_changes", "change_id", "CHG-")
    canonical = sorted(booking_ids)
    row = {
        "change_id": change_id,
        "confirmation_id": confirmation["confirmation_id"],
        "event_id": confirmation["event_id"],
        "booking_ids_json": json.dumps(canonical),
        "booking_count": len(canonical),
        "new_travel_date": new_travel_date,
        "ticketing_option": option,
        "change_fees_usd": fees,
        "rush_fee_usd": float(confirmation["rush_fee_usd"]) if option == "rush" else 0.0,
        "expected_ticketing_date": expected,
        "status": "SUBMITTED",
        "requested_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO booking_changes (change_id, confirmation_id, event_id, booking_ids_json, booking_count, new_travel_date, ticketing_option, change_fees_usd, rush_fee_usd, expected_ticketing_date, status, requested_by, created_at, revision) "
        "VALUES (:change_id, :confirmation_id, :event_id, :booking_ids_json, :booking_count, :new_travel_date, :ticketing_option, :change_fees_usd, :rush_fee_usd, :expected_ticketing_date, :status, :requested_by, :created_at, :revision)",
        row,
    )
    world.audit(tool, "booking_changes", change_id, "insert", row)
    world.record_mutation(tool, "booking_changes", change_id, "SUBMITTED", {**args, "booking_ids": canonical})
    return _change(row)


# --------------------------------------------------------------------------- #
# Budget system
# --------------------------------------------------------------------------- #


def lines_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("cost_center", "fiscal_period", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"lines": [_line(row) for row in world.all(f"SELECT * FROM budget_lines {where} ORDER BY line_id", params)]}


def lines_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _line(world.one("SELECT * FROM budget_lines WHERE line_id = ?", (args["line_id"],), missing=f"budget line {args['line_id']} not found"))


def adjustments_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("line_id", "status", "related_event_id"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = world.all(f"SELECT * FROM budget_adjustments {where} ORDER BY adjustment_id", params)
    return {"total": len(rows), "adjustments": [_adjustment(row) for row in rows]}


def adjustments_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _adjustment(world.one("SELECT * FROM budget_adjustments WHERE adjustment_id = ?", (args["adjustment_id"],), missing=f"adjustment {args['adjustment_id']} not found"))


def adjustments_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "expense.adjustments.create"
    line = world.one("SELECT * FROM budget_lines WHERE line_id = ?", (args["line_id"],), missing=f"budget line {args['line_id']} not found")
    if line["status"] != "open":
        raise ValueError(f"budget line {args['line_id']} is {line['status']} and cannot be adjusted")
    amount = int(args["amount_usd"])
    if amount > int(line["adjustment_ceiling_usd"]):
        raise ValueError(f"USD {amount} exceeds the {args['line_id']} adjustment ceiling of USD {int(line['adjustment_ceiling_usd'])}; finance business partner release required")
    if not args["reason"].strip():
        raise ValueError("reason is required")
    if args.get("related_event_id"):
        world.one("SELECT event_id FROM events WHERE event_id = ?", (args["related_event_id"],), missing=f"Event/{args['related_event_id']} not found")
    adjustment_id = world.next_id("budget_adjustments", "adjustment_id", "ADJ-")
    row = {
        "adjustment_id": adjustment_id,
        "line_id": line["line_id"],
        "amount_usd": amount,
        "reason": args["reason"],
        "related_event_id": args.get("related_event_id"),
        "status": "SUBMITTED",
        "requested_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO budget_adjustments (adjustment_id, line_id, amount_usd, reason, related_event_id, status, requested_by, created_at, revision) "
        "VALUES (:adjustment_id, :line_id, :amount_usd, :reason, :related_event_id, :status, :requested_by, :created_at, :revision)",
        row,
    )
    world.audit(tool, "budget_adjustments", adjustment_id, "insert", row)
    reserved = float(line["reserved_usd"]) + amount
    revision = int(line["revision"]) + 1
    world.connection.execute("UPDATE budget_lines SET reserved_usd = ?, revision = ?, last_updated = ? WHERE line_id = ?", (reserved, revision, world.clock(), line["line_id"]))
    world.audit(tool, "budget_lines", line["line_id"], "update", {"reserved_usd": reserved, "revision": revision})
    world.record_mutation(tool, "budget_adjustments", adjustment_id, "SUBMITTED", args)
    return _adjustment(row)


# --------------------------------------------------------------------------- #
# Approvals, chat, drafts
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


def chat_threads_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    query = args["q"].strip().strip('"')
    rows = world.all("SELECT thread_id, channel, title FROM chat_threads WHERE instr(title, ?) > 0 OR instr(messages_json, ?) > 0 ORDER BY thread_id", (query, query))
    return {"threads": rows}


def chat_threads_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM chat_threads WHERE thread_id = ?", (args["thread_id"],), missing=f"thread {args['thread_id']} not found")
    return {"thread_id": row["thread_id"], "channel": row["channel"], "title": row["title"], "messages": json.loads(row["messages_json"])}


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
        "related_event_id": args.get("related_event_id"),
        "related_line_id": args.get("related_line_id"),
        "created_at": world.clock(),
        "status": "DRAFT",
    }
    world.connection.execute(
        "INSERT INTO note_drafts (draft_id, recipient, subject, body, related_event_id, related_line_id, created_at, status) "
        "VALUES (:draft_id, :recipient, :subject, :body, :related_event_id, :related_line_id, :created_at, :status)",
        row,
    )
    world.audit(tool, "note_drafts", draft_id, "insert", row)
    world.record_mutation(tool, "note_drafts", draft_id, "DRAFT", args)
    return dict(row)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

ISO_DATE = "ISO date, YYYY-MM-DD"
MONDAY = "ISO date of a Monday (venue weeks run Monday to Sunday)"

TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec("mail.messages.list", "Search the workplace-operations mailbox by keyword (subject, body, labels).", obj({"q": string(), "max_results": integer(minimum=1)}, ["q"]), "read", messages_list, "mailbox search"),
    ToolSpec("mail.messages.get", "Read one message with body and attachment list.", obj({"message_id": string()}, ["message_id"]), "read", messages_get, "mailbox message"),
    ToolSpec("mail.threads.get", "Read every message in one mail thread.", obj({"thread_id": string()}, ["thread_id"]), "read", threads_get, "mailbox thread"),
    ToolSpec("calendar.events.list", "Search calendar events by keyword (title, description, id), organizer, or date range.", obj({"q": string(), "organizer_id": string(), "start_date": string(ISO_DATE), "end_date": string(ISO_DATE)}), "read", events_list, "calendar event search"),
    ToolSpec("calendar.events.get", "Read one calendar event: dates, session days, venue, organizer, linked agenda and budget line, revision.", obj({"event_id": string()}, ["event_id"]), "read", events_get, "calendar event record"),
    ToolSpec("calendar.attendees.list", "List an event's attendees with required flag, response, home office, and timezone.", obj({"event_id": string(), "required": {"type": "boolean"}}, ["event_id"]), "read", attendees_list, "calendar attendee list"),
    ToolSpec("calendar.freebusy.query", "Free/busy blocks for an event's attendees (or named people) inside a date range, with the hard-conflict flag per block.", obj({"event_id": string(), "person_ids": {"type": "array", "items": {"type": "string"}}, "start_date": string(ISO_DATE), "end_date": string(ISO_DATE)}, ["start_date", "end_date"]), "read", freebusy_query, "calendar free/busy"),
    ToolSpec("calendar.rooms.list", "List bookable in-house rooms with capacity, optionally for one office.", obj({"office_id": string()}), "read", rooms_list, "calendar room directory"),
    ToolSpec(
        "calendar.events.update",
        "Move or re-locate an event. Required attendees with a protected hard conflict (board meeting, customer commitment, leave, conference) on the new dates block the move; the record revision increments.",
        obj({"event_id": string(), "start_date": string(ISO_DATE), "end_date": string(ISO_DATE), "venue_id": string(), "location": string(), "description": string()}, ["event_id"]),
        "write",
        events_update,
        "calendar event update",
        idempotent=False,
    ),
    ToolSpec("directory.people.search", "Search the people directory by name, email, team, title, or office.", obj({"q": string(), "team": string(), "office_id": string()}), "read", people_search, "directory search"),
    ToolSpec("directory.people.get", "Read one person: title, team, home office, timezone.", obj({"person_id": string()}, ["person_id"]), "read", people_get, "directory person"),
    ToolSpec("directory.offices.list", "List offices with city, timezone, and region.", obj({}), "read", offices_list, "directory offices"),
    ToolSpec("docs.documents.list", "Search documents by title, folder, or id.", obj({"q": string()}, ["q"]), "read", documents_list, "document search"),
    ToolSpec("docs.documents.get", "Read one document's metadata and current revision number.", obj({"doc_id": string()}, ["doc_id"]), "read", documents_get, "document record"),
    ToolSpec("docs.revisions.list", "List a document's revisions with status (current / superseded / draft).", obj({"doc_id": string()}, ["doc_id"]), "read", revisions_list, "document revision list"),
    ToolSpec("docs.revisions.get", "Read one document revision: body and structured metadata.", obj({"revision_id": string()}, ["revision_id"]), "read", revisions_get, "document revision"),
    ToolSpec("sheets.spreadsheets.list", "Search spreadsheets by title, folder, or id.", obj({"q": string()}, ["q"]), "read", spreadsheets_list, "spreadsheet search"),
    ToolSpec("sheets.spreadsheets.get", "Read a spreadsheet's metadata and version history.", obj({"spreadsheet_id": string()}, ["spreadsheet_id"]), "read", spreadsheets_get, "spreadsheet record"),
    ToolSpec("sheets.values.get", "Read the cell rows of a spreadsheet version (default: the current version).", obj({"spreadsheet_id": string(), "version": integer(minimum=1)}, ["spreadsheet_id"]), "read", values_get, "spreadsheet values"),
    ToolSpec("drive.files.list", "Search shared-drive files by keyword (name, folder, content).", obj({"q": string()}, ["q"]), "read", drive_files_list, "shared drive search"),
    ToolSpec("drive.files.get", "Read shared-drive file metadata.", obj({"file_id": string()}, ["file_id"]), "read", drive_files_get, "shared drive file"),
    ToolSpec("drive.files.export", "Export a shared-drive file as text (spreadsheets as CSV, PDFs as extracted text).", obj({"file_id": string()}, ["file_id"]), "read", drive_files_export, "shared drive export"),
    ToolSpec("venues.venues.search", "Search venues on the booking portal by name or city.", obj({"q": string(), "city": string()}), "read", venues_search, "venue portal search"),
    ToolSpec("venues.venues.get", "Read one venue: capacity, local office, hold policy, deposit terms, events director.", obj({"venue_id": string()}, ["venue_id"]), "read", venues_get, "venue portal record"),
    ToolSpec("venues.availability.list", "Venue availability calendar by week (open / held / booked / blackout) between two Mondays.", obj({"venue_id": string(), "start_week": string(MONDAY), "end_week": string(MONDAY), "status": string()}, ["venue_id", "start_week", "end_week"]), "read", availability_list, "venue availability calendar"),
    ToolSpec("venues.quotes.list", "List venue quotes by venue, event, or status.", obj({"venue_id": string(), "event_id": string(), "status": string()}), "read", quotes_list, "venue quote search"),
    ToolSpec("venues.quotes.get", "Read one venue quote: week, days, total, deposit, validity, status.", obj({"quote_id": string()}, ["quote_id"]), "read", quotes_get, "venue quote"),
    ToolSpec("venues.holds.list", "List venue holds by event, venue, or status.", obj({"event_id": string(), "venue_id": string(), "status": string()}), "read", holds_list, "venue hold search"),
    ToolSpec("venues.holds.get", "Read one venue hold.", obj({"hold_id": string()}, ["hold_id"]), "read", holds_get, "venue hold"),
    ToolSpec(
        "venues.holds.create",
        "Place a hold on an open venue week against a current quote. The deposit is taken from the quote; held, booked, and blackout weeks are never displaced.",
        obj({"venue_id": string(), "week_start": string(MONDAY), "quote_id": string(), "event_id": string()}, ["venue_id", "week_start", "quote_id", "event_id"]),
        "write",
        holds_create,
        "venue hold create",
        idempotent=False,
    ),
    ToolSpec("travel.policies.list", "List travel and events policy versions.", obj({}), "read", policies_list, "travel policy list"),
    ToolSpec("travel.policies.get", "Read one travel policy version with its structured parameters (per-diem, fare caps, thresholds, contingency).", obj({"policy_id": string()}, ["policy_id"]), "read", policies_get, "travel policy record"),
    ToolSpec("travel.bookings.list", "List an event's bookings: traveller, fare class, changeability, change fee, refundability, status.", obj({"event_id": string(), "person_id": string(), "status": string(), "kind": string()}, ["event_id"]), "read", bookings_list, "travel booking list"),
    ToolSpec("travel.bookings.get", "Read one booking.", obj({"booking_id": string()}, ["booking_id"]), "read", bookings_get, "travel booking"),
    ToolSpec("travel.confirmations.list", "List group-desk ticketing confirmations by event or travel management company.", obj({"event_id": string(), "tmc_id": string(), "status": string()}), "read", confirmations_list, "ticketing confirmation search"),
    ToolSpec("travel.confirmations.get", "Read one ticketing confirmation: seats, group fare, standard and rush ticketing dates, rush fee, validity.", obj({"confirmation_id": string()}, ["confirmation_id"]), "read", confirmations_get, "ticketing confirmation"),
    ToolSpec("travel.changes.list", "List booking-change requests by event, status, or confirmation.", obj({"event_id": string(), "status": string(), "confirmation_id": string()}), "read", changes_list, "booking change search"),
    ToolSpec("travel.changes.get", "Read one booking-change request.", obj({"change_id": string()}, ["change_id"]), "read", changes_get, "booking change"),
    ToolSpec(
        "travel.changes.create",
        "Submit a booking-change request to the group desk: only ticketed, changeable bookings of the confirmation's event may move; the count is bounded by the confirmation's seats and the ticketing date is set by the chosen option.",
        obj(
            {"confirmation_id": string(), "booking_ids": {"type": "array", "items": {"type": "string"}}, "new_travel_date": string(ISO_DATE), "ticketing_option": {"type": "string", "enum": ["standard", "rush"]}},
            ["confirmation_id", "booking_ids", "new_travel_date", "ticketing_option"],
        ),
        "write",
        changes_create,
        "booking change create",
        idempotent=False,
    ),
    ToolSpec("expense.budget_lines.list", "List budget lines by cost centre, fiscal period, or status.", obj({"cost_center": string(), "fiscal_period": string(), "status": string()}), "read", lines_list, "budget line list"),
    ToolSpec("expense.budget_lines.get", "Read one budget line: approved, committed, reserved, gross remaining, adjustment ceiling, revision.", obj({"line_id": string()}, ["line_id"]), "read", lines_get, "budget line record"),
    ToolSpec("expense.adjustments.list", "List budget-line adjustments by line, status, or related event.", obj({"line_id": string(), "status": string(), "related_event_id": string()}), "read", adjustments_list, "budget adjustment search"),
    ToolSpec("expense.adjustments.get", "Read one budget-line adjustment.", obj({"adjustment_id": string()}, ["adjustment_id"]), "read", adjustments_get, "budget adjustment"),
    ToolSpec(
        "expense.adjustments.create",
        "Submit a budget-line adjustment. The amount must sit within the line's adjustment ceiling; the line's reserved balance and revision move with it.",
        obj({"line_id": string(), "amount_usd": integer(minimum=1), "reason": string(), "related_event_id": string()}, ["line_id", "amount_usd", "reason"]),
        "write",
        adjustments_create,
        "budget adjustment create",
        idempotent=False,
    ),
    ToolSpec("approvals.list", "List approval records, optionally by keyword.", obj({"q": string()}), "read", approvals_list, "approval workflow record"),
    ToolSpec("approvals.get", "Read one approval record with its exact scope and approver.", obj({"approval_id": string()}, ["approval_id"]), "read", approvals_get, "approval workflow record"),
    ToolSpec("chat.threads.list", "Search team chat threads by keyword.", obj({"q": string()}, ["q"]), "read", chat_threads_list, "team chat search"),
    ToolSpec("chat.threads.get", "Read one team chat thread.", obj({"thread_id": string()}, ["thread_id"]), "read", chat_threads_get, "team chat thread"),
    ToolSpec(
        "notes.drafts.create",
        "Create, but do not send, a stakeholder draft note.",
        obj({"recipient": string(), "subject": string(), "body": string(), "related_event_id": string(), "related_line_id": string()}, ["recipient", "subject", "body"]),
        "write",
        drafts_create,
        "collaboration draft",
        idempotent=False,
    ),
)

SERVERS = {
    "mail": "Workplace-operations mailbox (Gmail / Outlook shaped): messages and threads.",
    "calendar": "Calendar service (Google Calendar shaped): events, attendees, free/busy with hard-conflict flags, rooms.",
    "directory": "People directory: people, teams, home offices, and timezones.",
    "docs": "Documents service (Docs shaped): agenda documents with revisions.",
    "sheets": "Spreadsheet service (Sheets shaped): budget workbooks with versions.",
    "drive": "Shared drive (Drive shaped) holding policies, registers, calendars, quotes, and exports.",
    "venues": "Venue booking portal: venues, weekly availability, quotes, and holds.",
    "travel": "Corporate travel desk: policy versions, bookings, group-ticketing confirmations, and booking changes.",
    "expense": "Budget and expense system: budget lines and adjustments.",
    "approvals": "Approval workflow records with exact scope.",
    "chat": "Workplace-operations chat threads.",
    "notes": "Stakeholder draft notes (never sent by the benchmark).",
}

__all__ = ["HARD_KINDS", "SERVERS", "SOFT_KINDS", "TOOLS", "add_business_days"]
