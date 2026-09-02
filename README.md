# hub-agent-simulation

> **Simulation only.** Every organisation, person, patient, host, dataset, reagent,
> supplier, ticket, quantity, amount, document, approval, and message in this
> repository is clean-room synthetic test data.

`hub-agent-simulation` is the executable source repository for
[HubBench](https://blobfish.ai/benchmarks/hubbench), Blobfish AI's counterpart to
the open-source agent benchmarks listed on
[hub.harborframework.com](https://hub.harborframework.com/datasets): one
Blobfish-authored, oracle-proven benchmark family per professional-domain cluster,
each a stateful multi-system world that an agent reaches as **MCP servers** (stdio
and streamable HTTP, one per mock provider), a **REST API**, a **web console**, and a
**terminal `tool` CLI** — all over one isolated SQLite world — graded by the
deterministic **HubScore** verifier with zero LLM-judge calls.

Every task is an employee decision worked over a dependent chain of evidence,
never a lookup: the request → the operative policy or spec → quantities from live
records minus the excluded ones → a capacity calendar with protected windows → a
vendor or partner lead time → three costed alternatives with outcome, incremental
cost, and authority status → a controlled state change, its readback, and a
stakeholder draft → the exact graded answer with every intermediate derivation.

## Releases

**v1.1.0 (published 2026-09-01)** — 7 families / 56 tasks on Harbor and Hugging Face,
269 tools, 1,767 agent-visible evidence files, and 3,649 deterministic criteria.
Every task passed the exact Docker package gate at reward 1.0 with zero errors or
retries; the Hugging Face payload publishes all 56 oracle traces plus five disclosed
model-pilot traces. The compose healthcheck probes the world service's private
`/health` endpoint instead of the graded task endpoint. **v1.0.0** remains the
immutable five-family / 40-task predecessor.

| Family | Hub cluster | Tasks | MCP servers | Tools |
|---|---|---|---|---|
| ClinicOps (`clinicops`) | healthcare | 8 | 10 | 34 |
| DataDesk (`datadesk`) | data-engineering-analytics | 8 | 10 | 33 |
| HostOps (`hostops`) | terminal-operations | 8 | 12 | 39 |
| PolicyDesk (`policydesk`) | policy-compliance-instruction-following | 8 | 16 | 41 |
| ResearchDesk (`researchdesk`) | reasoning-knowledge-qa | 8 | 12 | 32 |
| SciLab (`scilab`) | scientific-research | 8 | 11 | 43 |
| Workplace (`workplace`) | customer-workplace-agents | 8 | 13 | 47 |

Qualification across the 56 released tasks (784 executions): 56/56 oracle strict
passes at a mean HubScore of 100.0, 56/56 byte-identical replays,
560 negative-control executions across 10 attack policies with 0 false
accepts, 112/112 mutation omissions detected; reasoning-chain audit
56/56 with hop classes H1–H13 covered. Every number is recomputed from
`benchmark/hubbench/reports/` and `benchmark/hubbench/release/reports/release.json`
by the tests — nothing here is typed by hand.

6 more families (deskops, webstudio, itsmdesk, secops, designops, repodesk) complete the thirteen-cluster map and
are released as they clear the same admission gate; each new tag republishes
Harbor and Hugging Face and updates `benchmark/hubbench/reports/publication.json`.

## Distribution

- **Website** — https://blobfish.ai/benchmarks/hubbench (leaderboard, task
  browser, asset room, environment and tool contract, trajectories, methodology)
- **Harbor** — https://hub.harborframework.com/datasets/blobfishai/hubbench
  (`harbor run -d blobfishai/hubbench@v1.1.0 -a <agent>`; task packages
  `blobfishai/hubbench-<family>-NNN`)
- **Hugging Face** — https://huggingface.co/datasets/SamuelChien821/hubbench
  (dataset card, public task records, evidence files, tool contracts, sealed
  verifier contracts)
- **Source** — this repository (Apache-2.0 code, CC BY 4.0 data)

## Quickstart

```bash
python3 -m pytest benchmark/hubbench -q                     # engine, families, surfaces, distribution, model runs

# Serve one task: MCP over streamable HTTP + REST API + web console in one process
python3 -m hubbench.engine.http --family clinicops --task clinicops-001 \
    --db /tmp/clinicops-001.db --fresh --host 0.0.0.0 --port 8765      # run from benchmark/
curl -s localhost:8765/api/v1/task | head -c 400
curl -s -X POST localhost:8765/mcp/pharmacy -H 'content-type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
HUBBENCH_URL=http://localhost:8765 benchmark/hubbench/bin/tool list

# Stdio MCP server and the local CLI over the same world
python3 -m hubbench.engine.server --family hostops --task hostops-001 --db /tmp/hostops-001.db --fresh
HUBBENCH_FAMILY=hostops HUBBENCH_TASK=hostops-001 benchmark/hubbench/bin/tool list

# Rebuild, qualify, audit, and distribute a family
python3 benchmark/hubbench/build_release.py --family scilab
python3 benchmark/hubbench/qualify.py --family scilab --write
python3 benchmark/hubbench/chain_adapter.py --family scilab --write
python3 benchmark/hubbench/build_distribution.py

# Run the packaged oracle against a published task from the registry (Docker)
harbor run -d blobfishai/hubbench@v1.1.0 -a oracle
```

Python 3.12 standard library only — no third-party runtime dependency; `pytest`
for the test suite.

## Model runs

`benchmark/hubbench/model_runs/` holds imported Harbor model jobs (durable world
call trace, HubScore verdict, token and cost receipt per trial). A run is ranked
only when it completed every published task once with zero errors and retries;
the stratified GPT-5.6 Luna pilot (Codex 0.151.0, max reasoning; five tasks spanning
the v1.0.0 families) is a disclosed partial run: 5/5 completed, 0 errors, HubScore
52.35–74.41 (mean 66.22), no strict passes, about $0.07 per task — trajectories
only, never ranked.

## Repository layout

```text
benchmark/hubbench/
├── engine/                 domain-agnostic engine: world, verifier, decision model, evaluation,
│                           MCP (stdio + HTTP), REST, web console, CLI, release + distribution emitters
├── families/<slug>/        one family: schema.sql, tools.py, specs, scenarios, build.py, release/
├── reports/                qualification + reasoning-chain reports, reference trajectories
├── release/                Harbor dataset + task packages, Hugging Face payload, receipts
├── tests/                  engine, per-family, surfaces, parity, distribution, chain-audit tests
├── site_data.py            derives the blobfish.ai explorer page data from the release
└── README.md               engine, families, surfaces, and distribution in depth
benchmark/chain_adapters/   the reasoning-chain audit adapter (hop classes H1–H13)
benchmark/realism-standard.json  the admission standard every task is measured against
```

## Provenance and licences

HubBench is independently authored. Each family names the public Harbor Hub
datasets whose *evaluation shape* informed it (see
`benchmark/hubbench/release/huggingface/ANCHORS.md`); no upstream task, fixture,
prompt, seed record, attachment, answer, or score was copied, adapted,
redistributed, or claimed. The engine is a port of the FactoryBench-100 engine
(Apache-2.0, Blobfish AI) — see `NOTICE`. Code is licensed under Apache-2.0
(`LICENSE`); benchmark data under CC BY 4.0 (`LICENSE-DATA`).
