"""The committed release must pass the portfolio reasoning-chain audit, 8/8."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HUBBENCH_ROOT = Path(__file__).resolve().parents[1]


def _load_chain_adapter():
    spec = importlib.util.spec_from_file_location("hubbench_chain_adapter", HUBBENCH_ROOT / "chain_adapter.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_chain_audit_passes_all_tasks_and_report_is_current():
    adapter = _load_chain_adapter()
    report = adapter.measure_family("clinicops")
    assert report["measuredTasks"] == 8
    assert report["passingTasks"] == 8, report["failures"]
    assert report["meetsStandard"] is True
    assert report["chainDepth"] == {"min": 8, "max": 8}
    for hop in (f"H{i}" for i in range(1, 14)):
        assert report["hopCoverage"][hop] == 8, hop
    committed = json.loads((HUBBENCH_ROOT / "reports" / "reasoning-chain" / "clinicops.json").read_text(encoding="utf-8"))
    assert committed == report, "committed chain report is stale; rerun chain_adapter.py --write"


def test_hubbench_mode_chains_match_portfolio_audit():
    adapter = _load_chain_adapter()
    from chain_adapters.factorybench_100 import FACTORY_MODE_CHAINS

    for mode, chain in adapter.HUBBENCH_MODE_CHAINS.items():
        assert chain == FACTORY_MODE_CHAINS[mode], mode
