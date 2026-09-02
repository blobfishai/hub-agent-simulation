# hubbench-clinicops-008 — Replace tocilizumab after the fridge excursion before Monday's clinic

HubBench 1.0.0 · family **ClinicOps** (`clinicops`, cluster `healthcare`) · decision mode `quantity` · role `infusion_pharmacy_buyer` · as of 2026-03-09.

Infusion operations decisions against a FHIR-shaped EHR, chair scheduling, pharmacy inventory, supplier confirmations, and approval records.

## What the agent gets

The agent works as a non-root user in the `main` container and reaches the isolated, stateful world only through its public surfaces on the `world` service:

- MCP over streamable HTTP, one endpoint per server: `http://world:8765/mcp/<server>`
- the terminal `tool` CLI (`tool list`, `tool schema <name>`, `tool <name> '<json>'`), bound to the same world through `HUBBENCH_URL`
- the REST API under `http://world:8765/api/v1/`
- the web console at `http://world:8765/`

Servers mounted for this task:

- `approvals` — Approval workflow records with exact scope. (2 tools)
- `chat` — Infusion team chat threads. (2 tools)
- `drive` — Shared drive holding policies, registers, calendars, and exports. (3 tools)
- `ehr` — FHIR R4-shaped electronic health record: Patient, Observation, MedicationRequest, Practitioner. (6 tools)
- `messages` — Secure messaging and email for the infusion service. (2 tools)
- `notes` — Stakeholder draft notes (never sent by the benchmark). (1 tools)
- `pharmacy` — Pharmacy formulary, lot register, inventory balances, purchase orders, and inter-site transfers. (8 tools)
- `scheduling` — Infusion chair scheduling: chairs, FHIR Slot sessions, and Appointment resources. (6 tools)
- `supplier` — Specialty distributor delivery confirmations. (2 tools)
- `hubbench` — Benchmark-only discovery and structured answer submission controls. (2 tools)

Evidence files under `/workspace/evidence` (31 files):

- `approvals/approval-AP-CO-0108.json` — Approval record AP-CO-0108 (application/json)
- `approvals/decision-record.json` — Decision control record — CLIN-0008 (application/json)
- `audit/evidence-index.yaml` — Evidence index (application/yaml)
- `audit/evidence-status.yaml` — Evidence readiness — CLIN-0008 (application/yaml)
- `audit/system-audit.log` — System audit log — CLIN-0008 (text/plain)
- `chat/CHAT-0008.json` — CLIN-0008 fridge B excursion — tocilizumab (application/json)
- `collaboration/operations-thread.json` — Operations thread — CLIN-0008 (application/json)
- `communications/source-request.eml` — Source integrity request — CLIN-0008 (message/rfc822)
- `contracts/provider-contracts.json` — Provider contract — CLIN-0008 (application/json)
- `controls/current-authority.md` — Current authority — CLIN-0008 (text/markdown)
- `controls/retired-authority.md` — Retired authority — CLIN-0008 (text/markdown)
- `controls/source-integrity.pdf` — Source integrity control — CLIN-0008 (application/pdf)
- `ehr/medication-request-MR-70601.json` — MedicationRequest MR-70601 (FHIR export) (application/json)
- `ehr/patient-MRN-462007-summary.json` — Patient MRN-462007 summary with weight observations (FHIR export) (application/json)
- `exports/live-snapshot.json` — Live pre-action snapshot — CLIN-0008 (application/json)
- `exports/starting-state-clinicops-008.json` — Starting-state export (appointments, orders, transfers) (application/json)
- `lineage/record-lineage.csv` — Cross-system record lineage — CLIN-0008 (text/csv)
- `messages/THR-0008.eml` — CLIN-0008 fridge B excursion — Monday tocilizumab clinic (message/rfc822)
- `pharmacy/excursion-register.csv` — Refrigerator excursion register — infusion pharmacy (text/csv)
- `pharmacy/formulary-vial-strengths.csv` — Formulary vial strengths and minimum dating (text/csv)
- `pharmacy/lot-status-register.csv` — Lot status register (quarantine, reservation, excursion notes) (text/csv)
- `pharmacy/on-hand-by-lot.xlsx` — On-hand inventory by lot (gross) (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `pharmacy/stability-letter-tocilizumab-2024.pdf` — Manufacturer stability letter — tocilizumab (2024, superseded) (application/pdf)
- `pharmacy/stability-letter-tocilizumab-2026-03.pdf` — Manufacturer stability letter — tocilizumab 400 mg vials (current) (application/pdf)
- `policy/infusion-operations-policy.md` — Infusion operations policy v3 (effective) (text/markdown)
- `policy/superseded-infusion-policy-2024.md` — Infusion operations policy 2024 (superseded) (text/markdown)
- `provenance/harbor-open-source-anchors.json` — Open-source benchmark provenance — ClinicOps (application/json)
- `scheduling/chair-calendar-2026-03-09.xlsx` — Chair calendar, three weeks from 2026-03-09 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `scheduling/chair-roster-and-capabilities.csv` — Chair roster and first-dose capability (text/csv)
- `supplier/delivery-confirmation-Q-78044.pdf` — Supplier delivery confirmation Q-78044 (application/pdf)
- `workbooks/review-capacity.xlsx` — Review capacity — CLIN-0008 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)

## How it is graded

The verifier runs as root after the episode, pulls the finished world over a token-gated, read-only channel that the agent user cannot open, and computes **HubScore** (0–1 reward = score / 100) from executable checks only: required investigations before the first write, provider payload assertions, post-write readbacks, write containment, exact graded answer fields, and semantic milestone aggregation (61 atomic criteria, 24 graded answer fields). No LLM judge is called. Exact call order is not graded.

The sealed contract, expected answer, and oracle policy live only in `tests/` and `solution/`; they are not present in either container image.

## Provenance

Clean-room synthetic data; no real patient, employee, supplier, or organisation is represented. Public Harbor Hub anchors for this family (evaluation-shape inspiration only):

- MedAgentBench: `stanford/medagentbench` — evaluation-shape inspiration only; clean-room task, state, tools, and answer
- PhysicianBench: `josancamon19/physician-bench` — evaluation-shape inspiration only; clean-room task, state, tools, and answer

More: https://blobfish.ai/benchmarks/hubbench
