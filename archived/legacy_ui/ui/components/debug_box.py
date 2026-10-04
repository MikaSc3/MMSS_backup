# -*- coding: utf-8 -*-
"""
Debug box component for displaying workflow status messages.
"""

import streamlit as st
from ui.state import get_activity_messages


def render_debug_box():
    """Render compact workflow activity."""
    
    activity_messages = get_activity_messages()
    
    debug_container = st.container(border=True, height=190)
    
    with debug_container:
        if not activity_messages:
            st.caption("Workflow activity will appear here.")
        else:
            for message in activity_messages[-8:]:
                st.caption(message)
