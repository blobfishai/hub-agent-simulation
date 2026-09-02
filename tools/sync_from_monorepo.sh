#!/bin/bash
# Sync this public repository from a checkout (or `git archive` extraction) of the
# Blobfish monorepo: benchmark/hubbench + the reasoning-chain audit it depends on.
#   tools/sync_from_monorepo.sh <monorepo-root-or-archive-dir>
set -euo pipefail
SRC="$1"
DST="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$DST/benchmark/chain_adapters"
rsync -a --delete \
  --exclude '__pycache__' \
  --exclude '.pytest_cache' \
  --exclude '.hubbench' \
  --exclude '.venv' \
  "$SRC/benchmark/hubbench/" "$DST/benchmark/hubbench/"
for f in __init__.py core.py factorybench_100.py; do cp "$SRC/benchmark/chain_adapters/$f" "$DST/benchmark/chain_adapters/$f"; done
cp "$SRC/benchmark/realism-standard.json" "$DST/benchmark/realism-standard.json"
cp "$SRC/benchmark/reasoning_chain_audit.py" "$DST/benchmark/reasoning_chain_audit.py"
cp "$SRC/benchmark/huggingface_receipts.py" "$DST/benchmark/huggingface_receipts.py"
cp "$SRC/benchmark/hubbench/NOTICE" "$DST/NOTICE"
find "$DST" -name __pycache__ -type d -prune -exec rm -rf {} +
echo "synced $SRC -> $DST"
