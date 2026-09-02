"""Root pytest configuration for hub-agent-simulation: expose ``benchmark/`` for ``hubbench`` imports."""
from __future__ import annotations

import sys
from pathlib import Path

_BENCHMARK = Path(__file__).resolve().parent / "benchmark"
if str(_BENCHMARK) not in sys.path:
    sys.path.insert(0, str(_BENCHMARK))
