# HubBench 1.0.0 — distribution tree

Deterministic release emitted by `benchmark/hubbench/build_distribution.py` from the committed family releases and reports. Rebuilding it from the same inputs reproduces every byte.

- **ClinicOps** (`clinicops`, cluster `healthcare`): 8 tasks, 34 tools over 10 MCP servers
- **DataDesk** (`datadesk`, cluster `data-engineering-analytics`): 8 tasks, 33 tools over 10 MCP servers
- **HostOps** (`hostops`, cluster `terminal-operations`): 8 tasks, 39 tools over 12 MCP servers
- **ResearchDesk** (`researchdesk`, cluster `reasoning-knowledge-qa`): 8 tasks, 32 tools over 12 MCP servers
- **SciLab** (`scilab`, cluster `scientific-research`): 8 tasks, 43 tools over 11 MCP servers

Totals: 40 tasks, 181 tools, 1243 evidence files, 2548 atomic criteria; 40/40 oracle strict passes at mean 100.0 HubScore, 40/40 byte-identical replays, 0 false accepts over 400 negative-control executions, 80/80 mutation omissions detected.

## Layout

- `harbor/` — Harbor dataset `blobfishai/hubbench` v1.0.0: `dataset.toml`, `task-digests.json`, and 40 self-contained task packages under `tasks/hubbench-<family>-NNN/` (`task.toml`, `instruction.md`, `README.md`, `environment/`, `tests/`, `solution/`). Root digest `54f0ff520bf36106d9f21e725e9a8f4ef7cd5fc2a1f05bd84d71754df60138d3`.
- `huggingface/` — Hugging Face dataset payload (`README.md` card, `data/tasks.jsonl`, `assets/`, `contracts/`, `verifiers/`, `ANCHORS.md`, `LICENSE`, `trajectories/`). Payload manifest `0357dfce087b9a90a041b8343683ff80888b910e9334a3091352c06cbc2988ab`.
- `reports/` — `release.json` (aggregate receipt with input digests) plus verbatim copies of every family's qualification and reasoning-chain report.
- `tasks/` — one public record per task (no gold values).

## Publish (operator, from the repository root)

```bash
harbor publish benchmark/hubbench/release/harbor/tasks --public -t v1.0.0
harbor publish benchmark/hubbench/release/harbor --no-tasks --public -t v1.0.0
hf upload-large-folder SamuelChien821/hubbench benchmark/hubbench/release/huggingface --repo-type dataset
```

## Containment

`environment/` (both container images) never carries the expected answer, the sealed verifier contract, the oracle policy, the task builder, or scenario data; `tests/` (root verifier) and `solution/` (oracle) do. The verifier reaches the finished world through a token-gated, read-only channel on the world service; the world container only holds the token's SHA-256.
