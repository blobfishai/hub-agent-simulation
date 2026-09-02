# hubbench-secops-002 — Size the billing custody rollover for the week of 15 June

HubBench 1.3.0 · family **SecOps** (`secops`, cluster `security`) · decision mode `quantity` · role `security_operations_coordinator` · as of 2026-06-08.

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

- `approvals/approval-AP-SO-0102.json` — Approval record AP-SO-0102 (application/json)
- `approvals/decision-record.json` — Decision control record — SEC-0002 (application/json)
- `audit/evidence-index.yaml` — Evidence index (application/yaml)
- `audit/evidence-status.yaml` — Evidence readiness — SEC-0002 (application/yaml)
- `audit/system-audit.log` — System audit log — SEC-0002 (text/plain)
- `chat/CHAT-1002.json` — SEC-0002 billing custody reviews week of 06-15 (application/json)
- `collaboration/operations-thread.json` — Operations thread — SEC-0002 (application/json)
- `communications/source-request.eml` — Source integrity request — SEC-0002 (message/rfc822)
- `contracts/provider-contracts.json` — Provider contract — SEC-0002 (application/json)
- `controls/current-authority.md` — Current authority — SEC-0002 (text/markdown)
- `controls/retired-authority.md` — Retired authority — SEC-0002 (text/markdown)
- `controls/source-integrity.pdf` — Source integrity control — SEC-0002 (application/pdf)
- `edr/host-inventory-and-detections.csv` — EDR host inventory and detections (text/csv)
- `exports/live-snapshot.json` — Live pre-action snapshot — SEC-0002 (application/json)
- `exports/starting-state-secops-002.json` — Starting-state export (bridges, invalidation orders, revocations) (application/json)
- `iam/credential-class-catalog.csv` — Credential class catalog: object kinds and revocation channels (text/csv)
- `iam/credential-register-by-grant.xlsx` — Registered credential objects by grant (gross) (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `iam/grant-status-register.csv` — Grant status register (expiry, rotation, revocation, owner deferrals) (text/csv)
- `iam/identity-svc-billing-gw-summary.json` — Identity svc-billing-gw summary with inventory snapshots (IAM export) (application/json)
- `iam/sessions-and-factors-svc-billing-gw.csv` — Sessions and MFA factors for svc-billing-gw (text/csv)
- `iam/token-family-margin-policy.csv` — Token-family margin policy (IAM register) (text/csv)
- `idpvendor/invalidation-confirmation-CR-66120.pdf` — Vendor invalidation confirmation CR-66120 (application/pdf)
- `lineage/record-lineage.csv` — Cross-system record lineage — SEC-0002 (text/csv)
- `messages/THR-1002.eml` — SEC-0002 billing custody rollover — place the order today (message/rfc822)
- `oncall/responder-calendar-2026-06-08.xlsx` — Responder window calendar, three weeks from 2026-06-08 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `oncall/responder-roster-and-qualification.csv` — Responder roster and Tier-2 qualification (text/csv)
- `playbooks/containment-playbook.md` — Credential compromise containment playbook v5 (effective) (text/markdown)
- `playbooks/superseded-containment-playbook-2024.md` — Credential compromise containment playbook 2024 (superseded) (text/markdown)
- `provenance/harbor-open-source-anchors.json` — Open-source benchmark provenance — SecOps (application/json)
- `siem/alert-AL-77522-events.csv` — Correlated events and rule versions behind AL-77522 (text/csv)
- `siem/alert-AL-77522.json` — Alert AL-77522 (SIEM export) (application/json)
- `tickets/ticket-SR-61240.json` — Ticket SR-61240 (service-desk export) (application/json)
- `workbooks/review-capacity.xlsx` — Review capacity — SEC-0002 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)

## How it is graded

The verifier runs as root after the episode, pulls the finished world over a token-gated, read-only channel that the agent user cannot open, and computes **HubScore** (0–1 reward = score / 100) from executable checks only: required investigations before the first write, provider payload assertions, post-write readbacks, write containment, exact graded answer fields, and semantic milestone aggregation (68 atomic criteria, 24 graded answer fields). No LLM judge is called. Exact call order is not graded.

The sealed contract, expected answer, and oracle policy live only in `tests/` and `solution/`; they are not present in either container image.

## Provenance

Clean-room synthetic data; no real patient, employee, supplier, or organisation is represented. Public Harbor Hub anchors for this family (evaluation-shape inspiration only):

- CyberDefense-Bench: `polyvorlabs/cyberdefense-bench` — evaluation-shape inspiration only; clean-room task, state, tools, and answer
- Terminal-Bench 2.1 systems security: `NovitaAI/tb21-systems-security` — evaluation-shape inspiration only; clean-room task, state, tools, and answer
- binary-audit: `binary-audit/binary-audit` — evaluation-shape inspiration only; clean-room task, state, tools, and answer

More: https://blobfish.ai/benchmarks/hubbench
