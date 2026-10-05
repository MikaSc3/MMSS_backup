# UI changes

This document is the working backlog and change log for the current Streamlit UI
and structured-output presentation rework. New requests are recorded here before
implementation and updated after verification.

## Working agreement

- Collect related visual and structured-output requests in this document.
- Ask the user only when a missing decision blocks implementation or materially
  changes the result.
- Preserve artifact data and schemas unless a requested presentation change
  explicitly requires a schema change.
- Prefer native Streamlit layout and theme capabilities. Use targeted CSS only
  where the requested design cannot be expressed through the native API.
- Test with `C:\Users\Mika\miniforge3\envs\apa-occ\python.exe`.
- Do not mark an item complete until its implementation has been checked.

## Status legend

- `Planned`: understood but not yet implemented
- `In progress`: implementation has started
- `Needs decision`: a required user decision is missing
- `Implemented`: code is changed but verification is still pending
- `Verified`: implementation and relevant checks pass

## Change list

| ID | Area | Requested change | Acceptance criteria | Status |
| --- | --- | --- | --- | --- |
| UI-001 | Shared controls | Highlight pressable controls, image toggles, structured-output selectors, and dropdowns using the application blue | Selected controls use solid blue; inactive controls use a restrained blue treatment; disabled controls remain neutral | Verified |
| UI-002 | FfA step results | Remove the oversized artifact-wide total-step metric from the selected-step header | The card identifies the selected step without displaying the total number of FfA steps as a large metric | Verified |
| UI-003 | Interaction results | Apply the same selected-step header behavior to interaction analysis | No oversized artifact-wide total appears above the selected interaction step | Verified |
| UI-004 | Detailed step plans | Apply the same selected-step header behavior to detailed automation plans | No oversized artifact-wide total appears above the selected detailed plan | Verified |
| UI-005 | Workspace surfaces | Make the visual workspace and structured-output body plain white and remove the added blue outlines; retain light-grey headers | Both workspaces have white content surfaces, one neutral border, and no doubled grey/blue outline | Verified |
| UI-006 | Progress bar | Use the standard structured-output font styling for progress labels | Progress labels are legible, use the normal application sans-serif face, and do not inherit the terminal/monospace style | Verified |
| UI-007 | Progress model | Merge sequence rendering, interaction analysis, FfA assessment/scoring, and report generation into one `Feasibility analysis` point | The progress bar has one stable feasibility stage whose active/completed state reflects all underlying stages without regressions or duplicate points | Verified |
| UI-008 | Automation idea | Add a summary card matching the established result-card appearance and feature `system_architecture` in it | Selecting Automation idea shows a bordered summary card with the system architecture before the remaining fields | Verified |
| UI-009 | Detailed step plans | Render subprocesses compactly as `Subprocess | automation mode`, followed by equipment, solution, and risk; feature this in the step card | Subprocesses no longer expand into sparse generic key/value blocks and the selected plan card contains the compact subprocess overview | Verified |
| UI-010 | Automation concept | Reuse the compact subprocess presentation in the consolidated concept | Concept subprocess information uses the same order and visual language as detailed plans | Verified |
| UI-011 | Equipment presentation | Reuse a compact equipment view for detailed plans, automation concept, and equipment layout | Equipment shows `Name | Step IDs`, optional `Task`, and `Specimen`; layout coordinates and size values appear on one line | Verified |
| UI-012 | Structured-output editing | Make edit mode available for every output and move its toggle into the structured-output header | One consistently placed header toggle controls edit mode for every artifact; unsupported nested values remain safe to edit and save through the artifact workflow | Verified |
| UI-013 | Visual workspace | Hide image filenames | Images display without filename captions while selection and filtering behavior remain unchanged | Verified |

## Incoming requests

Add each new request as a separate row. Split a request only when its parts can be
implemented or accepted independently.

| ID | Area | Requested change | Acceptance criteria | Status |
| --- | --- | --- | --- | --- |

## Implementation notes

### UI-001

- Theme colors live in `.streamlit/config.toml`.
- Targeted widget states live in
  `src/assembly_automation/app/streamlit/styles.py`.

### UI-002 to UI-004

- Per-step presentation lives in
  `src/assembly_automation/app/streamlit/components/structured_results.py`.
- Assembly, monopart, and sequence totals remain because they summarize the
  complete selected artifact. Whole-artifact automation, layout, and cost
  metrics remain for the same reason.

## Verification log

| Date | Scope | Result |
| --- | --- | --- |
| 2026-10-04 | UI-001 | Streamlit configuration parsed in `apa-occ`; 13 relevant UI tests passed |
| 2026-10-04 | UI-002 to UI-004 | Module compilation and 13 relevant UI tests passed |
| 2026-10-05 | UI-005 to UI-013 | Module compilation and targeted Streamlit tests pass |
| 2026-10-05 | UI-005 to UI-013 | Full Streamlit subset: 24 passed; one unrelated pre-existing activity-console assertion fails |

## Open decisions

None.
