"""Reasoning-chain audit adapters, one module per benchmark release.

An adapter module exposes:

* ``SLUG`` — the ``benchmark/catalog.json`` slug it measures, or ``None`` for a
  generic adapter that instead defines ``matches(entry) -> bool``;
* ``audit(source_root, entry, release_override=None) -> report`` — reads the
  benchmark's released task and verifier artifacts and returns either
  :func:`core.summarize` output or :func:`core.not_measured` with a precise
  reason. The optional override binds an audit to an immutable external export
  instead of a potentially stale sibling ``dist/`` tree.

Modules are discovered automatically: every public module in this package is
imported and registered, slug adapters take precedence over generic ones, and
generic adapters are tried in module-name order.  Adding a benchmark means
adding one module here; the audit script never needs to change.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any, Callable

from . import core

Adapter = Callable[[Path, dict[str, Any], Path | None], dict[str, Any]]


def discover() -> tuple[dict[str, Adapter], list[tuple[str, Callable[[dict[str, Any]], bool], Adapter]]]:
    """Return ``(slug adapters, generic adapters)`` from every public module."""
    by_slug: dict[str, Adapter] = {}
    generic: list[tuple[str, Callable[[dict[str, Any]], bool], Adapter]] = []
    for module_info in sorted(pkgutil.iter_modules(__path__), key=lambda info: info.name):
        name = module_info.name
        if name.startswith("_") or name == "core":
            continue
        module = importlib.import_module(f"{__name__}.{name}")
        audit = getattr(module, "audit", None)
        if audit is None:
            continue
        slug = getattr(module, "SLUG", None)
        if slug:
            if slug in by_slug:
                raise RuntimeError(f"two chain adapters claim slug {slug!r}")
            by_slug[slug] = audit
        elif hasattr(module, "matches"):
            generic.append((name, module.matches, audit))
    return by_slug, generic


def adapter_for(entry: dict[str, Any]) -> Adapter | None:
    by_slug, generic = discover()
    if entry["slug"] in by_slug:
        return by_slug[entry["slug"]]
    for _, matches, audit in generic:
        if matches(entry):
            return audit
    return None


__all__ = ["Adapter", "adapter_for", "core", "discover"]
