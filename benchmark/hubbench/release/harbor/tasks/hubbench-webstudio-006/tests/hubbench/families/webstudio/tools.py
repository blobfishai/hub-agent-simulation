"""WebStudio provider-shaped tools over the family's SQLite world.

Read tools return CMS, design-token registry, design-file, asset-library,
checklist, deploy-lane, and vendor-quote records; write tools persist to the
domain tables, refresh the affected records, and record the exact payload for
the sealed contract.  There is no LLM anywhere here.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from ...engine.families import ToolSpec
from ...engine.validation import integer, obj, string
from ...engine.world import World

TERRITORY_UNIT = "TERRITORY"
CONSUMER_UNIT = "CONSUMER"


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #


def _page(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "page_id": row["page_id"],
        "slug": row["slug"],
        "title": row["title"],
        "owner_team": row["owner_team"],
        "owner": f"Person/{row['owner_person_id']}" if row.get("owner_person_id") else None,
        "markets": json.loads(row["markets_json"]),
        "status": row["status"],
    }


def _change_request(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "change_request_id": row["cr_id"],
        "page": f"Page/{row['page_id']}",
        "title": row["title"],
        "kind": row["kind"],
        "status": row["status"],
        "priority": row["priority"],
        "launch_territories": json.loads(row["territories_json"]),
        "entries_in_scope": row["entries_in_scope"],
        "scope_note": row["scope_note"],
        "deploy_minutes": row["deploy_minutes"],
        "verify_minutes": row["verify_minutes"],
        "duplicate_of": row.get("duplicate_of"),
        "impact_panel_consumers": row.get("impact_consumers"),
        "opened_at": row["opened_at"],
        "requested_by": f"Person/{row['requested_by']}",
        "note": row.get("note") or "",
    }


def _entry(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "entry_id": row["entry_id"],
        "page": f"Page/{row['page_id']}",
        "change_request": f"ChangeRequest/{row['cr_id']}" if row.get("cr_id") else None,
        "content_type": row["content_type"],
        "title": row["title"],
        "status": row["status"],
        "revision": row["revision"],
        "bound_token": row.get("bound_token_id"),
        "bound_component": row.get("bound_component_id"),
        "bound_asset": row.get("bound_asset_id"),
        "blocked_reason": row.get("blocked_reason"),
    }


def _release(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["release_id"],
        "status": row["status"],
        "description": row.get("description"),
        "start": row.get("start_time"),
        "end": row.get("end_time"),
        "lane": row.get("lane_id"),
        "page": f"Page/{row['page_id']}",
        "change_request": f"ChangeRequest/{row['cr_id']}" if row.get("cr_id") else None,
        "entry_count": row.get("entry_count"),
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
        "release": row.get("release_id"),
    }


def _licence(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "licence_id": row["licence_id"],
        "asset": f"Asset/{row['asset_id']}",
        "vendor": f"Vendor/{row['vendor_id']}",
        "reference": row["reference"],
        "territories": json.loads(row["territories_json"]),
        "territory_count": row["territory_count"],
        "usage_scope": row["usage_scope"],
        "expires_on": row["expires_on"],
        "status": row["status"],
        "status_reason": row.get("status_reason"),
        "reserved_for_change_request": row.get("reserved_for_cr"),
    }


def _pin(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "pin_id": row["pin_id"],
        "token": f"Token/{row['token_id']}",
        "version": row["version"],
        "change_request": f"ChangeRequest/{row['cr_id']}",
        "consumer_count": row["consumer_count"],
        "unit": row["unit"],
        "status": row["status"],
        "requested_by": row["requested_by"],
        "created_at": row["created_at"],
        "meta": {"versionId": str(row["revision"])},
    }


# --------------------------------------------------------------------------- #
# CMS reads
# --------------------------------------------------------------------------- #


def pages_search(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("slug"):
        rows = world.all("SELECT * FROM pages WHERE slug = ? ORDER BY page_id", (args["slug"],))
    elif args.get("name"):
        rows = world.all("SELECT * FROM pages WHERE instr(lower(title), lower(?)) > 0 OR instr(lower(slug), lower(?)) > 0 ORDER BY page_id", (args["name"], args["name"]))
    else:
        raise ValueError("slug or name is required")
    return {"total": len(rows), "pages": [_page(row) for row in rows]}


def pages_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _page(world.one("SELECT * FROM pages WHERE page_id = ?", (args["page_id"],), missing=f"Page/{args['page_id']} not found"))


def entries_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    if args.get("page_id"):
        clauses.append("page_id = ?")
        params.append(args["page_id"])
    if args.get("change_request_id"):
        clauses.append("cr_id = ?")
        params.append(args["change_request_id"])
    if args.get("status"):
        clauses.append("status = ?")
        params.append(args["status"])
    if not clauses:
        raise ValueError("at least one of page_id, change_request_id, status is required")
    rows = world.all(f"SELECT * FROM entries WHERE {' AND '.join(clauses)} ORDER BY entry_id", params)
    return {"total": len(rows), "entries": [_entry(row) for row in rows]}


def entries_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _entry(world.one("SELECT * FROM entries WHERE entry_id = ?", (args["entry_id"],), missing=f"Entry/{args['entry_id']} not found"))


def change_requests_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key, column in (("page_id", "page_id"), ("status", "status"), ("kind", "kind")):
        if args.get(key):
            clauses.append(f"{column} = ?")
            params.append(args[key])
    if not clauses:
        raise ValueError("at least one of page_id, status, kind is required")
    rows = world.all(f"SELECT * FROM change_requests WHERE {' AND '.join(clauses)} ORDER BY cr_id", params)
    return {"total": len(rows), "change_requests": [_change_request(row) for row in rows]}


def change_requests_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM change_requests WHERE cr_id = ?", (args["change_request_id"],), missing=f"ChangeRequest/{args['change_request_id']} not found")
    return _change_request(row)


def releases_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key, column in (("page_id", "page_id"), ("change_request_id", "cr_id"), ("lane_id", "lane_id"), ("status", "status")):
        if args.get(key):
            clauses.append(f"{column} = ?")
            params.append(args[key])
    if args.get("start_date"):
        clauses.append("substr(start_time, 1, 10) >= ?")
        params.append(args["start_date"])
    if args.get("end_date"):
        clauses.append("substr(start_time, 1, 10) <= ?")
        params.append(args["end_date"])
    if not clauses:
        raise ValueError("at least one filter is required")
    rows = world.all(f"SELECT * FROM releases WHERE {' AND '.join(clauses)} ORDER BY start_time, release_id", params)
    return {"total": len(rows), "releases": [_release(row) for row in rows]}


def releases_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _release(world.one("SELECT * FROM releases WHERE release_id = ?", (args["release_id"],), missing=f"Release/{args['release_id']} not found"))


# --------------------------------------------------------------------------- #
# CMS writes: scheduled releases against the deploy-lane calendar
# --------------------------------------------------------------------------- #


def _split_datetime(value: str, label: str) -> tuple[str, str]:
    if len(value) != 19 or value[10] != "T":
        raise ValueError(f"{label} must be YYYY-MM-DDTHH:MM:SS")
    date.fromisoformat(value[:10])
    return value[:10], value[11:]


def _windows_for_interval(world: World, lane_id: str, start: str, end: str) -> list[dict[str, Any]]:
    start_date, start_time = _split_datetime(start, "start_time")
    end_date, end_time = _split_datetime(end, "end_time")
    if start_date != end_date:
        raise ValueError("a deploy must start and end on the same service date")
    if start_time >= end_time:
        raise ValueError("start_time must precede end_time")
    rows = world.all("SELECT * FROM deploy_windows WHERE lane_id = ? AND service_date = ? ORDER BY start_time", (lane_id, start_date))
    covering = [row for row in rows if row["start_time"] < end_time and row["end_time"] > start_time]
    if not covering:
        raise ValueError(f"no {lane_id} window covers {start} - {end}")
    if start_time < min(row["start_time"] for row in covering) or end_time > max(row["end_time"] for row in covering):
        raise ValueError(f"{start} - {end} falls outside the {lane_id} deploy windows")
    return covering


def _require_free(windows: list[dict[str, Any]], *, holder: str | None = None) -> None:
    for row in windows:
        if row["status"] == "free":
            continue
        if holder and row.get("release_id") == holder:
            continue
        raise ValueError(f"{row['window_id']} is {row['status']}: {row.get('hold_reason') or 'not available'}; protected and blocked windows cannot be displaced")


def _claim(world: World, tool: str, windows: list[dict[str, Any]], release_id: str) -> None:
    for row in windows:
        world.connection.execute("UPDATE deploy_windows SET status = 'busy', hold_reason = 'scheduled release', release_id = ? WHERE window_id = ?", (release_id, row["window_id"]))
        world.audit(tool, "deploy_windows", row["window_id"], "update", {"status": "busy", "release_id": release_id})


def _release_windows(world: World, tool: str, release_id: str) -> None:
    for row in world.all("SELECT window_id FROM deploy_windows WHERE release_id = ?", (release_id,)):
        world.connection.execute("UPDATE deploy_windows SET status = 'free', hold_reason = NULL, release_id = NULL WHERE window_id = ?", (row["window_id"],))
        world.audit(tool, "deploy_windows", row["window_id"], "update", {"status": "free", "release_id": None})


def shippable_entries(world: World, cr_id: str) -> tuple[int, int]:
    """(shippable, total) entries for a change request: REVIEWED and not blocked."""

    rows = world.all("SELECT status, blocked_reason FROM entries WHERE cr_id = ?", (cr_id,))
    shippable = sum(1 for row in rows if row["status"] == "REVIEWED" and not row.get("blocked_reason"))
    return shippable, len(rows)


def _active_lane(world: World, lane_id: str) -> dict[str, Any]:
    lane = world.one("SELECT * FROM lanes WHERE lane_id = ?", (lane_id,), missing=f"lane {lane_id} not found")
    if lane["status"] != "ACTIVE":
        raise ValueError(f"{lane_id} is {lane['status']}: {lane.get('status_note') or ''}".strip())
    return lane


def releases_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "cms.releases.create"
    cr = world.one("SELECT * FROM change_requests WHERE cr_id = ?", (args["change_request_id"],), missing=f"ChangeRequest/{args['change_request_id']} not found")
    if cr["status"] != "open":
        raise ValueError(f"ChangeRequest/{args['change_request_id']} is {cr['status']} and cannot be scheduled")
    _active_lane(world, args["lane_id"])
    entry_count = args.get("entry_count")
    if entry_count is not None:
        shippable, total = shippable_entries(world, cr["cr_id"])
        if entry_count > shippable:
            raise ValueError(
                f"only {shippable} of {cr['cr_id']}'s {total} entries are shippable (REVIEWED and not blocked by an unpinned breaking change or a missing licence); "
                f"a subset release cannot carry {entry_count}"
            )
    windows = _windows_for_interval(world, args["lane_id"], args["start_time"], args["end_time"])
    _require_free(windows)
    release_id = world.next_id("releases", "release_id", "REL-")
    row = {
        "release_id": release_id,
        "page_id": cr["page_id"],
        "cr_id": cr["cr_id"],
        "lane_id": args["lane_id"],
        "start_time": args["start_time"],
        "end_time": args["end_time"],
        "status": "scheduled",
        "description": args.get("description"),
        "entry_count": entry_count,
        "revision": 1,
        "last_updated": world.clock(),
    }
    world.connection.execute(
        "INSERT INTO releases (release_id, page_id, cr_id, lane_id, start_time, end_time, status, description, entry_count, revision, last_updated) "
        "VALUES (:release_id, :page_id, :cr_id, :lane_id, :start_time, :end_time, :status, :description, :entry_count, :revision, :last_updated)",
        row,
    )
    world.audit(tool, "releases", release_id, "insert", row)
    _claim(world, tool, windows, release_id)
    world.record_mutation(tool, "releases", release_id, "scheduled", args)
    return _release(row)


def releases_update(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "cms.releases.update"
    current = world.one("SELECT * FROM releases WHERE release_id = ?", (args["release_id"],), missing=f"Release/{args['release_id']} not found")
    if current["status"] in {"cancelled", "deployed"}:
        raise ValueError(f"Release/{args['release_id']} is {current['status']} and cannot be changed")
    changes = {key: args[key] for key in ("lane_id", "start_time", "end_time", "status", "description") if key in args}
    if not changes:
        raise ValueError("no change requested")
    updated = {**current, **changes}
    new_status = updated["status"]
    if new_status == "cancelled":
        _release_windows(world, tool, current["release_id"])
    else:
        if any(key in changes for key in ("lane_id", "start_time", "end_time")) or current["status"] != "scheduled":
            if not (updated.get("lane_id") and updated.get("start_time") and updated.get("end_time")):
                raise ValueError("scheduling a release needs lane_id, start_time, and end_time")
            _active_lane(world, updated["lane_id"])
            windows = _windows_for_interval(world, updated["lane_id"], updated["start_time"], updated["end_time"])
            _require_free(windows, holder=current["release_id"])
            _release_windows(world, tool, current["release_id"])
            _claim(world, tool, windows, current["release_id"])
            if new_status not in {"scheduled", "pending"}:
                raise ValueError(f"unsupported status transition to {new_status}")
    updated["revision"] = int(current["revision"]) + 1
    updated["last_updated"] = world.clock()
    world.connection.execute(
        "UPDATE releases SET lane_id = :lane_id, start_time = :start_time, end_time = :end_time, status = :status, description = :description, revision = :revision, last_updated = :last_updated WHERE release_id = :release_id",
        updated,
    )
    world.audit(tool, "releases", current["release_id"], "update", changes)
    world.record_mutation(tool, "releases", current["release_id"], new_status, args, revision=updated["revision"])
    return _release(updated)


# --------------------------------------------------------------------------- #
# Design-token and component registry
# --------------------------------------------------------------------------- #


def _versions(world: World, token_id: str) -> list[dict[str, Any]]:
    rows = world.all("SELECT * FROM token_versions WHERE token_id = ? ORDER BY released_on, version", (token_id,))
    return [{"version": r["version"], "value": r["value"], "status": r["status"], "breaking": bool(r["breaking"]), "released_on": r["released_on"], "note": r.get("note") or ""} for r in rows]


def tokens_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM tokens WHERE token_id = ?", (args["token_id"],), missing=f"Token/{args['token_id']} not found")
    token_set = world.one("SELECT * FROM token_sets WHERE set_id = ?", (row["set_id"],))
    return {
        "token_id": row["token_id"],
        "name": row["name"],
        "kind": row["kind"],
        "set": {"set_id": token_set["set_id"], "name": token_set["name"], "current_version": token_set["current_version"]},
        "versions": _versions(world, row["token_id"]),
    }


def versions_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT token_id FROM tokens WHERE token_id = ?", (args["token_id"],), missing=f"Token/{args['token_id']} not found")
    return {"token_id": args["token_id"], "versions": _versions(world, args["token_id"])}


def components_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("library", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = world.all(f"SELECT * FROM components {where} ORDER BY component_id", params)
    return {"components": [_component(row) for row in rows]}


def _component(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "component_id": row["component_id"],
        "name": row["name"],
        "library": row["library"],
        "version": row["version"],
        "allowed_variants": json.loads(row["allowed_variants_json"]),
        "status": row["status"],
        "deprecated": bool(row["deprecated"]),
        "breaking_change_pending": bool(row["breaking_change_pending"]),
        "note": row.get("note") or "",
    }


def components_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _component(world.one("SELECT * FROM components WHERE component_id = ?", (args["component_id"],), missing=f"Component/{args['component_id']} not found"))


def consumers_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    if args.get("token_id"):
        clauses.append("token_id = ?")
        params.append(args["token_id"])
    if args.get("component_id"):
        clauses.append("component_id = ?")
        params.append(args["component_id"])
    if not clauses:
        raise ValueError("token_id or component_id is required")
    if args.get("status"):
        clauses.append("status = ?")
        params.append(args["status"])
    rows = world.all(f"SELECT * FROM consumers WHERE {' AND '.join(clauses)} ORDER BY consumer_id", params)
    return {
        "total": len(rows),
        "consumers": [
            {"consumer_id": r["consumer_id"], "token": r.get("token_id"), "component": r.get("component_id"), "page": f"Page/{r['page_id']}", "surface": r["surface"], "status": r["status"], "note": r.get("note") or ""}
            for r in rows
        ],
        "note": "Gross registry rows; DEPRECATED and MIGRATED consumers are listed and must be excluded by the reader.",
    }


def pinnable_consumers(world: World, token_id: str, page_id: str) -> int:
    row = world.one("SELECT COUNT(*) AS n FROM consumers WHERE token_id = ? AND status = 'ACTIVE' AND page_id != ?", (token_id, page_id))
    return int(row["n"])


def pins_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _pin(world.one("SELECT * FROM token_pins WHERE pin_id = ?", (args["pin_id"],), missing=f"pin {args['pin_id']} not found"))


def pins_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "tokens.pins.create"
    world.one("SELECT token_id FROM tokens WHERE token_id = ?", (args["token_id"],), missing=f"Token/{args['token_id']} not found")
    world.one("SELECT version FROM token_versions WHERE token_id = ? AND version = ?", (args["token_id"], args["version"]), missing=f"{args['token_id']} has no version {args['version']}")
    cr = world.one("SELECT * FROM change_requests WHERE cr_id = ?", (args["change_request_id"],), missing=f"ChangeRequest/{args['change_request_id']} not found")
    if cr["status"] != "open":
        raise ValueError(f"ChangeRequest/{cr['cr_id']} is {cr['status']}; pins attach to open change requests only")
    existing = world.all("SELECT pin_id FROM token_pins WHERE token_id = ? AND cr_id = ? AND status = 'PINNED'", (args["token_id"], cr["cr_id"]))
    if existing:
        raise ValueError(f"{args['token_id']} is already pinned for {cr['cr_id']} ({existing[0]['pin_id']})")
    pinnable = pinnable_consumers(world, args["token_id"], cr["page_id"])
    if args["consumer_count"] > pinnable:
        raise ValueError(
            f"{args['token_id']} has {pinnable} active consumers outside {cr['page_id']}; deprecated, migrated, and on-page consumers are not pinned, so a pin cannot cover {args['consumer_count']}"
        )
    pin_id = world.next_id("token_pins", "pin_id", "PIN-")
    row = {
        "pin_id": pin_id,
        "token_id": args["token_id"],
        "version": args["version"],
        "cr_id": cr["cr_id"],
        "consumer_count": args["consumer_count"],
        "unit": CONSUMER_UNIT,
        "status": "PINNED",
        "requested_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO token_pins (pin_id, token_id, version, cr_id, consumer_count, unit, status, requested_by, created_at, revision) "
        "VALUES (:pin_id, :token_id, :version, :cr_id, :consumer_count, :unit, :status, :requested_by, :created_at, :revision)",
        row,
    )
    world.audit(tool, "token_pins", pin_id, "insert", row)
    world.record_mutation(tool, "token_pins", pin_id, "PINNED", args)
    return _pin(row)


# --------------------------------------------------------------------------- #
# Design-file index
# --------------------------------------------------------------------------- #


def design_files_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    if args.get("page_id"):
        clauses.append("page_id = ?")
        params.append(args["page_id"])
    if args.get("q"):
        query = args["q"].strip().strip('"')
        clauses.append("instr(lower(name), lower(?)) > 0")
        params.append(query)
    if not clauses:
        raise ValueError("page_id or q is required")
    rows = world.all(f"SELECT * FROM design_files WHERE {' AND '.join(clauses)} ORDER BY file_id", params)
    return {"files": rows}


def design_files_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM design_files WHERE file_id = ?", (args["file_id"],), missing=f"design file {args['file_id']} not found"))


def design_frames_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT file_id FROM design_files WHERE file_id = ?", (args["file_id"],), missing=f"design file {args['file_id']} not found")
    clauses, params = ["file_id = ?"], [args["file_id"]]
    if args.get("status"):
        clauses.append("status = ?")
        params.append(args["status"])
    rows = world.all(f"SELECT * FROM design_frames WHERE {' AND '.join(clauses)} ORDER BY frame_id", params)
    return {"file_id": args["file_id"], "frames": [{"frame_id": r["frame_id"], "name": r["name"], "status": r["status"], "components": json.loads(r["components_json"]), "note": r.get("note") or ""} for r in rows]}


# --------------------------------------------------------------------------- #
# Digital asset library
# --------------------------------------------------------------------------- #


def assets_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("page_id", "kind"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"assets": world.all(f"SELECT * FROM assets {where} ORDER BY asset_id", params)}


def assets_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM assets WHERE asset_id = ?", (args["asset_id"],), missing=f"Asset/{args['asset_id']} not found")
    vendor = world.one("SELECT * FROM vendors WHERE vendor_id = ?", (row["vendor_id"],))
    return {**row, "licence_required": bool(row["licence_required"]), "vendor_name": vendor["name"]}


def licences_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT asset_id FROM assets WHERE asset_id = ?", (args["asset_id"],), missing=f"Asset/{args['asset_id']} not found")
    clauses, params = ["asset_id = ?"], [args["asset_id"]]
    if args.get("status"):
        clauses.append("status = ?")
        params.append(args["status"])
    rows = world.all(f"SELECT * FROM licences WHERE {' AND '.join(clauses)} ORDER BY expires_on, licence_id", params)
    return {"asset_id": args["asset_id"], "licences": [_licence(row) for row in rows]}


def licence_requests_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM licence_requests WHERE request_id = ?", (args["request_id"],), missing=f"licence request {args['request_id']} not found"))


def licence_requests_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "dam.licence_requests.create"
    vendor = world.one("SELECT * FROM vendors WHERE vendor_id = ?", (args["vendor_id"],), missing=f"vendor {args['vendor_id']} not found")
    world.one("SELECT asset_id FROM assets WHERE asset_id = ?", (args["asset_id"],), missing=f"Asset/{args['asset_id']} not found")
    quote = world.one("SELECT * FROM licence_quotes WHERE quote_id = ?", (args["quote_id"],), missing=f"quote {args['quote_id']} not found")
    if quote["vendor_id"] != vendor["vendor_id"] or quote["asset_id"] != args["asset_id"]:
        raise ValueError(f"quote {args['quote_id']} does not cover {args['asset_id']} from {args['vendor_id']}")
    if quote["kind"] != "licence":
        raise ValueError(f"quote {args['quote_id']} is a {quote['kind']} quote, not a licence quote")
    if quote["status"] != "OPEN":
        raise ValueError(f"quote {args['quote_id']} is {quote['status']}")
    if args["territory_count"] > quote["units_available"]:
        raise ValueError(f"quote {args['quote_id']} covers at most {quote['units_available']} {TERRITORY_UNIT}")
    expected = quote["standard_issue_date"] if args["issuance_option"] == "standard" else quote["expedited_issue_date"]
    request_id = world.next_id("licence_requests", "request_id", "LR-")
    row = {
        "request_id": request_id,
        "vendor_id": vendor["vendor_id"],
        "quote_id": quote["quote_id"],
        "asset_id": args["asset_id"],
        "territory_count": args["territory_count"],
        "unit": TERRITORY_UNIT,
        "issuance_option": args["issuance_option"],
        "expected_licence_date": expected,
        "status": "SUBMITTED",
        "requested_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO licence_requests (request_id, vendor_id, quote_id, asset_id, territory_count, unit, issuance_option, expected_licence_date, status, requested_by, created_at, revision) "
        "VALUES (:request_id, :vendor_id, :quote_id, :asset_id, :territory_count, :unit, :issuance_option, :expected_licence_date, :status, :requested_by, :created_at, :revision)",
        row,
    )
    world.audit(tool, "licence_requests", request_id, "insert", row)
    world.record_mutation(tool, "licence_requests", request_id, "SUBMITTED", args)
    return dict(row)


# --------------------------------------------------------------------------- #
# Release checklist
# --------------------------------------------------------------------------- #


def gates_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT cr_id FROM change_requests WHERE cr_id = ?", (args["change_request_id"],), missing=f"ChangeRequest/{args['change_request_id']} not found")
    clauses, params = ["cr_id = ?"], [args["change_request_id"]]
    if args.get("category"):
        clauses.append("category = ?")
        params.append(args["category"])
    rows = world.all(f"SELECT * FROM checklist_gates WHERE {' AND '.join(clauses)} ORDER BY gate_id", params)
    return {"change_request_id": args["change_request_id"], "gates": rows}


def budgets_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT page_id FROM pages WHERE page_id = ?", (args["page_id"],), missing=f"Page/{args['page_id']} not found")
    rows = world.all("SELECT * FROM perf_budgets WHERE page_id = ? ORDER BY budget_id", (args["page_id"],))
    return {"page_id": args["page_id"], "budgets": [{**row, "headroom": round(row["budget_value"] - row["measured_value"], 2)} for row in rows]}


def waivers_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "checklist.waivers.create"
    gate = world.one("SELECT * FROM checklist_gates WHERE gate_id = ?", (args["gate_id"],), missing=f"gate {args['gate_id']} not found")
    if gate["cr_id"] != args["change_request_id"]:
        raise ValueError(f"gate {args['gate_id']} belongs to {gate['cr_id']}, not {args['change_request_id']}")
    if gate["category"] == "legal":
        raise ValueError(f"gate {args['gate_id']} is a legal gate and is never waived; an eligible licence grant is required")
    approval_id = args.get("approval_id")
    covering = None
    if approval_id:
        approval = world.one("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,), missing=f"approval {approval_id} not found")
        scope = json.loads(approval["scope_json"])
        if approval["status"] == "APPROVED" and approval["approver_role"] == gate["authority_role"] and gate["gate_id"] in scope.get("waivers", []):
            covering = approval
    if covering is None:
        raise ValueError(f"waiving {args['gate_id']} ({gate['category']}) requires the {gate['authority_role']}'s signed approval naming the gate")
    waiver_id = world.next_id("waivers", "waiver_id", "WVR-")
    row = {
        "waiver_id": waiver_id,
        "gate_id": gate["gate_id"],
        "cr_id": gate["cr_id"],
        "reason": args["reason"],
        "approval_id": approval_id,
        "status": "WAIVED",
        "requested_by": world.task["role"],
        "created_at": world.clock(),
    }
    world.connection.execute(
        "INSERT INTO waivers (waiver_id, gate_id, cr_id, reason, approval_id, status, requested_by, created_at) VALUES (:waiver_id, :gate_id, :cr_id, :reason, :approval_id, :status, :requested_by, :created_at)",
        row,
    )
    world.connection.execute("UPDATE checklist_gates SET status = 'WAIVED' WHERE gate_id = ?", (gate["gate_id"],))
    world.audit(tool, "waivers", waiver_id, "insert", row)
    world.audit(tool, "checklist_gates", gate["gate_id"], "update", {"status": "WAIVED"})
    world.record_mutation(tool, "waivers", waiver_id, "WAIVED", args)
    return dict(row)


# --------------------------------------------------------------------------- #
# CDN deploy lanes
# --------------------------------------------------------------------------- #


def lanes_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("pool"):
        rows = world.all("SELECT * FROM lanes WHERE pool = ? ORDER BY lane_id", (args["pool"],))
    else:
        rows = world.all("SELECT * FROM lanes ORDER BY lane_id")
    return {"lanes": [{**row, "rollback_capable": bool(row["rollback_capable"])} for row in rows]}


def windows_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses = ["service_date >= ?", "service_date <= ?"]
    params: list[Any] = [args["start_date"], args["end_date"]]
    if args.get("lane_id"):
        clauses.append("lane_id = ?")
        params.append(args["lane_id"])
    if args.get("status"):
        clauses.append("status = ?")
        params.append(args["status"])
    rows = world.all(f"SELECT * FROM deploy_windows WHERE {' AND '.join(clauses)} ORDER BY service_date, lane_id, session DESC", params)
    return {"windows": [_window(row) for row in rows]}


# --------------------------------------------------------------------------- #
# Vendor quotes, approvals, collaboration surfaces
# --------------------------------------------------------------------------- #


def quotes_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("asset_id", "vendor_id", "kind"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"quotes": world.all(f"SELECT * FROM licence_quotes {where} ORDER BY quote_id", params)}


def quotes_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM licence_quotes WHERE quote_id = ?", (args["quote_id"],), missing=f"quote {args['quote_id']} not found")
    vendor = world.one("SELECT * FROM vendors WHERE vendor_id = ?", (row["vendor_id"],))
    return {**row, "vendor_name": vendor["name"]}


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
        "related_change_request_id": args.get("related_change_request_id"),
        "related_page_id": args.get("related_page_id"),
        "created_at": world.clock(),
        "status": "DRAFT",
    }
    world.connection.execute(
        "INSERT INTO note_drafts (draft_id, recipient, subject, body, related_change_request_id, related_page_id, created_at, status) "
        "VALUES (:draft_id, :recipient, :subject, :body, :related_change_request_id, :related_page_id, :created_at, :status)",
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
    ToolSpec("cms.pages.search", "Search CMS pages by immutable slug or by title fragment.", obj({"slug": string("page slug"), "name": string("title fragment")}), "read", pages_search, "CMS page search"),
    ToolSpec("cms.pages.get", "Read one CMS page record with its market list and owner.", obj({"page_id": string()}, ["page_id"]), "read", pages_get, "CMS page record"),
    ToolSpec("cms.entries.list", "List CMS entries by page, change request, or status, with token / component / asset bindings and blocking reasons.", obj({"page_id": string(), "change_request_id": string(), "status": string()}), "read", entries_list, "CMS entry list"),
    ToolSpec("cms.entries.get", "Read one CMS entry.", obj({"entry_id": string()}, ["entry_id"]), "read", entries_get, "CMS entry record"),
    ToolSpec("cms.change_requests.list", "List change requests by page, status, or kind; duplicates and superseded requests are listed with their state.", obj({"page_id": string(), "status": string(), "kind": string()}), "read", change_requests_list, "CMS change request search"),
    ToolSpec("cms.change_requests.get", "Read one change request: launch territories, entries in scope, deploy and verification durations, and impact notes.", obj({"change_request_id": string()}, ["change_request_id"]), "read", change_requests_get, "CMS change request record"),
    ToolSpec("cms.releases.list", "List scheduled releases by page, change request, lane, status, or start-date window.", obj({"page_id": string(), "change_request_id": string(), "lane_id": string(), "status": string(), "start_date": string("ISO date"), "end_date": string("ISO date")}), "read", releases_list, "CMS scheduled release search"),
    ToolSpec("cms.releases.get", "Read one scheduled release.", obj({"release_id": string()}, ["release_id"]), "read", releases_get, "CMS scheduled release record"),
    ToolSpec(
        "cms.releases.create",
        "Schedule a release for a change request on a deploy lane. Every window the interval touches must be free; protected and blocked windows are never displaced. A subset release declares entry_count, which cannot exceed the change request's shippable entries.",
        obj(
            {"change_request_id": string(), "lane_id": string(), "start_time": string(DATETIME), "end_time": string(DATETIME), "entry_count": integer(minimum=1), "description": string()},
            ["change_request_id", "lane_id", "start_time", "end_time"],
        ),
        "write",
        releases_create,
        "CMS scheduled release create",
        idempotent=False,
    ),
    ToolSpec(
        "cms.releases.update",
        "Move, schedule, or cancel an existing release. Moving re-validates the target lane and windows; the record revision increments.",
        obj(
            {"release_id": string(), "lane_id": string(), "start_time": string(DATETIME), "end_time": string(DATETIME), "status": {"type": "string", "enum": ["scheduled", "pending", "cancelled"]}, "description": string()},
            ["release_id"],
        ),
        "write",
        releases_update,
        "CMS scheduled release update",
        idempotent=False,
    ),
    ToolSpec("tokens.tokens.get", "Read one design token with its set and every version (current, proposed, deprecated) and breaking flags.", obj({"token_id": string()}, ["token_id"]), "read", tokens_get, "design token record"),
    ToolSpec("tokens.versions.list", "List the versions of one design token with value, status, and breaking flag.", obj({"token_id": string()}, ["token_id"]), "read", versions_list, "design token version list"),
    ToolSpec("tokens.components.list", "List component-library components with allowed variants, deprecation, and pending breaking changes.", obj({"library": string(), "status": string()}), "read", components_list, "component registry list"),
    ToolSpec("tokens.components.get", "Read one component record.", obj({"component_id": string()}, ["component_id"]), "read", components_get, "component registry record"),
    ToolSpec("tokens.consumers.list", "List registry consumers of a token or component (gross: ACTIVE, DEPRECATED, and MIGRATED rows), optionally by status.", obj({"token_id": string(), "component_id": string(), "status": string()}), "read", consumers_list, "token consumer registry"),
    ToolSpec("tokens.pins.get", "Read one token version pin.", obj({"pin_id": string()}, ["pin_id"]), "read", pins_get, "token version pin"),
    ToolSpec(
        "tokens.pins.create",
        "Pin a token version for the active consumers outside a change request's page. The count cannot exceed the registry's active consumers outside that page; deprecated, migrated, and on-page consumers are never pinned.",
        obj({"token_id": string(), "version": string(), "change_request_id": string(), "consumer_count": integer(minimum=1)}, ["token_id", "version", "change_request_id", "consumer_count"]),
        "write",
        pins_create,
        "token version pin",
        idempotent=False,
    ),
    ToolSpec("design.files.list", "List design files by page or name fragment, with current / superseded status.", obj({"page_id": string(), "q": string()}), "read", design_files_list, "design file index"),
    ToolSpec("design.files.get", "Read one design file record.", obj({"file_id": string()}, ["file_id"]), "read", design_files_get, "design file record"),
    ToolSpec("design.frames.list", "List the frames of a design file with review status (APPROVED / IN_REVIEW / SUPERSEDED) and component usage.", obj({"file_id": string(), "status": string()}, ["file_id"]), "read", design_frames_list, "design frame list"),
    ToolSpec("dam.assets.list", "List library assets, optionally by page or kind.", obj({"page_id": string(), "kind": string()}), "read", assets_list, "asset library list"),
    ToolSpec("dam.assets.get", "Read one library asset with vendor and licence requirement.", obj({"asset_id": string()}, ["asset_id"]), "read", assets_get, "asset library record"),
    ToolSpec("dam.licences.list", "List licence grants for an asset with territories, usage scope, expiry, status, and reservations.", obj({"asset_id": string(), "status": string()}, ["asset_id"]), "read", licences_list, "licence grant register"),
    ToolSpec("dam.licence_requests.get", "Read one vendor licence request.", obj({"request_id": string()}, ["request_id"]), "read", licence_requests_get, "vendor licence request"),
    ToolSpec(
        "dam.licence_requests.create",
        "Place a licence request against an open vendor licence quote. The expected licence date is taken from the quote for the chosen issuance option.",
        obj(
            {
                "vendor_id": string(),
                "quote_id": string(),
                "asset_id": string(),
                "territory_count": integer(minimum=1),
                "issuance_option": {"type": "string", "enum": ["standard", "expedited"]},
            },
            ["vendor_id", "quote_id", "asset_id", "territory_count", "issuance_option"],
        ),
        "write",
        licence_requests_create,
        "vendor licence request",
        idempotent=False,
    ),
    ToolSpec("checklist.gates.list", "List release-checklist gates for a change request (QA, accessibility, legal, performance) with status, measured value, budget, and waiver authority.", obj({"change_request_id": string(), "category": string()}, ["change_request_id"]), "read", gates_list, "release checklist gate list"),
    ToolSpec("checklist.budgets.list", "List performance budgets for a page with the latest measured value and headroom.", obj({"page_id": string()}, ["page_id"]), "read", budgets_list, "performance budget list"),
    ToolSpec(
        "checklist.waivers.create",
        "Record a waiver for a checklist gate. Legal gates are never waived; other gates need a signed approval by the gate's authority that names the gate.",
        obj({"gate_id": string(), "change_request_id": string(), "reason": string(), "approval_id": string()}, ["gate_id", "change_request_id", "reason"]),
        "write",
        waivers_create,
        "checklist gate waiver",
        idempotent=False,
    ),
    ToolSpec("cdn.lanes.list", "List deploy lanes with status and instant-rollback capability.", obj({"pool": string()}), "read", lanes_list, "deploy lane roster"),
    ToolSpec("cdn.windows.list", "List deploy windows between two dates with free / busy / protected / blocked status.", obj({"start_date": string("ISO date"), "end_date": string("ISO date"), "lane_id": string(), "status": string()}, ["start_date", "end_date"]), "read", windows_list, "deploy window calendar"),
    ToolSpec("vendors.quotes.list", "List vendor quotes (licence, agency delivery, lane re-certification).", obj({"asset_id": string(), "vendor_id": string(), "kind": string()}), "read", quotes_list, "vendor quote"),
    ToolSpec("vendors.quotes.get", "Read one vendor quote: units available, standard and expedited issue dates, rush fee, validity.", obj({"quote_id": string()}, ["quote_id"]), "read", quotes_get, "vendor quote"),
    ToolSpec("approvals.list", "List approval records, optionally by keyword.", obj({"q": string()}), "read", approvals_list, "approval workflow record"),
    ToolSpec("approvals.get", "Read one approval record with its exact scope and approver.", obj({"approval_id": string()}, ["approval_id"]), "read", approvals_get, "approval workflow record"),
    ToolSpec("messages.list", "Search the web-studio mailbox by keyword (subject, body, labels).", obj({"q": string(), "max_results": integer(minimum=1)}, ["q"]), "read", messages_list, "mailbox search"),
    ToolSpec("messages.get", "Read one message with body and attachment list.", obj({"message_id": string()}, ["message_id"]), "read", messages_get, "mailbox message"),
    ToolSpec("chat.threads.list", "Search team chat threads by keyword.", obj({"q": string()}, ["q"]), "read", chat_threads_list, "team chat search"),
    ToolSpec("chat.threads.get", "Read one team chat thread.", obj({"thread_id": string()}, ["thread_id"]), "read", chat_threads_get, "team chat thread"),
    ToolSpec("drive.files.list", "Search shared-drive files by keyword (name, folder, content).", obj({"q": string()}, ["q"]), "read", drive_files_list, "shared drive search"),
    ToolSpec("drive.files.get", "Read shared-drive file metadata.", obj({"file_id": string()}, ["file_id"]), "read", drive_files_get, "shared drive file"),
    ToolSpec("drive.files.export", "Export a shared-drive file as text (spreadsheets as CSV, PDFs as extracted text).", obj({"file_id": string()}, ["file_id"]), "read", drive_files_export, "shared drive export"),
    ToolSpec(
        "notes.drafts.create",
        "Create, but do not send, a stakeholder draft note.",
        obj({"recipient": string(), "subject": string(), "body": string(), "related_change_request_id": string(), "related_page_id": string()}, ["recipient", "subject", "body"]),
        "write",
        drafts_create,
        "collaboration draft",
        idempotent=False,
    ),
)

SERVERS = {
    "cms": "Headless CMS: pages, entries with token / component / asset bindings, change requests, and scheduled releases.",
    "tokens": "Design-token and component registry: token versions with breaking flags, components with allowed variants and deprecations, consumer registry, and version pins.",
    "design": "Design-file index: files per page with current / superseded status and frame review states.",
    "dam": "Digital asset library: assets, licence grants with territories and expiry, and vendor licence requests.",
    "checklist": "Release checklist: QA, accessibility, legal, and performance gates with measured values, plus gate waivers.",
    "cdn": "CDN deploy scheduler: deploy lanes with rollback capability and the deploy-window calendar.",
    "vendors": "Vendor desk: foundry and stock-imagery licence quotes, agency delivery quotes, and edge-provider lane re-certification quotes.",
    "approvals": "Approval workflow records with exact scope.",
    "messages": "Web-studio mailbox for the release team.",
    "chat": "Web-release chat threads.",
    "drive": "Shared drive holding the playbook, registers, calendars, and exports.",
    "notes": "Stakeholder draft notes (never sent by the benchmark).",
}

__all__ = ["CONSUMER_UNIT", "SERVERS", "TERRITORY_UNIT", "TOOLS", "pinnable_consumers", "shippable_entries"]
