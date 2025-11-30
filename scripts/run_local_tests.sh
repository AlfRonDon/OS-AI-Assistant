#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -f ".venv/bin/activate" ]; then
  # shellcheck source=/dev/null
  source ".venv/bin/activate"
elif [ -f ".venv/Scripts/activate" ]; then
  # shellcheck source=/dev/null
  source ".venv/Scripts/activate"
fi

mkdir -p reports/tests

python -m pip install --upgrade pip
python -m pip install pytest jsonschema psutil

pytest tests -q --junitxml reports/tests/junit.xml | tee reports/tests/pytest_output.txt
