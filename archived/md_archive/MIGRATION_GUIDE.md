# Migration Guide - Technical Changes & Architecture

**Last Updated: 29. Januar 2026**

Quick reference for technical implementation details, breaking changes, and architectural decisions. For user guide, see GETTING_STARTED.md.

## 🔄 Recent Breaking Changes

### v3.0 (29.01.2026) - Spatial Touching Simplification

**Removed:** spatial_relations (complex dict with distances/vectors)
**Added:** part_is_touching (simple string list)

Before:
`json
"spatial_relations": [{"part_id": "part_002", "euclidean_distance": 12.5, "bbox_distance": 0.0}]
`

After:
`json
"part_is_touching": ["part_002", "part_005"]
`

**Rationale:** Faster computation, simpler structure, only touching parts (bbox_distance <= 0.0)

### v3.0 (28.01.2026) - Rendering System Overhaul

**Views:** 4 views (iso+ortho) → 2 isometric views (iso1, iso2)
**Transparency:** List-based 	ransparency_values=[0.0, 0.3] for multiple variants
**Edge Width:** Configurable edge_width=2.0 parameter

**File Naming:**
- Opaque: ssembly-iso1.png
- Transparent: ssembly-iso1_transp_0_3.png

### v2.0 (22.01.2026) - Naming Convention Cleanup

**ALL UNDERSCORES + NO .STEP EXTENSION**

Before: IPA_Cranfield.STEP/IPA_Cranfield.STEP-BOM.json
After: IPA_Cranfield/IPA_Cranfield_BOM.json

**Key Changes:**
- Hyphens → Underscores
- .STEP stripped from folders/files
- Metadata → Data for part files

**⚠️ NO BACKWARD COMPATIBILITY**

### v2.0 (20.01.2026) - Assembly Sequence v3

**Simplified Structure:**
- Removed nested Subassembly objects
- Added elongs_to field ("Assembly (basic config)" | "Subassy 1")
- Flat rendering (no subfolders)

**Prompt:** generate_assembly_sequence_v3 in configs/prompts.yaml

### v1.5 (20.01.2026) - Workflow File Rename

**Changed:** Workflow_enrich_data.py → workflow.py

All imports updated in un_experiments.py, 	est_workflow_compile.py

## 🏗️ Core Architecture

### Stepparser (stepparser/)

**Purpose:** Geometry analysis & rendering

**Key Components:**
- processor.py: Main orchestration
- core/part.py: Part class with part_is_touching
- endering/renderer.py: OpenCascade rendering with transparency
- io/metadata_manager.py: JSON output

**Configuration:**
`python
StepProcessor(
    input_folder="data/input/step",
    output_folder="data/processed/stepparser",
    transparency_values=[0.0, 0.3],
    edge_width=2.0
)
`

### LLM Workflow (agent/)

**Purpose:** Vision-based enrichment & sequence generation

**Key Files:**
- workflow.py: LangGraph workflow definition
- structured_output.py: Pydantic models
- Assembly_sequence_generation.py: Sequence generation
- Assembly_sequence_validation.py: Step-by-step validation
- FFA_assessment.py: Fast-Flow Assembly evaluation

**Workflow Nodes:**
`
resolve_paths → run_assembly → list_parts → run_monoparts → merge_bom
→ assess_ffa → generate_assembly_sequence → render_assembly_steps 
→ validate_assembly_sequence → END
`

**Configuration (configs/default_settings.yaml):**
`yaml
ASG_image_keywords: ["iso1", "explosion"]
ASG_json_keywords: ["BOM_enriched"]
ASV_enabled: false  # Slow - disabled by default
ASV_transparency_values: [0.0]
FFA_mode: "enabled"
`

## 📦 Key Implementations

### Part Touching Detection

**Efficient BBox Check:**
`python
@staticmethod
def compute_spatial_relations(parts, ...):
    for part in parts:
        touching_parts = []
        for other in parts:
            bbox_dist = Part._compute_bbox_distance(bbox_self, bbox_other)
            if bbox_dist <= 0.0:  # Touching or overlapping
                touching_parts.append(other.part_id)
        part.part_is_touching = touching_parts
`

**No COM calculation, no distance vectors, no sorting - just touching detection**

### Transparency Rendering

**Current System:**
`python
# In renderer.py
def _display_shape(shape, color, transparency):
    ais_shape = AIS_Shape(shape)
    if transparency > 0:
        ais_shape.SetTransparency(transparency)
    
    # Edge width
    drawer = ais_shape.Attributes()
    line_aspect = Prs3d_LineAspect(edge_color, Aspect_TOL_SOLID, edge_width)
    drawer.SetFaceBoundaryAspect(line_aspect)
    drawer.SetFaceBoundaryDraw(True)
    
    # Update viewer for proper rendering
    self.display.Context.Display(ais_shape, True)
    if transparency > 0:
        self.display.Context.UpdateCurrentViewer()
`

### Assembly Sequence Rendering

**Incremental Logic:**
`python
def render_assembly_steps(sequence, ...):
    all_steps = expand_steps(sequence.steps)  # Expand SA1 → parts
    
    for step_idx, step in enumerate(all_steps):
        # Accumulate parts up to current step
        parts_to_render = []
        for s in all_steps[:step_idx + 1]:
            parts_to_render.extend(get_parts_from_step(s))
        
        # Render with transparency loop
        for transparency in transparency_values:
            for view in views:
                render_assembly_step(assembly, parts_to_render, view, ...)
`

### BOM Caching (FFA Assessment)

**MD5-based Cache:**
`python
bom_cache = {}

def get_cached_bom_data(bom_path, keys):
    file_hash = compute_md5(bom_path)
    if file_hash not in bom_cache:
        bom_cache[file_hash] = extract_json_keys_from_file(bom_path, keys)
    return bom_cache[file_hash]
`

## 📊 Performance & Cost

### Processing Time (per assembly)

**Stepparser:**
- Geometry analysis: 30-60s
- Rendering (2 views × transparency variants): 60-90s
- Total: 2-3 min

**LLM Workflow:**
- Assembly enrichment: 30-60s
- Parts enrichment: 10-20s each
- Assembly sequence: 30-60s
- Validation (per step): 30-60s
- FFA: 60-120s

**Total (5 parts):**
- Without validation: 5-8 min
- With validation: 10-15 min

### Cost (GPT-4o, per assembly)

- Assembly analysis: .02-0.05
- Part analysis (×N): .01-0.02 each
- Assembly sequence: .03-0.05
- Validation (×steps): .02-0.03 each
- FFA: .02-0.04

**Total (5 parts, 4 steps with validation): ~.25-0.40**

## 🐛 Known Issues

### Assembly Sequence Completeness

**Issue:** LLM may skip parts or generate incorrect order

**Detection:**
`python
bom_parts = set(bom["parts"].keys())
sequence_parts = set(...)  # Extract from steps
missing = bom_parts - sequence_parts
`

**Workaround:** Always compare vs BOM, use validation

### Transparency Rendering Artifacts

**Issue:** Parts may appear/disappear inconsistently

**Current Solution:** UpdateCurrentViewer() after transparent shapes

**Alternative:** Use only opaque (	ransparency_values: [0.0])

### Edge Width Minimal Effect

**Solution:** Use edge_width >= 2.0 for noticeable difference
- Implemented with FaceBoundaryAspect system

## 🔧 Configuration Reference

### Stepparser (main.py)

`python
processor = StepProcessor(
    input_folder="data/input/step",
    output_folder="data/processed/stepparser",
    skip_if_processed=True,
    color_mode="geometry",  # or "different"
    transparency_values=[0.0, 0.3],
    edge_width=2.0
)
`

### Workflow (configs/default_settings.yaml)

`yaml
# Assembly Sequence
ASG_image_keywords: ["iso1", "explosion"]
ASG_json_keywords: ["BOM_enriched"]
ASG_prompt_id: "generate_assembly_sequence_v3"

# Validation (optional - slow!)
ASV_enabled: false
ASV_transparency_values: [0.0, 0.3]
ASV_step_img_keywords: ["iso1"]
ASV_max_iterations: 1

# FFA Assessment
FFA_mode: "enabled"  # or "disabled", "validate_only"
FFA_prompt_id: "ffa_assessment_full_v1"
`

### Experiments (configs/experiments/*.yaml)

`yaml
experiment_name: "exp1_baseline"
step_files: ["IPA_Cranfield"]

enable_assembly_enrichment: true
enable_monopart_enrichment: true
enable_merge_bom: true
enable_assembly_sequence: true
enable_sequence_validation: false
enable_ffa_assessment: true

assembly_sequence_image_keywords: ["iso1", "explosion"]
assembly_sequence_json_keywords: ["BOM_enriched"]
`

## 📚 Data Structures

### Part (stepparser/core/part.py)

`python
class Part:
    part_id: str
    geometry_data: GeometryData
    color: Color
    part_is_touching: List[str]  # NEW: Simple touching detection
    
    def to_metadata_dict() -> dict:
        return {
            "part_id": ...,
            "volume": ...,
            "bounding_box": {...},
            "COM": {...},
            "part_is_touching": [...]
        }
`

### Assembly Sequence (agent/structured_output.py)

`python
class AssemblyStep(BaseModel):
    step_id: int
    step_description: str
    belongs_to: str  # "Assembly (basic config)" | "Subassy 1"
    base_part: str
    joining_part: Union[str, List[str]]
    joining_process: str  # "Insert" | "Screw" | "Press-fit" | ...

class AssemblySequence(BaseModel):
    assembly_name: str
    sequence_logic: str
    steps: List[AssemblyStep]
    sequence_notation: str
`

### BOM Structure

`json
{
  "parts": {
    "part_001": {
      "part_id": "part_001",
      "volume": 1234.5,
      "bounding_box": {...},
      "part_is_touching": ["part_002", "part_003"],
      "part_name_guess": "Shaft",  // From LLM enrichment
      "material_info": {...}
    }
  }
}
`

## 🔮 Future Improvements

### Planned
1. Validation optimization (parallel rendering)
2. BOM completeness check (automatic detection)
3. Interactive sequence editor

### Under Consideration
1. Web-based visualization (Three.js)
2. Automatic assembly constraints
3. Cost/time prediction

## 📚 Related Documentation

- **GETTING_STARTED.md**: User-facing comprehensive guide
- **QUICK_REFERENCE.md**: Workflow diagrams
- **EXPERIMENT_GUIDE.md**: Experiment setup details
- **ToDos.md**: Known issues & future work
