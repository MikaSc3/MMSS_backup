# Layout Generator Specification

Status: proposed MVP, 2026-08-05

## Goal

Add a deterministic layout-generation node directly after automation-planner module `03_automatisierungsvarianten`.

For every automation strategy, the node shall:

1. render every station as a standalone image from `equipment_station` and `equipment_coordinates`;
2. render one combined plant layout from `station_coordinates`;
3. save machine-readable rendering metadata and validation warnings;
4. optionally call an LLM once to assign equipment categories and pictograms.

The first version uses labeled rectangles only. Every rectangle contains the exact
`equipment_coordinates[].equipment_name` value, wrapped across multiple lines where
necessary. Pictograms and the pictogram-assignment LLM call are explicitly deferred
and must not be required by the MVP renderer.

## Workflow position

```text
03_automatisierungsvarianten
  -> 03a_layout_generator
  -> later automation-planner modules
```

The node consumes the three existing files:

```text
automation_planner/03_automatisierungsvarianten/
  variante_manuell.json
  variante_halbautomatisiert.json
  variante_vollautomatisiert.json
```

It should run after all requested variant files have been written. A failure to render one strategy must be reported for that strategy and should not prevent rendering the other valid strategies.

## Input contract

The renderer uses these fields from `AutomatisierungsGesamtkonzept`:

```json
{
  "varianten_id": "Stehlager_Sicherungsring_halbautomatisiert",
  "strategie": "halbautomatisiert",
  "stationen": [
    {
      "station_nr": 1,
      "equipment_station": [
        {
          "name": "Tray indexer for part_001",
          "function": "Feed oriented parts to the pick position",
          "specimen": "Single-pick presentation",
          "quantity": 1
        }
      ],
      "equipment_coordinates": [
        {
          "equipment_name": "Tray indexer for part_001",
          "x": -70,
          "y": 0
        }
      ]
    }
  ],
  "station_coordinates": [
    {
      "station_nr": 1,
      "x": 0,
      "y": 0
    }
  ]
}
```

All coordinates are center points in centimetres. The layout uses a top view. Positive X points right and positive Y points upward in engineering coordinates. The renderer must invert Y only when converting to image coordinates, where Y normally points downward.

### Identity rules

- `station_nr` is the stable join key between `stationen` and `station_coordinates`.
- `equipment_station[].name` and `equipment_coordinates[].equipment_name` are the current join keys for equipment.
- Matching first uses exact normalized text: trim, collapse whitespace, and compare case-insensitively.
- The renderer must not silently use fuzzy matching. A fuzzy suggestion may be written as a warning, but ambiguous entries remain unlinked.
- Equipment names should be unique within one station. Duplicate names require a future stable `equipment_id` field.

Recommended future schema improvement:

```json
{
  "equipment_id": "station_001_equipment_004",
  "name": "Tray indexer for part_001"
}
```

Both the equipment row and coordinate row should then reference `equipment_id` instead of joining by display text.

## Output contract

Create one folder per strategy:

```text
automation_planner/03a_layouts/
  manuell/
    station_001.svg
    station_001.png
    overall_layout.svg
    overall_layout.png
    layout_manifest.json
  halbautomatisiert/
    station_001.svg
    station_001.png
    overall_layout.svg
    overall_layout.png
    layout_manifest.json
  vollautomatisiert/
    ...
```

PNG is the required standalone image output. SVG is the recommended source format because it keeps text sharp, is easy to inspect, and supports later pictogram insertion without changing the geometry engine.

`layout_manifest.json` records reproducibility and warnings:

```json
{
  "schema_version": "1.0",
  "varianten_id": "Stehlager_Sicherungsring_halbautomatisiert",
  "strategy": "halbautomatisiert",
  "source_file": "../03_automatisierungsvarianten/variante_halbautomatisiert.json",
  "coordinate_unit": "cm",
  "renderer": {
    "version": "1.0",
    "pixels_per_cm": 4,
    "padding_cm": 25
  },
  "station_images": [
    {
      "station_nr": 1,
      "svg": "station_001.svg",
      "png": "station_001.png"
    }
  ],
  "overall_images": {
    "svg": "overall_layout.svg",
    "png": "overall_layout.png"
  },
  "warnings": []
}
```

## MVP rendering logic

### Equipment representation

Every equipment entity is a labeled rectangle:

- center: `equipment_coordinates[].x/y`;
- default footprint: configurable, initially `30 cm x 18 cm`;
- fill colour: neutral grey in the MVP;
- main label: the exact `equipment_name` from the coordinate entry, wrapped inside the rectangle;
- second line: `x{quantity}` when quantity is greater than one;
- optional small footer: coordinate `(x, y) cm` in debug mode;
- tooltip in SVG: full name, function, and specimen.

The MVP must not replace the equipment name with an abbreviated or LLM-generated
label. If the text does not fit, wrap it and increase the rectangle height up to a
configured maximum. If it still does not fit, clip the visible text with an ellipsis
and preserve the complete name in the SVG tooltip and manifest.

Quantity does not create multiple rectangles in the MVP. One row represents one equipment type and shows its quantity. Later, an explicit coordinate is required for every physical instance if multiple rectangles are desired.

The station origin `(0, 0)` gets crosshairs and an origin label. Add a light grid, a scale bar, station number, strategy, legend, and coordinate axes. Long labels are wrapped and clipped to the rectangle; full text remains available in the SVG tooltip and manifest.

### Footprints

The current schema supplies center points but no width, depth, orientation, or safety envelope. Therefore the MVP cannot claim to be a dimensionally valid factory layout.

Use category defaults only for visualization:

| Category | Default width x depth |
|---|---:|
| fixture | 30 x 25 cm |
| robot | 60 x 60 cm |
| feeder | 70 x 35 cm |
| conveyor/track | 80 x 20 cm |
| sensor/camera | 20 x 20 cm |
| tool/gripper | 20 x 15 cm |
| operator | 50 x 50 cm |
| safety | 80 x 20 cm |
| other/unknown | 30 x 18 cm |

These dimensions must be marked as `visual_default`, not engineering facts. A later schema should add `width_cm`, `depth_cm`, `rotation_deg`, and optionally `safety_radius_cm` or a polygon footprint.

### Standalone station image algorithm

For each `stationen[]` entry:

1. validate and join equipment rows to coordinate rows;
2. obtain the visual footprint from the generic MVP default;
3. compute the bounding box of all rectangles;
4. add configurable padding for labels, legend, operator access, and axes;
5. transform engineering coordinates to SVG/image coordinates;
6. render grid, origin, equipment rectangles, labels, and warnings;
7. save `station_{station_nr:03d}.svg` and `.png`;
8. store bounds and warnings in the manifest.

An empty station still produces an image containing the station title, origin, and a visible `No positioned equipment` warning.

### Combined layout algorithm

The combined layout uses `station_coordinates` as the authoritative station centers.

For each station:

1. calculate its local rendered footprint from its equipment extents;
2. place the station footprint center at the matching global station coordinate;
3. translate every local equipment position by the global station position;
4. render a station boundary, station number, and all internal equipment rectangles;
5. draw optional transfer arrows in station order when there is more than one station;
6. compute global bounds, add padding, and save `overall_layout.svg` and `.png`.

The combined image should show real relative coordinate spacing. It must not independently auto-arrange stations. If station boundaries overlap, render the overlap and emit a warning; silently moving a station would falsify the LLM output.

For a very dense layout, the renderer may switch internal labels to short labels, but coordinates and geometry remain unchanged.

## Deferred: pictogram assignment LLM call

### Responsibility boundary

The LLM assigns semantic presentation metadata only. It must not change:

- station number;
- equipment identity;
- quantity;
- X/Y coordinates;
- station coordinates;
- station order.

The call should deduplicate identical normalized equipment names across all three strategies and classify them in one batch. Cache the result by normalized equipment name plus prompt/schema version.

### Input

Provide only the information required for classification:

```json
{
  "equipment": [
    {
      "equipment_key": "tray indexer for part_001",
      "name": "Tray indexer for part_001",
      "function": "Feed oriented pedestal bracket bodies to the pick position",
      "specimen": "Single-pick presentation with fixed orientation"
    }
  ],
  "allowed_categories": [
    "fixture",
    "robot",
    "linear_axis",
    "feeder",
    "tray_or_bin",
    "conveyor_or_track",
    "gripper_or_tool",
    "joining_machine",
    "sensor_or_camera",
    "inspection_system",
    "operator",
    "buffer",
    "safety",
    "control_cabinet",
    "other"
  ]
}
```

### Structured output

```json
{
  "assignments": [
    {
      "equipment_key": "tray indexer for part_001",
      "category": "tray_or_bin",
      "pictogram_id": "tray",
      "short_label": "Part 001 tray indexer",
      "confidence": 0.94,
      "reason": "Provides an oriented part tray at a fixed pick position"
    }
  ]
}
```

Suggested Pydantic contract:

```python
class EquipmentVisualAssignment(BaseModel):
    equipment_key: str
    category: Literal[
        "fixture", "robot", "linear_axis", "feeder", "tray_or_bin",
        "conveyor_or_track", "gripper_or_tool", "joining_machine",
        "sensor_or_camera", "inspection_system", "operator", "buffer",
        "safety", "control_cabinet", "other"
    ]
    pictogram_id: Literal[
        "fixture", "robot_arm", "scara", "linear_axis", "feeder_bowl",
        "tray", "conveyor", "gripper", "press", "camera", "sensor",
        "inspection", "operator", "buffer", "safety_fence",
        "control_cabinet", "generic_machine"
    ]
    short_label: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class EquipmentVisualAssignments(BaseModel):
    assignments: List[EquipmentVisualAssignment]
```

### System prompt specification

```text
You classify manufacturing-station equipment for schematic top-view rendering.
Return exactly one assignment for every supplied equipment_key.
Choose only from the allowed category and pictogram enums.
Base the choice on name, function, and specimen.
Do not infer or modify position, quantity, dimensions, station membership, or
process design. Use other/generic_machine when evidence is insufficient.
short_label must be concise, distinct within the supplied list, and preserve
part identifiers such as part_001 when relevant.
```

The caller validates exact input/output key coverage. Missing, duplicate, unknown, or extra keys reject the classification response. Low-confidence assignments use `generic_machine` in the renderer and produce a warning.

### Do we need the LLM for the MVP?

No. The first implementation should render neutral rectangles and should not make
an LLM call. A later intermediate version can use deterministic keyword rules before
the LLM integration is introduced:

- `robot`, `SCARA`, `portal` -> robot;
- `fixture`, `nest`, `hold-down` -> fixture;
- `tray`, `bin`, `pallet` -> tray_or_bin;
- `feeder`, `escapement` -> feeder;
- `track`, `conveyor` -> conveyor_or_track;
- `gripper`, `tool` -> gripper_or_tool;
- `camera`, `vision` -> sensor_or_camera;
- `sensor` -> sensor_or_camera;
- `operator`, `worker` -> operator;
- otherwise -> other.

This makes the initial renderer cheap, repeatable, and testable. The LLM becomes useful when names are ambiguous or when short labels need improvement. The final assignment file should use the same schema regardless of whether rules or the LLM produced it.

## Recommended pictograms

Use a small industrial icon vocabulary instead of one icon per exact machine name:

- robot arm and SCARA;
- fixture/workpiece nest;
- tray/bin/pallet;
- bowl or step feeder;
- conveyor/linear track;
- linear axis/slide;
- gripper/tool/end effector;
- press/joining head;
- camera and generic sensor;
- inspection station;
- operator;
- buffer/rack;
- safety fence/light curtain;
- control cabinet;
- generic machine.

An icon alone is not sufficient: a tray indexer, fixture, and feeder can look similar in a top-view schematic. The recommended visual grammar is therefore **icon plus labeled footprint rectangle**, not free-standing pictograms. Colour expresses category, the rectangle expresses occupied area, the icon supports quick recognition, and the label preserves technical specificity.

Do not generate pictogram bitmap images with an LLM for each run. Use a versioned local SVG icon library with a consistent view box, stroke width, licence, and visual style. The classification call selects an icon ID from that library.

## Renderer implementation

Recommended module:

```text
agent/layout_generator.py
```

Suggested public API:

```python
def generate_variant_layouts(
    variant_path: Path,
    output_dir: Path,
    *,
    visual_assignments: EquipmentVisualAssignments | None = None,
    config: LayoutGeneratorConfig | None = None,
) -> LayoutManifest:
    ...


def run_layout_generator_on_session(
    session_root: Path,
    *,
    strategies: Iterable[str] = STRATEGIES,
    classify_with_llm: bool = False,
) -> dict[str, LayoutManifest]:
    ...
```

Preferred rendering pipeline:

1. create SVG deterministically using the Python standard library or a small SVG helper;
2. convert SVG to PNG with CairoSVG if available;
3. if CairoSVG is undesirable on Windows, use Pillow or matplotlib for direct PNG output while retaining the same geometry model;
4. never use screenshots or an image-generation model for technical layout rendering.

The geometry calculation should be independent from the output backend so SVG and PNG use identical bounds and positions.

Suggested configuration:

```yaml
layout_generator:
  enabled: true
  output_svg: true
  output_png: true
  pixels_per_cm: 4
  padding_cm: 25
  show_grid: true
  grid_step_cm: 25
  show_coordinates: false
  show_transfer_arrows: true
  classification: rules  # rules | llm | disabled
  low_confidence_threshold: 0.65
```

## Validation and failure behaviour

Hard errors for one strategy:

- invalid JSON or model validation failure;
- duplicate station numbers;
- duplicate coordinate entry for one station;
- non-numeric or non-finite coordinates;
- no usable stations.

Warnings that still produce images:

- equipment without coordinates;
- coordinates without matching equipment;
- station without a global coordinate;
- global coordinate without a station;
- duplicate normalized equipment names;
- overlapping equipment footprints;
- overlapping station footprints;
- category dimensions based on visual defaults;
- unknown or low-confidence pictogram classification.

Unpositioned equipment should appear in a separate `Unpositioned equipment` list at the side of the station image. It must not be assigned invented coordinates.

## Acceptance criteria for the box MVP

1. Running the node on a valid variant creates one PNG and one SVG per station.
2. It creates one combined PNG and SVG per strategy.
3. Every matched equipment entry appears exactly once in its station image.
4. The combined layout places every station at its supplied station coordinate.
5. `(0, 0)` is visibly identifiable in station and overall images.
6. Negative coordinates render correctly.
7. Input order does not change image geometry.
8. Missing or mismatched coordinate records produce visible warnings and manifest entries, not invented positions.
9. Repeated execution with unchanged input produces equivalent SVG geometry and manifest content.
10. The provided semi-automated example renders station 1 and its overall single-station layout without manual edits.

## Test plan

- unit test coordinate transforms, including negative X/Y and Y-axis inversion;
- unit test exact normalized joins and mismatches;
- unit test bounding-box and padding calculation;
- unit test equipment and station overlap detection;
- unit test classification output coverage and enum validation;
- golden SVG test for a small two-equipment station;
- integration test using `variante_halbautomatisiert.json`;
- integration test with two stations to confirm local-to-global translation;
- test missing equipment coordinates and missing station coordinates;
- test identical outputs after permuting JSON list order.

## Recommended delivery stages

### Stage 1: boxes

- validate and join current JSON;
- render standalone station SVG/PNG;
- render combined SVG/PNG;
- write manifest and warnings;
- render neutral rectangles containing the exact `equipment_name`;
- do not call an LLM and do not require pictogram assets.

### Stage 2: stable equipment IDs and footprints

- add `equipment_id` to structured output;
- add optional width, depth, rotation, and safety envelope;
- add overlap checks using explicit geometry.

### Stage 3: pictogram classification

- add the structured LLM classification call;
- cache assignments;
- add a local SVG icon library;
- render icon plus label inside each footprint.

### Stage 4: engineering layout semantics

- add material-flow and assembly-transfer edges;
- distinguish physical equipment, working envelope, safety envelope, and operator access;
- support non-rectangular polygon footprints;
- add a legend for assumptions versus confirmed dimensions.
