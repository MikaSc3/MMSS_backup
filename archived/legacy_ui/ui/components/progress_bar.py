# -*- coding: utf-8 -*-
"""
Progress Bar Component for STEP2FFA Workflow

Renders a horizontal progress bar with dots and connectors showing workflow state.
"""

import streamlit as st

PROGRESS_STEPS = [
    "Upload Stepfile",
    "Preprocess Stepfile",
    "Analyse Assembly",
    "Discuss about Assembly",
    "Analyse Monoparts",
    "Generate Assembly Sequence",
    "Discuss about Assembly Sequence",
    "Render Assembly Steps",
    "Analyse Interactions",
    "Assess Fitness for Automation",
    "Generate FFA Report",
    "Discuss / Download Report",
]


def render_progress_bar():
    """
    Render horizontal progress bar with dots and connectors.
    
    - Current step highlighted in orange (#F58220)
    - Completed steps shown in green (#179C7D)
    - Upcoming steps shown in grey (#cbd5e1)
    - Text label shown only under current active step
    """
    current_step = st.session_state.get("progress_step", 0)
    
    # Progress bar styling
    st.markdown("""
    <style>
    .progress-wrapper {
        width: 100%;
        padding: 1.1rem 0 1.25rem 0;
        overflow-x: auto;
        overflow-y: hidden;
        background: #FFFFFF;
        border: 1px solid #D9E2E7;
        border-radius: 12px;
        box-shadow: 0 10px 28px rgba(17, 24, 39, 0.06);
    }
    
    .progress-track {
        display: flex;
        align-items: flex-start;
        gap: 0;
        width: 100%;
        min-width: 920px;
        position: relative;
        padding-top: 1rem;
        padding-right: 0;
    }
    
    .progress-step {
        display: flex;
        flex-direction: column;
        align-items: center;
        position: relative;
        flex: 1 1 0;
        min-width: 78px;
    }
    
    .progress-dot {
        width: 28px;
        height: 28px;
        border-radius: 50%;
        transition: background-color 0.3s ease;
        position: relative;
        z-index: 2;
        flex-shrink: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.9rem;
        font-weight: 760;
        border: 1px solid #B8C4CC;
        background: #FFFFFF;
    }
    
    .progress-dot.active {
        background-color: #F58220;
        border-color: #F58220;
        color: #FFFFFF;
        box-shadow: 0 0 0 4px rgba(245, 130, 32, 0.13);
    }
    
    .progress-dot.completed {
        background-color: #FFFFFF;
        border-color: #179C7D;
        color: #179C7D;
    }
    
    .progress-dot.inactive {
        color: #66737C;
        border-color: #B8C4CC;
    }
    
    .progress-line {
        position: absolute;
        top: 14px;
        left: 50%;
        width: 100%;
        height: 2px;
        background-color: #D9E2E7;
        z-index: 1;
    }

    .progress-line.completed {
        background-color: #179C7D;
    }
    
    .progress-step:last-child .progress-line {
        display: none;
    }
    
    .progress-label {
        font-size: 0.86rem;
        color: #1F2933;
        font-weight: 600;
        text-align: center;
        width: 100%;
        line-height: 1.25;
        margin-top: 0.65rem;
        min-height: 2.5rem;
        word-break: break-word;
        overflow: hidden;
    }
    
    </style>
    """, unsafe_allow_html=True)
    
    # Build progress bar HTML
    steps_html = ""
    for i, step in enumerate(PROGRESS_STEPS):
        is_active = i == current_step
        is_completed = i < current_step
        
        if is_active:
            dot_class = "active"
        elif is_completed:
            dot_class = "completed"
        else:
            dot_class = "inactive"
        
        label_html = f'<div class="progress-label">{step}</div>' if is_active else ""
        line_class = "completed" if is_completed else ""
        dot_text = str(i + 1)

        # Build compact one-line HTML to avoid markdown code-block parsing from indentation.
        steps_html += (
            f'<div class="progress-step">'
            f'<div class="progress-dot {dot_class}">{dot_text}</div>'
            f'<div class="progress-line {line_class}"></div>'
            f'{label_html}'
            f'</div>'
        )
    
    st.markdown(f'<div class="progress-wrapper"><div class="progress-track">{steps_html}</div></div>', unsafe_allow_html=True)
