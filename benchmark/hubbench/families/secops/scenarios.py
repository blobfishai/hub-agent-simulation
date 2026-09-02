"""All SecOps scenarios, in release order."""

from __future__ import annotations

from functools import lru_cache

from .scenarios_a import SCENARIOS_A
from .scenarios_b import SCENARIOS_B
from .specs import Scenario


@lru_cache(maxsize=None)
def scenarios() -> tuple[Scenario, ...]:
    built = tuple(factory() for factory in (*SCENARIOS_A, *SCENARIOS_B))
    ordinals = [scenario.ordinal for scenario in built]
    if ordinals != list(range(1, len(built) + 1)):
        raise ValueError(f"scenario ordinals must be 1..n, got {ordinals}")
    return built


__all__ = ["scenarios"]
