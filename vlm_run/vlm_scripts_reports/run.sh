#!/usr/bin/env bash
# ./run.sh [scripts/run_s3_vlm.py options]   e.g. ./run.sh --list | ./run.sh --dry-run --limit 1 | ./run.sh
set -euo pipefail
cd "$(dirname "$0")"
unset VIRTUAL_ENV
PY=.venv/bin/python
[ -x "$PY" ] || { echo "run ./setup_instance.sh first"; exit 1; }
exec "$PY" scripts/run_s3_vlm.py "$@"
