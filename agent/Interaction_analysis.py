"""
Interaction Analysis - Geometric Interaction Analysis

Analysiert geometrische Interaktionen zwischen Bauteilen pro Assembly Step.
Nutzt Rendering + BOM Metadaten für LLM-basierte räumliche Analyse.

Diese Datei läuft UNABHÄNGIG vom Workflow_enrich_data.py.

Usage:
    python -m agent.Interaction_analysis

Features:
1. Per-step geometric interaction analysis (NEW interactions only, not accumulative)
2. Multimodal LLM (GPT-4o Vision) analyzing:
   - Contact surfaces between base + joining parts
   - Alignment challenges
   - Collision risks
   - Assembly feasibility
3. Step renderings + monopart renderings (optional)
4. BOM metadata filtering via JSON keys
5. Structured output with confidence scores

Workflow Integration siehe: workflow.py → _node_interaction_analysis()
"""

from __future__ import annotations

import os
import json
import re
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

# LLM + utilities
try:
    from agent.tools import _get_img_describer_llm, extract_json_keys_from_file, ImageLoader
    from agent.prompt_store import get_prompt_template
    from agent.tools import save_structured_json
    from agent.structured_output import StepInteractionAnalysis, InteractionAnalysisDetailed
except ImportError:
    from tools import _get_img_describer_llm, extract_json_keys_from_file, ImageLoader
    from prompt_store import get_prompt_template
    from tools import save_structured_json
    from structured_output import StepInteractionAnalysis, InteractionAnalysisDetailed

# ============================================================================
#                    UTILITIES
# ============================================================================

def normalize_part_id(part_id: str) -> str:
    """
    Entfernt _copyN suffix von part_id.
    
    Beispiele:
        part_003_copy1 -> part_003
        part_003 -> part_003
    """
    return re.sub(r'_copy\d+$', '', part_id)


def _extract_interaction_detail_payload(payload: Any) -> Any:
    """Accept bare IA details or common wrapper objects returned by fallback LLM calls."""
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump()

    while isinstance(payload, dict) and "parsed" in payload:
        payload = payload["parsed"]
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump()

    if isinstance(payload, dict):
        for key in (
            "InteractionAnalysisDetail",
            "InteractionAnalysisDetailed",
            "interaction_analysis_detail",
            "interaction_detail",
            "interaction_analysis",
            "analysis",
            "result",
        ):
            nested = payload.get(key)
            if nested is not None:
                return _extract_interaction_detail_payload(nested)

    return payload


def _interaction_detail_only_instruction() -> str:
    keys = "\n".join(f"- {key}" for key in InteractionAnalysisDetailed.model_fields)
    return (
        "\n\nIMPORTANT FALLBACK OUTPUT FORMAT:\n"
        "Return one valid JSON object for InteractionAnalysisDetailed only. "
        "Do not include step_id, step_description, InteractionAnalysisDetail, markdown, or surrounding text. "
        "The JSON object must contain exactly these top-level keys, each as an array of strings:\n"
        f"{keys}"
    )


def get_monopart_renderings(
    part_id: str,
    stepparser_dir: Path,
    keywords: Optional[List[str]] = None,
    downscale_factor: float = 1.0
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Lädt Renderings für ein Part aus stepparser output.
    
    Handling von Copies: part_003_copy1 → versucht part_003 zu laden (base part)
    
    Args:
        part_id: Part ID (e.g., 'part_003' oder 'part_003_copy1')
        stepparser_dir: Base directory z.B. data/processed/stepparser/{assembly}/
        keywords: Keywords zum Filtern (z.B. ["iso1", "iso2"])
        downscale_factor: Image scaling (0.5 = half size)
    
    Returns:
        Dict: {"part_id": [list of image dicts]}
    """
    # Normalisiere auf base part (entferne _copy1, _copy2, etc.)
    base_part_id = normalize_part_id(part_id)
    
    # Finde Part-Ordner: part_XXX/ oder part_XXX_unique/
    part_folders = []
    for pattern in [f"{base_part_id}/", f"{base_part_id}_unique/"]:
        folder = stepparser_dir / pattern
        if folder.exists():
            part_folders.append(folder)
    
    if not part_folders:
        return {base_part_id: []}
    
    # Load images from first matching folder
    part_folder = part_folders[0]
    result_images = []
    
    try:
        if downscale_factor < 1.0:
            from PIL import Image
            import io
            import base64
            
            for img_file in part_folder.glob("*.png"):
                # Filter by keywords if provided
                if keywords and not any(kw in img_file.name for kw in keywords):
                    continue
                
                try:
                    img = Image.open(img_file)
                    new_size = (int(img.width * downscale_factor), int(img.height * downscale_factor))
                    img_resized = img.resize(new_size, Image.Resampling.LANCZOS)
                    
                    buffer = io.BytesIO()
                    img_resized.save(buffer, format="PNG")
                    b64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
                    
                    result_images.append({
                        "filename": img_file.name,
                        "b64": b64_data,
                        "mime": "image/png"
                    })
                except Exception as e:
                    print(f"    [WARNING] Could not load {img_file.name}: {e}")
        else:
            # Use original images
            loader = ImageLoader(str(part_folder))
            for img_file in part_folder.glob("*.png"):
                # Filter by keywords
                if keywords and not any(kw in img_file.name for kw in keywords):
                    continue
                
                try:
                    b64_data = loader.load_image_b64(img_file.name)
                    result_images.append({
                        "filename": img_file.name,
                        "b64": b64_data,
                        "mime": "image/png"
                    })
                except Exception as e:
                    print(f"    [WARNING] Could not load {img_file.name}: {e}")
    except Exception as e:
        print(f"    [ERROR] Failed to load images from {part_folder}: {e}")
    
    return {base_part_id: result_images}


def get_step_renderings(
    step_folder: Path,
    keywords: Optional[List[str]] = None,
    downscale_factor: float = 1.0,
) -> List[Dict[str, Any]]:
    """
    Lädt Renderings eines Assembly Steps.
    
    Args:
        step_folder: Folder mit Step_N_*.png files
        keywords: Keywords zum Filtern (z.B. ["iso1_transp_0_3"])
        downscale_factor: Image scaling (0.5 = half)
    
    Returns:
        List of image dicts: [{"filename": ..., "b64": ..., "mime": ...}]
    """
    if not step_folder.exists():
        return []
    
    result_images = []
    
    try:
        if downscale_factor < 1.0:
            from PIL import Image
            import io
            import base64
            
            for img_file in step_folder.glob("*.png"):
                # Filter by keywords
                if keywords and not any(kw in img_file.name for kw in keywords):
                    continue
                
                try:
                    img = Image.open(img_file)
                    new_size = (int(img.width * downscale_factor), int(img.height * downscale_factor))
                    img_resized = img.resize(new_size, Image.Resampling.LANCZOS)
                    
                    buffer = io.BytesIO()
                    img_resized.save(buffer, format="PNG")
                    b64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
                    
                    result_images.append({
                        "filename": img_file.name,
                        "b64": b64_data,
                        "mime": "image/png"
                    })
                except Exception as e:
                    print(f"    [WARNING] Could not downscale {img_file.name}: {e}")
        else:
            # Use original images
            loader = ImageLoader(str(step_folder))
            for img_file in step_folder.glob("*.png"):
                # Filter by keywords
                if keywords and not any(kw in img_file.name for kw in keywords):
                    continue
                
                try:
                    b64_data = loader.load_image_b64(img_file.name)
                    result_images.append({
                        "filename": img_file.name,
                        "b64": b64_data,
                        "mime": "image/png"
                    })
                except Exception as e:
                    print(f"    [WARNING] Could not load {img_file.name}: {e}")
    except Exception as e:
        print(f"    [ERROR] Failed to load step images from {step_folder}: {e}")
    
    return result_images


# ============================================================================
#                    CORE ANALYSIS LOGIC
# ============================================================================

def analyze_step_interaction(
    step_id: int,
    step_description: str,
    base_part_id: str,
    joining_part_ids: Optional[List[str]],
    base_metadata: Dict[str, Any],
    joining_metadata: Optional[List[Dict[str, Any]]],
    step_images: List[Dict[str, Any]],
    monopart_images: Dict[str, List[Dict[str, Any]]],
    joining_process: str = "",
    belongs_to: str = "",
    system_prompt_id: str = "interaction_analyst_system_v1",
    human_prompt_id: str = "interaction_analysis_task_v1",
    prior_step_images: Optional[List[Dict[str, Any]]] = None,
    additional_context_block: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Analysiert geometrische Interaktion für einen Step mit LLM.
    
    Args:
        step_id: Step ID
        step_description: Step description
        base_part_id: Base part
        joining_part_ids: List of joining parts (e.g., ["part_003"])
        base_metadata: Base part metadata (already filtered)
        joining_metadata: List of joining part metadata (already filtered)
        step_images: List of current step renderings
        monopart_images: Dict of {part_id: [images]}
        joining_process: Joining process type (Place, Insert, Screw, etc.)
        belongs_to: Assembly context (e.g., "Assembly (basic config)", "Subassy 1")
        system_prompt_id: System prompt ID (defaults to "interaction_analyst_system_v1")
        human_prompt_id: Human prompt ID (defaults to "interaction_analysis_task_v1")
    
    Returns:
        Dict with interaction analysis matching StepInteractionAnalysis schema
    """
    # Get LLM
    llm = _get_img_describer_llm(max_completion_tokens=4000)
    
    # Load prompts from prompt_store
    try:
        from agent.prompt_store import get_prompt_template
    except ImportError:
        from prompt_store import get_prompt_template
    
    system_prompt = get_prompt_template(system_prompt_id)
    if not system_prompt:
        print(f"    [WARNING] System prompt '{system_prompt_id}' not found, using default")
        system_prompt = "You are a geometric interaction analyst. Analyze spatial relationships and interactions between assembly parts."
    
    human_template = get_prompt_template(human_prompt_id)
    if not human_template:
        print(f"    [WARNING] Human prompt '{human_prompt_id}' not found, using default")
        human_template = """Analyze the geometric interaction between the base part and joining parts for this assembly step.
Base Part: {base_part}
Joining Parts: {joining_parts}

Analyze and return structured JSON with positioning, accessibility, motion, tolerances, stability, feeding, and fixing information."""
    
    # Build human prompt
    joining_parts_str = ", ".join(joining_part_ids) if joining_part_ids else "none"
    
    try:
        human_prompt = human_template.format(
            step_id=step_id,
            step_description=step_description,
            base_part=base_part_id,
            joining_parts=joining_parts_str,
        )
    except KeyError:
        # Fallback if template doesn't have all keys
        human_prompt = human_template
    
    # Add metadata context
    metadata_context = f"""

=== ASSEMBLY STEP INFORMATION ===

**Step Details:**
- Step ID: {step_id}
- Description: {step_description}
- Assembly Context: {belongs_to}
- Joining Process: {joining_process}
- Base Part: {base_part_id if base_part_id else "None (initial placement)"}
- Joining Parts: {joining_parts_str}

=== PART METADATA ===

**Base Part ({base_part_id}):**
```json
{json.dumps(base_metadata, indent=2, ensure_ascii=False)}
```

**Joining Parts ({joining_parts_str}):**
"""
    
    if joining_metadata:
        for i, metadata in enumerate(joining_metadata):
            metadata_context += f"\n```json\n{json.dumps(metadata, indent=2, ensure_ascii=False)}\n```\n"
    else:
        metadata_context += "None\n"
    
    human_prompt += metadata_context

    try:
        from agent.tools import format_content_agent_context_block
        content_agent_block = format_content_agent_context_block(additional_context_block)
    except Exception:
        content_agent_block = None
    if content_agent_block:
        label, context_text = content_agent_block
        human_prompt += f"\n\n=== {label} ===\n{context_text}"
    
    # Build message with images
    message_content = [{"type": "text", "text": human_prompt}]
    
    # Add prior step images (state WITHOUT joining part)
    if prior_step_images:
        message_content.append({
            "type": "text",
            "text": f"\n### PRIOR STATE – Assembly WITHOUT joining part (before step {step_id}):\n"
        })
        for img in prior_step_images:
            message_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{img['mime']};base64,{img['b64']}"
                }
            })

    # Add current step images (state WITH joining part)
    if step_images:
        message_content.append({
            "type": "text",
            "text": f"\n### CURRENT STATE – Assembly WITH joining part added (after step {step_id}):\n"
        })
        for img in step_images:
            message_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{img['mime']};base64,{img['b64']}"
                }
            })
    
    # Call LLM
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message_content}
        ]
        
        # Call LLM with structured output schema enforcement
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
        
        def llm_invoke_call():
            # Use with_structured_output without include_raw - returns parsed object directly
            # This avoids Pydantic serialization warnings from ParsedChatCompletionMessage
            structured_llm = llm.with_structured_output(InteractionAnalysisDetailed)
            return structured_llm.invoke(messages)
        
        try:
            # Execute with timeout
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(llm_invoke_call)
            try:
                interaction_detail = future.result(timeout=300)  # 300 second timeout
            except (FuturesTimeoutError, TimeoutError, KeyboardInterrupt):
                future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                raise
            except Exception:
                executor.shutdown(wait=False, cancel_futures=True)
                raise
            else:
                executor.shutdown(wait=True)
            
            # Defensive: handle case where response might be wrapped in dict with "parsed" key
            if isinstance(interaction_detail, dict) and "parsed" in interaction_detail:
                interaction_detail = interaction_detail["parsed"]
            
            # Ensure we have an InteractionAnalysisDetailed instance
            if not isinstance(interaction_detail, InteractionAnalysisDetailed):
                # Convert to dict if it's a Pydantic object and back, to ensure clean serialization
                interaction_detail = InteractionAnalysisDetailed.model_validate(
                    _extract_interaction_detail_payload(interaction_detail)
                )
            
            result = StepInteractionAnalysis(
                step_id=step_id,
                step_description=step_description,
                InteractionAnalysisDetail=interaction_detail
            )
            
            return result.model_dump()
            
        except (FuturesTimeoutError, TimeoutError, KeyboardInterrupt) as e:
            print(f"    [WARNING] LLM call timeout/cancelled ({type(e).__name__}), returning step error")
            raise TimeoutError(f"Interaction analysis LLM call timed out for step {step_id}") from e

        except Exception as e:
            print(f"    [WARNING] Structured LLM call failed ({type(e).__name__}), using fallback")
            # Fallback to manual JSON parsing without structured output. Keep the
            # requested shape identical to InteractionAnalysisDetailed; Python
            # owns step_id/step_description wrapping below.
            fallback_messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": message_content + [
                        {"type": "text", "text": _interaction_detail_only_instruction()}
                    ],
                },
            ]
            response = llm.invoke(fallback_messages)
            
            # Extract text response
            if hasattr(response, "content"):
                llm_response_text = response.content
            else:
                llm_response_text = str(response)
            
            # Parse JSON from LLM response
            try:
                # Try to extract JSON from response (may contain surrounding text)
                json_match = re.search(r'\{.*\}', llm_response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    analysis_data = json.loads(json_str)
                else:
                    # Fallback: treat entire response as JSON attempt
                    analysis_data = json.loads(llm_response_text)

                # Validate response with Pydantic
                interaction_detail = InteractionAnalysisDetailed.model_validate(
                    _extract_interaction_detail_payload(analysis_data)
                )

                result = StepInteractionAnalysis(
                    step_id=step_id,
                    step_description=step_description,
                    InteractionAnalysisDetail=interaction_detail
                )

                return result.model_dump()

            except (json.JSONDecodeError, TypeError, ValueError) as json_err:
                print(f"    [WARNING] Could not parse JSON from LLM response for step {step_id}: {json_err}")
                raise json_err
    
    except Exception as e:
        print(f"    [ERROR] Interaction analysis failed for step {step_id}: {e}")
        import traceback
        traceback.print_exc()
        
        # Return error result with structured format
        interaction_detail = InteractionAnalysisDetailed(
            geometric_interaction=[f"Error during analysis: {str(e)}"],
            positioning_possibilities=[],
            accuracy_of_target_position=[f"Error during analysis: {str(e)}"],
            positioning_aids=[],
            additional_orientation_by_rotation=[],
            accessibility_to_joining_position=[],
            joining_motion=[],
            joining_tolerances=[],
            stability_in_positioned_state=[],
            feeding_of_joining_element=[],
            fixing_of_mounted_part=[]
        )
        
        result = StepInteractionAnalysis(
            step_id=step_id,
            step_description=step_description,
            InteractionAnalysisDetail=interaction_detail
        )
        
        return {**result.model_dump(), "error": str(e)}


def analyze_assembly_sequence_interactions(
    sequence_json_path: Path,
    rendered_steps_dir: Path,
    stepparser_dir: Path,
    output_dir: Path,
    bom_json_path: Optional[Path] = None,
    system_prompt_id: str = "Interaction_Analyst_V1",
    human_prompt_id: str = "Analyse_Interaction_V1",
    base_metadata_keys: Optional[List[str]] = None,
    joining_metadata_keys: Optional[List[str]] = None,
    sequence_step_img_keywords: Optional[List[str]] = None,
    monopart_img_keywords: Optional[List[str]] = None,
    include_monopart_renderings: bool = True,
    image_downscale: float = 1.0,
    parallel: bool = False,
    max_workers: int = 4,
    additional_context_block: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Analysiert geometrische Interaktionen für komplette Assembly Sequence.
    
    Args:
        sequence_json_path: Path zu assembly_sequence.json
        rendered_steps_dir: Directory mit sequence_renderings/
        stepparser_dir: Base directory mit Part-Renderings
        output_dir: Output directory für Ergebnisse
        bom_json_path: Path zu BOM_enriched.json (optional, für Metadaten)
        system_prompt_id: System prompt ID
        human_prompt_id: Human prompt ID
        base_metadata_keys: Keys für base part metadata
        joining_metadata_keys: Keys für joining part metadata
        sequence_step_img_keywords: Keywords für Step-Bilder
        monopart_img_keywords: Keywords für Part-Bilder
        include_monopart_renderings: Ob Part-Renderings einbinden
        image_downscale: Image scaling factor
    
    Returns:
        Dict mit allen Step-Analysen + Summary
    """
    print(f"\n{'='*80}")
    print("INTERACTION ANALYSIS - Geometric Interaction Analysis")
    print(f"{'='*80}\n")
    
    # Load BOM data for metadata
    bom_data_full = {}
    if bom_json_path and bom_json_path.exists():
        print(f"Loading parts from BOM: {bom_json_path.name}")
        with open(bom_json_path, "r", encoding="utf-8") as f:
            bom_data_full = json.load(f)
        parts_count = len(bom_data_full.get("parts", []))
        print(f"  Loaded {parts_count} parts\n")
    
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
    print(f"Loaded {len(steps)} assembly steps\n")
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    partial_output_file = output_dir / "interaction_analysis_partial.json"

    def _output_payload(step_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        ordered = sorted(step_results, key=lambda result: result.get("step_id") or 0)
        return {
            "assembly_name": sequence_data.get("assembly_name", "unknown"),
            "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
            "system_prompt_id": system_prompt_id,
            "human_prompt_id": human_prompt_id,
            "steps": ordered,
            "summary": {
                "total_steps_expected": len(steps),
                "total_steps_analyzed": len(ordered),
                "successful_analyses": len([item for item in ordered if "error" not in item]),
                "failed_analyses": len([item for item in ordered if "error" in item]),
            },
        }

    def _save_partial(step_results: List[Dict[str, Any]]) -> None:
        save_structured_json(
            partial_output_file,
            _output_payload(step_results),
            add_metadata=False,
        )

    _save_partial([])

    # Pre-load ALL step renderings once (avoids N redundant disk reads in the loop)
    all_step_images = get_step_renderings(
        rendered_steps_dir,
        keywords=sequence_step_img_keywords,
        downscale_factor=image_downscale,
    )

    # ── Helper function for nested key filtering ──────────────────────────────
    def filter_part_metadata(part_data: Dict[str, Any], keys: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Filter part metadata on desired keys, supporting nested keys with dot notation.
        
        Args:
            part_data: Part metadata dict from BOM
            keys: Keys to keep (None = keep all). Supports nested keys like "monopart_analysis.geometric_characteristics"
        
        Returns:
            Filtered dict with nested structure preserved
        """
        if not keys or not part_data:
            return part_data or {}
        
        filtered = {}
        for key in keys:
            # Check if key contains dot notation (nested key)
            if "." in key:
                # Navigate nested structure
                keys_path = key.split(".")
                current = part_data
                
                # Try to traverse the path
                try:
                    for k in keys_path:
                        if isinstance(current, dict) and k in current:
                            current = current[k]
                        else:
                            current = None
                            break
                    
                    if current is not None:
                        # Add to filtered dict with nested structure preserved
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

    # ── Per-step worker ──────────────────────────────────────────────────────
    def _process_step(step: Dict[str, Any]) -> Dict[str, Any]:
        step_id = step.get("step_id")
        step_description = step.get("step_description", "")
        base_part = step.get("base_part", "")
        joining_part = step.get("joining_part")
        belongs_to = step.get("belongs_to", "")

        print(f"[Step {step_id}] {step_description}")
        print(f"  Base: {base_part} | Joining: {joining_part}")

        joining_parts_list = joining_part if isinstance(joining_part, list) else ([joining_part] if joining_part else [])

        # Metadata from BOM (read-only – thread-safe)
        base_metadata = {}
        if bom_json_path and bom_data_full.get("parts"):
            for part in bom_data_full["parts"]:
                if part.get("part_id") == base_part:
                    base_metadata = part
                    if base_metadata_keys:
                        base_metadata = filter_part_metadata(base_metadata, base_metadata_keys)
                    break

        joining_metadata_list = []
        for joining_part_id in joining_parts_list:
            joining_meta = {}
            if bom_json_path and bom_data_full.get("parts"):
                for part in bom_data_full["parts"]:
                    if part.get("part_id") == normalize_part_id(joining_part_id):
                        joining_meta = part
                        if joining_metadata_keys:
                            joining_meta = filter_part_metadata(joining_meta, joining_metadata_keys)
                        break
            joining_metadata_list.append(joining_meta)

        # Current step images – WITH joining part (filenames contain "_after_" or are ISO views)
        step_images = [
            img for img in all_step_images
            if img["filename"].startswith(f"step_{step_id:02d}_")
            and "_before_" not in img["filename"]
        ]

        # Prior step images – get images from PREVIOUS step
        prior_step_images = []
        if step_id > 1:
            prior_step_images = [
                img for img in all_step_images
                if img["filename"].startswith(f"step_{step_id-1:02d}_")
                and "_before_" not in img["filename"]
            ]

        # Optional monopart renderings
        monopart_renderings = {}
        if include_monopart_renderings:
            if base_part:
                monopart_renderings.update(
                    get_monopart_renderings(base_part, stepparser_dir, keywords=monopart_img_keywords, downscale_factor=image_downscale)
                )
            for joining_part_id in joining_parts_list:
                monopart_renderings.update(
                    get_monopart_renderings(normalize_part_id(joining_part_id), stepparser_dir, keywords=monopart_img_keywords, downscale_factor=image_downscale)
                )

        analysis_result = analyze_step_interaction(
            step_id=step_id,
            step_description=step_description,
            base_part_id=base_part,
            joining_part_ids=joining_parts_list,
            base_metadata=base_metadata,
            joining_metadata=joining_metadata_list,
            step_images=step_images,
            monopart_images=monopart_renderings,
            joining_process=step.get("joining_process", ""),
            belongs_to=belongs_to,
            system_prompt_id=system_prompt_id,
            human_prompt_id=human_prompt_id,
            prior_step_images=prior_step_images,
            additional_context_block=additional_context_block,
        )

        if not isinstance(analysis_result, dict):
            analysis_result = {
                "step_id": step_id,
                "step_description": step_description,
                "InteractionAnalysisDetail": {},
                "error": "No analysis result returned",
            }

        if analysis_result and "error" not in analysis_result:
            print(f"  ✓ Analysis complete")
        else:
            print(f"  ✗ Analysis failed: {analysis_result.get('error')}")
        return analysis_result

    # ── Dispatch ─────────────────────────────────────────────────────────
    if parallel and max_workers > 1 and len(steps) > 1:
        print(f"[IA] Running {len(steps)} steps in parallel (max_workers={max_workers})")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_process_step, step): step for step in steps}
            unordered: List[Dict[str, Any]] = []
            for future in as_completed(futures):
                unordered.append(future.result())
                _save_partial(unordered)
        step_analyses = sorted(unordered, key=lambda r: r.get("step_id") or 0)
    else:
        step_analyses = []
        for step in steps:
            step_analyses.append(_process_step(step))
            _save_partial(step_analyses)
    output_data = _output_payload(step_analyses)
    
    # Save output
    output_file = output_dir / "interaction_analysis.json"
    save_structured_json(output_file, output_data, add_metadata=False)
    partial_output_file.unlink(missing_ok=True)
    print(f"\n✓ Analysis saved: {output_file}")
    
    return {
        "status": "success",
        "output_file": str(output_file),
        "output_data": output_data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================================
#                    MAIN ENTRY POINT (STANDALONE)
# ============================================================================

if __name__ == "__main__":
    # Standalone testing
    import sys
    from pathlib import Path
    
    assembly_name = "IPA_Reducer_Case"
    experiment_name = "expX_most_info"
    run_base = Path(f"data/experiments/run_2026-02-23_081633/{experiment_name}/{assembly_name}/assembly_sequence_run1")
    
    if not run_base.exists():
        print(f"ERROR: Run directory not found: {run_base}")
        sys.exit(1)
    
    sequence_file = run_base / "assembly_sequence.json"
    rendered_dir = run_base / "sequence_renderings"
    stepparser_base = Path(f"data/processed/stepparser/{assembly_name}")
    output_base = run_base  # Save in same directory
    
    bom_file = Path(f"data/experiments/run_2026-02-23_081633/{experiment_name}/{assembly_name}/{assembly_name}_BOM_enriched.json")
    
    result = analyze_assembly_sequence_interactions(
        sequence_json_path=sequence_file,
        rendered_steps_dir=rendered_dir,
        stepparser_dir=stepparser_base,
        output_dir=output_base,
        bom_json_path=bom_file if bom_file.exists() else None,
        system_prompt_id="Interaction_Analyst_V1",
        human_prompt_id="Analyse_Interaction_V1",
        base_metadata_keys=["part_id", "part_name_guess", "geometry_description"],
        joining_metadata_keys=["part_id", "part_name_guess", "material_word", "geometry_description", "functional_surfaces"],
        sequence_step_img_keywords=["iso1_transp_0_3"],
        monopart_img_keywords=["iso1_transp_0_0", "iso1_transp_0_3"],
        include_monopart_renderings=True,
        image_downscale=0.7,
    )
    
    print(f"\nResult: {result.get('status')}")
    if result.get("status") == "success":
        print(f"Output: {result.get('output_file')}")
