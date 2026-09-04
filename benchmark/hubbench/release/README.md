# HubBench 1.4.0 — distribution tree

Deterministic release emitted by `benchmark/hubbench/build_distribution.py` from the committed family releases and reports. Rebuilding it from the same inputs reproduces every byte.

- **ClinicOps** (`clinicops`, cluster `healthcare`): 8 tasks, 34 tools over 10 MCP servers
- **DataDesk** (`datadesk`, cluster `data-engineering-analytics`): 8 tasks, 33 tools over 10 MCP servers
- **DesignOps** (`designops`, cluster `manufacturing-engineering-design`): 8 tasks, 42 tools over 13 MCP servers
- **DeskOps** (`deskops`, cluster `computer-use-gui`): 8 tasks, 51 tools over 13 MCP servers
- **HostOps** (`hostops`, cluster `terminal-operations`): 8 tasks, 39 tools over 12 MCP servers
- **ITSMDesk** (`itsmdesk`, cluster `it-operations-observability`): 8 tasks, 43 tools over 11 MCP servers
- **PolicyDesk** (`policydesk`, cluster `policy-compliance-instruction-following`): 8 tasks, 41 tools over 16 MCP servers
- **RepoDesk** (`repodesk`, cluster `software-engineering`): 8 tasks, 57 tools over 13 MCP servers
- **ResearchDesk** (`researchdesk`, cluster `reasoning-knowledge-qa`): 8 tasks, 32 tools over 12 MCP servers
- **SciLab** (`scilab`, cluster `scientific-research`): 8 tasks, 43 tools over 11 MCP servers
- **SecOps** (`secops`, cluster `security`): 8 tasks, 48 tools over 14 MCP servers
- **WebStudio** (`webstudio`, cluster `web-product-design`): 8 tasks, 44 tools over 13 MCP servers
- **Workplace** (`workplace`, cluster `customer-workplace-agents`): 8 tasks, 47 tools over 13 MCP servers

Totals: 104 tasks, 554 tools, 3450 evidence files, 7001 atomic criteria; 104/104 oracle strict passes at mean 100.0 HubScore, 104/104 byte-identical replays, 0 false accepts over 1040 negative-control executions, 208/208 mutation omissions detected.

## Layout

- `harbor/` — Harbor dataset `blobfishai/hubbench` v1.4.0: `dataset.toml`, `task-digests.json`, and 104 self-contained task packages under `tasks/hubbench-<family>-NNN/` (`task.toml`, `instruction.md`, `README.md`, `environment/`, `tests/`, `solution/`). Root digest `fd6b79f4e5bc88326ab90be064b369d0098908ac155c218a89a16581d2b5c6c9`.
- `huggingface/` — Hugging Face dataset payload (`README.md` card, `data/tasks.jsonl`, `assets/`, `contracts/`, `verifiers/`, `ANCHORS.md`, `LICENSE`, `trajectories/`). Payload manifest `b4a1673ca1ec16ed144ee8e34ecb04973555f91681bce61f48ceedc7aa2b776c`.
- `reports/` — `release.json` (aggregate receipt with input digests) plus verbatim copies of every family's qualification and reasoning-chain report.
- `tasks/` — one public record per task (no gold values).

## Publish (operator, from the repository root)

```bash
harbor publish benchmark/hubbench/release/harbor/tasks --public -t v1.4.0
harbor publish benchmark/hubbench/release/harbor --no-tasks --public -t v1.4.0
hf upload-large-folder SamuelChien821/hubbench benchmark/hubbench/release/huggingface --repo-type dataset
```

## Containment

`environment/` (both container images) never carries the expected answer, the sealed verifier contract, the oracle policy, the task builder, or scenario data; `tests/` (root verifier) and `solution/` (oracle) do. The verifier reaches the finished world through a token-gated, read-only channel on the world service; the world container only holds the token's SHA-256.
