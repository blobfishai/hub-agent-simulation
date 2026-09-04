# hubbench-itsmdesk-004 — Patch the ledger-sync arm pool before the advisory SLA

HubBench 1.4.0 · family **ITSMDesk** (`itsmdesk`, cluster `it-operations-observability`) · decision mode `plan` · role `service_operations_coordinator` · as of 2026-04-14.

Change-scheduling decisions against a ServiceNow-shaped ITSM (CIs, incidents, problems, change requests, outage notices), Grafana-shaped SLOs and error budgets, a change calendar with lanes and freeze windows, a PagerDuty-shaped on-call plane, vendor patch advisories, and approval records.

## What the agent gets

The agent works as a non-root user in the `main` container and reaches the isolated, stateful world only through its public surfaces on the `world` service:

- MCP over streamable HTTP, one endpoint per server: `http://world:8765/mcp/<server>`
- the terminal `tool` CLI (`tool list`, `tool schema <name>`, `tool <name> '<json>'`), bound to the same world through `HUBBENCH_URL`
- the REST API under `http://world:8765/api/v1/`
- the web console at `http://world:8765/`

Servers mounted for this task:

- `approvals` — Approval workflow records with exact scope. (2 tools)
- `calendar` — Change calendar: change lanes, freeze register, and the maintenance-window calendar. (3 tools)
- `chat` — Service-operations chat threads. (2 tools)
- `drive` — Shared drive holding policies, registers, calendars, and exports. (3 tools)
- `itsm` — IT service management: service CIs, nodes, meterings, incidents, problems, change requests, change tasks, and planned-outage notices. (15 tools)
- `messages` — Service-operations mailbox. (2 tools)
- `notes` — Stakeholder draft notes (never sent by the benchmark). (1 tools)
- `oncall` — On-call plane: schedules, rostered shifts, escalation policies, responders, and overrides. (6 tools)
- `telemetry` — Observability: SLO definitions, error-budget views, burn-rate samples, and alert history. (5 tools)
- `vendor` — Vendor patch portal: advisories with affected versions, restart requirements, release dates, and premium-support fees. (2 tools)
- `hubbench` — Benchmark-only discovery and structured answer submission controls. (2 tools)

Evidence files under `/workspace/evidence` (34 files):

- `approvals/approval-AP-SO-0104.json` — Approval record AP-SO-0104 (application/json)
- `approvals/decision-record.json` — Decision control record — SVCOPS-0004 (application/json)
- `audit/evidence-index.yaml` — Evidence index (application/yaml)
- `audit/evidence-status.yaml` — Evidence readiness — SVCOPS-0004 (application/yaml)
- `audit/system-audit.log` — System audit log — SVCOPS-0004 (text/plain)
- `calendar/change-calendar-2026-04-14.xlsx` — Change calendar, three weeks from 2026-04-14 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `calendar/freeze-register.csv` — Freeze register (change calendar) (text/csv)
- `calendar/lane-roster.csv` — Change-lane roster and certification (text/csv)
- `chat/CHAT-2004.json` — SVCOPS-0004 ledger-sync arm64 (application/json)
- `collaboration/operations-thread.json` — Operations thread — SVCOPS-0004 (application/json)
- `communications/source-request.eml` — Source integrity request — SVCOPS-0004 (message/rfc822)
- `contracts/provider-contracts.json` — Provider contract — SVCOPS-0004 (application/json)
- `controls/current-authority.md` — Current authority — SVCOPS-0004 (text/markdown)
- `controls/retired-authority.md` — Retired authority — SVCOPS-0004 (text/markdown)
- `controls/source-integrity.pdf` — Source integrity control — SVCOPS-0004 (application/pdf)
- `exports/live-snapshot.json` — Live pre-action snapshot — SVCOPS-0004 (application/json)
- `exports/starting-state-itsmdesk-004.json` — Starting-state export (changes, tasks, outages, overrides) (application/json)
- `itsm/change-CHG-40340.json` — Change CHG-40340 (ITSM export) (application/json)
- `itsm/incident-register.csv` — Incident register with problem-review notes (text/csv)
- `itsm/service-ledger-sync-summary.json` — Service ledger-sync summary with restart meterings (ITSM export) (application/json)
- `itsm/staged-build-register.csv` — Staged build register — ledger-sync (text/csv)
- `lineage/record-lineage.csv` — Cross-system record lineage — SVCOPS-0004 (text/csv)
- `messages/THR-2004.eml` — SVCOPS-0004 ledger-sync arm pool — can we make the SLA? (message/rfc822)
- `oncall/secondary-roster.csv` — Secondary on-call roster — SCHED-LDG-SEC (text/csv)
- `policy/change-and-error-budget-policy.md` — Change and error-budget policy v3 (effective) (text/markdown)
- `policy/superseded-change-policy-2024.md` — Change and error-budget policy 2024 (superseded) (text/markdown)
- `provenance/harbor-open-source-anchors.json` — Open-source benchmark provenance — ITSMDesk (application/json)
- `telemetry/burn-rate-samples.csv` — Burn-rate samples — SLO-LDG-AVAIL (text/csv)
- `telemetry/error-budget-ledger.xlsx` — Error-budget ledger — ledger-sync (gross incident minutes) (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `telemetry/slo-catalog.csv` — SLO catalog: objectives, windows, budgets, and reserve floors (text/csv)
- `vendor/advisory-OWA-2026-052-rev1.json` — Advisory OWA-2026-052 rev 1 (withdrawn, superseded) (application/json)
- `vendor/advisory-OWA-2026-052.pdf` — Vendor advisory OWA-2026-052 (application/pdf)
- `vendor/orrinwave-support-terms.md` — Orrinwave Data Systems — support terms (extract) (text/markdown)
- `workbooks/review-capacity.xlsx` — Review capacity — SVCOPS-0004 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)

## How it is graded

The verifier runs as root after the episode, pulls the finished world over a token-gated, read-only channel that the agent user cannot open, and computes **HubScore** (0–1 reward = score / 100) from executable checks only: required investigations before the first write, provider payload assertions, post-write readbacks, write containment, exact graded answer fields, and semantic milestone aggregation (69 atomic criteria, 28 graded answer fields). No LLM judge is called. Exact call order is not graded.

The sealed contract, expected answer, and oracle policy live only in `tests/` and `solution/`; they are not present in either container image.

## Provenance

Clean-room synthetic data; no real patient, employee, supplier, or organisation is represented. Public Harbor Hub anchors for this family (evaluation-shape inspiration only):

- ITSM-Bench: `vibrantlabsai/itsm-bench` — evaluation-shape inspiration only; clean-room task, state, tools, and answer
- o11y-bench: `grafana/o11y-bench` — evaluation-shape inspiration only; clean-room task, state, tools, and answer
- otel-bench: `quesma/otel-bench` — evaluation-shape inspiration only; clean-room task, state, tools, and answer

More: https://blobfish.ai/benchmarks/hubbench
