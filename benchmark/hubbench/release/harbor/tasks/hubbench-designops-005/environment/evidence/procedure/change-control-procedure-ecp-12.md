# Engineering Change Control Procedure ECP-12 (rev 5, effective 2026-03-02)

Applies to Ashgrove Motion Systems engineering change orders (ECOs) cut in at the Ashgrove main plant (PLANT-ASH), the Kelbrook satellite plant (PLANT-KEL), and the Ashgrove tool room (PLANT-TR). This revision supersedes ECP-12 rev 3 (2024) in full.

## 1. Change scope

1.1 The affected assemblies of an ECO are the where-used parents of the changed component at RELEASED parent revisions in the live PLM. Parent revisions that are SUPERSEDED or OBSOLETE, alternate lines, phantom lines, and lines whose effectivity has ended are out of scope. A where-used export or an annual BOM report is never the scope of record.
1.2 A Class I change alters form, fit, function, or a certified interface. A Class II change is documentation, material-equivalence, or process only and alters no certified interface.
1.3 The affected-item list on the ECO must agree with the live where-used at RELEASED parent revisions; a disagreement is resolved in favour of the live PLM.
1.4 A cut-in may be advanced by up to 7 days from its booked date with the change owner's written note.

## 2. Certified configurations

2.1 A certified configuration counts toward coverage only while its register status is ACTIVE. EXPIRED, SUPERSEDED, and WITHDRAWN certificates cover nothing.
2.2 A Class I change on a component listed in a certificate's covered components invalidates that certificate for the new revision. A Class II change invalidates nothing. A certificate that does not list the changed component survives the change.
2.3 Re-certification is performed by an accredited laboratory against the laboratory's quoted slot. The certification office issues the updated certificate on the next business day after the laboratory report date. An open laboratory order is not a certificate.
2.4 An invalidated configuration may not be released without re-certification. An interim release under a certified-configuration exception (deviation) requires the change control board chair and the customer notification the deviation names.

## 3. Tooling

3.1 A fixture-set lot counts toward tooling coverage only when its status is CALIBRATED, it is not reserved for a named change, it is not flagged in the register as built to a superseded revision or outside the current calibration bulletin, and it retains at least the family minimum remaining calibration (14 days from the planning date). On a planning date of 2026-05-11, lots whose calibration is due on or before 2026-05-25 are inside the calibration-due horizon and are not usable.
3.2 Supplier-built sets are received, inspected, and calibration-checked; they release to the line on the next business day after the supplier's ready date. Transferred sets ride the evening inter-plant shuttle and release at the receiving plant on the next business day after the scheduled transfer date.
3.3 Order sizing: order the uncovered requirement plus the spare margin from the spare-set policy. Inter-plant transfers move releasable lots only and cover only the receiving plant's uncovered quantity; the receiving plant's own releasable sets are used first.
3.4 Sets required for a cut-in are the fixture family's sets per station multiplied by the station count on the current line roster.

## 4. Release calendar

4.1 Cut-in windows are AM 07:00-11:00 and PM 12:00-16:00, Monday to Friday. A cut-in run (first-article inspection plus changeover) of up to 4 hours occupies one window; a longer run requires both windows of one line on one day.
4.2 Protected windows (customer audit freeze, month-end build freeze, compliance batch) and blocked windows (line maintenance, safety validation) are never displaced without the change control board.
4.3 Two short cut-ins of the same change (2 hours or less each including changeover) may be sequenced in one window.
4.4 A Class I first-article inspection is one continuous run on a CMM-capable line per the line roster; it may not be split across windows on different days.
4.5 Second-shift, weekend, and overtime windows require the manufacturing engineering lead's separate approval.

## 5. Authority

5.1 Configuration manager: supplier-portal orders (fixture builds and laboratory slots) within the signed approval's quantity, supplier, and spend, including any expedite fee the approval names; ECO release with an effectivity date inside the approved window.
5.2 Director of engineering: expedited service not named in an approval, inter-plant transfers and direct builds outside an approval, calibration-due extensions, certificate-validity extensions, and use of calibration-failed or bulletin-excluded sets.
5.3 Manufacturing engineering lead: line re-home plans, overtime, and second-shift windows.
5.4 Change control board (chair): displacing protected windows, certified-configuration exceptions, and rescheduling a cut-in series.
5.5 An approval covers exactly the change, quantity, supplier, and options it names. It never selects an option in advance and never extends to a broader record.

---
Evidence-room mount: designops-005 / DSGN-0005.
