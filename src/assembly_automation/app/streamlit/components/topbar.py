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
        f"""<div class="topbar"><div class="brand-lockup">{brand}
        <span class="brand">Automation Engineering AI-Assistant</span></div>
        <div class="session-name">{session}</div>
        <div><span class="status-dot {'live' if busy else ''}"></span>{status}
        <span class="checkpoint">{checkpoint}</span></div></div>""",
        unsafe_allow_html=True,
    )

