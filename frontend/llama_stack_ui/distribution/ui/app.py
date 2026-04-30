# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the terms described in the LICENSE file in
# the root directory of this source tree.
import os

import streamlit as st

from llama_stack_ui.distribution.ui.modules.guardrails_storage import read_state

_INIT_KEY = "_f5_guardrails_persist_hydrated"


def _init_guardrails_from_persisted():
    if st.session_state.get(_INIT_KEY):
        return
    data = read_state()
    gurl = (data.get("guardrail_url", "") or "").strip() or os.environ.get("F5_GUARDRAIL_URL", "").strip()
    tok = (data.get("api_token", "") or "").strip() or os.environ.get("F5_GUARDRAIL_API_TOKEN", "").strip()
    st.session_state["guardrail_url"] = gurl
    st.session_state["api_token"] = tok
    st.session_state.setdefault("ls_endpoint_url", os.environ.get("LLAMA_STACK_ENDPOINT", "http://localhost:8321"))
    st.session_state.setdefault("ls_api_token", os.environ.get("LLAMA_STACK_API_TOKEN", ""))
    st.session_state[_INIT_KEY] = True


def main():
    _init_guardrails_from_persisted()
    # Define available pages: path and icon
    pages = {
        "Chat": ("page/playground/chat.py", "💬"),
        "Settings": ("page/distribution/inspect.py", "⚙️"),
    }

    # Build navigation items dynamically
    nav_items = [
        st.Page(path, title=name, icon=icon, default=(name == "Chat"))
        for name, (path, icon) in pages.items()
    ]
    # Render navigation
    pg = st.navigation({"Playground": nav_items}, expanded=False)
    pg.run()


if __name__ == "__main__":
    main()
