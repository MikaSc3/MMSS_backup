"""Local MarkItDown conversion and Streamlit interaction smoke checks.

Run: python scripts/check_document_ui_env.py
"""

from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory


def check_markitdown() -> None:
    from markitdown import MarkItDown

    with TemporaryDirectory() as directory:
        source = Path(directory) / "sample.html"
        source.write_text(
            "<html><body><h1>Environment check</h1>"
            "<p>A <strong>small document</strong> for conversion.</p>"
            "<ul><li>PythonOCC</li><li>Streamlit</li></ul></body></html>",
            encoding="utf-8",
        )
        markdown = MarkItDown().convert(str(source)).text_content
    for expected in ("# Environment check", "**small document**", "PythonOCC", "Streamlit"):
        if expected not in markdown:
            raise AssertionError(f"Converted document is missing {expected!r}: {markdown!r}")
    print(f"PASS MarkItDown {version('markitdown')}: HTML converted to Markdown")
    print(markdown)


def check_streamlit() -> None:
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_string('''
import streamlit as st
st.title("Environment check")
name = st.text_input("Your name", value="Mika")
if st.button("Check"):
    st.success(f"Hello {name}!")
''').run(timeout=20)
    if app.exception:
        raise AssertionError(f"Streamlit startup failed: {app.exception}")
    if app.title[0].value != "Environment check":
        raise AssertionError("Streamlit did not render the expected title")
    app.text_input[0].set_value("Tester")
    app.button[0].click().run(timeout=20)
    if app.exception:
        raise AssertionError(f"Streamlit interaction failed: {app.exception}")
    if len(app.success) != 1 or app.success[0].value != "Hello Tester!":
        raise AssertionError("Streamlit did not process the input and button click")
    print(f"PASS Streamlit {version('streamlit')}: app rendering, input, and button click")


def main() -> int:
    failures = 0
    for check in (check_markitdown, check_streamlit):
        try:
            check()
        except Exception as exc:
            failures += 1
            print(f"FAIL {check.__name__}: {type(exc).__name__}: {exc}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
