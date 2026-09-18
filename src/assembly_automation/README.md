# Product rebuild

This package is being filled incrementally from the existing implementation.
It does not yet replace the working App V3 launchers.

- `stepparser`: CAD processing and rendering.
- `user_agent`: conversation, document context, and user-facing tools.
- `workflows`: explicit execution definitions, node-local prompts/schemas, shared runtime.
- `data`: session storage, artifacts, revisions, and compatibility.
- `app`: Streamlit and terminal adapters.

The configuration loader and standalone STEP parser are implemented. Run the
parser through `scripts/test_stepparser.py`; its settings live under
`nodes.step_preprocessing` in `configs/appsettingsv3.yaml`. Other workflow nodes
and their prompt/schema selections remain scaffolds until their resources are
extracted. App V3 still uses the existing implementation.

See `docs/reorganize.md` for the source inventory, extraction order, and checks.
