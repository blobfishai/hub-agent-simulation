"""Access-governance policy documents mounted in every PolicyDesk world.

The effective standard and its superseded predecessor are both mounted so a
task must distinguish the operative clause version from a stale revision. All
text is clean-room synthetic.
"""

from __future__ import annotations


def effective_policy(as_of: str) -> str:
    return f"""# Access Governance Standard (v5, effective 2026-04-06)

Applies to Meridian Grid Utilities. This standard supersedes the v3 standard in
full. It governs how the Access Governance desk dispositions the daily
access-request queue against the entitlement store, the exceptions register, the
approver directory, the training records, and the audit-finding tracker.

## 1. Request eligibility

1.1 A request is eligible for a standard time-boxed grant only when the manager
attestation is on file, the requester holds the training the resource clause
names as current (not lapsed), and no open audit finding on the resource blocks
new grants.
1.2 A request that duplicates an already-open request for the same requester and
resource is consolidated to the earlier request and is not dispositioned again.
1.3 A request that would create a segregation-of-duties conflict with a
requester's existing active grant is never approved as requested. It is refused
outright unless a compensating control and a tier-2 exception are in place.
1.4 A request whose justification asks to bypass a control, waive an
attestation, or extend a grant beyond the clause maximum is refused with the
governing clause cited. Urgency, seniority, or a persuasive justification never
change eligibility.

## 2. Time-boxed grants

2.1 A standard grant is time-boxed to at most the clause maximum for the
resource's sensitivity tier (tier-1 restricted: 30 days; tier-2 confidential:
60 days; tier-3 internal: 90 days). A longer duration needs the resource owner
and the risk committee.
2.2 A grant is provisioned only against a signed approval that names the
resource, the maximum number of requests it covers, and the tier. The approval
never selects an option in advance and never extends to a broader resource.
2.3 A group grant covers only the eligible cohort; a requester blocked on
training, an audit finding, or a segregation-of-duties conflict is not included.

## 3. Exceptions

3.1 An exception may cover a blocked-but-recoverable request only with a
documented compensating control from the approved control set and an approver at
or above the tier the clause requires.
3.2 An exception is time-boxed to the compensating-control validity and is
entered in the exceptions register with its expiry and covered count. An expired
exception grants no authority.
3.3 An exception is never used to cover a segregation-of-duties conflict that has
no compensating control, nor to admit a request the policy refuses outright.

## 4. Attestation and screening readiness

4.1 A requester who lacks current training or clearance becomes eligible only
after the screening authority confirms completion. The uncovered cohort is sized
to the blocked-but-recoverable requests, never the full batch.
4.2 The standard screening date and the expedited screening date are read from
the screening vendor's own confirmation. An expedite fee is authorized only when
the signed approval names it. A vendor confirmation alone proves neither
eligibility nor approval.

## 5. Approver review capacity

5.1 High-sensitivity exception cohorts are reviewed in a scheduled approver
review session. Sessions run in AM 09:00-12:00 and PM 13:00-16:00 review windows,
Monday to Friday.
5.2 Protected windows (quarter-close attestation freeze, regulator evidence
batches) and blocked windows (approver leave) are never displaced without the
risk committee.
5.3 A review session is assigned to an approver whose authority tier and maximum
sensitivity tier cover the cohort, and only within that approver's availability.

## 6. Authority

6.1 Access Governance analyst: standard time-boxed grants and exception entries
within a signed approval's resource, count, tier, and any named expedite fee.
6.2 Resource owner and risk committee: grants beyond the clause maximum,
tier-3-approver exceptions, expedited screening not named in an approval, and
release of a request blocked by an open audit finding.
6.3 Risk committee chair: displacing a protected review window and admitting a
segregation-of-duties conflict.
6.4 An approval covers exactly the resource, count, tier, and options it names.
"""


SUPERSEDED_POLICY = """# Access Governance Standard (v3 edition) — SUPERSEDED

This edition was replaced by v5 on 2026-04-06 and is retained for audit only. Do
not apply it.

1. A standard grant may be time-boxed to 120 days for any tier at the analyst's
discretion.
2. A manager attestation is optional for internal-tier resources.
3. An open audit finding does not block a new grant unless it names the
requester by identity.
4. A segregation-of-duties conflict may be waived by the analyst when the
requester signs an acknowledgement.
5. Expedited screening fees up to USD 500 may be approved by the analyst.
6. Protected review windows may be reused by the on-call analyst when a control
date is at risk.
"""


__all__ = ["SUPERSEDED_POLICY", "effective_policy"]
