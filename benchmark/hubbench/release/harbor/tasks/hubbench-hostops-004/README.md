# hubbench-hostops-004 — Restore the audit-log week before the regulator session

HubBench 1.4.0 · family **HostOps** (`hostops`, cluster `terminal-operations`) · decision mode `plan` · role `platform_operations_coordinator` · as of 2026-04-13.

Host-operations recovery decisions against a Linux service inventory, cron/CI scheduler, backup catalog with retention and vendor retrievals, release build farm, and approval records.

## What the agent gets

The agent works as a non-root user in the `main` container and reaches the isolated, stateful world only through its public surfaces on the `world` service:

- MCP over streamable HTTP, one endpoint per server: `http://world:8765/mcp/<server>`
- the terminal `tool` CLI (`tool list`, `tool schema <name>`, `tool <name> '<json>'`), bound to the same world through `HUBBENCH_URL`
- the REST API under `http://world:8765/api/v1/`
- the web console at `http://world:8765/`

Servers mounted for this task:

- `approvals` — Approval workflow records with exact scope. (2 tools)
- `backup` — Backup catalog: artifact classes, segment-set register, vendor restore jobs, and inter-store copies. (8 tools)
- `buildfarm` — Release build farm: runners, reservation-window calendar, and reservations. (6 tools)
- `chat` — Platform operations chat threads. (2 tools)
- `cmdb` — Configuration database: services, engineers, Linux host inventory, and payload meterings. (5 tools)
- `drive` — Shared drive holding runbooks, registers, calendars, and exports. (3 tools)
- `jobs` — Scheduler: cron / CI job definitions and run history. (4 tools)
- `messages` — Operations mailbox for the platform team. (2 tools)
- `notes` — Stakeholder draft notes (never sent by the benchmark). (1 tools)
- `releases` — Release and recovery tickets with payload basis and run durations. (2 tools)
- `vendor` — Cold-archive vault retrieval confirmations. (2 tools)
- `hubbench` — Benchmark-only discovery and structured answer submission controls. (2 tools)

Evidence files under `/workspace/evidence` (30 files):

- `approvals/approval-AP-HO-0104.json` — Approval record AP-HO-0104 (application/json)
- `approvals/decision-record.json` — Decision control record — HOST-0004 (application/json)
- `audit/evidence-index.yaml` — Evidence index (application/yaml)
- `audit/evidence-status.yaml` — Evidence readiness — HOST-0004 (application/yaml)
- `audit/system-audit.log` — System audit log — HOST-0004 (text/plain)
- `backup/artifact-class-catalog.csv` — Artifact class catalog: segment sizes and minimum retention (text/csv)
- `backup/dr-replication-status.md` — DR replica status — audit-log archive (text/markdown)
- `backup/segment-holdings-by-set.xlsx` — Catalogued segment holdings by set (gross) (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `backup/set-status-register.csv` — Segment-set status register (checksum, reservation, durability notes) (text/csv)
- `buildfarm/runner-calendar-2026-04-13.xlsx` — Runner window calendar, three weeks from 2026-04-13 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `buildfarm/runner-roster-and-capabilities.csv` — Runner roster and isolation capability (text/csv)
- `chat/CHAT-1004.json` — HOST-0004 audit-log restore (application/json)
- `cmdb/service-telemetry-audit-summary.json` — Service telemetry-audit summary with payload meterings (CMDB export) (application/json)
- `collaboration/operations-thread.json` — Operations thread — HOST-0004 (application/json)
- `communications/source-request.eml` — Source integrity request — HOST-0004 (message/rfc822)
- `contracts/provider-contracts.json` — Provider contract — HOST-0004 (application/json)
- `controls/current-authority.md` — Current authority — HOST-0004 (text/markdown)
- `controls/retired-authority.md` — Retired authority — HOST-0004 (text/markdown)
- `controls/source-integrity.pdf` — Source integrity control — HOST-0004 (application/pdf)
- `exports/live-snapshot.json` — Live pre-action snapshot — HOST-0004 (application/json)
- `exports/starting-state-hostops-004.json` — Starting-state export (reservations, restores, copies) (application/json)
- `jobs/job-schedule-and-runs.csv` — Scheduler jobs and recent runs (text/csv)
- `lineage/record-lineage.csv` — Cross-system record lineage — HOST-0004 (text/csv)
- `messages/THR-1004.eml` — HOST-0004 audit-log week — must be indexed before Monday the 20th (message/rfc822)
- `provenance/harbor-open-source-anchors.json` — Open-source benchmark provenance — HostOps (application/json)
- `releases/ticket-RT-51272.json` — Ticket RT-51272 (releases export) (application/json)
- `runbook/platform-operations-runbook.md` — Platform operations runbook v4 (effective) (text/markdown)
- `runbook/superseded-operations-runbook-2024.md` — Platform operations runbook 2024 (superseded) (text/markdown)
- `vendor/retrieval-confirmation-RQ-66207.pdf` — Vault retrieval confirmation RQ-66207 (application/pdf)
- `workbooks/review-capacity.xlsx` — Review capacity — HOST-0004 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)

## How it is graded

The verifier runs as root after the episode, pulls the finished world over a token-gated, read-only channel that the agent user cannot open, and computes **HubScore** (0–1 reward = score / 100) from executable checks only: required investigations before the first write, provider payload assertions, post-write readbacks, write containment, exact graded answer fields, and semantic milestone aggregation (65 atomic criteria, 27 graded answer fields). No LLM judge is called. Exact call order is not graded.

The sealed contract, expected answer, and oracle policy live only in `tests/` and `solution/`; they are not present in either container image.

## Provenance

Clean-room synthetic data; no real patient, employee, supplier, or organisation is represented. Public Harbor Hub anchors for this family (evaluation-shape inspiration only):

- Terminal-Bench: `terminal-bench/terminal-bench` — evaluation-shape inspiration only; clean-room task, state, tools, and answer
- Terminal-Bench 2.1 file recovery: `NovitaAI/tb21-file-recovery` — evaluation-shape inspiration only; clean-room task, state, tools, and answer

More: https://blobfish.ai/benchmarks/hubbench
