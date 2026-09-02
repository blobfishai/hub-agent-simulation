# hubbench-repodesk-005 — Backport the ingest fix for this week's hotfix deploys

HubBench 1.3.0 · family **RepoDesk** (`repodesk`, cluster `software-engineering`) · decision mode `quantity` · role `release_engineering_coordinator` · as of 2026-05-04.

Release-engineering decisions around a regression fix against a GitHub-shaped repository, a Jira-shaped issue tracker, a CI evidence register with flaky-test and runner-pool state, a deploy pipeline with release lanes, freeze windows, change records, and feature flags, customer cutover commitments, external certification partners, reviewer availability, and approval records.

## What the agent gets

The agent works as a non-root user in the `main` container and reaches the isolated, stateful world only through its public surfaces on the `world` service:

- MCP over streamable HTTP, one endpoint per server: `http://world:8765/mcp/<server>`
- the terminal `tool` CLI (`tool list`, `tool schema <name>`, `tool <name> '<json>'`), bound to the same world through `HUBBENCH_URL`
- the REST API under `http://world:8765/api/v1/`
- the web console at `http://world:8765/`

Servers mounted for this task:

- `approvals` — Approval workflow records with exact scope. (2 tools)
- `chat` — Release-engineering chat threads. (2 tools)
- `ci` — CI service: gate classes, the verification-evidence register, pipelines and run history, the flaky-test registry, coverage reports, and runner pools. (10 tools)
- `deploy` — Deploy pipeline: release lanes, the lane window calendar, change records, and feature flags. (8 tools)
- `drive` — Shared drive holding the playbook, registers, calendars, and exports. (3 tools)
- `messages` — Release-engineering mailbox. (2 tools)
- `notes` — Stakeholder draft notes (never sent by the benchmark). (1 tools)
- `oncall` — Reviewer and on-call availability calendar. (1 tools)
- `partners` — External certification partners: confirmations and certification orders. (5 tools)
- `scm` — Source control: repositories, components, impact analyses, modules with codeowners and gates, commits, pull requests, reviews, protected-branch rules, and backport requests. (14 tools)
- `success` — Customer success: customer accounts and contracted commitments (cutover dates, penalties). (3 tools)
- `tracker` — Issue tracker: regressions and remediation issues with gate class, scope basis, customer links, and durations. (4 tools)
- `hubbench` — Benchmark-only discovery and structured answer submission controls. (2 tools)

Evidence files under `/workspace/evidence` (38 files):

- `approvals/approval-AP-RD-0105.json` — Approval record AP-RD-0105 (application/json)
- `approvals/decision-record.json` — Decision control record — SHIP-0005 (application/json)
- `audit/evidence-index.yaml` — Evidence index (application/yaml)
- `audit/evidence-status.yaml` — Evidence readiness — SHIP-0005 (application/yaml)
- `audit/system-audit.log` — System audit log — SHIP-0005 (text/plain)
- `chat/CHAT-1005.json` — SHIP-0005 ingest backport — hotfix/26.1.3 (application/json)
- `ci/flaky-test-registry.csv` — Flaky-test registry (quarantine and retry exposure) (text/csv)
- `ci/gate-class-catalog.csv` — Gate class catalog: runs per module and minimum validity (text/csv)
- `ci/pipeline-runs.csv` — Pipelines and recent runs (text/csv)
- `ci/result-status-register.csv` — Result-set status register (status, holds, incident notes) (text/csv)
- `ci/runner-pool-capacity.json` — Runner pool capacity and queue — SHIP-0005 (application/json)
- `ci/verification-results-by-set.xlsx` — Registered verification results by set (gross) (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `collaboration/operations-thread.json` — Operations thread — SHIP-0005 (application/json)
- `communications/source-request.eml` — Source integrity request — SHIP-0005 (message/rfc822)
- `contracts/provider-contracts.json` — Provider contract — SHIP-0005 (application/json)
- `controls/current-authority.md` — Current authority — SHIP-0005 (text/markdown)
- `controls/retired-authority.md` — Retired authority — SHIP-0005 (text/markdown)
- `controls/source-integrity.pdf` — Source integrity control — SHIP-0005 (application/pdf)
- `deploy/lane-calendar-2026-05-04.xlsx` — Lane window calendar, three weeks from 2026-05-04 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `deploy/lane-roster-and-capabilities.csv` — Lane roster and tenant-isolation capability (text/csv)
- `exports/live-snapshot.json` — Live pre-action snapshot — SHIP-0005 (application/json)
- `exports/starting-state-repodesk-005.json` — Starting-state export (changes, certification orders, backports) (application/json)
- `lineage/record-lineage.csv` — Cross-system record lineage — SHIP-0005 (text/csv)
- `messages/THR-1005.eml` — SHIP-0005 ingest hotfix deploys — hotfix branch is behind (message/rfc822)
- `oncall/reviewer-availability.csv` — Reviewer and on-call availability (text/csv)
- `partners/certification-confirmation-CQ-88355.pdf` — Certification confirmation CQ-88355 (application/pdf)
- `playbook/release-engineering-playbook.md` — Release engineering playbook v5 (effective) (text/markdown)
- `playbook/superseded-release-playbook-2024.md` — Release engineering playbook 2024 (superseded) (text/markdown)
- `provenance/harbor-open-source-anchors.json` — Open-source benchmark provenance — RepoDesk (application/json)
- `scm/backport-procedure.md` — Hotfix backport procedure (extract) (text/markdown)
- `scm/commits-release-26.1-fix-range.csv` — Commits on release/26.1 around the fix range (SCM export) (text/csv)
- `scm/component-ingest-fleet-a-impact.json` — Component ingest-fleet-a summary with impact analyses (SCM export) (application/json)
- `scm/fix-range-commit-count-2026-04.xlsx` — Fix-range commit count — April sweep (stale) (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `scm/module-registry.csv` — Module registry: codeowners, gate class, revert / flag gates (text/csv)
- `scm/pull-requests-and-reviews.json` — Pull requests and reviews linked to the case (SCM export) (application/json)
- `success/commitment-COM-ORV-0507.json` — Customer commitment COM-ORV-0507 (customer-success export) (application/json)
- `tracker/issue-LKS-4500.json` — Issue LKS-4500 (tracker export) (application/json)
- `workbooks/review-capacity.xlsx` — Review capacity — SHIP-0005 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)

## How it is graded

The verifier runs as root after the episode, pulls the finished world over a token-gated, read-only channel that the agent user cannot open, and computes **HubScore** (0–1 reward = score / 100) from executable checks only: required investigations before the first write, provider payload assertions, post-write readbacks, write containment, exact graded answer fields, and semantic milestone aggregation (70 atomic criteria, 25 graded answer fields). No LLM judge is called. Exact call order is not graded.

The sealed contract, expected answer, and oracle policy live only in `tests/` and `solution/`; they are not present in either container image.

## Provenance

Clean-room synthetic data; no real patient, employee, supplier, or organisation is represented. Public Harbor Hub anchors for this family (evaluation-shape inspiration only):

- SWE-bench Verified: `swe-bench/swe-bench-verified` — evaluation-shape inspiration only; clean-room task, state, tools, and answer
- SWE-bench Pro: `scale-ai/swe-bench-pro` — evaluation-shape inspiration only; clean-room task, state, tools, and answer
- Aider Polyglot: `aider/aider-polyglot` — evaluation-shape inspiration only; clean-room task, state, tools, and answer

More: https://blobfish.ai/benchmarks/hubbench
