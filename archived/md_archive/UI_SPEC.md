# UI Specification - STEP2FFA Streamlit App

Complete UI/UX specification for the Streamlit-based workflow interface.

---

## 1. Overview

**Framework**: Streamlit (Python-based, rapid prototyping, built-in state management)

**Purpose**: Interactive single-window interface for app_workflow_v2 orchestration

**Entry Point**: 
```bash
streamlit run app.py
```

---

## 2. Layout Architecture

### Main Container (Full Window)

```
┌────────────────────────────────────────────────────────────────────┐
│                     STEP2FFA - Assembly Workflow UI                │
├────────────────────────────────────────────────────────────────────┤
│                          UPLOAD SECTION                             │
│  [📤 Upload STEP File] [Assembly Name: ________] [▶ Start]         │
├────────────────────┬──────────────────────────────────────────────┤
│                    │                                              │
│  CHAT WINDOW       │  IMAGE BOX                                  │
│  (Scrollable)      │  ┌────────────────────────────────────────┐ │
│                    │  │                                        │ │
│  [Agent 1]:        │  │  [Assembly/Step Rendering/FFA Image]  │ │
│  "Analyzing        │  │                                        │ │
│   assembly..."     │  │  (Dynamic - Changes per phase)        │ │
│                    │  │                                        │ │
│  [User]:           │  │  (Carousel if multiple images)         │ │
│  "How rigid is     │  │                                        │ │
│   Part_1?"         │  └────────────────────────────────────────┘ │
│                    │                                              │
│  [Agent 1]:        │  DEBUG BOX (4 lines, overflow scrolls)      │
│  "Part_1 is        │  ┌────────────────────────────────────────┐ │
│   aluminum 6063..."│  │ ✓ Phase 1 complete                   │ │
│                    │  │ ✓ Assembly enriched (v2)             │ │
│  [Phase: Agent 2]  │  │ → Running Phase 2a...                │ │
│  Agent 2: "Ready   │  │ ✓ Part_1 analyzed                    │ │
│   for approval?"   │  └────────────────────────────────────────┘ │
│                    │                                              │
│  [User]: "Yes"     │  Caption:                                   │
│                    │  "STEP2FFA"                                │
│  [Agent 3]:        │                                              │
│  "FFA Assessment   │                                              │
│   Summary: 12/15   │                                              │
│   steps automata..." │                                             │
│                    │                                              │
│  [Autoload Input]  │                                              │
│  [Type Question]   │                                              │
│  [Send]            │                                              │
│                    │                                              │
└────────────────────┴──────────────────────────────────────────────┘
│  📍 FOOTER                                                         │
│  This project was supported by Fraunhofer IPA and University of   │
│  Stuttgart. | Session: 2026-03-25_142356 | Data: /session_root/  │
└────────────────────────────────────────────────────────────────────┘
```

---

## 3. Component Specifications

### 3.1 Upload Section (Top)

**Purpose**: User provides STEP file to start workflow

**Components**:
- File uploader (`.STEP` files only)
- Text input: Assembly name (auto-filled from filename, editable)
- Button: "▶ Start Workflow"
- Status message: "Ready to upload..." → "Processing..." → "Workflow started at 14:23:56"

**Workflow Upon Upload**:

1. **Validation**
   - File extension must be `.STEP`
   - Assembly name cannot be empty
   - Name must be alphanumeric + underscore

2. **Session Creation**
   - Generate timestamp: `YYYY-MM-DD_HHMMSS`
   - Create session folder: `data/sessions/{timestamp}_{assembly_name}/`
   - Create subdirectories: `input`, `preprocessing`, `Agent_txt_files`, `enriched_parts`, `ffa_assessment`
   - Copy STEP file to `session_root/input/{assembly_name}.STEP`
   - Set `st.session_state.session_root = Path(...)`
   - Set `st.session_state.assembly_name = assembly_name`
   - Set `st.session_state.workflow_started = True`

3. **Workflow Trigger**
   - Call `run_app_workflow_v2(session_root, assembly_name, config)`
   - Pass callback to update UI during execution

4. **Status Updates**
   - Display: "✓ Session created: `/data/sessions/2026-03-25_142356_MyAssembly/`"
   - Display: "→ Starting workflow..."

---

### 3.2 Chat Window (Left - 60% width)

**Purpose**: Display all user-agent interactions + system messages

**Features**:
- **Scrollable**: Auto-scroll to bottom after new message
- **Multi-turn History**: Shows complete conversation from all 3 agents
- **Persistent**: Session_state.messages stores all messages
- **User Input Zone**: At bottom

**Message Types**:

```python
{
  "role": "system" | "agent1" | "agent2" | "agent3" | "user",
  "content": string,
  "timestamp": ISO8601,
  "turn": int,
  "phase": "PHASE_1" | "PHASE_2a" | "PHASE_2b" | "AGENT_1" | "AGENT_2_LOOP" | "PHASE_4" | "AGENT_3"
}
```

**Rendering**:

```
System Messages (gray background):
┌─────────────────────────────────────────┐
│ 🔄 Phase 1: Preprocessing...           │
│ 14:23:56                                │
└─────────────────────────────────────────┘

Agent Messages (blue background, left-aligned):
┌─────────────────────────────────────────┐
│ 🤖 Agent 1 (Assembly Analyst)           │
│ "The assembly has 15 parts with complex │
│  interactions. Part_1 (aluminum) serves │
│  as the base component..."              │
│ 14:24:12                                │
└─────────────────────────────────────────┘

User Messages (green background, right-aligned):
                        ┌─────────────────────────────────────────┐
                        │ How rigid is the aluminum housing?      │
                        │ (User) 14:24:45                         │
                        └─────────────────────────────────────────┘

Phase Transitions (yellow background, center):
┌─────────────────────────────────────────┐
│ ✓ Phase 2a complete │ → Agent 2 Loop   │
└─────────────────────────────────────────┘
```

**User Input Area** (Always visible at bottom of chat window):

```
[Auto-complete: previous questions ▼]

What is the automation fitness for step 3?
[📤 Send] [Clear]
```

**Features**:
- Auto-complete suggestions from previous questions
- Button to clear input
- Enter key submits (Ctrl+Enter for multiline)
- Disable input if workflow not running

---

### 3.3 Image Box (Right-Top - 40% width)

**Purpose**: Display visual outputs from workflow in real-time

**Approach**: Auto-detect latest JPG image from entire session folder structure

**Implementation**:

```python
def get_latest_jpg(session_root: Path) -> Path | None:
    """Find most recently created JPG in entire session (all subfolders)"""
    jpgs = list(session_root.rglob("*.jpg"))
    if not jpgs:
        return None
    # Return path with latest modification time
    return max(jpgs, key=lambda p: p.stat().st_mtime)

# In Streamlit component:
image_placeholder = st.empty()

while workflow_running:
    latest_jpg = get_latest_jpg(st.session_state.session_root)
    if latest_jpg:
        with image_placeholder.container():
            st.image(latest_jpg, width=400)
            st.caption(f"Latest: {latest_jpg.name}")
    else:
        with image_placeholder.container():
            st.info("📷 Waiting for first image...")
    
    time.sleep(2)  # Refresh every 2 seconds
```

**Images Shown**:
- Phase 1: Assembly overview (from stepparser)
- Phase 2a: Assembly/monopart renderings (as generated)
- Phase 2b: Step renderings (from sequence generation)
- Phase 4: Final step renderings (high-quality)
- Agent 3: Any FFA-related visuals

**Features**:
- No phase-based logic needed
- Automatically shows newest image regardless of where it's stored
- Auto-refresh every 2 seconds
- Fallback message if no images exist yet
- Uses filesystem modification time (reliable)

---

### 3.4 Debug Box (Right-Middle - 40% width)

**Purpose**: Show workflow activity indicator (something is happening)

**Behavior**:
- **Max 4 lines** visible
- **Overflow**: Auto-scroll to bottom (oldest messages disappear, FIFO queue)
- **Message Types**: Only status updates (✓ = completed, → = running, ✗ = error)
- **Not shown**: Node outputs, JSON data, debug details

**Example Content**:

```
✓ Phase 1 complete
✓ Assembly enriched
→ Analyzing monoparts...
```

(After a few seconds):

```
✓ Assembly enriched
→ Analyzing monoparts...
✓ BOM generated
→ Generating sequence...
```

**Implementation**:

```python
# Initialize in session state
if "debug_messages" not in st.session_state:
    st.session_state.debug_messages = []

# Create placeholder
debug_placeholder = st.empty()

# In workflow callback:
def update_debug_message(msg: str):
    """Add status message to debug box (FIFO: max 4 lines)"""
    st.session_state.debug_messages.append(msg)
    if len(st.session_state.debug_messages) > 4:
        st.session_state.debug_messages.pop(0)  # Remove oldest
    
    # Render updated box
    with debug_placeholder.container():
        st.text("\n".join(st.session_state.debug_messages))
```

**Example Callback Messages**:
- `"✓ Stepparser complete"`
- `"→ Phase 2a enrichment running"`
- `"✓ Assembly analysis done"`
- `"→ Generating sequence..."`
- `"✓ Sequence generated"`
- `"→ Phase 4: FFA assessment..."`
- `"✓ FFA assessment complete"`
- `"✗ ERROR: Agent response failed"`

**Error Handling**:

```
✗ ERROR: Stepparser failed
→ Retrying...
✓ Stepparser complete
```

---

### 3.5 Caption Section (Right-Side, centered)

**Content**: 
```
STEP2FFA
```

**Styling**: 
- Large, bold font (h3)
- Centered
- Gray text (#666)
- Always visible below image box

---

### 3.6 Footer (Bottom)

**Content**:
```
📍 This project was supported by Fraunhofer IPA and University of Stuttgart.
Session: 2026-03-25_142356 | Data: /data/sessions/2026-03-25_142356_MyAssembly
```

**Features**:
- Always visible
- Small font
- Light gray background
- Right-aligned timestamp + session path (click to copy)
- Links: [Documentation] [GitHub] [Report Issue]

---

## 4. State Management (Streamlit Session State)

```python
st.session_state keys:

# Upload & Session
"upload_step_file": UploadedFile | None
"assembly_name": str  # e.g., "MyAssembly"
"session_root": Path  # e.g., Path("data/sessions/2026-03-25_142356_MyAssembly/")
"workflow_started": bool
"workflow_complete": bool

# Messages & UI
"messages": list[dict]  # Chat history
"debug_messages": list[str]  # Last 4 status messages (FIFO queue)

# Workflow State
"workflow_phase": str  # "PHASE_1", "AGENT_2_LOOP", etc.
"workflow_state": dict  # Complete LLM state from app_workflow_v2
"user_approval_pending": bool  # For Agent 2 loop

# Note: Images are auto-detected from filesystem every 2 seconds
# No need to store current_image_path or track step numbers
```

---

## 5. Workflow Integration

### 5.1 Session Root Structure

When STEP file uploaded, create:

```
data/sessions/{timestamp}_{assembly_name}/
├── input/
│   └── {assembly_name}.STEP                    ← Uploaded file
├── preprocessing/
│   └── stepparser/
│       └── {assembly_name}/                    ← Stepparser output
│           ├── assembly_{assembly_name}/
│           ├── Part_*/
│           ├── images/
│           ├── BOM.json
│           └── Overview_Stepparser.json
├── Agent_txt_files/                            ← Agent conversations
│   ├── Agent1_conversation.txt
│   ├── Agent2_validation_iteration_1.txt
│   ├── Agent2_validation_iteration_2.txt (if loop)
│   └── Agent3_ffa_explanation.txt
├── enriched_parts/                             ← Phase 2a outputs
│   ├── Part_1-Metadata_enriched.json
│   └── Part_*_Data_enriched_merged.json
├── assembly_sequence_run1/                     ← Phase 2b outputs
│   ├── assembly_sequence.json
│   ├── sequence_renderings/
│   │   ├── step_01_isometric.png
│   │   ├── step_01_front.png
│   │   └── ... (5 images × steps)
│   └── remarks.txt (if Agent 2 feedback)
├── ffa_assessment/                             ← Phase 4 outputs
│   └── ffa_assessment.json
├── logs/
│   └── workflow.log                            ← Complete execution log
└── {assembly_name}-Metadata_assembly_enriched.json (v1 → v2)
└── {assembly_name}_BOM_enriched.json
```

### 5.2 Workflow Callback Pattern

**Problem**: Streamlit re-runs entire script on every interaction. Need real-time updates.

**Solution**: Use `st.session_state` + streaming output

```python
# In Streamlit app
def run_workflow():
    """Execute workflow with UI callbacks"""
    
    # Callback function that UI can call
    def update_callback(event: dict):
        """Called by workflow to update UI"""
        if event["type"] == "message":
            # Agent or system message
            st.session_state.messages.append({
                "role": event["role"],
                "content": event["content"],
                "timestamp": event.get("timestamp"),
                "phase": event.get("phase")
            })
        elif event["type"] == "status":
            # Status message for debug box (activity indicator)
            update_debug_message(event["content"])
        elif event["type"] == "phase_changed":
            st.session_state.workflow_phase = event["phase"]
        
        # Note: Images are auto-detected from filesystem every 2 seconds
        # No need for explicit image callback
        
        # Force rerun to update UI
        st.rerun()
    
    # Call workflow with callback
    result = run_app_workflow_v2(
        session_root=st.session_state.session_root,
        assembly_name=st.session_state.assembly_name,
        config=config,
        ui_callback=update_callback
    )
    
    st.session_state.workflow_complete = True
    st.session_state.workflow_state = result
```

### 5.3 Agent 2 Loop - User Approval

**Special Handling for Agent 2**:

When Agent 2 requires approval:

```python
# In chat window, show special UI:
st.info("⏸️ Sequence Generated - Awaiting Your Approval")

# Display current sequence with images
show_current_sequence(st.session_state.last_sequence_data)

col1, col2 = st.columns(2)
with col1:
    if st.button("✅ Approve Sequence"):
        st.session_state.user_approval_pending = False
        st.session_state.messages.append({
            "role": "user",
            "content": "Approved",
            "timestamp": datetime.now()
        })
        # Continue workflow
        st.rerun()

with col2:
    feedback = st.text_area("Feedback for improvement:")
    if st.button("↩️ Request Changes"):
        st.session_state.messages.append({
            "role": "user", 
            "content": f"Feedback: {feedback}",
            "timestamp": datetime.now()
        })
        # Workflow regenerates with remarks
        st.rerun()
```

---

## 6. Message Flow Examples

### Example 1: Simple Workflow (No Agent 2 Loop)

```
[Upload MyAssembly.STEP] → Session created

PHASE_1 START:
  System: "🔄 Phase 1: Preprocessing..."
  Debug:  "→ Running stepparser..."
  Debug:  "✓ Stepparser complete"
  
PHASE_2a START:
  System: "🔄 Phase 2a: Assembly Enrichment..."
  Agent1: "The assembly consists of 15 parts..."
  Debug:  "→ Running Phase 2a LLM analysis..."
  Debug:  "✓ Part_1 analyzed"
  Debug:  "✓ Part_2 analyzed"
  ...
  Debug:  "✓ BOM generated"

AGENT_2_LOOP START (Iteration 1):
  System: "🔄 Agent 2: Sequence Validation"
  Agent2: "Generated assembly sequence with 15 steps. Ready for review?"
  [Image: Step 1 rendering]
  
  User: "Looks good, approve"
  
  Agent2: "✓ Approved. Proceeding to FFA assessment."

PHASE_4 START:
  System: "🔄 Phase 4: Rendering + FFA Assessment..."
  Debug:  "→ Rendering step 1/15..."
  Debug:  "✓ Rendering complete"
  Debug:  "→ Analyzing interactions..."
  Debug:  "✓ Interaction analysis complete"
  Debug:  "→ FFA assessment..."
  Debug:  "✓ FFA assessment complete"

AGENT_3 START (Final):
  System: "🔄 Agent 3: FFA Explainer"
  Agent3: "AUTOMATION FITNESS ASSESSMENT SUMMARY
            This assembly has 12/15 automatable steps.
            
            Key Challenges:
            1. Step 2 (press-fit): Requires precise positioning
            2. Step 8 (surface gluing): Sensitive to orientation
            
            Key Opportunities:
            1. Redesign Step 2 bore to allow loose fit
            2. Add fiducial markers for Step 8 orientation"
  
  User: "Can Step 2 be redesigned easily?"
  
  Agent3: "Yes. The current ±0.1mm tolerance drives the challenge.
           Relaxing to ±0.5mm would enable robot insertion.
           Trade-off: Slight loss of assembly precision."

WORKFLOW COMPLETE ✓
```

### Example 2: With Agent 2 Loop (User Feedback)

```
[Previous steps same as above...]

AGENT_2_LOOP START (Iteration 1):
  System: "🔄 Agent 2: Sequence Validation"
  Agent2: "Generated assembly sequence with 15 steps. Ready for review?"
  [Image: Step 1 rendering]
  
  User: "Step 2 should come after Step 3"
  
  Agent2: "Understood. Regenerating sequence with your feedback..."

PHASE_2b REGENERATION (Iteration 2):
  System: "🔄 Phase 2b: Sequence Regeneration (User Feedback)"
  Debug:  "→ Regenerating with remarks..."
  Debug:  "✓ Sequence regenerated (Iteration 2)"

AGENT_2_LOOP (Iteration 2):
  Agent2: "Updated sequence: Step 3 now comes before Step 2.
           Does this look correct?"
  [Image: Updated Step 1 rendering]
  
  User: "Perfect, approve"
  
  Agent2: "✓ Approved. Proceeding to FFA assessment."

[Continue to Phase 4 as above...]
```

---

## 7. Technical Implementation Notes

### File Organization

```
apa_from_cad/
├── ui/
│   ├── app.py                    ← Main Streamlit app
│   ├── components/
│   │   ├── chat.py              ← Chat window component
│   │   ├── image_box.py         ← Image display component
│   │   ├── debug_box.py         ← Debug output component
│   │   └── upload_section.py    ← Upload control
│   ├── callbacks.py             ← Workflow callbacks for UI updates
│   ├── state_manager.py         ← Session state utilities
│   └── styles.css               ← Streamlit custom styling (if needed)
└── app_workflow_v2.py           ← Existing workflow (modified for callbacks)
```

### Key Dependencies

```
streamlit>=1.28.0
streamlit-chat>=0.1.0          # Optional: for better chat rendering
pillow>=9.0.0                  # Image handling
pyyaml>=6.0                    # Config loading
```

### Streamlit Config

```toml
# .streamlit/config.toml

[theme]
primaryColor = "#1f77b4"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f0f2f6"
textColor = "#262626"
font = "sans serif"

[client]
showErrorDetails = true
toolbarMode = "viewer"

[logger]
level = "info"

[server]
port = 8501
headless = true
```

---

## 8. Running the App

**Start**:
```bash
cd c:\Users\KAB-MS\VSCode\apa_from_cad
streamlit run ui/app.py
```

**Open**: http://localhost:8501

**Config**:
```bash
streamlit run ui/app.py --config .streamlit/config.toml
```

---

## 9. Future Enhancements

- [ ] Dark mode toggle
- [ ] Export session as PDF report
- [ ] Batch processing (multiple assemblies)
- [ ] Session history browser
- [ ] Live progress bar for workflow phases
- [ ] Side-by-side sequence comparison (Iteration 1 vs Iteration N)
- [ ] 3D viewer for renderings (if interactive 3D desirable)
- [ ] Real-time cost estimation (automation vs manual)

---

## 10. Accessibility & Responsiveness

- **Responsive**: Works on laptop (1920px), tablet, desktop monitors
- **Keyboard Navigation**: Tab through inputs, Enter to submit
- **Screen Readers**: Use semantic HTML + ARIA labels where needed
- **Color Blind**: Use icons + text, not color alone for status
- **Performance**: Lazy-load images, max image width 800px

---

## Summary

| Component | Type | Purpose |
|-----------|------|---------|
| Upload Section | Control | User selects STEP file, starts workflow |
| Chat Window | Display | Shows all agent-user interactions (all 3 agents) |
| Image Box | Display | Shows visual outputs (assembly → steps → FFA) |
| Debug Box | Display | Shows status updates (max 4 lines, scrolling) |
| Caption | Display | "STEP2FFA" label |
| Footer | Info | Attribution + session metadata |

All components update in real-time as workflow executes.

