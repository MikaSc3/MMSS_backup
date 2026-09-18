"""
FFA Assessment - Fitness for Automation Evaluation

Bewertet Assembly Sequence Steps nach FFA-Kriterien (Fitness for Automation).
Nutzt Metadata der Base/Joining Parts + Renderings für LLM-basierte Analyse.

Diese Datei läuft UNABHÄNGIG vom Workflow_enrich_data.py.

Usage:
    python -m agent.FFA_assessment

Features:
1. Step-by-step FFA assessment mit 4 Kategorien: Separation, Handling, Positioning, Joining
2. Multimodal LLM-Call mit GPT-4o Vision
3. Strukturierte Outputs via Pydantic (FFA_Assessment_Complete)
4. Lädt Base/Joining Part Metadata aus enriched JSONs
5. Nutzt Step Renderings (multiple views: front, top, isometric)

Workflow Integration siehe: Workflow_enrich_data.py → _node_assess_ffa()

Rate-limit handling: 429 errors are retried up to 5 times with exponential backoff
(2 s → 4 s → 8 s → 16 s → 32 s).
"""

from __future__ import annotations

import os
import json
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from agent.utils import invoke_with_retry

# LLM - use existing setup from tools.py
try:
    from agent.tools import _get_img_describer_llm, extract_json_keys_from_file
    from agent.structured_output import FFA_Assessment_Complete
except ImportError:
    from tools import _get_img_describer_llm, extract_json_keys_from_file
    from structured_output import FFA_Assessment_Complete

# Prompt loading
try:
    from agent.prompt_store import get_prompt_template
except ImportError:
    try:
        from prompt_store import get_prompt_template
    except ImportError:
        get_prompt_template = None


def save_ffa_to_excel(stripped_result: Dict[str, Any], output_dir: Path) -> None:
    """
    Speichert stripped FFA assessment als Excel/CSV Datei.
    
    Args:
        stripped_result: Stripped FFA assessment result
        output_dir: Output directory
    """
    try:
        import pandas as pd
    except ImportError:
        print("  [WARNING] pandas not installed - skipping Excel export")
        return
    
    # Konvertiere zu tabellarischem Format
    rows = []
    
    for step_assessment in stripped_result.get("step_assessments", []):
        row = {
            "step_id": step_assessment.get("step_id"),
            "step_description": step_assessment.get("step_description"),
            "base_part_id": step_assessment.get("base_part_id"),
            "joining_part_id": str(step_assessment.get("joining_part_id")),  # Convert list to string
            "joining_process": step_assessment.get("joining_process"),
        }
        
        assessment = step_assessment.get("assessment")
        if assessment:
            # Separation
            if assessment.get("separation"):
                row["separation_nature_of_provision"] = assessment["separation"].get("nature_of_provision")
            else:
                row["separation_nature_of_provision"] = None
            
            # Handling
            if assessment.get("handling"):
                row["handling_part_rigidity"] = assessment["handling"].get("part_rigidity")
                row["handling_gripping_areas"] = assessment["handling"].get("gripping_areas")
                row["handling_orientation_features"] = assessment["handling"].get("orientation_features")
                row["handling_surface_sensibility"] = assessment["handling"].get("surface_sensibility")
            else:
                row["handling_part_rigidity"] = None
                row["handling_gripping_areas"] = None
                row["handling_orientation_features"] = None
                row["handling_surface_sensibility"] = None
            
            # Positioning
            if assessment.get("positioning"):
                row["positioning_accuracy"] = assessment["positioning"].get("accuracy_of_target_position")
                row["positioning_aids"] = assessment["positioning"].get("positioning_aids")
                row["positioning_rotation"] = assessment["positioning"].get("additional_orientation_by_rotation")
                row["positioning_accessibility"] = assessment["positioning"].get("accessibility_to_joining_position")
                row["positioning_motion"] = assessment["positioning"].get("positioning_motion")
                row["positioning_tolerances"] = assessment["positioning"].get("positioning_tolerances")
                row["positioning_stability"] = assessment["positioning"].get("stability_in_positioned_state")
            else:
                row["positioning_accuracy"] = None
                row["positioning_aids"] = None
                row["positioning_rotation"] = None
                row["positioning_accessibility"] = None
                row["positioning_motion"] = None
                row["positioning_tolerances"] = None
                row["positioning_stability"] = None
            
            # Joining
            if assessment.get("joining"):
                row["joining_feeding"] = assessment["joining"].get("feeding_of_joining_element")
                row["joining_fixing"] = assessment["joining"].get("fixing_of_mounted_part")
            else:
                row["joining_feeding"] = None
                row["joining_fixing"] = None
        
        rows.append(row)
    
    # Erstelle DataFrame
    df = pd.DataFrame(rows)
    
    # Speichere als Excel
    excel_file = output_dir / "ffa_assessment.xlsx"
    df.to_excel(excel_file, index=False, sheet_name="FFA Assessment")
    print(f"✓ Excel export saved to: {excel_file}")
    
    # Speichere auch als CSV (besser für Git/Diff)
    csv_file = output_dir / "ffa_assessment.csv"
    df.to_csv(csv_file, index=False, encoding="utf-8-sig")  # utf-8-sig for Excel compatibility
    print(f"✓ CSV export saved to: {csv_file}")


def strip_ffa_assessment(assessment: Dict[str, Any]) -> Dict[str, Any]:
    """
    Entfernt options_analysis, reasoning, evidence aus FFA-Assessment.
    Behält nur die tatsächlichen Kriterien-Bewertungen.
    
    Args:
        assessment: Full FFA assessment dict
    
    Returns:
        Stripped assessment mit nur Kriterien und Antworten
    """
    if not assessment:
        return None
    
    stripped = {}
    
    # Separation (nur nature_of_provision)
    if assessment.get('separation'):
        stripped['separation'] = {
            'nature_of_provision': assessment['separation'].get('nature_of_provision'),
            'automatable_reasoning': assessment['separation'].get('automatable_reasoning'),
            'automatable': assessment['separation'].get('automatable')
        }
    else:
        stripped['separation'] = None
    
    # Handling (nur die 4 Kriterien)
    if assessment.get('handling'):
        stripped['handling'] = {
            'part_rigidity': assessment['handling'].get('part_rigidity'),
            'gripping_areas': assessment['handling'].get('gripping_areas'),
            'orientation_features': assessment['handling'].get('orientation_features'),
            'surface_sensibility': assessment['handling'].get('surface_sensibility'),
            'automatable_reasoning': assessment['handling'].get('automatable_reasoning'),
            'automatable': assessment['handling'].get('automatable')
        }
    else:
        stripped['handling'] = None
    
    # Positioning (alle 6 Kriterien)
    if assessment.get('positioning'):
        stripped['positioning'] = {
            'accuracy_of_target_position': assessment['positioning'].get('accuracy_of_target_position'),
            'positioning_aids': assessment['positioning'].get('positioning_aids'),
            'additional_orientation_by_rotation': assessment['positioning'].get('additional_orientation_by_rotation'),
            'accessibility_to_joining_position': assessment['positioning'].get('accessibility_to_joining_position'),
            'positioning_motion': assessment['positioning'].get('positioning_motion'),
            'positioning_tolerances': assessment['positioning'].get('positioning_tolerances'),
            'stability_in_positioned_state': assessment['positioning'].get('stability_in_positioned_state'),
            'automatable_reasoning': assessment['positioning'].get('automatable_reasoning'),
            'automatable': assessment['positioning'].get('automatable')
        }
    else:
        stripped['positioning'] = None
    
    # Joining (nur die 2 Kriterien)
    if assessment.get('joining'):
        stripped['joining'] = {
            'automatable_reasoning': assessment['joining'].get('automatable_reasoning'),
            'automatable': assessment['joining'].get('automatable'),
            'feeding_of_joining_element': assessment['joining'].get('feeding_of_joining_element'),
            'fixing_of_mounted_part': assessment['joining'].get('fixing_of_mounted_part'),
        }
    else:
        stripped['joining'] = None
    
    return stripped


# ============================================================================
#                    UTILITIES
# ============================================================================

import hashlib
import re

def normalize_part_id(part_id: str) -> str:
    """
    Entfernt _copyN suffix von part_id.
    
    Beispiele:
        part_003_copy1 -> part_003
        part_003 -> part_003
        SA1 -> SA1
    """
    return re.sub(r'_copy\d+$', '', part_id)


def get_metadata_hash(metadata: Dict[str, Any]) -> str:
    """
    Erstellt Hash von Part-Metadata für FFA-Caching.
    
    Identische Metadaten = identischer Hash = gleiche FFA-Bewertung.
    """
    import json
    # Sortiere Keys für konsistenten Hash
    metadata_str = json.dumps(metadata, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(metadata_str.encode()).hexdigest()

def load_part_metadata(part_id: str, enriched_dir: Path, json_keys: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """
    Lädt enriched Metadata für ein Part mit JSON-Key-Filterung.
    
    Args:
        part_id: Part ID (z.B. 'part_001' oder 'SA1')
        enriched_dir: Directory mit enriched JSONs
        json_keys: Keys to extract (filters the JSON to only these keys)
    
    Returns:
        Part metadata dict (gefiltert nach json_keys) oder None
    """
    # Use only merged enriched files
    json_path = enriched_dir / f"{part_id}_Data_enriched_merged.json"
    
    if not json_path.exists():
        return None
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if json_keys:
            # Filter to only requested keys (for token efficiency)
            filtered = {}
            for key in json_keys:
                if key in data:
                    filtered[key] = data[key]
            return filtered
        else:
            # Return all (not recommended - wastes tokens)
            return data
    except Exception as e:
        print(f"[WARNING] Failed to load {json_path}: {e}")
        return None


def attach_step_images(step_folder: Path, downscale_factor: float = 1.0) -> List[Dict[str, Any]]:
    """
    Lädt alle Renderings eines Assembly Steps.
    
    Args:
        step_folder: Folder mit Step_{ID}_*.png Files
        downscale_factor: Image scaling factor (0.5 = half size)
    
    Returns:
        List of {"path": str, "filename": str, "b64": str, "mime": str}
    """
    from agent.tools import ImageLoader
    
    if not step_folder.exists():
        return []


def filter_part_metadata(part_data: Dict[str, Any], keys: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Filter Part-Metadata-Dict on desired keys, supporting nested keys with dot notation.
    
    Args:
        part_data: Part metadata dict
        keys: Keys to keep (None = keep all). Supports nested keys like "monopart_analysis.geometric_characteristics"
    
    Returns:
        Filtered dict with nested structure preserved
    """
    if keys is None or not part_data:
        return part_data or {}
    
    # If keys is empty list, return empty dict (filter everything out)
    if len(keys) == 0:
        return {}
    
    filtered = {}
    for key in keys:
        # Check if key contains dot notation (nested key)
        if "." in key:
            # Navigate nested structure
            keys_path = key.split(".")
            current = part_data
            value = None
            
            # Try to traverse the path
            try:
                for k in keys_path:
                    if isinstance(current, dict) and k in current:
                        current = current[k]
                    else:
                        current = None
                        break
                
                if current is not None:
                    # Add to filtered dict with nested structure
                    # Build nested dict: filtered[keys_path[0]][keys_path[1]]... = value
                    target = filtered
                    for i, k in enumerate(keys_path[:-1]):
                        if k not in target:
                            target[k] = {}
                        target = target[k]
                    target[keys_path[-1]] = current
            except (KeyError, TypeError):
                pass  # Skip if path doesn't exist
        else:
            # Direct key lookup (non-nested)
            if key in part_data:
                filtered[key] = part_data[key]
    
    return filtered
    
    loader = ImageLoader(str(step_folder))
    result_images = []
    
    # Load all PNG files in folder
    for img_file in step_folder.glob("*.png"):
        if downscale_factor < 1.0:
            # Downscale image before base64 encoding
            from PIL import Image
            import io
            import base64
            
            img = Image.open(img_file)
            new_size = (int(img.width * downscale_factor), int(img.height * downscale_factor))
            img_resized = img.resize(new_size, Image.Resampling.LANCZOS)
            
            buffer = io.BytesIO()
            img_resized.save(buffer, format="PNG")
            b64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
            
            result_images.append({
                "path": str(img_file),
                "filename": img_file.name,
                "b64": b64_data,
                "mime": "image/png"
            })
        else:
            # Use original image
            b64_data = loader.load_image_b64(img_file.name)
            result_images.append({
                "path": str(img_file),
                "filename": img_file.name,
                "b64": b64_data,
                "mime": "image/png"
            })
    
    return result_images


# ============================================================================
#                    CORE ASSESSMENT LOGIC
# ============================================================================

def assess_step_ffa(
    step_id: int,
    step_description: str,
    base_part_id: str,
    joining_part_id: Optional[str],
    joining_process: str,
    base_metadata: Dict[str, Any],
    joining_metadata: Optional[Dict[str, Any]],
    step_images: List[Dict[str, Any]],
    prior_step_images: List[Dict[str, Any]],
    prompt_id: str = "ffa_assessment_full_v1",
    cached_separation: Optional[Dict[str, Any]] = None,
    cached_handling: Optional[Dict[str, Any]] = None,
    interaction_context: Optional[str] = None,
    include_step_info: bool = True,
    settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Bewertet einen Assembly Step nach FFA-Kriterien.
    
    Args:
        step_id: Step ID
        step_description: Human-readable step description
        base_part_id: Base part ID
        joining_part_id: Joining part ID (oder None bei initial placement)
        joining_process: Joining process (Insert, Screw, etc.)
        base_metadata: Base part enriched metadata (ALREADY FILTERED by load_part_metadata)
        joining_metadata: Joining part enriched metadata (ALREADY FILTERED by load_part_metadata)
        step_images: List of current step renderings
        prior_step_images: List of prior step renderings (empty if step_id==1)
        prompt_id: Prompt template ID
        cached_separation: Cached separation assessment (für identische Teile)
        cached_handling: Cached handling assessment (für identische Teile)
        interaction_context: Optional interaction analysis context for this step
        include_step_info: If False, omit step_description and joining_process from LLM prompt
    
    Returns:
        Dict with assessment result + metadata
    """
    # Load settings first to get FFA model override if available
    try:
        if settings is None:
            from agent.tools import _get_experiment_settings
            settings = _get_experiment_settings()
        llm_model_ffa = settings.get("llm_model_ffa")
    except Exception:
        llm_model_ffa = None
    
    # Get LLM with FFA-specific model if available (no structured_output parameter - use with_structured_output instead)
    llm = _get_img_describer_llm(max_completion_tokens=4000, llm_model_override=llm_model_ffa)
    # Use with_structured_output without include_raw - returns parsed object directly
    # This avoids Pydantic serialization warnings from ParsedChatCompletionMessage
    llm_structured = llm.with_structured_output(FFA_Assessment_Complete)
    
    # Load system + human prompts
    try:
        from agent.prompt_store import get_system_and_human_prompts, get_prompt_template
        system_prompt, human_prompt_template = get_system_and_human_prompts("FFA", settings)
    except Exception as e:
        raise ValueError(f"Could not load FFA prompts: {e}")
    
    # Get FFA explanation level and load corresponding enum options
    ffa_explanation_level = settings.get("FFA_explanation_level", "minimal")
    enum_options_prompt_id_map = {
        "minimal": "ffa_enum_options_minimal",
        "with_explanations": "ffa_enum_options_with_explanations",
        "full": "WITH_EXPLAINATION_AND_EXAMPLES",
    }
    enum_options_prompt_id = enum_options_prompt_id_map.get(ffa_explanation_level, "ffa_enum_options_minimal")
    enum_options_text = ""
    try:
        enum_options_text = get_prompt_template(enum_options_prompt_id)
    except Exception as e:
        print(f"    [WARNING] Could not load FFA enum options '{enum_options_prompt_id}': {e}")
    
    # Append FFA explanation level options to system prompt
    if enum_options_text:
        system_prompt = system_prompt + "\n\n" + enum_options_text
    
    # Metadata is already filtered by load_part_metadata() using base_metadata_keys/joining_metadata_keys
    # No need for additional filtering here
    base_metadata_filtered = base_metadata
    joining_metadata_filtered = joining_metadata or {}
    
    # Build human prompt parts - reordered: Step Info → Images → Metadata
    human_prompt_parts = []
    human_prompt_parts.append(human_prompt_template)
    
    # 1. STEP INFORMATION (at the top)
    # Optionally include step description and joining process based on include_step_info flag
    if include_step_info:
        step_info_text = f"""
=== STEP INFORMATION ===
- Step ID: {step_id}
- Description: {step_description}
- Joining Process: {joining_process}
"""
    else:
        # Omit description and process - LLM must infer from images and metadata
        step_info_text = f"""
=== STEP INFORMATION ===
- Step ID: {step_id}
- Description: 
- Joining Process: 
"""
    
    # 2. METADATA CONTEXT (Base Part + Joining Part)
    metadata_context = f"""
=== PART METADATA ===
**Base Part ({base_part_id}):**
```json
{json.dumps(base_metadata_filtered, indent=2, ensure_ascii=False)}
```

**Joining Part ({joining_part_id or "None"}):**
```json
{json.dumps(joining_metadata_filtered, indent=2, ensure_ascii=False)}
```
"""
    
    # Build message with reordered content: Step Info → Images → Metadata → Interaction
    message_content = [{"type": "text", "text": human_prompt_parts[0] + step_info_text}]
    
    # Add prior step images (if available)
    if prior_step_images:
        message_content.append({
            "type": "text",
            "text": f"\n### PRIOR STEP (Step {step_id - 1}) - Assembly State BEFORE Current Step:\n"
        })
        for img in prior_step_images:
            message_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{img['mime']};base64,{img['b64']}"
                }
            })
    
    # Add current step images
    message_content.append({
        "type": "text",
        "text": f"\n### CURRENT STEP (Step {step_id}) - Assembly State AFTER This Step:\n"
    })
    for img in step_images:
        message_content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{img['mime']};base64,{img['b64']}"
            }
        })
    
    # Add metadata after images
    message_content.append({"type": "text", "text": metadata_context})
    
    # Add interaction analysis context if provided
    if interaction_context:
        print(f"    [DEBUG] Adding interaction context ({len(interaction_context)} chars) to step {step_id} prompt")
        message_content.append({
            "type": "text",
            "text": "\n\n=== GEOMETRIC INTERACTION ANALYSIS ===\n" + interaction_context
        })
    else:
        print(f"    [DEBUG] No interaction context for step {step_id}")
    
    # Call LLM with System + Human messages
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message_content}
        ]

        response = invoke_with_retry(llm_structured, messages)
        
        # Defensive: handle case where response might be wrapped in dict with "parsed" key
        if isinstance(response, dict) and "parsed" in response:
            response = response["parsed"]
        
        # response is already FFA_Assessment_Complete instance (no ParsedChatCompletionMessage wrapping)
        assessment = response
        
        # Convert to dict
        assessment_dict = assessment.model_dump() if hasattr(assessment, "model_dump") else assessment
        
        # Override with cached values (für identische Teile)
        cache_used = False
        if cached_separation is not None:
            assessment_dict['separation'] = cached_separation
            cache_used = True
        if cached_handling is not None:
            assessment_dict['handling'] = cached_handling
            cache_used = True
        
        if cache_used:
            print(f"    → Applied cached Separation/Handling (Positioning/Joining freshly evaluated)")
        
        return {
            "step_id": step_id,
            "step_description": step_description,
            "base_part_id": base_part_id,
            "joining_part_id": joining_part_id,
            "joining_process": joining_process,
            "assessment": assessment_dict,
        }
    
    except Exception as e:
        print(f"    [ERROR] FFA Assessment failed for step {step_id}: {e}")
        import traceback
        traceback.print_exc()
        return {
            "step_id": step_id,
            "step_description": step_description,
            "base_part_id": base_part_id,
            "joining_part_id": joining_part_id,
            "joining_process": joining_process,
            "assessment": None,
            "error": str(e),
        }


def assess_assembly_sequence_ffa(
    sequence_json_path: Path,
    enriched_dir: Path,
    rendered_steps_dir: Path,
    output_dir: Path,
    prompt_id: str = "ffa_assessment_full_v1",
    base_metadata_keys: Optional[List[str]] = None,
    joining_metadata_keys: Optional[List[str]] = None,
    image_downscale: float = 1.0,
    step_img_keywords: Optional[List[str]] = None,
    prior_step_img_keywords: Optional[List[str]] = None,
    bom_json_path: Optional[Path] = None,
    interaction_analysis_data: Optional[Dict[str, Any]] = None,
    include_step_info: bool = True,
    parallel: bool = False,
    max_workers: int = 4,
    settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Bewertet komplette Assembly Sequence nach FFA-Kriterien.
    
    Args:
        sequence_json_path: Path to assembly_sequence.json
        enriched_dir: (Deprecated - kept for backward compatibility) Not used if bom_json_path provided
        rendered_steps_dir: Directory with rendered assembly steps
        output_dir: Output directory for FFA results
        prompt_id: Prompt template ID
        base_metadata_keys: Keys to extract from base part metadata
        joining_metadata_keys: Keys to extract from joining part metadata
        image_downscale: Image downscale factor
        step_img_keywords: Keywords to filter step images (e.g., ["isometric", "front"])
        prior_step_img_keywords: Keywords to filter prior step images (empty if step_id==1)
        bom_json_path: Path to BOM_enriched.json (recommended - more efficient than individual files)
        interaction_analysis_data: Optional interaction analysis data to enrich FFA assessment
        include_step_info: If False, omit step_description and joining_process from LLM prompts
    
    Returns:
        Dict with all step assessments + summary
    """
    print(f"\n{'='*80}")
    print("FFA ASSESSMENT - Fitness for Automation")
    print(f"{'='*80}\n")
    
    # FFA Cache: {metadata_hash: (normalized_part_id, assessment_dict)}
    # Verhindert doppelte Bewertungen für identische Teile (part_003_copy1, part_003_copy2, etc.)
    ffa_cache = {}
    cache_lock = threading.Lock()  # Schützt ffa_cache bei paralleler Ausführung
    
    # Load BOM_enriched.json for efficient part metadata access
    bom_data_full = {}
    if bom_json_path and bom_json_path.exists():
        print(f"Loading parts from BOM: {bom_json_path.name}")
        # Load full BOM - filtering happens per-part later
        with open(bom_json_path, "r", encoding="utf-8") as f:
            bom_data_full = json.load(f)
        
        parts_list = bom_data_full.get("parts", [])
        print(f"  Loaded {len(parts_list)} parts from BOM")
    else:
        print(f"No BOM provided - will load individual part files from {enriched_dir}")
    
    # Load assembly sequence
    if not sequence_json_path.exists():
        return {
            "status": "error",
            "error": f"Sequence file not found: {sequence_json_path}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    with open(sequence_json_path, "r", encoding="utf-8") as f:
        sequence_data = json.load(f)
    
    steps = sequence_data.get("steps", [])
    print(f"Loaded {len(steps)} assembly steps from {sequence_json_path.name}\n")
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # ── Per-step worker (runs sequentially or in parallel via ThreadPoolExecutor) ──
    def _process_step(step: Dict[str, Any]) -> Dict[str, Any]:
        """Process one assembly step: load metadata, images, run FFA LLM assessment."""
        step_id = step.get("step_id")
        step_description = step.get("step_description", "")
        base_part = step.get("base_part", "")
        joining_part = step.get("joining_part")
        joining_process = step.get("joining_process", "")
        belongs_to = step.get("belongs_to", "")
        
        print(f"[Step {step_id}] {step_description}")
        print(f"  Base: {base_part} | Joining: {joining_part} | Process: {joining_process}")
        print(f"  Belongs to: {belongs_to}")
        
        # Load and filter metadata from BOM
        base_metadata_full = None
        joining_metadata_full = None
        
        # Find base part in BOM
        if base_part and bom_data_full:
            parts_list = bom_data_full.get("parts", [])
            for part in parts_list:
                if part.get("part_id") == base_part:
                    base_metadata_full = part
                    break
        
        # Filter base part metadata to only needed keys
        base_metadata = filter_part_metadata(base_metadata_full, base_metadata_keys)
        if not base_metadata and base_part:
            print(f"  [WARNING] Base part metadata not found in BOM: {base_part}")
            base_metadata = {}
        
        # Handle joining_part: can be string or list
        # If list, use first part for metadata/cache (all parts in list should be identical)
        joining_part_for_metadata = joining_part
        if isinstance(joining_part, list) and len(joining_part) > 0:
            joining_part_for_metadata = joining_part[0]
            print(f"  [INFO] Multiple joining parts detected - using '{joining_part_for_metadata}' for FFA evaluation (assuming identical parts)")
        
        # Find joining part in BOM
        if joining_part_for_metadata and bom_data_full:
            parts_list = bom_data_full.get("parts", [])
            for part in parts_list:
                if part.get("part_id") == joining_part_for_metadata:
                    joining_metadata_full = part
                    break
        
        # Filter joining part metadata to only needed keys
        joining_metadata = filter_part_metadata(joining_metadata_full, joining_metadata_keys)
        if not joining_metadata and joining_part_for_metadata:
            print(f"  [WARNING] Joining part metadata not found in BOM: {joining_part_for_metadata}")
            joining_metadata = {}
        
        # Load step images
        step_images = []
        
        # Find all images for this step
        matching_images = list(rendered_steps_dir.glob(f"Step_{step_id:02d}_*.png"))
        if not matching_images:
            # Try without zero-padding
            matching_images = list(rendered_steps_dir.glob(f"Step_{step_id}_*.png"))
        
        # Filter by keywords if provided
        if step_img_keywords:
            from agent.tools import matches_image_keyword
            filtered_images = []
            for img_path in matching_images:
                if any(matches_image_keyword(img_path.name, kw) for kw in step_img_keywords):
                    filtered_images.append(img_path)
            matching_images = filtered_images
        
        if matching_images:
            # Load images with downscaling
            for img_path in matching_images:
                if image_downscale < 1.0:
                    # Downscale image
                    from PIL import Image
                    import io
                    import base64
                    
                    img = Image.open(img_path)
                    new_size = (int(img.width * image_downscale), int(img.height * image_downscale))
                    img_resized = img.resize(new_size, Image.Resampling.LANCZOS)
                    
                    buffer = io.BytesIO()
                    img_resized.save(buffer, format="PNG")
                    b64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
                    
                    step_images.append({
                        "path": str(img_path),
                        "filename": img_path.name,
                        "b64": b64_data,
                        "mime": "image/png"
                    })
                else:
                    # Use original image
                    import base64
                    with open(img_path, "rb") as f:
                        b64_data = base64.b64encode(f.read()).decode("utf-8")
                    
                    step_images.append({
                        "path": str(img_path),
                        "filename": img_path.name,
                        "b64": b64_data,
                        "mime": "image/png"
                    })
        
        if not step_images:
            print(f"  [WARNING] No renderings found for step {step_id}")
        else:
            print(f"  Loaded {len(step_images)} renderings")
        
        # Load prior step images (if step_id > 1 AND belongs to same assembly/subassembly)
        prior_step_images = []
        if step_id > 1 and prior_step_img_keywords:
            prior_step_id = step_id - 1
            
            # Check if prior step belongs to same assembly/subassembly
            prior_step = next((s for s in steps if s.get("step_id") == prior_step_id), None)
            if prior_step:
                prior_belongs_to = prior_step.get("belongs_to", "")
                
                # Only load prior images if same assembly/subassembly
                if prior_belongs_to == belongs_to:
                    # Find all images for prior step
                    prior_matching = list(rendered_steps_dir.glob(f"Step_{prior_step_id:02d}_*.png"))
                    if not prior_matching:
                        prior_matching = list(rendered_steps_dir.glob(f"Step_{prior_step_id}_*.png"))
                    
                    # Filter by keywords
                    if prior_step_img_keywords:
                        from agent.tools import matches_image_keyword
                        filtered_prior = []
                        for img_path in prior_matching:
                            if any(matches_image_keyword(img_path.name, kw) for kw in prior_step_img_keywords):
                                filtered_prior.append(img_path)
                        prior_matching = filtered_prior
                    
                    # Load prior images
                    if prior_matching:
                        for img_path in prior_matching:
                            if image_downscale < 1.0:
                                from PIL import Image
                                import io
                                import base64
                                
                                img = Image.open(img_path)
                                new_size = (int(img.width * image_downscale), int(img.height * image_downscale))
                                img_resized = img.resize(new_size, Image.Resampling.LANCZOS)
                                
                                buffer = io.BytesIO()
                                img_resized.save(buffer, format="PNG")
                                b64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
                                
                                prior_step_images.append({
                                    "path": str(img_path),
                                    "filename": img_path.name,
                                    "b64": b64_data,
                                    "mime": "image/png"
                                })
                            else:
                                import base64
                                with open(img_path, "rb") as f:
                                    b64_data = base64.b64encode(f.read()).decode("utf-8")
                                
                                prior_step_images.append({
                                    "path": str(img_path),
                                    "filename": img_path.name,
                                    "b64": b64_data,
                                    "mime": "image/png"
                                })
                        
                        print(f"  Loaded {len(prior_step_images)} prior step renderings (Step {prior_step_id}, same assembly)")
                else:
                    print(f"  [INFO] Prior step belongs to different assembly ('{prior_belongs_to}' vs '{belongs_to}') - skipping prior images")
        
        # Check FFA Cache for identical parts (Separation + Handling only)
        # Positioning and Joining are interaction-specific, not cached
        cached_separation = None
        cached_handling = None
        cache_source = None
        
        if joining_metadata:  # Only cache joining part (separation/handling)
            metadata_hash = get_metadata_hash(joining_metadata)
            normalized_id = normalize_part_id(joining_part_for_metadata)
            
            with cache_lock:
                if metadata_hash in ffa_cache:
                    cached_entry = ffa_cache[metadata_hash]
                    cached_separation = cached_entry.get('separation')
                    cached_handling = cached_entry.get('handling')
                    cache_source = cached_entry['part_id']
                    print(f"  [FFA CACHE] ✓ HIT: Reusing Separation/Handling from '{cache_source}' (identical metadata)")
                else:
                    print(f"  [FFA CACHE] ○ MISS: First occurrence of '{normalized_id}' - will evaluate and cache")
        
        # Assess step (cache will be used inside assess_step_ffa if provided)
        # Prepare interaction context if available (NEW)
        interaction_context = None
        if interaction_analysis_data:
            print(f"  [DEBUG] Interaction analysis data keys: {list(interaction_analysis_data.keys())}")
            # Extract detailed InteractionAnalysisDetail from steps array (not legacy step_interactions)
            ia_steps = interaction_analysis_data.get("steps", [])
            print(f"  [DEBUG] Found {len(ia_steps)} steps in interaction data")
            for ia_step in ia_steps:
                step_id_in_ia = ia_step.get("step_id")
                print(f"  [DEBUG] Checking step {step_id_in_ia} (looking for {step_id})...")
                if step_id_in_ia == step_id:
                    # Use the full InteractionAnalysisDetail structure
                    print(f"  [DEBUG] Step {step_id} matched! Keys in step: {list(ia_step.keys())}")
                    ia_detail = ia_step.get("InteractionAnalysisDetail", {})
                    print(f"  [DEBUG] InteractionAnalysisDetail found: {type(ia_detail).__name__}, empty: {not ia_detail}")
                    if ia_detail:
                        print(f"  [DEBUG] Creating interaction context for step {step_id}")
                        # "Stupid" approach: just include ALL fields from InteractionAnalysisDetail
                        # Convert field names from snake_case to Title Case for readability
                        interaction_context = "\n=== GEOMETRIC INTERACTION ANALYSIS (From Prior Step Analysis) ===\n"
                        
                        # Handle dict vs Pydantic model
                        if isinstance(ia_detail, dict):
                            detail_dict = ia_detail
                        else:
                            detail_dict = ia_detail.model_dump() if hasattr(ia_detail, 'model_dump') else dict(ia_detail)
                        
                        for field_name, field_value in detail_dict.items():
                            # Convert snake_case to Title Case
                            display_name = field_name.replace("_", " ").title()
                            interaction_context += f"\n**{display_name}:**\n"
                            interaction_context += f"{json.dumps(field_value, indent=2, ensure_ascii=False)}\n"
                        
                        print(f"  [DEBUG] Interaction context created: {len(interaction_context)} chars with {len(detail_dict)} fields")
                    else:
                        print(f"  [DEBUG] InteractionAnalysisDetail was empty for step {step_id}")
                    break
            else:
                print(f"  [DEBUG] Step {step_id} not found in interaction analysis data")
        else:
            print(f"  [DEBUG] No interaction_analysis_data provided")
        
        assessment_result = assess_step_ffa(
            step_id=step_id,
            step_description=step_description,
            base_part_id=base_part,
            joining_part_id=joining_part,
            joining_process=joining_process,
            base_metadata=base_metadata,
            joining_metadata=joining_metadata,
            step_images=step_images,
            prior_step_images=prior_step_images,
            prompt_id=prompt_id,
            cached_separation=cached_separation,
            cached_handling=cached_handling,
            interaction_context=interaction_context,
            include_step_info=include_step_info,
            settings=settings,
        )
        
        # Update cache with new assessment (Separation + Handling for joining part)
        if joining_metadata and "assessment" in assessment_result and assessment_result["assessment"]:
            metadata_hash = get_metadata_hash(joining_metadata)
            normalized_id = normalize_part_id(joining_part_for_metadata)
            
            # Only update cache if we did a new LLM call (not using cached values)
            # Double-check under lock: another thread may have already stored the same hash
            with cache_lock:
                if cache_source is None and metadata_hash not in ffa_cache:
                    assessment_data = assessment_result["assessment"]
                    ffa_cache[metadata_hash] = {
                        'part_id': normalized_id,
                        'separation': assessment_data.get('separation'),
                        'handling': assessment_data.get('handling'),
                    }
                    print(f"  [FFA CACHE] ✓ STORED: Cached Separation/Handling for '{normalized_id}' (hash: {metadata_hash[:8]}...)")
        
        if "error" in assessment_result:
            print(f"  ✗ Assessment failed: {assessment_result['error']}")
        else:
            print(f"  ✓ Assessment completed")
        print()
        return assessment_result

    # ── Dispatch: parallel vs. sequential ─────────────────────────────────────
    if parallel and max_workers > 1 and len(steps) > 1:
        print(f"[FFA ASSESSMENT] Running {len(steps)} steps in parallel (max_workers={max_workers})")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_process_step, step): step for step in steps}
            unordered: List[Dict[str, Any]] = []
            for future in as_completed(futures):
                unordered.append(future.result())
        step_assessments = sorted(unordered, key=lambda r: r.get("step_id") or 0)
    else:
        step_assessments = [_process_step(step) for step in steps]

    # Save results
    result = {
        "assembly_name": sequence_data.get("assembly_name"),
        "total_steps": len(steps),
        "assessed_steps": len(step_assessments),
        "step_assessments": step_assessments,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    output_file = output_dir / "ffa_assessment.json"
    from agent.tools import save_structured_json
    save_structured_json(output_file, result, add_metadata=True)
    
    print(f"✓ FFA Assessment saved to: {output_file}\n")
    
    # Create stripped version (nur Kriterien, keine reasoning/evidence)
    stripped_assessments = []
    for step_assessment in step_assessments:
        stripped_step = {
            "step_id": step_assessment["step_id"],
            "step_description": step_assessment["step_description"],
            "base_part_id": step_assessment["base_part_id"],
            "joining_part_id": step_assessment["joining_part_id"],
            "joining_process": step_assessment["joining_process"],
        }
        
        if "assessment" in step_assessment:
            stripped_step["assessment"] = strip_ffa_assessment(step_assessment["assessment"])
        else:
            stripped_step["assessment"] = None
            stripped_step["error"] = step_assessment.get("error")
        
        stripped_assessments.append(stripped_step)
    
    stripped_result = {
        "assembly_name": sequence_data.get("assembly_name"),
        "total_steps": len(steps),
        "assessed_steps": len(step_assessments),
        "step_assessments": stripped_assessments,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    stripped_output_file = output_dir / "ffa_assessment_stripped.json"
    with open(stripped_output_file, "w", encoding="utf-8") as f:
        json.dump(stripped_result, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Stripped version saved to: {stripped_output_file}")
    
    # Export to Excel/CSV
    save_ffa_to_excel(stripped_result, output_dir)
    
    print(f"{'='*80}\n")
    
    return result


# ============================================================================
#                    MAIN (for standalone testing)
# ============================================================================

if __name__ == "__main__":
    """
    Standalone test: Assess FFA for latest experiment run.
    """
    workspace_root = Path(__file__).resolve().parents[1]
    
    # Find latest experiment
    experiments_dir = workspace_root / "data" / "experiments"
    debug_folders = sorted([d for d in experiments_dir.glob("debug_ASG_*")], reverse=True)
    
    if not debug_folders:
        print("No experiment folders found!")
        exit(1)
    
    latest_exp = debug_folders[0]
    print(f"Using latest experiment: {latest_exp.name}\n")
    
    # Find latest run
    run_folders = sorted([d for d in latest_exp.glob("assembly_sequence_run*")], reverse=True)
    if not run_folders:
        print("No assembly sequence runs found!")
        exit(1)
    
    latest_run = run_folders[0]
    print(f"Using latest run: {latest_run.name}\n")
    
    # Setup paths
    sequence_json = latest_run / "assembly_sequence.json"
    enriched_dir = workspace_root / "data" / "processed" / "stepparser" / "worm_gear_demonstrator" / "enriched_parts"
    rendered_steps = latest_run / "rendered_steps"
    output_dir = latest_run / "ffa_assessment"
    
    # Run assessment
    result = assess_assembly_sequence_ffa(
        sequence_json_path=sequence_json,
        enriched_dir=enriched_dir,
        rendered_steps_dir=rendered_steps,
        output_dir=output_dir,
        prompt_id="ffa_assessment_full_v1",
        base_metadata_keys=["part_name_guess", "geometry_features", "material_info"],
        joining_metadata_keys=["part_name_guess", "geometry_features", "material_info"],
        image_downscale=0.7,
    )
    
    print(f"Assessment complete. Status: {result.get('status', 'unknown')}")
