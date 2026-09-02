# Public design anchors and clean-room boundary

HubBench is independently authored. Each family names the public Harbor Hub datasets whose *evaluation shape* informed it. No upstream task, fixture, prompt, seed record, attachment, answer, or score was copied, adapted, redistributed, or claimed; every case, record, tool response, and answer is clean-room synthetic (`clean_room: true`, `upstream_tasks_copied: false`, `upstream_scores_claimed: false` in every task's provenance record). Gated upstream distributions were not downloaded.

## ClinicOps (`clinicops`, cluster `healthcare`)

- **MedAgentBench** — Harbor `stanford/medagentbench` (https://hub.harborframework.com/datasets/stanford/medagentbench/latest); upstream https://github.com/stanfordmlgroup/MedAgentBench; license MIT. Evaluation shape: stateful FHIR-backed EHR retrieval and action tasks. Relationship: evaluation-shape inspiration only; clean-room task, state, tools, and answer.
- **PhysicianBench** — Harbor `josancamon19/physician-bench` (https://hub.harborframework.com/datasets/josancamon19/physician-bench/latest); upstream https://github.com/HealthRex/PhysicianBench; license Apache-2.0. Evaluation shape: long-horizon clinical workflows with checkpointed FHIR interactions. Relationship: evaluation-shape inspiration only; clean-room task, state, tools, and answer.

## DataDesk (`datadesk`, cluster `data-engineering-analytics`)

- **DataEngBench** — Harbor `snowflake-labs/data-eng-bench` (https://hub.harborframework.com/datasets/snowflake-labs/data-eng-bench/latest); upstream https://github.com/Snowflake-Labs/data-eng-bench; license Apache-2.0. Evaluation shape: hermetic dbt data-engineering tasks with row-level deterministic verification. Relationship: evaluation-shape inspiration only; clean-room task, state, tools, and answer.
- **ADE-Bench** — Harbor `dbt-labs/ade-bench` (https://hub.harborframework.com/datasets/dbt-labs/ade-bench/latest); upstream https://github.com/dbt-labs/ade-bench; license Apache-2.0. Evaluation shape: sandboxed analytics-engineering tasks with project and database state checks. Relationship: evaluation-shape inspiration only; clean-room task, state, tools, and answer.

## HostOps (`hostops`, cluster `terminal-operations`)

- **Terminal-Bench** — Harbor `terminal-bench/terminal-bench` (https://hub.harborframework.com/datasets/terminal-bench/terminal-bench/latest); upstream https://github.com/harbor-framework/terminal-bench; license Apache-2.0. Evaluation shape: stateful sandbox tasks with deterministic end-state verification. Relationship: evaluation-shape inspiration only; clean-room task, state, tools, and answer.
- **Terminal-Bench 2.1 file recovery** — Harbor `NovitaAI/tb21-file-recovery` (https://hub.harborframework.com/datasets/NovitaAI/tb21-file-recovery/latest); upstream https://github.com/harbor-framework/terminal-bench; license Apache-2.0. Evaluation shape: file operations, data processing, log analysis, and recovery tasks. Relationship: evaluation-shape inspiration only; clean-room task, state, tools, and answer.

## PolicyDesk (`policydesk`, cluster `policy-compliance-instruction-following`)

- **TaskTrove Nemotron Gym — instruction following (adversarial)** — Harbor `openthoughts/tasktrove-nemotron-gym-instruction-following-adversarial-v3` (https://hub.harborframework.com/datasets/openthoughts/tasktrove-nemotron-gym-instruction-following-adversarial-v3/latest); upstream https://huggingface.co/datasets/openthoughts/tasktrove-nemotron-gym-instruction-following-adversarial-v3; license CC-BY-4.0. Evaluation shape: adversarial instruction- and identity-following under a stated policy. Relationship: evaluation-shape inspiration only; clean-room task, state, tools, and answer.
- **StrongREJECT** — Harbor `strongreject/strongreject` (https://hub.harborframework.com/datasets/strongreject/strongreject/latest); upstream https://github.com/alexandrasouly/strongreject; license MIT. Evaluation shape: refusal of persuasive but policy-violating requests. Relationship: evaluation-shape inspiration only; clean-room task, state, tools, and answer.
- **Reward Hack Bench** — Harbor `islo-labs/reward-hack-bench` (https://hub.harborframework.com/datasets/islo-labs/reward-hack-bench/latest); upstream https://huggingface.co/datasets/islo-labs/reward-hack-bench; license Apache-2.0. Evaluation shape: resistance to shortcut / reward-hacking dispositions with a paired control. Relationship: evaluation-shape inspiration only; clean-room task, state, tools, and answer.

## ResearchDesk (`researchdesk`, cluster `reasoning-knowledge-qa`)

- **GAIA** — Harbor `gaia/gaia` (https://hub.harborframework.com/datasets/gaia/gaia/latest); upstream https://huggingface.co/datasets/gaia-benchmark/GAIA; license see upstream (gated upstream; no tasks, answers, or attachments redistributed). Evaluation shape: multi-step questions requiring source discovery, reasoning, and exact answers. Relationship: evaluation-shape inspiration only; clean-room task, state, tools, and answer.
- **DeepSearchQA** — Harbor `kgmon/deepsearchqa` (https://hub.harborframework.com/datasets/kgmon/deepsearchqa/latest); upstream https://huggingface.co/datasets/google/deepsearchqa; license Apache-2.0. Evaluation shape: long-form multi-source information seeking with traceable evidence. Relationship: evaluation-shape inspiration only; clean-room task, state, tools, and answer.
- **SimpleQA** — Harbor `openai/simpleqa` (https://hub.harborframework.com/datasets/openai/simpleqa/latest); upstream https://github.com/openai/simple-evals; license MIT. Evaluation shape: short fact-seeking questions with exact-answer evaluation. Relationship: evaluation-shape inspiration only; clean-room task, state, tools, and answer.

## SciLab (`scilab`, cluster `scientific-research`)

- **ScienceAgentBench** — Harbor `scienceagentbench/scienceagentbench` (https://hub.harborframework.com/datasets/scienceagentbench/scienceagentbench/latest); upstream https://github.com/OSU-NLP-Group/ScienceAgentBench; license per the upstream repository; nothing from it is redistributed here. Evaluation shape: data-driven scientific tasks with program-executed, deterministic success checks. Relationship: evaluation-shape inspiration only; clean-room task, state, tools, and answer.
- **BixBench** — Harbor `futurehouse/bixbench` (https://hub.harborframework.com/datasets/futurehouse/bixbench/latest); upstream https://github.com/Future-House/BixBench; license per the upstream repository; nothing from it is redistributed here. Evaluation shape: multi-step bioinformatics analysis capsules with exact graded answers. Relationship: evaluation-shape inspiration only; clean-room task, state, tools, and answer.
- **LAB-Bench** — Harbor `futurehouse/labbench` (https://hub.harborframework.com/datasets/futurehouse/labbench/latest); upstream https://github.com/Future-House/LAB-Bench; license per the upstream repository; nothing from it is redistributed here. Evaluation shape: practical biology-laboratory reasoning over protocols, figures, and literature with exact answers. Relationship: evaluation-shape inspiration only; clean-room task, state, tools, and answer.

## Workplace (`workplace`, cluster `customer-workplace-agents`)

- **TheAgentCompany** — Harbor `theagentcompany/theagentcompany` (https://hub.harborframework.com/datasets/theagentcompany/theagentcompany/latest); upstream https://github.com/TheAgentCompany/TheAgentCompany; license MIT. Evaluation shape: simulated-company work across issue tracker, wiki, chat, and file-share apps with checkpoint grading. Relationship: evaluation-shape inspiration only; clean-room task, state, tools, and answer.
- **tau3-bench** — Harbor `sierra-research/tau3-bench` (https://hub.harborframework.com/datasets/sierra-research/tau3-bench/latest); upstream https://github.com/sierra-research/tau2-bench; license MIT. Evaluation shape: policy-bound customer-service tool use with database end-state checks. Relationship: evaluation-shape inspiration only; clean-room task, state, tools, and answer.
- **MMAU** — Harbor `apple/mmau` (https://hub.harborframework.com/datasets/apple/mmau/latest); upstream https://github.com/apple/axlearn; license Apache-2.0. Evaluation shape: tool-use, planning, and problem-solving capability suite for agents. Relationship: evaluation-shape inspiration only; clean-room task, state, tools, and answer.
- **BFCL** — Harbor `gorilla/bfcl` (https://hub.harborframework.com/datasets/gorilla/bfcl/latest); upstream https://github.com/ShishirPatil/gorilla; license Apache-2.0. Evaluation shape: function-calling accuracy with executable and state-based checks. Relationship: evaluation-shape inspiration only; clean-room task, state, tools, and answer.

The engine (world, stateful surfaces, deterministic verifier, negative controls) is a domain-agnostic port of the Apache-2.0 FactoryBench-100 engine by Blobfish AI.
