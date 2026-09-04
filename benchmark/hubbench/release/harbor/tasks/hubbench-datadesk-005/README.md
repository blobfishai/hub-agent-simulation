# hubbench-datadesk-005 — Reload the attribution days broken by Cormorant's schema cutover

HubBench 1.4.0 · family **DataDesk** (`datadesk`, cluster `data-engineering-analytics`) · decision mode `plan` · role `analytics_engineer_oncall` · as of 2026-03-09.

Data engineering decisions against a dbt-style warehouse catalog, pipeline run history, vendor feed deliveries, freshness SLAs, batch-window capacity, and finance reconciliation controls.

## What the agent gets

The agent works as a non-root user in the `main` container and reaches the isolated, stateful world only through its public surfaces on the `world` service:

- MCP over streamable HTTP, one endpoint per server: `http://world:8765/mcp/<server>`
- the terminal `tool` CLI (`tool list`, `tool schema <name>`, `tool <name> '<json>'`), bound to the same world through `HUBBENCH_URL`
- the REST API under `http://world:8765/api/v1/`
- the web console at `http://world:8765/`

Servers mounted for this task:

- `approvals` — Approval workflow records with exact scope. (2 tools)
- `chat` — Data platform team chat threads. (2 tools)
- `drive` — Shared drive holding policies, registers, calendars, and exports. (3 tools)
- `feeds` — Source feeds, delivery logs, and vendor redelivery confirmations. (5 tools)
- `messages` — Mailbox for the data platform team. (2 tools)
- `notes` — Stakeholder draft notes (never sent by the benchmark). (1 tools)
- `pipelines` — Pipeline runs, run schedules, and backfill jobs. (6 tools)
- `recon` — Finance reconciliation: published control totals and adjustment entries. (4 tools)
- `warehouse` — Warehouse catalog: dbt-style models, lineage, freshness SLAs, clusters, and the batch window calendar. (6 tools)
- `hubbench` — Benchmark-only discovery and structured answer submission controls. (2 tools)

Evidence files under `/workspace/evidence` (30 files):

- `approvals/approval-AP-DD-0205.json` — Approval record AP-DD-0205 (application/json)
- `approvals/decision-record.json` — Decision control record — DATA-0005 (application/json)
- `audit/evidence-index.yaml` — Evidence index (application/yaml)
- `audit/evidence-status.yaml` — Evidence readiness — DATA-0005 (application/yaml)
- `audit/system-audit.log` — System audit log — DATA-0005 (text/plain)
- `catalog/model-MDL-ATTR-T.json` — Catalog manifest — fct_attribution_touch (application/json)
- `chat/CHAT-0005.json` — DATA-0005 Cormorant schema cutover (application/json)
- `collaboration/operations-thread.json` — Operations thread — DATA-0005 (application/json)
- `communications/source-request.eml` — Source integrity request — DATA-0005 (message/rfc822)
- `contracts/provider-contracts.json` — Provider contract — DATA-0005 (application/json)
- `controls/current-authority.md` — Current authority — DATA-0005 (text/markdown)
- `controls/retired-authority.md` — Retired authority — DATA-0005 (text/markdown)
- `controls/source-integrity.pdf` — Source integrity control — DATA-0005 (application/pdf)
- `exports/live-snapshot.json` — Live pre-action snapshot — DATA-0005 (application/json)
- `exports/starting-state-datadesk-005.json` — Starting-state export (schedules, backfills, adjustments) (application/json)
- `feeds/cormorant-schema-change-notice.md` — Cormorant Adtech — v3.0 event schema notice (received late) (text/markdown)
- `feeds/delivery-log-FEED-CORM-CLK.csv` — Delivery log — Cormorant clickstream events (text/csv)
- `feeds/redelivery-confirmation-CA-5519.pdf` — Vendor redelivery confirmation CA-5519 (application/pdf)
- `lineage/record-lineage.csv` — Cross-system record lineage — DATA-0005 (text/csv)
- `messages/THR-0005.eml` — DATA-0005 attribution numbers wrong before Thursday review (message/rfc822)
- `pipelines/run-history-MDL-ATTR-T.xlsx` — Run history — fct_attribution_touch (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `pipelines/schedule-register.csv` — Run schedule register (text/csv)
- `policy/data-platform-operations-policy.md` — Data Platform Operations Policy v4 (effective) (text/markdown)
- `policy/superseded-data-platform-policy-2025.md` — Data Platform Operations Policy 2025 (superseded) (text/markdown)
- `provenance/harbor-open-source-anchors.json` — Open-source benchmark provenance — DataDesk (application/json)
- `recon/certification-workbook-DATA-0005.xlsx` — Certification workbook — DATA-0005 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `sla/freshness-sla-register.csv` — Freshness SLA register (text/csv)
- `warehouse/cluster-roster.csv` — Cluster roster and backfill capability (text/csv)
- `warehouse/window-calendar-2026-03-09.xlsx` — Warehouse window calendar, three weeks from 2026-03-09 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `workbooks/review-capacity.xlsx` — Review capacity — DATA-0005 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)

## How it is graded

The verifier runs as root after the episode, pulls the finished world over a token-gated, read-only channel that the agent user cannot open, and computes **HubScore** (0–1 reward = score / 100) from executable checks only: required investigations before the first write, provider payload assertions, post-write readbacks, write containment, exact graded answer fields, and semantic milestone aggregation (62 atomic criteria, 24 graded answer fields). No LLM judge is called. Exact call order is not graded.

The sealed contract, expected answer, and oracle policy live only in `tests/` and `solution/`; they are not present in either container image.

## Provenance

Clean-room synthetic data; no real patient, employee, supplier, or organisation is represented. Public Harbor Hub anchors for this family (evaluation-shape inspiration only):

- DataEngBench: `snowflake-labs/data-eng-bench` — evaluation-shape inspiration only; clean-room task, state, tools, and answer
- ADE-Bench: `dbt-labs/ade-bench` — evaluation-shape inspiration only; clean-room task, state, tools, and answer

More: https://blobfish.ai/benchmarks/hubbench
