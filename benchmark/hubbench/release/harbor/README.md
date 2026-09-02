# HubBench 1.2.0

One Blobfish-authored, oracle-proven benchmark family per Harbor Hub professional-domain cluster: mock stateful tools over an isolated SQLite world, reachable as MCP servers over streamable HTTP, a terminal `tool` CLI, a REST API, and a web console, graded by the deterministic **HubScore** verifier (zero LLM judge). Every task is an employee decision worked over a dependent chain of evidence — never a lookup.

| Family | Cluster | Tasks | MCP servers | Tools |
|---|---|---|---|---|
| ClinicOps (`clinicops`) | healthcare | 8 | 10 | 34 |
| DataDesk (`datadesk`) | data-engineering-analytics | 8 | 10 | 33 |
| DesignOps (`designops`) | manufacturing-engineering-design | 8 | 13 | 42 |
| HostOps (`hostops`) | terminal-operations | 8 | 12 | 39 |
| ITSMDesk (`itsmdesk`) | it-operations-observability | 8 | 11 | 43 |
| PolicyDesk (`policydesk`) | policy-compliance-instruction-following | 8 | 16 | 41 |
| RepoDesk (`repodesk`) | software-engineering | 8 | 13 | 57 |
| ResearchDesk (`researchdesk`) | reasoning-knowledge-qa | 8 | 12 | 32 |
| SciLab (`scilab`) | scientific-research | 8 | 11 | 43 |
| SecOps (`secops`) | security | 8 | 14 | 48 |
| WebStudio (`webstudio`) | web-product-design | 8 | 13 | 44 |
| Workplace (`workplace`) | customer-workplace-agents | 8 | 13 | 47 |

96 tasks across 12 families. Qualification: 96/96 oracle strict passes at mean 100.0, 96/96 byte-identical replays, 960 negative-control executions across 10 policies with 0 false accepts, 192/192 mutation omissions detected.

## Run

```bash
harbor run -d blobfishai/hubbench@v1.2.0 -a <agent> -m <provider/model>
```

Each task package is self-contained: a digest-pinned `python:3.12-slim` agent image (non-root `agent`, `tool` on PATH, evidence under `/workspace/evidence`) and a `world` service exposing the surfaces on port 8765. The verifier runs as root, pulls the finished world over a token-gated read-only channel, and writes `/logs/verifier/reward.txt` (= HubScore / 100).

All data is clean-room synthetic; no real patient, employee, supplier, or organisation is represented. Page: https://blobfish.ai/benchmarks/hubbench · Hugging Face: https://huggingface.co/datasets/SamuelChien821/hubbench
