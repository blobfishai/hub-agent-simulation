# hubbench-designops-004 — Re-certify the sensor bracket before the conformity review

HubBench 1.4.0 · family **DesignOps** (`designops`, cluster `manufacturing-engineering-design`) · decision mode `plan` · role `engineering_change_coordinator` · as of 2026-05-11.

Engineering-change release decisions against a PLM with part revisions and CAD check-in history, change orders with affected items, a multi-level BOM, a certification register, a tooling register with calibration state, supplier-portal quotes, a production release calendar, and approval records.

## What the agent gets

The agent works as a non-root user in the `main` container and reaches the isolated, stateful world only through its public surfaces on the `world` service:

- MCP over streamable HTTP, one endpoint per server: `http://world:8765/mcp/<server>`
- the terminal `tool` CLI (`tool list`, `tool schema <name>`, `tool <name> '<json>'`), bound to the same world through `HUBBENCH_URL`
- the REST API under `http://world:8765/api/v1/`
- the web console at `http://world:8765/`

Servers mounted for this task:

- `approvals` — Approval workflow records with exact scope. (2 tools)
- `bom` — Multi-level bill of materials: assembly lines, alternates, phantoms, and where-used. (2 tools)
- `calendar` — Production release calendar: lines, cut-in windows with freeze and maintenance holds, cut-in reservations. (6 tools)
- `cert` — Certification register: certified assembly configurations, covered component revisions, re-certification lead time and fee. (2 tools)
- `chat` — Engineering change office chat threads. (2 tools)
- `drive` — Shared drive holding procedures, registers, calendars, and exports. (3 tools)
- `eco` — Engineering change orders: workflow state, class, affected items, effectivity release. (4 tools)
- `messages` — Engineering change office mailbox. (2 tools)
- `notes` — Stakeholder draft notes (never sent by the benchmark). (1 tools)
- `plm` — Product lifecycle management: parts, revision lifecycle, CAD models and drawings, check-in history, engineers. (6 tools)
- `supplier` — Supplier portal: fixture-build and laboratory re-certification quotes and orders. (5 tools)
- `tooling` — Tooling register: fixture families, lot register with calibration state, inter-plant transfers. (5 tools)
- `hubbench` — Benchmark-only discovery and structured answer submission controls. (2 tools)

Evidence files under `/workspace/evidence` (32 files):

- `approvals/approval-AP-DO-0104.json` — Approval record AP-DO-0104 (application/json)
- `approvals/decision-record.json` — Decision control record — DSGN-0004 (application/json)
- `audit/evidence-index.yaml` — Evidence index (application/yaml)
- `audit/evidence-status.yaml` — Evidence readiness — DSGN-0004 (application/yaml)
- `audit/system-audit.log` — System audit log — DSGN-0004 (text/plain)
- `bom/where-used-SNS-5182.json` — Where-used SNS-5182 (live BOM export) (application/json)
- `calendar/line-roster-and-capabilities.csv` — Line roster: stations, status, and CMM capability (text/csv)
- `calendar/release-calendar-2026-05-11.xlsx` — Release calendar, four weeks from 2026-05-11 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `cert/certification-register.csv` — Certification register: certified configurations and covered components (text/csv)
- `cert/program-prg-sns7-scope-note.md` — Certification program PRG-SNS7 — scope note (text/markdown)
- `chat/CHAT-1004.json` — DSGN-0004 sensor bracket re-cert (application/json)
- `collaboration/operations-thread.json` — Operations thread — DSGN-0004 (application/json)
- `communications/source-request.eml` — Source integrity request — DSGN-0004 (message/rfc822)
- `contracts/provider-contracts.json` — Provider contract — DSGN-0004 (application/json)
- `controls/current-authority.md` — Current authority — DSGN-0004 (text/markdown)
- `controls/retired-authority.md` — Retired authority — DSGN-0004 (text/markdown)
- `controls/source-integrity.pdf` — Source integrity control — DSGN-0004 (application/pdf)
- `eco/change-ECO-24131.json` — Change order ECO-24131 (ECO export) (application/json)
- `exports/live-snapshot.json` — Live pre-action snapshot — DSGN-0004 (application/json)
- `exports/starting-state-designops-004.json` — Starting-state export (reservations, supplier orders, transfers) (application/json)
- `lineage/record-lineage.csv` — Cross-system record lineage — DSGN-0004 (text/csv)
- `messages/THR-1004.eml` — DSGN-0004 sensor bracket — must be cut in before the conformity review on the 22nd (message/rfc822)
- `plm/checkin-history.csv` — CAD check-in history (text/csv)
- `plm/part-SNS-5182-summary.json` — Part SNS-5182 summary with revisions and CAD documents (PLM export) (application/json)
- `procedure/change-control-procedure-ecp-12.md` — Change control procedure ECP-12 rev 5 (effective) (text/markdown)
- `procedure/superseded-change-control-procedure-rev3.md` — Change control procedure ECP-12 rev 3 (superseded) (text/markdown)
- `provenance/harbor-open-source-anchors.json` — Open-source benchmark provenance — DesignOps (application/json)
- `supplier/quote-RQ-3322.pdf` — Supplier quotation RQ-3322 (application/pdf)
- `tooling/fixture-family-catalog.csv` — Fixture family catalog: sets per station and calibration horizon (text/csv)
- `tooling/fixture-holdings-by-lot.xlsx` — Registered fixture-set holdings by lot (gross) (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `tooling/fixture-lot-status-register.csv` — Fixture-lot status register (calibration, reservation, revision notes) (text/csv)
- `workbooks/review-capacity.xlsx` — Review capacity — DSGN-0004 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)

## How it is graded

The verifier runs as root after the episode, pulls the finished world over a token-gated, read-only channel that the agent user cannot open, and computes **HubScore** (0–1 reward = score / 100) from executable checks only: required investigations before the first write, provider payload assertions, post-write readbacks, write containment, exact graded answer fields, and semantic milestone aggregation (71 atomic criteria, 31 graded answer fields). No LLM judge is called. Exact call order is not graded.

The sealed contract, expected answer, and oracle policy live only in `tests/` and `solution/`; they are not present in either container image.

## Provenance

Clean-room synthetic data; no real patient, employee, supplier, or organisation is represented. Public Harbor Hub anchors for this family (evaluation-shape inspiration only):

- CAD-Bench: `gnucleus-ai/cad-bench` — evaluation-shape inspiration only; clean-room task, state, tools, and answer
- HWE-Bench: `hwe-bench/hwe-bench` — evaluation-shape inspiration only; clean-room task, state, tools, and answer
- FactoryBench-100: `blobfishai/factorybench-100` — evaluation-shape inspiration only; clean-room task, state, tools, and answer

More: https://blobfish.ai/benchmarks/hubbench
