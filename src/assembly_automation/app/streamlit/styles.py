CSS = r"""
<style>
:root {
  --font-tech:"Cascadia Code","Segoe UI Mono",monospace;
  --white:#FFFFFF; --onyx:#0A0A0A; --carbon:#1D1D1D; --gunmetal:#3E3E3E;
  --steel:#2A81BF; --sky:#7EB3D8; --amber:#FFB547;
  --steel-rgb:42,129,191; --sky-rgb:126,179,216; --amber-rgb:255,181,71;
  --ink:var(--carbon); --muted:var(--gunmetal); --line:var(--sky);
  --accent:var(--steel); --accent-soft:var(--sky); --panel:var(--white); --canvas:var(--white);
  --workspace-panel:#FFFFFF; --workspace-border:#D5D9DC; --workspace-radius:6px;
}
.stApp {
  background:radial-gradient(circle at 45% -15%, var(--white) 0, rgba(var(--sky-rgb),.16) 52%, rgba(var(--sky-rgb),.28) 100%);
  color:var(--ink);font-family:var(--font-tech)!important;
}
[data-testid="stHeader"] { height:0!important;min-height:0!important;background:transparent; }
.block-container { max-width:100%; padding:.15rem 1.4rem 1.2rem; }
.topbar {
  display:grid; grid-template-columns:1fr 1.6fr 1fr; align-items:center; gap:1rem;
  border:1px solid var(--line); border-top:3px solid var(--accent);
  background:rgba(255,255,255,.96); box-shadow:0 8px 26px rgba(29,29,29,.10);
  padding:.52rem 1rem; margin-bottom:.5rem;
  font:650 .72rem var(--font-tech); letter-spacing:.08em; color:var(--gunmetal);
}
.brand-mark { color:var(--white); background:var(--steel); padding:.3rem .42rem; margin-right:.6rem; }
.brand-lockup { display:flex;align-items:center;gap:.7rem;min-width:0; }
.company-logo { display:block;width:clamp(108px, 9vw, 148px);height:auto;max-height:2.35rem;object-fit:contain; }
.brand { color:var(--onyx); }
.session-name { overflow:hidden;text-overflow:ellipsis;text-align:center;white-space:nowrap;color:var(--gunmetal); }
.topbar>div:last-child{text-align:right}
.status-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--gunmetal);margin-right:.4rem}
.status-dot.live{background:var(--steel);box-shadow:0 0 0 4px rgba(var(--steel-rgb),.16)}
.checkpoint{margin-left:.7rem;color:var(--steel)}
[data-testid="stVerticalBlockBorderWrapper"] {
  background:var(--white); border:1px solid var(--workspace-border)!important;
  border-radius:var(--workspace-radius)!important;
  box-shadow:0 10px 28px rgba(29,29,29,.08);
}
[data-testid="stExpander"] {
  background:var(--white);border:0!important;
  border-radius:var(--workspace-radius)!important;overflow:hidden;
}
[data-testid="stExpander"] details>summary {
  border-radius:var(--workspace-radius)!important;
  border:1px solid var(--workspace-border)!important;
  background:var(--white)!important;
  font-weight:700!important;
}
[data-testid="stExpander"] details>summary p { font-weight:700!important; }
.st-key-data_upload_expander {
  border:0!important;box-shadow:none!important;
}
.st-key-data_upload_expander details {
  border:0!important;
}
.st-key-data_upload_expander details>summary {
  border:1px solid var(--workspace-border)!important;
  box-shadow:none!important;
}
h4 { color:var(--onyx)!important;font-family:var(--font-tech)!important;letter-spacing:.04em; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color:var(--muted)!important; }
.empty-visual {
  min-height:55vh;display:flex;align-items:center;justify-content:center;
  border:1px dashed var(--sky);color:var(--gunmetal);
  font:650 .78rem var(--font-tech);letter-spacing:.14em;background:rgba(var(--sky-rgb),.12);
  border-radius:var(--workspace-radius);
}
[data-testid="stChatMessage"], .stChatMessage {
  background:var(--white)!important;border:1px solid var(--sky)!important;
  border-radius:var(--workspace-radius);padding:.8rem 1rem!important;
  color:var(--carbon);box-shadow:0 2px 7px rgba(29,29,29,.05);
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]),
.stChatMessage:has([data-testid="stChatMessageAvatarUser"]) {
  background:rgba(var(--sky-rgb),.24)!important;border-color:var(--sky)!important;
}
[data-testid="stChatMessage"] p,
[data-testid="stChatMessage"] li,
[data-testid="stChatMessage"] code {
  color:var(--carbon)!important;overflow-wrap:anywhere;word-break:break-word;max-width:100%;
}
[data-testid="stChatMessage"] { max-width:100%;overflow:hidden; }
[data-testid="stChatMessage"] pre { max-width:100%;overflow-x:auto; }
[data-testid="stChatInput"] {
  width:100%!important;max-width:100%;margin:0!important;overflow:hidden;
  border-radius:var(--workspace-radius)!important;
}
.st-key-chat_composer {
  width:100%!important;padding:.5rem 0 0;
  background:transparent;border-top:0;
}
.st-key-dialogue_panel { max-width:100%; }
.st-key-dialogue_history { min-height:0; }
.part-card-header { color:var(--carbon);line-height:1.4; }
.part-card-name { font-size:1.08rem;font-weight:750; }
.structured-output-header {
  color:var(--onyx);font:750 .9rem/1.2 Arial,Helvetica,sans-serif;
  padding:.25rem 0 .45rem;
}
.st-key-concept_equipment_summary_card .equipment-name,
.st-key-detailed_equipment_summary_card .equipment-name {
  font-size:1.08em;font-weight:700;
}
.st-key-layout_equipment_summary_card [data-testid="stTable"] th {
  text-align:center!important;
}
.st-key-structured-output-header [data-testid="stToggle"] {
  justify-content:flex-end;
}
.st-key-part_summary_card [data-testid="stMetricValue"],
.st-key-assembly_summary_card [data-testid="stMetricValue"],
.st-key-sequence_summary_card [data-testid="stMetricValue"],
.st-key-interaction_summary_card [data-testid="stMetricValue"],
.st-key-ffa_summary_card [data-testid="stMetricValue"] {
  font-size:1.05rem!important;line-height:1.35!important;
}
.st-key-part_summary_card [data-testid="stMetricLabel"],
.st-key-assembly_summary_card [data-testid="stMetricLabel"],
.st-key-sequence_summary_card [data-testid="stMetricLabel"],
.st-key-interaction_summary_card [data-testid="stMetricLabel"],
.st-key-ffa_summary_card [data-testid="stMetricLabel"] {
  font-size:.78rem!important;
}
.overall-ffa-table {
  width:100%;border-collapse:collapse;table-layout:fixed;
  color:var(--carbon);font-size:.8rem;line-height:1.35;
}
.overall-ffa-table th,.overall-ffa-table td {
  padding:.34rem .45rem;text-align:left;vertical-align:top;
  border-top:1px solid rgba(var(--sky-rgb),.45);overflow-wrap:anywhere;
}
.overall-ffa-table th {
  border-top:0;color:var(--gunmetal);font-size:.72rem;font-weight:750;
}
.overall-ffa-table th:nth-child(1),.overall-ffa-table td:nth-child(1) { width:18%; }
.overall-ffa-table th:nth-child(2),.overall-ffa-table td:nth-child(2) { width:24%; }
.overall-ffa-table td.ffa-potential-low {
  background:rgba(174,72,72,.16);box-shadow:inset 3px 0 rgba(150,56,56,.48);
}
.overall-ffa-table td.ffa-potential-medium {
  background:rgba(var(--amber-rgb),.22);box-shadow:inset 3px 0 rgba(196,132,35,.55);
}
.overall-ffa-table td.ffa-potential-high {
  background:rgba(72,145,91,.17);box-shadow:inset 3px 0 rgba(53,120,71,.48);
}
[data-testid="stChatInput"] { border-color:var(--gunmetal)!important;background:var(--white)!important; }
[data-testid="stChatInput"] textarea,
[data-testid="stChatInput"] textarea:focus,
[data-testid="stChatInput"] [contenteditable="true"] {
  color:var(--carbon)!important;background:var(--white)!important;caret-color:var(--steel)!important;
  -webkit-text-fill-color:var(--carbon)!important;
}
[data-testid="stChatInput"] textarea::placeholder { color:var(--gunmetal)!important;opacity:1; }
.stButton button[kind="primary"] { background:var(--steel);color:var(--white);border-color:var(--steel); }
.stButton button[kind="primary"]:hover { background:#236e9f;border-color:#236e9f;color:var(--white); }
.stButton button[kind="secondary"],
.stDownloadButton button {
  color:var(--steel)!important;border-color:var(--steel)!important;
  background:rgba(var(--steel-rgb),.08)!important;
}
.stButton button[kind="secondary"]:hover,
.stDownloadButton button:hover {
  color:var(--white)!important;border-color:var(--steel)!important;
  background:var(--steel)!important;
}
[data-testid="stButtonGroup"] button {
  color:var(--steel)!important;border-color:rgba(var(--steel-rgb),.72)!important;
  background:rgba(var(--steel-rgb),.08)!important;
}
[data-testid="stButtonGroup"] button:hover {
  color:var(--steel)!important;border-color:var(--steel)!important;
  background:rgba(var(--steel-rgb),.18)!important;
}
[data-testid="stButtonGroup"] button[data-selected] {
  color:var(--white)!important;border-color:var(--steel)!important;
  background:var(--steel)!important;
  box-shadow:0 1px 4px rgba(var(--steel-rgb),.22);
}
[data-testid="stButtonGroup"] button[data-selected] * { color:var(--white)!important; }
[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stSelectbox"] div:has(> input[role="combobox"]) {
  border-color:var(--steel)!important;
  background:rgba(var(--steel-rgb),.07)!important;
  box-shadow:inset 3px 0 0 rgba(var(--steel-rgb),.72);
}
[data-testid="stSelectbox"] [data-baseweb="select"] > div:hover,
[data-testid="stSelectbox"] [data-baseweb="select"] > div[data-focus-within],
[data-testid="stSelectbox"] div:has(> input[role="combobox"]):hover,
[data-testid="stSelectbox"] div:has(> input[role="combobox"]):focus-within {
  border-color:var(--steel)!important;
  background:rgba(var(--steel-rgb),.13)!important;
  box-shadow:inset 3px 0 0 var(--steel),0 0 0 2px rgba(var(--steel-rgb),.12);
}
[data-testid="stSelectbox"] [aria-label="Open"] { color:var(--steel)!important; }
[data-testid="stSelectboxVirtualDropdown"] [role="option"][data-focused] [data-item-hl],
[data-testid="stSelectboxVirtualDropdown"] [role="option"][data-hovered] [data-item-hl],
[data-testid="stSelectboxVirtualDropdown"] [role="option"][aria-selected="true"] [data-item-hl] {
  color:var(--steel)!important;background:rgba(var(--steel-rgb),.16)!important;
}
.stButton button[kind="secondary"]:disabled,
.stDownloadButton button:disabled,
[data-testid="stButtonGroup"] button:disabled,
[data-testid="stButtonGroup"] button[data-disabled] {
  color:var(--muted)!important;
  border-color:var(--workspace-border)!important;
  background:rgba(185,195,201,.18)!important;
  box-shadow:none!important;
}
div[data-testid="stImage"] img { background:rgba(var(--sky-rgb),.14); }
[data-testid="stFileUploaderDropzone"] {
  min-height:4.15rem!important;padding:.4rem .65rem!important;
}
[data-testid="stFileUploaderDropzoneInstructions"] { padding:0!important; }
[data-testid="stFileUploaderDropzoneInstructions"] small { display:none!important; }
[data-testid="stFileUploaderDropzone"] small { display:none!important; }
[data-testid="stFileUploaderDropzone"] button { padding:.25rem .65rem!important; }
.data-upload-next-focus,.start-assessment-next-focus,.chat-next-focus {
  display:block;width:0;height:0;overflow:hidden;
}
.st-key-data_upload_expander:has(.data-upload-collapsed-focus) {
  box-shadow:none!important;
}
.st-key-data_upload_expander:has(.data-upload-collapsed-focus) details>summary {
  color:var(--carbon)!important;font-weight:750!important;
  background:rgba(var(--amber-rgb),.10)!important;
  box-shadow:inset 0 0 0 1px rgba(var(--amber-rgb),.18),
             0 0 10px rgba(var(--amber-rgb),.22);
  animation:upload-collapsed-pulse 1.9s ease-in-out infinite;
}
.st-key-data_upload_expander:has(.data-upload-collapsed-focus) details>summary svg {
  color:var(--amber)!important;
}
[data-testid="stExpander"]:has(.data-upload-next-focus) {
  border:1px solid var(--line)!important;background:var(--white)!important;
  box-shadow:none!important;animation:none!important;
}
[data-testid="stExpander"]:has(.data-upload-next-focus) details>summary {
  background:var(--white)!important;color:var(--carbon)!important;font-weight:750!important;
}
[data-testid="stExpander"]:has(.data-upload-next-focus) details>summary svg { color:var(--steel)!important; }
[data-testid="stExpander"]:has(.data-upload-next-focus) [data-testid="stFileUploaderDropzone"] {
  border-color:var(--steel)!important;
  box-shadow:0 0 0 3px rgba(var(--steel-rgb),.14);
}
.st-key-start_assessment_action:has(.start-assessment-next-focus) button,
[data-testid="stExpander"]:has(.data-upload-next-focus) [data-testid="stFileUploaderDropzone"] button {
  background:var(--steel)!important;color:var(--white)!important;border-color:var(--steel)!important;
  animation:action-button-pulse 1.25s ease-in-out infinite;
}
.st-key-dialogue_panel:has(.chat-next-focus) {
  border-color:var(--amber)!important;
  box-shadow:0 0 0 4px rgba(var(--amber-rgb),.12),0 10px 28px rgba(29,29,29,.10),
             0 0 0 0 rgba(var(--amber-rgb),.18)!important;
  animation:next-action-pulse 1.9s ease-in-out infinite;
}
@keyframes next-action-pulse {
  0%,100% { box-shadow:0 0 0 4px rgba(var(--amber-rgb),.12),0 8px 22px rgba(29,29,29,.08); }
  90% { box-shadow:0 0 0 7px rgba(var(--amber-rgb),.22),0 10px 28px rgba(29,29,29,.13); }
}
@keyframes action-button-pulse {
  0%,100% { box-shadow:0 0 0 0 rgba(var(--amber-rgb),.22); }
  50% { box-shadow:0 0 0 7px rgba(var(--amber-rgb),.9),0 4px 14px rgba(29,29,29,.14); }
}
@keyframes upload-collapsed-pulse {
  0%,100% { background:rgba(var(--amber-rgb),.08)!important; box-shadow:inset 0 0 0 1px rgba(var(--amber-rgb),.14),0 0 8px rgba(var(--amber-rgb),.16); }
  50% { background:rgba(var(--amber-rgb),.22)!important; box-shadow:inset 0 0 0 1px rgba(var(--amber-rgb),.28),0 0 16px rgba(var(--amber-rgb),.36); }
}
@keyframes blue-action-pulse {
  0%,100% { box-shadow:0 0 0 0 rgba(var(--steel-rgb),.18); }
  50% { box-shadow:0 0 0 6px rgba(var(--steel-rgb),.28),0 4px 14px rgba(29,29,29,.12); }
}
.workflow-progress {
  height:3.7rem;box-sizing:border-box;margin:.12rem 0;padding:.22rem .62rem;border:1px solid var(--line);
  background:var(--workspace-panel);border-radius:var(--workspace-radius);box-shadow:0 5px 18px rgba(29,29,29,.06);
}
.workflow-progress-head {
  display:flex;align-items:center;justify-content:space-between;gap:1rem;margin-bottom:.18rem;
  color:var(--gunmetal);font:700 .58rem var(--font-tech);letter-spacing:.04em;
  text-transform:uppercase;
}
.workflow-progress-head span:last-child { color:var(--muted);font-weight:600;white-space:nowrap; }
.workflow-track { display:flex;align-items:flex-start;overflow:visible;white-space:nowrap;
  padding:.35rem 0 .05rem;transform:translateY(10px); }
.workflow-phase { position:relative;flex:1 0 76px;text-align:center;min-width:76px; }
.workflow-node {
  position:relative;z-index:2;width:11px;height:11px;margin:0 auto;border-radius:50%;
  border:1px solid var(--sky);background:var(--white);color:var(--gunmetal);
  display:flex;align-items:center;justify-content:center;
  font:800 .48rem var(--font-tech);line-height:1;
}
.workflow-connector {
  position:absolute;z-index:1;top:5px;left:50%;width:100%;height:2px;background:rgba(var(--sky-rgb),.55);
}
.workflow-phase:last-child .workflow-connector { display:none; }
.workflow-connector.complete { background:var(--amber); }
.workflow-phase.complete .workflow-node {
  border-color:var(--amber);background:rgba(var(--amber-rgb),.28);color:var(--carbon);
}
.workflow-phase.complete .workflow-label { color:var(--carbon); }
.workflow-phase.active .workflow-node,
.workflow-phase.waiting .workflow-node {
  color:var(--carbon);background:var(--amber);border-color:var(--amber);font-weight:900;
  width:15px;height:15px;margin-top:-2px;box-shadow:0 0 0 2px rgba(var(--amber-rgb),.16);
}
.workflow-phase.active .workflow-node::after {
  content:"";position:absolute;inset:-7px;border-radius:50%;
  border:2px solid rgba(var(--amber-rgb),.24);border-top-color:var(--amber);
  border-right-color:var(--sky);animation:workflow-active-spin .85s linear infinite;
}
.workflow-phase.active .workflow-node::before {
  content:"";position:absolute;inset:-3px;border-radius:50%;
  box-shadow:0 0 0 1px rgba(var(--amber-rgb),.18),0 0 9px rgba(var(--amber-rgb),.30);
  animation:workflow-active-pulse 1.7s ease-in-out infinite;
}
.workflow-phase.failed .workflow-node { color:#fff;background:#c93c3c;border-color:#c93c3c; }
.workflow-label {
  margin-top:.35rem;padding:0 .18rem;color:var(--gunmetal);font:600 .64rem/1.1 Arial,Helvetica,sans-serif;
}
.workflow-phase.active .workflow-label,.workflow-phase.waiting .workflow-label { color:var(--carbon);font-weight:750; }
.workflow-item-progress { height:2px;margin-top:.18rem;background:rgba(var(--sky-rgb),.30);overflow:hidden; }
.workflow-item-progress span { display:block;height:100%;background:var(--amber); }
.workflow-item-count { margin-top:.08rem;text-align:right;color:var(--muted);font:600 .62rem Arial,Helvetica,sans-serif; }
.st-key-live_activity { height:3.7rem;box-sizing:border-box;margin:.12rem 0; }
@keyframes workflow-active-spin { to { transform:rotate(360deg); } }
@keyframes workflow-active-pulse {
  0%,100% { opacity:.35;transform:scale(.94); }
  50% { opacity:1;transform:scale(1.08); }
}
@media (prefers-reduced-motion: reduce) {
  .workflow-phase.active .workflow-node::after,
  .workflow-phase.active .workflow-node::before { animation:none; }
}
.activity-console-header {
  margin:0;padding:.2rem .55rem;border:1px solid var(--sky);border-bottom:0;
  background:rgba(var(--sky-rgb),.22);color:var(--carbon);font:700 .58rem var(--font-tech);
  letter-spacing:.12em;
}
.activity-console {
  height:calc(8.4rem - 1.35rem);box-sizing:border-box;overflow-y:auto;padding:.45rem .55rem;border:1px solid var(--gunmetal);
  background:var(--carbon);color:var(--white);font:500 .65rem/1.35 var(--font-tech);
  white-space:nowrap;box-shadow:inset 0 1px 8px rgba(10,10,10,.22);
}
.console-cursor { color:var(--amber);animation:console-blink 1s steps(1) infinite; }
@keyframes console-blink { 50% { opacity:0; } }
@media(max-width:1000px){
  .topbar{grid-template-columns:1fr}.session-name,.topbar>div:last-child{text-align:left!important}
  .workflow-phase{flex-basis:70px;min-width:70px}
}
</style>
"""
