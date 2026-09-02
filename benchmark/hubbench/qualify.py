#!/usr/bin/env python3
"""Qualify a HubBench family: oracle 100 %, deterministic replay, negative controls.

    python3 benchmark/hubbench/qualify.py --family clinicops --write

Writes ``benchmark/hubbench/reports/<family>-qualification.json`` (sorted keys,
no timestamps, no machine paths) when ``--write`` is passed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hubbench.engine.evaluation import qualify  # noqa: E402
from hubbench.engine.families import load_family  # noqa: E402
from hubbench.engine.tasks import load_release_tasks, release_dir  # noqa: E402

REPORTS = Path(__file__).resolve().parent / "reports"


def qualification_report(family_slug: str, *, from_release: bool = True) -> dict:
    family = load_family(family_slug)
    if from_release and (release_dir(family) / "tasks").is_dir():
        tasks = load_release_tasks(family)
    else:
        tasks = family.build_tasks()
    return qualify(family, tasks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", default="clinicops")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--fresh", action="store_true", help="qualify a fresh build instead of the committed release")
    args = parser.parse_args()
    report = qualification_report(args.family, from_release=not args.fresh)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.write:
        target = REPORTS / f"{args.family}-qualification.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered + "\n", encoding="utf-8")
        print(f"wrote {target.relative_to(Path(__file__).resolve().parents[2])}")
    oracle = report["oracle"]
    controls = report["negative_controls"]
    print(
        f"{args.family}: oracle {oracle['passes']}/{oracle['executions']} strict at {oracle['mean_score']}; "
        f"deterministic={report['determinism']['deterministic']}; false accepts={report['false_accepts']}; "
        f"mutation omissions detected {report['mutation_omissions']['detected']}/{report['mutation_omissions']['total']}; "
        f"qualification_passed={report['qualification_passed']}"
    )
    for policy, control in sorted(controls.items()):
        print(f"  {policy:20s} mean {control['mean_score']:6.2f}  false accepts {control['false_accepts']}")
    return 0 if report["qualification_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
