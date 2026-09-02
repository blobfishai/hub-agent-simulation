# hubbench-workplace-002 — Settle the Tamsin & Vale SLA credit claim for the release week

HubBench 1.1.0 · family **Workplace** (`workplace`, cluster `customer-workplace-agents`) · decision mode `quantity` · role `customer_delivery_coordinator` · as of 2026-04-14.

Customer-escalation delivery decisions against a helpdesk with SLA policies, a delivery tracker with sprints and capacity reports, a versioned wiki standard, a staff calendar with leave and on-call, an HRIS skills roster, a contract register with commitments and a credit ledger, counterparty confirmations, and approval records.

## What the agent gets

The agent works as a non-root user in the `main` container and reaches the isolated, stateful world only through its public surfaces on the `world` service:

- MCP over streamable HTTP, one endpoint per server: `http://world:8765/mcp/<server>`
- the terminal `tool` CLI (`tool list`, `tool schema <name>`, `tool <name> '<json>'`), bound to the same world through `HUBBENCH_URL`
- the REST API under `http://world:8765/api/v1/`
- the web console at `http://world:8765/`

Servers mounted for this task:

- `approvals` — Approval workflow records with exact scope. (2 tools)
- `calendar` — Staff calendar: AM/PM blocks, leave, on-call shifts, and customer-facing session bookings. (7 tools)
- `chat` — Customer Delivery chat threads. (2 tools)
- `contracts` — Contract register: agreements, customer commitments, the credit ledger, and billing runs. (7 tools)
- `drive` — Shared drive holding the standard, exports, registers, calendars, and confirmations. (3 tools)
- `helpdesk` — Customer support desk: customer accounts, tickets with SLA timelines, escalations, and SLA policies. (7 tools)
- `hris` — HRIS roster: employees, contractors, and certified skill levels. (3 tools)
- `mail` — Customer Delivery mailbox. (2 tools)
- `notes` — Stakeholder draft notes (never sent by the benchmark). (1 tools)
- `portal` — Counterparty portal: partner staffing confirmations, customer change-window confirmations, and customer billing-run confirmations. (2 tools)
- `tracker` — Delivery tracker: issues, sprints, and planning-time capacity reports. (6 tools)
- `wiki` — Team wiki: the Escalation Handling Standard and its version history. (3 tools)
- `hubbench` — Benchmark-only discovery and structured answer submission controls. (2 tools)

Evidence files under `/workspace/evidence` (35 files):

- `approvals/approval-AP-WP-0102.json` — Approval record AP-WP-0102 (application/json)
- `approvals/decision-record.json` — Decision control record — WORK-0002 (application/json)
- `audit/evidence-index.yaml` — Evidence index (application/yaml)
- `audit/evidence-status.yaml` — Evidence readiness — WORK-0002 (application/yaml)
- `audit/system-audit.log` — System audit log — WORK-0002 (text/plain)
- `calendar/leave-and-oncall.csv` — Approved leave and on-call shifts (text/csv)
- `calendar/staff-calendar-2026-04-14.xlsx` — Staff calendar blocks, four weeks from 2026-04-14 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `chat/CHAT-1002.json` — WORK-0002 Tamsin & Vale credit claim (application/json)
- `collaboration/operations-thread.json` — Operations thread — WORK-0002 (application/json)
- `communications/source-request.eml` — Source integrity request — WORK-0002 (message/rfc822)
- `contracts/agreement-AGR-7735.json` — Agreement AGR-7735 with commitments (contract register export) (application/json)
- `contracts/commitment-register-AGR-7735.csv` — Customer commitment register (text/csv)
- `contracts/credit-ledger-AGR-7735.csv` — Credit ledger (gross) (text/csv)
- `contracts/provider-contracts.json` — Provider contract — WORK-0002 (application/json)
- `contracts/sla-credit-schedule-enterprise-plus.md` — SLA credit schedule — Enterprise Plus (extract) (text/markdown)
- `controls/current-authority.md` — Current authority — WORK-0002 (text/markdown)
- `controls/retired-authority.md` — Retired authority — WORK-0002 (text/markdown)
- `controls/source-integrity.pdf` — Source integrity control — WORK-0002 (application/pdf)
- `customer/tamsin-vale-credit-claim-2026-04-06.pdf` — Tamsin & Vale credit claim letter (2026-04-06) (application/pdf)
- `exports/live-snapshot.json` — Live pre-action snapshot — WORK-0002 (application/json)
- `exports/starting-state-workplace-002.json` — Starting-state export (escalation, bookings, credit ledger) (application/json)
- `helpdesk/escalation-ESC-3118.json` — Escalation ESC-3118 (helpdesk export) (application/json)
- `helpdesk/sla-policy-SLA-PLUS-2026.csv` — SLA policy SLA-PLUS-2026 targets (text/csv)
- `helpdesk/ticket-TCK-88301.json` — Ticket TCK-88301 (helpdesk export) (application/json)
- `helpdesk/ticket-TCK-88312.json` — Ticket TCK-88312 (duplicate of TCK-88301) (application/json)
- `hris/squad-roster-and-skills.csv` — Squad roster with certified skill levels (text/csv)
- `lineage/record-lineage.csv` — Cross-system record lineage — WORK-0002 (text/csv)
- `mail/THR-1002.eml` — WORK-0002 Tamsin & Vale credit claim — answer before the May invoice (message/rfc822)
- `portal/confirmation-TV-AP-51022.pdf` — Counterparty confirmation TV-AP-51022 (application/pdf)
- `provenance/harbor-open-source-anchors.json` — Open-source benchmark provenance — Workplace (application/json)
- `standards/escalation-handling-standard-v4-superseded.md` — Escalation Handling Standard v4 (superseded) (text/markdown)
- `standards/escalation-handling-standard-v5.md` — Escalation Handling Standard v5 (effective) (text/markdown)
- `tracker/linked-issues-ESC-3118.csv` — Tracker issues linked to ESC-3118 (text/csv)
- `tracker/sprint-capacity-SPR-27.xlsx` — Sprint capacity report SPR-27 (planning-time) (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `workbooks/review-capacity.xlsx` — Review capacity — WORK-0002 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)

## How it is graded

The verifier runs as root after the episode, pulls the finished world over a token-gated, read-only channel that the agent user cannot open, and computes **HubScore** (0–1 reward = score / 100) from executable checks only: required investigations before the first write, provider payload assertions, post-write readbacks, write containment, exact graded answer fields, and semantic milestone aggregation (70 atomic criteria, 26 graded answer fields). No LLM judge is called. Exact call order is not graded.

The sealed contract, expected answer, and oracle policy live only in `tests/` and `solution/`; they are not present in either container image.

## Provenance

Clean-room synthetic data; no real patient, employee, supplier, or organisation is represented. Public Harbor Hub anchors for this family (evaluation-shape inspiration only):

- TheAgentCompany: `theagentcompany/theagentcompany` — evaluation-shape inspiration only; clean-room task, state, tools, and answer
- tau3-bench: `sierra-research/tau3-bench` — evaluation-shape inspiration only; clean-room task, state, tools, and answer
- MMAU: `apple/mmau` — evaluation-shape inspiration only; clean-room task, state, tools, and answer
- BFCL: `gorilla/bfcl` — evaluation-shape inspiration only; clean-room task, state, tools, and answer

More: https://blobfish.ai/benchmarks/hubbench
