# Platform Operations Runbook (v4, effective 2026-02-02)

Applies to Ridgeline Systems Platform Operations: the nearline artifact store (STORE-NEAR), the Drayton DR object store (STORE-DR), the release staging store (STORE-STAGE), and the release build farm. This version supersedes the 2024 runbook in full.

## 1. Recovery requirement

1.1 Metered payloads (release bundle size, daily log volume) are sized at the most recent final metering for the service in the CMDB. A stale metering is never used.
1.2 Tiered rehearsals use the rehearsal tier table at the current measured dataset size.
1.3 Archive segments are immutable fixed-size objects. Every payload rounds up to whole segments; partial segments are never retrieved or copied.
1.4 Release trains with a rollback gate within 7 days: both the release bundle and the rollback baseline bundle must be fully staged and verified before the train's verification run is scheduled. An open vendor retrieval is not a substitute for staged segments.
1.5 A scheduled verification or rehearsal run may be advanced by up to 7 days with the change owner's written note.

## 2. Restorable sources

2.1 A segment set counts toward coverage only when its status is VERIFIED, it is not reserved for a named ticket or legal hold, and it retains at least the class minimum remaining retention (14 days from the planning date). On a planning date of 2026-04-13, sets whose retention expires on or before 2026-04-27 are inside the purge-queue horizon and are not restore-eligible.
2.2 Checksum-failed, scrub-flagged, and durability-uncovered sets are never staged for release or evidence work. Release requires the infrastructure director, and the change board where a release exception is involved.
2.3 Vendor-retrieved and DR-copied segments are checksum-verified and released to the staging store on the next business day after the retrieval-ready or copy date.
2.4 Retrieval sizing: retrieve the uncovered requirement plus the class retrieval margin from the margin table. Inter-store copies move releasable sets only and cover only the receiving store's uncovered quantity.

## 3. Build-farm windows

3.1 Release-farm windows are AM 08:00-12:00 and PM 12:30-16:30, Monday to Friday, with operations coverage on shift. A run of up to 4 hours including verification occupies one window; a longer run requires both windows of one runner on one day.
3.2 Protected windows (release-freeze verification, compliance batches) and blocked windows (hypervisor or firmware maintenance) are never displaced without the change advisory board.
3.3 Two short runs of the same job class (2 hours or less each, including verification) may be sequenced in one window.
3.4 Regulated restore rehearsals are one continuous run on an isolation-capable runner per the roster; they may not be split across windows on different days.
3.5 Out-of-hours, weekend, and overtime windows require the SRE lead's separate approval.

## 4. Authority

4.1 Release engineering manager: restore jobs and retrievals within the signed approval's segment count, vendor, and spend, including any expedite fee the approval names.
4.2 Infrastructure director: expedited retrieval not named in an approval, cross-site DR copies and direct retrievals outside an approval, retention extensions and purge-queue overrides, and release of checksum-failed or durability-uncovered sets.
4.3 SRE lead: runner re-home plans, overtime, and out-of-hours windows.
4.4 Change advisory board: displacing protected windows, release exceptions, and rescheduling a release train.
4.5 An approval covers exactly the ticket, quantity, vendor, and options it names. It never selects an option in advance and never extends to a broader record.

---
Evidence-room mount: hostops-002 / HOST-0002.
