# hubbench-secops-001 — Contain the treasury identity after the impossible-travel consent alert

HubBench 1.2.0 · family **SecOps** (`secops`, cluster `security`) · decision mode `plan` · role `security_operations_coordinator` · as of 2026-06-08.

Defensive credential-compromise triage and containment decisions against a SIEM with versioned detection rules, an EDR host inventory, an IAM identity register with sessions, factors, and credential-object grants, a cloud key registry, a security ticket queue, containment-tier playbooks, a responder on-call calendar, identity-provider vendor invalidation confirmations, and approval records.

## What the agent gets

The agent works as a non-root user in the `main` container and reaches the isolated, stateful world only through its public surfaces on the `world` service:

- MCP over streamable HTTP, one endpoint per server: `http://world:8765/mcp/<server>`
- the terminal `tool` CLI (`tool list`, `tool schema <name>`, `tool <name> '<json>'`), bound to the same world through `HUBBENCH_URL`
- the REST API under `http://world:8765/api/v1/`
- the web console at `http://world:8765/`

Servers mounted for this task:

- `approvals` — Approval workflow records with exact scope. (2 tools)
- `chat` — SOC incident chat threads. (2 tools)
- `cloudiam` — Cloud key registry: access-key register and gross credential-object balances. (2 tools)
- `drive` — Shared drive holding playbooks, registers, calendars, and exports. (3 tools)
- `edr` — Endpoint detection and response: host inventory with isolation state and detections. (4 tools)
- `iam` — Workforce identity register: identities, owners, inventory snapshots, sessions, MFA factors, credential classes, grant register, and tenant revocations. (10 tools)
- `idpvendor` — Identity-provider and key-custody vendor portal: invalidation confirmations and orders. (5 tools)
- `messages` — Security-operations mailbox. (2 tools)
- `notes` — Stakeholder draft notes (never sent by the benchmark). (1 tools)
- `oncall` — On-call roster: responders, window calendar, and incident bridges. (6 tools)
- `playbooks` — Containment playbook library: tier records with revocation rules and authority levels. (2 tools)
- `servicedesk` — Security ticket queue with object basis, tier, and review durations. (2 tools)
- `siem` — Security information and event management: alerts, correlated events, and versioned detection rules. (5 tools)
- `hubbench` — Benchmark-only discovery and structured answer submission controls. (2 tools)

Evidence files under `/workspace/evidence` (33 files):

- `approvals/approval-AP-SO-0101.json` — Approval record AP-SO-0101 (application/json)
- `approvals/decision-record.json` — Decision control record — SEC-0001 (application/json)
- `audit/evidence-index.yaml` — Evidence index (application/yaml)
- `audit/evidence-status.yaml` — Evidence readiness — SEC-0001 (application/yaml)
- `audit/system-audit.log` — System audit log — SEC-0001 (text/plain)
- `chat/CHAT-1001.json` — SEC-0001 treasury identity containment (application/json)
- `collaboration/operations-thread.json` — Operations thread — SEC-0001 (application/json)
- `communications/source-request.eml` — Source integrity request — SEC-0001 (message/rfc822)
- `contracts/provider-contracts.json` — Provider contract — SEC-0001 (application/json)
- `controls/current-authority.md` — Current authority — SEC-0001 (text/markdown)
- `controls/retired-authority.md` — Retired authority — SEC-0001 (text/markdown)
- `controls/source-integrity.pdf` — Source integrity control — SEC-0001 (application/pdf)
- `edr/host-inventory-and-detections.csv` — EDR host inventory and detections (text/csv)
- `exports/live-snapshot.json` — Live pre-action snapshot — SEC-0001 (application/json)
- `exports/starting-state-secops-001.json` — Starting-state export (bridges, invalidation orders, revocations) (application/json)
- `iam/credential-class-catalog.csv` — Credential class catalog: object kinds and revocation channels (text/csv)
- `iam/credential-register-by-grant.xlsx` — Registered credential objects by grant (gross) (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `iam/grant-status-register.csv` — Grant status register (expiry, rotation, revocation, owner deferrals) (text/csv)
- `iam/identity-m.arendse-summary.json` — Identity m.arendse summary with inventory snapshots (IAM export) (application/json)
- `iam/sessions-and-factors-m.arendse.csv` — Sessions and MFA factors for m.arendse (text/csv)
- `idpvendor/halyard-invalidation-terms.md` — Halyard Identity Cloud — invalidation service terms (extract) (text/markdown)
- `idpvendor/invalidation-confirmation-IR-88214.pdf` — Vendor invalidation confirmation IR-88214 (application/pdf)
- `lineage/record-lineage.csv` — Cross-system record lineage — SEC-0001 (text/csv)
- `messages/THR-1001.eml` — SEC-0001 treasury identity — what is really contained before the regulator session? (message/rfc822)
- `oncall/responder-calendar-2026-06-08.xlsx` — Responder window calendar, three weeks from 2026-06-08 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `oncall/responder-roster-and-qualification.csv` — Responder roster and Tier-2 qualification (text/csv)
- `playbooks/containment-playbook.md` — Credential compromise containment playbook v5 (effective) (text/markdown)
- `playbooks/superseded-containment-playbook-2024.md` — Credential compromise containment playbook 2024 (superseded) (text/markdown)
- `provenance/harbor-open-source-anchors.json` — Open-source benchmark provenance — SecOps (application/json)
- `siem/alert-AL-88811-events.csv` — Correlated events and rule versions behind AL-88811 (text/csv)
- `siem/alert-AL-88811.json` — Alert AL-88811 (SIEM export) (application/json)
- `tickets/ticket-SR-61203.json` — Ticket SR-61203 (service-desk export) (application/json)
- `workbooks/review-capacity.xlsx` — Review capacity — SEC-0001 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)

## How it is graded

The verifier runs as root after the episode, pulls the finished world over a token-gated, read-only channel that the agent user cannot open, and computes **HubScore** (0–1 reward = score / 100) from executable checks only: required investigations before the first write, provider payload assertions, post-write readbacks, write containment, exact graded answer fields, and semantic milestone aggregation (72 atomic criteria, 27 graded answer fields). No LLM judge is called. Exact call order is not graded.

The sealed contract, expected answer, and oracle policy live only in `tests/` and `solution/`; they are not present in either container image.

## Provenance

Clean-room synthetic data; no real patient, employee, supplier, or organisation is represented. Public Harbor Hub anchors for this family (evaluation-shape inspiration only):

- CyberDefense-Bench: `polyvorlabs/cyberdefense-bench` — evaluation-shape inspiration only; clean-room task, state, tools, and answer
- Terminal-Bench 2.1 systems security: `NovitaAI/tb21-systems-security` — evaluation-shape inspiration only; clean-room task, state, tools, and answer
- binary-audit: `binary-audit/binary-audit` — evaluation-shape inspiration only; clean-room task, state, tools, and answer

More: https://blobfish.ai/benchmarks/hubbench
