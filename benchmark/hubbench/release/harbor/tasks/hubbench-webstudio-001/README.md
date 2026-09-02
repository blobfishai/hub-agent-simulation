# hubbench-webstudio-001 — Ship the pricing page refresh before the Q2 plan names go live

HubBench 1.3.0 · family **WebStudio** (`webstudio`, cluster `web-product-design`) · decision mode `plan` · role `web_release_coordinator` · as of 2026-05-11.

Design-operations release decisions against a headless CMS, a design-token and component registry, a design-file index, an asset library with licence grants and vendor quotes, a release checklist, CDN deploy lanes, and approval records.

## What the agent gets

The agent works as a non-root user in the `main` container and reaches the isolated, stateful world only through its public surfaces on the `world` service:

- MCP over streamable HTTP, one endpoint per server: `http://world:8765/mcp/<server>`
- the terminal `tool` CLI (`tool list`, `tool schema <name>`, `tool <name> '<json>'`), bound to the same world through `HUBBENCH_URL`
- the REST API under `http://world:8765/api/v1/`
- the web console at `http://world:8765/`

Servers mounted for this task:

- `approvals` — Approval workflow records with exact scope. (2 tools)
- `cdn` — CDN deploy scheduler: deploy lanes with rollback capability and the deploy-window calendar. (2 tools)
- `chat` — Web-release chat threads. (2 tools)
- `checklist` — Release checklist: QA, accessibility, legal, and performance gates with measured values, plus gate waivers. (3 tools)
- `cms` — Headless CMS: pages, entries with token / component / asset bindings, change requests, and scheduled releases. (10 tools)
- `dam` — Digital asset library: assets, licence grants with territories and expiry, and vendor licence requests. (5 tools)
- `design` — Design-file index: files per page with current / superseded status and frame review states. (3 tools)
- `drive` — Shared drive holding the playbook, registers, calendars, and exports. (3 tools)
- `messages` — Web-studio mailbox for the release team. (2 tools)
- `notes` — Stakeholder draft notes (never sent by the benchmark). (1 tools)
- `tokens` — Design-token and component registry: token versions with breaking flags, components with allowed variants and deprecations, consumer registry, and version pins. (7 tools)
- `vendors` — Vendor desk: foundry and stock-imagery licence quotes, agency delivery quotes, and edge-provider lane re-certification quotes. (2 tools)
- `hubbench` — Benchmark-only discovery and structured answer submission controls. (2 tools)

Evidence files under `/workspace/evidence` (34 files):

- `approvals/approval-AP-WS-0101.json` — Approval record AP-WS-0101 (application/json)
- `approvals/decision-record.json` — Decision control record — WEB-0001 (application/json)
- `audit/evidence-index.yaml` — Evidence index (application/yaml)
- `audit/evidence-status.yaml` — Evidence readiness — WEB-0001 (application/yaml)
- `audit/system-audit.log` — System audit log — WEB-0001 (text/plain)
- `cdn/deploy-window-calendar-2026-05-11.xlsx` — Deploy-window calendar, three weeks from 2026-05-11 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `cdn/lane-roster-and-capabilities.csv` — Deploy-lane roster and rollback capability (text/csv)
- `chat/CHAT-1001.json` — WEB-0001 pricing refresh (application/json)
- `checklist/perf-budgets-pricing.csv` — Performance budgets for pricing (text/csv)
- `checklist/release-checklist-CR-4410.csv` — Release checklist for CR-4410 (text/csv)
- `cms/change-request-CR-4410.json` — Change request CR-4410 (CMS export) (application/json)
- `cms/page-pricing-entries.json` — Page pricing with entries and bindings (CMS export) (application/json)
- `collaboration/operations-thread.json` — Operations thread — WEB-0001 (application/json)
- `communications/source-request.eml` — Source integrity request — WEB-0001 (message/rfc822)
- `contracts/provider-contracts.json` — Provider contract — WEB-0001 (application/json)
- `controls/current-authority.md` — Current authority — WEB-0001 (text/markdown)
- `controls/retired-authority.md` — Retired authority — WEB-0001 (text/markdown)
- `controls/source-integrity.pdf` — Source integrity control — WEB-0001 (application/pdf)
- `dam/licence-grants.xlsx` — Licence grants by asset (gross territories) (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `dam/licence-status-register.csv` — Licence-grant status register (countersign, scope, reservations) (text/csv)
- `design/design-file-index.csv` — Design-file index with frame review status (text/csv)
- `exports/live-snapshot.json` — Live pre-action snapshot — WEB-0001 (application/json)
- `exports/starting-state-webstudio-001.json` — Starting-state export (releases, pins, licence requests) (application/json)
- `lineage/record-lineage.csv` — Cross-system record lineage — WEB-0001 (text/csv)
- `messages/THR-1001.eml` — WEB-0001 pricing refresh — can it ship this week? (message/rfc822)
- `playbook/superseded-web-release-playbook-2024.md` — Web release playbook 2024 (superseded) (text/markdown)
- `playbook/web-release-playbook.md` — Web release playbook v3 (effective) (text/markdown)
- `provenance/harbor-open-source-anchors.json` — Open-source benchmark provenance — WebStudio (application/json)
- `tokens/component-register.csv` — Component register: versions, variants, deprecations (text/csv)
- `tokens/consumer-registry.xlsx` — Token and component consumer registry (gross) (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `tokens/token-register.csv` — Design-token register: versions, status, breaking flags (text/csv)
- `vendors/stillframe-licensing-terms.md` — Stillframe Stock Imagery — licensing terms (extract) (text/markdown)
- `vendors/vendor-quote-SFQ-90412.pdf` — Vendor quote SFQ-90412 (application/pdf)
- `workbooks/review-capacity.xlsx` — Review capacity — WEB-0001 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)

## How it is graded

The verifier runs as root after the episode, pulls the finished world over a token-gated, read-only channel that the agent user cannot open, and computes **HubScore** (0–1 reward = score / 100) from executable checks only: required investigations before the first write, provider payload assertions, post-write readbacks, write containment, exact graded answer fields, and semantic milestone aggregation (71 atomic criteria, 28 graded answer fields). No LLM judge is called. Exact call order is not graded.

The sealed contract, expected answer, and oracle policy live only in `tests/` and `solution/`; they are not present in either container image.

## Provenance

Clean-room synthetic data; no real patient, employee, supplier, or organisation is represented. Public Harbor Hub anchors for this family (evaluation-shape inspiration only):

- WebGen-Bench: `webgen-bench/webgen-bench` — evaluation-shape inspiration only; clean-room task, state, tools, and answer
- Open Design: `open-design/open-design` — evaluation-shape inspiration only; clean-room task, state, tools, and answer
- Vector Edit Gym: `thetalab/vector-edit-gym` — evaluation-shape inspiration only; clean-room task, state, tools, and answer

More: https://blobfish.ai/benchmarks/hubbench
