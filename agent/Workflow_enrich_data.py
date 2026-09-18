from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
import json
from datetime import datetime, timezone
import time

try:
	from langgraph.checkpoint.memory import InMemorySaver
	from langgraph.graph import END, StateGraph
except ImportError:  # pragma: no cover
	# Keep imports local-friendly if this file is executed outside package context.
	from langgraph.checkpoint.memory import InMemorySaver
	from langgraph.graph import END, StateGraph


try:
	from agent.tools import analyse_assembly_img, analyse_monopart_img, _get_experiment_output_dir
except ImportError:  # pragma: no cover
	from tools import analyse_assembly_img, analyse_monopart_img, _get_experiment_output_dir


try:
	from agent.merge_enriched import merge_copy_part_data
except ImportError:  # pragma: no cover
	from merge_enriched import merge_copy_part_data


try:
	from agent.prompt_store import resolve_stepparser_layout_vars
except ImportError:  # pragma: no cover
	from prompt_store import resolve_stepparser_layout_vars


try:
	from agent.prompt_store import load_experiment_settings
except ImportError:  # pragma: no cover
	from prompt_store import load_experiment_settings


try:
	from agent.prompt_store import get_prompt_template, get_system_prompt, get_user_bootstrap_prompt
except ImportError:  # pragma: no cover
	from prompt_store import get_prompt_template, get_system_prompt, get_user_bootstrap_prompt


try:
	from agent.utils import (
		wprint as _wprint,
		carry as _carry,
		format_metadata_files_in_prompt as _format_metadata_files_in_prompt,
		token_usage_from_tool_result as _token_usage_from_tool_result,
		sha256_text as _sha256_text,
		extract_step_details as _extract_step_details,
	)

except ImportError:  # pragma: no cover
	from utils import (  # type: ignore
		wprint as _wprint,
		carry as _carry,
		format_metadata_files_in_prompt as _format_metadata_files_in_prompt,
		token_usage_from_tool_result as _token_usage_from_tool_result,
		sha256_text as _sha256_text,
		extract_step_details as _extract_step_details,
	)


def _sequence_validation_condition(state: Dict[str, Any]) -> str:
	"""Choose next workflow step after validation results."""
	if not state.get("enable_sequence_validation", True):
		return "complete"
	if state.get("sequence_iterations_exhausted", False):
		return "exhausted"
	if state.get("sequence_needs_regeneration", False):
		return "retry"
	return "complete"


def _node_resolve_paths(state: Dict[str, Any]) -> Dict[str, Any]:
	root = Path(state["datasource_root"]).expanduser()
	if not root.exists() or not root.is_dir():
		raise FileNotFoundError(f"datasource_root does not exist or is not a directory: {root}")

	layout = resolve_stepparser_layout_vars(str(root))
	assembly_dir = str(layout.get("assembly_dir") or "").strip()
	use_unique_parts = bool(state.get("use_unique_parts", True))
	part_dirs = list((layout.get("unique_part_dirs") if use_unique_parts else layout.get("part_dirs")) or [])

	if not assembly_dir:
		raise FileNotFoundError(f"Could not resolve assembly_dir under: {root}")

	_wprint(
		state,
		"[resolve_paths] assembly_dir="
		+ assembly_dir
		+ f" | parts={'unique' if use_unique_parts else 'all'}:{len(part_dirs)}",
	)

	return _carry(
		state,
		datasource_root=str(root),
		assembly_dir=assembly_dir,
		part_dirs=[str(p) for p in part_dirs],
	)


def _node_run_assembly(state: Dict[str, Any]) -> Dict[str, Any]:
	datasource_root = state["datasource_root"]
	assembly_dir = state["assembly_dir"]
	part_dirs = list(state.get("part_dirs") or [])
	payload: Dict[str, Any] = {"searchdir": str(assembly_dir)}

	# Optional knobs
	if state.get("assembly_keywords"):
		payload["keywords"] = list(state["assembly_keywords"])  # type: ignore[arg-type]
	if state.get("assembly_limit") is not None:
		payload["limit"] = int(state["assembly_limit"])
	if state.get("overwrite_assembly_metadata") is not None:
		payload["overwrite_metadata"] = bool(state["overwrite_assembly_metadata"])

	_wprint(state, f"[run_assembly] dir={assembly_dir}")
	result = analyse_assembly_img.invoke(payload)
	_wprint(state, f"[run_assembly] metadata_in_prompt: {_format_metadata_files_in_prompt(result)}")
	try:
		stats = ((result or {}).get("analysis") or {}).get("stats") or {}
		prev = stats.get("prompt_preview")
		imgs = [x.get("pic_name") for x in (((result or {}).get("analysis") or {}).get("selected") or [])]
		if prev:
			_wprint(state, f"[run_assembly] prompt_id={stats.get('prompt_id')} | images={imgs}")
			_wprint(state, "[run_assembly] prompt_preview:\n" + str(prev))
	except Exception:
		pass

	return _carry(
		state,
		datasource_root=datasource_root,
		assembly_dir=assembly_dir,
		part_dirs=[str(p) for p in part_dirs],
		assembly_result=result,
	)


def _node_list_parts(state: Dict[str, Any]) -> Dict[str, Any]:
	datasource_root = state["datasource_root"]
	assembly_dir = state["assembly_dir"]
	part_dirs = list(state.get("part_dirs") or [])
	return _carry(
		state,
		datasource_root=datasource_root,
		assembly_dir=assembly_dir,
		part_dirs=[str(p) for p in part_dirs],
	)


def _run_one_part(part_dir: str, part_keywords: Optional[List[str]], part_limit: Optional[int]) -> Dict[str, Any]:
	payload: Dict[str, Any] = {"searchdir": part_dir}
	if part_keywords:
		payload["keywords"] = list(part_keywords)
	if part_limit is not None:
		payload["limit"] = int(part_limit)
	return analyse_monopart_img.invoke(payload)


def _node_run_monoparts(state: Dict[str, Any]) -> Dict[str, Any]:
	datasource_root = state.get("datasource_root")
	assembly_dir = state.get("assembly_dir")
	part_dirs: List[str] = list(state.get("part_dirs") or [])
	parallel = bool(state.get("parallel", False))
	max_workers = int(state.get("max_workers") or 4)
	part_keywords = list(state.get("part_keywords") or []) or None
	part_limit = int(state.get("part_limit") or 8)

	results: List[Dict[str, Any]] = []
	warnings: List[str] = []

	if not part_dirs:
		warnings.append("No Part_* directories found; skipping monopart enrichment")
		return _carry(
			state,
			datasource_root=datasource_root,
			assembly_dir=assembly_dir,
			part_results=results,
			warnings=warnings,
		)

	if not parallel:
		for d in part_dirs:
			try:
				_wprint(state, f"[run_monoparts] part={d}")
				res = _run_one_part(d, part_keywords, part_limit)
				_wprint(state, f"[run_monoparts] metadata_in_prompt: {_format_metadata_files_in_prompt(res)}")
				results.append(res)
				warnings.extend(res.get("warnings") or [])
				try:
					stats = ((res or {}).get("analysis") or {}).get("stats") or {}
					prev = stats.get("prompt_preview")
					imgs = [x.get("pic_name") for x in (((res or {}).get("analysis") or {}).get("selected") or [])]
					if prev:
						_wprint(state, f"[run_monoparts] prompt_id={stats.get('prompt_id')} | images={imgs}")
						_wprint(state, "[run_monoparts] prompt_preview:\n" + str(prev))
				except Exception:
					pass
			except Exception as e:
				warnings.append(f"Monopart failed for '{d}': {e}")
		return _carry(
			state,
			datasource_root=datasource_root,
			assembly_dir=assembly_dir,
			part_results=results,
			warnings=warnings,
		)

	# Parallel mode
	max_workers = max(1, min(max_workers, len(part_dirs)))
	with ThreadPoolExecutor(max_workers=max_workers) as ex:
		futs = {
			ex.submit(_run_one_part, d, part_keywords, part_limit): d
			for d in part_dirs
		}
		for fut in as_completed(futs):
			d = futs[fut]
			try:
				res = fut.result()
				_wprint(state, f"[run_monoparts] part={d}")
				_wprint(state, f"[run_monoparts] metadata_in_prompt: {_format_metadata_files_in_prompt(res)}")
				results.append(res)
				warnings.extend(res.get("warnings") or [])
			except Exception as e:
				warnings.append(f"Monopart failed for '{d}': {e}")

	# Keep stable order in output
	results.sort(key=lambda r: str(r.get("searchdir", "")).lower())
	return _carry(
		state,
		datasource_root=datasource_root,
		assembly_dir=assembly_dir,
		part_results=results,
		warnings=warnings,
	)


def _node_merge_bom(state: Dict[str, Any]) -> Dict[str, Any]:
	"""Merge enriched part JSONs into single BOM file (Phase 4.3: instance-aware)."""
	# Check if enabled (default: true)
	if not state.get("enable_merge_bom", True):
		_wprint(state, "[merge_bom] SKIPPED (enable_merge_bom=False)")
		return state
	
	_wprint(state, "[merge_bom] Starting BOM merge (instance-aware)...")
	
	# Get experiment output directory
	exp_output_dir = _get_experiment_output_dir()
	if not exp_output_dir:
		_wprint(state, "[merge_bom] WARNING: No experiment output dir, skipping BOM merge")
		return _carry(state, merged_bom_path=None)
	
	exp_output_dir = Path(exp_output_dir)
	
	# PHASE 4.3: Prefer -enriched-merged.json (from merge_copy_part_data)
	# Fallback to -Metadata_enriched.json (if merge_copy_part_data was skipped)
	enriched_parts_dir = exp_output_dir / "enriched_parts"
	part_jsons = []
	
	if enriched_parts_dir.exists():
		# First try: _Data_enriched_merged.json (instance-aware)
		part_jsons = list(enriched_parts_dir.glob("*_Data_enriched_merged.json"))
		
		# Fallback: _Data_enriched.json (legacy)
		if not part_jsons:
			part_jsons = list(enriched_parts_dir.glob("*_Data_enriched.json"))
	
	# Legacy fallback: root directory
	if not part_jsons:
		part_jsons = list(exp_output_dir.glob("*_Data_enriched.json"))
	
	if not part_jsons:
		_wprint(state, "[merge_bom] WARNING: No enriched part JSONs found")
		_wprint(state, f"[merge_bom]   Searched in: {exp_output_dir}")
		_wprint(state, f"[merge_bom]   And in: {enriched_parts_dir}")
		return _carry(state, merged_bom_path=None)
	
	# Determine which source we're using
	using_merged = any("_Data_enriched_merged.json" in str(p) for p in part_jsons)
	source_type = "instance_aware_enrichment" if using_merged else "monopart_enrichment"
	
	# Load and concatenate all part metadata
	merged_parts = []
	for part_json in sorted(part_jsons):
		try:
			with open(part_json, 'r', encoding='utf-8') as f:
				part_data = json.load(f)
				merged_parts.append(part_data)
		except Exception as e:
			_wprint(state, f"[merge_bom] WARNING: Failed to load {part_json.name}: {e}")
	
	# Create merged BOM structure (Phase 4.3: instance-aware format)
	merged_bom = {
		"schema_version": 2,  # Bumped for instance-aware format
		"timestamp": datetime.now(timezone.utc).isoformat(),
		"datasource_root": state.get("datasource_root"),
		"parts": merged_parts,
		"total_parts": len(merged_parts),
		"source": source_type,
		"instance_aware": using_merged  # NEW: Indicates if parts are instance-specific
	}
	
	# Write {assembly}_BOM_enriched.json with assembly name prefix
	assembly_name = state.get("assembly_name", "unknown_assembly")
	output_path = exp_output_dir / f"{assembly_name}_BOM_enriched.json"
	try:
		with open(output_path, 'w', encoding='utf-8') as f:
			json.dump(merged_bom, f, indent=2, ensure_ascii=False)
		_wprint(state, f"[merge_bom] Merged {len(merged_parts)} parts → {output_path.name} ({source_type})")
	except Exception as e:
		_wprint(state, f"[merge_bom] ERROR: Failed to write {output_path.name}: {e}")
		return _carry(state, merged_bom_path=None)
	
	return _carry(state, merged_bom_path=str(output_path))


def _node_merge_copy_part_data(state: Dict[str, Any]) -> Dict[str, Any]:
	"""Merge enriched parts with instance-specific Stepparser metadata (Phase 4.2)."""
	# Check if enabled (default: true)
	if not state.get("enable_merge_copy_part_data", True):
		_wprint(state, "[merge_copy_part_data] SKIPPED (enable_merge_copy_part_data=False)")
		return state
	
	_wprint(state, "[merge_copy_part_data] Starting instance-aware enrichment merge...")
	
	# Get experiment output directory
	exp_output_dir = _get_experiment_output_dir()
	if not exp_output_dir:
		_wprint(state, "[merge_copy_part_data] WARNING: No experiment output dir (APA_EXPERIMENT_OUTPUT_DIR not set), skipping")
		return state
	
	exp_output_dir = Path(exp_output_dir)
	_wprint(state, f"[merge_copy_part_data] exp_output_dir={exp_output_dir}")
	_wprint(state, f"[merge_copy_part_data] enriched_parts dir={exp_output_dir / 'enriched_parts'}")
	
	# Get assembly name from state
	assembly_name = state.get("assembly_name")
	if not assembly_name:
		_wprint(state, "[merge_copy_part_data] WARNING: No assembly_name in state, skipping")
		return state
	
	_wprint(state, f"[merge_copy_part_data] assembly_name={assembly_name}")
	
	# Get stepparser root (default: data/processed/stepparser)
	workspace_root = Path(__file__).resolve().parents[1]
	stepparser_root = workspace_root / "data" / "processed" / "stepparser"
	_wprint(state, f"[merge_copy_part_data] stepparser_root={stepparser_root}")
	_wprint(state, f"[merge_copy_part_data] stepparser assembly dir={stepparser_root / assembly_name}")
	
	# Call merge function
	try:
		_wprint(state, f"[merge_copy_part_data] Calling merge_copy_part_data()...")
		result = merge_copy_part_data(
			assembly_name=assembly_name,
			experiment_output_dir=exp_output_dir,
			stepparser_root=stepparser_root
		)
		_wprint(state, f"[merge_copy_part_data] Result: status={result.get('status')}, merged_count={result.get('merged_count')}")
		
		if result["status"] == "success":
			_wprint(state, f"[merge_copy_part_data] ✓ Merged {result['merged_count']} parts → {result['output_dir']}")
			if result.get("errors"):
				_wprint(state, f"[merge_copy_part_data] ⚠️  {len(result['errors'])} errors occurred:")
				for error in result["errors"][:5]:  # Show first 5 errors
					_wprint(state, f"  - {error}")
		else:
			error_msg = result.get('error', 'Unknown error')
			_wprint(state, f"[merge_copy_part_data] ✗ ERROR: {error_msg}")
			return state
		
	except Exception as e:
		_wprint(state, f"[merge_copy_part_data] ✗ EXCEPTION: {e}")
		import traceback
		_wprint(state, traceback.format_exc())
		return state
	
	return _carry(state, merge_copy_part_data_result=result)


def _node_generate_assembly_sequence(state: Dict[str, Any]) -> Dict[str, Any]:
	"""Generate assembly sequence with LLM-based per-step generation."""
	# Check if enabled (default: true)
	enable_generation = state.get("enable_assembly_sequence", True)
	if not enable_generation:
		_wprint(state, "[generate_assembly_sequence] SKIPPED (enable_assembly_sequence=False)")
		return state
	
	_wprint(state, "[generate_assembly_sequence] Starting assembly sequence generation...")
	
	# Import the generation function
	from agent.Assembly_sequence_generation import generate_assembly_sequence
	
	# Get required state variables
	assembly_name = state.get("assembly_name")
	
	if not assembly_name:
		_wprint(state, "[generate_assembly_sequence] ERROR: No assembly_name in state")
		return _carry(state, assembly_sequence_path=None)
	
	# Setup paths
	workspace_root = Path(__file__).resolve().parents[1]
	stepparser_output = workspace_root / "data" / "processed" / "stepparser" / assembly_name
	# New convention: assembly_{name} folders
	# Legacy: {name}.STEP folders
	assembly_dir = stepparser_output / f"assembly_{assembly_name}"
	if not assembly_dir.exists():
		assembly_dir = stepparser_output / f"{assembly_name}.STEP"
	
	# Use experiment output dir from environment variable (set in run_experiments.py)
	exp_output_dir_env = _get_experiment_output_dir()
	if not exp_output_dir_env:
		_wprint(state, "[generate_assembly_sequence] ERROR: No experiment output dir from environment")
		return _carry(state, assembly_sequence_path=None)
	exp_output_dir_root = Path(exp_output_dir_env)
	
	if not assembly_dir.exists():
		_wprint(state, f"[generate_assembly_sequence] ERROR: Assembly dir not found: {assembly_dir}")
		return _carry(state, assembly_sequence_path=None)
	
	if not exp_output_dir_root.exists():
		_wprint(state, f"[generate_assembly_sequence] ERROR: Exp output dir not found: {exp_output_dir_root}")
		return _carry(state, assembly_sequence_path=None)
	
	# Load settings for generation
	settings = load_experiment_settings()
	generation_settings = {
		"ASG_image_keywords": settings.get("ASG_image_keywords"),
		"ASG_json_keywords": settings.get("ASG_json_keywords"),
	}
	max_iterations = int(settings.get("ASV_max_iterations", 3))

	# Determine current iteration (run_1, run_2, ...)
	previous_runs = int(state.get("sequence_run_counter", 0))
	current_run = previous_runs + 1
	run_folder_name = f"assembly_sequence_run{current_run}"
	current_run_dir = exp_output_dir_root / run_folder_name
	current_run_dir.mkdir(parents=True, exist_ok=True)

	_wprint(state, f"[generate_assembly_sequence] Iteration: run_{current_run} (max {max_iterations})")

	# Load remarks from previous iteration if available
	remarks_context = None
	if previous_runs >= 1:
		prev_run_dir = exp_output_dir_root / f"assembly_sequence_run{previous_runs}"
		remarks_path = prev_run_dir / "remarks.json"
		if remarks_path.exists():
			try:
				remarks_context = remarks_path.read_text(encoding="utf-8")
				_wprint(state, f"[generate_assembly_sequence] Loaded previous remarks from {remarks_path.name}")
			except Exception as err:
				_wprint(state, f"[generate_assembly_sequence] WARNING: Could not read remarks.json: {err}")
	
	_wprint(state, f"[generate_assembly_sequence] Assembly: {assembly_name}")
	_wprint(state, f"[generate_assembly_sequence] Assembly Dir: {assembly_dir}")
	_wprint(state, f"[generate_assembly_sequence] Output Dir: {current_run_dir}")
	_wprint(state, f"[generate_assembly_sequence] Settings: {generation_settings}")
	
	try:
		# Run generation
		result = generate_assembly_sequence(
			assembly_name=assembly_name,
			assembly_dir=assembly_dir,
			exp_output_dir=current_run_dir,
			json_dir=exp_output_dir_root,
			image_keywords=generation_settings["ASG_image_keywords"],
			json_keywords=generation_settings["ASG_json_keywords"],
			remarks_context=remarks_context,
		)
		
		if "error" in result:
			_wprint(state, f"[generate_assembly_sequence] ERROR: {result.get('error')}")
			return _carry(state, assembly_sequence_path=None)
		
		# Get output path
		sequence_path = result.get("assembly_sequence_path")
		sequence_data = result.get("sequence_data", {})
		num_steps = len(sequence_data.get("steps", []))
		
		_wprint(state, f"[generate_assembly_sequence] COMPLETE")
		_wprint(state, f"[generate_assembly_sequence]   Steps generated: {num_steps}")
		_wprint(state, f"[generate_assembly_sequence]   Output: {Path(sequence_path).name}")
		
		return _carry(
			state,
			assembly_sequence_path=sequence_path,
			assembly_sequence_data=sequence_data,
			sequence_run_counter=current_run,
			current_sequence_run_dir=str(current_run_dir),
			previous_remarks_context=remarks_context,
			sequence_max_iterations=max_iterations,
			sequence_needs_regeneration=False,
			sequence_iterations_exhausted=False,
		)
		
	except Exception as e:
		_wprint(state, f"[generate_assembly_sequence] EXCEPTION: {e}")
		import traceback
		traceback.print_exc()
		return _carry(state, assembly_sequence_path=None)


def _node_render_assembly_steps(state: Dict[str, Any]) -> Dict[str, Any]:
	"""Render assembly steps for validation.
	
	Generates incremental visualizations of assembly steps.
	Creates sequence_renderings/ folder with step images.
	"""
	# Check if assembly sequence generation was run
	if not state.get("assembly_sequence_path"):
		_wprint(state, "[render_assembly_steps] SKIPPED (no assembly sequence generated)")
		return state
	
	# Check if validation is enabled (only render if validation will run)
	enable_validation = state.get("enable_sequence_validation", True)
	if not enable_validation:
		_wprint(state, "[render_assembly_steps] SKIPPED (enable_sequence_validation=False)")
		return state

	current_run = state.get("sequence_run_counter")
	last_rendered_run = state.get("last_rendered_run_counter")
	if current_run is not None and last_rendered_run == current_run:
		_wprint(state, "[render_assembly_steps] SKIPPED (already rendered for this iteration)")
		return state
	
	_wprint(state, "[render_assembly_steps] Starting assembly step rendering...")
	
	# Import the rendering function
	try:
		from agent.Assembly_sequence_validation import render_assembly_steps
	except ImportError:
		try:
			from Assembly_sequence_validation import render_assembly_steps
		except ImportError:
			_wprint(state, "[render_assembly_steps] ERROR: Could not import render_assembly_steps")
			return state
	
	# Get required state variables
	assembly_name = state.get("assembly_name")
	
	if not assembly_name:
		_wprint(state, "[render_assembly_steps] ERROR: No assembly_name in state")
		return state
	
	# Get experiment output dir
	exp_output_dir_env = _get_experiment_output_dir()
	if not exp_output_dir_env:
		_wprint(state, "[render_assembly_steps] ERROR: No experiment output dir from environment")
		return state

	# Prefer current iteration directory if available
	run_dir_override = state.get("current_sequence_run_dir")
	if run_dir_override:
		exp_output_dir_path = Path(run_dir_override)
	else:
		exp_output_dir_path = Path(exp_output_dir_env)
	
	_wprint(state, f"[render_assembly_steps] Assembly: {assembly_name}")
	_wprint(state, f"[render_assembly_steps] Output Dir: {exp_output_dir_path}")
	
	try:
		# Run rendering
		result = render_assembly_steps(
			assembly_name=assembly_name,
			experiment_name=state.get("experiment_name", "direct_run"),
			exp_output_dir=exp_output_dir_path
		)
		
		if result.get("status") == "error":
			_wprint(state, f"[render_assembly_steps] ERROR: {result.get('message')}")
			return state
		
		num_renderings = result.get("renderings_count", 0)
		_wprint(state, f"[render_assembly_steps] COMPLETE")
		_wprint(state, f"[render_assembly_steps]   Renderings created: {num_renderings}")
		
		return _carry(
			state,
			assembly_renderings_path=result.get("output_dir"),
			last_rendered_run_counter=current_run,
		)
		
	except Exception as e:
		_wprint(state, f"[render_assembly_steps] EXCEPTION: {e}")
		import traceback
		traceback.print_exc()
		return state


def _node_validate_assembly_sequence(state: Dict[str, Any]) -> Dict[str, Any]:
	"""Validate assembly sequence with LLM-based per-step validation."""
	# Check if enabled (default: true)
	enable_validation = state.get("enable_sequence_validation", True)
	if not enable_validation:
		_wprint(state, "[validate_assembly_sequence] SKIPPED (enable_sequence_validation=False)")
		return state
	
	_wprint(state, "[validate_assembly_sequence] Starting assembly sequence validation...")
	
	# Import the validation function
	from agent.Assembly_sequence_validation import validate_assembly_sequence
	
	# Get required state variables
	assembly_name = state.get("assembly_name")
	
	if not assembly_name:
		_wprint(state, "[validate_assembly_sequence] ERROR: No assembly_name in state")
		return _carry(state, assembly_sequence_validation_path=None)
	
	# Load settings for validation (all defaults should come from settings.yaml)
	settings = load_experiment_settings()
	validation_settings = {
		"ASV_json_keywords": settings.get("ASV_json_keywords"),
		"ASV_step_img_keywords": settings.get("ASV_step_img_keywords"),
		"ASV_finished_assy_keywords": settings.get("ASV_finished_assy_keywords"),
	}
	
	_wprint(state, f"[validate_assembly_sequence] Assembly: {assembly_name}")
	_wprint(state, f"[validate_assembly_sequence] Settings: {validation_settings}")
	
	try:
		# Get experiment output dir from environment variable (set in run_experiments.py)
		exp_output_dir_env = _get_experiment_output_dir()
		if not exp_output_dir_env:
			_wprint(state, "[validate_assembly_sequence] ERROR: No experiment output dir from environment")
			return _carry(state, assembly_sequence_validation_path=None)
		
		# Prefer current iteration directory if available
		run_dir_override = state.get("current_sequence_run_dir")
		if run_dir_override:
			exp_output_dir_path = Path(run_dir_override)
		else:
			exp_output_dir_path = Path(exp_output_dir_env)
		
		exp_output_dir_path.mkdir(parents=True, exist_ok=True)
		
		# Run validation - pass explicit exp_output_dir
		result = validate_assembly_sequence(
			assembly_name=assembly_name,
			experiment_name=state.get("experiment_name", "direct_run"),
			settings=validation_settings,
			exp_output_dir=exp_output_dir_path
		)
		
		if result.get("status") == "error":
			_wprint(state, f"[validate_assembly_sequence] ERROR: {result.get('message')}")
			return _carry(state, assembly_sequence_validation_path=None)
		
		# Extract summary
		overall_valid = result.get("overall_valid", False)
		overall_confidence = result.get("overall_confidence", 0.0)
		overall_risk = result.get("overall_risk_level", "UNKNOWN")
		validated_steps = result.get("validation_summary", {}).get("validated_steps", 0)
		total_steps = result.get("validation_summary", {}).get("total_steps", 0)
		all_parts_processed = result.get("all_parts_processed", False)
		current_run = int(state.get("sequence_run_counter") or 0)
		max_iterations = int(state.get("sequence_max_iterations") or settings.get("ASV_max_iterations", 3))
		needs_regeneration = not (overall_valid and all_parts_processed)
		iterations_exhausted = needs_regeneration and current_run >= max_iterations
		
		_wprint(state, f"[validate_assembly_sequence] COMPLETE")
		_wprint(state, f"[validate_assembly_sequence]   Steps: {validated_steps}/{total_steps} validated")
		_wprint(state, f"[validate_assembly_sequence]   Overall Valid: {overall_valid}")
		_wprint(state, f"[validate_assembly_sequence]   Overall Confidence: {overall_confidence:.1f}%")
		_wprint(state, f"[validate_assembly_sequence]   Overall Risk: {overall_risk}")
		
		# Persist remarks.json for feedback loop
		remarks_payload = {
			"overall_valid": overall_valid,
			"all_parts_processed": all_parts_processed,
			"missing_parts": result.get("missing_parts", []),
			"summary": result.get("validation_summary", {}),
			"steps": [],
		}
		for step_validation in result.get("step_validations", []):
			remarks_payload["steps"].append({
				"step_number": step_validation.get("step_number"),
				"is_valid": step_validation.get("is_valid"),
				"remarks": step_validation.get("remarks"),
				"geometric_issues": step_validation.get("geometric_issues", []),
				"suggested_improvements": step_validation.get("suggested_improvements", []),
				"risk_level": step_validation.get("risk_level"),
			})
		remarks_path = exp_output_dir_path / "remarks.json"
		try:
			with open(remarks_path, "w", encoding="utf-8") as remarks_file:
				json.dump(remarks_payload, remarks_file, indent=2, ensure_ascii=False)
			_wprint(state, f"[validate_assembly_sequence]   Saved remarks.json")
		except Exception as err:
			_wprint(state, f"[validate_assembly_sequence] WARNING: Failed to write remarks.json: {err}")
			remarks_path = None
		
		# Prepare carry-over state
		validation_output_dir = exp_output_dir_path / "assembly_sequence_validation"
		validation_path = str(validation_output_dir)
		
		return _carry(
			state,
			assembly_sequence_validation_path=validation_path,
			assembly_sequence_validation_result=result,
			last_validation_overall_valid=overall_valid,
			last_validation_all_parts_processed=all_parts_processed,
			last_validation_missing_parts=result.get("missing_parts", []),
			latest_remarks_path=str(remarks_path) if remarks_path else None,
			sequence_needs_regeneration=needs_regeneration,
			sequence_iterations_exhausted=iterations_exhausted,
			sequence_max_iterations=max_iterations,
			last_validated_run_counter=current_run,
		)
		
	except Exception as e:
		_wprint(state, f"[validate_assembly_sequence] EXCEPTION: {e}")
		import traceback
		traceback.print_exc()
		return _carry(state, assembly_sequence_validation_path=None)
		
	except Exception as e:
		_wprint(state, f"[validate_assembly_sequence] EXCEPTION: {e}")
		import traceback
		traceback.print_exc()
		return _carry(state, assembly_sequence_validation_path=None)


def _node_assess_ffa(state: Dict[str, Any]) -> Dict[str, Any]:
	"""Assess assembly sequence steps for Fitness for Automation (FFA) criteria."""
	# Load settings
	settings = load_experiment_settings()
	ffa_mode = settings.get("FFA_mode", "disabled")
	
	# Check if FFA is enabled
	if ffa_mode == "disabled":
		_wprint(state, "[assess_ffa] SKIPPED (FFA_mode=disabled)")
		return state
	
	_wprint(state, "[assess_ffa] Starting FFA assessment...")
	
	# Import the assessment function
	from agent.FFA_assessment import assess_assembly_sequence_ffa
	
	# Get required state variables
	assembly_name = state.get("assembly_name")
	
	if not assembly_name:
		_wprint(state, "[assess_ffa] ERROR: No assembly_name in state")
		return _carry(state, ffa_assessment_path=None)
	
	# Get experiment output dir
	exp_output_dir_env = _get_experiment_output_dir()
	if not exp_output_dir_env:
		_wprint(state, "[assess_ffa] ERROR: No experiment output dir from environment")
		return _carry(state, ffa_assessment_path=None)
	
	# Use current iteration directory if available
	run_dir_override = state.get("current_sequence_run_dir")
	if run_dir_override:
		exp_output_dir_path = Path(run_dir_override)
	else:
		exp_output_dir_path = Path(exp_output_dir_env)
	
	exp_output_dir_path.mkdir(parents=True, exist_ok=True)
	
	# Find required paths
	sequence_json_path = exp_output_dir_path / "assembly_sequence.json"
	enriched_dir = exp_output_dir_path / "enriched_parts"
	rendered_steps_dir = exp_output_dir_path / "sequence_renderings"
	output_dir = exp_output_dir_path / "ffa_assessment"
	
	# Find BOM file (has assembly name prefix)
	bom_files = list(exp_output_dir_path.glob("*_BOM_enriched.json"))
	if not bom_files:
		_wprint(state, f"[assess_ffa] ERROR: No BOM_enriched.json found in {exp_output_dir_path}")
		return _carry(state, ffa_assessment_path=None)
	
	bom_json_path = bom_files[0]
	
	# Check if validation_only mode and output already exists
	if ffa_mode == "validate_only":
		ffa_output = output_dir / "ffa_assessment.json"
		if ffa_output.exists():
			_wprint(state, "[assess_ffa] SKIPPED (validate_only mode and output exists)")
			return _carry(state, ffa_assessment_path=str(output_dir))
	
	# Verify inputs exist
	if not sequence_json_path.exists():
		_wprint(state, f"[assess_ffa] ERROR: assembly_sequence.json not found: {sequence_json_path}")
		return _carry(state, ffa_assessment_path=None)
	
	if not rendered_steps_dir.exists():
		_wprint(state, f"[assess_ffa] ERROR: sequence_renderings not found: {rendered_steps_dir}")
		return _carry(state, ffa_assessment_path=None)
	
	# Load FFA settings
	ffa_settings = {
		"prompt_id": settings.get("FFA_prompt_id", "ffa_assessment_full_v1"),
		"base_metadata_keys": settings.get("FFA_base_part_json_keys", ["part_id", "part_name_guess"]),
		"joining_metadata_keys": settings.get("FFA_joining_part_json_keys", ["part_id", "part_name_guess"]),
		"image_downscale": settings.get("FFA_image_downscale", 0.7),
		"step_img_keywords": settings.get("FFA_step_img_keywords", ["isometric"]),
		"prior_step_img_keywords": settings.get("FFA_prior_step_img_keywords", ["isometric"]),
	}
	
	_wprint(state, f"[assess_ffa] Assembly: {assembly_name}")
	_wprint(state, f"[assess_ffa] BOM: {bom_json_path.name}")
	_wprint(state, f"[assess_ffa] Settings: {ffa_settings}")
	
	try:
		# Run FFA assessment
		result = assess_assembly_sequence_ffa(
			sequence_json_path=sequence_json_path,
			enriched_dir=enriched_dir,
			rendered_steps_dir=rendered_steps_dir,
			output_dir=output_dir,
			prompt_id=ffa_settings["prompt_id"],
			base_metadata_keys=ffa_settings["base_metadata_keys"],
			joining_metadata_keys=ffa_settings["joining_metadata_keys"],
			image_downscale=ffa_settings["image_downscale"],
			step_img_keywords=ffa_settings["step_img_keywords"],
			prior_step_img_keywords=ffa_settings["prior_step_img_keywords"],
			bom_json_path=bom_json_path,
		)
		
		if result.get("status") == "error":
			_wprint(state, f"[assess_ffa] ERROR: {result.get('error')}")
			return _carry(state, ffa_assessment_path=None)
		
		# Extract summary
		total_steps = result.get("total_steps", 0)
		assessed_steps = result.get("assessed_steps", 0)
		
		_wprint(state, f"[assess_ffa] COMPLETE")
		_wprint(state, f"[assess_ffa]   Steps: {assessed_steps}/{total_steps} assessed")
		_wprint(state, f"[assess_ffa]   Output: {output_dir}")
		
		return _carry(
			state,
			ffa_assessment_path=str(output_dir),
			ffa_assessment_result=result,
		)
		
	except Exception as e:
		_wprint(state, f"[assess_ffa] EXCEPTION: {e}")
		import traceback
		traceback.print_exc()
		return _carry(state, ffa_assessment_path=None)


def build_workflow():
	graph = StateGraph(dict)
	graph.add_node("resolve_paths", _node_resolve_paths)
	graph.add_node("run_assembly", _node_run_assembly)
	graph.add_node("list_parts", _node_list_parts)
	graph.add_node("run_monoparts", _node_run_monoparts)
	graph.add_node("merge_bom", _node_merge_bom)
	graph.add_node("merge_copy_part_data", _node_merge_copy_part_data)
	graph.add_node("generate_assembly_sequence", _node_generate_assembly_sequence)
	graph.add_node("render_assembly_steps", _node_render_assembly_steps)
	graph.add_node("validate_assembly_sequence", _node_validate_assembly_sequence)
	graph.add_node("assess_ffa", _node_assess_ffa)

	graph.set_entry_point("resolve_paths")
	graph.add_edge("resolve_paths", "run_assembly")
	graph.add_edge("run_assembly", "list_parts")
	graph.add_edge("list_parts", "run_monoparts")
	graph.add_edge("run_monoparts", "merge_copy_part_data")
	graph.add_edge("merge_copy_part_data", "merge_bom")
	graph.add_edge("merge_bom", "generate_assembly_sequence")
	graph.add_edge("generate_assembly_sequence", "render_assembly_steps")
	graph.add_edge("render_assembly_steps", "validate_assembly_sequence")
	graph.add_conditional_edges(
		"validate_assembly_sequence",
		_sequence_validation_condition,
		{
			"retry": "generate_assembly_sequence",
			"exhausted": "assess_ffa",
			"complete": "assess_ffa",
		},
	)
	graph.add_edge("assess_ffa", END)

	return graph.compile(checkpointer=InMemorySaver())


def run_enrichment(
	datasource_root: str,
	*,
	use_unique_parts: bool = True,
	workflow_print: Optional[bool] = None,
	parallel: bool = False,
	max_workers: int = 4,
	assembly_keywords: Optional[List[str]] = None,
	assembly_limit: int = 8,
	overwrite_assembly_metadata: bool = True,
	part_keywords: Optional[List[str]] = None,
	part_limit: int = 8,
) -> Dict[str, Any]:
	start_t = time.perf_counter()
	app = build_workflow()
	run_id = str(uuid.uuid4())
	config = {"configurable": {"thread_id": run_id}}
	settings = load_experiment_settings()
	if workflow_print is None:
		workflow_print = bool(settings.get("workflow_print", False))

	# Print run header + experiment overrides
	if workflow_print:
		workspace_root = Path(__file__).resolve().parents[1]
		exp_sel = os.environ.get("APA_EXPERIMENT_YAML")
		if exp_sel and str(exp_sel).strip():
			exp_path = Path(str(exp_sel))
			if not exp_path.is_absolute():
				exp_path = (workspace_root / exp_path).resolve()
			else:
				exp_path = exp_path.resolve()
		else:
			exp_path = (workspace_root / "experiment.yaml").resolve()

		exp_overrides: Dict[str, Any] = {}
		try:
			if exp_path.exists() and exp_path.is_file():
				loaded = yaml.safe_load(exp_path.read_text(encoding="utf-8", errors="replace"))
				if isinstance(loaded, dict):
					exp_overrides = loaded
		except Exception:
			exp_overrides = {}

		print("[run] datasource_root=", str(datasource_root))
		print(
			"[run] params:",
			{
				"use_unique_parts": bool(use_unique_parts),
				"parallel": bool(parallel),
				"max_workers": int(max_workers),
				"assembly_limit": int(assembly_limit),
				"part_limit": int(part_limit),
			},
		)
		print("[run] experiment_yaml=", str(exp_path))
		print("[run] experiment_overrides:\n" + (yaml.safe_dump(exp_overrides, sort_keys=True) if exp_overrides else "(none)"))

		important_keys = [
			"img_to_analyse_assy",
			"img_to_analyse_monopart",
			"max_images_per_call",
			"downscaling_factor",
			"img_describer_tokens_per_img",
			"prompt_id_assy",
			"prompt_id_monopart",
			"include_examples_assy",
			"include_examples_monopart",
			"AAI_use_assembly_metadata",
			"AMI_use_monopart_metadata",
			"AMI_use_assembly_metadata",
			"workflow_print_prompt_preview_chars",
		]
		effective_subset = {k: settings.get(k) for k in important_keys if k in settings}
		print("[run] effective_settings_subset:\n" + yaml.safe_dump(effective_subset, sort_keys=True))
	try:
		preview_chars = int(settings.get("workflow_print_prompt_preview_chars") or 800)
	except Exception:
		preview_chars = 800
	
	# Extract assembly_name from datasource_root for sequence generation/validation
	assembly_name = Path(datasource_root).name
	experiment_name = os.environ.get("APA_EXPERIMENT_NAME", "direct_run")
	
	state: Dict[str, Any] = {
		"run_id": run_id,
		"datasource_root": str(datasource_root),
		"assembly_name": assembly_name,                    # ⭐ NEW: For sequence generation/validation
		"experiment_name": experiment_name,                # ⭐ NEW: For sequence generation/validation
		"use_unique_parts": bool(use_unique_parts),
		"workflow_print": bool(workflow_print),
		"workflow_print_prompt_preview_chars": int(preview_chars),
		"parallel": bool(parallel),
		"max_workers": int(max_workers),
		"assembly_keywords": assembly_keywords,
		"assembly_limit": int(assembly_limit),
		"overwrite_assembly_metadata": bool(overwrite_assembly_metadata),
		"part_keywords": part_keywords,
		"part_limit": int(part_limit),
	}
	result = app.invoke(state, config=config)
	runtime_seconds = float(time.perf_counter() - start_t)

	assembly_res_for_sum = (result.get("assembly_result") if isinstance(result, dict) else None)
	parts_res_for_sum = ((result.get("part_results") or []) if isinstance(result, dict) else [])
	total_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
	for tr in [assembly_res_for_sum, *parts_res_for_sum]:
		u = _token_usage_from_tool_result(tr)
		total_usage["input_tokens"] += u["input_tokens"]
		total_usage["output_tokens"] += u["output_tokens"]
		total_usage["total_tokens"] += u["total_tokens"]

	if isinstance(result, dict):
		result["runtime_seconds"] = runtime_seconds
		result["token_usage_total"] = total_usage

	if workflow_print:
		print(
			"[run_summary] runtime_seconds="
			+ f"{runtime_seconds:.3f}"
			+ " | token_usage_total="
			+ json.dumps(total_usage)
		)

	# Persist run manifest for traceability (always enabled)
	try:
		include_prompt_text = bool(settings.get("workflow_save_run_manifest_include_prompt_text", False))
		include_rendered_prompts = bool(settings.get("workflow_save_run_manifest_include_rendered_prompts", False))
		include_step_details = bool(settings.get("workflow_save_run_manifest_include_step_details", True))
		exp_overrides_dump = exp_overrides
		effective_settings = settings
		
		# Use experiment output dir if set, otherwise fallback to stepparser directory
		exp_output_dir = _get_experiment_output_dir()
		if exp_output_dir:
			manifest_dir = exp_output_dir
		else:
			layout = resolve_stepparser_layout_vars(str(datasource_root))
			assembly_dir = str(layout.get("assembly_dir") or "").strip()
			manifest_dir = Path(assembly_dir) if assembly_dir else Path(str(datasource_root))
		manifest_dir.mkdir(parents=True, exist_ok=True)

		prompt_ids = {
			"prompt_id_system": str(effective_settings.get("prompt_id_system") or "").strip(),
			"prompt_id_user_bootstrap": str(effective_settings.get("prompt_id_user_bootstrap") or "").strip(),
			"prompt_id_assy": str(effective_settings.get("prompt_id_assy") or "").strip(),
			"prompt_id_monopart": str(effective_settings.get("prompt_id_monopart") or "").strip(),
		}

		prompt_templates: Dict[str, object] = {}
		for k, pid in prompt_ids.items():
			txt = get_prompt_template(pid) if pid else None
			prompt_templates[k] = {
				"id": pid or None,
				"text": txt if (include_prompt_text and isinstance(txt, str)) else None,
				"sha256": _sha256_text(txt) if isinstance(txt, str) else None,
			}

		# These two are rendered prompts (with datasource_root + layout variables)
		rendered_system = get_system_prompt(str(datasource_root))
		rendered_user_bootstrap = get_user_bootstrap_prompt(str(datasource_root))
		prompt_templates["rendered_system_prompt"] = {
			"text": rendered_system if include_rendered_prompts else None,
			"sha256": _sha256_text(rendered_system) if isinstance(rendered_system, str) else None,
		}
		prompt_templates["rendered_user_bootstrap_prompt"] = {
			"text": rendered_user_bootstrap if include_rendered_prompts else None,
			"sha256": _sha256_text(rendered_user_bootstrap) if isinstance(rendered_user_bootstrap, str) else None,
		}

		assembly_res = (result.get("assembly_result") if isinstance(result, dict) else None)
		part_res_list = ((result.get("part_results") or []) if isinstance(result, dict) else [])
		
		# ⭐ NEW: Assembly Sequence Results
		asm_seq_path = result.get("assembly_sequence_path") if isinstance(result, dict) else None
		asm_seq_val_path = result.get("assembly_sequence_validation_path") if isinstance(result, dict) else None

		important_keys = [
			"img_to_analyse_assy",
			"img_to_analyse_monopart",
			"max_images_per_call",
			"downscaling_factor",
			"img_describer_tokens_per_img",
			"prompt_id_system",
			"prompt_id_user_bootstrap",
			"prompt_id_assy",
			"prompt_id_monopart",
			"include_examples_assy",
			"include_examples_monopart",
			"AAI_use_assembly_metadata",
			"AMI_use_monopart_metadata",
			"AMI_use_assembly_metadata",
			"enable_assembly_sequence",
			"ASG_image_keywords",
			"ASG_json_keywords",
			"enable_sequence_validation",
			"ASV_step_img_keywords",
			"ASV_json_keywords",
			"ASV_finished_assy_keywords",
		]
		effective_subset = {k: effective_settings.get(k) for k in important_keys if k in effective_settings}

		manifest: Dict[str, object] = {
			"schema_version": 2,
			"run_id": run_id,
			"timestamp": datetime.now(timezone.utc).isoformat(),
			"runtime_seconds": runtime_seconds,
			"token_usage_total": total_usage,
			"datasource_root_name": Path(str(datasource_root)).name,
			"workflow_params": {
				"use_unique_parts": bool(use_unique_parts),
				"parallel": bool(parallel),
				"max_workers": int(max_workers),
				"assembly_limit": int(assembly_limit),
				"part_limit": int(part_limit),
			},
			"experiment": {
				"experiment_yaml": (Path(str(exp_path)).name if 'exp_path' in locals() else None),
				"overrides": exp_overrides_dump,
				"effective_settings_subset": effective_subset,
			},
			"prompts": prompt_templates,
			"outputs": {
				"assembly": _extract_step_details(assembly_res, include_step_details=bool(include_step_details)),
				"parts": [_extract_step_details(r, include_step_details=bool(include_step_details)) for r in part_res_list],
				# ⭐ NEW: Assembly Sequence Pipeline Outputs
				"assembly_sequence": {
					"path": asm_seq_path,
					"enabled": bool(effective_settings.get("enable_assembly_sequence", True)),
				},
				"assembly_sequence_validation": {
					"path": asm_seq_val_path,
					"enabled": bool(effective_settings.get("enable_sequence_validation", False)),
				},
			},
		}

		# Use experiment_details.json if in experiment mode, otherwise enrichment_run_{run_id}.json
		if _get_experiment_output_dir():
			manifest_path = manifest_dir / "experiment_details.json"
		else:
			manifest_path = manifest_dir / f"enrichment_run_{run_id}.json"
		
		# Always save manifest
		manifest_dir.mkdir(parents=True, exist_ok=True)
		tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
		tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
		tmp.replace(manifest_path)
		if isinstance(result, dict):
			result["run_manifest_path"] = str(manifest_path)
		if workflow_print:
			print(f"[run_summary] manifest saved: {manifest_path}")
	except Exception as e:
		if isinstance(result, dict):
			result.setdefault("warnings", [])
			try:
				result["warnings"].append(f"Could not write run manifest: {e}")
			except Exception:
				pass

	return result


if __name__ == "__main__":
	# Example usage:
	# datasource_root contains: IPA_Cranfield.STEP, Part_1, Part_2, ...
	root = os.environ.get(
		"APA_DATASOURCE_ROOT",
		r"C:\Users\KAB-MS\VSCode\apa_from_cad\data\processed\stepparser\IPA_Cranfield",
	)
	
	# Set experiment output directory if not already set
	if not os.environ.get("APA_EXPERIMENT_OUTPUT_DIR"):
		# Create experiment output folder: data/experiments/direct_run/{assembly_name}/
		workspace_root = Path(__file__).resolve().parents[1]
		assembly_name = Path(root).name
		exp_output = workspace_root / "data" / "experiments" / "direct_run" / assembly_name
		os.environ["APA_EXPERIMENT_OUTPUT_DIR"] = str(exp_output)
		print(f"[INFO] Experiment output directory: {exp_output}")
	
	res = run_enrichment(root, use_unique_parts=True, parallel=False, max_workers=4)
	print("assembly_written:", (res.get("assembly_result") or {}).get("metadata_written_path"))
	print("parts:", len(res.get("part_results") or []))
