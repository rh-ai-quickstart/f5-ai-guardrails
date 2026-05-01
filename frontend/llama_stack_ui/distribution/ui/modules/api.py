# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the terms described in the LICENSE file in
# the root directory of this source tree.

import os
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, List, Mapping, Optional, Sequence, Tuple
import requests
import httpx

from llama_stack_client import LlamaStackClient
from openai import OpenAI

_HTTPX_TIMEOUT = httpx.Timeout(120.0, connect=30.0)

# OpenAI Python ``base_url`` must end with ``/v1`` so requests go to ``…/v1/chat/completions``.
# LlamaStack 0.6+ serves chat there; ``/v1/openai/v1/…`` exists in some older builds but returns 404 on 0.6 starter.
_LLAMA_OPENAI_SDK_SUFFIX = "/v1"


def guardrail_openai_base_url(url: str) -> str:
    """Normalize Moderator OpenAI proxy URL (no trailing slash; strip pasted ``…/chat/completions``)."""
    u = (url or "").strip().rstrip("/")
    if u.endswith("/chat/completions"):
        u = u[: -len("/chat/completions")].rstrip("/")
    return u


def llamastack_openai_chat_base_url(endpoint: str) -> str:
    """
    Normalize LlamaStack origin for the OpenAI Python client (``base_url`` ending in ``/v1``).

    Chat requests use ``{base_url}/chat/completions`` → ``https://host/v1/chat/completions`` on LlamaStack 0.6+.
    Strips legacy ``/v1/openai/v1`` suffixes from older docs and accidental ``/v1/models`` paste targets.
    """
    u = (endpoint or "").strip().rstrip("/")
    if not u:
        u = (os.environ.get("LLAMA_STACK_ENDPOINT") or "http://localhost:8321").strip().rstrip("/")
    if u.endswith("/chat/completions"):
        u = u[: -len("/chat/completions")].rstrip("/")
    legacy = "/v1/openai/v1"
    while u.endswith(legacy):
        u = u[: -len(legacy)].rstrip("/")
    if u.endswith("/v1/models"):
        u = u[: -len("/models")].rstrip("/")
    if not u:
        u = (os.environ.get("LLAMA_STACK_ENDPOINT") or "http://localhost:8321").strip().rstrip("/")
    suf = _LLAMA_OPENAI_SDK_SUFFIX
    if not u.endswith(suf):
        u = u + suf
    return u


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
        base = guardrail_openai_base_url(base_url)
        return OpenAI(
            base_url=base,
            api_key=api_token,
            http_client=httpx.Client(verify=False, follow_redirects=True, timeout=_HTTPX_TIMEOUT),
        )

    def create_openai_client_for_llamastack(self, base_url: str = "", api_token: str = "") -> OpenAI:
        """Create an OpenAI client targeting LlamaStack chat at ``{origin}/v1/chat/completions``."""
        raw = base_url or os.environ.get("LLAMA_STACK_ENDPOINT", "http://localhost:8321")
        openai_base = llamastack_openai_chat_base_url(raw)
        origin = openai_base[: -len(_LLAMA_OPENAI_SDK_SUFFIX)].rstrip("/") if openai_base.endswith(_LLAMA_OPENAI_SDK_SUFFIX) else raw.strip().rstrip("/")
        hx = _httpx_client_for_url(origin) or httpx.Client(follow_redirects=True, timeout=_HTTPX_TIMEOUT)
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
    LlamaStack client using session URL/token when present, else env vars.
    Reads canonical keys plus legacy widget keys (Chat/Settings ran in different
    orders or used different keys) so API calls still see the URL the user set.
    """
    base = os.environ.get("LLAMA_STACK_ENDPOINT", "http://localhost:8321")
    token = os.environ.get("LLAMA_STACK_API_TOKEN", "")
    try:
        import streamlit as st

        if hasattr(st, "session_state"):
            ss = st.session_state
            # URL: prefer non-empty widget/session values (Chat may not have synced yet)
            for k in ("ls_endpoint_url", "ls_url_sidebar", "ls_url_settings"):
                v = (ss.get(k) or "").strip()
                if v:
                    base = v
                    break
            else:
                base = (ss.get("ls_endpoint_url") or base).strip() or base
            # Token: optional; empty widget means fall through to env
            tok = None
            for k in ("ls_api_token", "ls_token_sidebar", "ls_token_settings"):
                if k not in ss:
                    continue
                raw = ss.get(k)
                if raw is not None and str(raw).strip() != "":
                    tok = str(raw).strip()
                    break
            if tok is not None:
                token = tok
            else:
                token = (ss.get("ls_api_token") or token) or ""
    except Exception:
        pass
    return llama_stack_api.create_client_with_url(base, token)


@dataclass
class VectorDbRecord:
    """REST `/v1/vector-dbs` row when the Python client has no `vector_dbs` resource."""

    _raw: dict
    identifier: str
    vector_db_name: str

    @classmethod
    def from_mapping(cls, d: Mapping[str, Any]) -> "VectorDbRecord":
        raw = dict(d)
        ident = str(raw.get("vector_db_id") or raw.get("identifier") or raw.get("id") or "")
        name = str(raw.get("vector_db_name") or raw.get("name") or ident)
        return cls(_raw=raw, identifier=ident, vector_db_name=name)

    def to_dict(self) -> dict:
        return dict(self._raw)


def _vector_catalog_from_vector_stores(client: LlamaStackClient) -> List[Any]:
    """LlamaStack 0.6+ distributions may omit ``/v1/vector-dbs``; use OpenAI-compatible vector stores."""
    out: List[Any] = []
    for vs in client.vector_stores.list():
        dumped = vs.model_dump() if hasattr(vs, "model_dump") else {}
        vid = str(dumped.get("id") or getattr(vs, "id", "") or "")
        label = str(dumped.get("name") or vid)
        raw = {**dumped, "vector_db_id": vid, "vector_db_name": label, "identifier": vid}
        out.append(VectorDbRecord.from_mapping(raw))
    return out


def list_vector_catalog(client: LlamaStackClient) -> List[Any]:
    vd = getattr(client, "vector_dbs", None)
    if vd is not None:
        out = vd.list()
        return list(out) if out is not None else []
    try:
        raw = client.get("/v1/vector-dbs", cast_to=object)
    except Exception as e:
        if getattr(e, "status_code", None) == 404:
            return _vector_catalog_from_vector_stores(client)
        raise
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = raw.get("data") or raw.get("vector_dbs") or []
        if not isinstance(items, list):
            items = []
    else:
        items = []
    return [VectorDbRecord.from_mapping(x) if isinstance(x, dict) else x for x in items]


def register_vector_db(
    client: LlamaStackClient,
    *,
    vector_db_id: str,
    embedding_model: str,
    embedding_dimension: int = 384,
    provider_id: Optional[str] = None,
    vector_db_name: Optional[str] = None,
    provider_vector_db_id: Optional[str] = None,
) -> Any:
    vd = getattr(client, "vector_dbs", None)
    if vd is not None:
        kwargs: dict[str, Any] = {
            "vector_db_id": vector_db_id,
            "embedding_dimension": embedding_dimension,
            "embedding_model": embedding_model,
        }
        if provider_id:
            kwargs["provider_id"] = provider_id
        return vd.register(**kwargs)
    body: dict[str, Any] = {
        "vector_db_id": vector_db_id,
        "embedding_model": embedding_model,
        "embedding_dimension": embedding_dimension,
    }
    if provider_id:
        body["provider_id"] = provider_id
    if vector_db_name:
        body["vector_db_name"] = vector_db_name
    if provider_vector_db_id:
        body["provider_vector_db_id"] = provider_vector_db_id
    try:
        return client.post("/v1/vector-dbs", body=body, cast_to=object)
    except Exception as e:
        if getattr(e, "status_code", None) == 404:
            return client.vector_stores.create(name=vector_db_id)
        raise


def _serialize_rag_documents(documents: Sequence[Any]) -> list:
    out: list = []
    for d in documents:
        if hasattr(d, "to_dict"):
            out.append(d.to_dict())
        elif hasattr(d, "model_dump"):
            out.append(d.model_dump(exclude_none=True))
        elif isinstance(d, dict):
            out.append(d)
        else:
            row = {
                "document_id": getattr(d, "document_id", ""),
                "content": getattr(d, "content", ""),
            }
            md = getattr(d, "metadata", None)
            if md is not None:
                row["metadata"] = md
            mt = getattr(d, "mime_type", None)
            if mt is not None:
                row["mime_type"] = mt
            out.append(row)
    return out


def rag_tool_insert(
    client: LlamaStackClient,
    *,
    vector_db_id: str,
    documents: Sequence[Any],
    chunk_size_in_tokens: int = 512,
) -> Any:
    rag = getattr(getattr(client, "tool_runtime", None), "rag_tool", None)
    if rag is not None:
        return rag.insert(
            vector_db_id=vector_db_id,
            documents=list(documents),
            chunk_size_in_tokens=chunk_size_in_tokens,
        )
    body = {
        "vector_db_id": vector_db_id,
        "documents": _serialize_rag_documents(documents),
        "chunk_size_in_tokens": chunk_size_in_tokens,
    }
    return client.post("/v1/tool-runtime/rag-tool/insert", body=body, cast_to=object)


def rag_tool_query(
    client: LlamaStackClient,
    *,
    content: str,
    vector_db_ids: List[str],
    query_config: Optional[Any] = None,
) -> Any:
    rag = getattr(getattr(client, "tool_runtime", None), "rag_tool", None)
    if rag is not None:
        return rag.query(content=content, vector_db_ids=vector_db_ids)
    body: dict[str, Any] = {"content": content, "vector_db_ids": vector_db_ids}
    if query_config is not None:
        body["query_config"] = query_config
    raw = client.post("/v1/tool-runtime/rag-tool/query", body=body, cast_to=dict)
    return SimpleNamespace(content=raw.get("content"))
