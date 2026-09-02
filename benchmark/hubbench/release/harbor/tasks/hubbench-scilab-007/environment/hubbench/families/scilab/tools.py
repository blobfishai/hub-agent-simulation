"""SciLab provider-shaped tools over the family's SQLite world.

Read tools return LIMS, instrument-schedule, reagent-inventory, supplier-portal,
and ELN records; write tools persist to the domain tables, refresh the affected
records, and record the exact payload for the sealed contract.  There is no
LLM anywhere here.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from ...engine.families import ToolSpec
from ...engine.validation import integer, obj, string
from ...engine.world import World

VIAL_UNIT = "VIAL"


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #


def _assay(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "assay_id": row["assay_id"],
        "code": row["code"],
        "name": row["name"],
        "category": row["category"],
        "owner_lab": row["owner_lab"],
        "principal_scientist": f"Scientist/{row['principal_scientist_id']}" if row.get("principal_scientist_id") else None,
    }


def _batch(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "batch_id": row["batch_id"],
        "assay": f"Assay/{row['assay_id']}",
        "metric": row["metric"],
        "value": row["value"],
        "unit": row["unit"],
        "counted_at": row["counted_at"],
        "status": row["status"],
    }


def _protocol(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol_id": row["protocol_id"],
        "code": row["code"],
        "version": row["version"],
        "status": row["status"],
        "samples_per_plate": row["samples_per_plate"],
        "control_vials_per_plate": row["control_vials_per_plate"],
        "control_rule": row["control_rule"],
        "effective_from": row["effective_from"],
        "superseded_by": row.get("superseded_by"),
    }


def _request(row: dict[str, Any], reagent: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": row["request_id"],
        "status": row["status"],
        "kind": row["kind"],
        "priority": row["priority"],
        "assay": f"Assay/{row['assay_id']}",
        "protocol": {"protocol_id": row["protocol_id"], "code": protocol["code"], "version": protocol["version"], "status": protocol["status"]},
        "control_reagent": {"code": row["reagent_code"], "display": reagent["display"], "vial_format": reagent["vial_format"]},
        "unit_kind": row["unit_kind"],
        "unit_basis": row["unit_basis"],
        "samples": row["samples"],
        "units_in_scope": row["units_in_scope"],
        "scope_note": row["scope_note"],
        "run_minutes": row["run_minutes"],
        "read_minutes": row["read_minutes"],
        "opened_at": row["opened_at"],
        "requested_by": f"Scientist/{row['requested_by']}",
        "note": row.get("note") or "",
    }


def _booking(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["booking_id"],
        "status": row["status"],
        "description": row.get("description"),
        "start": row.get("start_time"),
        "end": row.get("end_time"),
        "instrument": row.get("instrument_id"),
        "assay": f"Assay/{row['assay_id']}",
        "request": f"RunRequest/{row['request_id']}" if row.get("request_id") else None,
        "meta": {"versionId": str(row["revision"]), "lastUpdated": row["last_updated"]},
    }


def _window(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["window_id"],
        "instrument": row["instrument_id"],
        "serviceDate": row["service_date"],
        "session": row["session"],
        "start": f"{row['service_date']}T{row['start_time']}",
        "end": f"{row['service_date']}T{row['end_time']}",
        "status": row["status"],
        "holdReason": row.get("hold_reason"),
        "booking": row.get("booking_id"),
    }


def _run(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "assay": f"Assay/{row['assay_id']}" if row.get("assay_id") else None,
        "protocol": f"Protocol/{row['protocol_id']}" if row.get("protocol_id") else None,
        "instrument": row["instrument_id"],
        "kind": row["kind"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "status": row["status"],
        "plates": row["plates"],
        "summary": row["summary"],
    }


def _result(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "result_id": row["result_id"],
        "run": f"AssayRun/{row['run_id']}",
        "control_level": row["control_level"],
        "lot": row.get("lot_id"),
        "value": row["value"],
        "unit": row["unit"],
        "acceptance_range": {"low": row["low_limit"], "high": row["high_limit"]},
        "valid": bool(row["valid"]),
        "note": row.get("note") or "",
    }


# --------------------------------------------------------------------------- #
# LIMS reads
# --------------------------------------------------------------------------- #


def assays_search(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("identifier"):
        rows = world.all("SELECT * FROM assays WHERE code = ? ORDER BY assay_id", (args["identifier"],))
    elif args.get("name"):
        rows = world.all("SELECT * FROM assays WHERE instr(lower(name), lower(?)) > 0 OR instr(lower(code), lower(?)) > 0 ORDER BY assay_id", (args["name"], args["name"]))
    else:
        raise ValueError("identifier or name is required")
    return {"total": len(rows), "assays": [_assay(row) for row in rows]}


def assays_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _assay(world.one("SELECT * FROM assays WHERE assay_id = ?", (args["assay_id"],), missing=f"Assay/{args['assay_id']} not found"))


def scientists_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM scientists WHERE scientist_id = ?", (args["scientist_id"],), missing="scientist not found")
    return {"scientist_id": row["scientist_id"], "name": row["name"], "role": row["role"], "focus": row["focus"]}


def batches_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT assay_id FROM assays WHERE assay_id = ?", (args["assay_id"],), missing=f"Assay/{args['assay_id']} not found")
    if args.get("metric"):
        rows = world.all("SELECT * FROM sample_batches WHERE assay_id = ? AND metric = ? ORDER BY counted_at DESC, batch_id", (args["assay_id"], args["metric"]))
    else:
        rows = world.all("SELECT * FROM sample_batches WHERE assay_id = ? ORDER BY counted_at DESC, batch_id", (args["assay_id"],))
    return {"total": len(rows), "batches": [_batch(row) for row in rows]}


def protocols_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("code", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    if not clauses:
        raise ValueError("code or status is required")
    rows = world.all(f"SELECT * FROM protocols WHERE {' AND '.join(clauses)} ORDER BY protocol_id", params)
    return {"total": len(rows), "protocols": [_protocol(row) for row in rows]}


def protocols_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _protocol(world.one("SELECT * FROM protocols WHERE protocol_id = ?", (args["protocol_id"],), missing=f"Protocol/{args['protocol_id']} not found"))


def _reagents_by_code(world: World) -> dict[str, dict[str, Any]]:
    return {row["reagent_code"]: row for row in world.all("SELECT * FROM reagents")}


def _protocols_by_id(world: World) -> dict[str, dict[str, Any]]:
    return {row["protocol_id"]: row for row in world.all("SELECT * FROM protocols")}


def requests_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("assay_id", "reagent_code", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    if not clauses:
        raise ValueError("at least one of assay_id, reagent_code, status is required")
    rows = world.all(f"SELECT * FROM run_requests WHERE {' AND '.join(clauses)} ORDER BY request_id", params)
    reagents = _reagents_by_code(world)
    protocols = _protocols_by_id(world)
    return {"total": len(rows), "requests": [_request(row, reagents[row["reagent_code"]], protocols[row["protocol_id"]]) for row in rows]}


def requests_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM run_requests WHERE request_id = ?", (args["request_id"],), missing=f"RunRequest/{args['request_id']} not found")
    return _request(row, _reagents_by_code(world)[row["reagent_code"]], _protocols_by_id(world)[row["protocol_id"]])


def runs_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("assay_id", "instrument_id", "status", "kind"):
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
    rows = world.all(f"SELECT * FROM assay_runs WHERE {' AND '.join(clauses)} ORDER BY started_at, run_id", params)
    return {"total": len(rows), "runs": [_run(row) for row in rows]}


def runs_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _run(world.one("SELECT * FROM assay_runs WHERE run_id = ?", (args["run_id"],), missing=f"AssayRun/{args['run_id']} not found"))


def results_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT run_id FROM assay_runs WHERE run_id = ?", (args["run_id"],), missing=f"AssayRun/{args['run_id']} not found")
    rows = world.all("SELECT * FROM qc_results WHERE run_id = ? ORDER BY result_id", (args["run_id"],))
    return {"run_id": args["run_id"], "total": len(rows), "results": [_result(row) for row in rows]}


# --------------------------------------------------------------------------- #
# Reagent inventory
# --------------------------------------------------------------------------- #


def reagents_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM reagents WHERE reagent_code = ?", (args["reagent_code"],), missing=f"reagent {args['reagent_code']} not found"))


def balances_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("reagent_code", "site_id"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = world.all(
        f"SELECT reagent_code, site_id, SUM(vials_on_hand) AS vials_on_hand, COUNT(*) AS lot_count FROM reagent_lots {where} "
        "GROUP BY reagent_code, site_id ORDER BY reagent_code, site_id",
        params,
    )
    return {"balances": rows, "note": "Gross on-hand vials including quarantined, reserved, expired, and short-dated lots; see inventory.lots.list for lot status."}


def lots_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = ["reagent_code = ?"], [args["reagent_code"]]
    for key in ("site_id", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    rows = world.all(f"SELECT * FROM reagent_lots WHERE {' AND '.join(clauses)} ORDER BY expiry_date, lot_id", params)
    return {"reagent_code": args["reagent_code"], "lots": rows}


def transfers_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM lot_transfers WHERE transfer_id = ?", (args["transfer_id"],), missing=f"transfer {args['transfer_id']} not found"))


def usable_vials(world: World, reagent_code: str, site_id: str) -> int:
    reagent = world.one("SELECT * FROM reagents WHERE reagent_code = ?", (reagent_code,), missing=f"reagent {reagent_code} not found")
    horizon = (world.as_of + timedelta(days=int(reagent["minimum_dating_days"]))).isoformat()
    row = world.one(
        "SELECT COALESCE(SUM(vials_on_hand), 0) AS quantity FROM reagent_lots WHERE reagent_code = ? AND site_id = ? "
        "AND status = 'AVAILABLE' AND reserved_for_request IS NULL AND expiry_date > ?",
        (reagent_code, site_id, horizon),
    )
    return int(row["quantity"])


def transfers_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    for key in ("from_site_id", "to_site_id"):
        world.one("SELECT site_id FROM sites WHERE site_id = ?", (args[key],), missing=f"site {args[key]} not found")
    if args["from_site_id"] == args["to_site_id"]:
        raise ValueError("a transfer needs two different sites")
    usable = usable_vials(world, args["reagent_code"], args["from_site_id"])
    if args["quantity"] > usable:
        raise ValueError(f"{args['from_site_id']} holds only {usable} usable {VIAL_UNIT} of {args['reagent_code']}; reserved, quarantined, expired, and short-dated lots cannot move")
    transfer_id = world.next_id("lot_transfers", "transfer_id", "TR-")
    row = {
        "transfer_id": transfer_id,
        "reagent_code": args["reagent_code"],
        "quantity": args["quantity"],
        "from_site_id": args["from_site_id"],
        "to_site_id": args["to_site_id"],
        "scheduled_date": args["scheduled_date"],
        "status": "SCHEDULED",
        "requested_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO lot_transfers (transfer_id, reagent_code, quantity, from_site_id, to_site_id, scheduled_date, status, requested_by, created_at, revision) "
        "VALUES (:transfer_id, :reagent_code, :quantity, :from_site_id, :to_site_id, :scheduled_date, :status, :requested_by, :created_at, :revision)",
        row,
    )
    world.audit("inventory.transfers.create", "lot_transfers", transfer_id, "insert", row)
    world.record_mutation("inventory.transfers.create", "lot_transfers", transfer_id, "SCHEDULED", args)
    return dict(row)


# --------------------------------------------------------------------------- #
# Supplier portal
# --------------------------------------------------------------------------- #


def confirmations_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("reagent_code", "supplier_id"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"confirmations": world.all(f"SELECT * FROM shipment_confirmations {where} ORDER BY confirmation_id", params)}


def confirmations_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM shipment_confirmations WHERE confirmation_id = ?", (args["confirmation_id"],), missing=f"confirmation {args['confirmation_id']} not found")
    supplier = world.one("SELECT * FROM suppliers WHERE supplier_id = ?", (row["supplier_id"],))
    return {**row, "supplier_name": supplier["name"]}


def orders_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("status", "reagent_code"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"orders": world.all(f"SELECT * FROM reagent_orders {where} ORDER BY order_id", params)}


def orders_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM reagent_orders WHERE order_id = ?", (args["order_id"],), missing=f"order {args['order_id']} not found"))


def orders_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    supplier = world.one("SELECT * FROM suppliers WHERE supplier_id = ?", (args["supplier_id"],), missing=f"supplier {args['supplier_id']} not found")
    world.one("SELECT reagent_code FROM reagents WHERE reagent_code = ?", (args["reagent_code"],), missing=f"reagent {args['reagent_code']} not found")
    confirmation = world.one(
        "SELECT * FROM shipment_confirmations WHERE confirmation_id = ?",
        (args["confirmation_id"],),
        missing=f"shipment confirmation {args['confirmation_id']} not found",
    )
    if confirmation["supplier_id"] != supplier["supplier_id"] or confirmation["reagent_code"] != args["reagent_code"]:
        raise ValueError(f"confirmation {args['confirmation_id']} does not cover {args['reagent_code']} from {args['supplier_id']}")
    if confirmation["status"] != "OPEN":
        raise ValueError(f"confirmation {args['confirmation_id']} is {confirmation['status']}")
    if args["quantity"] > confirmation["vials_available"]:
        raise ValueError(f"confirmation {args['confirmation_id']} covers at most {confirmation['vials_available']} {VIAL_UNIT}")
    expected = confirmation["standard_delivery_date"] if args["delivery_option"] == "standard" else confirmation["expedited_delivery_date"]
    order_id = world.next_id("reagent_orders", "order_id", "ORD-")
    row = {
        "order_id": order_id,
        "supplier_id": supplier["supplier_id"],
        "confirmation_id": confirmation["confirmation_id"],
        "reagent_code": args["reagent_code"],
        "quantity": args["quantity"],
        "unit": VIAL_UNIT,
        "delivery_option": args["delivery_option"],
        "expected_delivery_date": expected,
        "status": "SUBMITTED",
        "requested_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO reagent_orders (order_id, supplier_id, confirmation_id, reagent_code, quantity, unit, delivery_option, expected_delivery_date, status, requested_by, created_at, revision) "
        "VALUES (:order_id, :supplier_id, :confirmation_id, :reagent_code, :quantity, :unit, :delivery_option, :expected_delivery_date, :status, :requested_by, :created_at, :revision)",
        row,
    )
    world.audit("supplier.orders.create", "reagent_orders", order_id, "insert", row)
    world.record_mutation("supplier.orders.create", "reagent_orders", order_id, "SUBMITTED", args)
    return dict(row)


# --------------------------------------------------------------------------- #
# Instrument schedule
# --------------------------------------------------------------------------- #


def instruments_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("site_id"):
        rows = world.all("SELECT * FROM instruments WHERE site_id = ? ORDER BY instrument_id", (args["site_id"],))
    else:
        rows = world.all("SELECT * FROM instruments ORDER BY instrument_id")
    return {"instruments": rows}


def instruments_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM instruments WHERE instrument_id = ?", (args["instrument_id"],), missing=f"instrument {args['instrument_id']} not found"))


def certificates_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("instrument_id", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    if not clauses:
        raise ValueError("instrument_id or status is required")
    rows = world.all(f"SELECT * FROM calibration_certificates WHERE {' AND '.join(clauses)} ORDER BY expires_on DESC, cert_id", params)
    return {"total": len(rows), "certificates": rows}


def windows_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses = ["service_date >= ?", "service_date <= ?"]
    params: list[Any] = [args["start_date"], args["end_date"]]
    if args.get("instrument_id"):
        clauses.append("instrument_id = ?")
        params.append(args["instrument_id"])
    if args.get("status"):
        clauses.append("status = ?")
        params.append(args["status"])
    rows = world.all(f"SELECT * FROM instrument_windows WHERE {' AND '.join(clauses)} ORDER BY service_date, instrument_id, session DESC", params)
    return {"windows": [_window(row) for row in rows]}


def bookings_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("request_id", "instrument_id", "status", "assay_id"):
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
    rows = world.all(f"SELECT * FROM bookings WHERE {' AND '.join(clauses)} ORDER BY start_time, booking_id", params)
    return {"total": len(rows), "bookings": [_booking(row) for row in rows]}


def bookings_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _booking(world.one("SELECT * FROM bookings WHERE booking_id = ?", (args["booking_id"],), missing=f"Booking/{args['booking_id']} not found"))


def _split_datetime(value: str, label: str) -> tuple[str, str]:
    if len(value) != 19 or value[10] != "T":
        raise ValueError(f"{label} must be YYYY-MM-DDTHH:MM:SS")
    date.fromisoformat(value[:10])
    return value[:10], value[11:]


def _windows_for_interval(world: World, instrument_id: str, start: str, end: str) -> list[dict[str, Any]]:
    start_date, start_time = _split_datetime(start, "start_time")
    end_date, end_time = _split_datetime(end, "end_time")
    if start_date != end_date:
        raise ValueError("an analyser booking must start and end on the same service date")
    if start_time >= end_time:
        raise ValueError("start_time must precede end_time")
    rows = world.all("SELECT * FROM instrument_windows WHERE instrument_id = ? AND service_date = ? ORDER BY start_time", (instrument_id, start_date))
    covering = [row for row in rows if row["start_time"] < end_time and row["end_time"] > start_time]
    if not covering:
        raise ValueError(f"no {instrument_id} window covers {start} - {end}")
    if start_time < min(row["start_time"] for row in covering) or end_time > max(row["end_time"] for row in covering):
        raise ValueError(f"{start} - {end} falls outside the {instrument_id} analyser windows")
    return covering


def _require_free(windows: list[dict[str, Any]], *, holder: str | None = None) -> None:
    for row in windows:
        if row["status"] == "free":
            continue
        if holder and row.get("booking_id") == holder:
            continue
        raise ValueError(f"{row['window_id']} is {row['status']}: {row.get('hold_reason') or 'not available'}; protected and blocked windows cannot be displaced")


def _require_instrument(world: World, instrument_id: str, run_date: str) -> dict[str, Any]:
    instrument = world.one("SELECT * FROM instruments WHERE instrument_id = ?", (instrument_id,), missing=f"instrument {instrument_id} not found")
    if instrument["status"] != "ACTIVE":
        raise ValueError(f"{instrument_id} is {instrument['status']}: {instrument.get('status_note') or ''}".strip())
    valid = world.all(
        "SELECT cert_id FROM calibration_certificates WHERE instrument_id = ? AND status = 'VALID' AND issued_on <= ? AND expires_on >= ?",
        (instrument_id, run_date, run_date),
    )
    if not valid:
        raise ValueError(f"{instrument_id} has no valid calibration certificate covering {run_date}; a run may only be booked on a calibrated analyser")
    return instrument


def _claim(world: World, tool: str, windows: list[dict[str, Any]], booking_id: str) -> None:
    for row in windows:
        world.connection.execute("UPDATE instrument_windows SET status = 'busy', hold_reason = 'booked', booking_id = ? WHERE window_id = ?", (booking_id, row["window_id"]))
        world.audit(tool, "instrument_windows", row["window_id"], "update", {"status": "busy", "booking_id": booking_id})


def _release(world: World, tool: str, booking_id: str) -> None:
    for row in world.all("SELECT window_id FROM instrument_windows WHERE booking_id = ?", (booking_id,)):
        world.connection.execute("UPDATE instrument_windows SET status = 'free', hold_reason = NULL, booking_id = NULL WHERE window_id = ?", (row["window_id"],))
        world.audit(tool, "instrument_windows", row["window_id"], "update", {"status": "free", "booking_id": None})


def bookings_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "instruments.bookings.create"
    request = world.one("SELECT * FROM run_requests WHERE request_id = ?", (args["request_id"],), missing=f"RunRequest/{args['request_id']} not found")
    if request["status"] not in {"open", "active"}:
        raise ValueError(f"RunRequest/{args['request_id']} is {request['status']} and cannot be booked")
    run_date = _split_datetime(args["start_time"], "start_time")[0]
    _require_instrument(world, args["instrument_id"], run_date)
    windows = _windows_for_interval(world, args["instrument_id"], args["start_time"], args["end_time"])
    _require_free(windows)
    booking_id = world.next_id("bookings", "booking_id", "BK-")
    row = {
        "booking_id": booking_id,
        "assay_id": request["assay_id"],
        "request_id": args["request_id"],
        "instrument_id": args["instrument_id"],
        "start_time": args["start_time"],
        "end_time": args["end_time"],
        "status": "booked",
        "description": args.get("description"),
        "revision": 1,
        "last_updated": world.clock(),
    }
    world.connection.execute(
        "INSERT INTO bookings (booking_id, assay_id, request_id, instrument_id, start_time, end_time, status, description, revision, last_updated) "
        "VALUES (:booking_id, :assay_id, :request_id, :instrument_id, :start_time, :end_time, :status, :description, :revision, :last_updated)",
        row,
    )
    world.audit(tool, "bookings", booking_id, "insert", row)
    _claim(world, tool, windows, booking_id)
    world.record_mutation(tool, "bookings", booking_id, "booked", args)
    return _booking(row)


def bookings_update(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "instruments.bookings.update"
    current = world.one("SELECT * FROM bookings WHERE booking_id = ?", (args["booking_id"],), missing=f"Booking/{args['booking_id']} not found")
    if current["status"] in {"cancelled", "completed"}:
        raise ValueError(f"Booking/{args['booking_id']} is {current['status']} and cannot be changed")
    changes = {key: args[key] for key in ("instrument_id", "start_time", "end_time", "status", "description") if key in args}
    if not changes:
        raise ValueError("no change requested")
    updated = {**current, **changes}
    new_status = updated["status"]
    if new_status == "cancelled":
        _release(world, tool, current["booking_id"])
    else:
        if any(key in changes for key in ("instrument_id", "start_time", "end_time")) or current["status"] != "booked":
            if not (updated.get("instrument_id") and updated.get("start_time") and updated.get("end_time")):
                raise ValueError("booking a run needs instrument_id, start_time, and end_time")
            run_date = _split_datetime(updated["start_time"], "start_time")[0]
            _require_instrument(world, updated["instrument_id"], run_date)
            windows = _windows_for_interval(world, updated["instrument_id"], updated["start_time"], updated["end_time"])
            _require_free(windows, holder=current["booking_id"])
            _release(world, tool, current["booking_id"])
            _claim(world, tool, windows, current["booking_id"])
            if new_status not in {"booked", "pending"}:
                raise ValueError(f"unsupported status transition to {new_status}")
    updated["revision"] = int(current["revision"]) + 1
    updated["last_updated"] = world.clock()
    world.connection.execute(
        "UPDATE bookings SET instrument_id = :instrument_id, start_time = :start_time, end_time = :end_time, status = :status, description = :description, revision = :revision, last_updated = :last_updated WHERE booking_id = :booking_id",
        updated,
    )
    world.audit(tool, "bookings", current["booking_id"], "update", changes)
    world.record_mutation(tool, "bookings", current["booking_id"], new_status, args, revision=updated["revision"])
    return _booking(updated)


# --------------------------------------------------------------------------- #
# ELN, approvals, collaboration surfaces
# --------------------------------------------------------------------------- #


def notes_search(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    if args.get("protocol_code"):
        clauses.append("protocol_code = ?")
        params.append(args["protocol_code"])
    if args.get("q"):
        query = args["q"].strip().strip('"')
        clauses.append("(instr(title, ?) > 0 OR instr(content, ?) > 0 OR instr(protocol_code, ?) > 0)")
        params.extend([query, query, query])
    if not clauses:
        raise ValueError("protocol_code or q is required")
    rows = world.all(f"SELECT note_id, protocol_code, version, title, status, updated_at FROM method_notes WHERE {' AND '.join(clauses)} ORDER BY note_id", params)
    return {"total": len(rows), "notes": rows}


def notes_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM method_notes WHERE note_id = ?", (args["note_id"],), missing=f"method note {args['note_id']} not found"))


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
        "related_request_id": args.get("related_request_id"),
        "related_assay_id": args.get("related_assay_id"),
        "created_at": world.clock(),
        "status": "DRAFT",
    }
    world.connection.execute(
        "INSERT INTO note_drafts (draft_id, recipient, subject, body, related_request_id, related_assay_id, created_at, status) "
        "VALUES (:draft_id, :recipient, :subject, :body, :related_request_id, :related_assay_id, :created_at, :status)",
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
    ToolSpec("lims.assays.search", "Search registered assays by immutable assay code or by name.", obj({"identifier": string("assay code"), "name": string("name fragment")}), "read", assays_search, "LIMS assay search"),
    ToolSpec("lims.assays.get", "Read one assay record by id.", obj({"assay_id": string()}, ["assay_id"]), "read", assays_get, "LIMS assay record"),
    ToolSpec("lims.scientists.get", "Read one scientist record.", obj({"scientist_id": string()}, ["scientist_id"]), "read", scientists_get, "LIMS scientist record"),
    ToolSpec("lims.batches.list", "List final sample-batch counts for an assay, optionally by metric (SAMPLES-IN-BATCH, SAMPLES-PER-TIMEPOINT, SAMPLES-IN-STUDY), newest first.", obj({"assay_id": string(), "metric": string("metric code")}, ["assay_id"]), "read", batches_list, "LIMS sample batch count"),
    ToolSpec("lims.protocols.list", "List protocol versions by protocol code or status (current / superseded).", obj({"code": string("protocol code"), "status": string()}), "read", protocols_list, "LIMS protocol version list"),
    ToolSpec("lims.protocols.get", "Read one protocol version: samples per plate, control vials per plate, control rule, and supersession.", obj({"protocol_id": string()}, ["protocol_id"]), "read", protocols_get, "LIMS protocol version"),
    ToolSpec("lims.requests.list", "List run requests by assay, control reagent, or status.", obj({"assay_id": string(), "reagent_code": string(), "status": string()}), "read", requests_list, "LIMS run request search"),
    ToolSpec("lims.requests.get", "Read one run request with sample basis, scope, protocol version, and run durations.", obj({"request_id": string()}, ["request_id"]), "read", requests_get, "LIMS run request record"),
    ToolSpec("lims.runs.list", "List assay runs by assay, instrument, status, kind, or start-date window.", obj({"assay_id": string(), "instrument_id": string(), "status": string(), "kind": string(), "start_date": string("ISO date"), "end_date": string("ISO date")}), "read", runs_list, "LIMS run history"),
    ToolSpec("lims.runs.get", "Read one assay run with status, plates, and summary.", obj({"run_id": string()}, ["run_id"]), "read", runs_get, "LIMS run record"),
    ToolSpec("lims.results.list", "List QC control results for a run with acceptance range and validity flag.", obj({"run_id": string()}, ["run_id"]), "read", results_list, "LIMS QC result list"),
    ToolSpec("inventory.reagents.get", "Read a reagent record: vial format, storage, minimum remaining dating, validation status.", obj({"reagent_code": string()}, ["reagent_code"]), "read", reagents_get, "reagent catalog record"),
    ToolSpec("inventory.balances.list", "Gross on-hand vial balances by reagent and site (no netting of quarantine, reservation, or dating state).", obj({"reagent_code": string(), "site_id": string()}), "read", balances_list, "reagent inventory balance"),
    ToolSpec("inventory.lots.list", "List reagent lots for a reagent with vials on hand, expiry, status, and reservations.", obj({"reagent_code": string(), "site_id": string(), "status": string()}, ["reagent_code"]), "read", lots_list, "reagent lot register"),
    ToolSpec("inventory.transfers.get", "Read one inter-site lot transfer.", obj({"transfer_id": string()}, ["transfer_id"]), "read", transfers_get, "inter-site lot transfer"),
    ToolSpec(
        "inventory.transfers.create",
        "Schedule an inter-site lot transfer on the cold-chain courier run. Only usable lots at the source (available, unreserved, outside the dating horizon) may move.",
        obj(
            {"reagent_code": string(), "quantity": integer(minimum=1), "from_site_id": string(), "to_site_id": string(), "scheduled_date": string("ISO date")},
            ["reagent_code", "quantity", "from_site_id", "to_site_id", "scheduled_date"],
        ),
        "write",
        transfers_create,
        "inter-site lot transfer",
        idempotent=False,
    ),
    ToolSpec("supplier.confirmations.list", "List supplier shipment confirmations.", obj({"reagent_code": string(), "supplier_id": string()}), "read", confirmations_list, "supplier shipment confirmation"),
    ToolSpec("supplier.confirmations.get", "Read one shipment confirmation: vials, standard and expedited delivery dates, expedite fee, validity, cold-chain terms.", obj({"confirmation_id": string()}, ["confirmation_id"]), "read", confirmations_get, "supplier shipment confirmation"),
    ToolSpec("supplier.orders.list", "List reagent orders placed with suppliers.", obj({"status": string(), "reagent_code": string()}), "read", orders_list, "supplier reagent order"),
    ToolSpec("supplier.orders.get", "Read one reagent order.", obj({"order_id": string()}, ["order_id"]), "read", orders_get, "supplier reagent order"),
    ToolSpec(
        "supplier.orders.create",
        "Place a reagent order against an open shipment confirmation. The expected delivery date is taken from the confirmation for the chosen delivery option.",
        obj(
            {
                "supplier_id": string(),
                "confirmation_id": string(),
                "reagent_code": string(),
                "quantity": integer(minimum=1),
                "delivery_option": {"type": "string", "enum": ["standard", "expedited"]},
            },
            ["supplier_id", "confirmation_id", "reagent_code", "quantity", "delivery_option"],
        ),
        "write",
        orders_create,
        "supplier reagent order",
        idempotent=False,
    ),
    ToolSpec("instruments.instruments.list", "List analysers with status and operational-qualification capability, optionally by site.", obj({"site_id": string()}), "read", instruments_list, "instrument roster"),
    ToolSpec("instruments.instruments.get", "Read one analyser record.", obj({"instrument_id": string()}, ["instrument_id"]), "read", instruments_get, "instrument record"),
    ToolSpec("instruments.certificates.list", "List calibration certificates for an analyser or by status, newest expiry first.", obj({"instrument_id": string(), "status": string()}), "read", certificates_list, "calibration certificate register"),
    ToolSpec("instruments.windows.list", "List analyser booking windows between two dates with free / busy / protected / blocked status.", obj({"start_date": string("ISO date"), "end_date": string("ISO date"), "instrument_id": string(), "status": string()}, ["start_date", "end_date"]), "read", windows_list, "instrument window calendar"),
    ToolSpec("instruments.bookings.list", "List analyser bookings by run request, instrument, assay, status, or date window.", obj({"request_id": string(), "instrument_id": string(), "assay_id": string(), "status": string(), "start_date": string("ISO date"), "end_date": string("ISO date")}), "read", bookings_list, "instrument booking search"),
    ToolSpec("instruments.bookings.get", "Read one analyser booking.", obj({"booking_id": string()}, ["booking_id"]), "read", bookings_get, "instrument booking record"),
    ToolSpec(
        "instruments.bookings.create",
        "Book an analyser run for a run request. Every window the interval touches must be free, and the analyser must hold a valid calibration certificate on the run date; protected and blocked windows are never displaced.",
        obj(
            {"request_id": string(), "instrument_id": string(), "start_time": string(DATETIME), "end_time": string(DATETIME), "description": string()},
            ["request_id", "instrument_id", "start_time", "end_time"],
        ),
        "write",
        bookings_create,
        "instrument booking create",
        idempotent=False,
    ),
    ToolSpec(
        "instruments.bookings.update",
        "Move, book, or cancel an existing analyser booking. Moving re-validates the target windows and the calibration certificate; the record revision increments.",
        obj(
            {"booking_id": string(), "instrument_id": string(), "start_time": string(DATETIME), "end_time": string(DATETIME), "status": {"type": "string", "enum": ["booked", "pending", "cancelled"]}, "description": string()},
            ["booking_id"],
        ),
        "write",
        bookings_update,
        "instrument booking update",
        idempotent=False,
    ),
    ToolSpec("eln.notes.search", "Search ELN method notes by protocol code or keyword; returns current and superseded notes.", obj({"protocol_code": string(), "q": string()}), "read", notes_search, "ELN method note search"),
    ToolSpec("eln.notes.get", "Read one ELN method note with its protocol version reference and supersession status.", obj({"note_id": string()}, ["note_id"]), "read", notes_get, "ELN method note"),
    ToolSpec("approvals.list", "List approval records, optionally by keyword.", obj({"q": string()}), "read", approvals_list, "approval workflow record"),
    ToolSpec("approvals.get", "Read one approval record with its exact scope and approver.", obj({"approval_id": string()}, ["approval_id"]), "read", approvals_get, "approval workflow record"),
    ToolSpec("messages.list", "Search the assay-operations mailbox by keyword (subject, body, labels).", obj({"q": string(), "max_results": integer(minimum=1)}, ["q"]), "read", messages_list, "mailbox search"),
    ToolSpec("messages.get", "Read one message with body and attachment list.", obj({"message_id": string()}, ["message_id"]), "read", messages_get, "mailbox message"),
    ToolSpec("chat.threads.list", "Search team chat threads by keyword.", obj({"q": string()}, ["q"]), "read", chat_threads_list, "team chat search"),
    ToolSpec("chat.threads.get", "Read one team chat thread.", obj({"thread_id": string()}, ["thread_id"]), "read", chat_threads_get, "team chat thread"),
    ToolSpec("drive.files.list", "Search shared-drive files by keyword (name, folder, content).", obj({"q": string()}, ["q"]), "read", drive_files_list, "shared drive search"),
    ToolSpec("drive.files.get", "Read shared-drive file metadata.", obj({"file_id": string()}, ["file_id"]), "read", drive_files_get, "shared drive file"),
    ToolSpec("drive.files.export", "Export a shared-drive file as text (spreadsheets as CSV, PDFs as extracted text).", obj({"file_id": string()}, ["file_id"]), "read", drive_files_export, "shared drive export"),
    ToolSpec(
        "notes.drafts.create",
        "Create, but do not send, a stakeholder draft note.",
        obj({"recipient": string(), "subject": string(), "body": string(), "related_request_id": string(), "related_assay_id": string()}, ["recipient", "subject", "body"]),
        "write",
        drafts_create,
        "collaboration draft",
        idempotent=False,
    ),
)

SERVERS = {
    "lims": "Laboratory information management system: assays, scientists, sample-batch counts, protocol versions, run requests, assay runs, and QC results.",
    "instruments": "Instrument schedule: analyser roster, calibration certificates, booking-window calendar, and bookings.",
    "inventory": "Reagent inventory: reagent catalog, lot register with expiry and quarantine state, and inter-site transfers.",
    "supplier": "Supplier portal: shipment confirmations with lead times and cold-chain terms, and reagent orders.",
    "eln": "Electronic lab notebook: method notes and SOP references with supersession.",
    "approvals": "Approval workflow records with exact scope.",
    "messages": "Assay-operations mailbox for the core facility.",
    "chat": "Assay-operations chat threads.",
    "drive": "Shared drive holding SOPs, registers, calendars, and exports.",
    "notes": "Stakeholder draft notes (never sent by the benchmark).",
}

__all__ = ["SERVERS", "TOOLS", "usable_vials"]
