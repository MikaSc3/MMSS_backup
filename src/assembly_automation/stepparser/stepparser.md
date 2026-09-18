# STEP parser: current behavior and rebuild notes

Updated: 2026-09-18. Status: standalone implementation available; App V3 integration pending.

This module loads STEP models, identifies and analyzes part instances, assigns
colors, produce configurable CAD screenshots, and export geometry and spatial
relationships. It must work independently of the user-facing agent and LLMs.
The current application still uses the root `stepparser/` package. This directory
contains the independent replacement and these notes.

## Running the new parser

Use the existing `C:/Users/Mika/miniforge3/envs/apa-occ` Conda environment
(Python 3.12, pythonOCC 7.9). No packages were installed during this work.

```powershell
conda activate C:\Users\Mika\miniforge3\envs\apa-occ
python scripts/test_stepparser.py
```

With no arguments, the script loads the single `.step` or `.stp` file in
`data/input/lager`, currently `Stehlager_Sicherungsring.STEP`. Use `--step-file`
to override it. If the default folder contains multiple STEP files, an explicit
selection is required.

The script creates a fresh directory under `data/stepparser_tests`. Optional
flags: `--no-render`, `--config PATH`, and `--output-dir PATH` (must be empty).
It makes no LLM calls. A completed run exits zero; failed or partial runs exit
nonzero. The manifest records stages, settings, errors and generated files.

The public interface is `assembly_automation.stepparser.StepProcessor` with
`StepParserSettings`. The script adds `src` to its import path. For installation,
use `pip install -e '.[cad-rendering]'` in the OCC environment; Conda supplies
pythonOCC, and the optional dependency supplies Pillow for PNG capture.

### Implemented behavior

- XCAF loading of all free roots, shared part definitions and nested placements.
  Geometry grouping uses STEP definition identity, not matching volume/area.
  IDs are deterministic for a traversal, but are not guaranteed stable after
  modifying the source STEP or identical to legacy heuristic IDs.
- Normalized millimeter geometry and BREP validity checks before measurement.
  Invalid shapes fail explicitly; no automatic healing is performed. Non-solid
  shapes have a null volume rather than a fabricated solid volume.
- Local geometry, AABBs, OBBs, topology and full surface details in `bom.json`;
  placed instances include transforms and assembly-coordinate measurements.
- Every unordered instance pair is measured once. `assembly.json` contains
  distances, closest points and symmetric contact/close maps. Failed pair
  computations produce a partial result with explicit errors.
- Volume-dependent colors, named configurable assembly/part/exploded views,
  and optional highlighted-instance views. Standalone images are stored once
  per unique definition in its local coordinate frame.
- A persistent hidden viewer renders shaded PNGs at the configured size using
  an image buffer. JSON writes are atomic; nonempty output folders are rejected.

`iso4` is now a distinct camera; `legacy_iso4` preserves the old duplicated
direction. Camera definitions live in `rendering/views.py`.

Materials default to matte plastic to reduce bright surface glare. Set
`rendering.material_specular` (0..1, default 0) to control highlight intensity,
and `rendering.material_shininess` (0..1, default 0.1) to control highlight
concentration when specular reflection is enabled. These preserve directional
shading and the assigned part colors.

`rendering.show_origin_axes` enables an XYZ marker at coordinate (0, 0, 0):
red X, green Y and blue Z. Assembly/exploded/highlight images use the assembly
frame; standalone images use the part-local frame. The marker is drawn over
geometry so an origin inside a part remains visible. Its axis length is the
displayed model span times `origin_axes_size_ratio` (default 0.2). Framing
includes the origin, which can make offset models appear smaller.

User edits/revisions, selective reruns, sequence/section rendering, physical
inertia, collision volumes and feature recognition are later improvements.
The existing App V3 has not yet been switched to this output contract.

### Checks completed

Thirteen checks passed covering geometry, distances, containment, false AABB
contact, units, nested placements, shared definitions, multiple roots, failure
handling and settings. The saved example produced three unique parts, four
instances and six pair distances. The bracket/ring gaps measured 0.25 mm.
A rendering run produced twelve PNGs; inspection led to shading and capture-size
fixes. One corrected capture was verified at 1920 x 1080. The full screenshot
set should be inspected by rerunning the command above.

## Optional SAM image segmentation

SAM (Segment Anything) is from Meta. The first integration uses the official
SAM 1 automatic mask generator. It processes every original rendered image,
including assembly, exploded, standalone and highlighted images. Originals
are preserved; colored mask overlays are saved alongside them with the prefix
`SAM_`, for example `SAM_iso1_transp_0_0.png`. Their original resolution is kept.
`manifest.json` records the stage and `sam_images` source links/mask counts.

Setup in the OCC environment, from the project root:

```powershell
pip install -e '.[sam]'
New-Item -ItemType Directory -Force data/models/sam
Invoke-WebRequest -Uri 'https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth' -OutFile 'data/models/sam/sam_vit_b_01ec64.pth'
```

The ViT-B checkpoint is roughly 375 MB. Then set
`nodes.step_preprocessing.sam.enabled: true` in `configs/appsettingsv3.yaml`
and run `python scripts/test_stepparser.py`. The model is loaded once per run.
`device: auto` selects CUDA when available, otherwise CPU (which can be slow).
Lower `points_per_side` for a quicker first experiment; increase it to sample
smaller regions. `overlay_alpha` controls the colored overlay strength.
Checkpoint/model types must match. Relative checkpoint paths in the smoke-test
script are resolved against the project root. Missing dependencies/checkpoints
or inference errors fail the SAM stage explicitly while keeping the CAD outputs.

Segmentation defaults to disabled and requires rendering with at least one view.
SAM divides visible image regions; it does not guarantee one mask per CAD face
or map masks to BREP surface IDs. Background and axis markers can also receive
masks. The BOM's surface records remain authoritative CAD geometry. These PNGs
are visualizations, not exported individual masks or a CAD-surface correspondence.

Model-free checks verify source naming, image size, manifest-ready
records and overlay compositing. The existing `apa-occ` environment now includes
CPU PyTorch, torchvision, official SAM and OpenCV. The official ViT-B checkpoint
was downloaded to `data/models/sam/sam_vit_b_01ec64.pth` (375,042,383 bytes).
An isolated real CPU run with `--points-per-side 8` found 17 masks in the
front assembly image and saved its overlay in 38.38 seconds.

Official reference: https://github.com/facebookresearch/segment-anything

For an isolated one-image test, run `python scripts/test_sam.py`. It selects the
first original image alphabetically from
`data/stepparser_tests/2026-09-18_121542_36fd38da/images/assembly`
(`front_transp_0_0.png`) and writes `SAM_front_transp_0_0.png` beside it.
It forces SAM on without modifying the workflow toggle and skips existing
`SAM_` files when selecting the input. Repeated runs replace that overlay.
Override with `--image PATH`, `--checkpoint PATH`, `--device cpu|cuda|auto`, or
`--points-per-side 16` for a quicker experiment. Model setup above is still required.

## Automatic image selection

`nodes.step_preprocessing.automaticimageselection.enabled` enables the final
post-image stage. It creates `images/assembly/collage_assembly.png` and
`images/parts/<part_id>/collage_<part_id>.png`. Each contains two selected views
side by side, with filename labels. The manifest's `collages` records chosen
sources, component metrics, candidate counts and a low-diversity flag.

Selection compares cropped, centered, scale-normalized 128-pixel descriptors:
foreground silhouette difference, edge mismatch with a one-pixel tolerance,
and spatial color difference for assemblies. Assembly pair scores combine 85%
visual diversity with 15% foreground hue entropy; part scores use silhouette
and edges equally. Hue entropy reduces sensitivity to lighting, but is only
a heuristic for visible color diversity, not a count of visible parts.
Assembly `assembly_entropy_weight: 0` selects solely by visual difference.

Only original opaque standard views are used. SAM overlays, collages, highlights
and transparency variants are excluded. Set `include_exploded: true` to allow
exploded assembly views as candidates. Fewer than two valid distinct views
causes an explicit skip; near-identical pairs are flagged, not represented as
complementary evidence. The YAML now selects iso1/iso4/front/top/right for parts
so future runs offer multiple candidates. Existing runs with two part views
will necessarily select those two; camera selections remain configurable.

This heuristic cannot establish hidden CAD face coverage. Rotation, shading,
axis markers and symmetric shapes can affect scores. Future improvement:
render per-face ID buffers and maximize the union of visible BREP faces.

To try selection on the existing example without rerendering, run
`python scripts/test_automaticimageselection.py`. Override with
`--session-dir PATH`; this isolated test writes collages and `image_selection.json`
without rewriting the original run manifest. Config controls descriptor size,
collage tile dimensions and entropy weight. It needs Pillow and NumPy, no model.

## Legacy functionality (retained for migration reference)

The orchestrator is `stepparser/processor.py::StepProcessor`. Its pipeline is:

1. Load a STEP file as an assembly containing parts/subassemblies.
2. Analyze each part's volume, surface area, bounding box, topology counts, and
   surface types. Detailed face/BREP analysis is also computed and exported.
3. Group parts by a volume/surface-area fingerprint and assign `part_001`,
   `part_001_copy1`, etc.; assign `assy_001` identities to assemblies.
4. Populate `part_is_touching` using bounding-box overlap.
5. Assign colors using the geometry-group or per-instance mode.
6. Create per-assembly/per-part output folders and render screenshots.
7. Export metadata, a consolidated BOM JSON/CSV, and separate surface details;
   run sanity checks.

### Source map

| Responsibility | Current source |
| --- | --- |
| Orchestration, output layout, duplicate-image copying | `stepparser/processor.py` |
| STEP reader and hierarchy/fallback parsing | `stepparser/io/step_loader.py` |
| Assembly/part objects, bounding boxes and colors | `stepparser/core/` |
| Geometry and detailed surface analysis | `stepparser/analysis/brep_analyzer.py` |
| Duplicate grouping and IDs | `stepparser/identification/part_identifier.py` |
| Volume-dependent colors | `stepparser/rendering/color_generator.py` |
| Cameras, screenshots, explosions, highlights, sections | `stepparser/rendering/renderer.py` |
| Metadata and BOM exports | `stepparser/io/metadata_manager.py` |
| Bounding-box relationship heuristic | `stepparser/core/part.py::compute_spatial_relations` |
| Validation of saved outputs | `stepparser/io/sanity_check.py` |

### Loading and identities

The loader reads/transfers STEP roots and obtains an aggregate shape. It then
attempts XCAF hierarchy parsing; on failure it splits the aggregate compound
into solids. Single shapes become a one-part assembly.

The inspected XCAF branch uses `STEPControl_Reader` with XCAF-specific methods
and references `XCAFDoc_DocumentTool` without importing that name. It must be
reviewed and corrected against the installed bindings. It parses only the first
free root and recursively follows referred labels without explicitly composing
component placements. Proper instance locations, nested transformations, and
multiple roots are prerequisites for a trustworthy distance map. Do not assume
the hierarchy path currently works because the fallback returns geometry.

Duplicate detection uses rounded volume and surface area; this is a heuristic,
not proof of identical shapes. Preserve legacy ID compatibility during migration,
but document the heuristic and test same-volume/different-shape cases before
relying on it to reuse geometry or screenshots. Spatial relationships always
refer to placed instances, including copied parts, rather than unique geometries.

### Color assignment

`ColorGenerator.assign_colors_to_parts` groups by geometry hash, sorts unique
parts by volume, distributes hues, and decreases saturation for larger parts.
Identical parts share colors. The alternative `different` mode derives colors
from individual IDs, while retaining volume-based saturation. The geometry mode
currently seeds Python's global random generator; use a local generator in the
new implementation to avoid affecting unrelated code.

### Rendering and metadata

Assembly screenshots currently include four named ISO positions and exploded
versions, for each configured transparency. Standalone part screenshots use two
positions labeled `iso1` and `iso4`; duplicate instances reuse representative
standalone images. Highlighted-in-assembly images are rendered per placement,
unless a part group has more than ten instances. The renderer also supports
sequence subsets and XY/XZ/YZ section images used by later workflow stages.

Camera definitions are embedded in `renderer.py::View.create_standard_views`.
The fourth assembly camera duplicates the second. The standalone path selects
its cameras separately; reconcile actual directions and names during extraction.
Keep legacy camera/file compatibility explicit rather than silently changing
what an existing `iso4` name means.

The renderer lazily creates a persistent OCC display, hides its Windows window,
uses `FitAll(..., False)` to reduce redraw/event-loop problems, captures through
`View.Dump`, and clears AIS objects without recreating the display. Preserve this
lifecycle until a small-model rendering test validates changes. Some comments
mention `ToPixMap` while the actual capture method is `Dump`; document actual code.
Configured resolution must be verified against the actual output image size.

Part metadata includes IDs, volume, dimensions, center of mass, color, quantity,
duplicate references, and the current touching list. Assembly metadata includes
part counts, hierarchy references, dimensions, center of mass, and total volume.
Detailed surface data is kept separately. The BOM exports representative geometry
groups, whereas relationships must retain every instance.

## Limitations to address

- `part_is_touching` currently means overlapping/touching axis-aligned bounding
  boxes. Separate shapes can have overlapping boxes, so this can report false
  contact. `max_neighbors` and `bbox_threshold_mm` are unused despite the caller
  passing them.
- The current relationship loop evaluates both directions of every pair and
  does not export a geometric distance map.
- Cameras and view names are hardcoded across processor and renderer.
- Geometry analysis can replace failed operations with zero/empty values;
  distinguish failures from valid measurements in the new output.
- The detailed-analysis cache is keyed by part name, which can repeat. Use
  per-instance or verified geometry identities when caching.
- The processor catches broad exceptions and prints errors without returning a
  structured failure. Output-directory existence is insufficient evidence of a
  completed run; use a completion manifest.
- Existing units are treated as millimeters by convention. Verify and normalize
  STEP transfer units before labeling distances, dimensions, areas, and volumes.

## Target organization

### Agreed output contract

```text
preprocessing/stepparser/
  assembly.json
  bom.json
  manifest.json
  images/
    assembly/
    parts/
```

`bom.json` is authoritative for unique-part geometry and placed instances.
Unique-part records contain volume, surface area, color, axis-aligned and oriented
bounding boxes, shape validity, and detailed surface information. Instance records
contain stable IDs, their unique-part reference, assembly membership, and the
local-to-assembly placement transform. Keep local geometry measurements separate
from assembly-coordinate instance measurements; record each coordinate frame.
Quantities are derived from the instance records. No separate per-part metadata
files or surface-detail files are required.

`assembly.json` contains assembly metadata/hierarchy and all spatial relationships:
pairwise geometric distances, contact/overlap and proximity classifications,
closest points where available, thresholds, and computation statuses. Relationship
IDs refer to instances in the BOM, including copies. Closest points are expressed
in the assembly coordinate frame.

`manifest.json` records input identity, effective settings, normalization units,
stage completion/failures, warnings, and artifact references. Full records are
stored even when downstream prompt builders select only a few fields.

### Priority geometry upgrades

- Verify STEP units and normalize length to mm, area to mm², and volume to mm³.
- Compose nested instance placements correctly before spatial computations.
- Validate loaded geometry with `BRepCheck_Analyzer` before analysis, coloring,
  distance calculations, or rendering. Record failures explicitly; do not turn
  failed measurements into valid zeros or silently heal source geometry.
- Add oriented bounding boxes through `BRepBndLib.AddOBB`, recording center,
  axis directions, full dimensions, and computation status alongside AABBs.
- Export minimum distances and closest-point coordinates for valid shape pairs.

The existing loader checks STEP read success and rejects null aggregate shapes.
Its `SanityChecker` runs at the end and searches saved files for warning/error
keywords. These are not early BREP validity checks: no `BRepCheck_Analyzer`
call was found in the inspected loading/processing/analysis path.

Reference APIs: [shape validity](https://www.occt3d.com/dev/doc/refman/html/class_b_rep_check___analyzer.html)
and [oriented bounding boxes](https://dev.opencascade.org/doc/occt-7.5.0/refman/html/class_b_rep_bnd_lib.html).

Later optional improvements: principal axes/geometric inertia, Boolean overlap
volume, and explicit surface-adjacency/feature recognition. Physical mass/inertia
requires density; geometry alone must not be labeled as material-based mass.
Feature candidates must remain distinct from inferred engineering functions.
These additions are not prerequisites for the initial parser rebuild.

```text
stepparser/
  stepparser.md
  processor.py                  # Explicit stages and result/failure contract
  settings.py                   # Validated settings, no environment path routing
  core/                         # Geometry, part-instance and assembly contracts
  io/
    step_loader.py
    metadata_manager.py
  analysis/
    geometry.py
    spatial_relations.py        # Distance/contact/proximity calculation
  rendering/
    views.py                    # Named camera definitions, separate from renderer
    color_generator.py
    renderer.py
```

Keep reusable, proven geometry and rendering behavior; replace orchestration and
interfaces deliberately. No LLM prompt library is required for this deterministic
module. The workflow's `step_preprocessing` node will call its public interface.

## Configurable views and settings

Expose rendering and spatial settings through the preprocessing node entry in
`configs/appsettingsv3.yaml`. These settings are implemented:

```yaml
nodes:
  step_preprocessing:
    color_mode: geometry
    rendering:
      enabled: true
      assembly_views: [iso1, iso4, front, top, right]
      part_views: [iso1, iso4]
      exploded_views: [iso1]
      highlighted_view: null
      transparency_values: [0.0]
      resolution: [1920, 1080]
      explosion_factor: 2.5
    spatial_relations:
      enabled: true
      contact_tolerance_mm: 0.01
      proximity_threshold_mm: 3.0
      distance_mode: all_pairs
```

Resolve names through the isolated `rendering/views.py` registry. Reject unknown
names before creating a viewer. Use an empty selection to disable that image
category. Define camera direction and up vector unambiguously; front/top/right
names must reference a documented assembly coordinate convention. Preserve
legacy ISO directions through a compatibility mapping. The tolerance values
above are initial configurable defaults, to be checked on representative STEP
models; require proximity threshold >= contact tolerance >= 0.

## Distance and contact map upgrade

Compute minimum BREP distances between each unordered pair of placed part
instances once. Reuse that result for symmetric adjacency lists. First version:
all-pairs distances, plus derived contact and proximity maps, with no neighbor
limit. For a pair with a successful computation:

- `contact_or_overlap`: distance <= configured contact tolerance.
- `close`: contact tolerance < distance <= configured proximity threshold.
- `separated`: distance > proximity threshold.

A zero or tolerance-level distance is not proof of a mating connection, contact
area, or mechanical constraint. Keep the combined contact/overlap label until
additional analysis distinguishes those situations. Record `InnerSolution`
separately where available; it indicates one shape is fully or partly inside a
solid and does not quantify collision volume.

Suggested `assembly.json` spatial-relations section: schema version, normalized unit,
thresholds, part IDs, unordered pair records (`part_a`, `part_b`, minimum
distance, classification, computation status), and per-instance contact/close
adjacency. Failed pairs have null distance and an error/status, never an invented
zero. Include closest-point coordinates when the distance tool provides a valid
solution. Store full precision for classification; round only for display.

Use `BRepExtrema_DistShapeShape`, check `IsDone()` and `NbSolution()`, then read
`Value()` and optional `PointOnShape1/2`. The official documentation describes
these methods and `InnerSolution`: [OpenCascade distance tool reference](https://occt3d.com/dev/doc/refman/html/class_b_rep_extrema___dist_shape_shape.html).

The documentation also exposes parallel computation options, but retain serial
pair evaluation initially until the installed pythonOCC version and thread
safety have been verified. AABB distance can be a safe broad-phase lower bound
for a later threshold-only mode. Skipped pairs must not appear as exact geometric
distances. All-pairs output has quadratic compute/storage cost; report real pair
counts and introduce a documented sparse mode only when scale warrants it.

For rendering, the maintained pythonOCC viewer exposes named projection methods
and image export: [pythonOCC viewer source](https://github.com/tpaviot/pythonocc-core/blob/master/src/Display/OCCViewer.py).
Use our named camera registry to keep views consistent for metadata/screenshots
and downstream workflow consumers. Reference documentation was checked online;
the available installed OCC binding version still needs runtime verification.

## Incremental implementation and test script

1. Implement and test STEP loading, unit normalization, correct placements, early
   BREP validation, geometry metadata, oriented boxes, and stable instance IDs
   without creating a viewer. Export the agreed BOM/assembly/manifest contract.
2. Extract color assignment and named cameras; validate config selection.
3. Add assembly/part screenshot generation with the existing stable display
   lifecycle; add explosions/highlights behind explicit selections.
4. Add BREP distance calculations and contact/proximity output; compare the old
   bounding-box heuristic with actual distances on the example assembly.
5. Add a standalone `scripts/test_stepparser.py` CLI accepting `--step-file`,
   `--config`, `--output-dir`, and `--no-render`. Save a result manifest and exit
   nonzero for required-stage failures. It must not invoke LLMs or modify the
   original STEP file. Use a fresh output directory for each test run.
6. Connect the preprocessing workflow node after these module checks pass;
   preserve old session readers and filename expectations during transition.

Essential checks: boxes touching at a face; a known gap inside/outside the
proximity threshold; overlap and containment; overlapping AABBs with separated
BREPs; identical geometry at different placements; nested transformed instances;
multiple roots and single solids; unit conversion; failed pair computation;
unknown view names; selected/disabled image categories; deterministic colors
without global RNG mutation; output dimensions and repeated screenshots.

Use the saved Stehlager/Sicherungsring assembly as the integration example, but
do not assume its existing touching lists are geometric ground truth. Synthetic
shapes provide known distances for acceptance checks.

## Environment and progress

The standalone implementation is available in this directory. Existing App V3
remains active. The registered `C:/Users/Mika/miniforge3/envs/apa-occ` environment
provided Python 3.12.14, pythonOCC 7.9.0, PyYAML and Pillow for the checks above.
The checked-in venv points to another machine. No packages were installed and
no original session artifacts were changed; trial outputs are under
`data/stepparser_tests`.
