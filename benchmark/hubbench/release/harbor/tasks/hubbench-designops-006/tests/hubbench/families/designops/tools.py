"""DesignOps provider-shaped tools over the family's SQLite world.

Read tools return provider-shaped PLM, change-order, BOM, certification,
tooling-register, supplier-portal, and release-calendar records; write tools
persist to the domain tables, refresh the affected records, and record the
exact payload for the sealed contract.  There is no LLM anywhere here.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from ...engine.families import ToolSpec
from ...engine.validation import integer, obj, string
from ...engine.world import World

SET_UNIT = "SET"
CONFIGURATION_UNIT = "CONFIGURATION"
RELEASABLE_STATE = "CCB_APPROVED"


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #


def _part(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "part_id": row["part_id"],
        "number": row["number"],
        "name": row["name"],
        "part_type": row["part_type"],
        "owner_team": row["owner_team"],
        "current_revision": row["current_revision"],
        "primary_engineer": f"Engineer/{row['primary_engineer_id']}" if row.get("primary_engineer_id") else None,
    }


def _revision(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "revision_id": row["revision_id"],
        "part": f"Part/{row['part_id']}",
        "revision": row["revision"],
        "status": row["status"],
        "released_on": row.get("released_on"),
        "superseded_on": row.get("superseded_on"),
        "note": row.get("note") or "",
    }


def _document(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "document_id": row["document_id"],
        "part": f"Part/{row['part_id']}",
        "kind": row["kind"],
        "number": row["number"],
        "version": row["version"],
        "revision": row["revision"],
        "status": row["status"],
        "checked_in_at": row["checked_in_at"],
        "checked_in_by": f"Engineer/{row['checked_in_by']}",
        "note": row.get("note") or "",
    }


def _checkin(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "checkin_id": row["checkin_id"],
        "document": f"Document/{row['document_id']}",
        "version": row["version"],
        "checked_in_at": row["checked_in_at"],
        "check_kind": row["check_kind"],
        "status": row["status"],
        "summary": row["summary"],
    }


def _change(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "change_id": row["change_id"],
        "state": row["state"],
        "change_class": row["change_class"],
        "part": f"Part/{row['part_id']}",
        "from_revision": row["from_revision"],
        "to_revision": row["to_revision"],
        "title": row["title"],
        "reason": row["reason"],
        "effectivity_basis": row["effectivity_basis"],
        "effectivity_date": row.get("effectivity_date"),
        "fixture_family": row.get("fixture_family"),
        "fai_minutes": row["fai_minutes"],
        "changeover_minutes": row["changeover_minutes"],
        "required_by": row.get("required_by"),
        "requested_by": f"Engineer/{row['requested_by']}",
        "opened_at": row["opened_at"],
        "note": row.get("note") or "",
        "meta": {"versionId": str(row["revision"]), "lastUpdated": row["last_updated"]},
    }


def _affected(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_id": row["item_id"],
        "change": f"Change/{row['change_id']}",
        "assembly": f"Part/{row['assembly_part_id']}",
        "assembly_part_id": row["assembly_part_id"],
        "assembly_revision": row["assembly_revision"],
        "disposition": row["disposition"],
        "in_scope": bool(row["in_scope"]),
        "note": row.get("note") or "",
    }


def _bom_line(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "line_id": row["line_id"],
        "parent": f"Part/{row['parent_part_id']}",
        "parent_part_id": row["parent_part_id"],
        "parent_number": row.get("parent_number"),
        "parent_revision": row["parent_revision"],
        "parent_revision_status": row.get("parent_revision_status"),
        "component": f"Part/{row['component_part_id']}",
        "component_part_id": row["component_part_id"],
        "find_number": row["find_number"],
        "qty_per": row["qty_per"],
        "line_kind": row["line_kind"],
        "effectivity_end": row.get("effectivity_end"),
        "note": row.get("note") or "",
    }


def _certification(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "cert_id": row["cert_id"],
        "assembly": f"Part/{row['assembly_part_id']}",
        "assembly_part_id": row["assembly_part_id"],
        "assembly_revision": row["assembly_revision"],
        "program": row["program"],
        "status": row["status"],
        "issued_on": row["issued_on"],
        "expires_on": row["expires_on"],
        "covered_components": json.loads(row["covered_components_json"]),
        "recert_lead_days": row["recert_lead_days"],
        "recert_test_fee_usd": row["recert_test_fee_usd"],
        "note": row.get("note") or "",
    }


def _reservation(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["reservation_id"],
        "status": row["status"],
        "description": row.get("description"),
        "start": row.get("start_time"),
        "end": row.get("end_time"),
        "line": row.get("line_id"),
        "assembly": f"Part/{row['assembly_part_id']}",
        "change": f"Change/{row['change_id']}" if row.get("change_id") else None,
        "meta": {"versionId": str(row["revision"]), "lastUpdated": row["last_updated"]},
    }


def _window(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["window_id"],
        "line": row["line_id"],
        "serviceDate": row["service_date"],
        "session": row["session"],
        "start": f"{row['service_date']}T{row['start_time']}",
        "end": f"{row['service_date']}T{row['end_time']}",
        "status": row["status"],
        "holdReason": row.get("hold_reason"),
        "reservation": row.get("reservation_id"),
    }


# --------------------------------------------------------------------------- #
# PLM reads
# --------------------------------------------------------------------------- #


def parts_search(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("number"):
        rows = world.all("SELECT * FROM parts WHERE number = ? ORDER BY part_id", (args["number"],))
    elif args.get("name"):
        rows = world.all(
            "SELECT * FROM parts WHERE instr(lower(name), lower(?)) > 0 OR instr(lower(number), lower(?)) > 0 ORDER BY part_id",
            (args["name"], args["name"]),
        )
    else:
        raise ValueError("number or name is required")
    return {"total": len(rows), "parts": [_part(row) for row in rows]}


def parts_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _part(world.one("SELECT * FROM parts WHERE part_id = ?", (args["part_id"],), missing=f"Part/{args['part_id']} not found"))


def engineers_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM engineers WHERE engineer_id = ?", (args["engineer_id"],), missing="engineer not found")
    return {"engineer_id": row["engineer_id"], "name": row["name"], "role": row["role"], "focus": row["focus"]}


def revisions_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT part_id FROM parts WHERE part_id = ?", (args["part_id"],), missing=f"Part/{args['part_id']} not found")
    rows = world.all("SELECT * FROM part_revisions WHERE part_id = ? ORDER BY revision", (args["part_id"],))
    return {"total": len(rows), "revisions": [_revision(row) for row in rows]}


def documents_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT part_id FROM parts WHERE part_id = ?", (args["part_id"],), missing=f"Part/{args['part_id']} not found")
    if args.get("kind"):
        rows = world.all("SELECT * FROM cad_documents WHERE part_id = ? AND kind = ? ORDER BY document_id, version", (args["part_id"], args["kind"]))
    else:
        rows = world.all("SELECT * FROM cad_documents WHERE part_id = ? ORDER BY document_id, version", (args["part_id"],))
    return {"total": len(rows), "documents": [_document(row) for row in rows]}


def checkins_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    if args.get("document_id"):
        clauses.append("c.document_id = ?")
        params.append(args["document_id"])
    if args.get("part_id"):
        clauses.append("d.part_id = ?")
        params.append(args["part_id"])
    if args.get("status"):
        clauses.append("c.status = ?")
        params.append(args["status"])
    if args.get("start_date"):
        clauses.append("substr(c.checked_in_at, 1, 10) >= ?")
        params.append(args["start_date"])
    if args.get("end_date"):
        clauses.append("substr(c.checked_in_at, 1, 10) <= ?")
        params.append(args["end_date"])
    if not clauses:
        raise ValueError("at least one filter is required")
    rows = world.all(
        f"SELECT c.* FROM checkins c JOIN cad_documents d ON d.document_id = c.document_id WHERE {' AND '.join(clauses)} ORDER BY c.checked_in_at, c.checkin_id",
        params,
    )
    return {"total": len(rows), "checkins": [_checkin(row) for row in rows]}


# --------------------------------------------------------------------------- #
# Change orders
# --------------------------------------------------------------------------- #


def changes_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("part_id", "state", "fixture_family", "change_class"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    if not clauses:
        raise ValueError("at least one of part_id, state, fixture_family, change_class is required")
    rows = world.all(f"SELECT * FROM change_orders WHERE {' AND '.join(clauses)} ORDER BY change_id", params)
    return {"total": len(rows), "changes": [_change(row) for row in rows]}


def changes_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _change(world.one("SELECT * FROM change_orders WHERE change_id = ?", (args["change_id"],), missing=f"Change/{args['change_id']} not found"))


def affected_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT change_id FROM change_orders WHERE change_id = ?", (args["change_id"],), missing=f"Change/{args['change_id']} not found")
    rows = world.all("SELECT * FROM affected_items WHERE change_id = ? ORDER BY item_id", (args["change_id"],))
    return {"change_id": args["change_id"], "total": len(rows), "items": [_affected(row) for row in rows]}


def _free_windows_on(world: World, day: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = world.all(
        "SELECT w.*, l.status AS line_status FROM release_windows w JOIN lines l ON l.line_id = w.line_id WHERE w.service_date = ? ORDER BY w.line_id, w.session DESC",
        (day,),
    )
    if not rows:
        raise ValueError(f"{day} is not a production day on the release calendar")
    free = [row for row in rows if row["status"] == "free" and row["line_status"] == "ACTIVE"]
    return free, rows


def changes_update(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "eco.changes.update"
    current = world.one("SELECT * FROM change_orders WHERE change_id = ?", (args["change_id"],), missing=f"Change/{args['change_id']} not found")
    changes = {key: args[key] for key in ("state", "effectivity_date", "note") if key in args}
    if not changes:
        raise ValueError("no change requested")
    if current["state"] in {"RELEASED", "WITHDRAWN", "SUPERSEDED"} and ("state" in changes or "effectivity_date" in changes):
        raise ValueError(f"Change/{args['change_id']} is {current['state']} and cannot be changed")
    new_state = changes.get("state", current["state"])
    if "state" in changes:
        if new_state != "RELEASED":
            raise ValueError(f"unsupported state transition to {new_state}")
        if current["state"] != RELEASABLE_STATE:
            raise ValueError(f"Change/{args['change_id']} is {current['state']} and cannot be released; only a {RELEASABLE_STATE} change can be released")
        if not (changes.get("effectivity_date") or current.get("effectivity_date")):
            raise ValueError("releasing a change needs an effectivity_date")
    if "effectivity_date" in changes:
        day = changes["effectivity_date"]
        date.fromisoformat(day)
        free, rows = _free_windows_on(world, day)
        if not free:
            reasons = sorted({row.get("hold_reason") or row["status"] for row in rows})
            raise ValueError(f"no free cut-in window on {day}: {', '.join(reasons)}; freeze and blocked windows cannot be displaced")
    updated = {**current, **changes}
    updated["revision"] = int(current["revision"]) + 1
    updated["last_updated"] = world.clock()
    world.connection.execute(
        "UPDATE change_orders SET state = :state, effectivity_date = :effectivity_date, note = :note, revision = :revision, last_updated = :last_updated WHERE change_id = :change_id",
        updated,
    )
    world.audit(tool, "change_orders", current["change_id"], "update", changes)
    world.record_mutation(tool, "change_orders", current["change_id"], new_state, args, revision=updated["revision"])
    return _change(updated)


# --------------------------------------------------------------------------- #
# BOM
# --------------------------------------------------------------------------- #

_LINE_SELECT = (
    "SELECT b.*, p.number AS parent_number, "
    "(SELECT r.status FROM part_revisions r WHERE r.part_id = b.parent_part_id AND r.revision = b.parent_revision) AS parent_revision_status "
    "FROM bom_lines b JOIN parts p ON p.part_id = b.parent_part_id "
)


def bom_lines_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT part_id FROM parts WHERE part_id = ?", (args["parent_part_id"],), missing=f"Part/{args['parent_part_id']} not found")
    if args.get("parent_revision"):
        rows = world.all(_LINE_SELECT + "WHERE b.parent_part_id = ? AND b.parent_revision = ? ORDER BY b.find_number, b.line_id", (args["parent_part_id"], args["parent_revision"]))
    else:
        rows = world.all(_LINE_SELECT + "WHERE b.parent_part_id = ? ORDER BY b.parent_revision, b.find_number, b.line_id", (args["parent_part_id"],))
    return {"parent_part_id": args["parent_part_id"], "total": len(rows), "lines": [_bom_line(row) for row in rows]}


def whereused_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT part_id FROM parts WHERE part_id = ?", (args["component_part_id"],), missing=f"Part/{args['component_part_id']} not found")
    rows = world.all(_LINE_SELECT + "WHERE b.component_part_id = ? ORDER BY b.line_id", (args["component_part_id"],))
    return {
        "component_part_id": args["component_part_id"],
        "total": len(rows),
        "lines": [_bom_line(row) for row in rows],
        "note": "Gross where-used including obsolete and superseded parent revisions, alternates, and phantom lines; apply the change-control procedure to net the scope.",
    }


# --------------------------------------------------------------------------- #
# Certification register
# --------------------------------------------------------------------------- #


def certifications_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    if args.get("assembly_part_id"):
        clauses.append("assembly_part_id = ?")
        params.append(args["assembly_part_id"])
    if args.get("status"):
        clauses.append("status = ?")
        params.append(args["status"])
    if args.get("component_part_id"):
        clauses.append("instr(covered_components_json, ?) > 0")
        params.append(f'"{args["component_part_id"]}"')
    if not clauses:
        raise ValueError("at least one of assembly_part_id, component_part_id, status is required")
    rows = world.all(f"SELECT * FROM certifications WHERE {' AND '.join(clauses)} ORDER BY cert_id", params)
    return {"total": len(rows), "certifications": [_certification(row) for row in rows]}


def certifications_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _certification(world.one("SELECT * FROM certifications WHERE cert_id = ?", (args["cert_id"],), missing=f"certification {args['cert_id']} not found"))


# --------------------------------------------------------------------------- #
# Tooling register
# --------------------------------------------------------------------------- #


def families_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM fixture_families WHERE family_code = ?", (args["family_code"],), missing=f"fixture family {args['family_code']} not found"))


def inventory_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("family_code", "plant_id"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = world.all(
        f"SELECT family_code, plant_id, SUM(set_count) AS set_count, COUNT(*) AS lot_count FROM fixture_sets {where} GROUP BY family_code, plant_id ORDER BY family_code, plant_id",
        params,
    )
    return {"balances": rows, "note": "Gross registered sets including calibration-failed, reserved, and calibration-due lots; see tooling.sets.list for lot status."}


def sets_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = ["family_code = ?"], [args["family_code"]]
    for key in ("plant_id", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    rows = world.all(f"SELECT * FROM fixture_sets WHERE {' AND '.join(clauses)} ORDER BY calibration_due, set_id", params)
    return {"family_code": args["family_code"], "sets": rows}


def releasable_sets(world: World, family_code: str, plant_id: str) -> int:
    family = world.one("SELECT * FROM fixture_families WHERE family_code = ?", (family_code,), missing=f"fixture family {family_code} not found")
    horizon = (world.as_of + timedelta(days=int(family["minimum_remaining_calibration_days"]))).isoformat()
    row = world.one(
        "SELECT COALESCE(SUM(set_count), 0) AS quantity FROM fixture_sets WHERE family_code = ? AND plant_id = ? "
        "AND status = 'CALIBRATED' AND reserved_for_change IS NULL AND calibration_due > ?",
        (family_code, plant_id, horizon),
    )
    return int(row["quantity"])


def transfers_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM fixture_transfers WHERE transfer_id = ?", (args["transfer_id"],), missing=f"transfer {args['transfer_id']} not found"))


def transfers_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    for key in ("from_plant_id", "to_plant_id"):
        world.one("SELECT plant_id FROM plants WHERE plant_id = ?", (args[key],), missing=f"plant {args[key]} not found")
    if args["from_plant_id"] == args["to_plant_id"]:
        raise ValueError("a transfer needs two different plants")
    releasable = releasable_sets(world, args["family_code"], args["from_plant_id"])
    if args["set_count"] > releasable:
        raise ValueError(
            f"{args['from_plant_id']} holds only {releasable} releasable {SET_UNIT} of {args['family_code']}; reserved, calibration-failed, and calibration-due lots cannot move"
        )
    transfer_id = world.next_id("fixture_transfers", "transfer_id", "TRF-")
    row = {
        "transfer_id": transfer_id,
        "family_code": args["family_code"],
        "set_count": args["set_count"],
        "from_plant_id": args["from_plant_id"],
        "to_plant_id": args["to_plant_id"],
        "scheduled_date": args["scheduled_date"],
        "status": "SCHEDULED",
        "requested_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO fixture_transfers (transfer_id, family_code, set_count, from_plant_id, to_plant_id, scheduled_date, status, requested_by, created_at, revision) "
        "VALUES (:transfer_id, :family_code, :set_count, :from_plant_id, :to_plant_id, :scheduled_date, :status, :requested_by, :created_at, :revision)",
        row,
    )
    world.audit("tooling.transfers.create", "fixture_transfers", transfer_id, "insert", row)
    world.record_mutation("tooling.transfers.create", "fixture_transfers", transfer_id, "SCHEDULED", args)
    return dict(row)


# --------------------------------------------------------------------------- #
# Supplier portal
# --------------------------------------------------------------------------- #


def quotes_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("item_code", "supplier_id"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"quotes": world.all(f"SELECT * FROM supplier_quotes {where} ORDER BY quote_id", params)}


def quotes_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM supplier_quotes WHERE quote_id = ?", (args["quote_id"],), missing=f"quote {args['quote_id']} not found")
    supplier = world.one("SELECT * FROM suppliers WHERE supplier_id = ?", (row["supplier_id"],))
    return {**row, "supplier_name": supplier["name"], "supplier_kind": supplier["kind"]}


def orders_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("item_code", "status", "supplier_id"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"orders": world.all(f"SELECT * FROM supplier_orders {where} ORDER BY order_id", params)}


def orders_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM supplier_orders WHERE order_id = ?", (args["order_id"],), missing=f"order {args['order_id']} not found"))


def orders_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    supplier = world.one("SELECT * FROM suppliers WHERE supplier_id = ?", (args["supplier_id"],), missing=f"supplier {args['supplier_id']} not found")
    quote = world.one("SELECT * FROM supplier_quotes WHERE quote_id = ?", (args["quote_id"],), missing=f"quote {args['quote_id']} not found")
    if quote["supplier_id"] != supplier["supplier_id"] or quote["item_code"] != args["item_code"]:
        raise ValueError(f"quote {args['quote_id']} does not cover {args['item_code']} from {args['supplier_id']}")
    if quote["status"] != "OPEN":
        raise ValueError(f"quote {args['quote_id']} is {quote['status']}")
    unit = CONFIGURATION_UNIT if supplier["kind"] == "test_lab" else SET_UNIT
    if args["quantity"] > quote["quantity_available"]:
        raise ValueError(f"quote {args['quote_id']} covers at most {quote['quantity_available']} {unit}")
    expedited = args["service_option"] == "expedited"
    expected = quote["expedited_ready_date"] if expedited else quote["standard_ready_date"]
    total = round(args["quantity"] * float(quote["unit_price_usd"]) + (float(quote["expedite_fee_usd"]) if expedited else 0.0), 2)
    order_id = world.next_id("supplier_orders", "order_id", "SO-")
    row = {
        "order_id": order_id,
        "supplier_id": supplier["supplier_id"],
        "quote_id": quote["quote_id"],
        "item_code": args["item_code"],
        "quantity": args["quantity"],
        "unit": unit,
        "service_option": args["service_option"],
        "expected_ready_date": expected,
        "total_cost_usd": total,
        "status": "SUBMITTED",
        "requested_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO supplier_orders (order_id, supplier_id, quote_id, item_code, quantity, unit, service_option, expected_ready_date, total_cost_usd, status, requested_by, created_at, revision) "
        "VALUES (:order_id, :supplier_id, :quote_id, :item_code, :quantity, :unit, :service_option, :expected_ready_date, :total_cost_usd, :status, :requested_by, :created_at, :revision)",
        row,
    )
    world.audit("supplier.orders.create", "supplier_orders", order_id, "insert", row)
    world.record_mutation("supplier.orders.create", "supplier_orders", order_id, "SUBMITTED", args)
    return dict(row)


# --------------------------------------------------------------------------- #
# Release calendar
# --------------------------------------------------------------------------- #


def lines_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("plant_id"):
        rows = world.all("SELECT * FROM lines WHERE plant_id = ? ORDER BY line_id", (args["plant_id"],))
    else:
        rows = world.all("SELECT * FROM lines ORDER BY line_id")
    return {"lines": rows}


def windows_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses = ["service_date >= ?", "service_date <= ?"]
    params: list[Any] = [args["start_date"], args["end_date"]]
    if args.get("line_id"):
        clauses.append("line_id = ?")
        params.append(args["line_id"])
    if args.get("status"):
        clauses.append("status = ?")
        params.append(args["status"])
    rows = world.all(f"SELECT * FROM release_windows WHERE {' AND '.join(clauses)} ORDER BY service_date, line_id, session DESC", params)
    return {"windows": [_window(row) for row in rows]}


def reservations_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("change_id", "line_id", "status", "assembly_part_id"):
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
    rows = world.all(f"SELECT * FROM cutin_reservations WHERE {' AND '.join(clauses)} ORDER BY start_time, reservation_id", params)
    return {"total": len(rows), "reservations": [_reservation(row) for row in rows]}


def reservations_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _reservation(world.one("SELECT * FROM cutin_reservations WHERE reservation_id = ?", (args["reservation_id"],), missing=f"Reservation/{args['reservation_id']} not found"))


def _split_datetime(value: str, label: str) -> tuple[str, str]:
    if len(value) != 19 or value[10] != "T":
        raise ValueError(f"{label} must be YYYY-MM-DDTHH:MM:SS")
    date.fromisoformat(value[:10])
    return value[:10], value[11:]


def _windows_for_interval(world: World, line_id: str, start: str, end: str) -> list[dict[str, Any]]:
    start_date, start_time = _split_datetime(start, "start_time")
    end_date, end_time = _split_datetime(end, "end_time")
    if start_date != end_date:
        raise ValueError("a cut-in reservation must start and end on the same production day")
    if start_time >= end_time:
        raise ValueError("start_time must precede end_time")
    rows = world.all("SELECT * FROM release_windows WHERE line_id = ? AND service_date = ? ORDER BY start_time", (line_id, start_date))
    covering = [row for row in rows if row["start_time"] < end_time and row["end_time"] > start_time]
    if not covering:
        raise ValueError(f"no {line_id} window covers {start} - {end}")
    if start_time < min(row["start_time"] for row in covering) or end_time > max(row["end_time"] for row in covering):
        raise ValueError(f"{start} - {end} falls outside the {line_id} release windows")
    return covering


def _require_free(windows: list[dict[str, Any]], *, holder: str | None = None) -> None:
    for row in windows:
        if row["status"] == "free":
            continue
        if holder and row.get("reservation_id") == holder:
            continue
        raise ValueError(f"{row['window_id']} is {row['status']}: {row.get('hold_reason') or 'not available'}; protected freeze and blocked windows cannot be displaced")


def _claim(world: World, tool: str, windows: list[dict[str, Any]], reservation_id: str) -> None:
    for row in windows:
        world.connection.execute("UPDATE release_windows SET status = 'busy', hold_reason = 'reserved', reservation_id = ? WHERE window_id = ?", (reservation_id, row["window_id"]))
        world.audit(tool, "release_windows", row["window_id"], "update", {"status": "busy", "reservation_id": reservation_id})


def _release(world: World, tool: str, reservation_id: str) -> None:
    for row in world.all("SELECT window_id FROM release_windows WHERE reservation_id = ?", (reservation_id,)):
        world.connection.execute("UPDATE release_windows SET status = 'free', hold_reason = NULL, reservation_id = NULL WHERE window_id = ?", (row["window_id"],))
        world.audit(tool, "release_windows", row["window_id"], "update", {"status": "free", "reservation_id": None})


def _require_active_line(world: World, line_id: str) -> dict[str, Any]:
    line = world.one("SELECT * FROM lines WHERE line_id = ?", (line_id,), missing=f"line {line_id} not found")
    if line["status"] != "ACTIVE":
        raise ValueError(f"{line_id} is {line['status']}: {line.get('status_note') or ''}".strip())
    return line


def reservations_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "calendar.reservations.create"
    change = world.one("SELECT * FROM change_orders WHERE change_id = ?", (args["change_id"],), missing=f"Change/{args['change_id']} not found")
    if change["state"] not in {RELEASABLE_STATE, "RELEASED"}:
        raise ValueError(f"Change/{args['change_id']} is {change['state']} and cannot be scheduled for cut-in")
    world.one("SELECT part_id FROM parts WHERE part_id = ?", (args["assembly_part_id"],), missing=f"Part/{args['assembly_part_id']} not found")
    _require_active_line(world, args["line_id"])
    windows = _windows_for_interval(world, args["line_id"], args["start_time"], args["end_time"])
    _require_free(windows)
    reservation_id = world.next_id("cutin_reservations", "reservation_id", "RES-")
    row = {
        "reservation_id": reservation_id,
        "assembly_part_id": args["assembly_part_id"],
        "change_id": args["change_id"],
        "line_id": args["line_id"],
        "start_time": args["start_time"],
        "end_time": args["end_time"],
        "status": "booked",
        "description": args.get("description"),
        "revision": 1,
        "last_updated": world.clock(),
    }
    world.connection.execute(
        "INSERT INTO cutin_reservations (reservation_id, assembly_part_id, change_id, line_id, start_time, end_time, status, description, revision, last_updated) "
        "VALUES (:reservation_id, :assembly_part_id, :change_id, :line_id, :start_time, :end_time, :status, :description, :revision, :last_updated)",
        row,
    )
    world.audit(tool, "cutin_reservations", reservation_id, "insert", row)
    _claim(world, tool, windows, reservation_id)
    world.record_mutation(tool, "cutin_reservations", reservation_id, "booked", args)
    return _reservation(row)


def reservations_update(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "calendar.reservations.update"
    current = world.one("SELECT * FROM cutin_reservations WHERE reservation_id = ?", (args["reservation_id"],), missing=f"Reservation/{args['reservation_id']} not found")
    if current["status"] in {"cancelled", "fulfilled"}:
        raise ValueError(f"Reservation/{args['reservation_id']} is {current['status']} and cannot be changed")
    changes = {key: args[key] for key in ("line_id", "start_time", "end_time", "status", "description") if key in args}
    if not changes:
        raise ValueError("no change requested")
    updated = {**current, **changes}
    new_status = updated["status"]
    if new_status == "cancelled":
        _release(world, tool, current["reservation_id"])
    else:
        if any(key in changes for key in ("line_id", "start_time", "end_time")) or current["status"] != "booked":
            if not (updated.get("line_id") and updated.get("start_time") and updated.get("end_time")):
                raise ValueError("booking a reservation needs line_id, start_time, and end_time")
            _require_active_line(world, updated["line_id"])
            windows = _windows_for_interval(world, updated["line_id"], updated["start_time"], updated["end_time"])
            _require_free(windows, holder=current["reservation_id"])
            _release(world, tool, current["reservation_id"])
            _claim(world, tool, windows, current["reservation_id"])
            if new_status not in {"booked", "pending"}:
                raise ValueError(f"unsupported status transition to {new_status}")
    updated["revision"] = int(current["revision"]) + 1
    updated["last_updated"] = world.clock()
    world.connection.execute(
        "UPDATE cutin_reservations SET line_id = :line_id, start_time = :start_time, end_time = :end_time, status = :status, description = :description, revision = :revision, last_updated = :last_updated WHERE reservation_id = :reservation_id",
        updated,
    )
    world.audit(tool, "cutin_reservations", current["reservation_id"], "update", changes)
    world.record_mutation(tool, "cutin_reservations", current["reservation_id"], new_status, args, revision=updated["revision"])
    return _reservation(updated)


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
        "related_change_id": args.get("related_change_id"),
        "related_part_id": args.get("related_part_id"),
        "created_at": world.clock(),
        "status": "DRAFT",
    }
    world.connection.execute(
        "INSERT INTO note_drafts (draft_id, recipient, subject, body, related_change_id, related_part_id, created_at, status) "
        "VALUES (:draft_id, :recipient, :subject, :body, :related_change_id, :related_part_id, :created_at, :status)",
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
    ToolSpec("plm.parts.search", "Search parts by immutable part number or by name fragment.", obj({"number": string("part number"), "name": string("name fragment")}), "read", parts_search, "PLM part search"),
    ToolSpec("plm.parts.get", "Read one part master record by id.", obj({"part_id": string()}, ["part_id"]), "read", parts_get, "PLM part record"),
    ToolSpec("plm.engineers.get", "Read one engineer record.", obj({"engineer_id": string()}, ["engineer_id"]), "read", engineers_get, "PLM engineer record"),
    ToolSpec("plm.revisions.list", "List the lifecycle revisions of a part with RELEASED / SUPERSEDED / OBSOLETE / IN_WORK status.", obj({"part_id": string()}, ["part_id"]), "read", revisions_list, "PLM revision lifecycle"),
    ToolSpec("plm.documents.list", "List CAD models and drawings for a part with check-in version, revision, and release status.", obj({"part_id": string(), "kind": string("model | drawing")}, ["part_id"]), "read", documents_list, "PLM CAD document list"),
    ToolSpec("plm.checkins.list", "List CAD check-in history by document, part, status, or date window: version, check kind, result, and summary.", obj({"document_id": string(), "part_id": string(), "status": string(), "start_date": string("ISO date"), "end_date": string("ISO date")}), "read", checkins_list, "PLM check-in history"),
    ToolSpec("eco.changes.list", "List engineering change orders by part, state, fixture family, or change class.", obj({"part_id": string(), "state": string(), "fixture_family": string(), "change_class": string()}), "read", changes_list, "change order search"),
    ToolSpec("eco.changes.get", "Read one engineering change order: class, revisions, workflow state, effectivity, FAI and changeover durations.", obj({"change_id": string()}, ["change_id"]), "read", changes_get, "change order record"),
    ToolSpec("eco.affected.list", "List the affected items of a change order with disposition and scope flag.", obj({"change_id": string()}, ["change_id"]), "read", affected_list, "change order affected items"),
    ToolSpec(
        "eco.changes.update",
        "Release a CCB-approved change order with an effectivity (cut-in) date, or update its effectivity or note. The effectivity date must have a free cut-in window on an active line; freeze and blocked days are rejected. The record revision increments.",
        obj({"change_id": string(), "state": {"type": "string", "enum": ["RELEASED"]}, "effectivity_date": string("ISO date"), "note": string()}, ["change_id"]),
        "write",
        changes_update,
        "change order release",
        idempotent=False,
    ),
    ToolSpec("bom.lines.list", "List the bill-of-material lines of an assembly revision: component, find number, quantity per, and line kind (primary / alternate / phantom).", obj({"parent_part_id": string(), "parent_revision": string()}, ["parent_part_id"]), "read", bom_lines_list, "multi-level BOM lines"),
    ToolSpec("bom.whereused.list", "Gross where-used for a component: every parent assembly revision with revision status, quantity per, line kind, and effectivity end.", obj({"component_part_id": string()}, ["component_part_id"]), "read", whereused_list, "BOM where-used"),
    ToolSpec("cert.configurations.list", "List certified assembly configurations by assembly, covered component, or status, with covered component revisions and re-certification lead time and fee.", obj({"assembly_part_id": string(), "component_part_id": string(), "status": string()}), "read", certifications_list, "certification register"),
    ToolSpec("cert.configurations.get", "Read one certified configuration record.", obj({"cert_id": string()}, ["cert_id"]), "read", certifications_get, "certification register"),
    ToolSpec("tooling.families.get", "Read a fixture family: sets per station, calibration interval, minimum remaining calibration days, revision specificity.", obj({"family_code": string()}, ["family_code"]), "read", families_get, "tooling family record"),
    ToolSpec("tooling.inventory.list", "Gross registered fixture-set balances by family and plant (no netting of calibration, reservation, or revision state).", obj({"family_code": string(), "plant_id": string()}), "read", inventory_list, "tooling register balance"),
    ToolSpec("tooling.sets.list", "List registered fixture-set lots for a family with set count, calibration due date, status, and reservations.", obj({"family_code": string(), "plant_id": string(), "status": string()}, ["family_code"]), "read", sets_list, "tooling set register"),
    ToolSpec("tooling.transfers.get", "Read one inter-plant fixture transfer.", obj({"transfer_id": string()}, ["transfer_id"]), "read", transfers_get, "inter-plant fixture transfer"),
    ToolSpec(
        "tooling.transfers.create",
        "Schedule an inter-plant fixture-set transfer. Only releasable lots at the source (calibrated, unreserved, outside the calibration-due horizon) may move.",
        obj(
            {"family_code": string(), "set_count": integer(minimum=1), "from_plant_id": string(), "to_plant_id": string(), "scheduled_date": string("ISO date")},
            ["family_code", "set_count", "from_plant_id", "to_plant_id", "scheduled_date"],
        ),
        "write",
        transfers_create,
        "inter-plant fixture transfer",
        idempotent=False,
    ),
    ToolSpec("supplier.quotes.list", "List supplier-portal quotes (fixture builds and laboratory re-certification slots).", obj({"item_code": string(), "supplier_id": string()}), "read", quotes_list, "supplier portal quote"),
    ToolSpec("supplier.quotes.get", "Read one quote: quantity available, standard and expedited ready dates, expedite fee, unit price, validity.", obj({"quote_id": string()}, ["quote_id"]), "read", quotes_get, "supplier portal quote"),
    ToolSpec("supplier.orders.list", "List supplier-portal orders by item, status, or supplier.", obj({"item_code": string(), "status": string(), "supplier_id": string()}), "read", orders_list, "supplier portal order"),
    ToolSpec("supplier.orders.get", "Read one supplier-portal order.", obj({"order_id": string()}, ["order_id"]), "read", orders_get, "supplier portal order"),
    ToolSpec(
        "supplier.orders.create",
        "Place a supplier-portal order against an open quote (fixture sets or laboratory re-certification configurations). The expected ready date and total cost are taken from the quote for the chosen service option.",
        obj(
            {
                "supplier_id": string(),
                "quote_id": string(),
                "item_code": string(),
                "quantity": integer(minimum=1),
                "service_option": {"type": "string", "enum": ["standard", "expedited"]},
            },
            ["supplier_id", "quote_id", "item_code", "quantity", "service_option"],
        ),
        "write",
        orders_create,
        "supplier portal order",
        idempotent=False,
    ),
    ToolSpec("calendar.lines.list", "List production lines with station count, status, and first-article (CMM) capability.", obj({"plant_id": string()}), "read", lines_list, "release calendar line roster"),
    ToolSpec("calendar.windows.list", "List cut-in windows on the release calendar between two dates with free / busy / protected / blocked status.", obj({"start_date": string("ISO date"), "end_date": string("ISO date"), "line_id": string(), "status": string()}, ["start_date", "end_date"]), "read", windows_list, "release calendar windows"),
    ToolSpec("calendar.reservations.list", "List cut-in reservations by change, line, assembly, status, or date window.", obj({"change_id": string(), "line_id": string(), "assembly_part_id": string(), "status": string(), "start_date": string("ISO date"), "end_date": string("ISO date")}), "read", reservations_list, "cut-in reservation search"),
    ToolSpec("calendar.reservations.get", "Read one cut-in reservation.", obj({"reservation_id": string()}, ["reservation_id"]), "read", reservations_get, "cut-in reservation record"),
    ToolSpec(
        "calendar.reservations.create",
        "Book a cut-in reservation for a CCB-approved or released change on a line. Every window the interval touches must be free; protected freeze and blocked windows are never displaced.",
        obj(
            {"change_id": string(), "assembly_part_id": string(), "line_id": string(), "start_time": string(DATETIME), "end_time": string(DATETIME), "description": string()},
            ["change_id", "assembly_part_id", "line_id", "start_time", "end_time"],
        ),
        "write",
        reservations_create,
        "cut-in reservation create",
        idempotent=False,
    ),
    ToolSpec(
        "calendar.reservations.update",
        "Move, book, or cancel an existing cut-in reservation. Moving re-validates the target windows; the record revision increments.",
        obj(
            {"reservation_id": string(), "line_id": string(), "start_time": string(DATETIME), "end_time": string(DATETIME), "status": {"type": "string", "enum": ["booked", "pending", "cancelled"]}, "description": string()},
            ["reservation_id"],
        ),
        "write",
        reservations_update,
        "cut-in reservation update",
        idempotent=False,
    ),
    ToolSpec("approvals.list", "List approval records, optionally by keyword.", obj({"q": string()}), "read", approvals_list, "approval workflow record"),
    ToolSpec("approvals.get", "Read one approval record with its exact scope and approver.", obj({"approval_id": string()}, ["approval_id"]), "read", approvals_get, "approval workflow record"),
    ToolSpec("messages.list", "Search engineering-change mail by keyword (subject, body, labels).", obj({"q": string(), "max_results": integer(minimum=1)}, ["q"]), "read", messages_list, "mailbox search"),
    ToolSpec("messages.get", "Read one message with body and attachment list.", obj({"message_id": string()}, ["message_id"]), "read", messages_get, "mailbox message"),
    ToolSpec("chat.threads.list", "Search team chat threads by keyword.", obj({"q": string()}, ["q"]), "read", chat_threads_list, "team chat search"),
    ToolSpec("chat.threads.get", "Read one team chat thread.", obj({"thread_id": string()}, ["thread_id"]), "read", chat_threads_get, "team chat thread"),
    ToolSpec("drive.files.list", "Search shared-drive files by keyword (name, folder, content).", obj({"q": string()}, ["q"]), "read", drive_files_list, "shared drive search"),
    ToolSpec("drive.files.get", "Read shared-drive file metadata.", obj({"file_id": string()}, ["file_id"]), "read", drive_files_get, "shared drive file"),
    ToolSpec("drive.files.export", "Export a shared-drive file as text (spreadsheets as CSV, PDFs as extracted text).", obj({"file_id": string()}, ["file_id"]), "read", drive_files_export, "shared drive export"),
    ToolSpec(
        "notes.drafts.create",
        "Create, but do not send, a stakeholder draft note.",
        obj({"recipient": string(), "subject": string(), "body": string(), "related_change_id": string(), "related_part_id": string()}, ["recipient", "subject", "body"]),
        "write",
        drafts_create,
        "collaboration draft",
        idempotent=False,
    ),
)

SERVERS = {
    "plm": "Product lifecycle management: parts, revision lifecycle, CAD models and drawings, check-in history, engineers.",
    "eco": "Engineering change orders: workflow state, class, affected items, effectivity release.",
    "bom": "Multi-level bill of materials: assembly lines, alternates, phantoms, and where-used.",
    "cert": "Certification register: certified assembly configurations, covered component revisions, re-certification lead time and fee.",
    "tooling": "Tooling register: fixture families, lot register with calibration state, inter-plant transfers.",
    "supplier": "Supplier portal: fixture-build and laboratory re-certification quotes and orders.",
    "calendar": "Production release calendar: lines, cut-in windows with freeze and maintenance holds, cut-in reservations.",
    "approvals": "Approval workflow records with exact scope.",
    "messages": "Engineering change office mailbox.",
    "chat": "Engineering change office chat threads.",
    "drive": "Shared drive holding procedures, registers, calendars, and exports.",
    "notes": "Stakeholder draft notes (never sent by the benchmark).",
}

__all__ = ["SERVERS", "TOOLS", "releasable_sets"]
