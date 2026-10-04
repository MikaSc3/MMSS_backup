from __future__ import annotations

from typing import Any, Callable


def render_chat(st: Any, snapshot: Any, *, busy: bool,
                on_message: Callable[[str], None], pending_message: str | None = None,
                pre_session_messages: list[dict[str, str]] | None = None) -> None:
    messages = list(snapshot.messages if snapshot else ())
    for introduction in reversed(pre_session_messages or []):
        if introduction.get("role") != "assistant":
            continue
        if not any(message.get("role") == "assistant"
                   and message.get("content") == introduction.get("content")
                   for message in messages):
            messages.insert(0, introduction)
    visible_messages = messages[-40:]
    pending_is_persisted = any(message.get("role") == "user"
                               and message.get("content") == pending_message
                               for message in visible_messages[-6:])
    if pending_message and not pending_is_persisted:
        visible_messages.append({"role": "user", "content": pending_message,
                                  "pending": "true"})
    # ``st.bottom`` always spans the page. Keep the composer in this column so
    # the reading area and input share one visual boundary and width.
    with st.container(height=400, border=False, key="dialogue_history", autoscroll=True):
        if not visible_messages:
            st.info("FfA Navigator is getting ready...")
        for message in visible_messages:
            role = "user" if message.get("role") == "user" else "assistant"
            with st.chat_message(role):
                st.markdown(message.get("content", ""))
                if message.get("pending"): st.caption("Sending…")
    with st.container(border=False, key="chat_composer"):
        message = st.chat_input("Message the workflow agent…",
                                disabled=busy or snapshot is None,
                                submit_mode="disable")
    if message:
        on_message(message)
