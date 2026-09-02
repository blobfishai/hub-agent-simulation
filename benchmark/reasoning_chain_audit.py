#!/usr/bin/env python3
"""Reasoning-chain realism audit for the Blobfish benchmark portfolio.

The structural realism standard counted words, files, criteria, and options.
This audit measures the thing that standard exists for: whether each task can
only be answered by a *dependent chain* of evidence lookups and derivations
(schedule -> materials -> specification -> shortage -> vendor lead time ->
timeline -> alternatives -> exact answer) and whether the deterministic verifier
grades every hop of that chain.  See ``realism-standard.json``
``requirements.reasoningChain`` for the hop classes H1..H13.

Every benchmark is audited through an adapter that reads its *released* task
and verifier artifacts.  Adapters live in ``benchmark/chain_adapters/`` (one
module per benchmark release, discovered automatically).  Detection is
structural where the release exposes the chain as data (decision models,
sealed verifier contracts, graded answer fields) and conservative everywhere
else: a hop that cannot be shown from released artifacts counts as absent.
Benchmarks without an adapter, or whose release tree is not checked out, are
reported as ``not-measured`` rather than silently passing.

Usage::

    python3 benchmark/reasoning_chain_audit.py            # print summary
    python3 benchmark/reasoning_chain_audit.py --write    # refresh reports
    python3 benchmark/reasoning_chain_audit.py \
        --release counselbench-100=/path/to/exact/release \
        --release salesbench-100=/path/to/exact/release

Per-benchmark reports land in ``benchmark/reports/reasoning-chain/<slug>.json``
and the aggregate in ``benchmark/reports/reasoning-chain-audit.json``.  Reports
carry no timestamps or machine paths so they stay diff-stable.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from chain_adapters import adapter_for  # noqa: E402
from chain_adapters.core import (  # noqa: E402
    AGGREGATE_PATH,
    CATALOG_PATH,
    HOP_IDS,
    REPORT_DIR,
    SCHEMA_VERSION,
    STANDARD_PATH,
    not_measured,
    read_json,
    write_json,
)

NO_ADAPTER_REASON = "no reasoning-chain adapter for this release yet; add a module under benchmark/chain_adapters/"


def parse_release(value: str) -> tuple[str, Path]:
    """Parse ``slug=release-directory`` without embedding machine paths in reports."""

    slug, separator, raw_path = value.partition("=")
    if not separator or not slug.strip() or not raw_path.strip():
        raise argparse.ArgumentTypeError("expected slug=release-directory")
    return slug.strip(), Path(raw_path).expanduser().resolve()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def release_binding(release: Path, report: dict[str, Any]) -> dict[str, Any]:
    """Bind an override to stable release evidence without leaking its path."""

    candidates = (
        "reports/build.json",
        "reports/qualification.json",
        "release-manifest.json",
        "reports/release-manifest.json",
        "realism.json",
    )
    files = {
        relative: sha256_file(release / relative)
        for relative in candidates
        if (release / relative).is_file()
    }
    if not files:
        raise ValueError(
            f"{report['slug']}: explicit release override has no bindable release evidence"
        )
    return {"version": report.get("version"), "files": files}


def audit_all(
    source_root: Path,
    release_overrides: dict[str, Path] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return ``(aggregate report, per-benchmark detail reports)``."""
    catalog = read_json(CATALOG_PATH)
    standard = read_json(STANDARD_PATH)
    overrides = release_overrides or {}
    catalog_slugs = {str(entry["slug"]) for entry in catalog["benchmarks"]}
    unknown = sorted(set(overrides) - catalog_slugs)
    if unknown:
        raise ValueError(f"release overrides name unknown benchmarks: {unknown}")
    chain = standard["requirements"]["reasoningChain"]
    details: list[dict[str, Any]] = []
    for entry in catalog["benchmarks"]:
        adapter = adapter_for(entry)
        if adapter is None:
            details.append(not_measured(entry, NO_ADAPTER_REASON))
        else:
            slug = str(entry["slug"])
            override = overrides.get(slug)
            detail = adapter(source_root, entry, override)
            if override is not None:
                if detail["status"] != "measured":
                    raise ValueError(
                        f"{slug}: explicit release override is not measurable: "
                        f"{detail['reason']}"
                    )
                detail["releaseBinding"] = release_binding(override, detail)
            details.append(detail)
    measured = [r for r in details if r["status"] == "measured"]
    aggregate = {
        "schemaVersion": SCHEMA_VERSION,
        "standard": {
            "path": "benchmark/realism-standard.json",
            "schemaVersion": standard["schemaVersion"],
            "mandatoryHopClasses": chain["mandatoryHopClasses"],
            "minimumChainDepth": chain["minimumChainDepth"],
        },
        "hopClasses": chain["hopClasses"],
        "summary": {
            "benchmarks": len(details),
            "measuredBenchmarks": len(measured),
            "benchmarksMeetingStandard": [r["slug"] for r in measured if r["meetsStandard"]],
            "benchmarksBelowStandard": [r["slug"] for r in measured if not r["meetsStandard"]],
            "benchmarksNotMeasured": [r["slug"] for r in details if r["status"] != "measured"],
            "measuredTasks": sum(r["measuredTasks"] for r in measured),
            "passingTasks": sum(r["passingTasks"] for r in measured),
        },
        "benchmarks": [{k: v for k, v in r.items() if k != "taskMeasures"} for r in details],
        "detailReports": {r["slug"]: f"benchmark/reports/reasoning-chain/{r['slug']}.json" for r in measured},
    }
    return aggregate, details


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source-root", default=str(Path.home() / "dev"), help="directory holding the sibling benchmark source repositories")
    parser.add_argument(
        "--release",
        action="append",
        default=[],
        type=parse_release,
        metavar="SLUG=PATH",
        help="bind one benchmark to an exact release export instead of its sibling dist tree",
    )
    parser.add_argument("--write", action="store_true", help="write the per-benchmark and aggregate reports")
    parser.add_argument("--fail-below-standard", action="store_true", help="exit 1 if any measured benchmark is below the standard")
    args = parser.parse_args()
    source_root = Path(args.source_root).expanduser().resolve()
    release_overrides: dict[str, Path] = {}
    for slug, path in args.release:
        if slug in release_overrides:
            parser.error(f"duplicate release override for {slug}")
        if not path.is_dir():
            parser.error(f"release override is not a directory: {slug}={path}")
        release_overrides[slug] = path
    try:
        aggregate, details = audit_all(source_root, release_overrides)
    except ValueError as error:
        parser.error(str(error))
    if args.write:
        for detail in details:
            if detail["status"] == "measured":
                write_json(REPORT_DIR / f"{detail['slug']}.json", detail)
        write_json(AGGREGATE_PATH, aggregate)
    for report in aggregate["benchmarks"]:
        if report["status"] != "measured":
            print(f"{report['slug']:20s} not measured: {report['reason']}")
            continue
        depth = report["chainDepth"]
        print(
            f"{report['slug']:20s} {report['passingTasks']:3d}/{report['measuredTasks']:<3d} pass  depth {depth['min']}-{depth['max']}  "
            f"hops " + " ".join(f"{hop}={report['hopCoverage'][hop]}" for hop in HOP_IDS)
        )
        if report["failureReasons"]:
            print(f"{'':20s} failure reasons: {report['failureReasons']}")
    summary = aggregate["summary"]
    print(
        f"measured {summary['measuredTasks']} tasks across {summary['measuredBenchmarks']} benchmarks; "
        f"{summary['passingTasks']} pass; meeting standard: {summary['benchmarksMeetingStandard']}; "
        f"below: {summary['benchmarksBelowStandard']}; not measured: {summary['benchmarksNotMeasured']}"
    )
    if args.fail_below_standard and summary["benchmarksBelowStandard"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
