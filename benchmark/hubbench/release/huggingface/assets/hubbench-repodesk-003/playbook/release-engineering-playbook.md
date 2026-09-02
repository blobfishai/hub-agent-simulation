# Release Engineering Playbook (v5, effective 2026-03-02)

Applies to Larkspur Systems Release Engineering: the platform monorepo (REPO-PLATFORM), the infra image repository (REPO-INFRA), the release verification pipeline (CI-MAIN), the external certification partners, and the three release lanes. This version supersedes the 2024 playbook in full.

## 1. Fix requirement

1.1 The affected-module count of a regression is the most recent final impact analysis for the component in the SCM impact register. A stale impact analysis is never used.
1.2 Modules whose offending commit has already been reverted on the release branch, or whose change is behind a disabled feature flag, are gated and drop out of the requirement; every other touched module needs its release gate.
1.3 The gate class of the touched modules fixes the required check runs per module; the protected-branch rule names the checks. Runs are counted per module per environment in scope.
1.4 Dedicated-tenant cutovers inside 7 days: the gate runs on both the shared pipeline and the dedicated-tenant pipeline before the change is booked. An open partner certification is not a substitute for imported results.
1.5 A booked change may be advanced by up to 7 days with the change owner's written note.

## 2. Usable evidence

2.1 A verification-result set counts toward coverage only when its status is PASSED, it is not held for a named issue, it comes from a release-eligible source, and it stays valid for at least the class minimum (14 days from the planning date). On a planning date of 2026-05-04, result sets whose validity ends on or before 2026-05-18 are inside the expiry horizon and do not count.
2.2 Failed, quarantined, and incident-flagged result sets are never reused for a release gate. Reuse requires the director of engineering, and the change advisory board where a release exception is involved.
2.3 Partner-certified runs are imported and re-verified into the release evidence on the next business day after the partner's ready date.
2.4 Order sizing: order the uncovered requirement plus the class re-run margin from the margin table. Backports carry only eligible commits (merged, not reverted, not embargoed, not docs-only) and only the commits the target branch is missing.

## 3. Release lanes

3.1 Lane windows are AM 08:00-12:00 and PM 13:00-17:00, Monday to Friday, with release engineering on shift. A change of up to 4 hours including the canary bake occupies one window; a longer change requires both windows of one lane on one day.
3.2 Protected windows (release-freeze verification, compliance batches, customer blackouts) and blocked windows (cluster or deploy-controller maintenance) are never displaced without the change advisory board.
3.3 Two short changes of the same class (2 hours or less each, including the bake) may be sequenced in one window.
3.4 Dedicated-tenant cutover rehearsals are one continuous run on a tenant-isolation-capable lane per the roster; they may not be split across windows on different days.
3.5 Out-of-hours, weekend, and overtime windows require the SRE lead's separate approval.

## 4. Authority

4.1 Release engineering manager: certification orders, backports, and lane bookings within the signed approval's run count, partner, and spend, including any expedite fee the approval names.
4.2 Director of engineering: expedited certification not named in an approval, expedited-review exceptions, validity extensions for expiring result sets, and reuse of failed or incident-flagged result sets.
4.3 SRE lead: lane re-home plans, overtime, and out-of-hours windows.
4.4 Change advisory board: displacing protected windows, release exceptions, and rescheduling a customer cutover.
4.5 Bypassing a required check is never supported, whatever the approval. An approval covers exactly the issue, quantity, partner, and options it names. It never selects an option in advance and never extends to a broader record.

---
Evidence-room mount: repodesk-003 / SHIP-0003.
