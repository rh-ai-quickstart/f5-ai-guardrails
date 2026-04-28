#!/usr/bin/env bash
# Run the Streamlit UI on your machine while LlamaStack (and the rest of the RAG stack) stay on the cluster.
#
# Prerequisites: oc logged in; uv; cluster has route llamastack-http in the RAG namespace.
#
# Examples:
#   NAMESPACE=my-rag-ns ./dev-on-cluster.sh
#   PORT_FORWARD=1 NAMESPACE=my-rag-ns ./dev-on-cluster.sh   # if you prefer localhost tunnel
#
# F5 guardrails: open http://localhost:8501 → Settings → set Moderator URL + API token (see README).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

NAMESPACE="${NAMESPACE:-${RAG_NAMESPACE:-f5-ai-security}}"
export NAMESPACE
export RAG_NAMESPACE="$NAMESPACE"

MODERATOR_NAMESPACE="${MODERATOR_NAMESPACE:-cai-moderator}"
LLAMA_STACK_SVC="${LLAMA_STACK_SVC:-llamastack}"
LLAMA_STACK_PORT="${LLAMA_STACK_PORT:-8321}"
PF_PORT="${PORT_FORWARD_LOCAL_PORT:-8321}"

if ! command -v oc &>/dev/null; then
  echo "[WARN] oc not found: set LLAMA_STACK_ENDPOINT yourself or install OpenShift CLI."
else
  if ! oc whoami &>/dev/null; then
    echo "[ERROR] Not logged in: oc login ..." >&2
    exit 1
  fi
fi

if [ "${PORT_FORWARD:-0}" = "1" ]; then
  echo "[INFO] Port-forward: svc/${LLAMA_STACK_SVC} (${NAMESPACE}) -> 127.0.0.1:${PF_PORT}"
  oc port-forward -n "$NAMESPACE" "svc/${LLAMA_STACK_SVC}" "${PF_PORT}:${LLAMA_STACK_PORT}" &
  PF_PID=$!
  # shellcheck disable=SC2064
  trap 'kill ${PF_PID} 2>/dev/null; wait ${PF_PID} 2>/dev/null || true' EXIT
  sleep 1
  export LLAMA_STACK_ENDPOINT="http://127.0.0.1:${PF_PORT}"
  echo "[INFO] LLAMA_STACK_ENDPOINT=${LLAMA_STACK_ENDPOINT}"
else
  RHOST=$(oc get route llamastack-http -n "$NAMESPACE" -o jsonpath='{.spec.host}' 2>/dev/null || true)
  if [ -n "${RHOST:-}" ]; then
    TLS=$(oc get route llamastack-http -n "$NAMESPACE" -o jsonpath='{.spec.tls.termination}' 2>/dev/null || true)
    if [ -n "$TLS" ] && [ "$TLS" != "null" ]; then
      echo "[INFO] Using route: https://${RHOST}  (NAMESPACE=${NAMESPACE}, TLS edge)"
    else
      echo "[INFO] Using route: http://${RHOST}  (NAMESPACE=${NAMESPACE})"
    fi
  else
    echo "[WARN] Route llamastack-http not found in ${NAMESPACE}. Set LLAMA_STACK_ENDPOINT or use PORT_FORWARD=1."
  fi
fi

MOD_URL=$(oc get route cai-moderator-ui -n "$MODERATOR_NAMESPACE" -o jsonpath='https://{.spec.host}' 2>/dev/null || true)
if [ -n "$MOD_URL" ]; then
  echo "[INFO] F5 Moderator UI (tokens, policies): $MOD_URL"
  echo "       In Streamlit → Settings, set Guardrails endpoint to your OpenAI path, e.g. https://<moderator>/openai/<connection-name>"
fi

export STREAMLIT_RUN_ON_SAVE="${STREAMLIT_RUN_ON_SAVE:-1}"
echo "[INFO] Opening Streamlit on http://localhost:8501 (set STREAMLIT_RUN_ON_SAVE=0 to disable reload on save)"
echo ""

exec ./start.sh
