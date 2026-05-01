# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the terms described in the LICENSE file in
# the root directory of this source tree.

import asyncio
import asyncpg
import os
import pandas as pd
import streamlit as st
import traceback

from llama_stack_ui.distribution.ui.modules.utils import get_vector_db_id, get_vector_db_name, data_url_from_file
from llama_stack_ui.distribution.ui.modules.api import (
    active_llama_stack_client,
    list_vector_catalog,
    rag_tool_insert,
    rag_tool_query,
    register_vector_db,
)


def _vector_db_row_dict(v):
    to_dict = getattr(v, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    model_dump = getattr(v, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    return {}


def vector_dbs():
    """
    Inspect available vector databases and display details for the selected one.
    Now supports creating new vector databases.
    """
    st.header("Vector Databases")
    
    # Initialize session state for creation status messages
    if "creation_status" not in st.session_state:
        st.session_state["creation_status"] = None
    if "creation_message" not in st.session_state:
        st.session_state["creation_message"] = ""
    
    # Initialize session state for selected vector database
    # This persists the selection when navigating away and back to this page
    if "selected_vector_db" not in st.session_state:
        st.session_state["selected_vector_db"] = ""
    
    # Initialize the widget key to match our tracked selection
    # This ensures the selectbox displays the correct value on page load
    if "vector_db_selector" not in st.session_state:
        st.session_state["vector_db_selector"] = st.session_state["selected_vector_db"]
    
    # Initialize newly created VDB tracker
    if "newly_created_vdb" not in st.session_state:
        st.session_state["newly_created_vdb"] = None
    
    # Show status messages at the top level (before dropdown)
    if st.session_state["creation_status"] == "success":
        st.success(st.session_state["creation_message"])
        # Clear the message after showing it
        st.session_state["creation_status"] = None
        st.session_state["creation_message"] = ""
    elif st.session_state["creation_status"] == "error":
        st.error(st.session_state["creation_message"])
        # Clear the message after showing it  
        st.session_state["creation_status"] = None
        st.session_state["creation_message"] = ""
    
    # Fetch all vector databases
    vdb_list = list_vector_catalog(active_llama_stack_client())
    
    # Build dropdown options based on whether databases exist
    dropdown_options = []
    vdb_info = {}
    
    if vdb_list:
        # When databases exist: list actual DBs first, then "Create New" LAST
        existing_vdbs = {get_vector_db_name(v): _vector_db_row_dict(v) for v in vdb_list}
        dropdown_options.extend(list(existing_vdbs.keys()))
        dropdown_options.append("Create New")  # Add "Create New" as LAST item
        vdb_info = existing_vdbs
    else:
        # When NO databases exist: only show "Create New"
        dropdown_options = ["Create New"]
    
    # Sync session state for widget - ensure it shows the right value
    # Priority 1: If a database was just created, auto-select it (highest priority)
    if st.session_state["newly_created_vdb"]:
        newly_created_name = st.session_state["newly_created_vdb"]
        if newly_created_name in dropdown_options:
            # Update both session variables to sync state
            st.session_state["selected_vector_db"] = newly_created_name
            st.session_state["vector_db_selector"] = newly_created_name
            st.session_state["newly_created_vdb"] = None
    # Priority 2: Use the previously selected database from session if it still exists
    elif st.session_state["selected_vector_db"] and st.session_state["selected_vector_db"] in dropdown_options:
        # Sync widget state with our tracked state
        st.session_state["vector_db_selector"] = st.session_state["selected_vector_db"]
    # Priority 3: If no saved selection or saved selection doesn't exist, use smart default
    else:
        if vdb_list:
            # When databases exist: default to FIRST actual database (not "Create New")
            first_db = dropdown_options[0]  # First item is first actual database
            st.session_state["selected_vector_db"] = first_db
            st.session_state["vector_db_selector"] = first_db
        else:
            # When NO databases exist: default to "Create New"
            st.session_state["selected_vector_db"] = "Create New"
            st.session_state["vector_db_selector"] = "Create New"
    
    # Vector database selection dropdown with persistent selection
    # Using key parameter to bind directly to session state - NO index parameter to avoid conflicts
    def on_vector_db_change():
        """Callback to update session state when selection changes"""
        st.session_state["selected_vector_db"] = st.session_state["vector_db_selector"]
    
    selected_vector_db = st.selectbox(
        "Select a vector database", 
        dropdown_options,
        key="vector_db_selector",  # Key binds to session state (session state controls the value)
        on_change=on_vector_db_change,  # Callback updates our tracking variable
        help="Your selection will be remembered when you navigate to other pages"
    )
    
    # Ensure session state is updated (in case callback didn't fire)
    if selected_vector_db != st.session_state["selected_vector_db"]:
        st.session_state["selected_vector_db"] = selected_vector_db
    
    # Get the actual vector database object for API calls (do this before using it)
    selected_vdb_obj = None
    if selected_vector_db and selected_vector_db != "Create New":
        for vdb in vdb_list:
            if get_vector_db_name(vdb) == selected_vector_db:
                selected_vdb_obj = vdb
                break
    
    if selected_vector_db == "Create New":
        # Show vector database creation UI
        _show_create_vector_db_ui()
    elif selected_vector_db and selected_vector_db != "Create New":
        # Show existing documents in the database (heading will show only if documents exist)
        _show_existing_documents_table(selected_vector_db, selected_vdb_obj)
        
        # Add Browse functionality for uploading documents to this database
        st.subheader(f"📁 Upload Documents to '{selected_vector_db}'")
        _show_document_upload_ui(selected_vector_db, selected_vdb_obj)
    # If empty string is selected, show nothing (clean default state)


def _show_create_vector_db_ui():
    """
    Display UI for creating a new vector database.
    """
    st.subheader("Create New Vector Database")
    
    # Initialize session state for creation form
    if "new_vdb_name" not in st.session_state:
        st.session_state["new_vdb_name"] = ""
    
    # Vector database name input
    new_vdb_name = st.text_input(
        "Add New Vector Database",
        value=st.session_state["new_vdb_name"],
        help="Enter a unique name for the new vector database",
        key="new_vdb_name_input"
    )
    
    # Update session state
    st.session_state["new_vdb_name"] = new_vdb_name
    
    # Add button
    if st.button("Add", type="primary", disabled=not new_vdb_name.strip()):
        _create_vector_database(new_vdb_name.strip())


def _create_vector_database(vdb_name):
    """
    Create a new vector database using the LlamaStack API.
    
    Args:
        vdb_name (str): Name for the new vector database
    """
    try:
        # Reset status
        st.session_state["creation_status"] = None
        st.session_state["creation_message"] = ""
        
        # Validate input
        if not vdb_name or not vdb_name.strip():
            st.session_state["creation_status"] = "error"
            st.session_state["creation_message"] = "Vector database name cannot be empty."
            return
            
        # Check for duplicate names
        existing_vdbs = list_vector_catalog(active_llama_stack_client())
        existing_names = [get_vector_db_name(vdb) for vdb in existing_vdbs]
        if vdb_name in existing_names:
            st.session_state["creation_status"] = "error"
            st.session_state["creation_message"] = f"Vector database '{vdb_name}' already exists. Please choose a different name."
            return
        
        # Get vector IO provider
        providers = active_llama_stack_client().providers.list()
        vector_io_provider = None
        for provider in providers:
            if provider.api == "vector_io":
                vector_io_provider = provider.provider_id
                break
                
        if not vector_io_provider:
            st.session_state["creation_status"] = "error"
            st.session_state["creation_message"] = "No vector IO provider found. Cannot create vector database."
            return
        
        # Create the vector database
        with st.spinner(f"Creating vector database '{vdb_name}'..."):
            vector_db = register_vector_db(
                active_llama_stack_client(),
                vector_db_id=vdb_name,
                embedding_dimension=384,
                embedding_model="all-MiniLM-L6-v2",
                provider_id=vector_io_provider,
            )
            
        # Success
        st.session_state["creation_status"] = "success"
        st.session_state["creation_message"] = f"Vector database '{vdb_name}' created successfully!"
        
        # Mark this database to be auto-selected after refresh
        st.session_state["newly_created_vdb"] = vdb_name
        
        # Clear the input field
        st.session_state["new_vdb_name"] = ""
        
        # Trigger page refresh to update the dropdown - this will show the message at the top
        st.rerun()
        
    except Exception as e:
        st.session_state["creation_status"] = "error"
        st.session_state["creation_message"] = f"Error creating vector database: {str(e)}"


def _show_document_upload_ui(vector_db_name, vector_db_obj=None):
    """
    Display UI for uploading documents to an existing vector database.
    
    Args:
        vector_db_name (str): Name of the selected vector database
    """
    # Initialize session state for upload status
    if "upload_status" not in st.session_state:
        st.session_state["upload_status"] = None
    if "upload_message" not in st.session_state:
        st.session_state["upload_message"] = ""
    
    # Show upload status messages
    if st.session_state["upload_status"] == "success":
        st.success(st.session_state["upload_message"])
        # Clear after showing
        st.session_state["upload_status"] = None
        st.session_state["upload_message"] = ""
    elif st.session_state["upload_status"] == "error":
        st.error(st.session_state["upload_message"])
        # Clear after showing
        st.session_state["upload_status"] = None
        st.session_state["upload_message"] = ""
    
    # Initialize session state to track processed files
    upload_key = f"processed_files_{vector_db_name}"
    if upload_key not in st.session_state:
        st.session_state[upload_key] = set()
    
    # File uploader
    uploaded_files = st.file_uploader(
        "Browse and select files to upload (files will upload automatically)",
        accept_multiple_files=True,
        type=["txt", "pdf", "doc", "docx"],
        key=f"uploader_{vector_db_name}",  # Unique key per database
        help="Select one or more documents - they will be uploaded automatically to this vector database"
    )
    
    # Auto-upload when files are selected
    if uploaded_files:
        # Create a unique identifier for this set of files
        file_set_id = frozenset([f.name + str(f.size) for f in uploaded_files])
        
        # Only process if this is a new set of files
        if file_set_id not in st.session_state[upload_key]:
            # Mark as processed IMMEDIATELY before upload to prevent re-triggering
            st.session_state[upload_key].add(file_set_id)
            
            st.info(f"📤 Uploading {len(uploaded_files)} file(s): {', '.join([f.name for f in uploaded_files])}")
            
            # Get the correct database ID for upload
            vector_db_id = (
                get_vector_db_id(vector_db_obj) if vector_db_obj else vector_db_name
            )
            
            # Upload automatically
            _upload_documents_to_database(vector_db_name, uploaded_files, vector_db_id)


def _upload_documents_to_database(vector_db_name, uploaded_files, vector_db_id=None):
    """
    Upload documents to an existing vector database.
    
    Args:
        vector_db_name (str): Name of the target vector database
        uploaded_files: List of uploaded files from Streamlit file uploader
    """
    try:
        # Reset status
        st.session_state["upload_status"] = None
        st.session_state["upload_message"] = ""
        
        if not uploaded_files:
            st.session_state["upload_status"] = "error"
            st.session_state["upload_message"] = "No files selected for upload."
            return
        
        # Convert uploaded files into RAGDocument instances
        with st.spinner(f"Processing {len(uploaded_files)} file(s)..."):
            documents = [
                {
                    "document_id": uploaded_file.name,
                    "content": data_url_from_file(uploaded_file),
                    "metadata": {"source": uploaded_file.name, "type": "uploaded_file"},
                }
                for uploaded_file in uploaded_files
            ]
        
        # Insert documents into the existing vector database
        actual_db_id = vector_db_id or vector_db_name
        with st.spinner(f"Uploading documents to '{vector_db_name}'..."):
            rag_tool_insert(
                active_llama_stack_client(),
                vector_db_id=actual_db_id,
                documents=documents,
                chunk_size_in_tokens=512,
            )
        
        # Success
        st.session_state["upload_status"] = "success"
        st.session_state["upload_message"] = f"Successfully uploaded {len(uploaded_files)} document(s) to '{vector_db_name}'!"
        
        # Trigger refresh to show the success message
        st.rerun()
        
    except Exception as e:
        st.session_state["upload_status"] = "error"
        st.session_state["upload_message"] = f"Error uploading documents: {str(e)}"
        st.rerun()


def _get_documents_from_pgvector(vector_db_id):
    """
    Query pgvector directly to get document IDs stored in the database.
    
    Args:
        vector_db_id (str): The vector database identifier
        
    Returns:
        list: List of unique document IDs, or None if query fails
    """
    try:
        # Get pgvector connection details from environment or defaults
        pg_host = os.environ.get("PGVECTOR_HOST", "pgvector")
        pg_port = os.environ.get("PGVECTOR_PORT", "5432")
        pg_user = os.environ.get("PGVECTOR_USER", "postgres")
        pg_password = os.environ.get("PGVECTOR_PASSWORD", "rag_password")
        pg_database = os.environ.get("PGVECTOR_DB", "rag_blueprint")
        
        async def fetch_documents():
            try:
                # Connect to PostgreSQL
                conn = await asyncpg.connect(
                    host=pg_host,
                    port=pg_port,
                    user=pg_user,
                    password=pg_password,
                    database=pg_database
                )
                
                # Query for unique document IDs from the document JSONB column
                # The vector_db_id is used as the table name with underscores replacing hyphens
                table_name = f"vs_{vector_db_id.replace('-', '_')}"
                
                # Query chunk_metadata.source where LlamaStack stores the filename
                # Fall back to auto-generated document_id if source is null
                query = f"""
                    SELECT DISTINCT 
                        COALESCE(
                            NULLIF(document->'chunk_metadata'->>'source', 'null'),
                            document->'metadata'->>'document_id'
                        ) as document_id
                    FROM {table_name}
                    WHERE document->'metadata'->>'document_id' IS NOT NULL
                    ORDER BY document_id
                """
                
                queries = [query]
                
                doc_ids = []
                for query in queries:
                    try:
                        rows = await conn.fetch(query)
                        if rows:
                            doc_ids = [row['document_id'] for row in rows if row['document_id']]
                            if doc_ids:
                                break
                    except Exception as e:
                        continue  # Try next query pattern
                
                await conn.close()
                return doc_ids if doc_ids else None
                
            except Exception as e:
                return None
        
        # Run the async function
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(fetch_documents())
        
    except ImportError:
        # asyncpg not available
        return None
    except Exception as e:
        return None


def _delete_document_from_pgvector(vector_db_id, filename):
    """
    Delete a document and all its chunks/embeddings from pgvector.
    
    Args:
        vector_db_id (str): The vector database identifier
        filename (str): The filename/source to delete
        
    Returns:
        tuple: (success: bool, deleted_count: int, error_message: str)
    """
    try:
        # Get pgvector connection details from environment or defaults
        pg_host = os.environ.get("PGVECTOR_HOST", "pgvector")
        pg_port = os.environ.get("PGVECTOR_PORT", "5432")
        pg_user = os.environ.get("PGVECTOR_USER", "postgres")
        pg_password = os.environ.get("PGVECTOR_PASSWORD", "rag_password")
        pg_database = os.environ.get("PGVECTOR_DB", "rag_blueprint")
        
        async def delete_document():
            try:
                # Connect to PostgreSQL
                conn = await asyncpg.connect(
                    host=pg_host,
                    port=pg_port,
                    user=pg_user,
                    password=pg_password,
                    database=pg_database
                )
                
                # The vector_db_id is used as the table name with underscores replacing hyphens
                table_name = f"vs_{vector_db_id.replace('-', '_')}"
                
                # Delete all chunks where the source matches the filename
                query = f"""
                    DELETE FROM {table_name}
                    WHERE document->'chunk_metadata'->>'source' = $1
                """
                
                result = await conn.execute(query, filename)
                
                await conn.close()
                
                # Parse the result to get the number of deleted rows
                # Result format is like "DELETE 5" where 5 is the number of rows
                deleted_count = int(result.split()[-1]) if result else 0
                
                return True, deleted_count, None
                
            except Exception as e:
                return False, 0, str(e)
        
        # Run the async function
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(delete_document())
        
    except ImportError:
        return False, 0, "asyncpg module not available"
    except Exception as e:
        return False, 0, str(e)


def _show_existing_documents_table(vector_db_name, vector_db_obj=None):
    """
    Display information about documents in the selected vector database.
    
    Args:
        vector_db_name (str): Display name of the selected vector database
        vector_db_obj: The actual vector database object with identifier
    """
    try:
        # Get the correct vector database ID
        if vector_db_obj:
            vector_db_id = get_vector_db_id(vector_db_obj)
        else:
            vector_db_id = vector_db_name
        
        # Initialize session state for deletion status
        if "delete_status" not in st.session_state:
            st.session_state["delete_status"] = None
        if "delete_message" not in st.session_state:
            st.session_state["delete_message"] = ""
        
        # Show deletion status messages (before checking documents, so last delete shows)
        if st.session_state["delete_status"] == "success":
            st.success(st.session_state["delete_message"])
            st.session_state["delete_status"] = None
            st.session_state["delete_message"] = ""
        elif st.session_state["delete_status"] == "error":
            st.error(st.session_state["delete_message"])
            st.session_state["delete_status"] = None
            st.session_state["delete_message"] = ""
        
        with st.spinner("Checking for documents..."):
            # First, try to get document list from pgvector directly
            document_ids = _get_documents_from_pgvector(vector_db_id)
            
            if document_ids:
                # Success! We have the actual document filenames
                # Show heading for documents section
                st.subheader(f"📄 Documents in '{vector_db_name}'")
                
                # Display documents in a table with delete buttons
                # Display table header
                col1, col2, col3 = st.columns([0.5, 5, 0.5])
                with col1:
                    st.markdown("**#**")
                with col2:
                    st.markdown("**Filename**")
                with col3:
                    st.markdown("**Del**")
                
                st.divider()
                
                # Display each document in a row with delete button
                for idx, doc_id in enumerate(document_ids, start=1):
                    col1, col2, col3 = st.columns([0.5, 5, 0.5])
                    
                    with col1:
                        st.write(idx)
                    
                    with col2:
                        st.write(doc_id)
                    
                    with col3:
                        delete_key = f"delete_{vector_db_name}_{doc_id}_{idx}"
                        
                        if st.button("✕", key=delete_key, help=f"Delete {doc_id}"):
                            # Delete immediately without confirmation
                            success, deleted_count, error = _delete_document_from_pgvector(
                                vector_db_id,
                                doc_id
                            )
                            
                            if success:
                                st.session_state["delete_status"] = "success"
                                st.session_state["delete_message"] = f"✅ Successfully deleted '{doc_id}' ({deleted_count} chunk(s) removed)"
                            else:
                                st.session_state["delete_status"] = "error"
                                st.session_state["delete_message"] = f"❌ Failed to delete '{doc_id}': {error}"
                            
                            st.rerun()
                
            else:
                # Fallback: Try a simple query to see if documents exist
                try:
                    rag_response = rag_tool_query(
                        active_llama_stack_client(),
                        content="document",
                        vector_db_ids=[vector_db_id],
                    )
                    
                    # Check if we got content back (indicates documents exist)
                    has_content = hasattr(rag_response, 'content') and rag_response.content and len(str(rag_response.content).strip()) > 0
                    
                    if has_content:
                        content_length = len(str(rag_response.content))
                        
                        # Show heading for documents section
                        st.subheader(f"📄 Documents in '{vector_db_name}'")
                        
                        # Show that documents exist
                        st.success(f"✅ Documents are present in this vector database")
                        st.info(f"📊 Retrieved {content_length} characters of content from the database")
                        
                        # Show a preview of the content
                        with st.expander("📄 Content Preview", expanded=False):
                            preview_text = str(rag_response.content)[:500]
                            if len(str(rag_response.content)) > 500:
                                preview_text += "..."
                            st.text(preview_text)
                        
                        # Explain the limitation
                        st.warning("""
                        **Note:** Unable to retrieve document names directly. The documents exist but 
                        pgvector query is not available. To see which specific documents were uploaded:
                        
                        - Remember the filenames you uploaded
                        - Check the upload success messages
                        - Query the database with specific search terms to verify content
                        """)
                        
                        # Provide a test query interface
                        st.subheader("🔍 Test Document Search")
                        test_query = st.text_input(
                            "Enter a search query to test document retrieval:",
                            placeholder="e.g., 'security policy' or 'F5'",
                            key=f"test_query_{vector_db_id}"
                        )
                        
                        if test_query:
                            try:
                                test_response = rag_tool_query(
                                    active_llama_stack_client(),
                                    content=test_query,
                                    vector_db_ids=[vector_db_id],
                                )
                                
                                if test_response.content:
                                    st.success(f"✅ Found relevant content ({len(test_response.content)} characters)")
                                    with st.expander("View Retrieved Content"):
                                        st.text(test_response.content)
                                else:
                                    st.info("No content found for this query")
                            except Exception as e:
                                st.error(f"Query error: {str(e)}")
                    # else: Database is empty - no need to show obvious message, upload section is below
                        
                except Exception as e:
                    st.error(f"Error checking database: {str(e)}")
                    st.info("Unable to query the database. It may be empty or inaccessible.")
                
    except Exception as e:
        st.error(f"Error loading document information: {str(e)}")
        with st.expander("Error Details"):
            st.code(traceback.format_exc())
