"""
Assembly Sequence Generation - STANDALONE VERSION

Generiert Montagereihenfolgen basierend auf Bildern und BOM-Daten.
Multimodal LLM-Call mit GPT-4o Vision.

Diese Datei läuft UNABHÄNGIG vom Workflow_enrich_data.py.

Usage:
    python -m agent.Assembly_sequence_generation

Features:
1. Generate Assembly Sequence (multimodal LLM + Pydantic structured output)

Rendering + Validation siehe: Assembly_sequence_validation.py
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
    from agent.structured_output import AssemblySequence
except ImportError:
    from tools import _get_img_describer_llm, extract_json_keys_from_file
    from structured_output import AssemblySequence

# Note: Renderer not needed for generation (only validation)
# Kept for backwards compatibility
RENDERER_AVAILABLE = False


# ============================================================================
#                    PROMPT BUILDER UTILITIES
# ============================================================================

def attach_images_by_keywords(searchdir: str | Path, keywords: List[str], downscale_factor: float = 1.0) -> List[Dict[str, Any]]:
    """
    Lädt Bilder aus searchdir gefiltert nach Keywords.
    
    Args:
        searchdir: Directory to search for images
        keywords: Filter keywords for filenames
        downscale_factor: Image scaling factor (0.5 = half size, saves tokens)
    
    Returns:
        List of {"path": str, "filename": str, "b64": str, "mime": str}
    """
    from agent.tools import ImageLoader
    import base64
    
    loader = ImageLoader(str(searchdir))
    
    # Load images with keywords
    all_images = []
    # Normalize keywords: strip whitespace (handles YAML formatting quirks)
    keywords = [kw.strip() for kw in keywords] if keywords else []
    
    from agent.tools import matches_image_keyword
    for img_file in Path(searchdir).glob("*.png"):
        if keywords:
            if any(matches_image_keyword(img_file.name, kw) for kw in keywords):
                all_images.append(img_file)
        else:
            all_images.append(img_file)
    
    # Convert to base64 with optional downscaling
    result_images = []
    for img_path in all_images:
        if downscale_factor < 1.0:
            # Downscale image before base64 encoding
            from PIL import Image
            import io
            
            img = Image.open(img_path)
            new_width = int(img.width * downscale_factor)
            new_height = int(img.height * downscale_factor)
            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Convert to bytes
            img_buffer = io.BytesIO()
            img_resized.save(img_buffer, format='PNG')
            img_bytes = img_buffer.getvalue()
            img_b64 = base64.b64encode(img_bytes).decode('utf-8')
        else:
            # Original size
            with open(img_path, 'rb') as f:
                img_b64 = base64.b64encode(f.read()).decode('utf-8')
        
        result_images.append({
            "path": str(img_path),
            "filename": img_path.name,
            "b64": img_b64,
            "mime": "image/png"
        })
    
    return result_images


# Note: attach_jsons_by_keywords removed - use extract_json_keys_from_file from tools.py instead


def attach_additional_info(assembly_name: str) -> Optional[str]:
    """
    Lädt TXT aus Textbased_Data Ordner:
    - data/input/Textbased_Data/{assembly_name}/additional_info_{assembly_name}.txt
    
    Returns:
        TXT content, oder None falls keine Datei vorhanden
    """
    try:
        from agent.core.text_processor import load_additional_info
    except ImportError:
        from core.text_processor import load_additional_info

    return load_additional_info(assembly_name)


def attach_assembly_order(assembly_name: str) -> Optional[str]:
    """
    Lädt assembly sequence aus data/input/Textbased_Data/{assembly_name}/assembly_sequence_{assembly_name}.txt
    
    Unterstützt nur noch TXT Format (neue Struktur).
    
    Returns:
        TXT string, oder None falls nicht vorhanden
    """
    workspace_root = Path(__file__).resolve().parents[1]
    
    # Neue Struktur: Textbased_Data/{assembly_name}/assembly_sequence_{assembly_name}.txt
    txt_path = workspace_root / "data" / "input" / "Textbased_Data" / assembly_name / f"assembly_sequence_{assembly_name}.txt"
    if txt_path.exists():
        return txt_path.read_text(encoding="utf-8")
    
    return None


def attach_remarks(assembly_name: str) -> Optional[str]:
    """
    Lädt remarks aus data/input/Textbased_Data/{assembly_name}/remarks_{assembly_name}.txt
    
    Returns:
        TXT string, oder None falls nicht vorhanden
    """
    workspace_root = Path(__file__).resolve().parents[1]
    
    # Neue Struktur: Textbased_Data/{assembly_name}/remarks_{assembly_name}.txt
    txt_path = workspace_root / "data" / "input" / "Textbased_Data" / assembly_name / f"remarks_{assembly_name}.txt"
    if txt_path.exists():
        return txt_path.read_text(encoding="utf-8")
    
    return None


def attach_ground_truth_sequence(assembly_name: str) -> Optional[str]:
    """
    Lädt ground truth sequence aus data/input/Textbased_Data/{assembly_name}/.
    Sucht nach beliebigen Datei mit "ground_truth" im Namen.
    
    Returns:
        TXT string, oder None falls nicht vorhanden
    """
    workspace_root = Path(__file__).resolve().parents[1]
    
    # Struktur: Textbased_Data/{assembly_name}/ground_truth*.txt
    assembly_dir = workspace_root / "data" / "input" / "Textbased_Data" / assembly_name
    
    if not assembly_dir.exists():
        return None
    
    # Suche nach beliebiger Datei mit "ground_truth" im Namen
    gt_files = list(assembly_dir.glob("ground_truth*.txt"))
    
    if gt_files:
        # Verwende die erste gefundene Datei
        return gt_files[0].read_text(encoding="utf-8")
    
    return None


# ============================================================================
#                    ASSEMBLY SEQUENCE GENERATION
# ============================================================================

# Note: _build_part_name_map removed - part_name_map is now built directly in generate_assembly_sequence


def _calculate_missing_parts(bom_parts: List[Dict], sequence_steps: List) -> List[str]:
    """
    Calculate which parts from BOM are missing in the assembly sequence.
    """
    # Get all part_ids from BOM
    bom_part_ids = set()
    for part in bom_parts:
        part_id = part.get('part_id')
        if part_id:
            bom_part_ids.add(part_id)
    
    # Get all part_ids used in sequence
    used_part_ids = set()
    for step in sequence_steps:
        if step.get('base_part'):
            used_part_ids.add(step['base_part'])
        if step.get('joining_part'):
            jp = step['joining_part']
            if isinstance(jp, list):
                used_part_ids.update(jp)
            else:
                used_part_ids.add(jp)
    
    # Calculate missing
    missing = sorted(list(bom_part_ids - used_part_ids))
    return missing


def generate_assembly_sequence(
    assembly_name: str,
    assembly_dir: str | Path,
    exp_output_dir: str | Path,
    json_dir: str | Path = None,
    image_keywords: List[str] = None,
    json_keywords: List[str] = None,
    remarks_context: Optional[str] = None,
    use_manual_order: Optional[bool] = None,
    include_gt_sequence: Optional[bool] = None,
    additional_context_block: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generiere Montagereihenfolge basierend auf Bildern und Daten.
    
    Args:
        assembly_name: Name der Baugruppe (z.B. "IPA_Cranfield")
        assembly_dir: Pfad zu stepparser Assembly Output (mit Bildern)
        exp_output_dir: Pfad zu experiment output (wo assembly_sequence.json gespeichert wird)
        json_dir: Pfad zu JSONs ({assembly}_BOM_enriched.json, metadata). Falls None, wird exp_output_dir verwendet.
        image_keywords: Keywords für Bildfilterung (default: ["exploded", "Top"])
        json_keywords: Keywords für JSON-Filterung (default: ["BOM_enriched"])
        remarks_context: Optional feedback from previous validation runs
        use_manual_order: Optional override - if provided, use this instead of settings
        include_gt_sequence: Optional override - if provided, use this instead of settings
    
    Returns:
        Dict mit "assembly_sequence_path" und "sequence_data"
    """
    print(f"\n{'='*80}")
    print(f"GENERATE ASSEMBLY SEQUENCE: {assembly_name}")
    print(f"{'='*80}\n")
    
    assembly_dir = Path(assembly_dir)
    exp_output_dir = Path(exp_output_dir)
    json_dir = Path(json_dir) if json_dir else exp_output_dir
    
    # Load settings from experiment YAML
    from agent.tools import _get_experiment_settings
    settings = _get_experiment_settings()
    
    # Use settings directly (defaults should be in settings.yaml)
    if image_keywords is None:
        image_keywords = settings.get("ASG_image_keywords")
    
    # New JSON settings
    json_file_keyword = settings.get("ASG_json_file_keyword", "BOM_enriched")
    json_keys = settings.get("ASG_json_keys", ["part_id", "volume"])
    part_id_name_list = settings.get("ASG_part_id_name_list", [])
    
    use_additional_info = settings.get("ASG_use_additional_info", True)
    # Allow parameter overrides for session-based workflows
    use_manual_order = use_manual_order if use_manual_order is not None else settings.get("ASG_use_manual_order", True)
    include_remarks = settings.get("ASG_include_remarks", False)
    include_gt_sequence = include_gt_sequence if include_gt_sequence is not None else settings.get("ASG_include_GT_sequence", False)
    
    # Token usage settings
    max_completion_tokens = settings.get("ASG_max_completion_tokens", 4000)
    max_json_chars = settings.get("ASG_max_json_chars", 10000)
    max_additional_info_chars = settings.get("ASG_max_additional_info_chars", 2000)
    image_downscale = settings.get("ASG_downscale_images", 1.0)
    
    # 1. Bilder laden
    print(f"[1/6] Loading images with keywords: {image_keywords}")
    images = attach_images_by_keywords(assembly_dir, image_keywords, downscale_factor=image_downscale)
    print(f"      → Found {len(images)} images")
    for img in images:
        print(f"        - {Path(img['path']).name}")
    if image_downscale < 1.0:
        print(f"      → Images downscaled to {image_downscale*100:.0f}% (reduces token usage)")
    
    # 2. JSONs laden - NEW: Use extract_json_keys_from_file
    print(f"\n[2/6] Loading JSONs with file keyword: {json_file_keyword}")
    print(f"      Extracting keys: {json_keys}")
    if part_id_name_list:
        print(f"      Filtering parts: {part_id_name_list}")
    
    # Find JSON file matching keyword
    json_path = None
    for json_file in Path(json_dir).glob("*.json"):
        if json_file_keyword.lower() in json_file.name.lower():
            json_path = json_file
            break
    
    extracted_json = {}
    if json_path:
        extracted_json = extract_json_keys_from_file(json_path, json_keys, part_id_name_list)
        print(f"      → Loaded and filtered: {json_path.name}")
        if "parts" in extracted_json:
            print(f"      → Extracted {len(extracted_json['parts'])} parts with keys: {json_keys}")
    else:
        print(f"      → WARNING: No JSON file found matching keyword '{json_file_keyword}'")
    
    # Build part_id → part_name_guess mapping (for step enrichment)
    part_name_map = {}
    if "parts" in extracted_json and "part_name_guess" in json_keys:
        for part in extracted_json.get("parts", []):
            part_id = part.get("part_id")
            part_name = part.get("part_name_guess", "")
            if part_id and part_name:
                part_name_map[part_id] = part_name
    print(f"      → Built part_name_map with {len(part_name_map)} parts")
    
    # 3. Optional: Additional Info
    print(f"\n[3/6] Loading additional info...")
    additional_info = None
    if use_additional_info:
        additional_info = attach_additional_info(assembly_name)
    if additional_info:
        print(f"      → Found additional_info.txt ({len(additional_info)} chars)")
    else:
        print(f"      → No additional_info.txt found (or disabled)")
    
    # 4. Optional: Manual Assembly Sequence
    print(f"\n[4/6] Loading manual assembly sequence...")
    manual_order = None
    if use_manual_order:
        manual_order = attach_assembly_order(assembly_name)
    if manual_order:
        print(f"      → Found assembly_sequence_{assembly_name}.txt ({len(manual_order)} chars)")
    else:
        print(f"      → No assembly_sequence_{assembly_name}.txt found (or disabled)")
    
    # 4b. Optional: Remarks
    # Skip loading from disk if remarks_context already provided (from Agent 2 feedback)
    remarks = None
    if remarks_context:
        print(f"\n[4b/6] Using remarks from context (Agent 2 feedback) ({len(remarks_context)} chars)")
    else:
        print(f"\n[4b/6] Loading remarks from disk...")
        if include_remarks:
            remarks = attach_remarks(assembly_name)
        if remarks:
            print(f"      → Found remarks_{assembly_name}.txt ({len(remarks)} chars)")
        else:
            print(f"      → No remarks_{assembly_name}.txt found (or disabled)")
    
    # 4c. Optional: Ground Truth Sequence
    print(f"\n[4c/6] Loading ground truth sequence...")
    gt_sequence = None
    if include_gt_sequence:
        gt_sequence = attach_ground_truth_sequence(assembly_name)
    if gt_sequence:
        print(f"      → Found ground_truth_sequence_{assembly_name}.txt ({len(gt_sequence)} chars)")
    else:
        print(f"      → No ground_truth_sequence_{assembly_name}.txt found (or disabled)")
    
    # 5. Build Prompt & Call LLM
    print(f"\n[5/6] Calling LLM (GPT-4o Vision)...")
    
    # Load system + human prompts from prompts.yaml (configurable via settings)
    try:
        from agent.prompt_store import get_system_and_human_prompts
        system_prompt, human_prompt_template = get_system_and_human_prompts("ASG", settings)
        system_id = settings.get("ASG_system_prompt_id", "assembly_planner_expert_v1")
        human_id = settings.get("ASG_human_prompt_id", "generate_assembly_sequence_task_v3")
        print(f"      → Loaded prompts: system={system_id}, human={human_id}")
    except Exception as e:
        print(f"      → ERROR: Could not load prompts: {e}")
        raise
    
    # Build user prompt with text content
    user_text_parts = []
    # Start with human/task prompt
    user_text_parts.append(human_prompt_template)
    user_text_parts.append(f"\n\n=== INPUT DATA ===\n")
    user_text_parts.append(f"Assembly Name: {assembly_name}\n")
    
    if extracted_json:
        user_text_parts.append(f"\n## BOM Data (filtered):")
        # Truncate large JSONs to avoid token limits
        json_str = json.dumps(extracted_json, indent=2)
        if len(json_str) > max_json_chars:
            json_str = json_str[:max_json_chars] + "\n... (truncated)"
        user_text_parts.append(f"\nFile: {json_path.name if json_path else 'N/A'}")
        user_text_parts.append(f"```json\n{json_str}\n```")
    
    if additional_info:
        user_text_parts.append(f"\n## Additional Information:")
        # Truncate if too long
        info_text = additional_info[:max_additional_info_chars] if len(additional_info) > max_additional_info_chars else additional_info
        user_text_parts.append(f"```\n{info_text}\n```")

    try:
        from agent.tools import format_content_agent_context_block
        content_agent_block = format_content_agent_context_block(additional_context_block, settings)
    except Exception:
        content_agent_block = None
    if content_agent_block:
        label, context_text = content_agent_block
        user_text_parts.append(f"\n## {label}:")
        user_text_parts.append(f"```\n{context_text}\n```")
    
    if manual_order:
        user_text_parts.append(f"\n## Manual Assembly Order Reference:")
        user_text_parts.append(f"```\n{manual_order}\n```")
    
    if remarks:
        user_text_parts.append(f"\n## Remarks & Important Notes:")
        user_text_parts.append(f"```\n{remarks}\n```")
    
    if gt_sequence:
        user_text_parts.append(f"\n## Ground Truth Assembly Sequence:")
        user_text_parts.append(f"```\n{gt_sequence}\n```")
    
    if remarks_context:
        user_text_parts.append("\n## Previous Validation Feedback:")
        trimmed_remarks = remarks_context.strip()
        user_text_parts.append(trimmed_remarks if trimmed_remarks else "(empty)")
    
    user_text_parts.append("\n\nGenerate the assembly sequence in JSON format (no markdown code fences).")
    user_text = "\n".join(user_text_parts)
    
    # Use existing LLM setup from tools.py with structured output
    llm = _get_img_describer_llm(max_completion_tokens=max_completion_tokens)
    llm_structured = llm.with_structured_output(AssemblySequence, include_raw=True)
    
    print(f"      Token settings: max_completion={max_completion_tokens}, max_json_chars={max_json_chars}, downscale={image_downscale}")
    
    # Construct multimodal message
    user_content = [{"type": "text", "text": user_text}]
    
    # Add images with descriptive labels
    if images:
        # Organize images by keyword for better context
        user_content.append({
            "type": "text",
            "text": "\n=== ASSEMBLY IMAGES ===\n"
        })
        
        # Separate complete assembly from individual views
        complete_assy = [img for img in images if 'complete' in img.get('filename', '').lower() or 'finished' in img.get('filename', '').lower()]
        other_images = [img for img in images if img not in complete_assy]
        
        # Add complete assembly image(s) first with clear label
        for img in complete_assy:
            user_content.append({
                "type": "text",
                "text": f"\n### COMPLETE ASSEMBLED PRODUCT\nFile: {img['filename']}\n"
            })
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{img['mime']};base64,{img['b64']}"
                }
            })
        
        # Add other assembly images with keyword-based labels
        if other_images:
            user_content.append({
                "type": "text",
                "text": "\n### ASSEMBLY STEP VIEWS\n(Use these to determine part positions and assembly sequence)\n"
            })
            for img in other_images:
                filename = img.get('filename', 'unknown')
                # Infer view type from filename
                view_type = "Assembly View"
                if 'iso' in filename.lower():
                    view_type = "Isometric View"
                elif 'front' in filename.lower():
                    view_type = "Front View"
                elif 'top' in filename.lower():
                    view_type = "Top View"
                elif 'side' in filename.lower():
                    view_type = "Side View"
                elif 'explosion' in filename.lower():
                    view_type = "Exploded View"
                
                user_content.append({
                    "type": "text",
                    "text": f"\n**{view_type}** - {filename}\n"
                })
                user_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{img['mime']};base64,{img['b64']}"
                    }
                })
    else:
        user_content.append({
            "type": "text",
            "text": "\n(No assembly images provided)"
        })
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]
    
    try:
        response = invoke_with_retry(llm_structured, messages)
        if isinstance(response, dict) and "parsed" in response:
            sequence_data = response["parsed"]
            raw_msg = response.get("raw")
        else:
            sequence_data = response
            raw_msg = None
        
        print(f"      → LLM response received and parsed via Pydantic")
    except Exception as e:
        print(f"      → ERROR: LLM call or parsing failed: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}
    
    # 6. Validate structured output
    print(f"\n[6/6] Validating structured output...")
    
    if not isinstance(sequence_data, AssemblySequence):
        print(f"      → ERROR: Expected AssemblySequence, got {type(sequence_data)}")
        return {"error": "Invalid structured output type"}
    
    print(f"      → ✓ Valid AssemblySequence schema")
    print(f"      → Assembly: {sequence_data.assembly_name}")
    print(f"      → Steps: {len(sequence_data.steps)}")
    print(f"      → Sequence notation: {sequence_data.sequence_notation}")
    
    # Convert to dict for JSON serialization
    # Use exclude_none=True to remove all null values from output (cleaner JSON)
    sequence_dict = sequence_data.model_dump(exclude_none=True)
    
    print(f"      → Total steps: {len(sequence_data.steps)}")
    
    # Add metadata
    sequence_dict["assembly_sequence_id"] = str(uuid.uuid4())
    sequence_dict["method"] = "llm_vision"
    sequence_dict["confidence"] = 0.85  # TODO: Extract from certainty fields
    sequence_dict["metadata"] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": "gpt-4o",
        "input_images": [Path(img["path"]).name for img in images],
        "input_json": json_path.name if json_path else None,
        "additional_info_used": additional_info is not None,
        "manual_assembly_order_used": manual_order is not None,
    }
    
    # Write assembly_sequence.json
    from agent.tools import save_structured_json
    exp_output_dir = Path(exp_output_dir)
    exp_output_dir.mkdir(parents=True, exist_ok=True)
    output_path = exp_output_dir / "assembly_sequence.json"
    try:
        save_structured_json(output_path, sequence_dict, schema=AssemblySequence)
        print(f"\n✓ Assembly sequence saved: {output_path}")
    except Exception as e:
        print(f"\nX ERROR: Failed to write assembly_sequence.json: {e}")
        return {"error": str(e)}
    
    return {
        "assembly_sequence_path": str(output_path),
        "sequence_data": sequence_dict,
    }


# ============================================================================
#              GENERATE ASSEMBLY SEQUENCE FROM GROUND TRUTH (ASGT)
# ============================================================================

def generate_assembly_sequence_from_gt(
    assembly_name: str,
    assembly_dir: str | Path,
    exp_output_dir: str | Path,
    json_dir: str | Path = None,
    additional_context_block: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate assembly sequence step descriptions using a ground truth step structure.

    The GT sequence (step_id, belongs_to, base_part, joining_part) is loaded from:
        data/ground_truth/assembly_sequence_ground_truth/{assembly_name}/sequence.json

    The LLM receives the GT step skeleton + BOM + images and generates:
        - step_description  (one clear sentence per step)
        - joining_process   (e.g. "Place", "Insert", "Press-fit")

    Python then merges LLM output with the GT skeleton to produce a full
    AssemblySequence JSON (identical structure to generate_assembly_sequence output).

    Args:
        assembly_name:    Assembly name (e.g., "IPA_Cranfield")
        assembly_dir:     Stepparser assembly output folder (with images)
        exp_output_dir:   Experiment output folder (assembly_sequence.json saved here)
        json_dir:         Folder with BOM JSON. Defaults to exp_output_dir.

    Returns:
        Dict with "assembly_sequence_path" and "sequence_data", or {"error": ...}
    """
    print(f"\n{'='*80}")
    print(f"GENERATE ASSEMBLY SEQUENCE FROM GT: {assembly_name}")
    print(f"{'='*80}\n")

    assembly_dir = Path(assembly_dir)
    exp_output_dir = Path(exp_output_dir)
    json_dir = Path(json_dir) if json_dir else exp_output_dir

    # Load settings
    from agent.tools import _get_experiment_settings
    settings = _get_experiment_settings()

    # ASGT-specific settings (all toggleable via YAML)
    image_keywords   = settings.get("ASGT_image_keywords", ["iso1_transp_0_0", "iso1_exp_transp_0_0"])
    json_file_keyword = settings.get("ASGT_json_file_keyword", "BOM_enriched")
    json_keys        = settings.get("ASGT_json_keys", ["part_id", "part_name_guess", "part_is_touching"])
    include_images   = settings.get("ASGT_include_images", True)
    include_bom      = settings.get("ASGT_include_bom", True)
    use_additional_info = settings.get("ASGT_use_additional_info", False)
    max_completion_tokens = int(settings.get("ASGT_max_completion_tokens", 8000))
    max_json_chars   = int(settings.get("ASGT_max_json_chars", 10000))
    image_downscale  = float(settings.get("image_downscale_factor", settings.get("ASGT_downscale_images", 0.7)))

    # -----------------------------------------------------------------------
    # 1. Load Ground Truth sequence structure
    # -----------------------------------------------------------------------
    print(f"[1/5] Loading GT sequence structure...")
    workspace_root = Path(__file__).resolve().parents[1]
    gt_root_env = os.environ.get("APA_GROUND_TRUTH_SEQUENCE_ROOT")
    if gt_root_env:
        gt_root = Path(gt_root_env)
        if not gt_root.is_absolute():
            gt_root = workspace_root / gt_root
    else:
        gt_root = workspace_root / "data" / "ground_truth" / "assembly_sequence_ground_truth"
    gt_sequence_file = gt_root / assembly_name / "sequence.json"
    if not gt_sequence_file.exists():
        msg = f"GT sequence not found: {gt_sequence_file}"
        print(f"  ✗ {msg}")
        return {"error": msg}

    with open(gt_sequence_file, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    gt_steps = gt_data.get("steps", [])
    if not gt_steps:
        msg = f"GT sequence has no steps: {gt_sequence_file}"
        print(f"  ✗ {msg}")
        return {"error": msg}

    print(f"  → Loaded {len(gt_steps)} steps from GT")

    # Build a human-readable GT skeleton for the prompt
    gt_skeleton_lines = []
    for s in gt_steps:
        gt_skeleton_lines.append(
            f"  step_id: {s['step_id']} | belongs_to: {s.get('belongs_to', '')} | "
            f"base_part: {s.get('base_part', 'null')} | joining_part: {s.get('joining_part', 'null')}"
        )
    gt_skeleton_text = "\n".join(gt_skeleton_lines)

    # -----------------------------------------------------------------------
    # 2. Load BOM  (optional, toggleable)
    # -----------------------------------------------------------------------
    print(f"\n[2/5] Loading BOM (include_bom={include_bom})...")
    extracted_json = {}
    json_path = None
    if include_bom:
        for json_file in Path(json_dir).glob("*.json"):
            if json_file_keyword.lower() in json_file.name.lower():
                json_path = json_file
                break
        if json_path:
            extracted_json = extract_json_keys_from_file(json_path, json_keys, [])
            n_parts = len(extracted_json.get("parts", []))
            print(f"  → {json_path.name}  ({n_parts} parts, keys: {json_keys})")
        else:
            print(f"  → No BOM file found matching '{json_file_keyword}' (skipped)")

    # -----------------------------------------------------------------------
    # 3. Load images  (optional, toggleable)
    # -----------------------------------------------------------------------
    print(f"\n[3/5] Loading images (include_images={include_images}, keywords={image_keywords})...")
    images = []
    if include_images:
        images = attach_images_by_keywords(assembly_dir, image_keywords, downscale_factor=image_downscale)
        print(f"  → Found {len(images)} images" + (f" (downscaled {image_downscale*100:.0f}%)" if image_downscale < 1.0 else ""))
        for img in images:
            print(f"       {Path(img['path']).name}")

    # -----------------------------------------------------------------------
    # 4. Optional: additional_info.txt
    # -----------------------------------------------------------------------
    print(f"\n[4/5] Loading additional info (use_additional_info={use_additional_info})...")
    additional_info = None
    if use_additional_info:
        additional_info = attach_additional_info(assembly_name)
    if additional_info:
        print(f"  → Found additional_info.txt ({len(additional_info)} chars)")
    else:
        print(f"  → Not loaded (disabled or not found)")

    # -----------------------------------------------------------------------
    # 5. Build prompt & call LLM
    # -----------------------------------------------------------------------
    print(f"\n[5/5] Calling LLM...")

    from agent.prompt_store import get_system_and_human_prompts
    system_prompt, human_prompt_template = get_system_and_human_prompts("ASGT", settings)
    print(f"  → Prompts: system={settings.get('ASGT_system_prompt_id')}, human={settings.get('ASGT_human_prompt_id')}")

    user_parts = [human_prompt_template, "\n\n=== INPUT DATA ===\n"]
    user_parts.append(f"Assembly Name: {assembly_name}\n")

    # GT skeleton
    user_parts.append("\n## Ground Truth Assembly Sequence Structure (DO NOT CHANGE):\n")
    user_parts.append("The following defines WHICH parts are added in WHICH order and context.\n")
    user_parts.append("Your task: fill step_description and joining_process for each step_id.\n")
    user_parts.append("```\n" + gt_skeleton_text + "\n```\n")

    # BOM data
    if extracted_json:
        json_str = json.dumps(extracted_json, indent=2)
        if len(json_str) > max_json_chars:
            json_str = json_str[:max_json_chars] + "\n... (truncated)"
        user_parts.append(f"\n## BOM Data (part names + metadata):")
        user_parts.append(f"\n```json\n{json_str}\n```")

    # Additional info
    if additional_info:
        user_parts.append(f"\n## Additional Information:\n```\n{additional_info}\n```")

    try:
        from agent.tools import format_content_agent_context_block
        content_agent_block = format_content_agent_context_block(additional_context_block, settings)
    except Exception:
        content_agent_block = None
    if content_agent_block:
        label, context_text = content_agent_block
        user_parts.append(f"\n## {label}:\n```\n{context_text}\n```")

    user_parts.append("\n\nGenerate the output JSON (no markdown code fences).")
    user_text = "\n".join(user_parts)

    # Build multimodal message
    user_content: List[Dict] = [{"type": "text", "text": user_text}]
    if images:
        user_content.append({"type": "text", "text": "\n=== ASSEMBLY IMAGES ==="})
        for img in images:
            user_content.append({"type": "text", "text": f"\n{img['filename']}"})
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{img['mime']};base64,{img['b64']}"},
            })

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_content},
    ]

    from agent.structured_output import AssemblySequenceStepDescriptions
    llm = _get_img_describer_llm(max_completion_tokens=max_completion_tokens)
    llm_structured = llm.with_structured_output(AssemblySequenceStepDescriptions, include_raw=True)

    try:
        response = invoke_with_retry(llm_structured, messages)
        if isinstance(response, dict) and "parsed" in response:
            llm_result: AssemblySequenceStepDescriptions = response["parsed"]
        else:
            llm_result = response

        if llm_result is None:
            return {"error": "LLM returned None (structured output failed)"}

    except Exception as e:
        print(f"  ✗ LLM call failed: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

    # -----------------------------------------------------------------------
    # 6. Python merge: GT structure + LLM descriptions → full sequence dict
    # -----------------------------------------------------------------------
    llm_steps_by_id: Dict[int, Any] = {}
    for s in (llm_result.steps or []):
        llm_steps_by_id[s.step_id] = s

    merged_steps = []
    for gt_step in gt_steps:
        sid = gt_step["step_id"]
        llm_step = llm_steps_by_id.get(sid)

        # Fall back to GT joining_process if LLM didn't return this step
        step_description = (
            llm_step.step_description if llm_step else
            f"Step {sid}: assembly of {gt_step.get('joining_part', '?')}"
        )
        joining_process = (
            llm_step.joining_process if llm_step else
            gt_step.get("joining_process", "Unknown")
        )

        merged_steps.append({
            "step_id":          sid,
            "step_description": step_description,
            "belongs_to":       gt_step.get("belongs_to", "Assembly (basic config)"),
            "base_part":        gt_step.get("base_part"),
            "joining_part":     gt_step.get("joining_part"),
            "joining_process":  joining_process,
        })

    sequence_dict = {
        "assembly_name":        assembly_name,
        "assembly_description": getattr(llm_result, "assembly_description", ""),
        "sequence_description": getattr(llm_result, "sequence_description", ""),
        "sequence_logic_prior": getattr(llm_result, "sequence_logic_prior", ""),
        "sequence_notation_prior": gt_data.get("sequence_notation", ""),
        "steps":                merged_steps,
        "sequence_notation":    getattr(llm_result, "sequence_notation", gt_data.get("sequence_notation", "")),
        "assembly_sequence_id": str(uuid.uuid4()),
        "method":               "gt_structured",
        "confidence":           0.95,
        "metadata": {
            "generated_at":    datetime.now(timezone.utc).isoformat(),
            "model":           "gpt-4o",
            "gt_sequence_file": str(gt_sequence_file),
            "steps_from_gt":   len(gt_steps),
            "steps_merged":    len(merged_steps),
            "include_images":  include_images,
            "include_bom":     include_bom,
            "image_keywords":  image_keywords,
        },
    }

    # -----------------------------------------------------------------------
    # 7. Save
    # -----------------------------------------------------------------------
    from agent.tools import save_structured_json
    exp_output_dir.mkdir(parents=True, exist_ok=True)
    output_path = exp_output_dir / "assembly_sequence.json"
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(sequence_dict, f, indent=2, ensure_ascii=False)
        print(f"\n  ✓ Saved: {output_path}")
    except Exception as e:
        print(f"\n  ✗ Failed to save: {e}")
        return {"error": str(e)}

    print(f"  ✓ Steps merged: {len(merged_steps)} (GT: {len(gt_steps)}, LLM: {len(llm_steps_by_id)})")

    return {
        "assembly_sequence_path": str(output_path),
        "sequence_data": sequence_dict,
    }


# ============================================================================
#                    MAIN / TESTING
# ============================================================================

def main():
    """Test Assembly Sequence Generation & Rendering standalone."""
    
    print("\n" + "="*80)
    print("ASSEMBLY SEQUENCE GENERATION - STANDALONE TEST")
    print("="*80)
    
    # Configuration
    workspace_root = Path(__file__).resolve().parents[1]
    
    # Test Assembly
    assembly_name = "IPA_Cranfield"
    
    # Paths
    stepparser_output = workspace_root / "data" / "processed" / "stepparser" / assembly_name
    # New convention: assembly_{name} folders
    # Legacy: {name}.STEP folders
    assembly_dir = stepparser_output / f"assembly_{assembly_name}"
    if not assembly_dir.exists():
        assembly_dir = stepparser_output / f"{assembly_name}.STEP"
    
    # Use direct_run directory for JSONs AND as output (save assembly_sequence.json there)
    exp_output_dir = workspace_root / "data" / "experiments" / "direct_run" / assembly_name
    exp_output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nPaths:")
    print(f"  Assembly Dir:    {assembly_dir}")
    print(f"  Exp Output Dir:  {exp_output_dir}")
    
    # Check if paths exist
    if not assembly_dir.exists():
        print(f"\nX ERROR: Assembly dir not found: {assembly_dir}")
        print(f"  Please run stepparser first!")
        return
    
    if not exp_output_dir.exists():
        print(f"\nX ERROR: Experiment dir not found: {exp_output_dir}")
        print(f"  Please run workflow first to generate {assembly_name}_BOM_enriched.json!")
        return
    
    # ========================================================================
    # TEST 1: Generate Assembly Sequence
    # ========================================================================
    
    print("\n" + "="*80)
    print("TEST 1: GENERATE ASSEMBLY SEQUENCE")
    print("="*80)
    
    try:
        result_gen = generate_assembly_sequence(
            assembly_name=assembly_name,
            assembly_dir=assembly_dir,
            exp_output_dir=exp_output_dir,
            json_dir=exp_output_dir,  # Load JSONs from same directory
            image_keywords=None,  # Use settings from YAML
            json_keywords=None,  # Use settings from YAML
        )
        
        if "error" in result_gen:
            print(f"\nX Generation failed: {result_gen['error']}")
            return
        
        print(f"\nv SUCCESS: Assembly sequence generated")
        print(f"  Path: {result_gen['assembly_sequence_path']}")
        
    except Exception as e:
        print(f"\nX EXCEPTION during generation: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # ========================================================================
    # NEXT STEPS
    # ========================================================================
    
    print("\n" + "="*80)
    print("NEXT: RENDERING + VALIDATION")
    print("="*80)
    print("\nRun: python -m agent.Assembly_sequence_validation")
    print("  This will:")
    print("  1. Render assembly steps (incremental, 4 views)")
    print("  2. Validate each step with LLM")
    
    print("\n" + "="*80)
    print("TEST COMPLETED")
    print("="*80)


if __name__ == "__main__":
    main()
