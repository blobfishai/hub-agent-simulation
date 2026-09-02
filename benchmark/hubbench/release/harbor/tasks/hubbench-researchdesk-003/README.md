# hubbench-researchdesk-003 — Reserve the net-retention methodology review

HubBench 1.0.0 · family **ResearchDesk** (`researchdesk`, cluster `reasoning-knowledge-qa`) · decision mode `schedule` · role `research_analyst` · as of 2026-07-13.

Multi-source internal research across versioned knowledge, metric definitions, source provenance, ranked search, approvals, review capacity, published claims, and evidence packets.

## What the agent gets

The agent works as a non-root user in the `main` container and reaches the isolated, stateful world only through its public surfaces on the `world` service:

- MCP over streamable HTTP, one endpoint per server: `http://world:8765/mcp/<server>`
- the terminal `tool` CLI (`tool list`, `tool schema <name>`, `tool <name> '<json>'`), bound to the same world through `HUBBENCH_URL`
- the REST API under `http://world:8765/api/v1/`
- the web console at `http://world:8765/`

Servers mounted for this task:

- `approvals` — Signed task-scoped research approvals. (2 tools)
- `chat` — Research-team collaboration threads. (2 tools)
- `drive` — Evidence-room documents, workbooks, exports, and provenance. (3 tools)
- `knowledge` — Versioned internal knowledge articles and immutable revision history. (4 tools)
- `messages` — Research-team mailbox. (2 tools)
- `metrics` — Metric definitions and period snapshots with gross, excluded, and supported values. (4 tools)
- `notes` — Stakeholder drafts that are never sent by the benchmark. (1 tools)
- `research` — Published claims and evidence packets with exact source and definition contracts. (4 tools)
- `reviews` — Specialist review capacity and persistent reservations with protected-slot controls. (3 tools)
- `search` — Ranked internal search indexes; rank is never treated as authority. (2 tools)
- `sources` — Independent source-set contracts and source records with verification state. (3 tools)
- `hubbench` — Benchmark-only discovery and structured answer submission controls. (2 tools)

Evidence files under `/workspace/evidence` (30 files):

- `approvals/approval-AP-RSH-0003.json` — Signed research approval AP-RSH-0003 (application/json)
- `approvals/decision-record.json` — Decision control record — RSH-0003 (application/json)
- `audit/evidence-index.yaml` — Evidence index — RSH-0003 (application/yaml)
- `audit/evidence-status.yaml` — Evidence readiness — RSH-0003 (application/yaml)
- `audit/system-audit.log` — System audit log — RSH-0003 (text/plain)
- `collaboration/operations-thread.json` — Operations thread — RSH-0003 (application/json)
- `collaboration/research-thread.json` — Research thread — RSH-0003 (application/json)
- `communications/request.eml` — RSH-0003: Net retention methodology — evidence needed (message/rfc822)
- `communications/source-request.eml` — Source integrity request — RSH-0003 (message/rfc822)
- `contracts/provider-contracts.json` — Provider contract — RSH-0003 (application/json)
- `controls/current-authority.md` — Current authority — RSH-0003 (text/markdown)
- `controls/net-retention-methodology-source-attestation.pdf` — Source attestation — Net retention methodology (application/pdf)
- `controls/retired-authority.md` — Retired authority — RSH-0003 (text/markdown)
- `controls/source-integrity.pdf` — Source integrity control — RSH-0003 (application/pdf)
- `exports/live-snapshot.json` — Live pre-action snapshot — RSH-0003 (application/json)
- `exports/starting-state-researchdesk-003.json` — Research starting state — RSH-0003 (application/json)
- `knowledge/article-ART-0003.json` — Knowledge article — Net retention methodology (application/json)
- `knowledge/revision-history.csv` — Revision history — Net retention methodology (text/csv)
- `lineage/record-lineage.csv` — Cross-system record lineage — RSH-0003 (text/csv)
- `methodology/net-retention-methodology-memo.md` — Methodology memo — Net retention methodology (text/markdown)
- `metrics/definition-net_retention_v4.yaml` — Current definition — net-retention methodology review (application/yaml)
- `metrics/snapshot-SNAP-0003.xlsx` — Controlled metric snapshot — 2026-04-01 to 2026-06-30 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `policy/research-evidence-policy.md` — Research evidence and publication policy v6 (effective) (text/markdown)
- `policy/superseded-research-policy-2025.md` — Research publication policy 2025 (superseded) (text/markdown)
- `provenance/harbor-open-source-anchors.json` — Open-source benchmark provenance — ResearchDesk (application/json)
- `reviews/review-capacity.xlsx` — Research review capacity — RSH-0003 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
- `search/index-results.json` — Search results — net-retention-methodology (application/json)
- `sources/net-retention-methodology-exception-log.csv` — Source exception log — Net retention methodology (text/csv)
- `sources/source-register.csv` — Source register — SRCSET-0003 (text/csv)
- `workbooks/review-capacity.xlsx` — Review capacity — RSH-0003 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)

## How it is graded

The verifier runs as root after the episode, pulls the finished world over a token-gated, read-only channel that the agent user cannot open, and computes **HubScore** (0–1 reward = score / 100) from executable checks only: required investigations before the first write, provider payload assertions, post-write readbacks, write containment, exact graded answer fields, and semantic milestone aggregation (62 atomic criteria, 28 graded answer fields). No LLM judge is called. Exact call order is not graded.

The sealed contract, expected answer, and oracle policy live only in `tests/` and `solution/`; they are not present in either container image.

## Provenance

Clean-room synthetic data; no real patient, employee, supplier, or organisation is represented. Public Harbor Hub anchors for this family (evaluation-shape inspiration only):

- GAIA: `gaia/gaia` — evaluation-shape inspiration only; clean-room task, state, tools, and answer
- DeepSearchQA: `kgmon/deepsearchqa` — evaluation-shape inspiration only; clean-room task, state, tools, and answer
- SimpleQA: `openai/simpleqa` — evaluation-shape inspiration only; clean-room task, state, tools, and answer

More: https://blobfish.ai/benchmarks/hubbench
