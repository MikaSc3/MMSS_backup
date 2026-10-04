# Sequence rendering

`sequence_rendering` is a deterministic node. It turns an approved assembly
sequence into incremental CAD images; it does not call an LLM.

## Public entry point

```python
from assembly_automation.workflows.nodes.sequence_rendering import run_sequence_rendering

result = run_sequence_rendering(
    step_file=step_path,
    sequence=sequence_json_or_mapping,
    bom=enriched_bom_json_or_mapping,
    output_dir=empty_revision_renderings_dir,
    settings=config["nodes"]["sequence_rendering"],
)
```

Inputs are explicit so concurrent sessions cannot discover or overwrite each
other's artifacts. The sequence uses the strict flat sequence product shape;
old top-level `sequence` wrappers are unsupported. `joining_part` values must
be BOM `instance_id` values. The STEP and BOM instance sets must match.

## Step state

Steps use their global `step_id` order. `before` contains instances introduced
by earlier steps and `after` adds the current `joining_part` instance or
instances. This works for copied definitions because rendering addresses
placed physical instances rather than unique part IDs. `belongs_to` is retained
as metadata; it does not hide previously assembled geometry.

## Images

Each step can produce:

- configured normal views of the `after` state for every transparency;
- configured opaque exploded views;
- an optional view with current joining parts in magenta and prior context in
  translucent gray;
- opaque XY, XZ and/or YZ section views for `before` and `after`.
- one automatically selected `collage_step_XX.png`.
- one ordered `collage_sequence.png` covering the complete process.

The collage keeps opaque `iso1` first. It selects two complementary after-state
views using normalized silhouette, edge, color and entropy measures, then adds
the joining-part highlight and keeps opaque `iso1` exploded as the last panel.
The number of selected views and both fixed additions can be changed under
`sequence_rendering.collage`. Before-state sections remain separate evidence
and do not displace current-state views in the collage.

The sequence overview uses one opaque assembled ISO1 image per step in strict
`step_id` order. Each card shows the step number, joining process, operation
description and added instance IDs. The grid balances its columns for the
number of steps, centers incomplete rows and draws arrows between adjacent
cards. Configure it with `overview_enabled`, `overview_columns` and
`overview_tile_size` under `sequence_rendering.collage`. The Streamlit visual
workspace lists this overview first and separates the remaining output into
`Sequence steps` and `Sequence evidence` image sets.

The cut coordinate is the center of the current joining geometry along the
plane normal. The same coordinate is used for before and after, making the pair
directly comparable. Section cuts are cached by physical instance, plane and
coordinate. Failed boolean cuts fall back to the uncut shape and are listed in
`rendering_summary.json` instead of aborting all remaining images.

Names remain compatible with the important legacy selectors, for example:

```text
step_01_iso1_transp_0_0.png
step_01_iso1_exp_transp_0_0.png
step_01_iso1_joining_highlight_transp_0_0.png
step_01_section_xy_before_transp_0_0.png
step_01_section_xy_after_transp_0_0.png
collage_step_01.png
collage_sequence.png
```

Entropy is stored as image metadata in the summary instead of being embedded in
filenames. The node requires an empty output directory, so a sequence revision
gets its own immutable rendering set.

## Shared StepParser behavior

The node uses the new XCAF loader and the StepParser `Renderer`. It therefore
inherits correct placements, stable instance IDs, a persistent hidden viewer,
batched camera changes, matte materials, edge outlines, optional origin axes,
and whitespace cropping. It does not repeat BREP measurement, topology counts,
or bounding-box export. Bounds used internally for camera/explosion/section
work are not written as product artifacts.

All settings live below `nodes.sequence_rendering` in
`configs/appsettingsv3.yaml`. Unknown keys and camera names fail during settings
construction.
