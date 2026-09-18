# STEP2FFA Streamlit UI

Interactive web interface for assembly workflow orchestration.

## Quick Start

```bash
# Make sure venv is activated
cd c:\Users\KAB-MS\VSCode\apa_from_cad

# Install Streamlit (if not already installed)
pip install streamlit

# Run the app
streamlit run ui/app.py
```

The app will open at: **http://localhost:8501**

---

## Architecture

### Fixed Layout

```
┌─────────────────────────────────────────────────┐
│  📤 Upload  | Name _______ | ▶ Start            │
├─────────────────────┬───────────────────────────┤
│ 💬 Chat             │ 🖼️ Image Box             │
│ (scrollable)        │ (latest .jpg)            │
│                     │                          │
│                     │ STEP2FFA                 │
│                     │                          │
│                     │ 📊 Debug (4 lines)       │
│                     │                          │
├─────────────────────┴───────────────────────────┤
│ Footer: Fraunhofer IPA + University of Stuttgart│
└─────────────────────────────────────────────────┘
```

### Components

- **upload_section**: File upload + assembly name input
- **chat_window**: Multi-turn conversation display + user input
- **image_box**: Latest JPG auto-detected from session folders
- **debug_box**: Last 4 status messages (activity indicator)
- **footer**: Attribution + session info

### Threading Model

```
Main Thread (Streamlit):
  ├─ Renders fixed layout
  ├─ Auto-rerun every 2 seconds
  └─ Reads st.session_state (non-blocking)

Worker Thread:
  ├─ Runs workflow in background
  ├─ Calls ui_callback to update session_state
  └─ Never touches st.* directly
```

### State Management

All state in `st.session_state`:
- `session_root`: Path to session directory
- `assembly_name`: User-provided assembly name
- `messages`: Chat history
- `debug_messages`: Last 4 status messages (FIFO)
- `workflow_phase`: Current phase
- `workflow_started`: Bool
- `workflow_complete`: Bool
- `workflow_error`: Error message if failed

---

## Workflow Integration

When STEP file uploaded:

1. **Session Creation**
   - Generate timestamp: `2026-03-25_142356`
   - Create folder: `data/sessions/{timestamp}_{assembly_name}/`
   - Create subdirectories: input, preprocessing, Agent_txt_files, enriched_parts, ffa_assessment
   - Copy STEP file to `session_root/input/{assembly_name}.STEP`

2. **Workflow Start** (in background thread)
   - Call `run_app_workflow_v2()` with `ui_callback`
   - Workflow emits events: "status", "message", "phase_changed", "error", "complete"
   - UI updates `st.session_state` in real-time

3. **UI Updates**
   - Every 2 seconds, Streamlit re-runs and reads updated session_state
   - Chat messages appear as they arrive
   - Debug box shows last 4 status messages
   - Image box auto-scans and displays latest JPG
   - No blocking, no terminal wait

---

## Auto-Refresh Mechanism

```python
# In app.py main loop:
while True:
    render_all_components()  # Read from st.session_state
    time.sleep(2)
    st.rerun()  # Re-run app to pick up new state
```

This avoids blocking and allows UI to remain interactive.

---

## File Structure

```
ui/
├── app.py                    ← Main Streamlit app (entry point)
├── state.py                  ← Session state management
├── workflow_runner.py        ← Threaded workflow executor
└── components/
    ├── __init__.py
    ├── chat.py              ← Chat window
    ├── image_box.py         ← Image display
    ├── debug_box.py         ← Status messages
    ├── upload.py            ← Upload (placeholder)
    └── footer.py            ← Footer with attribution
```

---

## Troubleshooting

### Chat messages not appearing
- Check `st.session_state.messages` in browser console
- Verify workflow callback is being called
- Check worker thread didn't crash (see terminal)

### Images not showing
- Verify `.jpg` files are being created in session folder
- Check image_box.py `_get_latest_jpg()` logic
- Look at folder: `session_root/preprocessing/stepparser/*/images/`

### Workflow hangs
- Usually means Agent is waiting for input (should not happen with threading)
- Check if workflow thread exited with error
- Look at terminal output for exceptions

### Streamlit rerun too slow
- Reduce `time.sleep(2)` to faster interval if needed
- Or use `st.spinner()` instead of periodic rerun

---

## Next Steps

- [ ] Test upload + threading
- [ ] Test multi-turn chat
- [ ] Test Agent 2 approval flow
- [ ] Test image carousel
- [ ] Add error recovery
- [ ] Add session history browser
- [ ] Add batch processing

---

## Run Command

```bash
streamlit run ui/app.py
```

or with config:

```bash
streamlit run ui/app.py --config .streamlit/config.toml
```
