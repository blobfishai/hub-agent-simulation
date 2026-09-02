#!/usr/bin/env python3
"""Build (or rebuild) the aggregate HubBench distribution tree.

    python3 benchmark/hubbench/build_distribution.py --output benchmark/hubbench/release
    python3 benchmark/hubbench/build_distribution.py --output /tmp/hubbench-release --family clinicops --version 1.1.0

Emits the Harbor dataset (``harbor/``), the Hugging Face payload
(``huggingface/``), public task records (``tasks/``), and ``reports/release.json``
from every family with a committed ``families/<slug>/release/`` tree.  The tree
is byte-stable: rebuilding from the same inputs reproduces it exactly.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hubbench.engine.distribution import DEFAULT_OUTPUT, DEFAULT_VERSION, build_distribution  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--family", action="append", default=None, help="family slug (repeatable); default: every family with a committed release")
    parser.add_argument("--version", default=DEFAULT_VERSION)
    args = parser.parse_args()
    release = build_distribution(args.output, args.family, args.version)
    harbor = release["harbor"]
    totals = release["totals"]
    print(
        f"{release['benchmark']} {release['version']}: {totals['families']} families, {totals['tasks']} tasks, "
        f"{totals['tools']} tools -> {args.output}"
    )
    print(f"  harbor {harbor['dataset']}: {harbor['task_count']} packages, {harbor['root_files']} files, {harbor['root_bytes']} bytes, root sha256 {harbor['root_sha256']}")
    print(f"  huggingface {release['huggingface']['dataset']}: {release['huggingface']['files']} files, {release['huggingface']['bytes']} bytes, manifest {release['huggingface']['payload_manifest_sha256']}")
    for row in harbor["tasks"]:
        print(f"  {row['task_id']}  {row['mode']:8s}  {row['files']:3d} files  {row['bytes']:8d} bytes  {row['digest']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
