from __future__ import annotations

import base64
from pathlib import Path
from typing import Any


def _logo_data_uri() -> str | None:
    path = Path(__file__).resolve().parents[5] / "logos" / "HB.png"
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return None
    return f"data:image/png;base64,{encoded}"


def render_topbar(st: Any, snapshot: Any, *, busy: bool) -> None:
    status = "RUNNING" if busy else (snapshot.workflow_status.upper() if snapshot else "READY")
    checkpoint = snapshot.checkpoint.replace("_", " ").upper() if snapshot else "NO SESSION"
    session = (snapshot.session_id if snapshot and snapshot.workflow_status != "draft"
               else "" if snapshot else "Upload a STEP file to begin")
    logo = _logo_data_uri()
    brand = (f'<img class="company-logo" src="{logo}" alt="HiTROTEC BUCHER">'
             if logo else '<span class="brand-mark">FfA</span>')
    
    st.markdown(
        """
        <style>
            .topbar {
                font-family: Arial, Helvetica, sans-serif;
                font-size: 16px;
            }

            .topbar .brand {
                font-family: "Rajdhani", Arial, sans-serif;
                font-size: 18px;
                font-weight: 900;
                white-space: nowrap;
            }

            .topbar .extra-text {
                font-family: "Calibri", Arial, sans-serif;
                font-size: 12px;
                font-weight: 900;
                white-space: nowrap;
            }

            .topbar .session-name {
                font-size: 10px;
            }

            .topbar .checkpoint {
                font-size: 12px;
            }

            .topbar {
                display: flex;
                align-items: center;
                flex-wrap: nowrap;
            }

            .topbar .topbar-status {
                display: flex;
                align-items: center;
                gap: 8px;
                flex: 0 0 auto;
                margin-left: auto;
                white-space: nowrap;
            }

            .topbar .session-name {
                flex: 1 1 0;
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""<div class="topbar"><div class="brand-lockup">{brand}
        <span class="brand">Industrial Automation Assistant</span></div>
        <div class="extra-text">Beta V0.3 -Built by Mika Schmid</div>
        <div class="session-name">{session}</div>
        <div><span class="status-dot {'live' if busy else ''}"></span>{status}
        <span class="checkpoint">{checkpoint}</span></div></div>""",
        unsafe_allow_html=True,
    )

