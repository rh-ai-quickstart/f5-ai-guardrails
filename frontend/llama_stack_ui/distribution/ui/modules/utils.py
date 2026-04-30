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
    Falls back to identifier if vector_db_name attribute is not present.
    
    Args:
        vector_db: Vector database object from API
    
    Returns:
        str: The vector database name
    """
    return getattr(vector_db, 'vector_db_name', vector_db.identifier)


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
        get_vector_db_name(vdb): vdb.identifier 
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


def format_api_connection_error(exc: Exception) -> str:
    """Narrow large HTML bodies (e.g. OpenShift error pages) to a short, actionable message."""
    name = type(exc).__name__
    text = f"{name}: {exc}"
    tlow = text.lower()
    if (
        "<html" in tlow
        or "<style" in tlow
        or "application is not available" in tlow
        or "router did not respond" in tlow
    ):
        ep = os.environ.get("LLAMA_STACK_ENDPOINT", "http://localhost:8321")
        return (
            f"LlamaStack URL ({ep}) returned a web error page (HTML) instead of JSON. "
            "For OpenShift routes (*.apps...), use **https://** (edge TLS) and ensure pods are ready. "
            f"Test: `curl -sk {ep.rstrip('/')}/v1/models` (expect JSON). Error type: {name}"
        )
    if len(text) > 1200:
        return text[:1200] + "…"
    return text
