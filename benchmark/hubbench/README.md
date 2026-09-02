# HubBench

One Blobfish-authored benchmark family per professional-domain cluster on
[hub.harborframework.com](https://hub.harborframework.com/datasets), so every
open-source benchmark domain on the hub has an executable, oracle-proven
Blobfish counterpart. The cluster map and family plan live in
[`benchmark/reports/harbor-hub-coverage.json`](../reports/harbor-hub-coverage.json)
(`hubbench` block): thirteen families, eight tasks minimum each. Seven families
and 56 tasks are currently released and qualified.

| Cluster | Family | Status |
|---|---|---|
| healthcare | **clinicops** | **released here — 8/8 reasoning-chain qualified** |
| terminal-operations | **hostops** | **released here — 8/8 reasoning-chain qualified** |
| data-engineering-analytics | **datadesk** | **released here — 8/8 reasoning-chain qualified** |
| reasoning-knowledge-qa | **researchdesk** | **released here — 8/8 reasoning-chain qualified** |
| computer-use-gui | deskops | planned |
| web-product-design | webstudio | planned |
| policy-compliance-instruction-following | **policydesk** | **released here — 8/8 reasoning-chain qualified** |
| it-operations-observability | itsmdesk | planned |
| security | secops | planned |
| customer-workplace-agents | **workplace** | **released here — 8/8 reasoning-chain qualified** |
| scientific-research | **scilab** | **released here — 8/8 reasoning-chain qualified** |
| manufacturing-engineering-design | designops | planned |
| software-engineering | repodesk | planned |

Every task is an employee decision worked over a dependent chain of evidence —
never a lookup. The admission bar is
[`benchmark/realism-standard.json`](../realism-standard.json)
`requirements.reasoningChain` (hop classes H1–H13): a task counts only when the
portfolio audit (`benchmark/reasoning_chain_audit.py`) grades the full chain,
the oracle replays at 100 strictly, two replays are byte-identical, and every
negative control is rejected with zero false accepts.

All released families clear the same current quality floor: at least 28
globally unique agent-visible files across seven native formats, 26 provider
evidence reads (20 evidence reads and 17 live-domain reads minimum), five
independent source systems, 40 deterministic criteria, a real state change and
readback, ten negative controls, and zero LLM-judge calls. Each release also
carries an exact Harbor/upstream provenance record with explicit clean-room
boundaries.

## Engine (domain-agnostic, `engine/`)

A port of the FactoryBench-100 engine (Apache-2.0, our own release; see
[`NOTICE`](./NOTICE)) with the ERP world swapped for real per-family SQLite
tables behind provider-shaped tools:

- **World** (`world.py`): one isolated SQLite database per task/session, seeded
  from the family `schema.sql` plus the task's seed rows. Writes persist to
  real domain tables, readbacks reflect them, the call trace is durable (and
  re-synced when several surfaces share one database), and optional
  deterministic transient faults can be declared per task.
- **Verifier** (`verifier.py`): deterministic and contract-driven (HubScore):
  required investigations before the first write, provider payload assertions,
  post-write readbacks, write containment, exact graded answer fields, semantic
  milestone aggregation. Zero LLM calls.
- **Decision model** (`decision.py`): plan / quantity / schedule bundles that
  emit the exact calculation ids the reasoning-chain audit keys on (H2–H10),
  three alternatives with outcome + incremental cost + authority status, and an
  answer contract that grades every intermediate value.
- **Qualification** (`evaluation.py`): oracle, ten negative controls (`noop`,
  `shortcut`, `state_only`, `incomplete_read`, `write_before_read`,
  `missing_readback`, `unauthorized_write`, `wrong_value`, `wrong_decision`,
  `wrong_evidence`), mutation-omission proof, and determinism replay.
- **Release** (`release.py`, `assets.py`): diff-stable release trees with real
  `.xlsx` / `.pdf` / `.eml` / `.csv` / `.json` / `.md` / `.yaml` evidence files.

### Surfaces — CLI, MCP (stdio and HTTP), REST, website, one world

Every surface drives the same on-disk SQLite world through `World.call_tool`,
so a write on one surface is immediately visible on every other and a session
spread over the CLI, MCP, REST, and the website grades as **one** episode. The
sealed verifier contract, the expected answer, and the call trace are never
readable on any surface. Everything is Python 3.12 stdlib.

Serve one task (MCP over streamable HTTP + REST + website in one process; run
from `benchmark/`, or use the `bin/serve` wrapper from anywhere):

```bash
python3 -m hubbench.engine.http --family clinicops --task clinicops-001 \
    --db /tmp/clinicops-001.db --fresh --host 0.0.0.0 --port 8765
benchmark/hubbench/bin/serve --family clinicops --task clinicops-001 \
    --db /tmp/clinicops-001.db --fresh --host 0.0.0.0 --port 8765   # same thing
```

| Surface | Routes | Try it |
|---|---|---|
| **MCP over stdio** (`server.py`) | JSON-RPC 2.0, one message per line: `initialize`, `tools/list`, `tools/call`, `resources/*`, `prompts/*` | `echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \| python3 -m hubbench.engine.server --family clinicops --task clinicops-001 --db /tmp/clinicops-001.db` |
| **MCP over streamable HTTP** (`http.py`) | `POST /mcp` (every tool) · `POST /mcp/<server>` (one mock server; `/mcp/hubbench` = the two controls); requests, notifications (`202`), and batches | `curl -s localhost:8765/mcp/pharmacy -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'` |
| **REST API** (`http.py`) | `GET /api/v1/tools` · `GET\|POST /api/v1/tools/<name>` · `GET /api/v1/<server>/<resource>` · `GET /api/v1/<server>/<resource>/<id>` · `GET\|POST /api/v1/<server>/<resource>/<op>` · `GET /api/v1/task` · `POST /api/v1/submit` | `curl -s localhost:8765/api/v1/pharmacy/orders/PO-5100` · `curl -s -X POST localhost:8765/api/v1/tools/pharmacy.orders.create -H 'content-type: application/json' -d '{"supplier_id":"SUP-MERIDIAN","confirmation_id":"CONF-MER-55207","medication_code":"IVIG-10G","quantity":2,"delivery_option":"expedited"}'` |
| **Website** (`http.py`) | `GET /` (brief + connected systems) · `/app/<server>` · `/app/<server>/<resource>` (listing) · `/app/<server>/<resource>/<id>` (detail) · `/app/<server>/<resource>/<op>` (form generated from the input schema; `POST` writes through the world and links to the readback) · `/app/task` · `/app/submit` | `curl -s localhost:8765/app/pharmacy/orders` · `curl -s -X POST localhost:8765/app/pharmacy/orders/create -d 'supplier_id=SUP-MERIDIAN&confirmation_id=CONF-MER-55207&medication_code=IVIG-10G&quantity=2&delivery_option=expedited'` |
| **Terminal `tool` CLI** (`cli.py`, `bin/tool`) | `tool list` · `tool schema <name>` · `tool <name> '<json>'` over the local SQLite world (`HUBBENCH_DB`) or a served one (`HUBBENCH_URL` → the REST surface; `reset` / `trace` stay local-only) | `HUBBENCH_URL=http://localhost:8765 benchmark/hubbench/bin/tool pharmacy.orders.get '{"po_id":"PO-5100"}'` |

Harbor task packages mount the per-server MCP endpoints:

```toml
[[environment.mcp_servers]]
name = "pharmacy"
transport = "streamable-http"
url = "http://world:8765/mcp/pharmacy"
```

REST mapping rule: a tool `<server>.<resource>.<operation>` is served at
`GET /api/v1/<server>/<resource>` (its `list` tool, else `search`; query-string
arguments are coerced through the input schema — integer, number, boolean,
JSON arrays / objects), `GET /api/v1/<server>/<resource>/<id>` (its `get` tool,
`<id>` bound to the single required argument), and
`GET|POST /api/v1/<server>/<resource>/<operation>` (GET + query string for read
tools, POST + JSON body for write tools). Two-part names `<server>.<operation>`
use the server as the resource (`approvals.get` →
`/api/v1/approvals/approvals/<id>`, shorthand `/api/v1/approvals/<id>`); any
tool that fits neither shape stays reachable at `/api/v1/tools/<name>`. Errors
are JSON: `400` bad JSON or arguments (the world's own validation message),
`404` unknown tool / server / resource / record, `405` wrong method (`Allow`
header), `422` a well-formed call the world rejected, `503` a declared
transient fault. The website renders the same routes as HTML (no scripts,
inline CSS, readable from `curl` or `lynx`).

## First family: ClinicOps (healthcare)

World: FHIR-shaped EHR (Patient, Observation, MedicationRequest), infusion
chair scheduling (Slot/Appointment), pharmacy formulary + lot register +
purchase orders + inter-site transfers, supplier delivery confirmations,
approval records, mailbox, team chat, shared drive, and draft notes — 32
provider-shaped tools plus the two benchmark controls, over 19 domain tables.
Anchor question (per the coverage report): *"When can this patient
realistically get the infusion, given the order, the drug on hand, the chair
schedule, and the supplier's delivery window?"* Hub anchors:
stanford/medagentbench, josancamon19/physician-bench. All data is clean-room
synthetic; FHIR shapes only, no real patients, clinicians, or organisations.

Eight tasks across three decision modes (3 plan, 3 quantity, 2 schedule), each
with 29–31 heterogeneous evidence files (policy `.md`, FHIR order and patient
exports `.json`, on-hand workbook `.xlsx`, lot-status register `.csv`, chair
calendar `.xlsx`, supplier confirmation `.pdf`, request email `.eml`, chat
thread `.json`, approval record, starting-state export, superseded/decoy
records, evidence index `.yaml`, lineage, provenance, provider contracts,
audit records, and live snapshots), 61–66 deterministic criteria, 24–27 graded
answer fields, and a unique causal reference sequence: order → dose
requirement → on-hand minus expired/quarantined → chair schedule → supplier
lead time → alternatives → controlled write + readback + stakeholder draft →
exact answer.

### Measured state (committed reports)

- Reasoning chain ([`reports/reasoning-chain/clinicops.json`](./reports/reasoning-chain/clinicops.json)),
  measured with the **unmodified** `measure_factorybench_task` from
  `benchmark/chain_adapters/factorybench_100.py`: **8/8 tasks pass**, chain depth 8/8
  spine hops on every task, hop coverage H1–H13 = 8/8, 23–26 graded dependent
  derivations, 24–27 graded answer fields, 9 source systems, and 26 graded
  evidence reads before the decision on every task.
- Qualification ([`reports/clinicops-qualification.json`](./reports/clinicops-qualification.json)):
  oracle 8/8 strict at 100.0, deterministic replay 8/8 byte-identical,
  10 negative controls × 8 tasks with **0 false accepts** (all means below
  oracle), 16/16 mutation omissions detected.

## Second family: HostOps (terminal-operations)

World: Linux host + build + backup mock — CMDB (services, hosts, payload
meterings), release/recovery tickets, cron/CI scheduler with run history,
backup catalog (artifact classes, segment-set register with checksum /
retention / reservation state, vendor restore jobs, inter-store copies),
release build farm (runners, reservation-window calendar with protected
freeze and compliance blocks), cold-archive vault retrieval confirmations,
approvals, mailbox, team chat, shared drive, and draft notes — 37
provider-shaped tools plus the two benchmark controls, over 22 domain tables.
Anchor question (per the coverage report): *"Can we recover last night's
failed deploy artifacts before the 09:00 release window, and what does it cost
us if we rebuild instead?"* Hub anchors: terminal-bench,
NovitaAI/tb21-file-recovery, openthoughts nl2bash, termigen. All data is
clean-room synthetic; no real organisation, engineer, or vendor.

Eight tasks across the same three decision modes (3 plan, 3 quantity,
2 schedule), each with 30–33 heterogeneous evidence files (runbook `.md`,
ticket and service exports `.json`, holdings workbook `.xlsx`, set-status
register `.csv`, job schedule + runs `.csv`, runner calendar `.xlsx`, vendor
confirmation `.pdf`, request email `.eml`, chat thread `.json`, approval
record, starting-state export, superseded/decoy records, evidence index
`.yaml`, lineage, provenance, provider contracts, audit records, and live
snapshots), 62–67 deterministic criteria, 24–27 graded answer fields, and a
unique causal reference sequence: failed job run → payload metering →
segments required → catalogued sets minus checksum-failed/purge-queued/reserved →
farm window calendar → vendor retrieval dates → alternatives → controlled
write + readback + stakeholder draft → exact answer. Measured state:
[`reports/reasoning-chain/hostops.json`](./reports/reasoning-chain/hostops.json)
(8/8 pass, chain depth 8/8, hop coverage H1–H13 = 8/8, 23–26 graded dependent
derivations, 11 source systems, 27 graded evidence reads) and
[`reports/hostops-qualification.json`](./reports/hostops-qualification.json)
(oracle 8/8 strict at 100.0, deterministic replay 8/8, 10 negative controls ×
8 tasks with 0 false accepts, 16/16 mutation omissions detected).

```bash
python3 benchmark/hubbench/build_release.py --family hostops
python3 -m hubbench.engine.server --family hostops --task hostops-001 \
    --db /tmp/hostops-001.db --fresh               # run from benchmark/
HUBBENCH_FAMILY=hostops HUBBENCH_TASK=hostops-001 benchmark/hubbench/bin/tool list
python3 benchmark/hubbench/chain_adapter.py --family hostops --write
python3 benchmark/hubbench/qualify.py --family hostops --write
```

## Third family: DataDesk (data-engineering-analytics)

World: warehouse + dbt-style models + pipeline runs — model catalog with
lineage and freshness SLAs, pipeline run history with durations / failures /
source versions, run schedules and backfill jobs, vendor source feeds with
delivery logs (invalid / duplicate / late buckets) and redelivery
confirmations, a batch-window capacity calendar with protected close and
replication loads, finance reconciliation controls and adjustment entries,
approvals, mailbox, team chat, shared drive, and draft notes — 31
provider-shaped tools plus the two benchmark controls, over 19 domain tables.
Anchor question (per the coverage report): *"Why does Monday's revenue
dashboard disagree with finance, and can we correct it before the board pack
without re-running the full backfill?"* Hub anchors:
snowflake-labs/data-eng-bench, dbt-labs/ade-bench, kumo, xlang/ds-1000,
NovitaAI/tb21-data-science. All data is clean-room synthetic; no real
organisation, vendor, or number.

Eight tasks across the same three decision modes (3 quantity, 3 plan,
2 schedule), each with 30–32 heterogeneous evidence files (policy `.md`,
catalog manifest and control exports `.json`, run-history workbook `.xlsx`,
delivery log and SLA / roster / schedule registers `.csv`, window calendar
`.xlsx`, vendor confirmation `.pdf`, request email `.eml`, chat thread
`.json`, approval record, starting-state export, superseded/decoy records,
evidence index `.yaml`, lineage, provenance, provider contracts, audit records,
and live snapshots), 60–62 deterministic criteria, 23–24 graded answer
fields, and a unique causal reference sequence: model lineage → run history →
source counts minus invalid/duplicate/late → freshness SLA → window-calendar
capacity → vendor redelivery dates → alternatives → controlled write
(adjustment entry, backfill job, or schedule re-window) + readback +
stakeholder draft → exact answer. Measured state:
[`reports/reasoning-chain/datadesk.json`](./reports/reasoning-chain/datadesk.json)
(8/8 pass, chain depth 8/8, hop coverage H1–H13 = 8/8, 22–23 graded dependent
derivations, 8–9 source systems, 26 graded evidence reads) and
[`reports/datadesk-qualification.json`](./reports/datadesk-qualification.json)
(oracle 8/8 strict at 100.0, deterministic replay 8/8, 10 negative controls ×
8 tasks with 0 false accepts, 16/16 mutation omissions detected).

```bash
python3 benchmark/hubbench/build_release.py --family datadesk
python3 -m hubbench.engine.server --family datadesk --task datadesk-001 \
    --db /tmp/datadesk-001.db --fresh              # run from benchmark/
HUBBENCH_FAMILY=datadesk HUBBENCH_TASK=datadesk-001 benchmark/hubbench/bin/tool list
python3 benchmark/hubbench/chain_adapter.py --family datadesk --write
python3 benchmark/hubbench/qualify.py --family datadesk --write
```

## Fourth family: ResearchDesk (reasoning-knowledge-qa)

World: versioned internal knowledge articles and revisions, current and
retired metric definitions, period snapshots, independently verified source
sets and records, ranked search indexes, specialist-review calendars with
protected capacity, signed approvals, persistent research claims and evidence
packets, mailbox, team chat, shared drive, and draft notes — 30
provider-shaped tools plus the two benchmark controls across 11 mock servers
and 17 domain tables. Anchor question: *"What is the exact figure we can cite
for last quarter's churn in the investor letter, and which alternative
definitions would change it?"* Exact Hub anchors: `gaia/gaia`,
`kgmon/deepsearchqa`, and `openai/simpleqa`. The upstream GAIA distribution is
gated; no upstream tasks, answers, attachments, or scores are redistributed or
claimed. Every case is clean-room synthetic.

Eight tasks (3 quantity, 3 plan, 2 schedule) cover exact-figure publication,
evidence-packet assembly, and qualified-review reservation. Each task has
exactly 30 globally unique files in eight native formats: current and retired
authority, metric workbooks, source registers, attestations, search results,
review-capacity workbooks, email, chat, lineage, audit logs, provider
contracts, live snapshots, and clean-room provenance. Each requires 26
pre-write provider investigations across 10 source systems, grades 60–62
deterministic criteria and 27–28 answer fields, and follows a causal chain:
article identity and revision → operative definition → period snapshot →
verified versus stale sources → supported value or capacity gap → three
alternatives and signed authority → claim, packet, or reservation write →
provider readback → stakeholder draft → exact answer.

Measured state:
[`reports/reasoning-chain/researchdesk.json`](./reports/reasoning-chain/researchdesk.json)
(8/8 pass, chain depth 7–8, mandatory hop coverage 8/8, 22–23 dependent
derivations, 10 source systems, 26 evidence reads, and 27–28 graded answer
fields) and
[`reports/researchdesk-qualification.json`](./reports/researchdesk-qualification.json)
(oracle 8/8 strict at 100.0, deterministic replay 8/8, 10 negative controls ×
8 tasks with 0 false accepts, 16/16 mutation omissions detected).

```bash
python3 benchmark/hubbench/build_release.py --family researchdesk
python3 -m hubbench.engine.server --family researchdesk --task researchdesk-001 \
    --db /tmp/researchdesk-001.db --fresh          # run from benchmark/
HUBBENCH_FAMILY=researchdesk HUBBENCH_TASK=researchdesk-001 benchmark/hubbench/bin/tool list
python3 benchmark/hubbench/chain_adapter.py --family researchdesk --write
python3 benchmark/hubbench/qualify.py --family researchdesk --write
```

## Run a task

Everything is local Python 3.12 stdlib; no Docker, no API keys, no network.

```bash
# rebuild the release tree (byte-stable)
python3 benchmark/hubbench/build_release.py --family clinicops

# stateful MCP server over stdio for one task
python3 -m hubbench.engine.server --family clinicops --task clinicops-001 \
    --db /tmp/clinicops-001.db --fresh          # run from benchmark/
```

MCP client config:

```json
{"mcpServers": {"clinicops": {"command": "python3", "args": ["-m", "hubbench.engine.server", "--family", "clinicops", "--task", "clinicops-001", "--db", "/tmp/clinicops-001.db", "--fresh"], "cwd": "benchmark"}}}
```

Terminal CLI (same world, persistent session state):

```bash
export HUBBENCH_TASK=clinicops-001 HUBBENCH_DB=/tmp/clinicops-001-cli.db
benchmark/hubbench/bin/tool list
benchmark/hubbench/bin/tool ehr.patients.search '{"identifier": "MRN-482913"}'
benchmark/hubbench/bin/tool pharmacy.lots.list '{"medication_code": "INFLIX-100"}'
```

Re-measure and re-qualify:

```bash
python3 benchmark/hubbench/chain_adapter.py --family clinicops --write
python3 benchmark/hubbench/qualify.py --family clinicops --write
python3.12 -m pytest benchmark/hubbench -q
```

## Adding the next family

A family is a directory under `families/<slug>/` exporting `FAMILY`
(`engine/families.py`): a `schema.sql`, provider-shaped `ToolSpec`s, and a
`build_tasks()` that assembles tasks through `engine/decision.py` +
`engine/catalog.py` (which enforce the realism standard at build time). The
engine, verifier, controls, server, CLI, release writer, and chain adapter are
family-agnostic. Integration into `benchmark/catalog.json` /
`benchmark/validate.mjs` / the portfolio audit's `ADAPTERS` table is a
deliberate follow-up, not part of this tree.

## Distribution (`engine/distribution.py`, `build_distribution.py`, `release/`)

`python3 benchmark/hubbench/build_distribution.py` rebuilds the aggregate,
byte-stable distribution tree `benchmark/hubbench/release/` from every family
with a committed `families/<slug>/release/`:

- `harbor/tasks/hubbench-<family>-NNN/` — one self-contained Harbor 1.4 task
  package per task: `task.toml` (`blobfishai/hubbench-<family>-NNN`, one
  `[[environment.mcp_servers]]` per mock server over streamable HTTP at
  `http://world:8765/mcp/<server>`), `environment/` (agent image + `world`
  service built from the digest-pinned `python:3.12-slim`, a vendored runtime
  subset of the engine with NO grading, oracle, or task-construction modules,
  the public task record, the agent-visible evidence files, and the `tool`
  CLI pointed at the world over `HUBBENCH_URL`), `tests/` (root-only verifier:
  pulls the finished world over a token-gated private channel — the raw token
  ships only here, the world image holds its SHA-256 — and grades it with the
  sealed HubScore contract, writing `reward.txt`, `verdict.json`, `trace.json`),
  and `solution/` (the oracle replayed THROUGH the surfaces: context and
  investigations over MCP-over-HTTP, the primary write and readback over the
  REST API, the stakeholder draft through the `tool` CLI, the answer through
  `POST /api/v1/submit`).
- `harbor/dataset.toml` + `harbor/task-digests.json` — dataset
  `blobfishai/hubbench` with the Harbor content digest of every package (the
  dataset name never equals a task package name; the registry treats that as a
  collision).
- `huggingface/` — the `SamuelChien821/hubbench` payload: dataset card with the
  measured qualification and chain-audit numbers, `data/tasks.jsonl` (public
  records: instruction, tools, evidence list, graded answer FIELD NAMES — no gold
  values), `assets/`, `contracts/tools.json`, `verifiers/` (sealed contracts,
  published like ERPBench), `ANCHORS.md`, `LICENSE`, and one strict,
  Docker-gated reference-trajectory sample per family under `trajectories/`
  (explicitly excluded from leaderboard scoring).
- `reports/release.json` — the aggregate receipt (families, tasks, tools,
  criteria, qualification and chain totals, `harbor_root_sha256`,
  `huggingface_manifest_sha256`, input digests) plus verbatim copies of every
  family report; `tasks/` public per-task records.

`tests/test_distribution.py` rebuilds the tree into a temporary directory and
requires it to be byte-identical to the committed one, checks every package's
shape and digest, proves the agent-visible surfaces carry no sealed key, engine
module, or raw verifier token, reconciles the receipt with the family reports,
and — for one task per family — starts the world service locally, runs the
packaged oracle through MCP/REST/CLI/submit, and grades it with the packaged
verifier to reward 1.0 (the private channel refuses requests without the token).

Publish order (from a frozen copy under a dedicated operator directory, never a rebuilding tree):
`harbor run -p <tasks> -a oracle` gate → `harbor publish tasks/* --public -t v<version>`
→ `yes | harbor publish <dataset.toml dir> --public --no-tasks -t v<version>` (the
dataset publish prompts for confirmation) → registry round-trip
`harbor run -d blobfishai/hubbench@v<version> -a oracle -i blobfishai/hubbench-<family>-NNN` →
`hf upload-large-folder SamuelChien821/hubbench <frozen>/huggingface --repo-type dataset`
→ `curl "https://huggingface.co/api/datasets/SamuelChien821/hubbench?blobs=true"` →
`python3 benchmark/hubbench/publication_receipt.py …` (writes `reports/publication.json`
only if every gate trial and round-trip scored 1.0 and the Hugging Face payload verifies
byte-for-byte) → `site_data.py` / `build_hubbench_site_data.py`.

## Adding a family (checklist)

A family lands as `families/<slug>/` (+ its `release/`), `tests/test_family_<slug>.py`,
`reports/<slug>-qualification.json`, and `reports/reasoning-chain/<slug>.json`. The
committed derivatives must then be regenerated in the same PR, or the suites go red:

```bash
python3 benchmark/hubbench/build_distribution.py            # release/ (byte-stable; tests/test_distribution.py)
python3 benchmark/harbor_hub_coverage.py --write            # reports/harbor-hub-coverage.json released counts
python3 benchmark/build_hubbench_site_data.py               # website hubbench-data.json
python3 benchmark/hubbench/site_data.py                     # website hubbench-explorer-data.json
python3 -m pytest benchmark/hubbench benchmark/tests/test_harbor_hub_census.py -q
```

Keep `tools.py` self-contained (the vendored Harbor runtime ships only `schema.sql`
and `tools.py` for the family), update the table above, and never edit
`reports/publication.json` — it describes the tagged release that was actually
published; newer families wait for the next tag.

## Model runs (`model_run.py`, `model_runs/`)

`python3 benchmark/hubbench/model_run.py <harbor-job-dir> --slug <slug> --label "<model>" [--allow-partial]`
imports a Harbor model job fail-closed: every trial must come from the published
dataset and a published task, carry a HubScore verdict that equals the Harbor
reward, and be free of errors. The importer keeps the durable world call trace the
packaged verifier pulled (provider-independent — every surface), the verdict with
per-category earned weight, and the agent's token and cost receipt under
`model_runs/<slug>/`. A run is **ranked** only when it completed every published
task exactly once with zero errors and zero retries; anything else is a
**disclosed partial run** whose trajectories are published and whose scores are
never ranked. `site_data.py` turns ranked runs into leaderboard rows and every
run into model trajectories on the page.
