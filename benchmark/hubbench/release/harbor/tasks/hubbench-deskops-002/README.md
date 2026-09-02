# hubbench-deskops-002 — Fund the leadership offsite move from the executive travel line

HubBench 1.3.0 · family **DeskOps** (`deskops`, cluster `computer-use-gui`) · decision mode `quantity` · role `workplace_operations_coordinator` · as of 2026-06-08.

Offsite-move decisions against a mailbox, a calendar with attendee free/busy, a people directory, agenda documents with revisions, a budget workbook with versions, a shared drive, a venue portal with weekly availability, quotes, and holds, a corporate travel desk with policy versions, bookings, group-ticketing confirmations, and booking changes, a budget system with lines and adjustments, and approval records.

## What the agent gets

The agent works as a non-root user in the `main` container and reaches the isolated, stateful world only through its public surfaces on the `world` service:

- MCP over streamable HTTP, one endpoint per server: `http://world:8765/mcp/<server>`
- the terminal `tool` CLI (`tool list`, `tool schema <name>`, `tool <name> '<json>'`), bound to the same world through `HUBBENCH_URL`
- the REST API under `http://world:8765/api/v1/`
- the web console at `http://world:8765/`

Servers mounted for this task:

- `approvals` — Approval workflow records with exact scope. (2 tools)
- `calendar` — Calendar service (Google Calendar shaped): events, attendees, free/busy with hard-conflict flags, rooms. (6 tools)
- `chat` — Workplace-operations chat threads. (2 tools)
- `directory` — People directory: people, teams, home offices, and timezones. (3 tools)
- `docs` — Documents service (Docs shaped): agenda documents with revisions. (4 tools)
- `drive` — Shared drive (Drive shaped) holding policies, registers, calendars, quotes, and exports. (3 tools)
- `expense` — Budget and expense system: budget lines and adjustments. (5 tools)
- `mail` — Workplace-operations mailbox (Gmail / Outlook shaped): messages and threads. (3 tools)
- `notes` — Stakeholder draft notes (never sent by the benchmark). (1 tools)
- `sheets` — Spreadsheet service (Sheets shaped): budget workbooks with versions. (3 tools)
- `travel` — Corporate travel desk: policy versions, bookings, group-ticketing confirmations, and booking changes. (9 tools)
- `venues` — Venue booking portal: venues, weekly availability, quotes, and holds. (8 tools)
- `hubbench` — Benchmark-only discovery and structured answer submission controls. (2 tools)

Evidence files under `/workspace/evidence` (37 files):

- `approvals/approval-AP-DK-0102.json` — Approval record AP-DK-0102 (application/json)
- `approvals/decision-record.json` — Decision control record — DESK-0002 (application/json)
- `audit/evidence-index.yaml` — Evidence index (application/yaml)
- `audit/evidence-status.yaml` — Evidence readiness — DESK-0002 (application/yaml)
- `audit/system-audit.log` — System audit log — DESK-0002 (text/plain)
- `calendar/attendees-EVT-LDR-LIS.csv` — Attendee roster for EVT-LDR-LIS (text/csv)
- `calendar/board-calendar-notice.md` — Board calendar notice — Q2 review moved (text/markdown)
- `calendar/event-EVT-LDR-LIS.json` — Calendar event EVT-LDR-LIS (export) (application/json)
- `calendar/freebusy-required-attendees-2026-06-08.xlsx` — Free/busy blocks of the required attendees, 2026-06-15 to 2026-08-30 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `chat/CHAT-1002.json` — DESK-0002 leadership offsite move (application/json)
- `collaboration/operations-thread.json` — Operations thread — DESK-0002 (application/json)
- `communications/source-request.eml` — Source integrity request — DESK-0002 (message/rfc822)
- `contracts/provider-contracts.json` — Provider contract — DESK-0002 (application/json)
- `controls/current-authority.md` — Current authority — DESK-0002 (text/markdown)
- `controls/retired-authority.md` — Retired authority — DESK-0002 (text/markdown)
- `controls/source-integrity.pdf` — Source integrity control — DESK-0002 (application/pdf)
- `directory/people-directory-export.json` — People directory export (offices and timezones) (application/json)
- `docs/agenda-EVT-LDR-LIS-rev4.md` — Leadership team offsite — agenda (rev 4, current) (text/markdown)
- `expense/budget-line-BL-EXEC-TRV-26H2.json` — Budget line BL-EXEC-TRV-26H2 (export) (application/json)
- `exports/live-snapshot.json` — Live pre-action snapshot — DESK-0002 (application/json)
- `exports/starting-state-deskops-002.json` — Starting-state export (events, holds, changes, adjustments) (application/json)
- `lineage/record-lineage.csv` — Cross-system record lineage — DESK-0002 (text/csv)
- `mail/THR-1002.eml` — DESK-0002 leadership offsite — board meeting collision, fund the move (message/rfc822)
- `policy/events-contingency-table.csv` — Events contingency table by attendee band (policy TE-07 v5) (text/csv)
- `policy/per-diem-table.csv` — Per-diem table by venue country (policy TE-07 v5) (text/csv)
- `policy/superseded-travel-and-events-policy-2024.md` — Travel & Events Policy TE-07 2024 edition (superseded) (text/markdown)
- `policy/travel-and-events-policy-te-07.md` — Travel & Events Policy TE-07 v5 (effective) (text/markdown)
- `provenance/harbor-open-source-anchors.json` — Open-source benchmark provenance — DeskOps (application/json)
- `sheets/SS-EXEC-TRV-26H2-v3.xlsx` — Executive travel & offsites H2 FY26 — budget workbook (v3, current) (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `sheets/executive-travel-budget-v2-superseded.xlsx` — Executive travel budget workbook v2 (superseded snapshot) (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `travel/bookings-register-EVT-LDR-LIS.csv` — Bookings register for EVT-LDR-LIS (text/csv)
- `travel/policy-parameters-te-07-v5.json` — Travel policy TE-07 v5 — structured parameters (application/json)
- `travel/ticketing-confirmation-WF-40255.pdf` — Group-desk ticketing confirmation WF-40255 (application/pdf)
- `venues/availability-2026-06-15.xlsx` — Venue availability by week, twelve weeks from 2026-06-15 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `venues/quote-SR-5121.pdf` — Venue quote SR-5121 (application/pdf)
- `venues/quotes-register-EVT-LDR-LIS.csv` — Venue quotes attached to EVT-LDR-LIS (text/csv)
- `workbooks/review-capacity.xlsx` — Review capacity — DESK-0002 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)

## How it is graded

The verifier runs as root after the episode, pulls the finished world over a token-gated, read-only channel that the agent user cannot open, and computes **HubScore** (0–1 reward = score / 100) from executable checks only: required investigations before the first write, provider payload assertions, post-write readbacks, write containment, exact graded answer fields, and semantic milestone aggregation (71 atomic criteria, 27 graded answer fields). No LLM judge is called. Exact call order is not graded.

The sealed contract, expected answer, and oracle policy live only in `tests/` and `solution/`; they are not present in either container image.

## Provenance

Clean-room synthetic data; no real patient, employee, supplier, or organisation is represented. Public Harbor Hub anchors for this family (evaluation-shape inspiration only):

- OSWorld-Verified: `xlang-ai/osworld-verified` — evaluation-shape inspiration only; clean-room task, state, tools, and answer
- AndroidBench: `android-bench/android-bench` — evaluation-shape inspiration only; clean-room task, state, tools, and answer

More: https://blobfish.ai/benchmarks/hubbench
