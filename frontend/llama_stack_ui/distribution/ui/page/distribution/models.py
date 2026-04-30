# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the terms described in the LICENSE file in
# the root directory of this source tree.

import os

import pandas as pd
import streamlit as st

from llama_stack_ui.distribution.ui.modules.api import llama_stack_api
from llama_stack_ui.distribution.ui.modules.guardrails_storage import write_state
from llama_stack_ui.distribution.ui.modules.utils import format_api_connection_error


def fetch_models():
    """Fetch models from the default LlamaStack endpoint and update session state"""
    st.session_state["models_loading"] = True
    st.session_state["models_error"] = None
    st.session_state["models_list"] = []

    try:
        models_list = llama_stack_api.client.models.list()
        st.session_state["models_loading"] = False
        if models_list:
            st.session_state["models_list"] = models_list
            st.session_state["models_error"] = None
            st.session_state["connection_status"] = "success"
        else:
            st.session_state["models_list"] = []
            st.session_state["models_error"] = "No models returned from LlamaStack"
            st.session_state["connection_status"] = "error"
    except Exception as e:
        st.session_state["models_loading"] = False
        st.session_state["models_list"] = []
        st.session_state["models_error"] = format_api_connection_error(e)
        st.session_state["connection_status"] = "error"


def models():
    """
    Configure F5 AI Guardrails and LlamaStack endpoints, and inspect available models.
    Both endpoints are used side-by-side in the Chat Comparison view.
    """
    st.header("Settings")

    # Session guardrail keys: hydrated in `app._init_guardrails_from_persisted` (file + optional env)
    st.session_state.setdefault("guardrail_url", "")
    st.session_state.setdefault("api_token", "")
    if "ls_endpoint_url" not in st.session_state:
        st.session_state["ls_endpoint_url"] = os.environ.get("LLAMA_STACK_ENDPOINT", "http://localhost:8321")
    if "ls_api_token" not in st.session_state:
        st.session_state["ls_api_token"] = os.environ.get("LLAMA_STACK_API_TOKEN", "")
    if "models_list" not in st.session_state:
        st.session_state["models_list"] = []
    if "models_loading" not in st.session_state:
        st.session_state["models_loading"] = False
    if "models_error" not in st.session_state:
        st.session_state["models_error"] = None
    if "connection_status" not in st.session_state:
        st.session_state["connection_status"] = None
    if "models_fetched" not in st.session_state:
        st.session_state["models_fetched"] = False

    # ------------------------------------------------------------------
    # F5 AI Guardrails
    # ------------------------------------------------------------------
    st.subheader("🛡️ F5 AI Guardrails")
    st.caption("When both fields are set, chat is scanned by your F5 AI Guardrails policies.")

    # Bind widgets to the same keys as hydration (`app._init_guardrails_from_persisted`).
    # Do not use separate widget keys + copy from return values: password inputs can
    # return "" on early frames and would overwrite a file-loaded token and corrupt JSON.
    st.text_input(
        "Endpoint URL",
        help="F5 AI Guardrails moderator endpoint (e.g., https://aisec.example.com/openai/llamastack). "
             "Leave empty to chat directly with LlamaStack. Also seedable via F5_GUARDRAIL_URL env var.",
        key="guardrail_url",
    )

    st.text_input(
        "API Token",
        type="password",
        help="Bearer token for the Guardrail endpoint. Create one in the Moderator UI under API tokens. "
             "Also seedable via F5_GUARDRAIL_API_TOKEN env var.",
        key="api_token",
    )

    try:
        write_state(
            st.session_state.get("guardrail_url", "") or "",
            st.session_state.get("api_token", "") or "",
        )
    except OSError as e:
        if not st.session_state.get("_guardrails_write_error_shown"):
            st.session_state["_guardrails_write_error_shown"] = True
            st.warning(f"Could not save guardrail settings to disk: {e}")

    # ------------------------------------------------------------------
    # LlamaStack Endpoint
    # ------------------------------------------------------------------
    st.subheader("🦙 LlamaStack Endpoint")
    st.caption("Direct LlamaStack inference endpoint (without guardrail scanning).")

    ls_url = st.text_input(
        "Endpoint URL",
        value=st.session_state["ls_endpoint_url"],
        help="LlamaStack endpoint URL. Also settable via LLAMA_STACK_ENDPOINT env var.",
        key="ls_url_settings",
    )
    ls_token = st.text_input(
        "API Token",
        value=st.session_state["ls_api_token"],
        type="password",
        help="Bearer token for LlamaStack (optional). "
             "Also settable via LLAMA_STACK_API_TOKEN env var.",
        key="ls_token_settings",
    )
    if ls_url != st.session_state["ls_endpoint_url"]:
        st.session_state["ls_endpoint_url"] = ls_url
    if ls_token != st.session_state["ls_api_token"]:
        st.session_state["ls_api_token"] = ls_token

    # ------------------------------------------------------------------
    # Auto-fetch models on first load
    # ------------------------------------------------------------------
    if not st.session_state["models_fetched"] and not st.session_state["models_loading"]:
        with st.spinner("Fetching models from LlamaStack..."):
            fetch_models()
        st.session_state["models_fetched"] = True
        st.rerun()

    if st.session_state["models_loading"]:
        st.info("Fetching models...")
        return

    # ------------------------------------------------------------------
    # Display available models
    # ------------------------------------------------------------------
    st.subheader("Available Models")

    models_list = st.session_state["models_list"]

    if not models_list and st.session_state["models_error"]:
        st.error(f"{st.session_state['models_error']}")
        return

    if not models_list:
        st.info("No models available.")
        return

    llm_models = [model for model in models_list if hasattr(model, 'api_model_type') and model.api_model_type == "llm"]

    if not llm_models:
        st.info("No LLM models available from this endpoint.")
        return

    models_data = [{"Model Identifier": model.identifier} for model in llm_models]
    df = pd.DataFrame(models_data)
    df.index = df.index + 1
    st.dataframe(df, use_container_width=True, hide_index=False)

    # ------------------------------------------------------------------
    # Endpoint status
    # ------------------------------------------------------------------
    st.subheader("Endpoint Status")
    col1, col2 = st.columns(2)
    with col1:
        if st.session_state["guardrail_url"] and st.session_state["api_token"]:
            st.success("🛡️ F5 Guardrails: Configured")
        else:
            st.warning("🛡️ F5 Guardrails: Not configured")
    with col2:
        if st.session_state["ls_endpoint_url"]:
            st.success("🦙 LlamaStack: Configured")
        else:
            st.warning("🦙 LlamaStack: Not configured")
