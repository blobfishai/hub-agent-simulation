"""ClinicOps provider-shaped tools over the family's SQLite world.

Read tools return FHIR R4-shaped resources (Patient, Observation,
MedicationRequest, Appointment, Slot) or plain provider records; write tools
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

MRN_SYSTEM = "urn:northlake:mrn"
FORMULARY_SYSTEM = "urn:northlake:formulary"
LOINC = "http://loinc.org"
SESSIONS = {"AM": ("08:00:00", "12:00:00"), "PM": ("12:30:00", "16:30:00")}
ORDER_UNIT = "VIAL"


# --------------------------------------------------------------------------- #
# FHIR-shaped renderers
# --------------------------------------------------------------------------- #


def _bundle(resources: list[dict[str, Any]]) -> dict[str, Any]:
    return {"resourceType": "Bundle", "type": "searchset", "total": len(resources), "entry": [{"resource": resource} for resource in resources]}


def _patient(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "resourceType": "Patient",
        "id": row["patient_id"],
        "identifier": [{"system": MRN_SYSTEM, "value": row["mrn"]}],
        "name": [{"family": row["family_name"], "given": [row["given_name"]]}],
        "birthDate": row["birth_date"],
        "gender": row["sex"],
        "generalPractitioner": [{"reference": f"Practitioner/{row['primary_practitioner_id']}"}] if row.get("primary_practitioner_id") else [],
    }


def _observation(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "resourceType": "Observation",
        "id": row["observation_id"],
        "status": row["status"],
        "code": {"coding": [{"system": LOINC, "code": row["code"], "display": row["display"]}]},
        "subject": {"reference": f"Patient/{row['patient_id']}"},
        "effectiveDateTime": row["effective_date"],
        "valueQuantity": {"value": row["value"], "unit": row["unit"]},
    }


def _medication_request(row: dict[str, Any], medication: dict[str, Any]) -> dict[str, Any]:
    return {
        "resourceType": "MedicationRequest",
        "id": row["request_id"],
        "status": row["status"],
        "intent": row["intent"],
        "priority": row["priority"],
        "medicationCodeableConcept": {"coding": [{"system": FORMULARY_SYSTEM, "code": row["medication_code"], "display": medication["display"]}]},
        "subject": {"reference": f"Patient/{row['patient_id']}"},
        "authoredOn": row["authored_on"],
        "requester": {"reference": f"Practitioner/{row['requester_id']}"},
        "dosageInstruction": [
            {
                "text": row["regimen"],
                "timing": {"code": {"text": row["regimen"]}},
                "route": {"text": medication["route"]},
                "doseAndRate": [{"doseQuantity": {"value": row["dose_value"], "unit": row["dose_unit"]}}],
            }
        ],
        "extension": [
            {"url": "urn:northlake:doses-in-scope", "valueInteger": row["doses_in_scope"]},
            {"url": "urn:northlake:infusion-minutes", "valueInteger": row["infusion_minutes"]},
            {"url": "urn:northlake:observation-minutes", "valueInteger": row["observation_minutes"]},
        ],
        "note": [{"text": row["note"]}] if row.get("note") else [],
    }


def _appointment(row: dict[str, Any]) -> dict[str, Any]:
    participants = [{"actor": {"reference": f"Patient/{row['patient_id']}"}, "status": "accepted"}]
    if row.get("chair_id"):
        participants.append({"actor": {"reference": f"Location/{row['chair_id']}"}, "status": "accepted"})
    return {
        "resourceType": "Appointment",
        "id": row["appointment_id"],
        "status": row["status"],
        "description": row.get("description"),
        "start": row.get("start_time"),
        "end": row.get("end_time"),
        "chair": row.get("chair_id"),
        "participant": participants,
        "basedOn": [{"reference": f"MedicationRequest/{row['request_id']}"}] if row.get("request_id") else [],
        "meta": {"versionId": str(row["revision"]), "lastUpdated": row["last_updated"]},
    }


def _slot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "resourceType": "Slot",
        "id": row["slot_id"],
        "schedule": {"reference": f"Schedule/{row['chair_id']}"},
        "chair": row["chair_id"],
        "serviceDate": row["service_date"],
        "session": row["session"],
        "start": f"{row['service_date']}T{row['start_time']}",
        "end": f"{row['service_date']}T{row['end_time']}",
        "status": row["status"],
        "holdReason": row.get("hold_reason"),
        "appointment": row.get("appointment_id"),
    }


def _order(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row)


# --------------------------------------------------------------------------- #
# EHR reads
# --------------------------------------------------------------------------- #


def patients_search(world: World, args: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    if args.get("identifier"):
        rows = world.all("SELECT * FROM patients WHERE mrn = ? ORDER BY patient_id", (args["identifier"],))
    elif args.get("family"):
        rows = world.all("SELECT * FROM patients WHERE lower(family_name) = lower(?) ORDER BY patient_id", (args["family"],))
    else:
        raise ValueError("identifier or family is required")
    return _bundle([_patient(row) for row in rows])


def patients_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _patient(world.one("SELECT * FROM patients WHERE patient_id = ?", (args["patient_id"],), missing=f"Patient/{args['patient_id']} not found"))


def observations_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.one("SELECT patient_id FROM patients WHERE patient_id = ?", (args["patient_id"],), missing=f"Patient/{args['patient_id']} not found")
    if args.get("code"):
        rows = world.all("SELECT * FROM observations WHERE patient_id = ? AND code = ? ORDER BY effective_date DESC, observation_id", (args["patient_id"], args["code"]))
    else:
        rows = world.all("SELECT * FROM observations WHERE patient_id = ? ORDER BY effective_date DESC, observation_id", (args["patient_id"],))
    return _bundle([_observation(row) for row in rows])


def _medications_by_code(world: World) -> dict[str, dict[str, Any]]:
    return {row["medication_code"]: row for row in world.all("SELECT * FROM medications")}


def medication_requests_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("patient_id", "medication_code", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    if not clauses:
        raise ValueError("at least one of patient_id, medication_code, status is required")
    rows = world.all(f"SELECT * FROM medication_requests WHERE {' AND '.join(clauses)} ORDER BY request_id", params)
    medications = _medications_by_code(world)
    return _bundle([_medication_request(row, medications[row["medication_code"]]) for row in rows])


def medication_requests_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM medication_requests WHERE request_id = ?", (args["request_id"],), missing=f"MedicationRequest/{args['request_id']} not found")
    return _medication_request(row, _medications_by_code(world)[row["medication_code"]])


def practitioners_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM practitioners WHERE practitioner_id = ?", (args["practitioner_id"],), missing="Practitioner not found")
    return {"resourceType": "Practitioner", "id": row["practitioner_id"], "name": [{"text": row["name"]}], "qualification": [{"code": {"text": row["specialty"]}}], "role": row["role"]}


# --------------------------------------------------------------------------- #
# Pharmacy
# --------------------------------------------------------------------------- #


def medications_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM medications WHERE medication_code = ?", (args["medication_code"],), missing=f"formulary item {args['medication_code']} not found"))


def inventory_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("medication_code", "location_id"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = world.all(
        f"SELECT medication_code, location_id, SUM(quantity_on_hand) AS quantity_on_hand, COUNT(*) AS lot_count FROM inventory_lots {where} "
        "GROUP BY medication_code, location_id ORDER BY medication_code, location_id",
        params,
    )
    return {"balances": rows, "note": "Gross on-hand balances including quarantined, reserved, and short-dated lots; see pharmacy.lots.list for lot status."}


def lots_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = ["medication_code = ?"], [args["medication_code"]]
    for key in ("location_id", "status"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    rows = world.all(f"SELECT * FROM inventory_lots WHERE {' AND '.join(clauses)} ORDER BY expiry_date, lot_id", params)
    return {"medication_code": args["medication_code"], "lots": rows}


def orders_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("status", "medication_code"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"orders": [_order(row) for row in world.all(f"SELECT * FROM purchase_orders {where} ORDER BY po_id", params)]}


def orders_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _order(world.one("SELECT * FROM purchase_orders WHERE po_id = ?", (args["po_id"],), missing=f"purchase order {args['po_id']} not found"))


def orders_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    supplier = world.one("SELECT * FROM suppliers WHERE supplier_id = ?", (args["supplier_id"],), missing=f"supplier {args['supplier_id']} not found")
    world.one("SELECT medication_code FROM medications WHERE medication_code = ?", (args["medication_code"],), missing=f"formulary item {args['medication_code']} not found")
    confirmation = world.one(
        "SELECT * FROM supplier_confirmations WHERE confirmation_id = ?",
        (args["confirmation_id"],),
        missing=f"supplier confirmation {args['confirmation_id']} not found",
    )
    if confirmation["supplier_id"] != supplier["supplier_id"] or confirmation["medication_code"] != args["medication_code"]:
        raise ValueError(f"confirmation {args['confirmation_id']} does not cover {args['medication_code']} from {args['supplier_id']}")
    if confirmation["status"] != "OPEN":
        raise ValueError(f"confirmation {args['confirmation_id']} is {confirmation['status']}")
    if args["quantity"] > confirmation["quantity_available"]:
        raise ValueError(f"confirmation {args['confirmation_id']} covers at most {confirmation['quantity_available']} {ORDER_UNIT}")
    expected = confirmation["standard_delivery_date"] if args["delivery_option"] == "standard" else confirmation["expedited_delivery_date"]
    po_id = world.next_id("purchase_orders", "po_id", "PO-")
    row = {
        "po_id": po_id,
        "supplier_id": supplier["supplier_id"],
        "confirmation_id": confirmation["confirmation_id"],
        "medication_code": args["medication_code"],
        "quantity": args["quantity"],
        "unit": ORDER_UNIT,
        "delivery_option": args["delivery_option"],
        "expected_delivery_date": expected,
        "status": "SUBMITTED",
        "requested_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO purchase_orders (po_id, supplier_id, confirmation_id, medication_code, quantity, unit, delivery_option, expected_delivery_date, status, requested_by, created_at, revision) "
        "VALUES (:po_id, :supplier_id, :confirmation_id, :medication_code, :quantity, :unit, :delivery_option, :expected_delivery_date, :status, :requested_by, :created_at, :revision)",
        row,
    )
    world.audit("pharmacy.orders.create", "purchase_orders", po_id, "insert", row)
    world.record_mutation("pharmacy.orders.create", "purchase_orders", po_id, "SUBMITTED", args)
    return _order(row)


def transfers_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return dict(world.one("SELECT * FROM stock_transfers WHERE transfer_id = ?", (args["transfer_id"],), missing=f"transfer {args['transfer_id']} not found"))


def releasable_quantity(world: World, medication_code: str, location_id: str) -> int:
    medication = world.one("SELECT * FROM medications WHERE medication_code = ?", (medication_code,), missing=f"formulary item {medication_code} not found")
    horizon = (world.as_of + timedelta(days=int(medication["minimum_dating_days"]))).isoformat()
    row = world.one(
        "SELECT COALESCE(SUM(quantity_on_hand), 0) AS quantity FROM inventory_lots WHERE medication_code = ? AND location_id = ? "
        "AND status = 'AVAILABLE' AND reserved_for_patient_id IS NULL AND expiry_date > ?",
        (medication_code, location_id, horizon),
    )
    return int(row["quantity"])


def transfers_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    for key in ("from_location_id", "to_location_id"):
        world.one("SELECT location_id FROM locations WHERE location_id = ?", (args[key],), missing=f"location {args[key]} not found")
    if args["from_location_id"] == args["to_location_id"]:
        raise ValueError("a transfer needs two different locations")
    releasable = releasable_quantity(world, args["medication_code"], args["from_location_id"])
    if args["quantity"] > releasable:
        raise ValueError(f"{args['from_location_id']} holds only {releasable} releasable {ORDER_UNIT} of {args['medication_code']}; reserved, quarantined, and short-dated lots cannot move")
    transfer_id = world.next_id("stock_transfers", "transfer_id", "TR-")
    row = {
        "transfer_id": transfer_id,
        "medication_code": args["medication_code"],
        "quantity": args["quantity"],
        "from_location_id": args["from_location_id"],
        "to_location_id": args["to_location_id"],
        "scheduled_date": args["scheduled_date"],
        "status": "SCHEDULED",
        "requested_by": world.task["role"],
        "created_at": world.clock(),
        "revision": 1,
    }
    world.connection.execute(
        "INSERT INTO stock_transfers (transfer_id, medication_code, quantity, from_location_id, to_location_id, scheduled_date, status, requested_by, created_at, revision) "
        "VALUES (:transfer_id, :medication_code, :quantity, :from_location_id, :to_location_id, :scheduled_date, :status, :requested_by, :created_at, :revision)",
        row,
    )
    world.audit("pharmacy.transfers.create", "stock_transfers", transfer_id, "insert", row)
    world.record_mutation("pharmacy.transfers.create", "stock_transfers", transfer_id, "SCHEDULED", args)
    return dict(row)


# --------------------------------------------------------------------------- #
# Scheduling
# --------------------------------------------------------------------------- #


def chairs_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("location_id"):
        rows = world.all("SELECT * FROM chairs WHERE location_id = ? ORDER BY chair_id", (args["location_id"],))
    else:
        rows = world.all("SELECT * FROM chairs ORDER BY chair_id")
    return {"chairs": rows}


def slots_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses = ["s.service_date >= ?", "s.service_date <= ?"]
    params: list[Any] = [args["start_date"], args["end_date"]]
    if args.get("chair_id"):
        clauses.append("s.chair_id = ?")
        params.append(args["chair_id"])
    if args.get("location_id"):
        clauses.append("c.location_id = ?")
        params.append(args["location_id"])
    if args.get("status"):
        clauses.append("s.status = ?")
        params.append(args["status"])
    rows = world.all(
        f"SELECT s.* FROM slots s JOIN chairs c ON c.chair_id = s.chair_id WHERE {' AND '.join(clauses)} ORDER BY s.service_date, s.chair_id, s.session DESC",
        params,
    )
    return {"slots": [_slot(row) for row in rows]}


def appointments_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("patient_id", "chair_id", "status"):
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
    rows = world.all(f"SELECT * FROM appointments WHERE {' AND '.join(clauses)} ORDER BY start_time, appointment_id", params)
    return _bundle([_appointment(row) for row in rows])


def appointments_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    return _appointment(world.one("SELECT * FROM appointments WHERE appointment_id = ?", (args["appointment_id"],), missing=f"Appointment/{args['appointment_id']} not found"))


def _split_datetime(value: str, label: str) -> tuple[str, str]:
    if len(value) != 19 or value[10] != "T":
        raise ValueError(f"{label} must be YYYY-MM-DDTHH:MM:SS")
    date.fromisoformat(value[:10])
    return value[:10], value[11:]


def _sessions_for_interval(world: World, chair_id: str, start: str, end: str) -> list[dict[str, Any]]:
    start_date, start_time = _split_datetime(start, "start_time")
    end_date, end_time = _split_datetime(end, "end_time")
    if start_date != end_date:
        raise ValueError("an infusion appointment must start and end on the same service date")
    if start_time >= end_time:
        raise ValueError("start_time must precede end_time")
    rows = world.all("SELECT * FROM slots WHERE chair_id = ? AND service_date = ? ORDER BY start_time", (chair_id, start_date))
    covering = [row for row in rows if row["start_time"] < end_time and row["end_time"] > start_time]
    if not covering:
        raise ValueError(f"no {chair_id} session covers {start} - {end}")
    if start_time < min(row["start_time"] for row in covering) or end_time > max(row["end_time"] for row in covering):
        raise ValueError(f"{start} - {end} falls outside the {chair_id} clinic sessions")
    return covering


def _require_free(sessions: list[dict[str, Any]], *, holder: str | None = None) -> None:
    for row in sessions:
        if row["status"] == "free":
            continue
        if holder and row.get("appointment_id") == holder:
            continue
        raise ValueError(f"{row['slot_id']} is {row['status']}: {row.get('hold_reason') or 'not available'}; protected and blocked sessions cannot be displaced")


def _claim(world: World, tool: str, sessions: list[dict[str, Any]], appointment_id: str) -> None:
    for row in sessions:
        world.connection.execute("UPDATE slots SET status = 'busy', hold_reason = 'booked', appointment_id = ? WHERE slot_id = ?", (appointment_id, row["slot_id"]))
        world.audit(tool, "slots", row["slot_id"], "update", {"status": "busy", "appointment_id": appointment_id})


def _release(world: World, tool: str, appointment_id: str) -> None:
    for row in world.all("SELECT slot_id FROM slots WHERE appointment_id = ?", (appointment_id,)):
        world.connection.execute("UPDATE slots SET status = 'free', hold_reason = NULL, appointment_id = NULL WHERE slot_id = ?", (row["slot_id"],))
        world.audit(tool, "slots", row["slot_id"], "update", {"status": "free", "appointment_id": None})


def appointments_create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "scheduling.appointments.create"
    world.one("SELECT patient_id FROM patients WHERE patient_id = ?", (args["patient_id"],), missing=f"Patient/{args['patient_id']} not found")
    request = world.one("SELECT * FROM medication_requests WHERE request_id = ?", (args["request_id"],), missing=f"MedicationRequest/{args['request_id']} not found")
    if request["patient_id"] != args["patient_id"]:
        raise ValueError(f"MedicationRequest/{args['request_id']} belongs to another patient")
    chair = world.one("SELECT * FROM chairs WHERE chair_id = ?", (args["chair_id"],), missing=f"chair {args['chair_id']} not found")
    if chair["status"] != "ACTIVE":
        raise ValueError(f"{args['chair_id']} is {chair['status']}: {chair.get('status_note') or ''}".strip())
    sessions = _sessions_for_interval(world, args["chair_id"], args["start_time"], args["end_time"])
    _require_free(sessions)
    appointment_id = world.next_id("appointments", "appointment_id", "APPT-")
    row = {
        "appointment_id": appointment_id,
        "patient_id": args["patient_id"],
        "request_id": args["request_id"],
        "chair_id": args["chair_id"],
        "start_time": args["start_time"],
        "end_time": args["end_time"],
        "status": "booked",
        "description": args.get("description"),
        "revision": 1,
        "last_updated": world.clock(),
    }
    world.connection.execute(
        "INSERT INTO appointments (appointment_id, patient_id, request_id, chair_id, start_time, end_time, status, description, revision, last_updated) "
        "VALUES (:appointment_id, :patient_id, :request_id, :chair_id, :start_time, :end_time, :status, :description, :revision, :last_updated)",
        row,
    )
    world.audit(tool, "appointments", appointment_id, "insert", row)
    _claim(world, tool, sessions, appointment_id)
    world.record_mutation(tool, "appointments", appointment_id, "booked", args)
    return _appointment(row)


def appointments_update(world: World, args: dict[str, Any]) -> dict[str, Any]:
    tool = "scheduling.appointments.update"
    current = world.one("SELECT * FROM appointments WHERE appointment_id = ?", (args["appointment_id"],), missing=f"Appointment/{args['appointment_id']} not found")
    if current["status"] in {"cancelled", "fulfilled"}:
        raise ValueError(f"Appointment/{args['appointment_id']} is {current['status']} and cannot be changed")
    changes = {key: args[key] for key in ("chair_id", "start_time", "end_time", "status", "description") if key in args}
    if not changes:
        raise ValueError("no change requested")
    updated = {**current, **changes}
    new_status = updated["status"]
    if new_status == "cancelled":
        _release(world, tool, current["appointment_id"])
    else:
        if any(key in changes for key in ("chair_id", "start_time", "end_time")) or current["status"] != "booked":
            if not (updated.get("chair_id") and updated.get("start_time") and updated.get("end_time")):
                raise ValueError("booking an appointment needs chair_id, start_time, and end_time")
            chair = world.one("SELECT * FROM chairs WHERE chair_id = ?", (updated["chair_id"],), missing=f"chair {updated['chair_id']} not found")
            if chair["status"] != "ACTIVE":
                raise ValueError(f"{updated['chair_id']} is {chair['status']}: {chair.get('status_note') or ''}".strip())
            sessions = _sessions_for_interval(world, updated["chair_id"], updated["start_time"], updated["end_time"])
            _require_free(sessions, holder=current["appointment_id"])
            _release(world, tool, current["appointment_id"])
            _claim(world, tool, sessions, current["appointment_id"])
            if new_status not in {"booked", "pending"}:
                raise ValueError(f"unsupported status transition to {new_status}")
    updated["revision"] = int(current["revision"]) + 1
    updated["last_updated"] = world.clock()
    world.connection.execute(
        "UPDATE appointments SET chair_id = :chair_id, start_time = :start_time, end_time = :end_time, status = :status, description = :description, revision = :revision, last_updated = :last_updated WHERE appointment_id = :appointment_id",
        updated,
    )
    world.audit(tool, "appointments", current["appointment_id"], "update", changes)
    world.record_mutation(tool, "appointments", current["appointment_id"], new_status, args, revision=updated["revision"])
    return _appointment(updated)


# --------------------------------------------------------------------------- #
# Supplier, approvals, collaboration surfaces
# --------------------------------------------------------------------------- #


def confirmations_list(world: World, args: dict[str, Any]) -> dict[str, Any]:
    clauses, params = [], []
    for key in ("medication_code", "supplier_id"):
        if args.get(key):
            clauses.append(f"{key} = ?")
            params.append(args[key])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return {"confirmations": world.all(f"SELECT * FROM supplier_confirmations {where} ORDER BY confirmation_id", params)}


def confirmations_get(world: World, args: dict[str, Any]) -> dict[str, Any]:
    row = world.one("SELECT * FROM supplier_confirmations WHERE confirmation_id = ?", (args["confirmation_id"],), missing=f"confirmation {args['confirmation_id']} not found")
    supplier = world.one("SELECT * FROM suppliers WHERE supplier_id = ?", (row["supplier_id"],))
    return {**row, "supplier_name": supplier["name"]}


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
        "related_patient_id": args.get("related_patient_id"),
        "created_at": world.clock(),
        "status": "DRAFT",
    }
    world.connection.execute(
        "INSERT INTO note_drafts (draft_id, recipient, subject, body, related_request_id, related_patient_id, created_at, status) "
        "VALUES (:draft_id, :recipient, :subject, :body, :related_request_id, :related_patient_id, :created_at, :status)",
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
    ToolSpec("ehr.patients.search", "Search patients by medical record number or family name (FHIR Patient searchset).", obj({"identifier": string("MRN"), "family": string("family name")}), "read", patients_search, "FHIR R4 Patient search"),
    ToolSpec("ehr.patients.get", "Read one Patient resource by id.", obj({"patient_id": string()}, ["patient_id"]), "read", patients_get, "FHIR R4 Patient read"),
    ToolSpec("ehr.observations.list", "List Observation resources for a patient, optionally by LOINC code (29463-7 body weight, 8302-2 height).", obj({"patient_id": string(), "code": string("LOINC code")}, ["patient_id"]), "read", observations_list, "FHIR R4 Observation search"),
    ToolSpec("ehr.medication_requests.list", "List MedicationRequest resources by patient, formulary code, or status.", obj({"patient_id": string(), "medication_code": string(), "status": string()}), "read", medication_requests_list, "FHIR R4 MedicationRequest search"),
    ToolSpec("ehr.medication_requests.get", "Read one MedicationRequest (order) with dose, regimen, and infusion timing.", obj({"request_id": string()}, ["request_id"]), "read", medication_requests_get, "FHIR R4 MedicationRequest read"),
    ToolSpec("ehr.practitioners.get", "Read one Practitioner resource.", obj({"practitioner_id": string()}, ["practitioner_id"]), "read", practitioners_get, "FHIR R4 Practitioner read"),
    ToolSpec("pharmacy.medications.get", "Read a formulary item: vial strength, storage, and minimum remaining dating.", obj({"medication_code": string()}, ["medication_code"]), "read", medications_get, "pharmacy formulary record"),
    ToolSpec("pharmacy.inventory.list", "Gross on-hand balances by formulary item and location (no netting of quarantine, reservation, or dating).", obj({"medication_code": string(), "location_id": string()}), "read", inventory_list, "pharmacy inventory balance"),
    ToolSpec("pharmacy.lots.list", "List inventory lots for a formulary item with quantity, expiry, status, and reservations.", obj({"medication_code": string(), "location_id": string(), "status": string()}, ["medication_code"]), "read", lots_list, "pharmacy lot register"),
    ToolSpec("pharmacy.orders.list", "List purchase orders.", obj({"status": string(), "medication_code": string()}), "read", orders_list, "procurement purchase order"),
    ToolSpec("pharmacy.orders.get", "Read one purchase order.", obj({"po_id": string()}, ["po_id"]), "read", orders_get, "procurement purchase order"),
    ToolSpec(
        "pharmacy.orders.create",
        "Create a purchase order against an open supplier confirmation. The expected delivery date is taken from the confirmation for the chosen delivery option.",
        obj(
            {
                "supplier_id": string(),
                "confirmation_id": string(),
                "medication_code": string(),
                "quantity": integer(minimum=1),
                "delivery_option": {"type": "string", "enum": ["standard", "expedited"]},
            },
            ["supplier_id", "confirmation_id", "medication_code", "quantity", "delivery_option"],
        ),
        "write",
        orders_create,
        "procurement purchase order",
        idempotent=False,
    ),
    ToolSpec("pharmacy.transfers.get", "Read one inter-site stock transfer.", obj({"transfer_id": string()}, ["transfer_id"]), "read", transfers_get, "pharmacy stock transfer"),
    ToolSpec(
        "pharmacy.transfers.create",
        "Schedule an inter-site stock transfer. Only releasable stock at the source (available, unreserved, within minimum dating) may move.",
        obj(
            {"medication_code": string(), "quantity": integer(minimum=1), "from_location_id": string(), "to_location_id": string(), "scheduled_date": string("ISO date")},
            ["medication_code", "quantity", "from_location_id", "to_location_id", "scheduled_date"],
        ),
        "write",
        transfers_create,
        "pharmacy stock transfer",
        idempotent=False,
    ),
    ToolSpec("scheduling.chairs.list", "List infusion chairs with status and first-dose capability.", obj({"location_id": string()}), "read", chairs_list, "FHIR R4 Location (chair) list"),
    ToolSpec("scheduling.slots.list", "List chair sessions (FHIR Slot) between two dates with free / busy / protected / blocked status.", obj({"start_date": string("ISO date"), "end_date": string("ISO date"), "location_id": string(), "chair_id": string(), "status": string()}, ["start_date", "end_date"]), "read", slots_list, "FHIR R4 Slot search"),
    ToolSpec("scheduling.appointments.list", "List Appointment resources by patient, chair, status, or date window.", obj({"patient_id": string(), "chair_id": string(), "status": string(), "start_date": string("ISO date"), "end_date": string("ISO date")}), "read", appointments_list, "FHIR R4 Appointment search"),
    ToolSpec("scheduling.appointments.get", "Read one Appointment resource.", obj({"appointment_id": string()}, ["appointment_id"]), "read", appointments_get, "FHIR R4 Appointment read"),
    ToolSpec(
        "scheduling.appointments.create",
        "Book an infusion appointment on a chair. Every session the interval touches must be free; protected and blocked sessions are never displaced.",
        obj(
            {"patient_id": string(), "request_id": string(), "chair_id": string(), "start_time": string(DATETIME), "end_time": string(DATETIME), "description": string()},
            ["patient_id", "request_id", "chair_id", "start_time", "end_time"],
        ),
        "write",
        appointments_create,
        "FHIR R4 Appointment create",
        idempotent=False,
    ),
    ToolSpec(
        "scheduling.appointments.update",
        "Move, book, or cancel an existing appointment. Moving re-validates the target sessions; the record revision increments.",
        obj(
            {"appointment_id": string(), "chair_id": string(), "start_time": string(DATETIME), "end_time": string(DATETIME), "status": {"type": "string", "enum": ["booked", "pending", "cancelled"]}, "description": string()},
            ["appointment_id"],
        ),
        "write",
        appointments_update,
        "FHIR R4 Appointment update",
        idempotent=False,
    ),
    ToolSpec("supplier.confirmations.list", "List supplier delivery confirmations.", obj({"medication_code": string(), "supplier_id": string()}), "read", confirmations_list, "supplier confirmation"),
    ToolSpec("supplier.confirmations.get", "Read one supplier delivery confirmation: quantity, standard and expedited delivery dates, fee, validity.", obj({"confirmation_id": string()}, ["confirmation_id"]), "read", confirmations_get, "supplier confirmation"),
    ToolSpec("approvals.list", "List approval records, optionally by keyword.", obj({"q": string()}), "read", approvals_list, "approval workflow record"),
    ToolSpec("approvals.get", "Read one approval record with its exact scope and approver.", obj({"approval_id": string()}, ["approval_id"]), "read", approvals_get, "approval workflow record"),
    ToolSpec("messages.list", "Search secure messages and email by keyword (subject, body, labels).", obj({"q": string(), "max_results": integer(minimum=1)}, ["q"]), "read", messages_list, "mailbox search"),
    ToolSpec("messages.get", "Read one message with body and attachment list.", obj({"message_id": string()}, ["message_id"]), "read", messages_get, "mailbox message"),
    ToolSpec("chat.threads.list", "Search team chat threads by keyword.", obj({"q": string()}, ["q"]), "read", chat_threads_list, "team chat search"),
    ToolSpec("chat.threads.get", "Read one team chat thread.", obj({"thread_id": string()}, ["thread_id"]), "read", chat_threads_get, "team chat thread"),
    ToolSpec("drive.files.list", "Search shared-drive files by keyword (name, folder, content).", obj({"q": string()}, ["q"]), "read", drive_files_list, "shared drive search"),
    ToolSpec("drive.files.get", "Read shared-drive file metadata.", obj({"file_id": string()}, ["file_id"]), "read", drive_files_get, "shared drive file"),
    ToolSpec("drive.files.export", "Export a shared-drive file as text (spreadsheets as CSV, PDFs as extracted text).", obj({"file_id": string()}, ["file_id"]), "read", drive_files_export, "shared drive export"),
    ToolSpec(
        "notes.drafts.create",
        "Create, but do not send, a stakeholder draft note.",
        obj({"recipient": string(), "subject": string(), "body": string(), "related_request_id": string(), "related_patient_id": string()}, ["recipient", "subject", "body"]),
        "write",
        drafts_create,
        "collaboration draft",
        idempotent=False,
    ),
)

SERVERS = {
    "ehr": "FHIR R4-shaped electronic health record: Patient, Observation, MedicationRequest, Practitioner.",
    "pharmacy": "Pharmacy formulary, lot register, inventory balances, purchase orders, and inter-site transfers.",
    "scheduling": "Infusion chair scheduling: chairs, FHIR Slot sessions, and Appointment resources.",
    "supplier": "Specialty distributor delivery confirmations.",
    "approvals": "Approval workflow records with exact scope.",
    "messages": "Secure messaging and email for the infusion service.",
    "chat": "Infusion team chat threads.",
    "drive": "Shared drive holding policies, registers, calendars, and exports.",
    "notes": "Stakeholder draft notes (never sent by the benchmark).",
}

__all__ = ["SERVERS", "SESSIONS", "TOOLS", "releasable_quantity"]
