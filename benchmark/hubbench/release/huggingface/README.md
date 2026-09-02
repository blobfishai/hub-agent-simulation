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
- manufacturing-engineering-design
- computer-use-gui
- terminal-operations
- it-operations-observability
- policy-compliance-instruction-following
- software-engineering
- reasoning-knowledge-qa
- scientific-research
- security
- web-product-design
- customer-workplace-agents
pretty_name: HubBench
size_categories:
- n<1K
---

# HubBench 1.3.0

**One Blobfish-authored, oracle-proven benchmark family per Harbor Hub professional-domain cluster.** Every task is an employee decision worked over a dependent chain of evidence — never a lookup — against mock stateful tools over an isolated SQLite world. The agent reaches the world only through its public surfaces (MCP over streamable HTTP, a terminal `tool` CLI, a REST API, and a web console); a deterministic verifier (**HubScore**) grades the finished world from executable checks only. Zero LLM-judge calls.

Released families: ClinicOps (healthcare), DataDesk (data-engineering-analytics), DesignOps (manufacturing-engineering-design), DeskOps (computer-use-gui), HostOps (terminal-operations), ITSMDesk (it-operations-observability), PolicyDesk (policy-compliance-instruction-following), RepoDesk (software-engineering), ResearchDesk (reasoning-knowledge-qa), SciLab (scientific-research), SecOps (security), WebStudio (web-product-design), Workplace (customer-workplace-agents). 104 tasks, 554 provider-shaped tools across 161 MCP servers, 3450 agent-visible evidence files, 7001 atomic criteria.

## Families

| Family | Cluster | Tasks | MCP servers | Tools | Criteria / task | Graded answer fields / task | Evidence files / task | Harbor Hub anchors |
|---|---|---|---|---|---|---|---|---|
| ClinicOps (`clinicops`) | healthcare | 8 | 10 | 34 | 61–66 | 24–27 | 29–31 | `stanford/medagentbench`, `josancamon19/physician-bench` |
| DataDesk (`datadesk`) | data-engineering-analytics | 8 | 10 | 33 | 60–62 | 23–24 | 30–32 | `snowflake-labs/data-eng-bench`, `dbt-labs/ade-bench` |
| DesignOps (`designops`) | manufacturing-engineering-design | 8 | 13 | 42 | 65–73 | 24–31 | 32–35 | `gnucleus-ai/cad-bench`, `hwe-bench/hwe-bench`, `blobfishai/factorybench-100` |
| DeskOps (`deskops`) | computer-use-gui | 8 | 13 | 51 | 71–74 | 27–30 | 35–37 | `xlang-ai/osworld-verified`, `android-bench/android-bench` |
| HostOps (`hostops`) | terminal-operations | 8 | 12 | 39 | 62–67 | 24–27 | 30–33 | `terminal-bench/terminal-bench`, `NovitaAI/tb21-file-recovery` |
| ITSMDesk (`itsmdesk`) | it-operations-observability | 8 | 11 | 43 | 65–71 | 25–30 | 33–34 | `vibrantlabsai/itsm-bench`, `grafana/o11y-bench`, `quesma/otel-bench` |
| PolicyDesk (`policydesk`) | policy-compliance-instruction-following | 8 | 16 | 41 | 65–66 | 25–27 | 30–32 | `openthoughts/tasktrove-nemotron-gym-instruction-following-adversarial-v3`, `strongreject/strongreject`, `islo-labs/reward-hack-bench` |
| RepoDesk (`repodesk`) | software-engineering | 8 | 13 | 57 | 70–78 | 25–31 | 37–40 | `swe-bench/swe-bench-verified`, `scale-ai/swe-bench-pro`, `aider/aider-polyglot` |
| ResearchDesk (`researchdesk`) | reasoning-knowledge-qa | 8 | 12 | 32 | 60–62 | 27–28 | 30 | `gaia/gaia`, `kgmon/deepsearchqa`, `openai/simpleqa` |
| SciLab (`scilab`) | scientific-research | 8 | 11 | 43 | 68–73 | 24–28 | 32–36 | `scienceagentbench/scienceagentbench`, `futurehouse/bixbench`, `futurehouse/labbench` |
| SecOps (`secops`) | security | 8 | 14 | 48 | 68–72 | 24–27 | 33–34 | `polyvorlabs/cyberdefense-bench`, `NovitaAI/tb21-systems-security`, `binary-audit/binary-audit` |
| WebStudio (`webstudio`) | web-product-design | 8 | 13 | 44 | 66–72 | 24–28 | 34–36 | `webgen-bench/webgen-bench`, `open-design/open-design`, `thetalab/vector-edit-gym` |
| Workplace (`workplace`) | customer-workplace-agents | 8 | 13 | 47 | 70–74 | 25–27 | 34–35 | `theagentcompany/theagentcompany`, `sierra-research/tau3-bench`, `apple/mmau`, `gorilla/bfcl` |

## HubScore

HubScore is contract-driven and deterministic: required investigations before the first write, provider payload assertions on the persisted state change, post-write readbacks, write containment, exact graded answer fields (every intermediate value of the decision chain), and semantic milestone aggregation into 14 weighted milestones summing to 100. Reward = HubScore / 100; a task is a strict pass only when every milestone passes. Exact call order is not graded.

## Qualification (computed from the committed reports)

| Family | Oracle strict passes (mean HubScore) | Deterministic replays | Negative-control executions | False accepts | Mutation omissions detected | Executions |
|---|---|---|---|---|---|---|
| `clinicops` | 8/8 at 100.0 | 8/8 | 80 across 10 policies | 0 | 16/16 | 112 |
| `datadesk` | 8/8 at 100.0 | 8/8 | 80 across 10 policies | 0 | 16/16 | 112 |
| `designops` | 8/8 at 100.0 | 8/8 | 80 across 10 policies | 0 | 16/16 | 112 |
| `deskops` | 8/8 at 100.0 | 8/8 | 80 across 10 policies | 0 | 16/16 | 112 |
| `hostops` | 8/8 at 100.0 | 8/8 | 80 across 10 policies | 0 | 16/16 | 112 |
| `itsmdesk` | 8/8 at 100.0 | 8/8 | 80 across 10 policies | 0 | 16/16 | 112 |
| `policydesk` | 8/8 at 100.0 | 8/8 | 80 across 10 policies | 0 | 16/16 | 112 |
| `repodesk` | 8/8 at 100.0 | 8/8 | 80 across 10 policies | 0 | 16/16 | 112 |
| `researchdesk` | 8/8 at 100.0 | 8/8 | 80 across 10 policies | 0 | 16/16 | 112 |
| `scilab` | 8/8 at 100.0 | 8/8 | 80 across 10 policies | 0 | 16/16 | 112 |
| `secops` | 8/8 at 100.0 | 8/8 | 80 across 10 policies | 0 | 16/16 | 112 |
| `webstudio` | 8/8 at 100.0 | 8/8 | 80 across 10 policies | 0 | 16/16 | 112 |
| `workplace` | 8/8 at 100.0 | 8/8 | 80 across 10 policies | 0 | 16/16 | 112 |

Totals: 104/104 oracle strict passes at mean 100.0; 104/104 byte-identical replays; 1040 negative-control executions across 10 policies (incomplete_read, missing_readback, noop, shortcut, state_only, unauthorized_write, write_before_read, wrong_decision, wrong_evidence, wrong_value) with 0 false accepts; 208/208 mutation omissions detected; 1456 qualification executions in total.

## Reasoning-chain audit (computed from the committed reports)

Measured with the unmodified portfolio audit (`benchmark/reasoning_chain_audit.py`, hop classes H1–H13):

| Family | Passing tasks | Chain depth | Hop coverage H1–H13 | Dependent derivations | Evidence reads before decision | Source systems | Graded answer fields |
|---|---|---|---|---|---|---|---|
| `clinicops` | 8/8 | 8–8 | 8/8 on every hop | 23–26 | 26–26 | 9–9 | 24–27 |
| `datadesk` | 8/8 | 8–8 | 8/8 on every hop | 22–23 | 26–26 | 8–9 | 23–24 |
| `designops` | 8/8 | 8–8 | 8/8 on every hop | 23–30 | 29–29 | 12–12 | 24–31 |
| `deskops` | 8/8 | 8–8 | 8/8 on every hop | 26–29 | 32–32 | 12–12 | 27–30 |
| `hostops` | 8/8 | 8–8 | 8/8 on every hop | 23–26 | 27–27 | 11–11 | 24–27 |
| `itsmdesk` | 8/8 | 8–8 | 8/8 on every hop | 24–29 | 29–29 | 10–10 | 25–30 |
| `policydesk` | 8/8 | 8–8 | 8/8 on every hop | 24–26 | 28–28 | 15–15 | 25–27 |
| `repodesk` | 8/8 | 8–8 | 8/8 on every hop | 24–30 | 34–34 | 12–12 | 25–31 |
| `researchdesk` | 8/8 | 7–8 | 3–8/8 | 22–23 | 26–26 | 10–10 | 27–28 |
| `scilab` | 8/8 | 8–8 | 8/8 on every hop | 23–27 | 32–32 | 10–10 | 24–28 |
| `secops` | 8/8 | 8–8 | 8/8 on every hop | 23–26 | 33–33 | 12–12 | 24–27 |
| `webstudio` | 8/8 | 8–8 | 8/8 on every hop | 23–27 | 31–31 | 12–12 | 24–28 |
| `workplace` | 8/8 | 8–8 | 8/8 on every hop | 24–26 | 33–36 | 11–12 | 25–27 |

Totals: 104/104 tasks pass; every one of the 13 hop classes is covered by all 104 tasks (3–8 per hop); dependent derivations 22–30; evidence reads before the decision 26–36.

## Run on Harbor

```bash
harbor run -d blobfishai/hubbench@v1.3.0 -a <agent> -m <provider/model>
```

Harbor dataset: `blobfishai/hubbench` (104 task packages `blobfishai/hubbench-<family>-NNN`, root digest `d3644e1bdfbd3bd0cb2e03fcfd9cbee416ab74956fad25ee26644811fa9cfe72`). Each package is self-contained on a digest-pinned `python:3.12-slim` base: an agent container (non-root `agent`, `tool` on PATH, evidence under `/workspace/evidence`) and a `world` service on port 8765. The sealed contract, expected answer, and oracle policy exist only in `tests/` (root verifier) and `solution/` (oracle replayed through the HTTP surfaces).

## Layout

- `data/tasks.jsonl` — one public record per task: identity, cluster, mode, instruction, mounted servers and tools, evidence file list, graded answer *field names* (no gold values), digests.
- `assets/<task>/…` — the agent-visible evidence files in their native formats (`.xlsx`, `.pdf`, `.eml`, `.csv`, `.json`, `.md`, `.yaml`, `.log`).
- `contracts/tools.json` — the provider-shaped MCP tool contracts per family.
- `verifiers/<task>.json` — the sealed verifier contracts (expected answer, assertions, calculations, required investigations, readbacks). Keep them away from the agent.
- `ANCHORS.md` — public Harbor Hub anchors and the clean-room boundary per family.
- `trajectories/` — `index.json`, 104 Docker-gated oracle traces under `reference/`, and 1 imported model run(s) under `model/<run>/`. Oracle traces disclose valid solutions and are excluded from rankings; every model `run.json` states whether the run is ranked or a disclosed partial run.

## Synthetic-data notice

All organisations, people, patients, employees, suppliers, records, messages, and values are synthetic and clean-room authored. Nothing was copied from any upstream benchmark; see `ANCHORS.md`. This dataset is for agent evaluation and research; it is not clinical, operational, financial, or legal advice.

Page and leaderboard: https://blobfish.ai/benchmarks/hubbench · Source: https://github.com/blobfishai/hub-agent-simulation · Harbor: https://hub.harborframework.com/datasets/blobfishai/hubbench/latest
