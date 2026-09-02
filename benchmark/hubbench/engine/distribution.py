"""Deterministic distribution emitter: Harbor dataset, Hugging Face dataset, public records.

Builds ONE aggregate, diff-stable release tree (``benchmark/hubbench/release/``)
from every family that has a committed ``families/<slug>/release/`` tree plus its
committed qualification and reasoning-chain reports.  Nothing is regenerated
here: tasks, sealed contracts, evidence bytes, and the measured numbers are read
from the committed inputs and re-packaged for the four public surfaces
(blobfish.ai page, Harbor, Hugging Face, GitHub).

Harbor task packages are self-contained (digest-pinned ``python:3.12-slim``,
everything ``COPY``'d in, nothing pulled or installed at build time) and keep the
sealed material out of the agent's reach:

* ``environment/`` — agent image (non-root ``agent``, ``tool`` CLI on PATH,
  evidence files) and world image (vendored runtime subset + public task.json
  + ``hubbench.engine.world_service``).  No expected answer, no oracle policy,
  no verifier contract, no task builder, no scenario data.
* ``tests/`` — root verifier: vendored runtime + ``engine/verifier.py``, the
  sealed task contract, and the raw verifier-channel token.
* ``solution/`` — the oracle policy replayed through the HTTP surfaces.

Every emitted byte is a pure function of the committed inputs and the release
version: sorted keys, no timestamps, no machine paths, deterministic tokens.
"""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .assets import asset_bytes
from .catalog import sealed_contract, sha256_json
from .families import CONTEXT_TOOL, SUBMIT_TOOL, Family, load_family, public_tool_definitions
from .tasks import HUBBENCH_ROOT, load_release_contract, load_release_tasks, release_dir

BENCHMARK = "HubBench"
METRIC = "HubScore"
DEFAULT_VERSION = "1.1.0"
HARBOR_ORG = "blobfishai"
HARBOR_DATASET = f"{HARBOR_ORG}/hubbench"
HARBOR_URL = f"https://hub.harborframework.com/datasets/{HARBOR_DATASET}/latest"
HARBOR_IMAGE = "python:3.12-slim@sha256:7a8b475003c4fe15a2cd4e55e5cfc2f3560bdc9333d624f24cdd6d4340fd7a17"
PAGE_URL = "https://blobfish.ai/benchmarks/hubbench"
SOURCE_URL = "https://github.com/blobfishai/hubbench"
HF_DATASET = "SamuelChien821/hubbench"
HF_URL = f"https://huggingface.co/datasets/{HF_DATASET}"
WORLD_HOST = "world"
WORLD_PORT = 8765
PRIVATE_PORT = 8766
AGENT_UID = 10001
ENGINE_SERVER = "hubbench"
DEFAULT_OUTPUT = HUBBENCH_ROOT / "release"
REPORTS_DIR = HUBBENCH_ROOT / "reports"
ENGINE_DIR = Path(__file__).resolve().parent

# Task keys the world runtime (and therefore the agent) may see.
PUBLIC_TASK_KEYS = (
    "benchmark",
    "benchmark_version",
    "task_id",
    "family",
    "title",
    "role",
    "level",
    "mode",
    "as_of",
    "instruction",
    "world",
    "reference_records",
    "starting_records",
    "seed_tables",
    "answer_schema",
    "transient_faults",
)
# Task keys that must never leave tests/ and solution/.
SEALED_TASK_KEYS = (
    "expected",
    "oracle_steps",
    "required_investigations",
    "required_read_calls",
    "required_reads",
    "post_write_verifications",
    "negative_controls",
    "decision_model",
    "rubric_milestones",
    "sequence_signature",
    "workflow",
    "allowed_write_tables",
)
VERIFIER_TASK_EXCLUDED = ("assets", "seed_tables", "oracle_steps")
# Engine modules that carry grading, oracle, or task-construction logic.
SEALED_ENGINE_MODULES = frozenset({"evaluation", "catalog", "decision", "quality_assets", "release", "distribution"})
VERIFIER_ENGINE_MODULES = frozenset({"verifier"})
RUNTIME_ROOTS = ("cli", "server", "http", "world_service")
FAMILY_RUNTIME_FILES = ("tools.py", "schema.sql")
HARBOR_PUBLISH_DIRECT_FILES = ("task.toml", "instruction.md", "README.md")
HARBOR_PUBLISH_DIRECTORIES = ("environment", "tests", "solution", "steps")
HARBOR_IGNORED_SUFFIXES = (".pyc", ".swp", ".swo", "~")
SURFACES = (
    "MCP over streamable HTTP, one endpoint per provider server (http://world:8765/mcp/<server>)",
    "terminal `tool` CLI bound to the same world through HUBBENCH_URL",
    "REST API under http://world:8765/api/v1/",
    "web console at http://world:8765/",
)
ORIENTATION = (
    "The connected systems are reachable from this container as MCP servers over streamable HTTP "
    f"(`http://{WORLD_HOST}:{WORLD_PORT}/mcp/<server>`), through the `tool` command-line client "
    "(`tool list`, `tool schema <name>`, `tool <name> '<json>'`), through the REST API under "
    f"`http://{WORLD_HOST}:{WORLD_PORT}/api/v1/`, and through the web console at `http://{WORLD_HOST}:{WORLD_PORT}/`. "
    "Every surface reads and writes the same isolated, stateful world. The task's evidence files are under "
    "`/workspace/evidence`. Record the structured decision with the benchmark's answer control when the work is complete."
)


# --------------------------------------------------------------------------- #
# Small deterministic writers and digests
# --------------------------------------------------------------------------- #


def _write_text(path: Path, value: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    path.chmod(0o755 if executable else 0o644)


def _write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    path.chmod(0o644)


def _write_json(path: Path, value: Any) -> None:
    _write_text(path, json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    _write_text(path, "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _harbor_ignored(relative: Path) -> bool:
    return "__pycache__" in relative.parts or relative.name == ".DS_Store" or relative.name.endswith(HARBOR_IGNORED_SUFFIXES)


def harbor_publishable_files(task_dir: Path) -> list[Path]:
    """The files Harbor 0.21's publisher packages (``harbor.publisher.packager.Packager``)."""

    files: set[Path] = set()
    for name in HARBOR_PUBLISH_DIRECT_FILES:
        path = task_dir / name
        if path.is_file():
            files.add(path)
    for name in HARBOR_PUBLISH_DIRECTORIES:
        directory = task_dir / name
        if directory.is_dir():
            files.update(path for path in directory.rglob("*") if path.is_file())
    files = {path for path in files if not _harbor_ignored(path.relative_to(task_dir))}
    return sorted(files, key=lambda path: path.relative_to(task_dir).as_posix())


def harbor_task_digest(task_dir: Path) -> tuple[str, int, int]:
    """Harbor's durable ``sha256:`` content digest for one task package.

    Mirrors ``Packager.compute_content_hash``: publishable files sorted by POSIX
    relative path, one ``<relative>\\0<sha256(file)>\\n`` line per file into an
    outer SHA-256.  ``benchmark/harbor_receipts.py`` implements the same protocol
    and is used by the tests as an independent cross-check.
    """

    outer = hashlib.sha256()
    total = 0
    files = harbor_publishable_files(task_dir)
    for path in files:
        relative = path.relative_to(task_dir).as_posix()
        total += path.stat().st_size
        outer.update(f"{relative}\0{sha256_file(path)}\n".encode("utf-8"))
    return f"sha256:{outer.hexdigest()}", len(files), total


def tree_digest(root: Path) -> tuple[str, int, int]:
    """Order-independent digest of every file under ``root`` (relative path + bytes)."""

    outer = hashlib.sha256()
    total = 0
    files = sorted(
        (path for path in root.rglob("*") if path.is_file() and "__pycache__" not in path.parts),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    for path in files:
        relative = path.relative_to(root).as_posix()
        total += path.stat().st_size
        outer.update(f"{relative}\0{sha256_file(path)}\n".encode("utf-8"))
    return outer.hexdigest(), len(files), total


def payload_manifest(root: Path) -> tuple[str, int, int]:
    """The Hugging Face payload manifest of ``benchmark/huggingface_receipts.py``."""

    digest = hashlib.sha256()
    total = 0
    files = sorted(
        (path for path in root.rglob("*") if path.is_file() and ".cache" not in path.relative_to(root).parts),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    for path in files:
        size = path.stat().st_size
        total += size
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest(), len(files), total


def verifier_token(version: str, task_id: str, task_sha256: str) -> str:
    """Deterministic per-task verifier-channel token (raw token lives only in tests/)."""

    return hashlib.sha256(f"hubbench-verifier-token:{version}:{task_id}:{task_sha256}".encode("utf-8")).hexdigest()


def _toml_string(value: str) -> str:
    escaped = []
    for character in value:
        if character == '"':
            escaped.append('\\"')
        elif character == "\\":
            escaped.append("\\\\")
        elif character == "\n":
            escaped.append("\\n")
        elif character == "\r":
            escaped.append("\\r")
        elif character == "\t":
            escaped.append("\\t")
        elif ord(character) < 0x20 or character == "\x7f":
            escaped.append(f"\\u{ord(character):04X}")
        else:
            escaped.append(character)
    return '"' + "".join(escaped) + '"'


def _toml_list(values: list[str]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def _sorted_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sorted_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_sorted_value(item) for item in value]
    return value


# --------------------------------------------------------------------------- #
# Inputs: committed family releases and reports
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FamilyInputs:
    family: Family
    manifest: dict[str, Any]
    tasks: list[dict[str, Any]]
    contracts: dict[str, dict[str, Any]]
    qualification: dict[str, Any]
    chain: dict[str, Any]
    anchors: list[dict[str, Any]]
    manifest_sha256: str
    qualification_sha256: str
    chain_sha256: str

    @property
    def slug(self) -> str:
        return self.family.slug


def discover_families() -> list[str]:
    """Every family with a committed release tree, in slug order."""

    return sorted(path.parent.parent.name for path in (HUBBENCH_ROOT / "families").glob("*/release/manifest.json"))


def _provenance_anchors(task: dict[str, Any]) -> list[dict[str, Any]]:
    records = [record for record in task["assets"] if record["kind"] == "open_source_provenance"]
    if len(records) != 1:
        raise ValueError(f"{task['task_id']}: expected one open-source provenance record")
    payload = json.loads(records[0]["content"])
    return [_sorted_value(anchor) for anchor in payload["anchors"]]


def load_family_inputs(slug: str) -> FamilyInputs:
    family = load_family(slug)
    directory = release_dir(family)
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tasks = load_release_tasks(family, directory)
    if not tasks:
        raise ValueError(f"{slug}: no released tasks under {directory}")
    contracts = {task["task_id"]: load_release_contract(family, task["task_id"], directory) for task in tasks}
    by_id = {entry["task_id"]: entry for entry in manifest["tasks"]}
    if [task["task_id"] for task in tasks] != [entry["task_id"] for entry in manifest["tasks"]]:
        raise ValueError(f"{slug}: manifest task order disagrees with the release tasks")
    for task in tasks:
        entry = by_id[task["task_id"]]
        if entry["task_sha256"] != sha256_json(task):
            raise ValueError(f"{task['task_id']}: release task is stale relative to manifest.json")
        if entry["contract_sha256"] != sha256_json(contracts[task["task_id"]]) or sha256_json(sealed_contract(task)) != entry["contract_sha256"]:
            raise ValueError(f"{task['task_id']}: sealed contract is stale relative to manifest.json")
        for record in task["assets"]:
            if hashlib.sha256(asset_bytes(record)).hexdigest() != entry["assets"][record["path"]]:
                raise ValueError(f"{task['task_id']}/{record['path']}: evidence bytes disagree with manifest.json")
    qualification_path = REPORTS_DIR / f"{slug}-qualification.json"
    chain_path = REPORTS_DIR / "reasoning-chain" / f"{slug}.json"
    qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
    chain = json.loads(chain_path.read_text(encoding="utf-8"))
    if qualification.get("family") != slug or qualification.get("qualification_passed") is not True:
        raise ValueError(f"{slug}: committed qualification report is missing or not passed")
    if sorted(qualification["oracle"]["task_scores"]) != sorted(task["task_id"] for task in tasks):
        raise ValueError(f"{slug}: qualification report does not cover the released tasks")
    if chain.get("slug") != slug or chain.get("meetsStandard") is not True or chain.get("passingTasks") != len(tasks):
        raise ValueError(f"{slug}: committed reasoning-chain report is missing or not passing")
    if sorted(measure["taskId"] for measure in chain["taskMeasures"]) != sorted(task["task_id"] for task in tasks):
        raise ValueError(f"{slug}: reasoning-chain report does not cover the released tasks")
    anchors = _provenance_anchors(tasks[0])
    for task in tasks[1:]:
        if _provenance_anchors(task) != anchors:
            raise ValueError(f"{slug}: tasks disagree on their open-source anchors")
    return FamilyInputs(
        family=family,
        manifest=manifest,
        tasks=tasks,
        contracts=contracts,
        qualification=qualification,
        chain=chain,
        anchors=anchors,
        manifest_sha256=sha256_file(manifest_path),
        qualification_sha256=sha256_file(qualification_path),
        chain_sha256=sha256_file(chain_path),
    )


# --------------------------------------------------------------------------- #
# Vendored runtime subset
# --------------------------------------------------------------------------- #


def _engine_imports(path: Path) -> set[str]:
    """Engine modules a source file imports (relative or absolute ``hubbench.engine`` imports)."""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level == 1:
                if module:
                    names.add(module.split(".")[0])
                else:
                    names.update(alias.name for alias in node.names)
            elif node.level >= 2 and module.startswith("engine."):
                names.add(module.split(".")[1])
            elif node.level == 0 and module.startswith("hubbench.engine."):
                names.add(module.split(".")[2])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("hubbench.engine."):
                    names.add(alias.name.split(".")[2])
    return {name for name in names if (ENGINE_DIR / f"{name}.py").is_file()}


def engine_closure(roots: set[str]) -> set[str]:
    closure: set[str] = set()
    pending = {root for root in roots if (ENGINE_DIR / f"{root}.py").is_file()}
    while pending:
        name = pending.pop()
        if name in closure:
            continue
        closure.add(name)
        pending.update(_engine_imports(ENGINE_DIR / f"{name}.py") - closure)
    return closure


def runtime_engine_modules(family: Family, *, include_verifier: bool) -> list[str]:
    """Engine modules vendored into a task package; sealed modules are never vendored.

    The agent-reachable runtime (``environment/``) starts from the public surfaces
    (``cli``, ``server``, ``http``, ``world_service``); the root verifier runtime
    (``tests/``) starts from ``verifier`` alone.  Both add whatever the family's
    tool module imports.
    """

    roots = set(VERIFIER_ENGINE_MODULES) if include_verifier else set(RUNTIME_ROOTS)
    family_dir = HUBBENCH_ROOT / "families" / family.slug
    for name in FAMILY_RUNTIME_FILES:
        if name.endswith(".py"):
            roots.update(_engine_imports(family_dir / name))
    closure = engine_closure(roots)
    sealed = sorted(closure & SEALED_ENGINE_MODULES)
    if sealed:
        raise ValueError(f"runtime import closure reaches sealed engine modules {sealed}; refusing to vendor them")
    if not include_verifier and closure & VERIFIER_ENGINE_MODULES:
        raise ValueError("the agent-reachable runtime must not import the verifier")
    return sorted(closure)


def _family_shim(family: Family) -> str:
    organization = repr(_sorted_value(family.organization))
    return f'''"""{family.name}: vendored HubBench runtime family (provider-shaped tools + schema only).

Emitted by ``hubbench.engine.distribution`` for the distributed task package.  It
carries no task builder, no scenario data, no oracle policy, and no verifier
contract: the task world is loaded from the package's task.json.
"""

from __future__ import annotations

from pathlib import Path

from ...engine.families import Family
from .tools import SERVERS, TOOLS


def _no_task_builder() -> list:
    raise RuntimeError("the distributed {family.slug} runtime does not build tasks; load the task from task.json")


FAMILY = Family(
    slug={family.slug!r},
    name={family.name!r},
    version={family.version!r},
    cluster={family.cluster!r},
    description={family.description!r},
    schema_sql=Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"),
    servers=SERVERS,
    tools=TOOLS,
    build_tasks=_no_task_builder,
    organization={organization},
    as_of={family.as_of!r},
)

__all__ = ["FAMILY"]
'''


def vendor_runtime(target: Path, family: Family, *, include_verifier: bool) -> list[str]:
    """Copy the runtime subset into ``target/hubbench`` and return the vendored engine modules."""

    modules = runtime_engine_modules(family, include_verifier=include_verifier)
    package = target / "hubbench"
    _write_text(package / "__init__.py", (HUBBENCH_ROOT / "__init__.py").read_text(encoding="utf-8"))
    engine = package / "engine"
    _write_text(engine / "__init__.py", (ENGINE_DIR / "__init__.py").read_text(encoding="utf-8"))
    _write_text(engine / "core.sql", (ENGINE_DIR / "core.sql").read_text(encoding="utf-8"))
    for name in modules:
        _write_text(engine / f"{name}.py", (ENGINE_DIR / f"{name}.py").read_text(encoding="utf-8"))
    families = package / "families"
    _write_text(families / "__init__.py", (HUBBENCH_ROOT / "families" / "__init__.py").read_text(encoding="utf-8"))
    family_dir = HUBBENCH_ROOT / "families" / family.slug
    _write_text(families / family.slug / "__init__.py", _family_shim(family))
    for name in FAMILY_RUNTIME_FILES:
        _write_text(families / family.slug / name, (family_dir / name).read_text(encoding="utf-8"))
    return modules


# --------------------------------------------------------------------------- #
# Task package templates
# --------------------------------------------------------------------------- #


def harbor_task_id(task: dict[str, Any]) -> str:
    family, _, number = task["task_id"].rpartition("-")
    if family != task["family"] or not number.isdigit():
        raise ValueError(f"{task['task_id']}: task ids must be <family>-NNN")
    return f"hubbench-{family}-{number}"


def harbor_task_name(task: dict[str, Any]) -> str:
    return f"{HARBOR_ORG}/{harbor_task_id(task)}"


def public_task(task: dict[str, Any]) -> dict[str, Any]:
    """The task as the world runtime sees it: no contract, no oracle, no builder inputs."""

    record = {key: task[key] for key in PUBLIC_TASK_KEYS if key in task}
    leaked = sorted(set(record) & set(SEALED_TASK_KEYS))
    if leaked:
        raise ValueError(f"{task['task_id']}: sealed keys in the public task: {leaked}")
    return record


def verifier_task(task: dict[str, Any]) -> dict[str, Any]:
    """The sealed task the root verifier grades with (world data already lives in the database)."""

    return {key: value for key, value in task.items() if key not in VERIFIER_TASK_EXCLUDED}


def task_servers(family: Family, task: dict[str, Any]) -> list[str]:
    """Every provider server the world mounts for the task plus the benchmark control server."""

    unknown = sorted(set(task["world"]["systems"]) - set(family.servers))
    if unknown:
        raise ValueError(f"{task['task_id']}: world systems not declared by the family: {unknown}")
    return [*sorted(family.servers), ENGINE_SERVER]


def _task_toml(inputs: FamilyInputs, task: dict[str, Any], version: str, *, evidence_count: int, criteria: int) -> str:
    family = inputs.family
    keywords = ["hubbench", family.slug, family.cluster, task["mode"], "mcp", "stateful", "multi-system", "deterministic", "clean-room-synthetic"]
    servers = "\n".join(
        f"[[environment.mcp_servers]]\nname = {_toml_string(server)}\ntransport = \"streamable-http\"\nurl = {_toml_string(f'http://{WORLD_HOST}:{WORLD_PORT}/mcp/{server}')}\n"
        for server in task_servers(family, task)
    )
    return f'''schema_version = "1.4"

[task]
name = {_toml_string(harbor_task_name(task))}
version = {_toml_string(version)}
description = {_toml_string(task["instruction"])}
authors = [{{ name = "Blobfish AI" }}]
keywords = {_toml_list(keywords)}

[agent]
user = "agent"
timeout_sec = 1200.0

[verifier]
user = "root"
timeout_sec = 120.0

[environment]
build_timeout_sec = 600.0
cpus = 1
memory_mb = 1024
storage_mb = 2048
gpus = 0

{servers}
[metadata]
benchmark = {_toml_string(BENCHMARK)}
version = {_toml_string(version)}
family = {_toml_string(family.slug)}
family_name = {_toml_string(family.name)}
family_version = {_toml_string(family.version)}
cluster = {_toml_string(family.cluster)}
task_id = {_toml_string(harbor_task_id(task))}
family_task_id = {_toml_string(task["task_id"])}
title = {_toml_string(task["title"])}
mode = {_toml_string(task["mode"])}
role = {_toml_string(task["role"])}
as_of = {_toml_string(task["as_of"])}
metric = {_toml_string(METRIC)}
evidence_files = {evidence_count}
atomic_criteria = {criteria}
graded_answer_fields = {len(task["expected"]["answer"])}
synthetic = true
llm_judge = false
hub_anchors = {_toml_list([anchor["harbor_dataset"] for anchor in inputs.anchors])}
page = {_toml_string(PAGE_URL)}
'''


def _instruction_md(task: dict[str, Any]) -> str:
    return f"{task['instruction']}\n\n{ORIENTATION}\n"


def _task_readme(inputs: FamilyInputs, task: dict[str, Any], version: str, *, criteria: int, servers: list[str]) -> str:
    family = inputs.family
    contracts = family.server_contracts()
    server_lines = "\n".join(f"- `{server}` — {contracts[server]['description']} ({len(contracts[server]['tools'])} tools)" for server in servers)
    evidence = "\n".join(f"- `{record['path']}` — {record['title']} ({record['media_type']})" for record in sorted(task["assets"], key=lambda item: item["path"]))
    anchors = "\n".join(f"- {anchor['name']}: `{anchor['harbor_dataset']}` — {anchor['relationship']}" for anchor in inputs.anchors)
    return f"""# {harbor_task_id(task)} — {task['title']}

{BENCHMARK} {version} · family **{family.name}** (`{family.slug}`, cluster `{family.cluster}`) · decision mode `{task['mode']}` · role `{task['role']}` · as of {task['as_of']}.

{family.description}

## What the agent gets

The agent works as a non-root user in the `main` container and reaches the isolated, stateful world only through its public surfaces on the `world` service:

- MCP over streamable HTTP, one endpoint per server: `http://{WORLD_HOST}:{WORLD_PORT}/mcp/<server>`
- the terminal `tool` CLI (`tool list`, `tool schema <name>`, `tool <name> '<json>'`), bound to the same world through `HUBBENCH_URL`
- the REST API under `http://{WORLD_HOST}:{WORLD_PORT}/api/v1/`
- the web console at `http://{WORLD_HOST}:{WORLD_PORT}/`

Servers mounted for this task:

{server_lines}

Evidence files under `/workspace/evidence` ({len(task['assets'])} files):

{evidence}

## How it is graded

The verifier runs as root after the episode, pulls the finished world over a token-gated, read-only channel that the agent user cannot open, and computes **{METRIC}** (0–1 reward = score / 100) from executable checks only: required investigations before the first write, provider payload assertions, post-write readbacks, write containment, exact graded answer fields, and semantic milestone aggregation ({criteria} atomic criteria, {len(task['expected']['answer'])} graded answer fields). No LLM judge is called. Exact call order is not graded.

The sealed contract, expected answer, and oracle policy live only in `tests/` and `solution/`; they are not present in either container image.

## Provenance

Clean-room synthetic data; no real patient, employee, supplier, or organisation is represented. Public Harbor Hub anchors for this family (evaluation-shape inspiration only):

{anchors}

More: {PAGE_URL}
"""


def _agent_dockerfile(family: Family) -> str:
    return f'''FROM {HARBOR_IMAGE}
RUN groupadd --gid {AGENT_UID} agent \\
    && useradd --uid {AGENT_UID} --gid {AGENT_UID} --create-home --shell /bin/bash agent \\
    && install -d -o agent -g agent -m 0755 /workspace \\
    && install -d -o root -g root -m 0755 /opt/hubbench/hubbench
COPY hubbench/__init__.py /opt/hubbench/hubbench/__init__.py
COPY hubbench/engine /opt/hubbench/hubbench/engine
COPY tools.json /opt/hubbench/tools.json
COPY evidence /workspace/evidence
COPY tool /usr/local/bin/tool
RUN chown -R root:root /opt/hubbench /workspace/evidence \\
    && chmod -R u=rwX,go=rX /opt/hubbench /workspace/evidence \\
    && chmod 0755 /usr/local/bin/tool
WORKDIR /workspace
ENV HUBBENCH_URL=http://{WORLD_HOST}:{WORLD_PORT} HUBBENCH_RUNTIME=/opt/hubbench HUBBENCH_FAMILY={family.slug} PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
CMD ["sh", "-c", "sleep infinity"]
'''


def _world_dockerfile(family: Family, token_sha256: str) -> str:
    return f'''FROM {HARBOR_IMAGE}
RUN install -d -o root -g root -m 0700 /var/lib/hubbench \\
    && install -d -o root -g root -m 0755 /opt/hubbench
COPY hubbench /opt/hubbench/hubbench
COPY task.json tools.json /opt/hubbench/
RUN chown -R root:root /opt/hubbench \\
    && chmod -R u=rwX,go=rX /opt/hubbench \\
    && chmod 0444 /opt/hubbench/task.json /opt/hubbench/tools.json
WORKDIR /opt/hubbench
ENV PYTHONPATH=/opt/hubbench PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HUBBENCH_FAMILY={family.slug} HUBBENCH_VERIFIER_TOKEN_SHA256={token_sha256}
CMD ["python3", "-m", "hubbench.engine.world_service", "--family", "{family.slug}", "--task", "/opt/hubbench/task.json", "--db", "/var/lib/hubbench/world.db", "--fresh", "--host", "0.0.0.0", "--port", "{WORLD_PORT}", "--private-port", "{PRIVATE_PORT}"]
'''


DOCKER_COMPOSE = f'''services:
  main:
    depends_on:
      world:
        condition: service_healthy
    environment:
      HUBBENCH_URL: http://{WORLD_HOST}:{WORLD_PORT}
    networks: [agent-egress, hubbench]
  world:
    build:
      context: .
      dockerfile: Dockerfile.world
    healthcheck:
      test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:{PRIVATE_PORT}/health', timeout=1)"]
      interval: 1s
      timeout: 2s
      retries: 30
    networks: [hubbench]
networks:
  agent-egress: {{}}
  hubbench:
    internal: true
'''


TOOL_LAUNCHER = '''#!/usr/bin/env python3
"""HubBench `tool` CLI: `tool list`, `tool schema <name>`, `tool <name> '<json>'` against the task world at HUBBENCH_URL."""

import os
import sys
from pathlib import Path

for candidate in (os.environ.get("HUBBENCH_RUNTIME"), "/opt/hubbench", str(Path(__file__).resolve().parent)):
    if candidate and (Path(candidate) / "hubbench" / "engine" / "cli.py").is_file():
        sys.path.insert(0, candidate)
        break
else:
    raise SystemExit("hubbench runtime not found; set HUBBENCH_RUNTIME")

from hubbench.engine.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
'''


VERIFY_SCRIPT = '''#!/usr/bin/env python3
"""HubBench verifier: pull the finished world over the root-only channel and grade it (HubScore).

Runs as root after the episode.  The raw channel token ships only with this
tests/ tree; the world container holds its SHA-256 alone.  Reward = score / 100.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from hubbench.engine.families import load_family  # noqa: E402
from hubbench.engine.verifier import verify_episode  # noqa: E402
from hubbench.engine.world import World  # noqa: E402

TOKEN_HEADER = "X-HubBench-Verifier-Token"


def fetch(url: str, token: str, attempts: int = 30) -> bytes:
    request = urllib.request.Request(url, headers={TOKEN_HEADER: token})
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403, 404, 405):
                raise SystemExit(f"verifier channel refused {url}: HTTP {exc.code}") from exc
            last = exc
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
            last = exc
        time.sleep(min(2.0, 0.25 * (attempt + 1)))
    raise SystemExit(f"verifier channel unreachable at {url}: {last}")


def main() -> int:
    task = json.loads((HERE / "task.json").read_text(encoding="utf-8"))
    token = (HERE / "verifier-token").read_text(encoding="utf-8").strip()
    base = os.environ.get("HUBBENCH_VERIFIER_URL", "http://__WORLD_HOST__:__PRIVATE_PORT__").rstrip("/")
    logs = Path(os.environ.get("HUBBENCH_LOGS_DIR", "/logs/verifier"))
    logs.mkdir(parents=True, exist_ok=True)
    database = logs / "world.db"
    database.write_bytes(fetch(f"{base}/verifier/world.db", token))
    family = load_family(task["family"])
    with World(family, task, database) as world:
        verdict = verify_episode(task, world)
        trace = world.trace
    reward = round(verdict["score"] / 100.0, 6)
    (logs / "reward.txt").write_text(f"{reward:.6f}\\n", encoding="utf-8")
    (logs / "verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
    (logs / "trace.json").write_text(json.dumps({"task_id": task["task_id"], "trace": trace}, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
    print(json.dumps({"task_id": task["task_id"], "metric": verdict["metric"], "score": verdict["score"], "strict_pass": verdict["strict_pass"], "reward": reward}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


SOLVE_SCRIPT = '''#!/usr/bin/env python3
"""HubBench oracle: replay the reference policy THROUGH the public surfaces.

Context and investigation reads go over MCP streamable HTTP (one endpoint per
server), the primary state change and its readback over the REST API, the
stakeholder draft through the `tool` CLI, and the structured answer through
POST /api/v1/submit, so a reward of 1.0 proves every surface end to end — not
just the world.  Set HUBBENCH_SOLVE_SURFACE=mcp|rest|cli to force one surface.
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = os.environ.get("HUBBENCH_URL", "http://__WORLD_HOST__:__WORLD_PORT__").rstrip("/")
TOOL = os.environ.get("HUBBENCH_TOOL", "tool")
SURFACE = os.environ.get("HUBBENCH_SOLVE_SURFACE", "mixed")
ROUTES = {
    "context": "mcp",
    "investigation": "mcp",
    "primary_mutation": "rest",
    "collaboration": "cli",
    "post_write_verification": "rest",
    "answer": "submit",
}
PROTOCOL_VERSION = "2025-03-26"


def request(method: str, path: str, payload=None, headers=None, timeout: float = 60.0):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    base_headers = {"Accept": "application/json, text/event-stream"}
    if data is not None:
        base_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={**base_headers, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, response.headers, response.read().decode("utf-8")


def wait_ready(attempts: int = 120) -> dict:
    last = None
    for attempt in range(attempts):
        try:
            _, _, body = request("GET", "/api/v1/task")
            return json.loads(body)
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(min(2.0, 0.25 * (attempt + 1)))
    raise SystemExit(f"world not reachable at {BASE}: {last}")


def parse_message(body: str, content_type: str, request_id):
    if "text/event-stream" in content_type:
        messages = [json.loads(line[5:].strip()) for line in body.splitlines() if line.startswith("data:") and line[5:].strip()]
        for message in messages:
            if isinstance(message, dict) and message.get("id") == request_id:
                return message
        return messages[-1] if messages else None
    return json.loads(body) if body.strip() else None


class Mcp:
    def __init__(self) -> None:
        self.sessions: dict[str, str | None] = {}
        self.counter = 0

    def send(self, server: str, method: str, params=None, *, notification: bool = False):
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notification:
            self.counter += 1
            payload["id"] = self.counter
        headers = {}
        if self.sessions.get(server):
            headers["Mcp-Session-Id"] = self.sessions[server]
        status, response_headers, body = request("POST", f"/mcp/{server}", payload, headers)
        session = response_headers.get("Mcp-Session-Id")
        if session:
            self.sessions[server] = session
        if notification:
            return None
        return parse_message(body, response_headers.get("Content-Type", ""), payload["id"])

    def initialize(self, server: str) -> None:
        if server in self.sessions:
            return
        self.sessions[server] = None
        self.send(server, "initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": "hubbench-oracle", "version": "1.0.0"}})
        self.send(server, "notifications/initialized", notification=True)

    def call(self, name: str, arguments: dict) -> dict:
        server = name.split(".", 1)[0]
        self.initialize(server)
        message = self.send(server, "tools/call", {"name": name, "arguments": arguments})
        if message is None or "error" in message:
            raise SystemExit(f"MCP tools/call failed for {name}: {message}")
        result = message["result"]
        content = result.get("content") or []
        text = next((item.get("text") for item in content if item.get("type") == "text"), None)
        return json.loads(text) if text is not None else result.get("structuredContent", {})


def rest_call(name: str, arguments: dict) -> dict:
    try:
        _, _, body = request("POST", f"/api/v1/tools/{name}", arguments)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
    payload = json.loads(body) if body.strip() else {}
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict) and "tool" in payload:
        return payload["result"]
    return payload


def rest_submit(fields: dict) -> dict:
    try:
        _, _, body = request("POST", "/api/v1/submit", fields)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
    payload = json.loads(body) if body.strip() else {}
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict) and "tool" in payload:
        return payload["result"]
    return payload


def cli_call(name: str, arguments: dict) -> dict:
    env = {**os.environ, "HUBBENCH_URL": BASE}
    completed = subprocess.run([TOOL, name, json.dumps(arguments)], capture_output=True, text=True, env=env, timeout=120)
    if completed.returncode not in (0, 1) or not completed.stdout.strip():
        raise SystemExit(f"tool CLI failed for {name}: rc={completed.returncode} {completed.stderr.strip()}")
    return json.loads(completed.stdout)


def main() -> int:
    oracle = json.loads((HERE / "oracle.json").read_text(encoding="utf-8"))
    task = wait_ready()
    served = task.get("task_id") or (task.get("task") or {}).get("task_id")
    if served and served != oracle["task_id"]:
        raise SystemExit(f"world serves {served}, oracle is for {oracle['task_id']}")
    _, _, listing = request("GET", "/api/v1/tools")
    if oracle["submit_tool"] not in listing:
        raise SystemExit("REST tool listing does not expose the answer control")
    _, headers, page = request("GET", "/")
    if "html" not in (headers.get("Content-Type", "") + page[:200]).lower():
        raise SystemExit("web console did not answer with HTML")
    mcp = Mcp()
    outcomes = []
    for index, step in enumerate(oracle["steps"], start=1):
        surface = ROUTES.get(step["phase"], "mcp") if SURFACE == "mixed" else SURFACE
        if step["tool"] == oracle["submit_tool"] and surface in ("submit", "rest"):
            result = rest_submit(step["arguments"])
        elif surface == "submit":
            result = rest_call(step["tool"], step["arguments"])
        elif surface == "rest":
            result = rest_call(step["tool"], step["arguments"])
        elif surface == "cli":
            result = cli_call(step["tool"], step["arguments"])
        else:
            result = mcp.call(step["tool"], step["arguments"])
        outcomes.append({"index": index, "tool": step["tool"], "surface": surface, "error": result.get("error") if isinstance(result, dict) else None})
    errors = [outcome for outcome in outcomes if outcome["error"]]
    print(json.dumps({"task_id": oracle["task_id"], "steps": len(outcomes), "surfaces": sorted({o["surface"] for o in outcomes}), "tool_errors": errors}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def _render(template: str) -> str:
    return template.replace("__WORLD_HOST__", WORLD_HOST).replace("__WORLD_PORT__", str(WORLD_PORT)).replace("__PRIVATE_PORT__", str(PRIVATE_PORT))


# --------------------------------------------------------------------------- #
# Harbor task packages
# --------------------------------------------------------------------------- #


def _atomic_criteria(task: dict[str, Any]) -> int:
    return sum(len(milestone["criterion_ids"]) for milestone in task["rubric_milestones"])


def write_task_package(root: Path, inputs: FamilyInputs, task: dict[str, Any], version: str) -> dict[str, Any]:
    family = inputs.family
    task_id = harbor_task_id(task)
    task_dir = root / task_id
    environment = task_dir / "environment"
    tests = task_dir / "tests"
    solution = task_dir / "solution"
    entry = next(item for item in inputs.manifest["tasks"] if item["task_id"] == task["task_id"])
    token = verifier_token(version, task_id, entry["task_sha256"])
    token_sha256 = hashlib.sha256(token.encode("utf-8")).hexdigest()
    criteria = _atomic_criteria(task)
    servers = task_servers(family, task)
    tools = public_tool_definitions(family, task["answer_schema"])

    toml_text = _task_toml(inputs, task, version, evidence_count=len(task["assets"]), criteria=criteria)
    parsed = tomllib.loads(toml_text)
    if parsed["task"]["description"] != task["instruction"] or parsed["task"]["name"] != harbor_task_name(task):
        raise ValueError(f"{task_id}: task.toml round-trip failed")
    _write_text(task_dir / "task.toml", toml_text)
    _write_text(task_dir / "instruction.md", _instruction_md(task))
    _write_text(task_dir / "README.md", _task_readme(inputs, task, version, criteria=criteria, servers=servers))

    runtime_modules = vendor_runtime(environment, family, include_verifier=False)
    _write_json(environment / "task.json", public_task(task))
    _write_json(
        environment / "tools.json",
        {
            "schema_version": "hubbench.tool-contract.v1",
            "benchmark": BENCHMARK,
            "family": family.slug,
            "task_id": task_id,
            "servers": {server: family.server_contracts()[server] for server in servers},
            "tools": tools,
        },
    )
    for record in task["assets"]:
        _write_bytes(environment / "evidence" / record["path"], asset_bytes(record))
    _write_text(environment / "tool", TOOL_LAUNCHER, executable=True)
    _write_text(environment / "Dockerfile", _agent_dockerfile(family))
    _write_text(environment / "Dockerfile.world", _world_dockerfile(family, token_sha256))
    _write_text(environment / "docker-compose.yaml", DOCKER_COMPOSE)
    _write_text(environment / "verifier-token.sha256", token_sha256 + "\n")

    _write_text(tests / "test.sh", '#!/bin/bash\nset -euo pipefail\npython3 "$(dirname "$0")/verify.py"\n', executable=True)
    _write_text(tests / "verify.py", _render(VERIFY_SCRIPT), executable=True)
    _write_json(tests / "task.json", verifier_task(task))
    _write_json(tests / "contract.json", inputs.contracts[task["task_id"]])
    _write_text(tests / "verifier-token", token + "\n")
    verifier_modules = vendor_runtime(tests, family, include_verifier=True)

    _write_text(solution / "solve.sh", '#!/bin/bash\nset -euo pipefail\npython3 "$(dirname "$0")/solve.py"\n', executable=True)
    _write_text(solution / "solve.py", _render(SOLVE_SCRIPT), executable=True)
    _write_json(
        solution / "oracle.json",
        {
            "task_id": task["task_id"],
            "harbor_task_id": task_id,
            "context_tool": CONTEXT_TOOL,
            "submit_tool": SUBMIT_TOOL,
            "steps": task["oracle_steps"],
            "expected_answer": task["expected"]["answer"],
        },
    )

    digest, files, size = harbor_task_digest(task_dir)
    return {
        "task_id": task_id,
        "name": harbor_task_name(task),
        "family": family.slug,
        "family_task_id": task["task_id"],
        "mode": task["mode"],
        "digest": digest,
        "files": files,
        "bytes": size,
        "servers": servers,
        "tool_count": len(tools),
        "evidence_files": len(task["assets"]),
        "atomic_criteria": criteria,
        "graded_answer_fields": len(task["expected"]["answer"]),
        "reference_tool_calls": len(task["oracle_steps"]),
        "task_sha256": entry["task_sha256"],
        "contract_sha256": entry["contract_sha256"],
        "verifier_token_sha256": token_sha256,
        "runtime_engine_modules": runtime_modules,
        "verifier_engine_modules": verifier_modules,
    }


def _dataset_readme(version: str, families: list[FamilyInputs], totals: dict[str, Any]) -> str:
    rows = "\n".join(
        f"| {inputs.family.name} (`{inputs.slug}`) | {inputs.family.cluster} | {len(inputs.tasks)} | {len(inputs.family.servers) + 1} | {inputs.manifest['tool_count']} |"
        for inputs in families
    )
    qualification = totals["qualification"]
    return f"""# {BENCHMARK} {version}

One Blobfish-authored, oracle-proven benchmark family per Harbor Hub professional-domain cluster: mock stateful tools over an isolated SQLite world, reachable as MCP servers over streamable HTTP, a terminal `tool` CLI, a REST API, and a web console, graded by the deterministic **{METRIC}** verifier (zero LLM judge). Every task is an employee decision worked over a dependent chain of evidence — never a lookup.

| Family | Cluster | Tasks | MCP servers | Tools |
|---|---|---|---|---|
{rows}

{totals['tasks']} tasks across {totals['families']} families. Qualification: {qualification['oracle_passes']}/{totals['tasks']} oracle strict passes at mean {qualification['oracle_mean_score']}, {qualification['exact_episode_matches']}/{qualification['deterministic_replays']} byte-identical replays, {qualification['negative_control_executions']} negative-control executions across {qualification['negative_control_policies']} policies with {qualification['false_accepts']} false accepts, {qualification['mutation_omissions_detected']}/{qualification['mutation_omissions_total']} mutation omissions detected.

## Run

```bash
harbor run -d {HARBOR_DATASET}@v{version} -a <agent> -m <provider/model>
```

Each task package is self-contained: a digest-pinned `python:3.12-slim` agent image (non-root `agent`, `tool` on PATH, evidence under `/workspace/evidence`) and a `world` service exposing the surfaces on port {WORLD_PORT}. The verifier runs as root, pulls the finished world over a token-gated read-only channel, and writes `/logs/verifier/reward.txt` (= {METRIC} / 100).

All data is clean-room synthetic; no real patient, employee, supplier, or organisation is represented. Page: {PAGE_URL} · Hugging Face: {HF_URL}
"""


def write_harbor_dataset(output: Path, families: list[FamilyInputs], version: str) -> dict[str, Any]:
    harbor = output / "harbor"
    tasks: list[dict[str, Any]] = []
    for inputs in families:
        for task in inputs.tasks:
            tasks.append(write_task_package(harbor / "tasks", inputs, task, version))
    names = {row["name"] for row in tasks}
    if HARBOR_DATASET in names or len(names) != len(tasks):
        raise ValueError("the Harbor dataset name collides with a task package name")
    lines = [
        f"# Generated {BENCHMARK} Harbor dataset",
        "[dataset]",
        f"name = {_toml_string(HARBOR_DATASET)}",
        f"version = {_toml_string(version)}",
        f"description = {_toml_string(f'{BENCHMARK}: one oracle-proven, deterministically graded Blobfish benchmark family per Harbor Hub professional-domain cluster — {len(tasks)} stateful multi-system employee-decision tasks over isolated SQLite worlds ({METRIC}, no LLM judge)')}",
        f"keywords = {_toml_list(['hubbench', 'agents', 'mcp', 'stateful', 'multi-system', 'deterministic', 'executable-verifier', *sorted(inputs.family.cluster for inputs in families)])}",
        "[[dataset.authors]]",
        'name = "Blobfish AI"',
        "",
    ]
    for row in tasks:
        lines.extend(["[[tasks]]", f"name = {_toml_string(row['name'])}", f"digest = {_toml_string(row['digest'])}", ""])
    _write_text(harbor / "dataset.toml", "\n".join(lines))
    parsed = tomllib.loads((harbor / "dataset.toml").read_text(encoding="utf-8"))
    if parsed["dataset"]["name"] != HARBOR_DATASET or len(parsed["tasks"]) != len(tasks):
        raise ValueError("dataset.toml round-trip failed")
    _write_json(
        harbor / "task-digests.json",
        {
            "schema_version": "hubbench.harbor-digests.v1",
            "dataset": HARBOR_DATASET,
            "version": version,
            "digest_algorithm": "harbor-0.21 publisher content hash: publishable files (task.toml, instruction.md, README.md, environment/, tests/, solution/, steps/) sorted by POSIX path; sha256 over '<relative>\\0<sha256(file)>\\n' lines",
            "tasks": [{key: row[key] for key in ("task_id", "name", "family", "digest", "files", "bytes")} for row in tasks],
        },
    )
    _write_text(harbor / "NOTICE", f"{BENCHMARK} is independently authored, clean-room synthetic benchmark material by Blobfish AI. The engine is Apache-2.0 (see the source repository NOTICE); the task data is CC BY 4.0. See ANCHORS.md in the Hugging Face release for the public Harbor Hub anchors and clean-room boundary.\n")
    return {"dataset": HARBOR_DATASET, "version": version, "tasks": tasks}


# --------------------------------------------------------------------------- #
# Hugging Face dataset and public records
# --------------------------------------------------------------------------- #


def public_record(inputs: FamilyInputs, task: dict[str, Any], harbor_row: dict[str, Any]) -> dict[str, Any]:
    family = inputs.family
    return {
        "task_id": harbor_row["task_id"],
        "harbor_task": harbor_row["name"],
        "harbor_digest": harbor_row["digest"],
        "family_task_id": task["task_id"],
        "family": family.slug,
        "family_name": family.name,
        "cluster": family.cluster,
        "benchmark": BENCHMARK,
        "metric": METRIC,
        "mode": task["mode"],
        "title": task["title"],
        "role": task["role"],
        "as_of": task["as_of"],
        "instruction": task["instruction"],
        "world": {"id": task["world"]["id"], "name": task["world"]["name"], "systems": task["world"]["systems"]},
        "servers": harbor_row["servers"],
        "tools": inputs.manifest["tools"],
        "evidence_files": [
            {"path": record["path"], "kind": record["kind"], "media_type": record["media_type"], "title": record["title"], "sha256": record["sha256"]}
            for record in sorted(task["assets"], key=lambda item: item["path"])
        ],
        "graded_answer_fields": sorted(task["expected"]["answer"]),
        "answer_schema": task["answer_schema"],
        "atomic_criteria": harbor_row["atomic_criteria"],
        "rubric_milestone_count": len(task["rubric_milestones"]),
        "reference_tool_calls": harbor_row["reference_tool_calls"],
        "evidence_reads_before_decision": len(task["required_investigations"]),
        "hub_anchors": [anchor["harbor_dataset"] for anchor in inputs.anchors],
        "task_sha256": harbor_row["task_sha256"],
        "contract_sha256": harbor_row["contract_sha256"],
        "synthetic": True,
        "llm_judge_calls": 0,
    }


def _anchors_text(families: list[FamilyInputs]) -> str:
    sections = []
    for inputs in families:
        lines = "\n".join(
            f"- **{anchor['name']}** — Harbor `{anchor['harbor_dataset']}` ({anchor['harbor_url']}); upstream {anchor['upstream_url']}; "
            f"license {anchor.get('license', 'see upstream')}"
            + (f" ({anchor['distribution_note']})" if anchor.get('distribution_note') else "")
            + f". Evaluation shape: {anchor['evaluation_shape']}. Relationship: {anchor['relationship']}."
            for anchor in inputs.anchors
        )
        sections.append(f"## {inputs.family.name} (`{inputs.slug}`, cluster `{inputs.family.cluster}`)\n\n{lines}")
    body = "\n\n".join(sections)
    return f"""# Public design anchors and clean-room boundary

{BENCHMARK} is independently authored. Each family names the public Harbor Hub datasets whose *evaluation shape* informed it. No upstream task, fixture, prompt, seed record, attachment, answer, or score was copied, adapted, redistributed, or claimed; every case, record, tool response, and answer is clean-room synthetic (`clean_room: true`, `upstream_tasks_copied: false`, `upstream_scores_claimed: false` in every task's provenance record). Gated upstream distributions were not downloaded.

{body}

The engine (world, stateful surfaces, deterministic verifier, negative controls) is a domain-agnostic port of the Apache-2.0 FactoryBench-100 engine by Blobfish AI.
"""


def _hf_card(version: str, families: list[FamilyInputs], totals: dict[str, Any], harbor: dict[str, Any]) -> str:
    family_rows = "\n".join(
        f"| {inputs.family.name} (`{inputs.slug}`) | {inputs.family.cluster} | {len(inputs.tasks)} | {len(inputs.family.servers) + 1} | {inputs.manifest['tool_count']} "
        f"| {_span(_atomic_criteria(task) for task in inputs.tasks)} | {_span(len(task['expected']['answer']) for task in inputs.tasks)} "
        f"| {_span(len(task['assets']) for task in inputs.tasks)} | {', '.join('`' + anchor['harbor_dataset'] + '`' for anchor in inputs.anchors)} |"
        for inputs in families
    )
    qualification_rows = "\n".join(
        f"| `{inputs.slug}` | {q['oracle']['passes']}/{q['oracle']['executions']} at {q['oracle']['mean_score']} | {q['determinism']['exact_episode_matches']}/{q['determinism']['replays']} "
        f"| {sum(control['executions'] for control in q['negative_controls'].values())} across {len(q['negative_controls'])} policies | {q['false_accepts']} "
        f"| {q['mutation_omissions']['detected']}/{q['mutation_omissions']['total']} | {q['executions']} |"
        for inputs in families
        for q in [inputs.qualification]
    )
    chain_rows = "\n".join(
        f"| `{inputs.slug}` | {c['passingTasks']}/{c['measuredTasks']} | {c['chainDepth']['min']}–{c['chainDepth']['max']} | {_hops(c)} "
        f"| {c['dependentDerivations']['min']}–{c['dependentDerivations']['max']} | {c['evidenceReadsBeforeDecision']['min']}–{c['evidenceReadsBeforeDecision']['max']} "
        f"| {c['sourceSystemsBeforeDecision']['min']}–{c['sourceSystemsBeforeDecision']['max']} | {c['gradedAnswerFields']['min']}–{c['gradedAnswerFields']['max']} |"
        for inputs in families
        for c in [inputs.chain]
    )
    q = totals["qualification"]
    c = totals["reasoning_chain"]
    families_text = ", ".join(f"{inputs.family.name} ({inputs.family.cluster})" for inputs in families)
    return f"""---
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
{chr(10).join('- ' + inputs.family.cluster for inputs in families)}
pretty_name: {BENCHMARK}
size_categories:
- n<1K
---

# {BENCHMARK} {version}

**One Blobfish-authored, oracle-proven benchmark family per Harbor Hub professional-domain cluster.** Every task is an employee decision worked over a dependent chain of evidence — never a lookup — against mock stateful tools over an isolated SQLite world. The agent reaches the world only through its public surfaces (MCP over streamable HTTP, a terminal `tool` CLI, a REST API, and a web console); a deterministic verifier (**{METRIC}**) grades the finished world from executable checks only. Zero LLM-judge calls.

Released families: {families_text}. {totals['tasks']} tasks, {totals['tools']} provider-shaped tools across {totals['servers']} MCP servers, {totals['evidence_files']} agent-visible evidence files, {totals['atomic_criteria']} atomic criteria.

## Families

| Family | Cluster | Tasks | MCP servers | Tools | Criteria / task | Graded answer fields / task | Evidence files / task | Harbor Hub anchors |
|---|---|---|---|---|---|---|---|---|
{family_rows}

## {METRIC}

{METRIC} is contract-driven and deterministic: required investigations before the first write, provider payload assertions on the persisted state change, post-write readbacks, write containment, exact graded answer fields (every intermediate value of the decision chain), and semantic milestone aggregation into 14 weighted milestones summing to 100. Reward = {METRIC} / 100; a task is a strict pass only when every milestone passes. Exact call order is not graded.

## Qualification (computed from the committed reports)

| Family | Oracle strict passes (mean {METRIC}) | Deterministic replays | Negative-control executions | False accepts | Mutation omissions detected | Executions |
|---|---|---|---|---|---|---|
{qualification_rows}

Totals: {q['oracle_passes']}/{totals['tasks']} oracle strict passes at mean {q['oracle_mean_score']}; {q['exact_episode_matches']}/{q['deterministic_replays']} byte-identical replays; {q['negative_control_executions']} negative-control executions across {q['negative_control_policies']} policies ({', '.join(q['negative_control_policy_names'])}) with {q['false_accepts']} false accepts; {q['mutation_omissions_detected']}/{q['mutation_omissions_total']} mutation omissions detected; {q['executions']} qualification executions in total.

## Reasoning-chain audit (computed from the committed reports)

Measured with the unmodified portfolio audit (`benchmark/reasoning_chain_audit.py`, hop classes H1–H13):

| Family | Passing tasks | Chain depth | Hop coverage H1–H13 | Dependent derivations | Evidence reads before decision | Source systems | Graded answer fields |
|---|---|---|---|---|---|---|---|
{chain_rows}

Totals: {c['passing_tasks']}/{c['measured_tasks']} tasks pass; every one of the 13 hop classes is covered by all {c['measured_tasks']} tasks ({c['hop_coverage_min']}–{c['hop_coverage_max']} per hop); dependent derivations {c['dependent_derivations_min']}–{c['dependent_derivations_max']}; evidence reads before the decision {c['evidence_reads_min']}–{c['evidence_reads_max']}.

## Run on Harbor

```bash
harbor run -d {HARBOR_DATASET}@v{version} -a <agent> -m <provider/model>
```

Harbor dataset: `{HARBOR_DATASET}` ({len(harbor['tasks'])} task packages `{HARBOR_ORG}/hubbench-<family>-NNN`, root digest `{harbor['root_sha256']}`). Each package is self-contained on a digest-pinned `python:3.12-slim` base: an agent container (non-root `agent`, `tool` on PATH, evidence under `/workspace/evidence`) and a `world` service on port {WORLD_PORT}. The sealed contract, expected answer, and oracle policy exist only in `tests/` (root verifier) and `solution/` (oracle replayed through the HTTP surfaces).

## Layout

- `data/tasks.jsonl` — one public record per task: identity, cluster, mode, instruction, mounted servers and tools, evidence file list, graded answer *field names* (no gold values), digests.
- `assets/<task>/…` — the agent-visible evidence files in their native formats (`.xlsx`, `.pdf`, `.eml`, `.csv`, `.json`, `.md`, `.yaml`, `.log`).
- `contracts/tools.json` — the provider-shaped MCP tool contracts per family.
- `verifiers/<task>.json` — the sealed verifier contracts (expected answer, assertions, calculations, required investigations, readbacks). Keep them away from the agent.
- `ANCHORS.md` — public Harbor Hub anchors and the clean-room boundary per family.
- `trajectories/` — `index.json` plus one JSON file per trajectory: `reference/` (the packaged oracle replayed through MCP/REST/CLI/submit inside Harbor under Docker, graded by the packaged verifier) and `model/<run>/` (imported model runs with the durable world call trace, HubScore verdict, and token/cost receipt; `run.json` states whether the run is ranked or a disclosed partial run — qualification controls are never ranked as models).

## Synthetic-data notice

All organisations, people, patients, employees, suppliers, records, messages, and values are synthetic and clean-room authored. Nothing was copied from any upstream benchmark; see `ANCHORS.md`. This dataset is for agent evaluation and research; it is not clinical, operational, financial, or legal advice.

Page and leaderboard: {PAGE_URL} · Source: {SOURCE_URL} · Harbor: {HARBOR_URL}
"""


def _span(values: Any) -> str:
    items = sorted(values)
    return f"{items[0]}" if items[0] == items[-1] else f"{items[0]}–{items[-1]}"


def _hops(chain: dict[str, Any]) -> str:
    coverage = chain["hopCoverage"]
    return f"{min(coverage.values())}–{max(coverage.values())}/{chain['measuredTasks']}" if min(coverage.values()) != max(coverage.values()) else f"{max(coverage.values())}/{chain['measuredTasks']} on every hop"


def write_hf_trajectories(target: Path, version: str) -> dict[str, Any]:
    """Publish the committed reference and model trajectories (``reports/reference-trajectories``, ``model_runs``)."""

    reference_dir = HUBBENCH_ROOT / "reports" / "reference-trajectories"
    model_dir = HUBBENCH_ROOT / "model_runs"
    index: dict[str, Any] = {"schema_version": "hubbench.trajectory-index.v1", "version": version, "reference": [], "model_runs": []}
    for path in (sorted(reference_dir.glob("*.json")) if reference_dir.is_dir() else []):
        record = json.loads(path.read_text(encoding="utf-8"))
        _write_json(target / "reference" / path.name, record)
        index["reference"].append({"task_id": record["task_id"], "harbor_task": record["harbor_task"], "job": record["job"], "score": record["score"], "strict_pass": record["strict_pass"], "tool_calls": len(record["trace"]), "path": f"reference/{path.name}"})
    run_dirs = sorted(path for path in model_dir.iterdir() if (path / "run.json").is_file()) if model_dir.is_dir() else []
    for run_dir in run_dirs:
        run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        _write_json(target / "model" / run_dir.name / "run.json", run)
        trials = []
        for path in sorted((run_dir / "trials").glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            _write_json(target / "model" / run_dir.name / "trials" / path.name, record)
            trials.append({"task_id": record["task_id"], "score": record["score"], "strict_pass": record["strict_pass"], "tool_calls": record["tool_calls"], "cost_usd": record["cost_usd"], "path": f"model/{run_dir.name}/trials/{path.name}"})
        index["model_runs"].append({"slug": run["slug"], "label": run["label"], "harness": run["harness"], "kind": run["kind"], "ranked": run["ranked"], "dataset": run["dataset"], "harbor_tag": run["harbor_tag"], "trials_completed": run["trials_completed"], "published_tasks": run["published_tasks"], "errors": run["errors"], "mean_score": run["mean_score"], "strict_passes": run["strict_passes"], "mean_cost_usd": run["mean_cost_usd"], "note": run["note"], "trials": trials})
    _write_json(target / "index.json", index)
    runs = "\n".join(
        f"- **{run['label']}** — `{run['harness']}` — {run['kind']}: {run['trials_completed']}/{run['published_tasks']} tasks, mean HubScore {run['mean_score']}, strict passes {run['strict_passes']}, mean cost ${run['mean_cost_usd']}. {run['note']}"
        for run in index["model_runs"]
    ) or "- none imported yet"
    _write_text(
        target / "README.md",
        f"# Trajectories\n\n`index.json` lists every trajectory. **Reference** trajectories are the durable world call traces of the packaged oracle "
        f"replayed through the public surfaces (MCP over HTTP, REST, the `tool` CLI, answer submission) inside Harbor under Docker and graded by "
        f"the packaged verifier — {len(index['reference'])} published. **Model** trajectories come from imported Harbor runs of `{HARBOR_DATASET}` with the "
        f"same durable trace, the HubScore verdict, and the token/cost receipt per trial; a run is ranked only when it completed every published task "
        f"once with zero errors and zero retries, otherwise it is a disclosed partial run. Qualification controls are never ranked as models.\n\n"
        f"## Model runs\n\n{runs}\n\nEach trace lists every tool call the world recorded (tool, arguments, success, result — long results are truncated with a "
        f"character count). Traces from v1.0.0 packages include repeated argument-free `hubbench.context.get` reads caused by the compose healthcheck "
        f"polling the task endpoint; v1.1.0 packages probe the private `/health` endpoint instead.\n",
    )
    return {"reference": len(index["reference"]), "model_runs": len(index["model_runs"]), "model_trials": sum(len(run["trials"]) for run in index["model_runs"])}


def write_huggingface(output: Path, families: list[FamilyInputs], harbor: dict[str, Any], totals: dict[str, Any], version: str) -> dict[str, Any]:
    hf = output / "huggingface"
    rows_by_task = {row["family_task_id"]: row for row in harbor["tasks"]}
    records = []
    for inputs in families:
        for task in inputs.tasks:
            row = rows_by_task[task["task_id"]]
            record = public_record(inputs, task, row)
            records.append(record)
            _write_json(output / "tasks" / f"{row['task_id']}.json", record)
            _write_json(hf / "verifiers" / f"{row['task_id']}.json", {"task_id": row["task_id"], "family_task_id": task["task_id"], "metric": METRIC, "contract": inputs.contracts[task["task_id"]]})
            for asset in task["assets"]:
                _write_bytes(hf / "assets" / row["task_id"] / asset["path"], asset_bytes(asset))
    _write_jsonl(hf / "data" / "tasks.jsonl", records)
    _write_json(
        hf / "contracts" / "tools.json",
        {
            "schema_version": "hubbench.tool-contract.v1",
            "benchmark": BENCHMARK,
            "version": version,
            "families": {
                inputs.slug: {"cluster": inputs.family.cluster, "servers": inputs.family.server_contracts(), "tools": public_tool_definitions(inputs.family)}
                for inputs in families
            },
        },
    )
    _write_text(hf / "ANCHORS.md", _anchors_text(families))
    _write_text(
        hf / "LICENSE",
        f"{BENCHMARK} task data, evidence files, and contracts: Creative Commons Attribution 4.0 International (CC BY 4.0)\nhttps://creativecommons.org/licenses/by/4.0/\n\nThe HubBench engine and task-package runtime are Apache-2.0 (Copyright (c) 2026 BlobfishAI).\n",
    )
    trajectories = write_hf_trajectories(hf / "trajectories", version)
    _write_text(hf / "README.md", _hf_card(version, families, totals, harbor))
    manifest_sha256, files, size = payload_manifest(hf)
    return {"dataset": HF_DATASET, "payload_manifest_sha256": manifest_sha256, "files": files, "bytes": size, "trajectories": trajectories}


# --------------------------------------------------------------------------- #
# Aggregates, reports, README
# --------------------------------------------------------------------------- #


def aggregate_totals(families: list[FamilyInputs], harbor_rows: list[dict[str, Any]]) -> dict[str, Any]:
    qualifications = [inputs.qualification for inputs in families]
    chains = [inputs.chain for inputs in families]
    policy_names = sorted({policy for report in qualifications for policy in report["negative_controls"]})
    hop_counts = [count for chain in chains for count in chain["hopCoverage"].values()]
    return {
        "families": len(families),
        "tasks": sum(len(inputs.tasks) for inputs in families),
        "tools": sum(inputs.manifest["tool_count"] for inputs in families),
        "servers": sum(len(inputs.family.servers) + 1 for inputs in families),
        "evidence_files": sum(row["evidence_files"] for row in harbor_rows),
        "atomic_criteria": sum(row["atomic_criteria"] for row in harbor_rows),
        "graded_answer_fields": sum(row["graded_answer_fields"] for row in harbor_rows),
        "reference_tool_calls": sum(row["reference_tool_calls"] for row in harbor_rows),
        "modes": {mode: sum(1 for row in harbor_rows if row["mode"] == mode) for mode in sorted({row["mode"] for row in harbor_rows})},
        "qualification": {
            "executions": sum(report["executions"] for report in qualifications),
            "oracle_passes": sum(report["oracle"]["passes"] for report in qualifications),
            "oracle_executions": sum(report["oracle"]["executions"] for report in qualifications),
            "oracle_mean_score": round(sum(report["oracle"]["mean_score"] * report["oracle"]["executions"] for report in qualifications) / sum(report["oracle"]["executions"] for report in qualifications), 2),
            "deterministic_replays": sum(report["determinism"]["replays"] for report in qualifications),
            "exact_episode_matches": sum(report["determinism"]["exact_episode_matches"] for report in qualifications),
            "negative_control_policies": len(policy_names),
            "negative_control_policy_names": policy_names,
            "negative_control_executions": sum(control["executions"] for report in qualifications for control in report["negative_controls"].values()),
            "false_accepts": sum(report["false_accepts"] for report in qualifications),
            "mutation_omissions_total": sum(report["mutation_omissions"]["total"] for report in qualifications),
            "mutation_omissions_detected": sum(report["mutation_omissions"]["detected"] for report in qualifications),
            "qualification_passed": all(report["qualification_passed"] for report in qualifications),
        },
        "reasoning_chain": {
            "measured_tasks": sum(chain["measuredTasks"] for chain in chains),
            "passing_tasks": sum(chain["passingTasks"] for chain in chains),
            "meets_standard": all(chain["meetsStandard"] for chain in chains),
            "chain_depth_min": min(chain["chainDepth"]["min"] for chain in chains),
            "chain_depth_max": max(chain["chainDepth"]["max"] for chain in chains),
            "hop_coverage_min": min(hop_counts),
            "hop_coverage_max": max(hop_counts),
            "hop_coverage_total": {hop: sum(chain["hopCoverage"][hop] for chain in chains) for hop in sorted(chains[0]["hopCoverage"], key=lambda hop: int(hop[1:]))},
            "dependent_derivations_min": min(chain["dependentDerivations"]["min"] for chain in chains),
            "dependent_derivations_max": max(chain["dependentDerivations"]["max"] for chain in chains),
            "evidence_reads_min": min(chain["evidenceReadsBeforeDecision"]["min"] for chain in chains),
            "evidence_reads_max": max(chain["evidenceReadsBeforeDecision"]["max"] for chain in chains),
            "source_systems_min": min(chain["sourceSystemsBeforeDecision"]["min"] for chain in chains),
            "source_systems_max": max(chain["sourceSystemsBeforeDecision"]["max"] for chain in chains),
            "graded_answer_fields_min": min(chain["gradedAnswerFields"]["min"] for chain in chains),
            "graded_answer_fields_max": max(chain["gradedAnswerFields"]["max"] for chain in chains),
        },
    }


def _family_report(inputs: FamilyInputs, harbor_rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in harbor_rows if row["family"] == inputs.slug]
    q = inputs.qualification
    c = inputs.chain
    return {
        "slug": inputs.slug,
        "name": inputs.family.name,
        "cluster": inputs.family.cluster,
        "version": inputs.family.version,
        "description": inputs.family.description,
        "as_of": inputs.family.as_of,
        "task_count": len(inputs.tasks),
        "modes": inputs.manifest["modes"],
        "servers": [*sorted(inputs.family.servers), ENGINE_SERVER],
        "tool_count": inputs.manifest["tool_count"],
        "evidence_files": sum(row["evidence_files"] for row in rows),
        "atomic_criteria": sum(row["atomic_criteria"] for row in rows),
        "graded_answer_fields": sum(row["graded_answer_fields"] for row in rows),
        "reference_tool_calls": sum(row["reference_tool_calls"] for row in rows),
        "hub_anchors": inputs.anchors,
        "harbor_tasks": [{"task_id": row["task_id"], "name": row["name"], "family_task_id": row["family_task_id"], "digest": row["digest"]} for row in rows],
        "qualification": {
            "executions": q["executions"],
            "oracle_passes": q["oracle"]["passes"],
            "oracle_executions": q["oracle"]["executions"],
            "oracle_mean_score": q["oracle"]["mean_score"],
            "deterministic_replays": q["determinism"]["replays"],
            "exact_episode_matches": q["determinism"]["exact_episode_matches"],
            "negative_controls": q["negative_controls"],
            "false_accepts": q["false_accepts"],
            "mutation_omissions": {"total": q["mutation_omissions"]["total"], "detected": q["mutation_omissions"]["detected"]},
            "qualification_passed": q["qualification_passed"],
        },
        "reasoning_chain": {
            "measured_tasks": c["measuredTasks"],
            "passing_tasks": c["passingTasks"],
            "meets_standard": c["meetsStandard"],
            "chain_depth": c["chainDepth"],
            "hop_coverage": c["hopCoverage"],
            "dependent_derivations": c["dependentDerivations"],
            "evidence_reads_before_decision": c["evidenceReadsBeforeDecision"],
            "source_systems_before_decision": c["sourceSystemsBeforeDecision"],
            "graded_answer_fields": c["gradedAnswerFields"],
        },
        "inputs": {
            "release_dir": f"benchmark/hubbench/families/{inputs.slug}/release",
            "manifest_sha256": inputs.manifest_sha256,
            "fingerprint": inputs.manifest["fingerprint"],
            "qualification_report_sha256": inputs.qualification_sha256,
            "reasoning_chain_report_sha256": inputs.chain_sha256,
            "tasks": {row["family_task_id"]: {"task_sha256": row["task_sha256"], "contract_sha256": row["contract_sha256"]} for row in rows},
        },
    }


def _top_readme(version: str, families: list[FamilyInputs], totals: dict[str, Any], harbor: dict[str, Any], huggingface: dict[str, Any]) -> str:
    family_lines = "\n".join(f"- **{inputs.family.name}** (`{inputs.slug}`, cluster `{inputs.family.cluster}`): {len(inputs.tasks)} tasks, {inputs.manifest['tool_count']} tools over {len(inputs.family.servers) + 1} MCP servers" for inputs in families)
    q = totals["qualification"]
    return f"""# {BENCHMARK} {version} — distribution tree

Deterministic release emitted by `benchmark/hubbench/build_distribution.py` from the committed family releases and reports. Rebuilding it from the same inputs reproduces every byte.

{family_lines}

Totals: {totals['tasks']} tasks, {totals['tools']} tools, {totals['evidence_files']} evidence files, {totals['atomic_criteria']} atomic criteria; {q['oracle_passes']}/{totals['tasks']} oracle strict passes at mean {q['oracle_mean_score']} {METRIC}, {q['exact_episode_matches']}/{q['deterministic_replays']} byte-identical replays, {q['false_accepts']} false accepts over {q['negative_control_executions']} negative-control executions, {q['mutation_omissions_detected']}/{q['mutation_omissions_total']} mutation omissions detected.

## Layout

- `harbor/` — Harbor dataset `{HARBOR_DATASET}` v{version}: `dataset.toml`, `task-digests.json`, and {len(harbor['tasks'])} self-contained task packages under `tasks/hubbench-<family>-NNN/` (`task.toml`, `instruction.md`, `README.md`, `environment/`, `tests/`, `solution/`). Root digest `{harbor['root_sha256']}`.
- `huggingface/` — Hugging Face dataset payload (`README.md` card, `data/tasks.jsonl`, `assets/`, `contracts/`, `verifiers/`, `ANCHORS.md`, `LICENSE`, `trajectories/`). Payload manifest `{huggingface['payload_manifest_sha256']}`.
- `reports/` — `release.json` (aggregate receipt with input digests) plus verbatim copies of every family's qualification and reasoning-chain report.
- `tasks/` — one public record per task (no gold values).

## Publish (operator, from the repository root)

```bash
harbor publish benchmark/hubbench/release/harbor/tasks --public -t v{version}
harbor publish benchmark/hubbench/release/harbor --no-tasks --public -t v{version}
hf upload-large-folder {HF_DATASET} benchmark/hubbench/release/huggingface --repo-type dataset
```

## Containment

`environment/` (both container images) never carries the expected answer, the sealed verifier contract, the oracle policy, the task builder, or scenario data; `tests/` (root verifier) and `solution/` (oracle) do. The verifier reaches the finished world through a token-gated, read-only channel on the world service; the world container only holds the token's SHA-256.
"""


def _refuse_unsafe_output(output: Path) -> None:
    if output.exists() and any(output.iterdir()) and not (output / "reports" / "release.json").is_file():
        raise ValueError(f"refusing to replace a directory that is not a HubBench distribution tree: {output}")


def build_distribution(output: Path | None = None, families: list[str] | None = None, version: str = DEFAULT_VERSION) -> dict[str, Any]:
    """Build (or rebuild) the aggregate distribution tree and return ``reports/release.json``."""

    output = (output or DEFAULT_OUTPUT).resolve()
    slugs = families or discover_families()
    if not slugs:
        raise ValueError("no family has a committed release tree")
    inputs = [load_family_inputs(slug) for slug in sorted(slugs)]
    _refuse_unsafe_output(output)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    harbor = write_harbor_dataset(output, inputs, version)
    totals = aggregate_totals(inputs, harbor["tasks"])
    _write_text(output / "harbor" / "README.md", _dataset_readme(version, inputs, totals))
    harbor["root_sha256"], harbor["files"], harbor["bytes"] = tree_digest(output / "harbor")
    huggingface = write_huggingface(output, inputs, harbor, totals, version)

    for item in inputs:
        _write_text(output / "reports" / f"{item.slug}-qualification.json", (REPORTS_DIR / f"{item.slug}-qualification.json").read_text(encoding="utf-8"))
        _write_text(output / "reports" / "reasoning-chain" / f"{item.slug}.json", (REPORTS_DIR / "reasoning-chain" / f"{item.slug}.json").read_text(encoding="utf-8"))
    release = {
        "schema_version": "hubbench.distribution.v1",
        "benchmark": BENCHMARK,
        "version": version,
        "metric": METRIC,
        "page": PAGE_URL,
        "source": SOURCE_URL,
        "surfaces": list(SURFACES),
        "base_image": HARBOR_IMAGE,
        "verifier": {
            "deterministic": True,
            "llm_judge_calls": 0,
            "user": "root",
            "channel": f"token-gated read-only HTTP channel on the world service (port {PRIVATE_PORT}); the world container holds only sha256(token)",
            "reward": f"{METRIC} / 100",
        },
        "harbor": {
            "dataset": HARBOR_DATASET,
            "version": version,
            "url": HARBOR_URL,
            "task_count": len(harbor["tasks"]),
            "task_files": sum(row["files"] for row in harbor["tasks"]),
            "task_bytes": sum(row["bytes"] for row in harbor["tasks"]),
            "root_sha256": harbor["root_sha256"],
            "root_files": harbor["files"],
            "root_bytes": harbor["bytes"],
            "digest_algorithm": "harbor-0.21 publisher content hash (exact reproduction of harbor.publisher.packager.Packager.compute_content_hash)",
            "tasks": [{key: row[key] for key in ("task_id", "name", "family", "family_task_id", "mode", "digest", "files", "bytes", "verifier_token_sha256")} for row in harbor["tasks"]],
            "runtime_engine_modules": sorted({module for row in harbor["tasks"] for module in row["runtime_engine_modules"]}),
            "verifier_engine_modules": sorted({module for row in harbor["tasks"] for module in row["verifier_engine_modules"]}),
        },
        "huggingface": {
            "dataset": HF_DATASET,
            "url": HF_URL,
            "payload_manifest_sha256": huggingface["payload_manifest_sha256"],
            "files": huggingface["files"],
            "bytes": huggingface["bytes"],
        },
        "families": [_family_report(item, harbor["tasks"]) for item in inputs],
        "totals": totals,
    }
    release["harbor_root_sha256"] = harbor["root_sha256"]
    release["huggingface_manifest_sha256"] = huggingface["payload_manifest_sha256"]
    _write_json(output / "reports" / "release.json", release)
    _write_text(output / "README.md", _top_readme(version, inputs, totals, harbor, huggingface))
    rendered = json.dumps(release)
    if "/Users/" in rendered or "/home/" in rendered or "/private/" in rendered:
        raise ValueError("release report contains a machine-local path")
    return release


__all__ = [
    "BENCHMARK",
    "DEFAULT_OUTPUT",
    "DEFAULT_VERSION",
    "HARBOR_DATASET",
    "HARBOR_IMAGE",
    "HF_DATASET",
    "METRIC",
    "PRIVATE_PORT",
    "PUBLIC_TASK_KEYS",
    "SEALED_ENGINE_MODULES",
    "SEALED_TASK_KEYS",
    "WORLD_PORT",
    "build_distribution",
    "discover_families",
    "engine_closure",
    "harbor_publishable_files",
    "harbor_task_digest",
    "harbor_task_id",
    "harbor_task_name",
    "load_family_inputs",
    "payload_manifest",
    "public_record",
    "public_task",
    "runtime_engine_modules",
    "tree_digest",
    "vendor_runtime",
    "verifier_task",
    "verifier_token",
]
