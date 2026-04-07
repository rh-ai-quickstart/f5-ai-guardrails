#!/bin/bash

cd "$(dirname "$0")"

set -euo pipefail

# Ensure project dependencies and the local venv exist.
uv sync

PYTHON_BIN=".venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    echo "[ERROR] Expected Python interpreter not found: $PYTHON_BIN"
    exit 1
fi

echo "[INFO] Using Python interpreter: $("$PYTHON_BIN" -c 'import sys; print(sys.executable)')"
echo "[INFO] Python version: $("$PYTHON_BIN" --version)"

"$PYTHON_BIN" -m streamlit run llama_stack_ui/distribution/ui/app.py --server.port=8501
