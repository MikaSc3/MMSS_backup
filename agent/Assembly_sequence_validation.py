"""
Assembly Sequence Validation - STANDALONE VERSION

Validiert generierte Montagereihenfolgen mit LLM-basierter visueller Analyse.
Per-Step Validation mit inkrementellen Renderings.

Diese Datei läuft UNABHÄNGIG vom Workflow_enrich_data.py.

Usage:
    python -m agent.Assembly_sequence_validation

Features:
1. Per-step LLM validation calls with BOM-integrated part metadata
2. Uses explosion view + incremental step renderings + prior-step renderings (BEFORE/AFTER)
3. Structured output: is_valid, feedback, improvements per step
4. JSON-key filtering for token efficiency
5. Image downscaling for cost reduction
6. Keyword-based image filtering

Generation siehe: Assembly_sequence_generation.py
"""

from __future__ import annotations

import os
import json
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from agent.utils import invoke_with_retry

# LLM - use existing setup from tools.py
try:
    from agent.tools import _get_img_describer_llm, extract_json_keys_from_file
except ImportError:
    from tools import _get_img_describer_llm, extract_json_keys_from_file

# Structured output models
try:
    from agent.structured_output import AssemblyStepValidation
except ImportError:
    from structured_output import AssemblyStepValidation

# Prompt loading
try:
    from agent.prompt_store import get_prompt_template
except ImportError:
    try:
        from prompt_store import get_prompt_template
    except ImportError:
        get_prompt_template = None

# Stepparser Renderer Import
try:
    from stepparser.rendering.renderer import Renderer, View
    from stepparser.io.step_loader import StepLoader
    from stepparser.core.assembly import Assembly
    RENDERER_AVAILABLE = True
except ImportError as e:
    print(f"[WARNING] stepparser not available - Rendering will be disabled: {e}")
    RENDERER_AVAILABLE = False


# ============================================================================
# ASSEMBLY SEQUENCE RENDERING
# ============================================================================

# ============================================================================
# UTILITY FUNCTIONS (für BOM-Integration & Image-Handling)
# ============================================================================

def filter_part_metadata(part_data: Dict[str, Any], keys: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Filtert ein Part-Metadata-Dict auf gewünschte Keys (für Token-Effizienz).
    
    Args:
        part_data: Part metadata dict from BOM
        keys: Keys to keep (None = keep all)
    
    Returns:
        Filtered dict
    """
    if not keys or not part_data:
        return part_data or {}
    
    filtered = {}
    for key in keys:
        if key in part_data:
            filtered[key] = part_data[key]
    return filtered


def load_part_metadata_from_bom(
    part_id: str,
    bom_data: Dict[str, Any],
    json_keys: Optional[List[str]] = None
) -> Optional[Dict[str, Any]]:
    """
    Lädt Part-Metadata aus BOM mit JSON-Key-Filterung.
    
    Args:
        part_id: Part ID (z.B. 'part_001', 'part_003_copy1')
        bom_data: Loaded BOM data dict (with "parts" list)
        json_keys: Keys to extract (filters the JSON to only these keys)
    
    Returns:
        Part metadata dict (gefiltert nach json_keys) oder None
    """
    if not bom_data:
        return None
    
    parts_list = bom_data.get("parts", [])
    for part in parts_list:
        if part.get("part_id") == part_id:
            # Filter to requested keys
            return filter_part_metadata(part, json_keys)
    
    return None


def load_and_downscale_image(
    img_path: Path,
    downscale_factor: float = 1.0
) -> Dict[str, Any]:
    """
    Lädt ein Bild und skaliert es optional herunter.
    
    Args:
        img_path: Pfad zum Bild
        downscale_factor: Scaling factor (0.5 = 50% size)
    
    Returns:
        Dict mit {"path": str, "filename": str, "b64": str, "mime": str}
    """
    import base64
    
    if downscale_factor < 1.0:
        # Downscale image
        from PIL import Image
        import io
        
        img = Image.open(img_path)
        new_size = (int(img.width * downscale_factor), int(img.height * downscale_factor))
        img_resized = img.resize(new_size, Image.Resampling.LANCZOS)
        
        buffer = io.BytesIO()
        img_resized.save(buffer, format="PNG")
        b64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
    else:
        # Use original image
        with open(img_path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")
    
    return {
        "path": str(img_path),
        "filename": img_path.name,
        "b64": b64_data,
        "mime": "image/png"
    }


# ============================================================================
# HELPER FUNCTIONS FOR RENDERING
# ============================================================================

def sanitize_filename(name: str, max_length: int = 50) -> str:
    """
    Sanitize a string for use in filenames.
    Removes invalid characters and truncates to max_length.
    """
    import re
    # Remove invalid filename characters
    sanitized = re.sub(r'[<>:"/\\|?*\[\]]', '', str(name))
    # Replace spaces with underscores
    sanitized = sanitized.replace(' ', '_')
    # Truncate to max length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    return sanitized


def expand_subassemblies_in_sequence(sequence_data: Dict) -> Dict:
    """
    Expand all subassembly references (SubAssy_X, SA1, SA2, etc.) to their constituent part_ids.
    
    This preprocesses the assembly sequence so that rendering only deals with real part_ids.
    
    Args:
        sequence_data: Assembly sequence JSON dict
    
    Returns:
        Modified sequence_data with all SubAssy references expanded to part_ids
    """
    subassembly_map = {}
    
    # FIRST: Build subassembly map from belongs_to field (new format)
    # This must happen BEFORE expansion to correctly map SA1, SA2, etc.
    subassy_parts = {}  # "Subassy 1" -> [list of parts in this subassy]
    
    for step in sequence_data.get('steps', []):
        belongs_to = step.get('belongs_to', 'Assembly (basic config)')
        if belongs_to != 'Assembly (basic config)':
            # This is a subassembly step
            if belongs_to not in subassy_parts:
                subassy_parts[belongs_to] = []
            
            # Add base_part (not expanded yet - direct from JSON)
            base_part = step.get('base_part')
            if base_part and base_part not in subassy_parts[belongs_to] and base_part != "table":
                subassy_parts[belongs_to].append(base_part)
            
            # Add joining_part (not expanded yet - direct from JSON)
            joining_part = step.get('joining_part')
            if joining_part:
                if isinstance(joining_part, list):
                    for part_id in joining_part:
                        if part_id not in subassy_parts[belongs_to]:
                            subassy_parts[belongs_to].append(part_id)
                else:
                    if joining_part not in subassy_parts[belongs_to]:
                        subassy_parts[belongs_to].append(joining_part)
    
    # Build mapping: "Subassy 1" -> SA1 -> parts, "Subassy 2" -> SA2 -> parts
    for subassy_name, parts in subassy_parts.items():
        # Map "Subassy 1" directly
        subassembly_map[subassy_name] = parts
        
        # Also map "SA1" format (extract number from "Subassy 1")
        if "Subassy " in subassy_name:
            number = subassy_name.replace("Subassy ", "")
            sa_id = f"SA{number}"
            subassembly_map[sa_id] = parts
    
    # SECOND: Build subassembly map from 'subassemblies' array (legacy format)
    for subassy in sequence_data.get('subassemblies', []):
        subassembly_map[subassy.get('id')] = subassy.get('parts', [])
    
    # THIRD: Extract subassemblies from steps (in case they're defined inline) - legacy
    for step in sequence_data.get('steps', []):
        if 'subassembly' in step and step['subassembly']:
            sa_data = step['subassembly']
            sa_id = sa_data.get('id')
            sa_parts = sa_data.get('parts', [])
            if sa_id and sa_parts:
                subassembly_map[sa_id] = sa_parts
    
    def expand_part_ref(part_ref):
        """Expand a single part reference (can be part_id, SubAssy_X, SA1, SA2, etc.)"""
        if isinstance(part_ref, str):
            # Check if this is a subassembly reference (either SubAssy_X or SA1/SA2 format)
            if part_ref in subassembly_map:
                # Expand to constituent parts
                return subassembly_map.get(part_ref, [])
            elif part_ref.startswith("SubAssy_"):
                # Legacy format - try to expand
                return subassembly_map.get(part_ref, [])
            else:
                # Regular part_id
                return [part_ref]
        else:
            return []
    
    # Expand all steps
    for step in sequence_data.get('steps', []):
        # Expand base_part (ALWAYS set it, even if empty)
        expanded_base = []
        if 'base_part' in step and step['base_part']:
            expanded_base = expand_part_ref(step['base_part'])
        step['_expanded_base_parts'] = expanded_base
        
        # Expand joining_part (ALWAYS set it, even if empty)
        expanded_joining = []
        if 'joining_part' in step and step['joining_part']:
            joining = step['joining_part']
            if isinstance(joining, list):
                for item in joining:
                    expanded_joining.extend(expand_part_ref(item))
            else:
                expanded_joining.extend(expand_part_ref(joining))
        step['_expanded_joining_parts'] = expanded_joining
    
    return sequence_data


def render_assembly_steps(assembly_name: str, experiment_name: str = "direct_run", exp_output_dir: Path = None, transparency_values: List[float] = None, headless_mode: bool = False) -> Dict:
    """
    Render incremental assembly steps with all 4 standard views.
    
    For each step N, renders all parts from steps 1 through N.
    Generates: step_N_isometric.png, step_N_front.png, step_N_top.png, step_N_side.png
    
    Args:
        assembly_name: Name of assembly (e.g., 'IPA_Cranfield')
        experiment_name: Experiment folder name
        exp_output_dir: Optional explicit output directory path (overrides default)
        transparency_values: List of transparency values (e.g., [0.0, 0.2]). Default: [0.0]
        headless_mode: If True, use headless rendering with aggressive display cleanup.
                      Recommended for complex section view rendering that hangs on some assemblies.
    
    Returns:
        Dict with rendering results
    """
    
    # Default to opaque only
    if transparency_values is None:
        transparency_values = [0.0]

    # Section views and explosion views render ONLY at transparency=0.0 (opaque).
    # If the caller did not include 0.0 (e.g. ASV_transparency_values: [0.3]),
    # those views would silently be skipped.  Always ensure 0.0 is present so
    # section/explosion renders are never accidentally omitted.
    if 0.0 not in transparency_values:
        transparency_values = [0.0] + list(transparency_values)

    print(f"  Transparency values (effective): {transparency_values}")
    print("\n" + "="*80)
    print(f"RENDERING ASSEMBLY STEPS: {assembly_name}")
    print("="*80)
    
    import json
    from pathlib import Path
    from stepparser.io.step_loader import StepLoader
    from stepparser.rendering.renderer import Renderer, View
    
    # Setup paths
    base_dir = Path(__file__).parent.parent
    
    # Use provided exp_output_dir or compute from defaults
    if exp_output_dir is None:
        exp_output_dir = base_dir / "data" / "experiments" / experiment_name / assembly_name
    else:
        exp_output_dir = Path(exp_output_dir)
    
    sequence_file = exp_output_dir / "assembly_sequence.json"
    output_dir = exp_output_dir / "sequence_renderings"
    output_dir.mkdir(exist_ok=True, parents=True)
    
    # Load assembly sequence
    if not sequence_file.exists():
        error_msg = f"Assembly sequence not found: {sequence_file}"
        print(f"[ERROR] {error_msg}")
        return {"status": "error", "message": error_msg}
    
    with open(sequence_file, 'r', encoding='utf-8') as f:
        sequence_data = json.load(f)
    
    # Expand all subassembly references in the sequence
    sequence_data = expand_subassemblies_in_sequence(sequence_data)
    
    steps = sequence_data.get('steps', [])
    if not steps:
        print("[WARNING] No assembly steps found")
        return {"status": "warning", "message": "No steps to render"}
    
    print(f"\\nLoaded {len(steps)} assembly steps")

    # Selective step rendering: if a previous run already produced images for
    # every step, reuse them. This is especially useful for experiment reruns
    # that failed after rendering but before FFA/report generation.
    summary_path = output_dir / "rendering_summary.json"
    complete_step_images = all(
        any(output_dir.glob(f"step_{int(step['step_id']):02d}_*.png"))
        for step in steps
        if "step_id" in step
    )
    if summary_path.exists() and complete_step_images:
        print(f"  [SKIP] Existing step renderings found: {output_dir}")
        return {
            "status": "success",
            "message": "existing_step_renderings_reused",
            "output_dir": str(output_dir),
            "renderings_count": len(steps),
        }
    
    # Load Assembly object from STEP file. Prefer the current experiment/session
    # input folder, then the terminal batch input folder, then legacy locations.
    step_file_patterns = []

    for root_value in [
        Path(exp_output_dir).parent / "input",
        Path(exp_output_dir) / "input",
        os.environ.get("APA_MASTER_STEP_INPUT_FOLDER"),
    ]:
        if not root_value:
            continue
        root = Path(root_value)
        if not root.is_absolute():
            root = base_dir / root
        step_file_patterns.extend([
            root / f"{assembly_name}.STEP",
            root / f"{assembly_name}.step",
        ])

    step_file_patterns.extend([
        base_dir / "data" / "input" / "test" / f"{assembly_name}.STEP",
        base_dir / "data" / "input" / "test" / f"{assembly_name}.step",
        base_dir / "data" / "input" / "ALL" / f"{assembly_name}.STEP",
        base_dir / "data" / "input" / "ALL" / f"{assembly_name}.step",
        base_dir / "data" / "input" / "STEP" / f"{assembly_name}.STEP",
        base_dir / "data" / "input" / "STEP" / f"{assembly_name}.step",
    ])
    
    step_file = None
    for pattern in step_file_patterns:
        if pattern.exists():
            step_file = pattern
            break
    
    if not step_file:
        error_msg = f"STEP file not found for assembly: {assembly_name}"
        print(f"[ERROR] {error_msg}")
        return {"status": "error", "message": error_msg}
    
    print(f"\\nLoading assembly from: {step_file}")
    loader = StepLoader()
    assembly = loader.load_step_file(str(step_file))
    
    if not assembly:
        error_msg = "Failed to load assembly"
        print(f"[ERROR] {error_msg}")
        return {"status": "error", "message": error_msg}
    
    print(f"Assembly loaded: {assembly.name} with {len(assembly.get_all_parts())} parts")
        # Analyze parts to compute bounding boxes (required for rendering)
    print(f"Analyzing geometry and assigning IDs...")
    from stepparser.analysis.brep_analyzer import BRepAnalyzer
    from stepparser.identification.part_identifier import PartIdentifier
    from stepparser.rendering.color_generator import ColorGenerator
    from stepparser.core.data_classes import BoundingBox
    
    analyzer = BRepAnalyzer()
    part_identifier = PartIdentifier()
    color_generator = ColorGenerator()
    all_parts = assembly.get_all_parts()
    
    for part in all_parts:
        if not part.geometry_data:
            part.geometry_data = analyzer.analyze_shape(part.shape, part.name)
    
    # Assign part IDs (required for matching with assembly_sequence.json)
    part_identifier.assign_part_ids(all_parts, prefix="part")
    print(f"  Assigned IDs to {len(all_parts)} parts")
    
    # Assign colors to parts
    color_generator.assign_colors_to_parts(all_parts)
    print(f"  Assigned colors to parts")
    
    # Compute assembly bounding box
    if all_parts:
        all_mins = []
        all_maxs = []
        for part in all_parts:
            if part.geometry_data and part.geometry_data.bounding_box:
                bbox = part.geometry_data.bounding_box
                all_mins.append(bbox.min_point)
                all_maxs.append(bbox.max_point)
        
        if all_mins and all_maxs:
            min_x = min(p[0] for p in all_mins)
            min_y = min(p[1] for p in all_mins)
            min_z = min(p[2] for p in all_mins)
            max_x = max(p[0] for p in all_maxs)
            max_y = max(p[1] for p in all_maxs)
            max_z = max(p[2] for p in all_maxs)
            
            assembly.bounding_box = BoundingBox(
                min_point=(min_x, min_y, min_z),
                max_point=(max_x, max_y, max_z)
            )
    
    print(f"  Bounding box computed")
    
    # Initialize renderer with headless mode option
    if headless_mode:
        print(f"  [HEADLESS MODE] Enabled - Display will reset aggressively after each render")
    renderer = Renderer(output_resolution=(1920, 1080), headless_mode=headless_mode)
    
    # Create standard views from assembly bounding box
    views = View.create_standard_views(assembly.bounding_box)
    view_names = ['iso1', 'iso2']
    
    # Render each step incrementally with folder organization
    results = {"rendered_steps": [], "errors": []}
    
    for step in steps:
        step_id = step['step_id']
        belongs_to = step.get('belongs_to', 'Assembly (basic config)')  # New field
        
        # Build filename components for flat structure
        # Format: {Step_ID}_{belongs_to}_{basepart}_{joining_parts}_{joining_process}_{view}.png
        base_part = step.get('base_part', 'unknown')
        joining_part = step.get('joining_part', 'none')
        joining_process = step.get('joining_process', 'unknown')
        
        # Clean up joining_part for filename (handle lists)
        if isinstance(joining_part, list):
            joining_part_str = "+".join(str(p) for p in joining_part[:3])  # Limit to 3 parts
            if len(joining_part) > 3:
                joining_part_str += f"+{len(joining_part)-3}more"
        else:
            joining_part_str = str(joining_part) if joining_part else 'none'
        
        # Sanitize all components
        belongs_to_clean = sanitize_filename(belongs_to, max_length=30)
        base_part_clean = sanitize_filename(base_part, max_length=20)
        joining_part_clean = sanitize_filename(joining_part_str, max_length=40)
        joining_process_clean = sanitize_filename(joining_process, max_length=20)
        
        # For backward compatibility
        if belongs_to == "Assembly (basic config)":
            subassembly_id = None
        else:
            subassembly_id = belongs_to.replace("Subassy ", "SA")  # "Subassy 1" -> "SA1"
        
        # All images go directly into output_dir (no subfolders!)
        step_output_dir = output_dir
        
        # Build filename following stepparser convention: step_01_iso1_transp_0_3.png
        # Format: step_{id}_{view}_{transp}.png (simplified, consistent with stepparser)
        print(f"\n--- Rendering {belongs_to} / Step {step_id} ---")
        
        # Collect all part IDs for this step
        part_ids = set()
        
        # New simplified logic: accumulate parts based on belongs_to
        if belongs_to == "Assembly (basic config)":
            # Main assembly: include all parts from main assembly steps up to current step
            for s in steps:
                if s.get('belongs_to', 'Assembly (basic config)') == 'Assembly (basic config)' and s['step_id'] <= step_id:
                    # Add expanded base_part
                    if '_expanded_base_parts' in s:
                        part_ids.update(s['_expanded_base_parts'])
                    
                    # Add expanded joining_part
                    if '_expanded_joining_parts' in s:
                        part_ids.update(s['_expanded_joining_parts'])
        else:
            # Subassembly: include only parts from THIS subassembly's steps
            for s in steps:
                if s.get('belongs_to') == belongs_to and s['step_id'] <= step_id:
                    # Add expanded base_part
                    if '_expanded_base_parts' in s:
                        part_ids.update(s['_expanded_base_parts'])
                    
                    # Add expanded joining_part
                    if '_expanded_joining_parts' in s:
                        part_ids.update(s['_expanded_joining_parts'])
        
        part_ids = list(part_ids)
        
        # Skip rendering if no parts to render
        if not part_ids:
            print(f"  [SKIP] No parts to render for this step")
            step_results = {"step_id": step_id, "belongs_to": belongs_to, "subassembly_id": subassembly_id, "views": {}}
            results["rendered_steps"].append(step_results)
            continue
        
        print(f"Parts to render: {part_ids}")
        
        step_results = {"step_id": step_id, "belongs_to": belongs_to, "subassembly_id": subassembly_id, "views": {}}
        
        # Render all views with conditional transparency values
        # ISO views: render with all transparency values (0.0, 0.3, etc.)
        # Explosion views: render ONLY with 0.0 (opaque)
        # Section views: render ONLY with 0.0 (opaque)
        
        for transparency in transparency_values:
            # Build transparency suffix (matches stepparser format)
            if transparency == 0.0:
                transp_suffix = "_transp_0_0"  # Explicit 0.0 for consistency
            else:
                # Format: transp_0_3 for 0.3, transp_0_2 for 0.2
                transp_str = str(transparency).replace(".", "_")
                transp_suffix = f"_transp_{transp_str}"
            
            for view, view_name in zip(views, view_names):
                # === STANDARD ISO VIEW ===
                # Render with ALL transparency values
                # Stepparser convention: step_01_iso1_transp_0_3.png
                output_filename = f"step_{step_id:02d}_{view_name}{transp_suffix}.png"
                output_path = step_output_dir / output_filename
                
                try:
                    renderer.render_assembly_step(assembly, part_ids, view, str(output_path), transparency=transparency)
                    print(f"  ✓ Rendered {output_filename}")
                    
                    # Store in results with transp suffix in key
                    result_key = f"{view_name}{transp_suffix}"
                    step_results["views"][result_key] = str(output_path)
                    
                except Exception as e:
                    error_msg = f"Failed to render step {step_id} {view_name} (transp={transparency}): {str(e)}"
                    print(f"  ✗ {error_msg}")
                    
                    # Save error placeholder
                    error_filename = f"step_{step_id:02d}_{view_name}{transp_suffix}_error.png"
                    error_path = step_output_dir / error_filename
                    result_key = f"{view_name}{transp_suffix}"
                    step_results["views"][result_key] = str(error_path)
                    results["errors"].append({
                        "step_id": step_id,
                        "belongs_to": belongs_to,
                        "view": view_name,
                        "transparency": transparency,
                        "error": str(e)
                    })
                
                # === EXPLOSION VIEW ===
                # Render ONLY with transparency 0.0 (opaque)
                # Render only parts assembled up to current step (not all parts in assembly)
                if transparency == 0.0:
                    explosion_filename = f"step_{step_id:02d}_{view_name}_exp{transp_suffix}.png"
                    explosion_path = step_output_dir / explosion_filename
                    
                    try:
                        renderer.render_explosion_view(assembly, view, str(explosion_path), 
                                                       explosion_factor=2.5, transparency=transparency,
                                                       part_ids=part_ids)
                        print(f"  ✓ Rendered {explosion_filename}")
                        
                        # Store in results with _exp suffix in key
                        result_key = f"{view_name}_exp{transp_suffix}"
                        step_results["views"][result_key] = str(explosion_path)
                        
                    except Exception as e:
                        error_msg = f"Failed to render explosion step {step_id} {view_name} (transp={transparency}): {str(e)}"
                        print(f"  ✗ {error_msg}")
                        
                        # Save error placeholder
                        explosion_error_filename = f"step_{step_id:02d}_{view_name}_exp{transp_suffix}_error.png"
                        explosion_error_path = step_output_dir / explosion_error_filename
                        result_key = f"{view_name}_exp{transp_suffix}"
                        step_results["views"][result_key] = str(explosion_error_path)
                        results["errors"].append({
                            "step_id": step_id,
                            "belongs_to": belongs_to,
                            "view": view_name,
                            "view_type": "explosion",
                            "transparency": transparency,
                            "error": str(e)
                        })
                
                # === SECTION VIEWS (Before & After) ===
                # Render ONLY with transparency 0.0 (opaque)
                if transparency == 0.0:
                    # Compute part_ids_before: all parts accumulated up to previous step
                    part_ids_before = set()
                    if belongs_to == "Assembly (basic config)":
                        for s in steps:
                            if s.get('belongs_to', 'Assembly (basic config)') == 'Assembly (basic config)' and s['step_id'] < step_id:
                                if '_expanded_base_parts' in s:
                                    part_ids_before.update(s['_expanded_base_parts'])
                                if '_expanded_joining_parts' in s:
                                    part_ids_before.update(s['_expanded_joining_parts'])
                    else:
                        for s in steps:
                            if s.get('belongs_to') == belongs_to and s['step_id'] < step_id:
                                if '_expanded_base_parts' in s:
                                    part_ids_before.update(s['_expanded_base_parts'])
                                if '_expanded_joining_parts' in s:
                                    part_ids_before.update(s['_expanded_joining_parts'])
                    
                    part_ids_before = list(part_ids_before)
                    part_ids_after = part_ids  # Already computed above as accumulated up to current step
                    
                    # Render section views for all 3 planes, before and after
                    plane_configs = [
                        ("xy", "render_section_view"),
                        ("xz", "render_section_view_xz"),
                        ("yz", "render_section_view_yz")
                    ]
                    
                    for plane_name, render_method_name in plane_configs:
                        for state, state_part_ids in [("before", part_ids_before), ("after", part_ids_after)]:
                            # Skip rendering if no parts
                            if not state_part_ids:
                                continue
                            
                            # Build output filename (entropy suffix will be added by render method)
                            output_filename = f"step_{step_id:02d}_section_{plane_name}_{state}{transp_suffix}.png"
                            output_path = step_output_dir / output_filename
                            
                            try:
                                render_method = getattr(renderer, render_method_name)
                                # Use cutting plane from AFTER state for both BEFORE and AFTER
                                reference_part = part_ids_after[-1] if part_ids_after else state_part_ids[-1]
                                # render_section_view* methods handle entropy calculation + filename update internally
                                render_method(assembly, state_part_ids, str(output_path), transparency=transparency,
                                            reference_part_id=reference_part)
                                
                                # Find the actual rendered file (with entropy in name)
                                # Pattern: step_01_section_xy_before_entropy_*.png
                                pattern = f"step_{step_id:02d}_section_{plane_name}_{state}{transp_suffix}_entropy_*.png"
                                rendered_files = list(step_output_dir.glob(pattern))
                                
                                if rendered_files:
                                    final_path = rendered_files[0]  # Should only be one match
                                    
                                    # Extract entropy from filename
                                    import re
                                    match = re.search(r'entropy_(\d+)_(\d+)', final_path.name)
                                    image_entropy = 0.0
                                    if match:
                                        entropy_str = f"{match.group(1)}.{match.group(2)}"
                                        image_entropy = float(entropy_str)
                                    
                                    print(f"  ✓ Rendered {final_path.name}")
                                    
                                    # Store in results with entropy score
                                    result_key = f"section_{plane_name}_{state}{transp_suffix}"
                                    step_results["views"][result_key] = str(final_path)
                                    
                                    # Track entropy separately
                                    if "entropy" not in step_results:
                                        step_results["entropy"] = {}
                                    step_results["entropy"][result_key] = image_entropy
                                else:
                                    print(f"  ⚠ Rendered but entropy filename not found for {plane_name} {state}")
                                
                            except Exception as e:
                                error_msg = f"Failed to render section {plane_name} {state} for step {step_id}: {str(e)}"
                                print(f"  ✗ {error_msg}")
                                results["errors"].append({
                                    "step_id": step_id,
                                    "belongs_to": belongs_to,
                                    "view": f"section_{plane_name}_{state}",
                                    "view_type": "section",
                                    "transparency": transparency,
                                    "error": str(e)
                                })
                    #                 
                    #                 # Extract entropy from filename
                    #                 import re
                    #                 match = re.search(r'entropy_(\d+)_(\d+)', final_path.name)
                    #                 image_entropy = 0.0
                    #                 if match:
                    #                     entropy_str = f"{match.group(1)}.{match.group(2)}"
                    #                     image_entropy = float(entropy_str)
                    #                 
                    #                 print(f"  ✓ Rendered {final_path.name}")
                    #                 
                    #                 # Store in results with entropy score
                    #                 result_key = f"section_{plane_name}_{state}{transp_suffix}"
                    #                 step_results["views"][result_key] = str(final_path)
                    #                 
                    #                 # Track entropy separately
                    #                 if "entropy" not in step_results:
                    #                     step_results["entropy"] = {}
                    #                 step_results["entropy"][result_key] = image_entropy
                    #             else:
                    #                 print(f"  ⚠ Rendered but entropy filename not found for {plane_name} {state}")
                    #             
                    #         except Exception as e:
                    #             error_msg = f"Failed to render section {plane_name} {state} for step {step_id}: {str(e)}"
                    #             print(f"  ✗ {error_msg}")
                    #             results["errors"].append({
                    #                 "step_id": step_id,
                    #                 "belongs_to": belongs_to,
                    #                 "view": f"section_{plane_name}_{state}",
                    #                 "view_type": "section",
                    #                 "transparency": transparency,
                    #                 "error": str(e)
                    #             })
        
        results["rendered_steps"].append(step_results)
    
    # Save rendering summary
    summary_path = output_dir / "rendering_summary.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    
    print(f"\\n" + "="*80)
    print(f"RENDERING COMPLETE")
    print(f"  Total steps: {len(steps)}")
    print(f"  Successful: {len(results['rendered_steps'])}")
    print(f"  Errors: {len(results['errors'])}")
    print(f"  Output: {output_dir}")
    print("="*80)
    
    # Return standardized result dict for workflow integration
    return {
        "status": "success",
        "output_dir": str(output_dir),
        "renderings_count": len(results['rendered_steps']),
        "errors_count": len(results['errors']),
        "steps_rendered": results['rendered_steps'],
    }


# ============================================================================
# HELPER FUNCTIONS FOR LLM VALIDATION
# ============================================================================

def attach_images_by_keywords(searchdir: str | Path, keywords: List[str]) -> List[Dict[str, Any]]:
    """
    Lädt Bilder aus searchdir gefiltert nach Keywords im Dateinamen.
    Sucht NICHT rekursiv - nur direkt im Ordner!
    
    Args:
        searchdir: Directory to search for images (does NOT search subdirs)
        keywords: Keywords to match in filenames (case-insensitive)
    
    Returns:
        List of {"path": str, "filename": str, "b64": str, "mime": str}
    """
    import base64
    
    searchdir = Path(searchdir)
    matched_images = []
    
    if not searchdir.exists():
        return matched_images
    
    # Normalize keywords: strip whitespace (handles YAML formatting quirks)
    keywords = [kw.strip() for kw in keywords] if keywords else []
    

    from agent.tools import matches_image_keyword
    for img_file in searchdir.glob("*.png"):
        if any(matches_image_keyword(img_file.name, kw) for kw in keywords):
            try:
                with open(img_file, 'rb') as f:
                    img_b64 = base64.b64encode(f.read()).decode('utf-8')
                matched_images.append({
                    "path": str(img_file),
                    "filename": img_file.name,
                    "b64": img_b64,
                    "mime": "image/png"
                })
            except Exception as e:
                print(f"[WARNING] Failed to load image {img_file.name}: {e}")
    
    return matched_images


# Note: attach_jsons_by_keywords and _resolve_bom_jsons removed - use extract_json_keys_from_file from tools.py instead


# ============================================================================
# LLM-BASED STEP VALIDATION (Redesigned with BOM Integration)
# ============================================================================

def validate_assembly_sequence_step(
    step_number: int,
    step_data: Dict[str, Any],
    bom_data: Dict[str, Any],
    step_images: List[Dict[str, Any]],
    prior_step_images: List[Dict[str, Any]],
    finished_assy_images: List[Dict[str, Any]],
    parts_json_keys: List[str],
    settings: Dict[str, Any],
) -> Optional[AssemblyStepValidation]:
    """
    Validate a single assembly step using LLM with multimodal input.
    
    NEW Design (matching FFA pattern):
    - Loads part metadata from BOM (with JSON-key filtering)
    - Uses prior-step images for BEFORE/AFTER context
    - Downscales images for token efficiency
    - Clean separation of concerns
    
    Args:
        step_number: Step to validate (1-indexed)
        step_data: Step dict from assembly_sequence.json
        bom_data: Loaded BOM data (with "parts" list)
        step_images: Current step renderings (AFTER state)
        prior_step_images: Prior step renderings (BEFORE state, empty for step 1)
        finished_assy_images: Complete assembly reference images
        parts_json_keys: Keys to extract from BOM for parts
        settings: Config dict with prompt IDs, etc.
    
    Returns:
        AssemblyStepValidation object or None if error
    """
    from agent.structured_output import AssemblyStepValidation
    
    print(f"\n[STEP {step_number}] Validating...")
    
    # =====================================================================
    # 1. Extract Step Information
    # =====================================================================
    
    step_description = step_data.get("step_description", "N/A")
    base_part_id = step_data.get("base_part")
    joining_part_id = step_data.get("joining_part")  # Can be str, list, or None
    joining_process = step_data.get("joining_process", "N/A")
    belongs_to = step_data.get("belongs_to", "Assembly (basic config)")
    
    print(f"  Description: {step_description[:60]}...")
    print(f"  Base part: {base_part_id}")
    print(f"  Joining part: {joining_part_id}")
    print(f"  Process: {joining_process}")
    
    # =====================================================================
    # 2. Load Part Metadata from BOM (with filtering)
    # =====================================================================
    
    base_metadata = {}
    joining_metadata = {}
    
    # Load base part metadata
    if base_part_id:
        base_metadata = load_part_metadata_from_bom(base_part_id, bom_data, parts_json_keys)
        if not base_metadata:
            print(f"  [WARNING] Base part metadata not found in BOM: {base_part_id}")
            base_metadata = {"part_id": base_part_id}
    
    # Load joining part metadata (handle list case)
    joining_part_for_metadata = joining_part_id
    if isinstance(joining_part_id, list) and len(joining_part_id) > 0:
        joining_part_for_metadata = joining_part_id[0]
        print(f"  [INFO] Multiple joining parts - using '{joining_part_for_metadata}' for metadata")
    
    if joining_part_for_metadata:
        joining_metadata = load_part_metadata_from_bom(joining_part_for_metadata, bom_data, parts_json_keys)
        if not joining_metadata:
            print(f"  [WARNING] Joining part metadata not found in BOM: {joining_part_for_metadata}")
            joining_metadata = {"part_id": joining_part_for_metadata}
    
    # =====================================================================
    # 3. Load System + Human Prompts
    # =====================================================================
    
    try:
        from agent.prompt_store import get_system_and_human_prompts
        system_prompt, human_prompt_template = get_system_and_human_prompts("ASV", settings)
        print(f"  ✓ Loaded prompts")
    except Exception as e:
        print(f"  [ERROR] Could not load prompts: {e}")
        return None
    
    # =====================================================================
    # 4. Build User Prompt with Multimodal Content
    # =====================================================================
    
    # Build metadata context
    metadata_context = f"""
=== STEP {step_number} INFORMATION ===

**Step Description:** {step_description}
**Belongs to:** {belongs_to}
**Joining Process:** {joining_process}

**Base Part ({base_part_id or 'None'}):**
```json
{json.dumps(base_metadata, indent=2, ensure_ascii=False)}
```

**Joining Part ({joining_part_id or 'None'}):**
```json
{json.dumps(joining_metadata, indent=2, ensure_ascii=False)}
```
"""
    
    # Complete human prompt
    full_human_prompt = human_prompt_template + "\n\n" + metadata_context
    
    # Build multimodal message content
    message_content = [{"type": "text", "text": full_human_prompt}]
    
    # Add complete assembly images (reference)
    if finished_assy_images:
        message_content.append({
            "type": "text",
            "text": f"\n### COMPLETE ASSEMBLY (Reference - Final State):\n"
        })
        for img in finished_assy_images:
            message_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{img['mime']};base64,{img['b64']}"}
            })
    
    # Add prior step images (BEFORE state) if available
    if prior_step_images:
        message_content.append({
            "type": "text",
            "text": f"\n### PRIOR STEP (Step {step_number - 1}) - Assembly State BEFORE Current Step:\n"
        })
        for img in prior_step_images:
            message_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{img['mime']};base64,{img['b64']}"}
            })
    
    # Add current step images (AFTER state)
    if step_images:
        message_content.append({
            "type": "text",
            "text": f"\n### CURRENT STEP (Step {step_number}) - Assembly State AFTER This Step:\n"
        })
        for img in step_images:
            message_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{img['mime']};base64,{img['b64']}"}
            })
    
    # =====================================================================
    # 5. Call LLM with Structured Output
    # =====================================================================
    
    print(f"  Calling LLM...")
    
    try:
        llm = _get_img_describer_llm(max_completion_tokens=2000)
        llm_structured = llm.with_structured_output(AssemblyStepValidation, include_raw=True)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message_content}
        ]
        
        response = invoke_with_retry(llm_structured, messages)
        
        if isinstance(response, dict) and "parsed" in response:
            validation_result = response["parsed"]
            raw_msg = response.get("raw")
        else:
            validation_result = response
            raw_msg = None
        
        print(f"  ✓ LLM response received")
        print(f"    Valid: {validation_result.is_valid}")
        print(f"    Confidence: {validation_result.confidence}%")
        print(f"    Risk: {validation_result.risk_level}")
        
        # Convert Pydantic object to dict to avoid serialization warnings
        return validation_result.model_dump()
        
    except Exception as e:
        print(f"  [ERROR] LLM call failed: {e}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================================
# OLD VERSION (kept for reference, will be removed)
# ============================================================================

def validate_assembly_sequence_step_OLD(
    step_number: int,
    assembly_name: str,
    experiment_name: str,
    sequence_data: Dict[str, Any],
    assembly_sequence_json: Dict[str, Any],
    settings: Dict[str, Any],
    exp_output_dir: Path = None,
) -> Optional[AssemblyStepValidation]:
    """
    Validate a single assembly step using LLM with multimodal input.
    
    Args:
        step_number: Step to validate (1-indexed)
        assembly_name: Name of assembly (e.g., 'IPA_Cranfield')
        experiment_name: Experiment folder name (e.g., 'direct_run')
        sequence_data: Complete assembly sequence (already loaded)
        assembly_sequence_json: Raw assembly_sequence.json content
        settings: Config dict from default_settings.yaml or experiment.yaml
        exp_output_dir: Optional output directory override
    
    Returns:
        AssemblyStepValidation object or None if error
    """
    base_dir = Path(__file__).parent.parent
    
    # Get settings (should be passed from workflow with all defaults from settings.yaml)
    asv_json_keywords = settings.get("ASV_json_keywords")
    asv_step_img_keywords = settings.get("ASV_step_img_keywords")
    asv_finished_assy_keywords = settings.get("ASV_finished_assy_keywords")
    
    print(f"\n[STEP {step_number}] Validating...")
    
    # =====================================================================
    # 1. Load Context Data
    # =====================================================================
    
    # Load complete assembly image (from stepparser folder)
    # New convention: assembly_{name} folders
    # Legacy: {name}.STEP folders
    stepparser_assy_dir = base_dir / "data" / "processed" / "stepparser" / assembly_name / f"assembly_{assembly_name}"
    if not stepparser_assy_dir.exists():
        stepparser_assy_dir = base_dir / "data" / "processed" / "stepparser" / assembly_name / f"{assembly_name}.STEP"
    
    complete_assy_images = attach_images_by_keywords(stepparser_assy_dir, asv_finished_assy_keywords)
    
    if not complete_assy_images:
        print(f"      [WARNING] No complete assembly images found in {stepparser_assy_dir}")
        complete_assy_images = []
    else:
        print(f"      ✓ Loaded {len(complete_assy_images)} complete assembly image(s)")
    
    # Load merged BOM JSON (from experiment folder) - NEW: Use extract_json_keys_from_file
    # Use provided exp_output_dir or compute from defaults
    if exp_output_dir is None:
        exp_output_dir = base_dir / "data" / "experiments" / experiment_name / assembly_name
    else:
        exp_output_dir = Path(exp_output_dir)
    
    # Load settings for JSON filtering
    from agent.tools import _get_experiment_settings
    settings = _get_experiment_settings()
    json_file_keyword = settings.get("ASV_json_file_keyword", "BOM_enriched")
    json_keys = settings.get("ASV_json_keys", ["part_id", "volume"])
    part_id_name_list = settings.get("ASV_part_id_name_list", [])
    
    # Find JSON file matching keyword (check run dir and parent)
    search_dirs = [exp_output_dir]
    if exp_output_dir.name.startswith("assembly_sequence_run"):
        search_dirs.append(exp_output_dir.parent)
    
    json_path = None
    bom_dir = None
    for candidate_dir in search_dirs:
        for json_file in candidate_dir.glob("*.json"):
            if json_file_keyword.lower() in json_file.name.lower():
                json_path = json_file
                bom_dir = candidate_dir
                break
        if json_path:
            break
    
    extracted_bom = {}
    if json_path:
        extracted_bom = extract_json_keys_from_file(json_path, json_keys, part_id_name_list)
        source_note = "" if bom_dir == exp_output_dir else f" (from {bom_dir})"
        print(f"      ✓ Loaded and filtered: {json_path.name}{source_note}")
        if "parts" in extracted_bom:
            print(f"      → Extracted {len(extracted_bom['parts'])} parts with keys: {json_keys}")
    else:
        print(f"      [WARNING] No BOM file found matching keyword '{json_file_keyword}'")
    
    # Load step images (from sequence_renderings)
    renderings_dir = exp_output_dir / "sequence_renderings"
    step_images = attach_images_by_keywords(renderings_dir, asv_step_img_keywords)
    
    # Filter to current step only
    # New format: Step_01_Subassy1_part001_part002_Insert_isometric.png
    # Old format: step_01_isometric.png
    step_prefix_new = f"Step_{step_number:02d}_"
    step_prefix_old_padded = f"step_{step_number:02d}_"
    step_prefix_old_plain = f"step_{step_number}_"
    
    step_images = [img for img in step_images 
                   if (step_prefix_new in img["filename"] or 
                       step_prefix_old_padded in img["filename"] or 
                       step_prefix_old_plain in img["filename"])]
    
    if not step_images:
        print(f"      [WARNING] No step images found for step {step_number}")
        print(f"                Looking for: {step_prefix_new}* or {step_prefix_old_padded}* in {renderings_dir}")
    else:
        print(f"      ✓ Loaded {len(step_images)} step image(s)")
    
    # =====================================================================
    # 2. Get Step Information
    # =====================================================================
    
    steps = sequence_data.get('steps', [])
    if step_number < 1 or step_number > len(steps):
        print(f"      [ERROR] Step {step_number} out of range (total: {len(steps)})")
        return None
    
    current_step = steps[step_number - 1]  # 0-indexed
    
    # Build parts list for this step
    parts_in_step = set()
    for i in range(step_number):
        s = steps[i]
        if s.get("base_part"):
            parts_in_step.add(s["base_part"])
        if s.get("joining_part"):
            joining_part = s["joining_part"]
            # Handle both str and List[str] cases
            if isinstance(joining_part, list):
                parts_in_step.update(joining_part)
            else:
                parts_in_step.add(joining_part)
    
    step_parts_list = "\n".join([f"  - {part}" for part in sorted(parts_in_step)])
    
    # =====================================================================
    # 3. Load System + Human Prompts
    # =====================================================================
    
    try:
        from agent.prompt_store import get_system_and_human_prompts
        system_prompt, human_prompt_template = get_system_and_human_prompts("ASV", settings)
        print(f"      ✓ Loaded prompts from prompts.yaml")
    except Exception as e:
        print(f"      [ERROR] Could not load prompts: {e}")
        raise
    
    # =====================================================================
    # 4. Build User Prompt with Multimodal Content
    # =====================================================================
    
    user_text_parts = []
    # Start with human/task prompt
    user_text_parts.append(human_prompt_template)
    user_text_parts.append(f"\n\n=== INPUT DATA ===\n")
    user_text_parts.append(f"Assembly: {assembly_name}")
    user_text_parts.append(f"Validating STEP {step_number}\n")
    
    # Section 1: Complete assembly context
    user_text_parts.append("=== COMPLETE ASSEMBLY CONTEXT ===")
    if complete_assy_images:
        user_text_parts.append("[Image of complete assembly (isometric view) - see image attachments]")
    else:
        user_text_parts.append("[No complete assembly image available]")
    
    # Section 2: BOM and metadata
    user_text_parts.append("\n=== ASSEMBLY METADATA ===")
    if extracted_bom:
        bom_str = json.dumps(extracted_bom, indent=2)
        if len(bom_str) > 3000:
            bom_str = bom_str[:3000] + "\n... (truncated)"
        user_text_parts.append(f"File: {json_path.name if json_path else 'N/A'}")
        user_text_parts.append(f"```json\n{bom_str}\n```")
    else:
        user_text_parts.append("[No BOM data available]")
    
    # Section 3: Assembly sequence overview
    user_text_parts.append("\n=== SEQUENCE OVERVIEW ===")
    seq_str = json.dumps(assembly_sequence_json, indent=2)
    if len(seq_str) > 5000:
        seq_str = seq_str[:5000] + "\n... (truncated)"
    user_text_parts.append(f"```json\n{seq_str}\n```")
    
    # Section 4: Current step validation
    user_text_parts.append(f"\n=== STEP {step_number} VALIDATION ===")
    user_text_parts.append(f"Step Description: {current_step.get('description', 'N/A')}")
    user_text_parts.append(f"Base Part: {current_step.get('base_part', 'N/A')}")
    user_text_parts.append(f"Joining Part: {current_step.get('joining_part', 'N/A')}")
    user_text_parts.append(f"Joining Process: {current_step.get('joining_process', 'N/A')}")
    user_text_parts.append(f"\nParts present after step {step_number}:\n{step_parts_list}")
    user_text_parts.append(f"\n[Step images (isometric, front, top, side) - see image attachments]")
    
    user_text = "\n".join(user_text_parts)
    
    # =====================================================================
    # 5. Call LLM with Structured Output
    # =====================================================================
    
    print(f"      Calling LLM...")
    
    try:
        llm = _get_img_describer_llm(max_completion_tokens=2000)
        llm_structured = llm.with_structured_output(AssemblyStepValidation, include_raw=True)
        
        # Build multimodal user content
        user_content = [{"type": "text", "text": user_text}]
        
        # Add complete assembly image (if available)
        for img in complete_assy_images:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{img['mime']};base64,{img['b64']}"}
            })
        
        # Add step images (if available)
        for img in step_images:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{img['mime']};base64,{img['b64']}"}
            })
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
        
        response = invoke_with_retry(llm_structured, messages)
        
        if isinstance(response, dict) and "parsed" in response:
            validation_result = response["parsed"]
            raw_msg = response.get("raw")
        else:
            validation_result = response
            raw_msg = None
        
        print(f"      ✓ LLM response received")
        print(f"        Valid: {validation_result.is_valid}")
        print(f"        Confidence: {validation_result.confidence}%")
        print(f"        Risk: {validation_result.risk_level}")
        
        # Convert Pydantic object to dict to avoid serialization warnings
        return validation_result.model_dump()
        
    except Exception as e:
        print(f"      [ERROR] LLM call failed: {e}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================================
# ASSEMBLY SEQUENCE VALIDATION (Main Function - Redesigned)
# ============================================================================

def validate_assembly_sequence(
    assembly_name: str,
    experiment_name: str = "direct_run",
    settings: Dict[str, Any] = None,
    exp_output_dir: Path = None,
) -> Dict[str, Any]:
    """
    Validate assembly sequence with per-step LLM calls (NEW design with BOM integration).
    
    NEW Features:
    - Loads part metadata from BOM (with JSON-key filtering for token efficiency)
    - Uses prior-step images for BEFORE/AFTER context
    - Image downscaling for cost reduction
    - Keyword-based image filtering
    
    Saves results to:
    - assembly_sequence_validation/step_{N:02d}_validation.json for each step
    - assembly_sequence_validation/assembly_sequence_validation_merged.json for summary
    
    Args:
        assembly_name: Name of assembly (e.g., 'IPA_Cranfield')
        experiment_name: Experiment folder name (default: 'direct_run')
        settings: Config dict with ASV_* keys (if None, uses defaults)
        exp_output_dir: Optional explicit output directory path (overrides default)
    
    Returns:
        Dict with overall validation results
    """
    from agent.structured_output import AssemblySequenceValidation
    
    print("\n" + "="*80)
    print(f"VALIDATING ASSEMBLY SEQUENCE: {assembly_name}")
    print("="*80)
    
    # Setup paths
    base_dir = Path(__file__).parent.parent
    
    # Use provided exp_output_dir or compute from defaults
    if exp_output_dir is None:
        exp_output_dir = base_dir / "data" / "experiments" / experiment_name / assembly_name
    else:
        exp_output_dir = Path(exp_output_dir)
    
    # NEW: Check if assembly_sequence is in a assembly_sequence_run* subfolder
    # This happens when ASG/ASV nodes iterate (run_1, run_2, etc.)
    sequence_file = exp_output_dir / "assembly_sequence.json"
    renderings_dir = exp_output_dir / "sequence_renderings"
    
    # If not found directly, check for assembly_sequence_run* subdirectories
    if not sequence_file.exists():
        # Find latest run folder
        run_folders = sorted(exp_output_dir.glob("assembly_sequence_run*"), reverse=True)
        if run_folders:
            latest_run = run_folders[0]  # Most recent run
            sequence_file = latest_run / "assembly_sequence.json"
            renderings_dir = latest_run / "sequence_renderings"
            print(f"  Using iteration folder: {latest_run.name}")
    
    validation_output_dir = exp_output_dir / "assembly_sequence_validation"
    validation_output_dir.mkdir(exist_ok=True, parents=True)
    
    # Load settings (should be passed from workflow or load defaults)
    if settings is None:
        from agent.prompt_store import load_experiment_settings
        settings = load_experiment_settings()
    
    # Extract ASV settings
    json_keywords = settings.get("ASV_json_keywords", ["merged_bom"])
    parts_json_keys = settings.get("ASV_parts_json_keys", ["part_id", "part_name_guess"])
    step_img_keywords = settings.get("ASV_step_img_keywords", ["iso1_transp_0_3"])
    prior_step_img_keywords = settings.get("ASV_prior_step_img_keywords", ["iso1_transp_0_3"])
    finished_assy_keywords = settings.get("ASV_finished_assy_keywords", ["iso1_transp_0_3"])
    image_downscale = settings.get("image_downscale_factor", 0.5)  # Global setting
    
    print(f"\nSettings:")
    print(f"  JSON keywords: {json_keywords}")
    print(f"  Parts JSON keys: {parts_json_keys}")
    print(f"  Step img keywords: {step_img_keywords}")
    print(f"  Prior step img keywords: {prior_step_img_keywords}")
    print(f"  Image downscale: {image_downscale}")
    
    # Check prerequisites
    if not sequence_file.exists():
        error_msg = f"Assembly sequence not found: {sequence_file}"
        print(f"[ERROR] {error_msg}")
        return {"status": "error", "message": error_msg, "step_validations": [], "overall_valid": False}
    
    if not renderings_dir.exists():
        error_msg = f"Renderings not found: {renderings_dir}. Run render_assembly_steps() first!"
        print(f"[ERROR] {error_msg}")
        return {"status": "error", "message": error_msg, "step_validations": [], "overall_valid": False}
    
    # Load assembly sequence
    print(f"\n[1/4] Loading assembly sequence...")
    with open(sequence_file, 'r', encoding='utf-8') as f:
        sequence_data = json.load(f)
    
    steps = sequence_data.get('steps', [])
    if not steps:
        print("[WARNING] No assembly steps found")
        return {"status": "warning", "message": "No steps to validate", "step_validations": [], "overall_valid": False}
    
    print(f"  ✓ Loaded {len(steps)} assembly steps")
    
    # =====================================================================
    # Load BOM Data (from experiment folder)
    # =====================================================================
    
    print(f"\n[2/4] Loading BOM data...")
    
    # Find BOM file matching keywords
    search_dirs = [exp_output_dir]
    if exp_output_dir.name.startswith("assembly_sequence_run"):
        search_dirs.append(exp_output_dir.parent)  # Also check parent folder
    
    bom_path = None
    for candidate_dir in search_dirs:
        for json_file in candidate_dir.glob("*BOM*.json"):
            # Check if any keyword matches
            if any(kw.lower() in json_file.name.lower() for kw in json_keywords):
                bom_path = json_file
                break
        if bom_path:
            break
    
    if not bom_path:
        error_msg = f"BOM file not found with keywords {json_keywords} in {exp_output_dir}"
        print(f"[ERROR] {error_msg}")
        return {"status": "error", "message": error_msg, "step_validations": [], "overall_valid": False}
    
    print(f"  ✓ Found BOM: {bom_path.name}")
    
    # Load BOM data
    with open(bom_path, 'r', encoding='utf-8') as f:
        bom_data = json.load(f)
    
    bom_parts_count = len(bom_data.get("parts", []))
    print(f"  ✓ Loaded BOM with {bom_parts_count} parts")
    
    # =====================================================================
    # Load Finished Assembly Images (Reference)
    # =====================================================================
    
    print(f"\n[3/4] Loading finished assembly images...")
    
    stepparser_assy_dir = base_dir / "data" / "processed" / "stepparser" / assembly_name / f"assembly_{assembly_name}"
    if not stepparser_assy_dir.exists():
        stepparser_assy_dir = base_dir / "data" / "processed" / "stepparser" / assembly_name / f"{assembly_name}.STEP"
    
    finished_assy_images = []
    if stepparser_assy_dir.exists() and finished_assy_keywords:
        for img_file in stepparser_assy_dir.glob("*.png"):
            from agent.tools import matches_image_keyword
            if any(matches_image_keyword(img_file.name, kw) for kw in finished_assy_keywords):
                img_data = load_and_downscale_image(img_file, image_downscale)
                finished_assy_images.append(img_data)
    
    if finished_assy_images:
        print(f"  ✓ Loaded {len(finished_assy_images)} finished assembly image(s)")
    else:
        print(f"  [WARNING] No finished assembly images found")
    
    # =====================================================================
    # Per-Step Validation Loop
    # =====================================================================
    
    print(f"\n[4/4] Validating each step individually...")
    
    all_validations = []
    errors = []
    
    for step_number in range(1, len(steps) + 1):
        print(f"\n--- STEP {step_number}/{len(steps)} ---")
        
        try:
            step_data = steps[step_number - 1]
            
            # Load current step images
            step_images = []
            # NEW: Match stepparser naming convention: step_01_iso1_transp_0_3.png
            matching_images = list(renderings_dir.glob(f"step_{step_number:02d}_*.png"))
            
            # Filter by keywords
            if step_img_keywords:
                from agent.tools import matches_image_keyword
                filtered_images = []
                for img_path in matching_images:
                    if any(matches_image_keyword(img_path.name, kw) for kw in step_img_keywords):
                        filtered_images.append(img_path)
                matching_images = filtered_images
            
            # Load and downscale
            for img_path in matching_images:
                img_data = load_and_downscale_image(img_path, image_downscale)
                step_images.append(img_data)
            
            if not step_images:
                print(f"  [WARNING] No step images found for step {step_number}")
            else:
                print(f"  Loaded {len(step_images)} step image(s)")
            
            # Load prior step images (if step > 1 AND prior_step_img_keywords is set)
            prior_step_images = []
            if step_number > 1 and prior_step_img_keywords:
                prior_step_number = step_number - 1
                prior_step_data = steps[prior_step_number - 1]
                
                # Check if prior step belongs to same assembly/subassembly
                current_belongs_to = step_data.get("belongs_to", "")
                prior_belongs_to = prior_step_data.get("belongs_to", "")
                
                if current_belongs_to == prior_belongs_to:
                    # Load prior step images
                    # NEW: Match stepparser naming convention
                    prior_matching = list(renderings_dir.glob(f"step_{prior_step_number:02d}_*.png"))
                    
                    # Filter by keywords
                    if prior_step_img_keywords:
                        from agent.tools import matches_image_keyword
                        filtered_prior = []
                        for img_path in prior_matching:
                            if any(matches_image_keyword(img_path.name, kw) for kw in prior_step_img_keywords):
                                filtered_prior.append(img_path)
                        prior_matching = filtered_prior
                    
                    # Load and downscale
                    for img_path in prior_matching:
                        img_data = load_and_downscale_image(img_path, image_downscale)
                        prior_step_images.append(img_data)
                    
                    if prior_step_images:
                        print(f"  Loaded {len(prior_step_images)} prior step image(s) (Step {prior_step_number})")
                else:
                    print(f"  [INFO] Prior step belongs to different assembly - skipping prior images")
            
            # Validate step
            validation_result = validate_assembly_sequence_step(
                step_number=step_number,
                step_data=step_data,
                bom_data=bom_data,
                step_images=step_images,
                prior_step_images=prior_step_images,
                finished_assy_images=finished_assy_images,
                parts_json_keys=parts_json_keys,
                settings=settings,
            )
            
            if validation_result is None:
                errors.append({
                    "step": step_number,
                    "error": "LLM validation returned None"
                })
                continue
            
            # Ensure step_number is set correctly
            validation_result.step_number = step_number
            all_validations.append(validation_result)
            
            # Save individual step validation
            step_json_path = validation_output_dir / f"step_{step_number:02d}_validation.json"
            with open(step_json_path, 'w', encoding='utf-8') as f:
                f.write(validation_result.model_dump_json(indent=2))
            print(f"  ✓ Saved to {step_json_path.name}")
            
        except Exception as e:
            print(f"  [ERROR] Step {step_number} validation failed: {e}")
            import traceback
            traceback.print_exc()
            errors.append({
                "step": step_number,
                "error": str(e)
            })
            continue
    
    # =====================================================================
    # Compute Overall Results & Save Merged Summary
    # =====================================================================
    
    print(f"\n[5/5] Computing validation results...")
    
    # Calculate all_parts_processed: compare parts in BOM vs parts used in sequence
    bom_parts = [p.get("part_id") for p in bom_data.get("parts", []) if p.get("part_id")]
    
    # Get parts used in sequence
    used_parts = set()
    for step in steps:
        if step.get("base_part"):
            used_parts.add(step["base_part"])
        if step.get("joining_part"):
            joining_part = step["joining_part"]
            if isinstance(joining_part, list):
                used_parts.update(joining_part)
            else:
                used_parts.add(joining_part)
    
    # Calculate missing parts
    missing_parts = [p for p in bom_parts if p not in used_parts]
    all_parts_processed = len(missing_parts) == 0
    
    if missing_parts:
        print(f"  ⚠ Missing parts: {missing_parts}")
    else:
        print(f"  ✓ All BOM parts used in sequence")
    
    # Compute overall metrics
    if all_validations:
        overall_confidence = sum(v.confidence for v in all_validations) / len(all_validations)
        overall_valid = all(v.is_valid for v in all_validations) and all_parts_processed
        
        # Overall risk = highest risk from all steps
        risk_levels = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
        max_risk_level = max(risk_levels.get(v.risk_level, 0) for v in all_validations)
        risk_level_names = ["LOW", "MEDIUM", "HIGH"]
        overall_risk_level = risk_level_names[max_risk_level]
    else:
        overall_confidence = 0.0
        overall_valid = False
        overall_risk_level = "HIGH"
    
    # Create merged validation result
    merged_validation = {
        "assembly_name": assembly_name,
        "assembly_sequence_id": sequence_data.get("assembly_sequence_id", "unknown"),
        "validation_id": str(uuid.uuid4()),
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "all_parts_processed": all_parts_processed,
        "missing_parts": missing_parts,
        "step_validations": [v.model_dump() for v in all_validations],
        "overall_confidence": overall_confidence,
        "overall_valid": overall_valid,
        "overall_risk_level": overall_risk_level,
        "validation_summary": {
            "total_steps": len(steps),
            "validated_steps": len(all_validations),
            "errors": len(errors),
            "valid_steps": sum(1 for v in all_validations if v.is_valid),
            "invalid_steps": sum(1 for v in all_validations if not v.is_valid),
            "all_parts_processed": all_parts_processed,
        },
        "errors": errors,
    }
    
    # Save merged validation
    from agent.tools import save_structured_json
    merged_path = validation_output_dir / "assembly_sequence_validation_merged.json"
    save_structured_json(merged_path, merged_validation, add_metadata=True)
    
    print(f"\n" + "="*80)
    print(f"VALIDATION COMPLETE")
    print(f"  Total steps: {len(steps)}")
    print(f"  Validated: {len(all_validations)}")
    print(f"  Valid steps: {merged_validation['validation_summary']['valid_steps']}")
    print(f"  Invalid steps: {merged_validation['validation_summary']['invalid_steps']}")
    print(f"  Errors: {len(errors)}")
    print(f"  All parts processed: {all_parts_processed}")
    if missing_parts:
        print(f"  Missing parts: {missing_parts}")
    print(f"  Overall Valid: {overall_valid}")
    print(f"  Overall Confidence: {overall_confidence:.1f}%")
    print(f"  Overall Risk: {overall_risk_level}")
    print(f"  Output: {validation_output_dir}")
    print("="*80)
    
    return merged_validation


# ============================================================================
# OLD VERSION (to be removed after testing)
# ============================================================================

def validate_assembly_sequence_OLD(
    assembly_name: str,
    experiment_name: str = "direct_run",
    settings: Dict[str, Any] = None,
    exp_output_dir: Path = None,
) -> Dict[str, Any]:
    """
    Validate assembly sequence with per-step LLM calls (OPTION A: Isolated calls).
    
    Uses complete assembly image + incremental step renderings (all 4 views)
    to validate each assembly step independently.
    
    Saves results to:
    - assembly_sequence_validation/{step_N_validation.json} for each step
    - assembly_sequence_validation/assembly_sequence_validation_merged.json for summary
    
    Args:
        assembly_name: Name of assembly (e.g., 'IPA_Cranfield')
        experiment_name: Experiment folder name (default: 'direct_run')
        settings: Config dict with ASV_* keys (if None, uses defaults)
        exp_output_dir: Optional explicit output directory path (overrides default)
    
    Returns:
        Dict with overall validation results
    """
    from agent.structured_output import AssemblySequenceValidation
    
    print("\n" + "="*80)
    print(f"VALIDATING ASSEMBLY SEQUENCE: {assembly_name}")
    print("="*80)
    
    # Setup paths
    base_dir = Path(__file__).parent.parent
    
    # Use provided exp_output_dir or compute from defaults
    if exp_output_dir is None:
        exp_output_dir = base_dir / "data" / "experiments" / experiment_name / assembly_name
    else:
        exp_output_dir = Path(exp_output_dir)
    
    sequence_file = exp_output_dir / "assembly_sequence.json"
    renderings_dir = exp_output_dir / "sequence_renderings"
    validation_output_dir = exp_output_dir / "assembly_sequence_validation"
    validation_output_dir.mkdir(exist_ok=True, parents=True)
    
    # Load settings (should be passed from workflow or load defaults)
    if settings is None:
        from agent.prompt_store import load_experiment_settings
        settings = load_experiment_settings()
    
    # Check prerequisites
    if not sequence_file.exists():
        error_msg = f"Assembly sequence not found: {sequence_file}"
        print(f"[ERROR] {error_msg}")
        return {"status": "error", "message": error_msg, "step_validations": [], "overall_valid": False}
    
    if not renderings_dir.exists():
        error_msg = f"Renderings not found: {renderings_dir}. Run render_assembly_steps() first!"
        print(f"[ERROR] {error_msg}")
        return {"status": "error", "message": error_msg, "step_validations": [], "overall_valid": False}
    
    # Load assembly sequence
    print(f"\n[1/3] Loading assembly sequence...")
    with open(sequence_file, 'r', encoding='utf-8') as f:
        sequence_data = json.load(f)
    
    steps = sequence_data.get('steps', [])
    if not steps:
        print("[WARNING] No assembly steps found")
        return {"status": "warning", "message": "No steps to validate", "step_validations": [], "overall_valid": False}
    
    print(f"  ✓ Loaded {len(steps)} assembly steps")
    
    # =====================================================================
    # Per-Step Validation Loop (OPTION A: Isolated calls)
    # =====================================================================
    
    print(f"\n[2/3] Validating each step individually...")
    
    all_validations = []
    errors = []
    
    for step_number in range(1, len(steps) + 1):
        print(f"\n--- STEP {step_number}/{len(steps)} ---")
        
        try:
            validation_result = validate_assembly_sequence_step(
                step_number=step_number,
                assembly_name=assembly_name,
                experiment_name=experiment_name,
                sequence_data=sequence_data,
                assembly_sequence_json=sequence_data,
                settings=settings,
                exp_output_dir=exp_output_dir,
            )
            
            if validation_result is None:
                errors.append({
                    "step": step_number,
                    "error": "LLM validation returned None"
                })
                continue
            
            # Ensure step_number is set correctly
            validation_result.step_number = step_number
            all_validations.append(validation_result)
            
            # Save individual step validation
            step_json_path = validation_output_dir / f"step_{step_number:02d}_validation.json"
            with open(step_json_path, 'w', encoding='utf-8') as f:
                f.write(validation_result.model_dump_json(indent=2))
            print(f"      ✓ Saved to {step_json_path.name}")
            
        except Exception as e:
            print(f"      [ERROR] Step {step_number} validation failed: {e}")
            import traceback
            traceback.print_exc()
            errors.append({
                "step": step_number,
                "error": str(e)
            })
            continue
    
    # =====================================================================
    # Compute Overall Results & Save Merged Summary
    # =====================================================================
    
    print(f"\n[3/3] Computing validation results...")
    
    # Calculate all_parts_processed: compare parts in BOM vs parts used in sequence
    json_keywords = settings.get("ASV_json_keywords")
    bom_parts: List[str] = []
    try:
        bom_jsons, bom_dir = _resolve_bom_jsons(exp_output_dir, json_keywords)
        for bom in bom_jsons:
            parts = (bom.get("content") or {}).get("parts")
            if parts:
                bom_parts = [p.get("part_id") for p in parts if p.get("part_id")]
                break
        if not bom_jsons:
            print(f"      [WARNING] Could not locate merged BOM in {bom_dir}")
    except Exception as e:
        print(f"      [WARNING] Could not load BOM parts: {e}")
        bom_parts = []
    
    # Get parts used in sequence
    used_parts = set()
    for step in steps:
        if step.get("base_part"):
            used_parts.add(step["base_part"])
        if step.get("joining_part"):
            joining_part = step["joining_part"]
            if isinstance(joining_part, list):
                used_parts.update(joining_part)
            else:
                used_parts.add(joining_part)
    
    # Calculate missing parts
    missing_parts = [p for p in bom_parts if p not in used_parts]
    all_parts_processed = len(missing_parts) == 0
    
    if missing_parts:
        print(f"      ⚠ Missing parts: {missing_parts}")
    else:
        print(f"      ✓ All BOM parts used in sequence")
    
    # Compute overall metrics
    if all_validations:
        overall_confidence = sum(v.confidence for v in all_validations) / len(all_validations)
        overall_valid = all(v.is_valid for v in all_validations) and all_parts_processed
        
        # Overall risk = highest risk from all steps
        risk_levels = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
        max_risk_level = max(risk_levels.get(v.risk_level, 0) for v in all_validations)
        risk_level_names = ["LOW", "MEDIUM", "HIGH"]
        overall_risk_level = risk_level_names[max_risk_level]
    else:
        overall_confidence = 0.0
        overall_valid = False
        overall_risk_level = "HIGH"
    
    # Create merged validation result
    merged_validation = {
        "assembly_name": assembly_name,
        "assembly_sequence_id": sequence_data.get("assembly_sequence_id", "unknown"),
        "validation_id": str(uuid.uuid4()),
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "all_parts_processed": all_parts_processed,
        "missing_parts": missing_parts,
        "step_validations": [v.model_dump() for v in all_validations],
        "overall_confidence": overall_confidence,
        "overall_valid": overall_valid,
        "overall_risk_level": overall_risk_level,
        "validation_summary": {
            "total_steps": len(steps),
            "validated_steps": len(all_validations),
            "errors": len(errors),
            "valid_steps": sum(1 for v in all_validations if v.is_valid),
            "invalid_steps": sum(1 for v in all_validations if not v.is_valid),
            "all_parts_processed": all_parts_processed,
        },
        "errors": errors,
    }
    
    # Save merged validation
    from agent.tools import save_structured_json
    merged_path = validation_output_dir / "assembly_sequence_validation_merged.json"
    save_structured_json(merged_path, merged_validation, add_metadata=True)
    
    print(f"\n" + "="*80)
    print(f"VALIDATION COMPLETE")
    print(f"  Total steps: {len(steps)}")
    print(f"  Validated: {len(all_validations)}")
    print(f"  Valid steps: {merged_validation['validation_summary']['valid_steps']}")
    print(f"  Invalid steps: {merged_validation['validation_summary']['invalid_steps']}")
    print(f"  Errors: {len(errors)}")
    print(f"  All parts processed: {all_parts_processed}")
    if missing_parts:
        print(f"  Missing parts: {missing_parts}")
    print(f"  Overall Valid: {overall_valid}")
    print(f"  Overall Confidence: {overall_confidence:.1f}%")
    print(f"  Overall Risk: {overall_risk_level}")
    print(f"  Output: {validation_output_dir}")
    print("="*80)
    
    return merged_validation


# ============================================================================
#                    MAIN / TESTING
# ============================================================================

def main():
    """Test Assembly Sequence Rendering + Validation standalone."""
    
    print("\n" + "="*80)
    print("ASSEMBLY SEQUENCE VALIDATION - STANDALONE TEST")
    print("="*80)
    
    if not RENDERER_AVAILABLE:
        print("\n[ERROR] Renderer not available")
        print("  Install stepparser: pip install -e stepparser/")
        return
    
    # Configuration
    assembly_name = "IPA_Cranfield"
    experiment_name = "direct_run"
    
    print(f"\nAssembly: {assembly_name}")
    print(f"Experiment: {experiment_name}")
    
    # ========================================================================
    # STEP 1: Render Assembly Steps
    # ========================================================================
    
    print("\n" + "="*80)
    print("STEP 1: RENDER ASSEMBLY STEPS")
    print("="*80)
    
    try:
        result_render = render_assembly_steps(
            assembly_name=assembly_name,
            experiment_name=experiment_name
        )
        
        if result_render.get("status") == "error":
            print(f"\n[X] Rendering failed: {result_render.get('message')}")
            return
        
        print(f"\n[v] Rendering completed")
        print(f"  Steps rendered: {len(result_render.get('rendered_steps', []))}")
        print(f"  Errors: {len(result_render.get('errors', []))}")
        
    except Exception as e:
        print(f"\n[X] EXCEPTION during rendering: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # ========================================================================
    # STEP 2: Validate Assembly Sequence
    # ========================================================================
    
    print("\n" + "="*80)
    print("STEP 2: VALIDATE ASSEMBLY SEQUENCE (TODO)")
    print("="*80)
    
    # Run validation
    try:
        result = validate_assembly_sequence(
            assembly_name=assembly_name,
            experiment_name=experiment_name
        )
        
        if result.get("status") == "error":
            print(f"\n[X] Validation failed: {result.get('message')}")
            return
        
        print(f"\n[v] Validation completed")
        print(f"  Overall valid: {result.get('overall_valid')}")
        
    except Exception as e:
        print(f"\n[X] EXCEPTION during validation: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
