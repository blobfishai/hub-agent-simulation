# Credential Compromise Containment Playbook (v5, effective 2026-03-02)

Applies to Kestrel Grid Utilities Security Operations: the workforce identity tenant on Halyard Identity Cloud (TENANT-PRIMARY), the Brindle cloud key registry, the EDR host estate, and the responder on-call roster. This version supersedes the 2024 playbook in full. Every action in this playbook is defensive: it concerns the organisation's own credentials and hosts.

## 1. Containment requirement

1.1 A confirmed credential compromise is sized at the most recent final inventory snapshot for the identity in the IAM register (live app grants, live access keys, or live federated sessions). A stale snapshot is never used.
1.2 Linked-principal rule: when a human identity is confirmed compromised, every service principal it owns or can impersonate is in scope; when a shared device is the pivot, every principal that signed in from it inside the alert window is in scope. Principals in scope are counted from the ticket, not inferred from the alert title.
1.3 Credential objects are immutable revocation units. A grant, key, or session is revoked whole; partial revocation of an object is not a state the tenant supports.
1.4 Tier T2-CONFIRMED (confirmed compromise, corroborated by SIEM correlation and the detection rule version in force): live objects the tenant can revoke are revoked without waiting for the owner. Objects the tenant cannot revoke itself (federated tokens, provider-issued keys) are covered by the identity-provider or key-custody vendor's invalidation job.
1.5 Tier T1-SUSPECTED (single-signal, uncorroborated): revocation waits for the owner's confirmation inside the tier SLA; the owner review is booked on a qualified responder window. A responder review may be advanced by up to 5 business days with the owner's written note.
1.6 Only detection rules in status ENABLED at the alert time count as corroboration. A rule version retired before the alert, or a duplicate alert raised by a suppressed rule, is context only.

## 2. Revocable objects

2.1 An object in the IAM register counts as tenant-revocable only when its status is ACTIVE and it is not deferred for a named owner ticket. Objects already EXPIRED, REVOKED, ROTATED, or DISABLED do not count, and neither do objects flagged in the register as owner-held.
2.2 Objects issued by the identity provider (federated session tokens, provider-issued signing keys) are invalidated only through the vendor's tenant-wide invalidation job. A vendor confirmation quotes a standard job date and an expedited job date; the invalidation is verified and reflected in the register on the next business day after the job date.
2.3 Invalidation sizing: order the uncovered requirement plus the class token-family margin from the margin table. Tenant revocations cover only ACTIVE unreferenced objects and only the receiving scope's uncovered quantity.
2.4 Vendor or tenant revocation of an object never selects a containment tier; the tier comes from the corroboration rule in §1.

## 3. Responder windows

3.1 Responder review windows are AM 08:00-12:00 and PM 12:30-16:30, Monday to Friday, with SOC coverage on shift. A review of up to 4 hours including owner confirmation occupies one window; a longer review requires both windows of one responder on one day.
3.2 Protected windows (major-incident bridges, regulator evidence sessions, change-freeze reviews) and blocked windows (identity-platform maintenance, tabletop exercises) are never displaced without the change advisory board.
3.3 Two short reviews of the same tier (2 hours or less each including owner confirmation) may be sequenced in one window.
3.4 A T2 containment review for a privileged principal is one continuous session on a Tier-2-qualified responder per the roster; it may not be split across windows on different days.
3.5 Out-of-hours, weekend, and overtime responder windows require the on-call lead's separate approval.

## 4. Authority

4.1 SOC manager: vendor invalidation orders and tenant revocations within the signed approval's object count, vendor, class, and spend, including any expedite fee the approval names.
4.2 Chief information security officer: expedited invalidation not named in an approval, tenant-wide sign-out or key-registry rollover outside an approval, revocation of objects deferred for an owner ticket, and revocation of owner-held or register-flagged objects.
4.3 On-call lead: responder re-home plans, overtime, and out-of-hours windows.
4.4 Change advisory board: displacing protected windows, containment exceptions, and moving a regulator evidence session.
4.5 An approval covers exactly the ticket, object count, vendor, and options it names. It never selects an option in advance and never extends to a broader identity.

---
Evidence-room mount: secops-004 / SEC-0004.
