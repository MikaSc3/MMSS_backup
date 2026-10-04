# -*- coding: utf-8 -*-
"""Footer component with attribution and session metadata."""

from pathlib import Path

import streamlit as st


def render_footer():
    """Render a clean footer without custom boxed markup."""
    session_root = st.session_state.get("session_root")

    st.caption("Fraunhofer IPA & University of Stuttgart")

    if session_root:
        session_path = Path(session_root)
        st.caption(f"Session: {session_path.name}")
