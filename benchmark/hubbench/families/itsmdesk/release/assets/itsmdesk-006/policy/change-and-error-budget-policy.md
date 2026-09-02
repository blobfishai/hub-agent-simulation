# Change and Error-Budget Policy (v3, effective 2026-02-01)

Applies to Brightmoor Commerce Service Operations: every production service in the CMDB, the change lanes on the change calendar, the SLOs published in telemetry, and the on-call schedules. This version supersedes the 2024 policy in full. Planning date for this room: 2026-04-14.

## 1. Sizing a change

1.1 Planned downtime = restarts required by the vendor advisory x the service's current restart-to-healthy metering (RESTART-MIN, most recent final metering in the CMDB) + the service runbook's post-change validation minutes. A vendor's own downtime estimate is never the figure of record. A stale metering is never used.
1.2 The planned interval of a change (planned start to planned end) is the planned downtime plus the service runbook's rollback reserve, starting at the window start.
1.3 Rolling node patches drain one node at a time and consume no error budget; each node takes the current DRAIN-MIN metering, so a window fits floor(window minutes / DRAIN-MIN) nodes.
1.4 A planned-outage notice covers the planned downtime plus the rollback reserve; the notice length is the figure customer communications publish.
1.5 A certificate rotation or model-runtime patch reserves the whole window: no other change shares it.
1.6 Coverage for a tier-1 change is the change window plus a two-hour post-change watch by a secondary responder holding the service's runbook certification.

## 2. Error budget

2.1 Each service's availability SLO carries a whole-minute budget for its rolling window, as published in telemetry. The rolling window ends on the evaluation day and excludes incidents opened on or before the day exactly one window earlier.
2.2 Budget consumed = the sum of charged impact minutes of incidents in the window. Only incidents the problem review left charged count; an incident the review reclassified as not customer-impacting is not charged. Raw SLI burn in telemetry is informational and never the governing figure.
2.3 Spendable budget = budget - consumed - the SLO's reserve floor. Planned downtime (or a planned-outage notice) may be scheduled on a day only if it fits inside the spendable budget on that day; otherwise the change waits for the window to roll or needs a budget exception from the change board chair.
2.4 While the remaining budget (budget - consumed) is below half the window budget, a rolling batch may not exceed half of the service's active nodes on the lane, rounded down.

## 3. Change windows

3.1 Sessions are NIGHT 01:00-05:00 and EVE 19:00-23:00 on every calendar day. A change must start and end inside one session of one lane.
3.2 Lanes with the weekday embargo (tier-1 lanes) accept standard changes in weekend sessions only; weekday sessions are protected and an embargo exception needs the change board chair.
3.3 Freeze windows on the freeze register (financial close, audit evidence, peak trading, vendor maintenance) protect every session they cover on the lanes they name; a freeze exception needs the authority the register names.
3.4 A lane whose deployment runner is suspended accepts no change until its return date; re-laning a change onto another lane requires that lane to be certified for the service's tier.
3.5 Nodes pinned for a named canary or drill are never patched before the pin ends; nodes on another lane are patched through that lane's own windows.
3.6 A multi-pool model-runtime patch runs one pool per day with drift monitoring between pools; two pools in one night need the risk lead and the change board.
3.7 A tier-1 change window is eligible only when a certified secondary responder is on the service's secondary schedule (rotation or override) for the whole coverage block of 1.6.

## 4. Vendor packages

4.1 A vendor package is production-eligible on the next business day after its release date, once the canary soak passes. Standard release dates and early-access (expedited) dates come from the vendor advisory; a superseded advisory revision must not be used.
4.2 Early-access packages carry the premium-support fee printed on the advisory; the fee needs the security lead unless a signed approval names it.
4.3 Remediation is due within the advisory's remediation SLA (days from publication). A deferral past the SLA needs the security lead.

## 5. Authority

5.1 Change manager: standard changes inside a signed approval's record, lane, windows, batch cap, and spend.
5.2 Change board chair: embargo exceptions, freeze exceptions, budget exceptions, and any emergency change.
5.3 SRE lead: on-call overrides and override premiums; suspended-lane returns.
5.4 Security lead: early-access fees not named in an approval and SLA deferrals; risk lead with the change board for pool sequencing exceptions.
5.5 An approval covers exactly the record, lane, windows, quantity, engineer, and fees it names. It never selects an option in advance and never extends to a broader record.

---
Evidence-room mount: itsmdesk-006 / SVCOPS-0006.
