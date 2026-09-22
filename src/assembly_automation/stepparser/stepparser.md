# STEP parser

Updated: 2026-09-21

This is the canonical handoff for the standalone STEP parser in
`src/assembly_automation/stepparser`. It documents implemented behavior, current
contracts, entry points, tests and known limits. Historical designs and
superseded formats are intentionally excluded.

## Status and scope

The parser is a working standalone preprocessing module. It loads STEP/XCAF,
preserves real assembly hierarchy, validates BREP shapes, measures geometry,
assigns colors, calculates spatial/contact relationships, estimates directional
blocking, renders assembly and part images, optionally applies SAM, selects
representative images and writes JSON artifacts.

The new package is exercised by the scripts below. Existing App V3 code still
has legacy integration points elsewhere in the repository; editing this package
does not automatically change every old workflow. Product workflows use the
thin `workflows.nodes.step_preprocessing.run_step_preprocessing` adapter. Direct
tools and tests may use `StepProcessor`.

The implementation uses Python 3.12 and pythonOCC 7.9 in:

```text
C:\Users\Mika\miniforge3\envs\apa-occ
```

No LLM or user-facing agent is involved in this node.

## Start here

From the repository root:

```powershell
& C:\Users\Mika\miniforge3\envs\apa-occ\python.exe scripts\test_stepparser.py
```

With no arguments, the launcher processes every `.step` and `.stp` file directly
inside `data/input/lager`, in filename order. For one file or another folder:

```powershell
python scripts/test_stepparser.py --step-file "C:\path\assembly.STEP"
python scripts/test_stepparser.py --input-dir "C:\path\step_files"
```

Useful options are `--config PATH`, `--output-dir PATH` and `--no-render`.
An output directory must be absent or empty. One input writes directly into it;
multiple inputs create numbered subdirectories and `batch_summary.json`. A
failed assembly does not stop the remaining batch.

`test_stepparser.py` runs `StepProcessor` and then creates part-universe and
relationship diagrams for every successful result.

Regenerate diagrams from saved metadata without rerunning CAD parsing:

```powershell
python scripts/test_part_universe.py
python scripts/test_part_universe.py --run-dir data\stepparser_tests\RUN_NAME
python scripts/test_part_universe.py --min-dot-radius 6 --max-dot-radius 36
```

This script recursively discovers every assembly folder in the latest
timestamped run, including failed folders. Missing metadata and parser errors are
reported as skipped entries in `part_universe_summary.json`.

Other isolated tools:

```powershell
python scripts/test_distance_diagram.py --session-dir SESSION
python scripts/test_distance_diagram.py --session-dir SESSION --layout contacts
python scripts/test_automaticimageselection.py --session-dir SESSION
python scripts/test_sam.py --image IMAGE.png
```

On Windows, `core/native_libraries.py` registers the active Conda environment's
`Library/bin` before NumPy linear algebra is used. This supports launching
`apa-occ\python.exe` directly; without it, BLAS/LAPACK may terminate the process
without a Python exception.

## Package map

```text
stepparser/
  processor.py                         pipeline orchestration
  settings.py                          validated immutable settings
  core/
    models.py                          definition/instance/assembly models
    native_libraries.py                Windows Conda DLL setup
  io/
    step_loader.py                     STEPCAF/XCAF loading and hierarchy
    assembly_export.py                 curated assembly.json contract
    bom_export.py                      status removal for BOM exports
    metadata_manager.py                strict atomic JSON writes
  analysis/
    geometry.py                        validation and measurements
    center_of_mass.py                  pairwise instance COM distances
    spatial_relations.py               distance/contact/close maps
    interlocking.py                    directional blocking analysis
  rendering/
    views.py                           named camera definitions
    renderer.py                        persistent OCC viewer and images
    color_generator.py                 deterministic volume colors
    image_layout.py                    cropping/layout helpers
    automaticimageselection.py         view selection and collages
    sam_segmentation.py                optional SAM overlays
    part_universe.py                   COM projection and maps
    distance_diagram.py                saved-run diagram orchestration
```

The active configuration is `configs/appsettingsv3.yaml` under
`nodes.step_preprocessing`. It is loaded by
`assembly_automation.workflows.runtime.configuration.load_settings` and converted
with `StepParserSettings.from_mapping`. Unknown keys fail immediately.

## Pipeline order

`StepProcessor.process_step_file(step_file, output_dir, progress=...)` executes:

1. `loading` — hash input, read XCAF, create definitions, instances and hierarchy.
2. `validation` — validate every definition and aggregate assembly. Invalid BREP
   stops before measurement.
3. `geometry` — measure unique definitions and the aggregate.
4. `colors` — assign deterministic colors and copy them to instances.
5. `spatial_relations` — calculate exact or bbox-filtered surface distances.
6. `interlocking` — estimate blocking directions or run sampled clearance.
7. `export` — write BOM, assembly, spatial and interlocking JSON.
8. `rendering` — create assembly, exploded, part and highlighted images.
9. `sam_segmentation` — optionally create `SAM_*.png` overlays.
10. `automaticimageselection` — create representative collages.

`manifest.json` is atomically written during every stage. Exceptions mark the
active stage and manifest as failed, preserve the exception type/message and
propagate. Warnings produce overall status `partial`.

Part-universe diagrams are postprocessing invoked by the launcher, not by
`StepProcessor`. Saved-run visualization therefore remains reproducible without
reloading STEP.

## Identity, hierarchy and coordinate frames

Three IDs have different meanings:

- `part_id`: unique STEP definition (`part_001`, ...).
- `instance_id`: one placed occurrence. Copies share `part_id` but have distinct
  `instance_id` values.
- `assembly_id`: actual STEP assembly label (`assy_001`, ...).

Never group definitions by volume, area or geometric fingerprints. The loader
groups by STEP definition identity, preserving geometrically identical but
semantically different definitions.

All free XCAF roots are traversed, nested locations are composed and the true
hierarchy is retained. No wrapper assembly is invented. One true root normally
becomes `assy_001`; multiple roots form a forest; a free solid has no assembly
container and `assembly_id: null`. Actual label names are retained.

Definition geometry, volume, area, size and definition COM use `part_local`.
Instance COM, spatial points, hierarchy and diagrams use the assembly frame. BOM
placement matrices map part-local geometry into assembly coordinates. Never
apply a location twice.

OCCT normalizes length to millimetres. Exported units are `mm`, `mm2`, `mm3`.

## Geometry contract

Default unique-part measurements are volume, surface area, uniform-density
geometric COM, coordinate frame and `size: {x, y, z}`. Nonsolid volume is `null`.

Size uses axis-aligned bounds internally but the full bbox is exported only when
`include_axis_aligned_box` is enabled. Oriented boxes and detailed surface
classification are disabled by default. Topology counts were removed. Detailed
surfaces, when enabled, include type, area, centroid, bounds and available
analytic parameters.

Validity and calculation statuses are diagnostics. They remain in
`manifest.json` and are recursively removed from BOM geometry. The assembly
export also excludes schema/process metadata, validity, source paths,
normalization notes, statuses and placements.

## JSON artifacts

### `bom.json`

The BOM is authoritative for unique-part geometry and placed instances. It
contains schema version, units, grouping method, `parts` and `instances`.

A part has `part_id`, name, source definition, quantity, color and cleaned
geometry. An instance has `instance_id`, `part_id`, name, assembly membership,
source path, color, local-to-assembly matrix, assembly-frame COM and optional
bbox. Quantities derive from instances. Copies remain separate instances.

### `assembly.json`

The concise assembly summary contains the real root ID (or `null` for a forest),
name, measurement units, total/unique counts, real hierarchy, aggregate geometry
and `spatial_relations_file`. Forests also expose `root_assembly_ids` and
`root_instance_ids`. Placement matrices are deliberately absent.

### `spatial_relations.json`

Every unordered instance pair appears once. Exact records use
`BRepExtrema_DistShapeShape` and may include distance, closest points and
`inner_solution`. Classifications are `contact_or_overlap`, `close` and
`separated`.

`all_pairs` calculates all distances exactly. `nearby_pairs` first calculates a
conservative assembly-frame AABB lower bound and skips exact OCC work beyond the
proximity threshold. A bbox never proves contact.

The file also contains symmetric contact/close maps, statistics and every
unordered placed-instance COM distance under `com_pairs`. COM distances are
Euclidean and independent of surface-distance settings.

### `interlocking.json`

The default `contact_direction_proxy` uses exact contacts and the vector between
placed part centres to estimate which global `±X`, `±Y`, `±Z` directions each
neighbour may block. It exports free/blocked directions, blocker IDs, a potential
interlock score, directed edges, connected groups, method and limitations.

This is a **potential-blocking proxy**, not a motion-planning proof. A
centre-to-centre vector is not a contact normal.

Experimental `sampled_clearance` translates each shape along the six global
directions. It uses conservative bbox filtering followed by OCC minimum-clearance
checks at quadratic path samples. It is much slower, may miss thin collisions
between samples and treats persistent zero-clearance sliding contact as blocked.
Neither mode models rotation, deformation, fasteners or group removal.

### `manifest.json`

The processing record contains input name/hash, effective settings, OCCT version,
units, stage states, warnings, artifacts, elapsed time, shape validity and
geometry diagnostics. Debug process health here; do not move these diagnostics
back into BOM or assembly JSON.

## Rendering

Named views live only in `rendering/views.py`:

```text
iso1 iso2 iso3 iso4 front rear right left top bottom
```

YAML view lists select normal assembly, part and exploded images. Lists replace
defaults and preserve order. Unknown/duplicate names fail validation.

The renderer uses one persistent hidden `Viewer3d` and reuses prepared scenes
while changing cameras. It renders shaded matte shapes, can show an origin
trihedron and crops white margins while preserving annotations.

Typical output paths:

```text
images/assembly/iso1_transp_0_0.png
images/assembly/iso1_exploded_transp_0_0.png
images/parts/part_001/iso1_transp_0_0.png
images/parts/part_001/highlighted_transp_0_0.png
```

Highlighted images show every placed copy of a definition in magenta inside the
assembly; surroundings are grey/translucent. One highlight is written per unique
definition. Manifest image records include path, category, view, transparency,
coordinate frame where relevant, final size and timings.

## Image selection, collages and SAM

Automatic selection excludes SAM, collages and highlights from candidates.
ISO1 is always the first normal panel; two complementary views follow. Assembly
collages append ISO1 exploded. Part collages append the highlighted assembly
view. Assembly scoring combines silhouette/edge/color difference with a small
entropy term; part scoring emphasizes silhouettes and edges. Decisions, scores
and skips are persisted.

SAM is optional and disabled by default. It writes `SAM_<original>.png` beside
each rendered image and loads the model once per run. The configured ViT-B
checkpoint is `data/models/sam/sam_vit_b_01ec64.pth`. SAM segments rendered
pixels, not CAD faces, and never replaces authoritative OCCT geometry.

## Part-universe and relationship maps

`part_universe.py` applies classical multidimensional scaling to the complete
pairwise 3D COM-distance matrix. The part nearest assembly COM becomes the map
origin/reference without special visual status. One uniform pixel/mm scale is
used for both axes. A 3D assembly cannot preserve every distance in 2D, so the
JSON stores normalized projection error and undisturbed projected coordinates.

Marker color is the assigned part color. Unique-part volume is min-max normalized
to 0–1 per assembly and mapped to marker **area**, with default radius bounds
6–36 px. Missing volume uses the minimum; equal-volume assemblies use 0.5.
Copies share definition volume but remain separate instances.

Overlapping markers combine into a segmented-color marker and combined ID label
without changing COM coordinates. Labels go inside large markers only when every
corner of the compact box fits; others use collision-aware external placement.

Generated files:

- `parts_distance_diagram.png`: clean COM/volume map with IDs and scale.
- `parts_universe_legend.png`: separate ISO1 card gallery.
- `part_contact_map.png`: grey undirected exact-contact edges.
- `part_interlock_map.png`: purple directed potential-blocker arrows.
- `parts_distance_diagram.json`: projection, exact distances, marker sizes/groups,
  labels and relationship metadata.

Arrow width represents the fraction of tested directions attributed to a
blocker. All maps reuse the same coordinates, sizes and labels.

## Configuration

Main groups in `nodes.step_preprocessing`:

- `color_mode`: definition colors (`geometry`) or instance variation (`different`).
- `geometry`: size, detailed surfaces, oriented box, axis-aligned box.
- `rendering`: view lists, highlight, transparency, resolution, explosion,
  materials, axes and cropping.
- `spatial_relations`: thresholds, distance mode and OCC multithreading.
- `interlocking`: mode, direction threshold, or sampled count/travel/clearance.
- `automaticimageselection`: selection, sizes, entropy and cropping.
- `sam`: model, checkpoint, device and mask parameters.

Defaults live in `settings.py`; YAML is the active experiment configuration.
When adding a setting, update dataclass validation, mapping, YAML and this guide.

## Tests

Run in the OCC environment:

```powershell
python -m unittest tests.test_stepparser
python -m unittest tests.test_distance_diagram
python -m unittest tests.test_image_layout
python -m unittest tests.test_interlocking
```

Tests cover settings, BREP measurements, units, hierarchy/multiple roots,
spatial filtering, export contracts, MDS/COM layout, volume scaling, marker
grouping, collage layout and directional blocking. Some create temporary STEP
boxes with OCCT. Add acceptance tests for changes to identity, transforms, units,
classification, hierarchy or exports. For visual changes, also generate and
inspect an existing session PNG.

## Invariants for future work

- Validate before measuring or rendering.
- Keep definitions separate from placed instances.
- Preserve real STEP hierarchy; never fabricate a root.
- Preserve local versus assembly coordinate frames.
- Treat bbox distance only as a conservative filter.
- Keep exact measurements separate from display coordinates.
- Keep diagnostics in the manifest and editable facts in BOM/assembly JSON.
- Write strict JSON atomically.
- Never overwrite a nonempty parser output directory.
- Keep optional heavy dependencies lazy.
- Preserve deterministic order, IDs, colors and filenames.
- Keep the default interlocking result labelled as a proxy.

## Known limitations and next work

- Definition identity depends on XCAF structure and source authoring.
- Uniform-density geometric COM is not mass COM without materials/densities.
- Contact uses minimum distance/tolerance, not true contact-patch area.
- The default interlocking mode is directional evidence, not disassembly proof.
  Contact normals, principal axes, rotations and group removal remain future work.
- Sampled clearance is slow and incomplete for sequence generation.
- Invalid BREP stops before BOM/assembly export, preventing saved-run diagrams.
- MDS is a 2D projection; always expose projection error.
- SAM reflects image segmentation, not CAD topology.
- App V3 should consume stable artifacts through a workflow node instead of
  importing parser internals.

Prefer focused modules under `analysis`, `io` or `rendering`, validated settings
for selectable behavior, explicit artifact contracts and acceptance tests.
