# -*- coding: utf-8 -*-
"""
Workflow executor with threading support.

Runs the workflow in a background thread to prevent blocking the UI.
Updates session state via thread-safe event queue.
"""

import threading
import queue
from pathlib import Path
from datetime import datetime, timezone
import shutil

import streamlit as st


def run_workflow_threaded(uploaded_file, assembly_name: str, workspace_root: Path):
    """Start workflow in background thread.
    
    Args:
        uploaded_file: Streamlit UploadedFile object
        assembly_name: Name of assembly (e.g., "MyAssembly")
        workspace_root: Path to workspace root
    """
    
    # Get event queue and input queue from session state
    event_queue = st.session_state.get("event_queue")
    input_queue = st.session_state.get("input_queue")
    
    if not event_queue:
        st.error("❌ Session state not initialized")
        return
    
    def put_event(event: dict):
        """Put event in queue (thread-safe)."""
        event_queue.put(event)
    
    def worker_thread():
        """Background thread that runs the workflow."""
        try:
            # Import here to avoid issues
            from scripts.app_workflow_v2 import (
                load_config, setup_session, load_prompt_library,
                run_app_workflow_v2
            )
            
            # Create session directory
            put_event({
                "type": "status",
                "content": "Creating session folder..."
            })
            
            session_dir = workspace_root / "data" / "sessions"
            session_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
            session_root = session_dir / f"{timestamp}_{assembly_name}"
            
            # Create subdirectories
            for subdir in ["input", "preprocessing", "Agent_txt_files", "enriched_parts", "ffa_assessment"]:
                (session_root / subdir).mkdir(parents=True, exist_ok=True)
            
            # Save uploaded STEP file
            input_step_path = session_root / "input" / f"{assembly_name}.STEP"
            with open(input_step_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            # Emit session creation event (includes session_root path)
            put_event({
                "type": "session_created",
                "session_root": str(session_root),
                "assembly_name": assembly_name
            })
            
            # Update session state via main thread (by putting event in queue)
            put_event({
                "type": "message",
                "role": "system",
                "content": f"Session created: {session_root.name}"
            })
            
            # Load configuration
            config = load_config()
            
            # Load prompts
            prompt_library = load_prompt_library()
            
            # Create callback that puts events in queue
            def workflow_callback(event: dict):
                """Callback from workflow - put events in queue."""
                put_event(event)
            
            # Run workflow with callback and input queue
            put_event({
                "type": "message",
                "role": "system",
                "content": f"Starting workflow for {assembly_name}..."
            })
            
            result = run_app_workflow_v2(
                session_root=str(session_root),
                assembly_name=assembly_name,
                config=config,
                prompt_library=prompt_library,
                ui_callback=workflow_callback,
                input_queue=input_queue
            )
            
            put_event({
                "type": "complete"
            })
        
        except Exception as e:
            import traceback
            error_msg = f"{type(e).__name__}: {str(e)}"
            put_event({
                "type": "error",
                "content": error_msg
            })
            print(f"[WORKFLOW ERROR]\n{traceback.format_exc()}")
    
    # Start background thread
    thread = threading.Thread(target=worker_thread, daemon=True)
    thread.start()

