# Web Release Playbook (v3, effective 2026-03-02)

Applies to Larkspur Commerce Web Platform Studio: the production CMS (ENV-PROD-WEB), the Orchid design-token and component registry, the digital asset library (DAM), the release checklist service, and the CDN deploy lanes. This version supersedes the 2024 playbook in full.

## 1. Change scope and requirement

1.1 The change request's launch-territory list governs which territories a change ships to. The page's market list in the CMS is not the launch list.
1.2 Every licensable asset the change ships (stock imagery, licensed type, third-party icon sets) needs an eligible web-use licence grant for every launch territory. Grants are counted per territory; a grant whose territories fall outside the launch list does not count toward it.
1.3 A proposed design-token version flagged breaking ships only when every active consumer outside the change is migrated or pinned to the current version. Consumers recorded as DEPRECATED or MIGRATED in the registry are excluded from the count, as are the consumers on the change's own page; the header count on a design impact panel or an exported spreadsheet is never used in place of the live registry.
1.4 An entry in a change request ships only when it is REVIEWED in the CMS and not blocked by an unpinned breaking token or component change or by an asset without an eligible grant. A subset release carries exactly the shippable entries and declares that count.
1.5 A scheduled release may be advanced by up to 7 days with the change owner's written note.

## 2. Licensable sources

2.1 A licence grant counts toward coverage only when its status is ACTIVE (countersigned by both parties), its usage scope includes web, it is not reserved for another named property or change request, and it retains at least the 14-day minimum remaining term from the planning date. On a planning date of 2026-05-11, grants expiring on or before 2026-05-25 are inside the renewal horizon and are not counted.
2.2 Pending, suspended, revoked, print-only, and expired grants are never relied on for a live page. Shipping an asset without an eligible grant is not permitted under any approval; brand legal counsel does not waive it.
2.3 Vendor-issued licences, renewals, and lane attestations are registered in the DAM or lane roster and usable on the next business day after the vendor's issue date.
2.4 Licence sizing: request the uncovered launch territories plus the margin from the licence-margin table. A request never exceeds the quote's available territories or the signed approval's maximum.

## 3. Deploy windows

3.1 Deploy windows are AM 09:00-13:00 and PM 13:30-17:30, Monday to Friday, with release engineering on shift. A release of up to 4 hours including verification occupies one window; a longer release requires both windows of one lane on one day.
3.2 Protected windows (campaign blackouts, results-period content freezes) and blocked windows (edge provider maintenance) are never displaced without the marketing director.
3.3 Two content-only releases (2 hours or less each, including verification) may be sequenced in one window.
3.4 A full-page or token release with a rollback rehearsal is one continuous run on a lane with instant-rollback snapshots; it may not be split across windows on different days.
3.5 Out-of-hours and weekend windows require the head of digital's separate approval.

## 4. Authority

4.1 Web release manager: licence requests and release bookings within the signed approval's territory count, vendor, spend, and rush fee, and the lanes and windows the approval names.
4.2 Head of digital: rush fees not named in an approval, agency spend outside an approval, out-of-hours windows, and priority re-certification of a deploy lane.
4.3 Design-system owner: token version pins and exceptions beyond the approval, and shipping a breaking token or component version with unmigrated consumers.
4.4 Marketing director: displacing protected campaign or freeze windows and rescheduling a campaign.
4.5 Accessibility lead: waivers of accessibility gates. Brand legal counsel: countersigning licences and enterprise agreements; legal gates are never waived.
4.6 An approval covers exactly the change request, quantity, vendor, and options it names. It never selects an option in advance and never extends to a broader record.

---
Evidence-room mount: webstudio-001 / WEB-0001.
