"""Standard operating procedure documents mounted in every SciLab world (effective and superseded)."""

from __future__ import annotations

from datetime import date, timedelta


def effective_sop(as_of: str) -> str:
    horizon = (date.fromisoformat(as_of) + timedelta(days=14)).isoformat()
    return f"""# Assay Operations SOP AO-014 (v3, effective 2026-02-02)

Applies to the Corvane Institute Assay Operations Core: the main assay laboratory (SITE-MAIN), the cold-store annex (SITE-ANNEX), the Ridgecombe satellite laboratory (SITE-SAT), and the microplate analyser fleet. This version supersedes the 2024 edition in full.

## 1. Run requirement

1.1 Metered runs (sample counts per batch, per timepoint) are sized at the most recent final sample count recorded for the assay in the LIMS. A stale intake count is never used.
1.2 Tiered validation panels use the validation tier table at the current measured sample count.
1.3 Plates are whole units. Every sample count rounds up to whole plates at the samples-per-plate figure of the current protocol version; partial plates are never planned.
1.4 Control requirement: every plate carries the number of single-use control vials named by the current protocol version, drawn from one released lot. After an invalid control, the re-run and any duplicate run the reporting rule requires must both have their control vials released before the run is booked. An open supplier order is not a substitute for released vials.
1.5 A booked validation or release run may be advanced by up to 7 days with the study director's written note.

## 2. Usable lots

2.1 A control lot counts toward coverage only when its status is AVAILABLE, it is not reserved for a named run request, and it retains at least the reagent's minimum remaining dating (14 days from the planning date). On a planning date of {as_of}, lots that expire on or before {horizon} are inside the dating horizon and are not usable.
2.2 Quarantined lots (temperature excursion, incoming-QC failure, manufacturer notice), expired lots, and lots outside the supplier's current stability letter are never used for a reportable run. Release from quarantine requires the QA director, and the study steering group where a reportable result is involved.
2.3 Received and transferred lots are released to use after incoming QC on the next laboratory day following the delivery or transfer date.
2.4 Order sizing: order the uncovered requirement plus the reagent's ordering margin from the margin table. Inter-site transfers move usable lots only and cover only the receiving site's uncovered quantity.

## 3. Instrument windows

3.1 Analyser windows are AM 08:00-12:00 and PM 12:30-16:30, Monday to Friday, with a qualified operator on shift. A run of up to 4 hours including plate reading occupies one window; a longer run requires both windows of one analyser on one day.
3.2 Protected windows (proficiency-testing panels, clinical-priority batches) and blocked windows (service, lamp replacement, calibration) are never displaced without the study steering group.
3.3 Two short runs of the same protocol class (2 hours or less each, including reading) may be sequenced in one window.
3.4 Validation runs are one continuous run on an analyser whose operational qualification is current per the roster; they may not be split across windows on different days. A run may only be booked on an analyser whose calibration certificate is valid on the run date.
3.5 Out-of-hours, weekend, and overtime windows require the laboratory manager's separate approval.

## 4. Authority

4.1 QA manager: reagent orders and lot transfers within the signed approval's vial count, supplier, and spend, including any expedite fee the approval names.
4.2 QA director: expedited delivery not named in an approval, inter-site transfers and direct orders outside an approval, dating extensions and quarantine releases, and use of lots outside the current stability letter.
4.3 Laboratory manager: analyser re-home plans, overtime, and out-of-hours windows.
4.4 Study steering group: displacing protected windows, reporting exceptions, and rescheduling a validation run.
4.5 An approval covers exactly the run request, quantity, supplier, and options it names. It never selects an option in advance and never extends to a broader record.
"""


SUPERSEDED_SOP = """# Assay Operations SOP AO-014 (2024 edition) — SUPERSEDED

This edition was replaced by v3 on 2026-02-02 and is retained for audit only. Do not apply it.

1. Runs may be sized at the sample count recorded when the study was opened.
2. Minimum remaining dating at scheduling: 7 days.
3. An open supplier order counts toward control coverage; the run may be booked once the order is confirmed.
4. Expedite fees up to USD 500 may be approved by the QA manager at discretion.
5. The analysers run a single 08:00-16:00 block; long validation runs may be split across two days with the operator's agreement.
6. Protected windows may be displaced by the on-shift operator when a study deadline is at risk.
7. One control vial per plate is sufficient for every immunoassay protocol.
"""


__all__ = ["SUPERSEDED_SOP", "effective_sop"]
