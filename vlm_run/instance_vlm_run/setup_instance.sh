#!/usr/bin/env bash
# One-time setup on a laptop or EC2 instance: own venv in this folder, requirements, .env from the example.
# Needs the whole vlm_run/ folder (run_vlm_repetitions.py, configs/, final_prompts/) next to this one.
set -euo pipefail
cd "$(dirname "$0")"
unset VIRTUAL_ENV
PY="${PYTHON:-python3}"
"$PY" -c 'import sys; assert sys.version_info >= (3, 9), "Python >= 3.9 needed"'
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
[ -f .env ] || cp .env.example .env
.venv/bin/python -c 'import boto3, av, cv2; print("deps ok: boto3", boto3.__version__, "av", av.__version__, "cv2", cv2.__version__)'
echo "next: edit .env (keys, AWS_PROFILE), then ./run.sh --list"
