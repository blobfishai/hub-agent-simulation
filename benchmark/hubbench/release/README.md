# HubBench 1.2.0 — distribution tree

Deterministic release emitted by `benchmark/hubbench/build_distribution.py` from the committed family releases and reports. Rebuilding it from the same inputs reproduces every byte.

- **ClinicOps** (`clinicops`, cluster `healthcare`): 8 tasks, 34 tools over 10 MCP servers
- **DataDesk** (`datadesk`, cluster `data-engineering-analytics`): 8 tasks, 33 tools over 10 MCP servers
- **DesignOps** (`designops`, cluster `manufacturing-engineering-design`): 8 tasks, 42 tools over 13 MCP servers
- **HostOps** (`hostops`, cluster `terminal-operations`): 8 tasks, 39 tools over 12 MCP servers
- **ITSMDesk** (`itsmdesk`, cluster `it-operations-observability`): 8 tasks, 43 tools over 11 MCP servers
- **PolicyDesk** (`policydesk`, cluster `policy-compliance-instruction-following`): 8 tasks, 41 tools over 16 MCP servers
- **RepoDesk** (`repodesk`, cluster `software-engineering`): 8 tasks, 57 tools over 13 MCP servers
- **ResearchDesk** (`researchdesk`, cluster `reasoning-knowledge-qa`): 8 tasks, 32 tools over 12 MCP servers
- **SciLab** (`scilab`, cluster `scientific-research`): 8 tasks, 43 tools over 11 MCP servers
- **SecOps** (`secops`, cluster `security`): 8 tasks, 48 tools over 14 MCP servers
- **WebStudio** (`webstudio`, cluster `web-product-design`): 8 tasks, 44 tools over 13 MCP servers
- **Workplace** (`workplace`, cluster `customer-workplace-agents`): 8 tasks, 47 tools over 13 MCP servers

Totals: 96 tasks, 503 tools, 3157 evidence files, 6424 atomic criteria; 96/96 oracle strict passes at mean 100.0 HubScore, 96/96 byte-identical replays, 0 false accepts over 960 negative-control executions, 192/192 mutation omissions detected.

## Layout

- `harbor/` — Harbor dataset `blobfishai/hubbench` v1.2.0: `dataset.toml`, `task-digests.json`, and 96 self-contained task packages under `tasks/hubbench-<family>-NNN/` (`task.toml`, `instruction.md`, `README.md`, `environment/`, `tests/`, `solution/`). Root digest `ade39d4b1f539182a7942423ae345243bf4466a8f8172fb5456325a999847bc3`.
- `huggingface/` — Hugging Face dataset payload (`README.md` card, `data/tasks.jsonl`, `assets/`, `contracts/`, `verifiers/`, `ANCHORS.md`, `LICENSE`, `trajectories/`). Payload manifest `f8c83fd3780e5a3fce0429057217b1fe41ddfc39133e9a19c39efcd22db016fc`.
- `reports/` — `release.json` (aggregate receipt with input digests) plus verbatim copies of every family's qualification and reasoning-chain report.
- `tasks/` — one public record per task (no gold values).

## Publish (operator, from the repository root)

```bash
harbor publish benchmark/hubbench/release/harbor/tasks --public -t v1.2.0
harbor publish benchmark/hubbench/release/harbor --no-tasks --public -t v1.2.0
hf upload-large-folder SamuelChien821/hubbench benchmark/hubbench/release/huggingface --repo-type dataset
```

## Containment

`environment/` (both container images) never carries the expected answer, the sealed verifier contract, the oracle policy, the task builder, or scenario data; `tests/` (root verifier) and `solution/` (oracle) do. The verifier reaches the finished world through a token-gated, read-only channel on the world service; the world container only holds the token's SHA-256.
