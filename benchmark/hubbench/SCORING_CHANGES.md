# HubBench v1.4.0 scoring candidate

Status: source/build candidate; the public registry publication is still v1.3.0.
This revision changes grading, not task count, evidence data, provider behavior,
or model performance. Family contract versions advance from 1.0.0 to 1.0.1.
No historical verdict or publication receipt is rewritten.

## Structural text contracts

All 104 stakeholder drafts must now name the actual persisted primary record and
supported outcome date in the **body**. Research drafts also name the current
definition. The exact recipient, unsent status, existing business-reference
check, mutation count, and all authority/evidence requirements remain. An
internal selected-option token is still graded in the structured answer, but
is no longer required in stakeholder prose. All original reference drafts
already satisfy this body contract without edits.

Eighteen individually audited primary mutations no longer require copying an
oracle sentence:

| Tasks | Field | Remaining requirement |
|---|---|---|
| ClinicOps-001; DataDesk-002/005/008; HostOps-001; PolicyDesk-003; RepoDesk-001; SciLab-001; SecOps-001/006; WebStudio-001/008; Workplace-006 | description | Nonempty text; exact target/resource/time/state fields retain the business constraints. |
| ResearchDesk-001/004/006 | note | Nonempty text; exact definition, source set, metric, value, unit, period, and approval remain. |
| ResearchDesk-003/007 | purpose | Nonempty text containing the current definition ID and source-set ID in this field, with the reservation's structured checks unchanged. |

The allowlist is explicit in `engine/grading_contracts.py`: new tasks do not
automatically inherit an exemption. Eleven other causal reasons, summaries, and
notes remain exact until their narrative-only facts have authored contracts;
DeskOps venue-display strings and PolicyDesk compensating controls remain exact.

The new assertion key `payload_argument_text` maps a provider argument name to
required literal facts. An empty fact list requires a nonempty string. Matching
normalizes case and punctuation while preserving whole-token boundaries, so
`BF-71010` cannot satisfy `BF-7101`. Facts in a subject, unrelated field, or nested
object cannot satisfy a body/purpose requirement. Old assertion formats retain
their original semantics; loading old JSON never migrates its contract.

These are **structural checks, not semantic equivalence**. A deterministic fact
matcher does not assess arbitrary prose, negation, or contradictions. It is not
an LLM judge. Exact state, answers, quantities, dates, recipients, authorization,
containment, investigations, readbacks, and milestone weights remain unchanged.

## Evidence-route limitation

Provider calls made through the `tool` CLI, MCP, REST, and web forms all enter
the same durable trace. Direct reads of `/workspace/evidence` do not. A missing
investigation verdict therefore proves missing mandated tool evidence, not
necessarily missing reasoning: an agent may have read equivalent file bytes.

This revision discloses the requirement in Harbor orientation and world context;
it does not silently remove investigations or pretend filesystem reads are
audited. Auditing equivalent local evidence requires a separately designed and
versioned mechanism.

## Verification and publication boundaries

- Fresh local Docker gate completed 2026-09-04 UTC: all 104 frozen v1.4.0
  packages scored reward 1.0, with zero errors, retries, or cancellations.
  Package-bound evidence is in
  [`reports/gates/hubbench-oracle-v1.4.0-full.json`](./reports/gates/hubbench-oracle-v1.4.0-full.json).
- Fresh Python/SQLite qualification: 104/104 strict oracle passes at 100;
  104/104 byte-identical replays; zero false accepts across 1,040 negative-control
  episodes; 208/208 mutation omissions detected.
- Alternate-wording replay: all 104 tasks still pass at 100 without internal
  option tokens in stakeholder prose, including alternative sentences in all 18
  audited primary fields.
- Regression tests cover incorrect structured values, recipients, dates,
  missing body/purpose facts, missing investigations/readbacks/handoffs,
  malformed payload types, boundary collisions, unchanged unsafe narratives,
  and unchanged legacy literal matching.
- The shared H12 audit recognizes body-scoped facts without counting matching
  text in unrelated fields. The other hop requirements are unchanged.
- Reference exports preserve the scoring version established by their original
  publication receipt. Older/unversioned trajectories are explicitly not
  evidence that a newer distribution passed.
- New gate imports independently rehash frozen packages and require matching
  Harbor trial-lock digests, release versions, completed oracle/Docker trials,
  strict verdicts, and trace identities. An admitted gate proof binds each
  compact reference to its original result, lock, trace, and verdict hashes;
  it establishes candidate provenance before a publication receipt exists.
  Imports validate the entire batch before writing. Registry round trips must
  use digest-pinned registry packages, not a local-directory run.

Before claiming v1.4.0 published: publish a new immutable Harbor tag and Hugging Face/source
revision, verify registry round trips and bytes, and regenerate publication/page
receipts. Then run full, version-bound model evaluations before ranking them.
The historical v1.0.0 Luna pilot remains 0/5 strict; it is not rescored here.

The publisher preserves existing frozen releases and job evidence. A new run
needs a new explicit job name; the admitted snapshot may use
`HUBBENCH_FROZEN_RELEASE=$HOME/.cache/hubbench/v1.4.0-qualified` after rebuilding
with admitted reference records. Before any external publish, `--check-gate`
requires complete package-bound coverage. Round trips must cover every family.
