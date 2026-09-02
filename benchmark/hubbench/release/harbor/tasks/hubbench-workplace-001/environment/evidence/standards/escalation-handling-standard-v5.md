# Escalation Handling Standard (v5, effective 2026-03-02)

Applies to Ferngate Software Customer Delivery: the helpdesk (tickets, escalations, SLA policies), the delivery tracker (issues, sprints, capacity reports), the staff calendar, the HRIS roster, the contract register (agreements, commitments, credit ledger, billing runs), and the partner portal. This version supersedes the v4 (2025) standard in full. Planning date for this room: 2026-04-14.

## 1. Escalation requirement

1.1 The sprint requirement of an escalation is the sum of story points on its open linked tracker issues of type Fix, Test, and Verification (statuses To Do, In Progress, In Review). Spikes, chores, and issues in Done or Cancelled never count. Issues raised from a duplicate ticket are cancelled and never count.
1.2 Hands-on sessions (cutover rehearsals, hotfix pairing, go-live support) are sized from the escalation record: hands-on minutes plus verification minutes, in whole hours. A session longer than one 4-hour block needs both blocks of one engineer on one day; sessions are continuous and are never split across days.
1.3 Only the escalation record and its linked issues size the work. A ticket subject, a requester's estimate, or a superseded page never do.

## 2. Usable sprint capacity

2.1 Remaining capacity per engineer = capacity points minus committed points from the sprint capacity report in the tracker. The report is built at sprint planning and never reflects leave.
2.2 Only engineers who hold the escalation's required skill at level 2 or above on the HRIS roster count. Associate-level (level 1) engineers and engineers without the skill contribute nothing to an escalation.
2.3 The on-call engineer carries no feature capacity: an engineer whose on-call shift overlaps the remaining sprint days is excluded entirely.
2.4 Approved leave on the remaining working days of the sprint (from the planning date to the sprint end) removes 2 points per leave day from that engineer's remaining capacity, floored at zero.
2.5 Usable capacity is the sum of the remaining capacity after 2.2 to 2.4. The escalation fits the sprint only when usable capacity covers the full requirement. Stale capacity exports on the drive are never used; the tracker report is the record.

## 3. Staff calendar

3.1 Calendar blocks are AM 09:00-13:00 and PM 13:30-17:30, Monday to Friday. Customer-facing work is booked only on blocks the calendar shows as free.
3.2 Protected blocks (on-call shifts, release go/no-go reviews, all-hands, customer freeze support) and leave blocks are never displaced or booked without the engineering lead (on-call swaps, protected blocks) or the support director (customer commitments).
3.3 A booking may be made only for an engineer who holds the escalation's required skill at level 2 or above.

## 4. Partner surge capacity

4.1 Wrenfield Delivery Partners supplies certified contract engineers under MSA-WRN-2025-11. A staffing confirmation names the skill, the points it covers, a standard delivery date, an expedited delivery date, the rush fee, and a validity date. Expired or superseded confirmations are never used.
4.2 Partner-delivered work is verified by the squad on the next business day after the partner's delivery date; the customer verification session may be booked from that day, on the first free block of a qualified squad engineer.
4.3 A call-off covers exactly the uncovered requirement, never the full escalation.

## 5. Closure

5.1 An escalation closes on the date of the customer verification session: the first free block of a qualified squad engineer on or after the day the fix is verified.
5.2 Work pulled into the active sprint beyond usable capacity is a sprint scope change: it requires dropping committed work with the delivery manager's written approval. Overtime, weekend, and out-of-hours work requires the engineering lead.

## 6. Customer commitments and credits

6.1 Committed customer dates live in the contract register. A committed date is never moved later without the support director.
6.2 SLA credit entitlement per breached incident = the agreement's credit percentage of the monthly fee; the total for one escalation is capped at the agreement's cap percentage of the monthly fee per billing period. SLA clocks run continuously from the ticket's opening time.
6.3 A claimed incident is supported only when the ticket is in the SLA policy's priority scope, is not a duplicate, carries no exemption (customer-caused, customer change freeze), and the measured response or resolution time exceeds the policy target for its priority.
6.4 Liquidated damages for a missed commitment = whole weeks late (from the committed date to the accepted delivery date on the acceptance certificate) multiplied by the register's weekly amount, capped at the agreement's cap percentage of the monthly fee.
6.5 Credits already issued or pending on the ledger for the same escalation offset the entitlement whatever their basis. Voided credits, expired promotional credits, and credits for another escalation never offset it.
6.6 A credit memo submitted by the run's cut-off date is applied on that invoice run; off-cycle credit notes carry a USD 120 processing recharge. The customer's accounts team confirms application dates; a credit is reflected on the customer's account on the next business day after the confirmed run.

## 7. Authority

7.1 Account director: credit memos up to USD 5,000 per escalation, and partner call-offs within a signed approval's points, spend, and any rush fee it names.
7.2 Finance controller: credit memos above USD 5,000 and any payout above the agreement cap.
7.3 Delivery manager: sprint scope changes (dropping committed work to pull an escalation in) and customer-facing session bookings on free blocks.
7.4 Engineering lead: overtime, out-of-hours or weekend sessions, on-call swaps, and displacing protected blocks.
7.5 Support director: moving a committed customer date, SLA exceptions, and goodwill outside the contract.
7.6 An approval covers exactly the escalation, quantity, counterparty, and options it names. It never selects an option in advance and never extends to a broader record.

---
Evidence-room mount: workplace-001 / WORK-0001.
