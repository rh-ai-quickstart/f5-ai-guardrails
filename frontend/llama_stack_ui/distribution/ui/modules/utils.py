# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the terms described in the LICENSE file in
# the root directory of this source tree.

import base64
import json
import os

import pandas as pd
import streamlit as st


"""
Utility functions for file processing and data conversion in the UI.
"""


def process_dataset(file):
    """
    Read an uploaded file into a Pandas DataFrame or return error messages.
    Supports CSV and Excel formats.
    """
    if file is None:
        return "No file uploaded", None

    try:
        # Determine file type and read accordingly
        file_ext = os.path.splitext(file.name)[1].lower()
        if file_ext == ".csv":
            df = pd.read_csv(file)
        elif file_ext in [".xlsx", ".xls"]:
            df = pd.read_excel(file)
        else:
            # Unsupported extension
            return "Unsupported file format. Please upload a CSV or Excel file.", None

        return df

    except Exception as e:
        st.error(f"Error processing file: {str(e)}")
        return None


def data_url_from_file(file) -> str:
    """
    Convert uploaded file content to a base64-encoded data URL.
    Used for embedding documents for vector DB ingestion.
    """
    file_content = file.getvalue()
    base64_content = base64.b64encode(file_content).decode("utf-8")
    mime_type = file.type

    data_url = f"data:{mime_type};base64,{base64_content}"

    return data_url


def get_vector_db_name(vector_db):
    """
    Get the display name for a vector database.
    Supports legacy vector_dbs objects, REST-shim records, and OpenAI vector_stores.
    """
    name = getattr(vector_db, "vector_db_name", None) or getattr(vector_db, "name", None)
    if name:
        return str(name)
    ident = getattr(vector_db, "identifier", None) or getattr(vector_db, "id", None)
    return str(ident or "")


def get_vector_db_id(vector_db) -> str:
    """Stable ID for RAG / vector_io (vector_db_id or OpenAI-style id)."""
    ident = getattr(vector_db, "identifier", None) or getattr(vector_db, "id", None)
    return str(ident or "")


def llamastack_model_is_llm(model) -> bool:
    """Pre-0.6 stack used ``api_model_type``; OpenAI-style 0.6 ``Model`` uses ``custom_metadata['model_type']``."""
    if getattr(model, "api_model_type", None) == "llm":
        return True
    meta = getattr(model, "custom_metadata", None)
    if isinstance(meta, dict) and meta.get("model_type") == "llm":
        return True
    return False


def llamastack_model_id(model) -> str:
    """Model id for chat/completions (legacy ``identifier`` or OpenAI ``id``)."""
    v = getattr(model, "identifier", None) or getattr(model, "id", None)
    return str(v or "")


def _openai_extract_content_value(content) -> str:
    """Normalize ``message.content`` (str, multimodal list, or loose JSON)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                t = item.get("text")
                if isinstance(t, str):
                    parts.append(t)
            else:
                t = getattr(item, "text", None)
                if isinstance(t, str):
                    parts.append(t)
        return "".join(parts)
    return str(content)


def openai_chat_completion_text(resp) -> str:
    """Read assistant text from a ChatCompletion; tolerates missing choices or message (avoids NoneType errors)."""
    choices = getattr(resp, "choices", None) or []
    if not choices:
        return ""
    ch0 = choices[0]
    if ch0 is None:
        return ""
    msg = getattr(ch0, "message", None)
    if msg is None:
        return ""
    text = _openai_extract_content_value(getattr(msg, "content", None))
    if not (text or "").strip():
        extra = getattr(msg, "model_extra", None) or {}
        text = _openai_extract_content_value(extra.get("content"))
    if (text or "").strip():
        return text
    refusal = getattr(msg, "refusal", None)
    if refusal:
        return str(refusal)
    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        return "(Model returned tool calls only; this chat UI shows plain text.)"
    return ""


def openai_chat_completion_debug_hint(resp) -> str:
    """Short diagnostic when the assistant message has no extractable text (e.g. proxy quirks)."""
    lines: list[str] = []
    try:
        d = resp.model_dump(mode="python")
    except Exception:
        return ""
    chs = d.get("choices") or []
    lines.append(f"choices: {len(chs)}")
    if chs:
        c0 = chs[0] or {}
        lines.append(f"finish_reason: {c0.get('finish_reason')!r}")
        m = c0.get("message") or {}
        lines.append(f"message.role: {m.get('role')!r}")
        lines.append(f"message.content type: {type(m.get('content')).__name__}")
        if m.get("refusal"):
            lines.append(f"message.refusal: {m.get('refusal')!r}")
        if m.get("tool_calls"):
            lines.append("message.tool_calls: present")
    if d.get("error"):
        lines.append(f"top-level error: {d.get('error')!r}")
    return "\n".join(lines) if lines else "(no structured diagnostic)"


def get_question_suggestions():
    """
    Load question suggestions from environment variable.
    Returns a dictionary mapping vector DB names to lists of suggested questions.
    """
    try:
        suggestions_json = os.environ.get("RAG_QUESTION_SUGGESTIONS", "{}")
        suggestions = json.loads(suggestions_json)
        return suggestions
    except json.JSONDecodeError:
        st.warning("Failed to parse question suggestions from environment variable.")
        return {}
    except Exception as e:
        st.warning(f"Error loading question suggestions: {str(e)}")
        return {}


def get_suggestions_for_databases(selected_dbs, all_vector_dbs):
    """
    Get combined question suggestions for selected databases.
    
    Args:
        selected_dbs: List of selected vector DB names
        all_vector_dbs: List of all vector DB objects from API
    
    Returns:
        List of tuples (question, source_db_name)
    """
    suggestions_map = get_question_suggestions()
    combined_suggestions = []
    
    if not suggestions_map:
        return []
    
    # Create a mapping from vector_db_name to identifier
    db_name_to_identifier = {
        get_vector_db_name(vdb): get_vector_db_id(vdb)
        for vdb in all_vector_dbs
    }
    
    for db_name in selected_dbs:
        # Get the identifier for this database name
        db_identifier = db_name_to_identifier.get(db_name)
        
        # Try both the identifier and the db_name as keys in the suggestions map
        questions = None
        if db_identifier and db_identifier in suggestions_map:
            questions = suggestions_map[db_identifier]
        elif db_name in suggestions_map:
            questions = suggestions_map[db_name]
        
        if questions:
            for question in questions:
                combined_suggestions.append((question, db_name))
    
    return combined_suggestions


def format_api_connection_error(exc: Exception, endpoint_hint: str | None = None) -> str:
    """
    Short, actionable message for proxy/OpenShift HTML pages and gateway failures.

    Note: llama-stack-client maps HTTP 502/503/504 to InternalServerError (status_code >= 500),
    so the exception *name* is often misleading when the edge returns HTML.
    """
    ep = (endpoint_hint or os.environ.get("LLAMA_STACK_ENDPOINT", "http://localhost:8321")).strip()
    name = type(exc).__name__
    status = getattr(exc, "status_code", None)
    text = f"{name}: {exc}"
    tlow = text.lower()
    htmlish = (
        "<html" in tlow
        or "<style" in tlow
        or "application is not available" in tlow
        or "router did not respond" in tlow
    )
    if htmlish or status in (502, 503, 504):
        parts = [
            f"**HTTP {status or '?'}** from `{ep}` — not a LlamaStack JSON API response. "
            f"The Python client reports **`{name}`** for many 5xx edge responses; check the real status with curl.\n\n",
        ]
        if status == 503 or htmlish:
            parts.append(
                "**503 / HTML** usually means the OpenShift route has no ready backend: "
                "Deployment not ready, pods failing readiness, wrong Service selector or target port, or scale to zero.\n\n"
            )
        parts.append(
            f"Run: `curl -skI {ep.rstrip('/')}/v1/models` — you want **200** and `content-type: application/json`, "
            f"not **503** and `text/html`.\n\n"
            f"Then: `oc get pods -n <ns> -l '…'` / `oc describe route …` / `oc get endpoints` for that Service."
        )
        return "".join(parts)
    if len(text) > 1200:
        return text[:1200] + "…"
    return text
