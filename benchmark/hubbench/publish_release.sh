#!/bin/bash
# Publish a HubBench release end to end, fail-closed, from a frozen copy under $HOME.
#
#   benchmark/hubbench/publish_release.sh <version> [--from-step N] [--to-step N] [--roundtrip-tasks "a b"]
#
# Steps (artifacts under ~/.cache/hubbench/v<version>/ and ~/.cache/hubbench/jobs/):
#   1  freeze   copy the committed release tree (must be clean and rebuilt: build_distribution.py)
#   2  gate     harbor run -p <frozen>/harbor/tasks -a oracle  → every trial must score reward 1.0
#   3  tasks    harbor publish <frozen>/harbor/tasks/* --public -t v<version>
#   4  dataset  printf y | harbor publish <frozen>/harbor --public --no-tasks -t v<version>   (prompts!)
#   5  roundtrip harbor run -d blobfishai/hubbench@v<version> -a oracle -i <one task per family>
#   6  hf       hf upload-large-folder SamuelChien821/hubbench <frozen>/huggingface --repo-type dataset
#   7  receipt  publication_receipt.py (verifies the HF payload byte-for-byte; refuses on any gap)
#   8  site     harbor_hub_coverage.py --write · build_hubbench_site_data.py · site_data.py
#
# Docker (Colima) is required for steps 2 and 5. Never run this from /private/tmp (Colima
# only bind-mounts $HOME). Publishing is outward-facing: run it only for a release the
# operator has decided to ship.
set -euo pipefail

VERSION="${1:?usage: publish_release.sh <version> [--from-step N] [--to-step N] [--roundtrip-tasks \"a b\"]}"
shift
FROM_STEP=1
TO_STEP=8
ROUNDTRIP_TASKS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --from-step) FROM_STEP="$2"; shift 2 ;;
    --to-step) TO_STEP="$2"; shift 2 ;;
    --roundtrip-tasks) ROUNDTRIP_TASKS="$2"; shift 2 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done

case "$FROM_STEP:$TO_STEP" in
  *[!0-9:]*|:*|*:) echo "steps must be integers from 1 through 8" >&2; exit 2 ;;
esac
[ "$FROM_STEP" -ge 1 ] && [ "$TO_STEP" -le 8 ] && [ "$FROM_STEP" -le "$TO_STEP" ] || {
  echo "require 1 <= --from-step <= --to-step <= 8" >&2
  exit 2
}

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
HUBBENCH="$REPO/benchmark/hubbench"
HARBOR="${HARBOR_BIN:-$HOME/.local/bin/harbor}"
CACHE="$HOME/.cache/hubbench"
FROZEN="$CACHE/v$VERSION"
JOBS="$CACHE/jobs"
DATASET="blobfishai/hubbench"
HF_DATASET="SamuelChien821/hubbench"
SOURCE_REPO="${HUBBENCH_SOURCE_REPO:-$HOME/dev/hub-agent-simulation}"
GATE_JOB="hubbench-oracle-v$VERSION-full"
ROUNDTRIP_JOB="hubbench-oracle-registry-roundtrip-v$VERSION"
LOG="$JOBS/publish-v$VERSION.log"
GATE_CONCURRENCY="${HUBBENCH_GATE_CONCURRENCY:-2}"
case "$GATE_CONCURRENCY" in
  ''|*[!0-9]*) echo "HUBBENCH_GATE_CONCURRENCY must be a positive integer" >&2; exit 2 ;;
esac
[ "$GATE_CONCURRENCY" -ge 1 ] || { echo "HUBBENCH_GATE_CONCURRENCY must be at least 1" >&2; exit 2; }
PUBLISH_CONCURRENCY="${HUBBENCH_PUBLISH_CONCURRENCY:-8}"
case "$PUBLISH_CONCURRENCY" in
  ''|*[!0-9]*) echo "HUBBENCH_PUBLISH_CONCURRENCY must be a positive integer" >&2; exit 2 ;;
esac
[ "$PUBLISH_CONCURRENCY" -ge 1 ] || { echo "HUBBENCH_PUBLISH_CONCURRENCY must be at least 1" >&2; exit 2; }
mkdir -p "$JOBS"
exec > >(tee -a "$LOG") 2>&1
echo "== HubBench publish v$VERSION steps $FROM_STEP..$TO_STEP ($(date -u +%FT%TZ)) =="

step() { [ "$FROM_STEP" -le "$1" ] && [ "$1" -le "$TO_STEP" ]; }

if step 1; then
  echo "-- 1 freeze"
  cd "$REPO"
  [ -z "$(git status --porcelain benchmark/hubbench)" ] || { echo "benchmark/hubbench is dirty; commit the rebuilt release first" >&2; exit 1; }
  built_version="$(python3 -c "import tomllib;print(tomllib.load(open('$HUBBENCH/release/harbor/dataset.toml','rb'))['dataset']['version'])")"
  [ "$built_version" = "$VERSION" ] || { echo "committed release is v$built_version, not v$VERSION (set DEFAULT_VERSION / rebuild)" >&2; exit 1; }
  mkdir -p "$FROZEN"
  rsync -a --delete "$HUBBENCH/release/harbor/" "$FROZEN/harbor/"
  rsync -a --delete "$HUBBENCH/release/huggingface/" "$FROZEN/huggingface/"
  rsync -a --delete "$HUBBENCH/release/reports/" "$FROZEN/reports/"
  echo "frozen $(ls "$FROZEN/harbor/tasks" | wc -l | tr -d ' ') packages at $FROZEN"
fi

if step 2; then
  echo "-- 2 docker oracle gate ($GATE_JOB)"
  rm -rf "$JOBS/$GATE_JOB"
  (cd "$CACHE" && "$HARBOR" run -p "$FROZEN/harbor/tasks" -a oracle -o "$JOBS" --job-name "$GATE_JOB" -n "$GATE_CONCURRENCY" -k 1 -r 0)
  total="$(ls "$FROZEN/harbor/tasks" | wc -l | tr -d ' ')"
  ones="$(find "$JOBS/$GATE_JOB" -name reward.txt -exec cat {} \; | grep -c '^1\.000000$' || true)"
  [ "$ones" = "$total" ] || { echo "gate: $ones/$total trials at reward 1.0 — refusing to publish" >&2; exit 1; }
  echo "gate: $ones/$total at reward 1.0"
fi

if step 3; then
  echo "-- 3 publish tasks (concurrency $PUBLISH_CONCURRENCY)"
  (cd "$FROZEN/harbor" && "$HARBOR" publish tasks/* --public -t "v$VERSION" -c "$PUBLISH_CONCURRENCY")
fi

if step 4; then
  echo "-- 4 publish dataset"
  # Send one confirmation. An unbounded `yes` receives SIGPIPE when Harbor exits;
  # under `set -o pipefail` that incorrectly turns a successful publish into 141.
  (cd "$FROZEN/harbor" && printf 'y\n' | "$HARBOR" publish . --public --no-tasks -t "v$VERSION" | tee "$JOBS/publish-dataset-v$VERSION.log")
  grep -o "$DATASET *│ *[0-9a-f]\{12\}" "$JOBS/publish-dataset-v$VERSION.log" | grep -o "[0-9a-f]\{12\}$" > "$FROZEN/dataset-digest-prefix.txt" || true
  echo "dataset digest prefix: $(cat "$FROZEN/dataset-digest-prefix.txt" 2>/dev/null || echo unknown)"
  curl -s -o /dev/null -w "hub page %{http_code}\n" "https://hub.harborframework.com/datasets/$DATASET/latest"
fi

if step 5; then
  echo "-- 5 registry round-trip ($ROUNDTRIP_JOB)"
  if [ -z "$ROUNDTRIP_TASKS" ]; then
    ROUNDTRIP_TASKS="$(ls "$FROZEN/harbor/tasks" | sed 's/-[0-9]*$//' | sort -u | while read -r fam; do ls "$FROZEN/harbor/tasks" | grep "^$fam-" | sort | sed -n 2p; done | tr '\n' ' ')"
  fi
  includes=""; for t in $ROUNDTRIP_TASKS; do includes="$includes -i blobfishai/$t"; done
  rm -rf "$JOBS/$ROUNDTRIP_JOB"; mkdir -p "$CACHE/registry-test"
  # shellcheck disable=SC2086
  (cd "$CACHE/registry-test" && "$HARBOR" run -d "$DATASET@v$VERSION" -a oracle $includes -o "$JOBS" --job-name "$ROUNDTRIP_JOB" -n 2 -k 1 -r 0)
  bad="$(find "$JOBS/$ROUNDTRIP_JOB" -name reward.txt -exec cat {} \; | grep -vc '^1\.000000$' || true)"
  [ "$bad" = "0" ] || { echo "round-trip: $bad trials below 1.0" >&2; exit 1; }
  echo "round-trip: all trials at reward 1.0"
fi

if step 6; then
  echo "-- 6 hugging face"
  (cd "$HOME" && hf upload-large-folder "$HF_DATASET" "$FROZEN/huggingface" --repo-type dataset)
  curl -s "https://huggingface.co/api/datasets/$HF_DATASET?blobs=true" -o "$FROZEN/hf-api.json"
  python3 -c "import json;d=json.load(open('$FROZEN/hf-api.json'));print('HF', d['id'], d['sha'], len(d['siblings']), 'files')"
fi

if step 7; then
  echo "-- 7 publication receipt"
  prefix="$(cat "$FROZEN/dataset-digest-prefix.txt" 2>/dev/null || echo unknown)"
  python3 "$HUBBENCH/publication_receipt.py" --frozen "$FROZEN/harbor" --gate-job "$JOBS/$GATE_JOB" \
    --roundtrip-job "$JOBS/$ROUNDTRIP_JOB" --hf-api-json "$FROZEN/hf-api.json" --hf-payload "$FROZEN/huggingface" \
    --source-repo "$SOURCE_REPO" --dataset-digest-prefix "$prefix" --published-at "$(date +%F)"
fi

if step 8; then
  echo "-- 8 site data"
  cd "$REPO"
  python3 benchmark/harbor_hub_coverage.py --write | tail -1
  python3 benchmark/build_hubbench_site_data.py | tail -1
  python3 benchmark/hubbench/site_data.py | tail -1
  echo "now: pytest benchmark/hubbench, commit reports/publication.json + page data, PR, deploy"
fi
echo "== done ($(date -u +%FT%TZ)) =="
