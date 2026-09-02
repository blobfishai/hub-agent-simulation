# hubbench-scilab-007 — Advance the NfL validation panel before the building decontamination

HubBench 1.1.0 · family **SciLab** (`scilab`, cluster `scientific-research`) · decision mode `plan` · role `assay_operations_coordinator` · as of 2026-05-11.

Assay-operations decisions against a LIMS with versioned protocols and QC results, an analyser schedule with calibration certificates, a reagent-lot inventory with expiry and quarantine state, supplier shipment confirmations, ELN method notes, and approval records.

## What the agent gets

The agent works as a non-root user in the `main` container and reaches the isolated, stateful world only through its public surfaces on the `world` service:

- MCP over streamable HTTP, one endpoint per server: `http://world:8765/mcp/<server>`
- the terminal `tool` CLI (`tool list`, `tool schema <name>`, `tool <name> '<json>'`), bound to the same world through `HUBBENCH_URL`
- the REST API under `http://world:8765/api/v1/`
- the web console at `http://world:8765/`

Servers mounted for this task:

- `approvals` — Approval workflow records with exact scope. (2 tools)
- `chat` — Assay-operations chat threads. (2 tools)
- `drive` — Shared drive holding SOPs, registers, calendars, and exports. (3 tools)
- `eln` — Electronic lab notebook: method notes and SOP references with supersession. (2 tools)
- `instruments` — Instrument schedule: analyser roster, calibration certificates, booking-window calendar, and bookings. (8 tools)
- `inventory` — Reagent inventory: reagent catalog, lot register with expiry and quarantine state, and inter-site transfers. (5 tools)
- `lims` — Laboratory information management system: assays, scientists, sample-batch counts, protocol versions, run requests, assay runs, and QC results. (11 tools)
- `messages` — Assay-operations mailbox for the core facility. (2 tools)
- `notes` — Stakeholder draft notes (never sent by the benchmark). (1 tools)
- `supplier` — Supplier portal: shipment confirmations with lead times and cold-chain terms, and reagent orders. (5 tools)
- `hubbench` — Benchmark-only discovery and structured answer submission controls. (2 tools)

Evidence files under `/workspace/evidence` (34 files):

- `approvals/approval-AP-SL-0107.json` — Approval record AP-SL-0107 (application/json)
- `approvals/decision-record.json` — Decision control record — LAB-0007 (application/json)
- `audit/evidence-index.yaml` — Evidence index (application/yaml)
- `audit/evidence-status.yaml` — Evidence readiness — LAB-0007 (application/yaml)
- `audit/system-audit.log` — System audit log — LAB-0007 (text/plain)
- `chat/CHAT-1007.json` — LAB-0007 NfL panel — decontamination (application/json)
- `collaboration/operations-thread.json` — Operations thread — LAB-0007 (application/json)
- `communications/source-request.eml` — Source integrity request — LAB-0007 (message/rfc822)
- `contracts/provider-contracts.json` — Provider contract — LAB-0007 (application/json)
- `controls/current-authority.md` — Current authority — LAB-0007 (text/markdown)
- `controls/retired-authority.md` — Retired authority — LAB-0007 (text/markdown)
- `controls/source-integrity.pdf` — Source integrity control — LAB-0007 (application/pdf)
- `eln/method-notes-IA-NFL-PANEL.md` — ELN method notes — IA-NFL-PANEL (text/markdown)
- `exports/live-snapshot.json` — Live pre-action snapshot — LAB-0007 (application/json)
- `exports/starting-state-scilab-007.json` — Starting-state export (bookings, orders, transfers) (application/json)
- `facilities/decontamination-notice.md` — Decontamination shutdown notice — building C (text/markdown)
- `instruments/analyser-calendar-2026-05-11.xlsx` — Analyser window calendar, three weeks from 2026-05-11 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `instruments/analyser-roster-and-certificates.csv` — Analyser roster, qualification flags, and calibration certificates (text/csv)
- `inventory/lot-holdings-by-lot.xlsx` — On-hand control vials by lot (gross) (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `inventory/lot-status-register.csv` — Lot status register (quarantine, reservation, stability notes) (text/csv)
- `inventory/reagent-catalog.csv` — Reagent catalog: vial format, storage, and minimum dating (text/csv)
- `lims/assay-neuro-nfl-panel-summary.json` — Assay neuro-nfl-panel summary with sample-batch counts (LIMS export) (application/json)
- `lims/protocol-IA-NFL-PANEL-versions.csv` — Protocol IA-NFL-PANEL version register (text/csv)
- `lims/request-RR-50110.json` — Run request RR-50110 (superseded 60-sample tier) (application/json)
- `lims/request-RR-51295.json` — Run request RR-51295 (LIMS export) (application/json)
- `lims/run-history-and-qc.csv` — Assay runs and QC control results (text/csv)
- `lineage/record-lineage.csv` — Cross-system record lineage — LAB-0007 (text/csv)
- `messages/THR-1007.eml` — LAB-0007 NfL validation panel — before the decontamination starts on the 23rd (message/rfc822)
- `provenance/harbor-open-source-anchors.json` — Open-source benchmark provenance — SciLab (application/json)
- `sop/assay-operations-sop-ao-014.md` — Assay operations SOP AO-014 v3 (effective) (text/markdown)
- `sop/superseded-assay-operations-sop-2024.md` — Assay operations SOP AO-014 2024 edition (superseded) (text/markdown)
- `supplier/shipment-confirmation-CR-66288.pdf` — Shipment confirmation CR-66288 (application/pdf)
- `validation/validation-tier-table.csv` — Validation panel tier table (text/csv)
- `workbooks/review-capacity.xlsx` — Review capacity — LAB-0007 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)

## How it is graded

The verifier runs as root after the episode, pulls the finished world over a token-gated, read-only channel that the agent user cannot open, and computes **HubScore** (0–1 reward = score / 100) from executable checks only: required investigations before the first write, provider payload assertions, post-write readbacks, write containment, exact graded answer fields, and semantic milestone aggregation (73 atomic criteria, 28 graded answer fields). No LLM judge is called. Exact call order is not graded.

The sealed contract, expected answer, and oracle policy live only in `tests/` and `solution/`; they are not present in either container image.

## Provenance

Clean-room synthetic data; no real patient, employee, supplier, or organisation is represented. Public Harbor Hub anchors for this family (evaluation-shape inspiration only):

- ScienceAgentBench: `scienceagentbench/scienceagentbench` — evaluation-shape inspiration only; clean-room task, state, tools, and answer
- BixBench: `futurehouse/bixbench` — evaluation-shape inspiration only; clean-room task, state, tools, and answer
- LAB-Bench: `futurehouse/labbench` — evaluation-shape inspiration only; clean-room task, state, tools, and answer

More: https://blobfish.ai/benchmarks/hubbench
