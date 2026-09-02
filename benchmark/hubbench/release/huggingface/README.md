---
license: cc-by-4.0
language:
- en
task_categories:
- question-answering
- text-generation
tags:
- agents
- benchmarking
- tool-use
- mcp
- harbor
- stateful
- multi-system
- deterministic-verifier
- synthetic
- healthcare
- data-engineering-analytics
- terminal-operations
- policy-compliance-instruction-following
- reasoning-knowledge-qa
- scientific-research
- customer-workplace-agents
pretty_name: HubBench
size_categories:
- n<1K
---

# HubBench 1.1.0

**One Blobfish-authored, oracle-proven benchmark family per Harbor Hub professional-domain cluster.** Every task is an employee decision worked over a dependent chain of evidence — never a lookup — against mock stateful tools over an isolated SQLite world. The agent reaches the world only through its public surfaces (MCP over streamable HTTP, a terminal `tool` CLI, a REST API, and a web console); a deterministic verifier (**HubScore**) grades the finished world from executable checks only. Zero LLM-judge calls.

Released families: ClinicOps (healthcare), DataDesk (data-engineering-analytics), HostOps (terminal-operations), PolicyDesk (policy-compliance-instruction-following), ResearchDesk (reasoning-knowledge-qa), SciLab (scientific-research), Workplace (customer-workplace-agents). 56 tasks, 269 provider-shaped tools across 84 MCP servers, 1767 agent-visible evidence files, 3649 atomic criteria.

## Families

| Family | Cluster | Tasks | MCP servers | Tools | Criteria / task | Graded answer fields / task | Evidence files / task | Harbor Hub anchors |
|---|---|---|---|---|---|---|---|---|
| ClinicOps (`clinicops`) | healthcare | 8 | 10 | 34 | 61–66 | 24–27 | 29–31 | `stanford/medagentbench`, `josancamon19/physician-bench` |
| DataDesk (`datadesk`) | data-engineering-analytics | 8 | 10 | 33 | 60–62 | 23–24 | 30–32 | `snowflake-labs/data-eng-bench`, `dbt-labs/ade-bench` |
| HostOps (`hostops`) | terminal-operations | 8 | 12 | 39 | 62–67 | 24–27 | 30–33 | `terminal-bench/terminal-bench`, `NovitaAI/tb21-file-recovery` |
| PolicyDesk (`policydesk`) | policy-compliance-instruction-following | 8 | 16 | 41 | 65–66 | 25–27 | 30–32 | `openthoughts/tasktrove-nemotron-gym-instruction-following-adversarial-v3`, `strongreject/strongreject`, `islo-labs/reward-hack-bench` |
| ResearchDesk (`researchdesk`) | reasoning-knowledge-qa | 8 | 12 | 32 | 60–62 | 27–28 | 30 | `gaia/gaia`, `kgmon/deepsearchqa`, `openai/simpleqa` |
| SciLab (`scilab`) | scientific-research | 8 | 11 | 43 | 68–73 | 24–28 | 32–36 | `scienceagentbench/scienceagentbench`, `futurehouse/bixbench`, `futurehouse/labbench` |
| Workplace (`workplace`) | customer-workplace-agents | 8 | 13 | 47 | 70–74 | 25–27 | 34–35 | `theagentcompany/theagentcompany`, `sierra-research/tau3-bench`, `apple/mmau`, `gorilla/bfcl` |

## HubScore

HubScore is contract-driven and deterministic: required investigations before the first write, provider payload assertions on the persisted state change, post-write readbacks, write containment, exact graded answer fields (every intermediate value of the decision chain), and semantic milestone aggregation into 14 weighted milestones summing to 100. Reward = HubScore / 100; a task is a strict pass only when every milestone passes. Exact call order is not graded.

## Qualification (computed from the committed reports)

| Family | Oracle strict passes (mean HubScore) | Deterministic replays | Negative-control executions | False accepts | Mutation omissions detected | Executions |
|---|---|---|---|---|---|---|
| `clinicops` | 8/8 at 100.0 | 8/8 | 80 across 10 policies | 0 | 16/16 | 112 |
| `datadesk` | 8/8 at 100.0 | 8/8 | 80 across 10 policies | 0 | 16/16 | 112 |
| `hostops` | 8/8 at 100.0 | 8/8 | 80 across 10 policies | 0 | 16/16 | 112 |
| `policydesk` | 8/8 at 100.0 | 8/8 | 80 across 10 policies | 0 | 16/16 | 112 |
| `researchdesk` | 8/8 at 100.0 | 8/8 | 80 across 10 policies | 0 | 16/16 | 112 |
| `scilab` | 8/8 at 100.0 | 8/8 | 80 across 10 policies | 0 | 16/16 | 112 |
| `workplace` | 8/8 at 100.0 | 8/8 | 80 across 10 policies | 0 | 16/16 | 112 |

Totals: 56/56 oracle strict passes at mean 100.0; 56/56 byte-identical replays; 560 negative-control executions across 10 policies (incomplete_read, missing_readback, noop, shortcut, state_only, unauthorized_write, write_before_read, wrong_decision, wrong_evidence, wrong_value) with 0 false accepts; 112/112 mutation omissions detected; 784 qualification executions in total.

## Reasoning-chain audit (computed from the committed reports)

Measured with the unmodified portfolio audit (`benchmark/reasoning_chain_audit.py`, hop classes H1–H13):

| Family | Passing tasks | Chain depth | Hop coverage H1–H13 | Dependent derivations | Evidence reads before decision | Source systems | Graded answer fields |
|---|---|---|---|---|---|---|---|
| `clinicops` | 8/8 | 8–8 | 8/8 on every hop | 23–26 | 26–26 | 9–9 | 24–27 |
| `datadesk` | 8/8 | 8–8 | 8/8 on every hop | 22–23 | 26–26 | 8–9 | 23–24 |
| `hostops` | 8/8 | 8–8 | 8/8 on every hop | 23–26 | 27–27 | 11–11 | 24–27 |
| `policydesk` | 8/8 | 8–8 | 8/8 on every hop | 24–26 | 28–28 | 15–15 | 25–27 |
| `researchdesk` | 8/8 | 7–8 | 3–8/8 | 22–23 | 26–26 | 10–10 | 27–28 |
| `scilab` | 8/8 | 8–8 | 8/8 on every hop | 23–27 | 32–32 | 10–10 | 24–28 |
| `workplace` | 8/8 | 8–8 | 8/8 on every hop | 24–26 | 33–36 | 11–12 | 25–27 |

Totals: 56/56 tasks pass; every one of the 13 hop classes is covered by all 56 tasks (3–8 per hop); dependent derivations 22–27; evidence reads before the decision 26–36.

## Run on Harbor

```bash
harbor run -d blobfishai/hubbench@v1.1.0 -a <agent> -m <provider/model>
```

Harbor dataset: `blobfishai/hubbench` (56 task packages `blobfishai/hubbench-<family>-NNN`, root digest `86f5805930e7674b6b32ce39fe07fe188fc8f24b6a30137c1a67d1d3a893e2af`). Each package is self-contained on a digest-pinned `python:3.12-slim` base: an agent container (non-root `agent`, `tool` on PATH, evidence under `/workspace/evidence`) and a `world` service on port 8765. The sealed contract, expected answer, and oracle policy exist only in `tests/` (root verifier) and `solution/` (oracle replayed through the HTTP surfaces).

## Layout

- `data/tasks.jsonl` — one public record per task: identity, cluster, mode, instruction, mounted servers and tools, evidence file list, graded answer *field names* (no gold values), digests.
- `assets/<task>/…` — the agent-visible evidence files in their native formats (`.xlsx`, `.pdf`, `.eml`, `.csv`, `.json`, `.md`, `.yaml`, `.log`).
- `contracts/tools.json` — the provider-shaped MCP tool contracts per family.
- `verifiers/<task>.json` — the sealed verifier contracts (expected answer, assertions, calculations, required investigations, readbacks). Keep them away from the agent.
- `ANCHORS.md` — public Harbor Hub anchors and the clean-room boundary per family.
- `trajectories/` — `index.json`, 56 Docker-gated oracle traces under `reference/`, and 1 imported model run(s) under `model/<run>/`. Oracle traces disclose valid solutions and are excluded from rankings; every model `run.json` states whether the run is ranked or a disclosed partial run.

## Synthetic-data notice

All organisations, people, patients, employees, suppliers, records, messages, and values are synthetic and clean-room authored. Nothing was copied from any upstream benchmark; see `ANCHORS.md`. This dataset is for agent evaluation and research; it is not clinical, operational, financial, or legal advice.

Page and leaderboard: https://blobfish.ai/benchmarks/hubbench · Source: https://github.com/blobfishai/hub-agent-simulation · Harbor: https://hub.harborframework.com/datasets/blobfishai/hubbench/latest
