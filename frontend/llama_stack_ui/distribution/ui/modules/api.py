# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the terms described in the LICENSE file in
# the root directory of this source tree.

import os
from typing import Optional, Tuple, List
import requests
import httpx

from llama_stack_client import LlamaStackClient
from openai import OpenAI

_HTTPX_TIMEOUT = httpx.Timeout(120.0, connect=30.0)


def _httpx_client_for_url(url: str) -> httpx.Client | None:
    """
    OpenShift edge routes are HTTPS; http:// to *.apps... often returns HTML/redirects.
    Use relaxed TLS and redirects for public cluster URLs. Keep defaults for local dev.
    """
    u = (url or "").lower().rstrip("/")
    if "localhost" in u or "127.0.0.1" in u or u.startswith("http://[::1]"):
        return httpx.Client(follow_redirects=True, timeout=_HTTPX_TIMEOUT)
    if u.startswith("http://llamastack") and ".apps." not in u:
        return httpx.Client(follow_redirects=True, timeout=_HTTPX_TIMEOUT)
    if u.startswith("http://") or u.startswith("https://"):
        return httpx.Client(verify=False, follow_redirects=True, timeout=_HTTPX_TIMEOUT)
    return None


class LlamaStackApi:
    def __init__(self):
        base = os.environ.get("LLAMA_STACK_ENDPOINT", "http://localhost:8321")
        token = os.environ.get("LLAMA_STACK_API_TOKEN", "")
        self.client = self.create_client_with_url(base, token)

    def run_scoring(self, row, scoring_function_ids: list[str], scoring_params: Optional[dict]):
        """Run scoring on a single row"""
        if not scoring_params:
            scoring_params = {fn_id: None for fn_id in scoring_function_ids}
        return self.client.scoring.score(input_rows=[row], scoring_functions=scoring_params)

    def create_openai_client(self, base_url: str, api_token: str) -> OpenAI:
        """Create an OpenAI client for the F5 AI Guardrails endpoint"""
        return OpenAI(
            base_url=base_url,
            api_key=api_token,
            http_client=httpx.Client(verify=False, follow_redirects=True, timeout=_HTTPX_TIMEOUT),
        )

    def create_openai_client_for_llamastack(self, base_url: str = "", api_token: str = "") -> OpenAI:
        """Create an OpenAI client targeting LlamaStack's OpenAI-compatible endpoint (/v1/openai/v1)."""
        url = base_url or os.environ.get("LLAMA_STACK_ENDPOINT", "http://localhost:8321")
        openai_base = url.rstrip("/") + "/v1/openai/v1"
        hx = _httpx_client_for_url(url) or httpx.Client(follow_redirects=True, timeout=_HTTPX_TIMEOUT)
        return OpenAI(
            base_url=openai_base,
            api_key=api_token or "no-key",
            http_client=hx,
        )

    def create_client_with_url(self, base_url: str, api_token: str = "") -> LlamaStackClient:
        """Create a LlamaStackClient with custom base URL and optional API token"""
        kwargs: dict = {"base_url": base_url}
        hx = _httpx_client_for_url(base_url)
        if hx is not None:
            kwargs["http_client"] = hx
        if api_token:
            kwargs["api_key"] = api_token
        return LlamaStackClient(**kwargs)

    def validate_llamastack_endpoint(self, url: str, api_token: str = "") -> Tuple[bool, Optional[List], Optional[str]]:
        """
        Validate if the URL is a LlamaStack endpoint and fetch models.

        Returns:
            Tuple[bool, Optional[List], Optional[str]]:
            (is_valid, models_list, error_message)
        """
        try:
            url = url.rstrip('/')

            if not url.startswith(('http://', 'https://')):
                return False, None, "XC URL must start with http:// or https://"

            client = self.create_client_with_url(url, api_token)

            models = client.models.list()

            if not models:
                return False, None, "XC URL must be a LlamaStack endpoint"

            return True, models, None

        except requests.exceptions.ConnectionError:
            return False, None, "Cannot connect to XC URL. Please check the URL and network connectivity."
        except requests.exceptions.Timeout:
            return False, None, "Connection to XC URL timed out. Please try again."
        except Exception as e:
            return False, None, f"Connection failed: {type(e).__name__}: {e}"

    def fetch_models_from_url(self, url: str, api_token: str = "") -> Tuple[bool, Optional[List], Optional[str]]:
        """
        Fetch models from a custom LlamaStack URL.

        Returns:
            Tuple[bool, Optional[List], Optional[str]]:
            (success, models_list, error_message)
        """
        return self.validate_llamastack_endpoint(url, api_token)

    def fetch_scanner_names(self, guardrail_url: str, api_token: str) -> dict[str, str]:
        """
        Fetch scanner ID → name mapping from the F5 Moderator API.
        Derives the Moderator base URL from the guardrail proxy URL
        (strips /openai/... suffix), finds the project, and queries
        /backend/v1/ui/project-scanners for human-readable names.
        Returns {scanner_id: scanner_name} or empty dict on failure.
        """
        url = guardrail_url.rstrip("/")
        if "/openai/" in url:
            base = url[:url.index("/openai/")]
        else:
            base = url

        headers = {"Authorization": f"Bearer {api_token}", "Accept": "application/json"}
        timeout = httpx.Timeout(10.0, connect=5.0)

        try:
            # Step 1: get projects to find the project ID
            resp = httpx.get(
                f"{base}/backend/v1/projects",
                headers=headers, verify=False, follow_redirects=True, timeout=timeout,
            )
            if resp.status_code != 200:
                return {}
            projects = resp.json().get("projects", [])
            if not projects:
                return {}

            # Step 2: for each project, fetch scanner details
            mapping: dict[str, str] = {}
            for project in projects:
                pid = project.get("id", "")
                if not pid:
                    continue
                resp = httpx.get(
                    f"{base}/backend/v1/ui/project-scanners",
                    params={"projectId": pid},
                    headers=headers, verify=False, follow_redirects=True, timeout=timeout,
                )
                if resp.status_code != 200:
                    continue
                scanners = resp.json().get("projectScanners", {}).get("scanners", {})
                for sid, info in scanners.items():
                    name = info.get("name", "")
                    if sid and name:
                        mapping[sid] = name
                if mapping:
                    return mapping
        except Exception:
            pass
        return {}


llama_stack_api = LlamaStackApi()


def active_llama_stack_client() -> LlamaStackClient:
    """
    LlamaStack client using Settings sidebar URL/token when present, else env vars.
    Use this from Streamlit pages instead of llama_stack_api.client so in-cluster
    LLAMA_STACK_* env and UI overrides stay consistent.
    """
    base = os.environ.get("LLAMA_STACK_ENDPOINT", "http://localhost:8321")
    token = os.environ.get("LLAMA_STACK_API_TOKEN", "")
    try:
        import streamlit as st

        if hasattr(st, "session_state"):
            base = (st.session_state.get("ls_endpoint_url") or base).strip() or base
            token = (st.session_state.get("ls_api_token") or token) or ""
    except Exception:
        pass
    return llama_stack_api.create_client_with_url(base, token)
