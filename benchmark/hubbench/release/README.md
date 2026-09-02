# HubBench 1.1.0 — distribution tree

Deterministic release emitted by `benchmark/hubbench/build_distribution.py` from the committed family releases and reports. Rebuilding it from the same inputs reproduces every byte.

- **ClinicOps** (`clinicops`, cluster `healthcare`): 8 tasks, 34 tools over 10 MCP servers
- **DataDesk** (`datadesk`, cluster `data-engineering-analytics`): 8 tasks, 33 tools over 10 MCP servers
- **HostOps** (`hostops`, cluster `terminal-operations`): 8 tasks, 39 tools over 12 MCP servers
- **PolicyDesk** (`policydesk`, cluster `policy-compliance-instruction-following`): 8 tasks, 41 tools over 16 MCP servers
- **ResearchDesk** (`researchdesk`, cluster `reasoning-knowledge-qa`): 8 tasks, 32 tools over 12 MCP servers
- **SciLab** (`scilab`, cluster `scientific-research`): 8 tasks, 43 tools over 11 MCP servers
- **Workplace** (`workplace`, cluster `customer-workplace-agents`): 8 tasks, 47 tools over 13 MCP servers

Totals: 56 tasks, 269 tools, 1767 evidence files, 3649 atomic criteria; 56/56 oracle strict passes at mean 100.0 HubScore, 56/56 byte-identical replays, 0 false accepts over 560 negative-control executions, 112/112 mutation omissions detected.

## Layout

- `harbor/` — Harbor dataset `blobfishai/hubbench` v1.1.0: `dataset.toml`, `task-digests.json`, and 56 self-contained task packages under `tasks/hubbench-<family>-NNN/` (`task.toml`, `instruction.md`, `README.md`, `environment/`, `tests/`, `solution/`). Root digest `86f5805930e7674b6b32ce39fe07fe188fc8f24b6a30137c1a67d1d3a893e2af`.
- `huggingface/` — Hugging Face dataset payload (`README.md` card, `data/tasks.jsonl`, `assets/`, `contracts/`, `verifiers/`, `ANCHORS.md`, `LICENSE`, `trajectories/`). Payload manifest `f3a593d6bf39f221f902eeb79163d5fb6dbeb702de33ab8dacbec924fc607e9d`.
- `reports/` — `release.json` (aggregate receipt with input digests) plus verbatim copies of every family's qualification and reasoning-chain report.
- `tasks/` — one public record per task (no gold values).

## Publish (operator, from the repository root)

```bash
harbor publish benchmark/hubbench/release/harbor/tasks --public -t v1.1.0
harbor publish benchmark/hubbench/release/harbor --no-tasks --public -t v1.1.0
hf upload-large-folder SamuelChien821/hubbench benchmark/hubbench/release/huggingface --repo-type dataset
```

## Containment

`environment/` (both container images) never carries the expected answer, the sealed verifier contract, the oracle policy, the task builder, or scenario data; `tests/` (root verifier) and `solution/` (oracle) do. The verifier reaches the finished world through a token-gated, read-only channel on the world service; the world container only holds the token's SHA-256.
