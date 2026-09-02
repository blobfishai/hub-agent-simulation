#!/usr/bin/env python3
"""Build (or rebuild) a HubBench family release tree.

    python3 benchmark/hubbench/build_release.py --family clinicops
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hubbench.engine.families import load_family  # noqa: E402
from hubbench.engine.release import build_release  # noqa: E402
from hubbench.engine.tasks import release_dir  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", default="clinicops")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    family = load_family(args.family)
    manifest = build_release(family, args.output)
    target = args.output or release_dir(family)
    print(f"{family.slug} v{manifest['version']}: {manifest['task_count']} tasks, {manifest['tool_count']} tools -> {target}")
    for entry in manifest["tasks"]:
        print(f"  {entry['task_id']}  {entry['mode']:8s}  {entry['asset_count']:2d} files  {entry['atomic_criteria']:2d} criteria  {entry['graded_answer_fields']:2d} answer fields  {entry['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
