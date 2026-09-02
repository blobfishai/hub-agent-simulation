"""Travel & Events Policy documents mounted in every DeskOps world (effective and superseded), with the structured parameters the travel desk serves."""

from __future__ import annotations

from typing import Any

POLICY_CODE = "TE-07"
CURRENT_POLICY_ID = "POL-TE07-V5"
SUPERSEDED_POLICY_ID = "POL-TE07-2024"

PER_DIEM_USD: dict[str, int] = {"GB": 85, "PT": 70, "CA": 95, "SG": 110, "US": 100}
FARE_CAP_USD: dict[str, int] = {"europe-europe": 450, "north-america-europe": 1400, "asia-pacific-europe": 1900, "europe-north-america": 1400, "north-america-north-america": 700}
CONTINGENCY_BANDS: tuple[tuple[int, int, int], ...] = ((1, 15, 500), (16, 40, 800), (41, 500, 1200))
CHANGE_DESK_THRESHOLD_USD = 2500
HOLD_DEPOSIT_THRESHOLD_USD = 5000

CURRENT_PARAMETERS: dict[str, Any] = {
    "per_diem_usd_by_country": PER_DIEM_USD,
    "fare_cap_usd_by_route": FARE_CAP_USD,
    "contingency_usd_by_attendee_band": [{"min_attendees": lo, "max_attendees": hi, "contingency_usd": amount} for lo, hi, amount in CONTINGENCY_BANDS],
    "change_desk_threshold_usd": CHANGE_DESK_THRESHOLD_USD,
    "hold_deposit_threshold_usd": HOLD_DEPOSIT_THRESHOLD_USD,
    "hard_conflict_kinds": ["board_meeting", "customer_commitment", "leave", "conference"],
    "soft_block_kinds": ["focus_time", "tentative", "recurring", "travel"],
    "traveller_confirmation": "next business day after the group desk's ticketing date",
    "basic_fares_changeable": False,
}
SUPERSEDED_PARAMETERS: dict[str, Any] = {
    "per_diem_usd_by_country": {"GB": 65, "PT": 55, "CA": 75, "SG": 90, "US": 80},
    "fare_cap_usd_by_route": {"europe-europe": 600, "north-america-europe": 1800, "asia-pacific-europe": 2400},
    "contingency_usd_by_attendee_band": [{"min_attendees": 1, "max_attendees": 500, "contingency_usd": 300}],
    "change_desk_threshold_usd": 5000,
    "hold_deposit_threshold_usd": 8000,
    "hard_conflict_kinds": ["board_meeting", "leave"],
    "soft_block_kinds": ["focus_time", "tentative", "recurring", "travel", "customer_commitment", "conference"],
    "traveller_confirmation": "same day as ticketing",
    "basic_fares_changeable": True,
}


def contingency_for(attendees: int) -> int:
    for low, high, amount in CONTINGENCY_BANDS:
        if low <= attendees <= high:
            return amount
    raise ValueError(f"no contingency band for {attendees} attendees")


def effective_policy(as_of: str) -> str:
    return f"""# Travel & Events Policy TE-07 (v5, effective 2026-03-02)

Applies to Larkspur Analytics offsites, summits, and team weeks organised through Workplace & Events Operations for every office (Bristol hub, Lisbon, Toronto, Denver, Singapore). This version supersedes the 2024 edition in full. Planning date for the cases in this room: {as_of}.

## 1. Attendance requirement

1.1 The required attendees of an offsite are the people flagged required on the calendar event at the current revision of its agenda document. Optional attendees never count toward viability or travel sizing.
1.2 A required attendee whose home office is the venue's local office attends without a travel booking. Every other required attendee needs one ticketed itinerary to the venue city.
1.3 Session days are the days named by the current agenda revision; the offsite runs Tuesday to the last session day. The Monday before the first session and the weekdays after the last session are travel or non-session days and carry no sessions.
1.4 Per-diem accrues per traveller per billed day at the venue country's rate in the per-diem table. A change in billed days changes the per-diem commitment.

## 2. Booking changes

2.1 A changeable itinerary is re-issued to the new travel date by the group desk for the change fee recorded on the booking. A basic (non-changeable) fare cannot be changed: the seat is forfeited and a new ticket is issued at the group desk's confirmed group fare.
2.2 New and re-issued tickets are confirmed to travellers on the next business day after the group desk's ticketing date (standard queue or rush). Travel on the day tickets issue is not planned.
2.3 Rebooking at a fare above the route's fare cap, or outside the group desk's confirmation, is not supported by this policy.
2.4 The group desk's confirmation sets the seats it can issue and its standard and rush ticketing dates; a rush fee applies to the rush queue.

## 3. Offsite week viability

3.1 A week is viable only when the venue's portal shows the week OPEN and no required attendee has a hard conflict (board meeting, customer commitment, approved leave, external conference) on a session day. Focus time, tentative holds, recurring internal meetings, and travel buffers are soft blocks and are never conflicts.
3.2 A held, booked, or blackout venue week is never displaced without the venue's events director and our events and workplace manager acting together.
3.3 A required attendee's protected commitment is never displaced without the chief of staff.
3.4 The venue must seat the full attendee list. A capacity shortfall makes the week unviable for that venue.
3.5 A week counts for a move only when its Monday falls on or after the travellers' confirmation date under the chosen ticketing queue.

## 4. Budget

4.1 The usable headroom of a budget line is approved less committed less reserved (open venue-hold deposits and pending adjustments). The gross remaining balance is never headroom.
4.2 The incremental cost of a move is the sum of change fees on re-issued itineraries, new tickets at the group fare, the venue difference between the target quote and the contracted quote, and the per-diem difference.
4.3 An incremental cost above usable headroom requires a budget-line adjustment posted before any booking is changed. An adjustment covers the uncovered incremental cost plus the events contingency from the contingency table.
4.4 An adjustment above the line's adjustment ceiling, and any reclass between cost centres, requires the finance business partner.

## 5. Authority

5.1 Events and workplace manager: venue holds with deposits within the signed approval, booking changes within the approval's incremental spend and ticketing queue, calendar moves inside the approval's window, and budget adjustments within the approval and the line ceiling.
5.2 Finance business partner: incremental spend above the approval, adjustments above the line ceiling, and reclasses between cost centres.
5.3 Travel program lead: rush ticketing not named in an approval and fare-cap exceptions.
5.4 Chief of staff: displacing a required attendee's protected commitment.
5.5 An approval covers exactly the event, spend, venue, queue, and options it names. It never selects an option in advance and never extends to a broader record.
"""


SUPERSEDED_POLICY = """# Travel & Events Policy TE-07 (2024 edition) — SUPERSEDED

This edition was replaced by v5 on 2026-03-02 and is retained for audit only. Do not apply it.

1. Attendance may be sized from the attendee list on the original invitation.
2. Basic fares may be changed for a flat USD 60 desk fee.
3. Customer commitments and external conferences are soft blocks; only board meetings and approved leave are conflicts.
4. Tickets are confirmed to travellers on the day they issue.
5. Budget headroom is the gross remaining balance of the line; reserved deposits are not deducted.
6. The events contingency is USD 300 for any offsite.
7. Incremental spend up to USD 5,000 may be approved by the events manager at discretion, and a held venue week may be released by the coordinator with the venue's sales desk.
"""


PER_DIEM_TABLE_CSV = "country,per_diem_usd_per_day,basis\n" + "".join(f"{country},{amount},per traveller per billed day\n" for country, amount in PER_DIEM_USD.items())
FARE_CAP_TABLE_CSV = "route,fare_cap_usd,cabin\n" + "".join(f"{route},{amount},economy\n" for route, amount in FARE_CAP_USD.items())
CONTINGENCY_TABLE_CSV = "min_attendees,max_attendees,contingency_usd,rule\n" + "".join(f"{lo},{hi},{amount},uncovered incremental cost plus contingency\n" for lo, hi, amount in CONTINGENCY_BANDS)

__all__ = [
    "CHANGE_DESK_THRESHOLD_USD",
    "CONTINGENCY_BANDS",
    "CONTINGENCY_TABLE_CSV",
    "CURRENT_PARAMETERS",
    "CURRENT_POLICY_ID",
    "FARE_CAP_TABLE_CSV",
    "FARE_CAP_USD",
    "HOLD_DEPOSIT_THRESHOLD_USD",
    "PER_DIEM_TABLE_CSV",
    "PER_DIEM_USD",
    "POLICY_CODE",
    "SUPERSEDED_PARAMETERS",
    "SUPERSEDED_POLICY",
    "SUPERSEDED_POLICY_ID",
    "contingency_for",
    "effective_policy",
]
