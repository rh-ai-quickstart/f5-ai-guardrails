# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the terms described in the LICENSE file in
# the root directory of this source tree.

import os

import streamlit as st
from llama_stack_ui.distribution.ui.modules.api import (
    active_llama_stack_client,
    list_vector_catalog,
    llama_stack_api,
    rag_tool_query,
)
from llama_stack_ui.distribution.ui.modules.guardrails_storage import write_state
from llama_stack_ui.distribution.ui.modules.utils import (
    format_api_connection_error,
    get_suggestions_for_databases,
    get_vector_db_id,
    get_vector_db_name,
    llamastack_model_id,
    llamastack_model_is_llm,
    openai_chat_completion_debug_hint,
    openai_chat_completion_text,
)


def _get_scanner_names() -> dict[str, str]:
    """Fetch and cache the scanner ID → name mapping from the Moderator API."""
    if "scanner_name_map" not in st.session_state:
        g_url = st.session_state.get("guardrail_url", "")
        g_token = st.session_state.get("api_token", "")
        if g_url and g_token:
            st.session_state.scanner_name_map = llama_stack_api.fetch_scanner_names(g_url, g_token)
        else:
            st.session_state.scanner_name_map = {}
    return st.session_state.scanner_name_map


def _format_guardrail_block(exc):
    """Parse a CAI guardrails block error into a user-friendly message."""
    body = getattr(exc, "body", None)
    if not isinstance(body, dict):
        return f"🚫 **Blocked by Guardrail**\n\n{exc}"

    cai_error = body.get("cai_error", {})
    if not cai_error:
        return f"🚫 **Blocked by Guardrail**\n\n{body.get('message', str(exc))}"

    scanner_results = cai_error.get("scanner_results", [])
    failed = [s for s in scanner_results if s.get("outcome") == "failed"]

    if not failed:
        return "🚫 **Blocked by Guardrail**"

    name_map = _get_scanner_names()

    lines = [f"🚫 **Blocked by Guardrail** — {len(failed)} scanner(s) triggered:\n"]
    for s in failed:
        sid = s.get("scanner_id", "unknown")
        sdir = s.get("scan_direction", "")
        scanner_name = name_map.get(sid)
        if scanner_name:
            label = scanner_name
        else:
            raw_data = s.get("data")
            data = raw_data if isinstance(raw_data, dict) else {}
            stype = data.get("type", "unknown")
            label = f"Pattern Match (PII/Regex) — `{sid}`" if stype == "regex" else f"AI Scanner — `{sid}`"
        dir_label = f" on {sdir}" if sdir else ""
        lines.append(f"- **{label}**{dir_label}")

    return "\n".join(lines)


def tool_chat_page():
    st.title("💬 Chat")

    # ------------------------------------------------------------------
    # Endpoint defaults  (guardrail keys hydrated in app._init_guardrails_from_persisted)
    # ------------------------------------------------------------------
    st.session_state.setdefault("guardrail_url", "")
    st.session_state.setdefault("api_token", "")
    if "ls_endpoint_url" not in st.session_state:
        st.session_state.ls_endpoint_url = os.environ.get("LLAMA_STACK_ENDPOINT", "http://localhost:8321")
    if "ls_api_token" not in st.session_state:
        st.session_state.ls_api_token = os.environ.get("LLAMA_STACK_API_TOKEN", "")

    # ------------------------------------------------------------------
    # Model list (shared — fetched from default LlamaStack endpoint)
    # ------------------------------------------------------------------
    def get_available_models():
        if "models_list" in st.session_state and st.session_state["models_list"]:
            models_list = st.session_state["models_list"]
            llm_models = [m for m in models_list if llamastack_model_is_llm(m)]
            return [llamastack_model_id(m) for m in llm_models]
        else:
            try:
                models = active_llama_stack_client().models.list()
                return [llamastack_model_id(m) for m in models if llamastack_model_is_llm(m)]
            except Exception:
                return []

    selected_vector_dbs = []
    toolgroup_selection = ["builtin::rag"]

    def reset_chat():
        keys_to_keep = {
            "guardrail_url", "api_token",
            "ls_endpoint_url", "ls_api_token",
            "models_list", "models_fetched",
            "_f5_guardrails_persist_hydrated",
        }
        for key in list(st.session_state.keys()):
            if key not in keys_to_keep:
                del st.session_state[key]
        st.cache_resource.clear()

    # ------------------------------------------------------------------
    # Sidebar — shared configuration
    # ------------------------------------------------------------------
    with st.sidebar:
        st.title("Configuration")

        # ---- F5 Guardrails endpoint ----
        with st.expander("🛡️ F5 Guardrails Endpoint", expanded=not st.session_state.get("guardrail_url")):
            g_url = st.text_input(
                "Endpoint URL",
                value=st.session_state.get("guardrail_url", ""),
                key="gurl_sidebar",
                help="F5 AI Guardrails endpoint (e.g. https://moderator.example.com/openai/connection-name)",
            )
            g_token = st.text_input(
                "API Token",
                value=st.session_state.get("api_token", ""),
                type="password",
                key="gtoken_sidebar",
                help="Bearer token for the F5 Guardrails endpoint",
            )
            f5_changed = False
            if g_url != st.session_state.get("guardrail_url", ""):
                st.session_state.guardrail_url = g_url
                f5_changed = True
            if g_token != st.session_state.get("api_token", ""):
                st.session_state.api_token = g_token
                f5_changed = True
            if f5_changed:
                try:
                    write_state(st.session_state.get("guardrail_url", ""),
                                st.session_state.get("api_token", ""))
                except OSError:
                    pass

        # ---- LlamaStack endpoint ----
        with st.expander("🦙 LlamaStack Endpoint", expanded=not st.session_state.get("ls_endpoint_url")):
            st.text_input(
                "Endpoint URL",
                help="LlamaStack endpoint URL (default from LLAMA_STACK_ENDPOINT env var)",
                key="ls_endpoint_url",
            )
            st.text_input(
                "API Token",
                type="password",
                help="Bearer token for LlamaStack (optional)",
                key="ls_api_token",
            )

        # LlamaStack widgets above must run before we build the client (same run + same keys).
        model_list: list = []
        tool_groups_list: list = []
        mcp_tools_list: list = []
        vector_dbs: list = []
        client = active_llama_stack_client()
        try:
            model_list = get_available_models()
        except Exception as e:
            st.sidebar.error(f"LlamaStack models: {e}")
        try:
            tool_groups = client.toolgroups.list()
            tool_groups_list = [tg.identifier for tg in tool_groups]
            mcp_tools_list = [t for t in tool_groups_list if t.startswith("mcp::")]
        except Exception as e:
            st.sidebar.warning(
                "LlamaStack tool groups: "
                + format_api_connection_error(e, st.session_state.get("ls_endpoint_url"))
            )
        try:
            vector_dbs = list_vector_catalog(client) or []
        except Exception as e:
            st.sidebar.warning(
                "LlamaStack vector DBs: "
                + format_api_connection_error(e, st.session_state.get("ls_endpoint_url"))
            )

        # ---- Document Collections (RAG) ----
        if vector_dbs:
            vector_db_names = [get_vector_db_name(vdb) for vdb in vector_dbs]
            selected_vector_dbs = st.multiselect(
                "Document Collections (RAG)",
                options=vector_db_names,
            )

        # ---- MCP servers ----
        if mcp_tools_list:
            mcp_selection = st.pills(
                "MCP Servers",
                options=mcp_tools_list,
                selection_mode="multi",
                format_func=lambda t: "".join(t.split("::")[1:]),
                help="MCP servers registered to your LlamaStack server.",
            )
            toolgroup_selection.extend(mcp_selection)

        # ---- Sampling parameters ----
        st.subheader("Sampling Parameters")
        temperature = st.slider("Temperature", 0.0, 2.0, 0.1, 0.05)
        top_p = st.slider("Top P", 0.0, 1.0, 0.95, 0.05)
        max_tokens = st.slider("Max Tokens", 1, 4096, 512, 64)
        repetition_penalty = st.slider("Repetition Penalty", 1.0, 2.0, 1.0, 0.05)

        # ---- System prompt ----
        st.subheader("System Prompt")
        system_prompt = st.text_area(
            "System Prompt",
            value="You are a helpful AI assistant.",
            height=100,
        )

        if st.button("Clear Chat & Reset", use_container_width=True):
            reset_chat()
            st.rerun()

    model_pick = model_list if model_list else ["(no models — check LlamaStack URL / cluster)"]

    # ------------------------------------------------------------------
    # Session state — dual message histories
    # ------------------------------------------------------------------
    if "f5_messages" not in st.session_state:
        st.session_state.f5_messages = [{"role": "assistant", "content": "How can I help you?"}]
    if "ls_messages" not in st.session_state:
        st.session_state.ls_messages = [{"role": "assistant", "content": "How can I help you?"}]
    if "selected_question" not in st.session_state:
        st.session_state.selected_question = None
    if "show_more_questions" not in st.session_state:
        st.session_state.show_more_questions = False

    if not model_list:
        st.warning(
            "LlamaStack did not return any models (connection error, wrong URL, or HTTP 503). "
            "For `./start.sh`, confirm `oc login` and that the `llamastack` pod in your RAG namespace is Ready, then refresh."
        )

    # ------------------------------------------------------------------
    # Dual-panel layout
    # ------------------------------------------------------------------
    left_col, right_col = st.columns(2)

    with left_col:
        st.markdown("### 🛡️ F5 Guardrails")
        f5_model = st.selectbox(
            "Model", model_pick, key="f5_model_select", label_visibility="collapsed",
        )
        g_url_display = st.session_state.get("guardrail_url", "")
        if g_url_display:
            st.caption(f"`{g_url_display}`")
        else:
            st.caption("⚠️ Endpoint not configured — set in sidebar")
        f5_chat = st.container(height=500)

    with right_col:
        st.markdown("### 🦙 LlamaStack Direct")
        ls_model = st.selectbox(
            "Model", model_pick, key="ls_model_select", label_visibility="collapsed",
        )
        st.caption(f"`{st.session_state.get('ls_endpoint_url', '')}`")
        ls_chat = st.container(height=500)

    # Render existing histories
    with f5_chat:
        for msg in st.session_state.f5_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    with ls_chat:
        for msg in st.session_state.ls_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # ------------------------------------------------------------------
    # Suggested questions (RAG)
    # ------------------------------------------------------------------
    def display_suggested_questions():
        if not model_list or not selected_vector_dbs:
            return
        try:
            all_vdbs = list_vector_catalog(active_llama_stack_client()) or []
        except Exception:
            return
        suggestions = get_suggestions_for_databases(selected_vector_dbs, all_vdbs)
        if not suggestions:
            return

        st.markdown("### 💡 Suggested Questions")
        num_to_show = len(suggestions) if st.session_state.show_more_questions else min(4, len(suggestions))
        cols_per_row = 2
        for i in range(0, num_to_show, cols_per_row):
            cols = st.columns(cols_per_row)
            for j in range(cols_per_row):
                idx = i + j
                if idx < num_to_show:
                    question, db_name = suggestions[idx]
                    with cols[j]:
                        if st.button(
                            question,
                            key=f"q_btn_{idx}_{hash(question)}",
                            use_container_width=True,
                            help=f"From: {db_name}",
                        ):
                            st.session_state.selected_question = question
                            st.rerun()

        if len(suggestions) > 4:
            _, mid, _ = st.columns([1, 1, 1])
            with mid:
                if st.session_state.show_more_questions:
                    if st.button("Show Less", use_container_width=True):
                        st.session_state.show_more_questions = False
                        st.rerun()
                else:
                    if st.button(f"Show More ({len(suggestions) - 4} more)", use_container_width=True):
                        st.session_state.show_more_questions = True
                        st.rerun()
        st.markdown("---")

    display_suggested_questions()

    # ------------------------------------------------------------------
    # Process a prompt — send the SAME request to BOTH endpoints
    # using the SAME OpenAI client (chat.completions.create)
    # ------------------------------------------------------------------
    def process_dual_prompt(prompt):
        if not model_list:
            st.error("Load LlamaStack models first (see warning above).")
            return
        # Append user message to both histories
        st.session_state.f5_messages.append({"role": "user", "content": prompt})
        st.session_state.ls_messages.append({"role": "user", "content": prompt})

        with f5_chat:
            with st.chat_message("user"):
                st.markdown(prompt)
        with ls_chat:
            with st.chat_message("user"):
                st.markdown(prompt)

        # --- Shared RAG context ---
        prompt_context = None
        if selected_vector_dbs:
            all_vdbs = list_vector_catalog(client) or []
            vdb_ids = [get_vector_db_id(v) for v in all_vdbs if get_vector_db_name(v) in selected_vector_dbs]
            with st.spinner("Retrieving context (RAG)..."):
                try:
                    rag_resp = rag_tool_query(
                        client,
                        content=prompt,
                        vector_db_ids=list(vdb_ids),
                    )
                    prompt_context = rag_resp.content
                except Exception as e:
                    st.warning(
                        "RAG Error: "
                        + format_api_connection_error(e, st.session_state.get("ls_endpoint_url"))
                    )

        if prompt_context:
            extended_prompt = (
                f"Please answer the following query using the context below.\n\n"
                f"CONTEXT:\n{prompt_context}\n\nQUERY:\n{prompt}"
            )
        else:
            extended_prompt = f"Please answer the following query.\n\nQUERY:\n{prompt}"

        messages_for_api = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": extended_prompt},
        ]

        # ---- F5 Guardrails (OpenAI client → chat.completions.create) ----
        f5_response = ""
        with f5_chat:
            with st.chat_message("assistant"):
                f5_placeholder = st.empty()
                f5_ep = st.session_state.get("guardrail_url", "")
                f5_tk = st.session_state.get("api_token", "")
                if f5_ep and f5_tk:
                    try:
                        f5_oai = llama_stack_api.create_openai_client(
                            f5_ep.strip(), f5_tk.strip(),
                        )
                        # Do not send vLLM-only extra_body through the Moderator; some stacks return 200 with empty messages.
                        resp = f5_oai.chat.completions.create(
                            model=f5_model,
                            messages=messages_for_api,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            top_p=top_p,
                        )
                        f5_response = openai_chat_completion_text(resp)
                        if not f5_response.strip():
                            f5_response = (
                                "⚠️ F5 Guardrails returned an empty completion.\n\n"
                                f"```\n{openai_chat_completion_debug_hint(resp)}\n```\n\n"
                                "Confirm the **Moderator → model** connection uses the same **model id** as in the sidebar, "
                                "and that the upstream URL is `/v1/chat/completions` on LlamaStack 0.6+."
                            )
                    except Exception as e:
                        body = getattr(e, "body", None)
                        if isinstance(body, dict) and "cai_error" in body:
                            f5_response = _format_guardrail_block(e)
                        else:
                            f5_response = f"⚠️ F5 Guardrails error: {e}"
                else:
                    f5_response = (
                        "⚠️ F5 Guardrails endpoint not configured.\n\n"
                        "Set **Endpoint URL** and **API Token** in the sidebar."
                    )
                f5_placeholder.markdown(f5_response)
        st.session_state.f5_messages.append({"role": "assistant", "content": f5_response})

        # ---- LlamaStack (same OpenAI client → chat.completions.create) ----
        ls_response = ""
        with ls_chat:
            with st.chat_message("assistant"):
                ls_placeholder = st.empty()
                try:
                    ls_oai = llama_stack_api.create_openai_client_for_llamastack(
                        st.session_state.ls_endpoint_url,
                        st.session_state.ls_api_token,
                    )
                    resp = ls_oai.chat.completions.create(
                        model=ls_model,
                        messages=messages_for_api,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        top_p=top_p,
                        extra_body={"repetition_penalty": repetition_penalty},
                    )
                    ls_response = openai_chat_completion_text(resp)
                    if not ls_response.strip():
                        ls_response = (
                            "⚠️ LlamaStack returned an empty completion. "
                            "Use the **server root** in settings (e.g. `https://…/…` without `/v1/models`)."
                        )
                except Exception as e:
                    ls_response = f"⚠️ LlamaStack error: {e}"
                ls_placeholder.markdown(ls_response)
        st.session_state.ls_messages.append({"role": "assistant", "content": ls_response})

    # ------------------------------------------------------------------
    # Handle input
    # ------------------------------------------------------------------
    if st.session_state.selected_question:
        prompt = st.session_state.selected_question
        st.session_state.selected_question = None
        process_dual_prompt(prompt)

    _chat_prompt = st.chat_input(
        "Ask a question — sent to both endpoints...",
        disabled=not model_list,
    )
    if model_list and _chat_prompt:
        process_dual_prompt(_chat_prompt)


tool_chat_page()
