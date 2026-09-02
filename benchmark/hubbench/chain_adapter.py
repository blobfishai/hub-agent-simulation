#!/usr/bin/env python3
"""Measure a HubBench family release against the reasoning-chain standard.

HubBench emits tasks and sealed verifier contracts in the same data shape as
FactoryBench releases, and its plan / quantity / schedule decision modes carry
the exact calculation ids the portfolio audit keys on, so the measurement is
the portfolio audit's own ``measure_factorybench_task``
(``benchmark/chain_adapters/factorybench_100.py``) — imported, never
re-implemented and never relaxed.

    python3 benchmark/hubbench/chain_adapter.py --family clinicops --write

Writes ``benchmark/hubbench/reports/reasoning-chain/<family>.json`` in the same
shape as ``benchmark/reports/reasoning-chain/factorybench-100.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HUBBENCH_ROOT = Path(__file__).resolve().parent
BENCHMARK_ROOT = HUBBENCH_ROOT.parent
sys.path.insert(0, str(BENCHMARK_ROOT))

from chain_adapters.core import HOP_IDS, summarize  # noqa: E402  (benchmark/chain_adapters)
from chain_adapters.factorybench_100 import FACTORY_MODE_CHAINS, measure_factorybench_task  # noqa: E402
from hubbench.engine.families import load_family  # noqa: E402
from hubbench.engine.tasks import load_release_contract, load_release_tasks, release_dir  # noqa: E402

REPORT_DIR = HUBBENCH_ROOT / "reports" / "reasoning-chain"

# HubBench mode chains: the graded calculation ids that realise hops H2..H6 for
# each decision mode.  These are deliberately identical to the FactoryBench
# chains for the shared modes so the unmodified portfolio audit measures a
# HubBench release directly; a future family adding a new mode must extend this
# table AND the portfolio audit together.
HUBBENCH_MODE_CHAINS: dict[str, dict[str, set[str]]] = {mode: FACTORY_MODE_CHAINS[mode] for mode in ("plan", "quantity", "schedule")}


def measure_family(family_slug: str) -> dict:
    family = load_family(family_slug)
    directory = release_dir(family)
    tasks = load_release_tasks(family, directory)
    if not tasks:
        raise SystemExit(f"no released tasks under {directory}; run build_release.py first")
    measures = []
    for task in tasks:
        mode = task["decision_model"].get("mode")
        chain = HUBBENCH_MODE_CHAINS.get(mode)
        if chain is None:
            raise SystemExit(f"{task['task_id']}: mode {mode!r} has no HubBench mode chain; the audit cannot measure it")
        calc_ids = {calc["id"] for calc in task["decision_model"]["calculations"]}
        for hop, required in chain.items():
            missing = sorted(required - calc_ids)
            if missing:
                raise SystemExit(f"{task['task_id']}: mode {mode} is missing graded chain calculations for {hop}: {missing}")
        contract = load_release_contract(family, task["task_id"], directory)
        measures.append(measure_factorybench_task(task, contract))
    entry = {"slug": family.slug, "name": f"HubBench {family.name}", "source": {"tasks": len(tasks)}}
    return summarize(
        entry,
        measures,
        adapter="hubbench-structural (chain_adapters.factorybench_100.measure_factorybench_task)",
        version=family.version,
        source=f"benchmark/hubbench/families/{family.slug}/release tasks + verifiers/contracts",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--family", default="clinicops")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = measure_family(args.family)
    if args.write:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        target = REPORT_DIR / f"{args.family}.json"
        target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {target.relative_to(BENCHMARK_ROOT.parent)}")
    depth = report["chainDepth"]
    print(
        f"{report['slug']:12s} {report['passingTasks']}/{report['measuredTasks']} pass  depth {depth['min']}-{depth['max']}  "
        + " ".join(f"{hop}={report['hopCoverage'][hop]}" for hop in HOP_IDS)
    )
    if report["failureReasons"]:
        print(f"failure reasons: {report['failureReasons']}")
        for failure in report["failures"]:
            print(f"  {failure['taskId']}: {failure['missing']}")
    return 0 if report["meetsStandard"] else 1


if __name__ == "__main__":
    sys.exit(main())
