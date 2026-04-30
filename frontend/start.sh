#!/bin/bash

cd "$(dirname "$0")"

set -euo pipefail

# Namespace for oc route discovery (RAG / LlamaStack). Same as deploy: make install NAMESPACE=...
_NS="${NAMESPACE:-${RAG_NAMESPACE:-f5-ai-security}}"

# LlamaStack endpoint for models, vector DBs, and tool groups.
# Override with: LLAMA_STACK_ENDPOINT=http://your-url ./start.sh
if [ -z "${LLAMA_STACK_ENDPOINT:-}" ]; then
    # Auto-detect from OpenShift route if oc is available and logged in
    if command -v oc &>/dev/null && oc whoami &>/dev/null 2>&1; then
        ROUTE_HOST=$(oc get route llamastack-http -n "$_NS" -o jsonpath='{.spec.host}' 2>/dev/null || true)
        if [ -n "$ROUTE_HOST" ]; then
            # Edge routes with TLS: use https:// so the router returns JSON from LlamaStack, not HTML/redirects.
            TLS=$(oc get route llamastack-http -n "$_NS" -o jsonpath='{.spec.tls.termination}' 2>/dev/null || true)
            if [ -n "$TLS" ] && [ "$TLS" != "null" ]; then
                export LLAMA_STACK_ENDPOINT="https://$ROUTE_HOST"
            else
                export LLAMA_STACK_ENDPOINT="http://$ROUTE_HOST"
            fi
        fi
    fi
fi
export LLAMA_STACK_ENDPOINT="${LLAMA_STACK_ENDPOINT:-http://llamastack:8321}"
echo "[INFO] LlamaStack endpoint: $LLAMA_STACK_ENDPOINT"

# Optional API token for LlamaStack (used by the dual-panel comparison view)
export LLAMA_STACK_API_TOKEN="${LLAMA_STACK_API_TOKEN:-}"

# Ensure project dependencies and the local venv exist.
uv sync

PYTHON_BIN=".venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    echo "[ERROR] Expected Python interpreter not found: $PYTHON_BIN"
    exit 1
fi

echo "[INFO] Using Python interpreter: $("$PYTHON_BIN" -c 'import sys; print(sys.executable)')"
echo "[INFO] Python version: $("$PYTHON_BIN" --version)"

# STREAMLIT_RUN_ON_SAVE=1: reload the app when you save a file (local dev)
STREAMLIT_EXTRA=(--server.port=8501)
if [ "${STREAMLIT_RUN_ON_SAVE:-0}" = "1" ]; then
  STREAMLIT_EXTRA+=(--server.runOnSave true)
  echo "[INFO] Streamlit will reload on file save (STREAMLIT_RUN_ON_SAVE=1)"
fi

exec "$PYTHON_BIN" -m streamlit run llama_stack_ui/distribution/ui/app.py "${STREAMLIT_EXTRA[@]}"
