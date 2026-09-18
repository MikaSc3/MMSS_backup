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
	from agent.checkpoint_utils import create_checkpoint
	from agent.merge_enriched import merge_copy_part_data
except ImportError:  # pragma: no cover
	from tools import analyse_assembly_img, analyse_monopart_img, _get_experiment_output_dir
	from checkpoint_utils import create_checkpoint
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
	if state.get("_tool_context_block"):
		payload["additional_context_block"] = str(state.get("_tool_context_block"))

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


def _run_one_part(
	part_dir: str,
	part_keywords: Optional[List[str]],
	part_limit: Optional[int],
	additional_context_block: Optional[str] = None,
) -> Dict[str, Any]:
	payload: Dict[str, Any] = {"searchdir": part_dir}
	if part_keywords:
		payload["keywords"] = list(part_keywords)
	if part_limit is not None:
		payload["limit"] = int(part_limit)
	if additional_context_block:
		payload["additional_context_block"] = additional_context_block
	return analyse_monopart_img.invoke(payload)


def _node_run_monoparts(state: Dict[str, Any]) -> Dict[str, Any]:
	datasource_root = state.get("datasource_root")
	assembly_dir = state.get("assembly_dir")
	part_dirs: List[str] = list(state.get("part_dirs") or [])
	parallel = bool(state.get("parallel", False))
	max_workers = int(state.get("max_workers") or 4)
	part_keywords = list(state.get("part_keywords") or []) or None
	part_limit = int(state.get("part_limit") or 8)
	additional_context_block = str(state.get("_tool_context_block")) if state.get("_tool_context_block") else None

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
				res = _run_one_part(d, part_keywords, part_limit, additional_context_block)
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
			ex.submit(_run_one_part, d, part_keywords, part_limit, additional_context_block): d
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
	# Force debug if environment variable set
	force_debug = bool(os.environ.get("APA_DEBUG_MERGE_COPY_PART_DATA"))
	debug_state = dict(state)
	if force_debug:
		debug_state["workflow_print"] = True
	
	# Check if enabled (default: true)
	if not state.get("enable_merge_copy_part_data", True):
		_wprint(debug_state, "[merge_copy_part_data] SKIPPED (enable_merge_copy_part_data=False)")
		return state
	
	_wprint(debug_state, "[merge_copy_part_data] Starting instance-aware enrichment merge...")
	
	# Get experiment output directory
	exp_output_dir = _get_experiment_output_dir()
	if not exp_output_dir:
		_wprint(debug_state, "[merge_copy_part_data] WARNING: No experiment output dir (APA_EXPERIMENT_OUTPUT_DIR not set), skipping")
		return state
	
	exp_output_dir = Path(exp_output_dir)
	_wprint(debug_state, f"[merge_copy_part_data] exp_output_dir={exp_output_dir}")
	_wprint(debug_state, f"[merge_copy_part_data] enriched_parts dir={exp_output_dir / 'enriched_parts'}")
	
	# Get assembly name from state
	assembly_name = state.get("assembly_name")
	if not assembly_name:
		_wprint(debug_state, "[merge_copy_part_data] WARNING: No assembly_name in state, skipping")
		return state
	
	_wprint(debug_state, f"[merge_copy_part_data] assembly_name={assembly_name}")
	
	# Get stepparser root (default: data/processed/stepparser)
	workspace_root = Path(__file__).resolve().parents[1]
	stepparser_root = workspace_root / "data" / "processed" / "stepparser"
	_wprint(debug_state, f"[merge_copy_part_data] stepparser_root={stepparser_root}")
	_wprint(debug_state, f"[merge_copy_part_data] stepparser assembly dir={stepparser_root / assembly_name}")
	
	# Call merge function
	try:
		_wprint(debug_state, f"[merge_copy_part_data] Calling merge_copy_part_data()...")
		result = merge_copy_part_data(
			assembly_name=assembly_name,
			experiment_output_dir=exp_output_dir,
			stepparser_root=stepparser_root
		)
		_wprint(debug_state, f"[merge_copy_part_data] Result: status={result.get('status')}, merged_count={result.get('merged_count')}")
		
		if result["status"] == "success":
			_wprint(debug_state, f"[merge_copy_part_data] ✓ Merged {result['merged_count']} parts → {result['output_dir']}")
			if result.get("errors"):
				_wprint(debug_state, f"[merge_copy_part_data] ⚠️  {len(result['errors'])} errors occurred:")
				for error in result["errors"][:5]:  # Show first 5 errors
					_wprint(debug_state, f"  - {error}")
		else:
			error_msg = result.get('error', 'Unknown error')
			_wprint(debug_state, f"[merge_copy_part_data] ✗ ERROR: {error_msg}")
			return state
		
	except Exception as e:
		_wprint(debug_state, f"[merge_copy_part_data] ✗ EXCEPTION: {e}")
		import traceback
		_wprint(debug_state, traceback.format_exc())
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
		# For session-based workflows, disable loading from input/textbased_data
		result = generate_assembly_sequence(
			assembly_name=assembly_name,
			assembly_dir=assembly_dir,
			exp_output_dir=current_run_dir,
			json_dir=exp_output_dir_root,
			image_keywords=generation_settings["ASG_image_keywords"],
			json_keywords=generation_settings["ASG_json_keywords"],
			remarks_context=remarks_context,
			use_manual_order=state.get("asg_use_manual_order", True),
			include_gt_sequence=state.get("asg_include_gt_sequence", True),
			additional_context_block=str(state.get("_tool_context_block")) if state.get("_tool_context_block") else None,
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


def _node_generate_assembly_sequence_v2_agent_feedback(state: Dict[str, Any]) -> Dict[str, Any]:
	"""Generate assembly sequence with Agent 2 feedback remarks priority.
	
	Version 2 differs from v1 in remarks loading:
	- First checks session_root/remarks_{assembly_name}.txt (Agent 2 feedback)
	- Falls back to input/textbased_data/ for backward compatibility
	
	This enables Agent 2's revision remarks to actually regenerate sequences.
	"""
	# Check if enabled (default: true)
	enable_generation = state.get("enable_assembly_sequence", True)
	if not enable_generation:
		_wprint(state, "[generate_assembly_sequence_v2] SKIPPED (enable_assembly_sequence=False)")
		return state
	
	_wprint(state, "[generate_assembly_sequence_v2] Starting assembly sequence generation (with Agent 2 feedback)...")
	
	# Import the generation function
	from agent.Assembly_sequence_generation import generate_assembly_sequence
	
	# Get required state variables
	assembly_name = state.get("assembly_name")
	
	if not assembly_name:
		_wprint(state, "[generate_assembly_sequence_v2] ERROR: No assembly_name in state")
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
		_wprint(state, "[generate_assembly_sequence_v2] ERROR: No experiment output dir from environment")
		return _carry(state, assembly_sequence_path=None)
	exp_output_dir_root = Path(exp_output_dir_env)
	
	if not assembly_dir.exists():
		_wprint(state, f"[generate_assembly_sequence_v2] ERROR: Assembly dir not found: {assembly_dir}")
		return _carry(state, assembly_sequence_path=None)
	
	if not exp_output_dir_root.exists():
		_wprint(state, f"[generate_assembly_sequence_v2] ERROR: Exp output dir not found: {exp_output_dir_root}")
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

	_wprint(state, f"[generate_assembly_sequence_v2] Iteration: run_{current_run} (max {max_iterations})")

	# Load remarks from session root (Agent 2 feedback) - NEW IN V2
	remarks_context = None
	session_root = state.get("session_root")
	if session_root:
		session_root = Path(session_root)
		agent2_remarks_path = session_root / f"remarks_{assembly_name}.txt"
		if agent2_remarks_path.exists():
			try:
				remarks_context = agent2_remarks_path.read_text(encoding="utf-8")
				_wprint(state, f"[generate_assembly_sequence_v2] ✓ Loaded Agent 2 remarks from {agent2_remarks_path.name}")
			except Exception as err:
				_wprint(state, f"[generate_assembly_sequence_v2] WARNING: Could not read Agent 2 remarks: {err}")
	
	# Fallback: Load from previous iteration if available (for backward compatibility)
	if remarks_context is None and previous_runs >= 1:
		prev_run_dir = exp_output_dir_root / f"assembly_sequence_run{previous_runs}"
		remarks_path = prev_run_dir / "remarks.json"
		if remarks_path.exists():
			try:
				remarks_context = remarks_path.read_text(encoding="utf-8")
				_wprint(state, f"[generate_assembly_sequence_v2] Loaded previous remarks from {remarks_path.name}")
			except Exception as err:
				_wprint(state, f"[generate_assembly_sequence_v2] WARNING: Could not read remarks.json: {err}")
	
	_wprint(state, f"[generate_assembly_sequence_v2] Assembly: {assembly_name}")
	_wprint(state, f"[generate_assembly_sequence_v2] Assembly Dir: {assembly_dir}")
	_wprint(state, f"[generate_assembly_sequence_v2] Output Dir: {current_run_dir}")
	_wprint(state, f"[generate_assembly_sequence_v2] Settings: {generation_settings}")
	if remarks_context:
		_wprint(state, f"[generate_assembly_sequence_v2] Using remarks context ({len(remarks_context)} chars)")
	
	try:
		# Run generation
		# For session-based workflows, disable loading from input/textbased_data (use only Agent 2 remarks)
		result = generate_assembly_sequence(
			assembly_name=assembly_name,
			assembly_dir=assembly_dir,
			exp_output_dir=current_run_dir,
			json_dir=exp_output_dir_root,
			image_keywords=generation_settings["ASG_image_keywords"],
			json_keywords=generation_settings["ASG_json_keywords"],
			remarks_context=remarks_context,
			use_manual_order=False,
			include_gt_sequence=False,
			additional_context_block=str(state.get("_tool_context_block")) if state.get("_tool_context_block") else None,
		)
		
		if "error" in result:
			_wprint(state, f"[generate_assembly_sequence_v2] ERROR: {result.get('error')}")
			return _carry(state, assembly_sequence_path=None)
		
		# Get output path
		sequence_path = result.get("assembly_sequence_path")
		sequence_data = result.get("sequence_data", {})
		num_steps = len(sequence_data.get("steps", []))
		
		_wprint(state, f"[generate_assembly_sequence_v2] COMPLETE")
		_wprint(state, f"[generate_assembly_sequence_v2]   Steps generated: {num_steps}")
		_wprint(state, f"[generate_assembly_sequence_v2]   Output: {Path(sequence_path).name}")
		
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
		_wprint(state, f"[generate_assembly_sequence_v2] EXCEPTION: {e}")
		import traceback
		traceback.print_exc()
		return _carry(state, assembly_sequence_path=None)


def _node_generate_assembly_sequence_from_gt(state: Dict[str, Any]) -> Dict[str, Any]:
	"""Generate assembly sequence step descriptions from ground-truth step structure.

	The step order (step_id, belongs_to, base_part, joining_part) is fixed by the
	GT sequence loaded from data/ground_truth/assembly_sequence_ground_truth/.
	The LLM only writes step_description and joining_process for each step.
	Python then merges both to produce a full assembly_sequence.json.
	"""
	from agent.Assembly_sequence_generation import generate_assembly_sequence_from_gt

	assembly_name = state.get("assembly_name")
	if not assembly_name:
		_wprint(state, "[generate_assembly_sequence_from_gt] ERROR: No assembly_name in state")
		return _carry(state, assembly_sequence_path=None)

	workspace_root = Path(__file__).resolve().parents[1]
	stepparser_output = workspace_root / "data" / "processed" / "stepparser" / assembly_name
	assembly_dir = stepparser_output / f"assembly_{assembly_name}"
	if not assembly_dir.exists():
		assembly_dir = stepparser_output / f"{assembly_name}.STEP"

	exp_output_dir_env = _get_experiment_output_dir()
	if not exp_output_dir_env:
		_wprint(state, "[generate_assembly_sequence_from_gt] ERROR: No experiment output dir")
		return _carry(state, assembly_sequence_path=None)
	exp_output_dir_root = Path(exp_output_dir_env)

	if not assembly_dir.exists():
		_wprint(state, f"[generate_assembly_sequence_from_gt] ERROR: Assembly dir not found: {assembly_dir}")
		return _carry(state, assembly_sequence_path=None)

	settings = load_experiment_settings()
	state_overrides = state.get("experiment_settings_overrides")
	if state_overrides:
		settings.update(state_overrides)

	# One run dir (no iteration needed – GT defines structure)
	run_folder_name = "assembly_sequence_run1"
	current_run_dir = exp_output_dir_root / run_folder_name
	current_run_dir.mkdir(parents=True, exist_ok=True)

	_wprint(state, f"[generate_assembly_sequence_from_gt] Assembly: {assembly_name}")
	_wprint(state, f"[generate_assembly_sequence_from_gt] Output: {current_run_dir}")

	try:
		result = generate_assembly_sequence_from_gt(
			assembly_name=assembly_name,
			assembly_dir=assembly_dir,
			exp_output_dir=current_run_dir,
			json_dir=exp_output_dir_root,
			additional_context_block=str(state.get("_tool_context_block")) if state.get("_tool_context_block") else None,
		)

		if "error" in result:
			_wprint(state, f"[generate_assembly_sequence_from_gt] ERROR: {result['error']}")
			return _carry(state, assembly_sequence_path=None)

		sequence_path = result.get("assembly_sequence_path")
		sequence_data = result.get("sequence_data", {})
		num_steps = len(sequence_data.get("steps", []))

		_wprint(state, f"[generate_assembly_sequence_from_gt] COMPLETE – {num_steps} steps")

		return _carry(
			state,
			assembly_sequence_path=sequence_path,
			assembly_sequence_data=sequence_data,
			sequence_run_counter=1,
			current_sequence_run_dir=str(current_run_dir),
			sequence_max_iterations=1,
			sequence_needs_regeneration=False,
			sequence_iterations_exhausted=False,
		)

	except Exception as e:
		_wprint(state, f"[generate_assembly_sequence_from_gt] EXCEPTION: {e}")
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
	
	# Check if step rendering is enabled via its own flag (default: True).
	# enable_step_rendering is independent of enable_sequence_validation so that
	# section views are always generated when needed (e.g. for Interaction Analysis
	# in the GT workflow where no ASV loop runs).
	enable_rendering = state.get("enable_step_rendering", True)
	if not enable_rendering:
		_wprint(state, "[render_assembly_steps] SKIPPED (enable_step_rendering=False)")
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
	
	# Load transparency settings
	settings = load_experiment_settings()
	transparency_values = settings.get("ASV_transparency_values", [0.0])
	headless_mode = settings.get("rendering_headless_mode", False)
	_wprint(state, f"[render_assembly_steps] Transparency values: {transparency_values}")
	_wprint(state, f"[render_assembly_steps] Headless mode: {headless_mode}")
	
	try:
		# Run rendering
		result = render_assembly_steps(
			assembly_name=assembly_name,
			experiment_name=state.get("experiment_name", "direct_run"),
			exp_output_dir=exp_output_dir_path,
			transparency_values=transparency_values,
			headless_mode=headless_mode
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


def _node_load_gt_renderings(state: Dict[str, Any]) -> Dict[str, Any]:
	"""Load pre-existing renderings from the ground-truth folder instead of rendering.

	This node is a drop-in replacement for _node_render_assembly_steps in the
	``sequence_gt_prerendered`` workflow variant.  Instead of invoking the OCC
	renderer it copies

	    data/ground_truth/assembly_sequence_ground_truth/{assembly_name}/renderings/

	into the experiment output directory as ``sequence_renderings/``, so that
	downstream nodes (interaction_analysis, assess_ffa) find images exactly where
	they expect them.
	"""
	assembly_name = state.get("assembly_name")
	if not assembly_name:
		_wprint(state, "[load_gt_renderings] ERROR: No assembly_name in state")
		return state

	if not state.get("assembly_sequence_path"):
		_wprint(state, "[load_gt_renderings] SKIPPED (no assembly_sequence_path in state)")
		return state

	workspace_root = Path(__file__).resolve().parents[1]
	gt_renderings = (
		workspace_root
		/ "data" / "ground_truth" / "assembly_sequence_ground_truth"
		/ assembly_name / "renderings"
	)

	if not gt_renderings.exists():
		_wprint(state, f"[load_gt_renderings] ERROR: GT renderings not found: {gt_renderings}")
		_wprint(state, "[load_gt_renderings] Run the renderer once first, or check the assembly name.")
		return state

	# Target: same location that _node_render_assembly_steps would produce
	run_dir_override = state.get("current_sequence_run_dir")
	if run_dir_override:
		run_dir_path = Path(run_dir_override)
	else:
		exp_output_dir_env = _get_experiment_output_dir()
		if not exp_output_dir_env:
			_wprint(state, "[load_gt_renderings] ERROR: No experiment output dir in environment")
			return state
		run_dir_path = Path(exp_output_dir_env) / "assembly_sequence_run1"

	run_dir_path.mkdir(parents=True, exist_ok=True)
	dest_renderings = run_dir_path / "sequence_renderings"

	import shutil
	if dest_renderings.exists():
		shutil.rmtree(dest_renderings)
	shutil.copytree(gt_renderings, dest_renderings)

	file_count = len(list(dest_renderings.glob("*")))
	_wprint(state, f"[load_gt_renderings] Copied {file_count} files from GT renderings")
	_wprint(state, f"[load_gt_renderings]   Source: {gt_renderings}")
	_wprint(state, f"[load_gt_renderings]   Dest  : {dest_renderings}")

	return _carry(
		state,
		assembly_renderings_path=str(run_dir_path),
		last_rendered_run_counter=state.get("sequence_run_counter"),
	)


def _node_interaction_analysis(state: Dict[str, Any]) -> Dict[str, Any]:
	"""Analyze geometric interactions between assembly parts.
	
	Per-step analysis of contact surfaces, alignment challenges, collision risks.
	Runs after render_assembly_steps, before validate_assembly_sequence.
	"""
	# Ensure output is visible
	import sys
	sys.stdout.flush()
	
	# Skip if assembly sequence not available
	if not state.get("assembly_sequence_path"):
		_wprint(state, "[interaction_analysis] SKIPPED (no assembly sequence)")
		sys.stdout.flush()
		return state
	
	# Check if node is enabled in settings
	settings = load_experiment_settings()
	ia_mode = settings.get("IA_mode", "disabled")
	_wprint(state, f"[interaction_analysis] IA_mode={ia_mode}")
	sys.stdout.flush()
	
	if ia_mode == "disabled":
		_wprint(state, "[interaction_analysis] SKIPPED (IA_mode=disabled)")
		sys.stdout.flush()
		return state
	
	_wprint(state, "[interaction_analysis] Starting geometric interaction analysis...")
	sys.stdout.flush()
	
	# Import interaction analysis function
	try:
		from agent.Interaction_analysis import analyze_assembly_sequence_interactions
	except ImportError:
		try:
			from Interaction_analysis import analyze_assembly_sequence_interactions
		except ImportError:
			_wprint(state, "[interaction_analysis] ERROR: Could not import analyze_assembly_sequence_interactions")
			return state
	
	# Get required state variables
	assembly_name = state.get("assembly_name")
	if not assembly_name:
		_wprint(state, "[interaction_analysis] ERROR: No assembly_name in state")
		return state
	
	exp_output_dir_env = _get_experiment_output_dir()
	if not exp_output_dir_env:
		_wprint(state, "[interaction_analysis] ERROR: No experiment output dir")
		return state
	
	run_dir_override = state.get("current_sequence_run_dir")
	if run_dir_override:
		run_dir_path = Path(run_dir_override)
	else:
		# Renderings are saved without assembly_name subfolder (set by generate_assembly_sequence node)
		run_dir_path = Path(exp_output_dir_env) / "assembly_sequence_run1"
	
	_wprint(state, f"[interaction_analysis] Assembly: {assembly_name}")
	_wprint(state, f"[interaction_analysis] Run Directory: {run_dir_path}")
	
	# Get configuration
	system_prompt_id = settings.get("IA_system_prompt_id", "interaction_analyst_system_v1")
	human_prompt_id = settings.get("IA_human_prompt_id", "interaction_analysis_task_v1")
	base_keys = settings.get("IA_base_part_json_keys", ["part_id", "part_name_guess"])
	joining_keys = settings.get("IA_joining_part_json_keys", ["part_id", "part_name_guess", "material_word"])
	step_img_kw = settings.get("IA_sequence_step_img_keywords", ["iso1_transp_0_3"])
	monopart_kw = settings.get("IA_monopart_img_keywords", ["iso1_transp_0_0"])
	include_monopart = settings.get("IA_include_monopart_renderings", True)
	image_scale = settings.get("image_downscale_factor", 1.0)
	ia_parallel = bool(settings.get("IA_parallel", False))
	ia_max_workers = int(settings.get("IA_max_workers", 4))
	
	try:
		# Paths
		sequence_file = run_dir_path / "assembly_sequence.json"
		rendered_steps_dir = run_dir_path / "sequence_renderings"
		stepparser_dir = Path(f"data/processed/stepparser/{assembly_name}")
		# BOM file is written flat in exp_output_dir_env (not nested under assembly_name subfolder)
		bom_file = Path(exp_output_dir_env) / f"{assembly_name}_BOM_enriched.json"
		
		_wprint(state, f"[interaction_analysis]   Sequence: {sequence_file.name}")
		_wprint(state, f"[interaction_analysis]   Renderings: {rendered_steps_dir.name}/")
		
		# Run interaction analysis
		result = analyze_assembly_sequence_interactions(
			sequence_json_path=sequence_file,
			rendered_steps_dir=rendered_steps_dir,
			stepparser_dir=stepparser_dir,
			output_dir=run_dir_path,
			bom_json_path=bom_file if bom_file.exists() else None,
			system_prompt_id=system_prompt_id,
			human_prompt_id=human_prompt_id,
			base_metadata_keys=base_keys,
			joining_metadata_keys=joining_keys,
			sequence_step_img_keywords=step_img_kw,
			monopart_img_keywords=monopart_kw,
			include_monopart_renderings=include_monopart,
			image_downscale=image_scale,
			parallel=ia_parallel,
			max_workers=ia_max_workers,
			additional_context_block=str(state.get("_tool_context_block")) if state.get("_tool_context_block") else None,
		)
		
		if result.get("status") != "success":
			_wprint(state, f"[interaction_analysis] ERROR: {result.get('error', 'Unknown error')}")
			return state
		
		_wprint(state, f"[interaction_analysis] COMPLETE")
		_wprint(state, f"[interaction_analysis]   Output: {Path(result.get('output_file', '')).name}")
		
		# Load the analysis data for potential use by FFA node
		if result.get("output_data"):
			return _carry(
				state,
				interaction_analysis_path=result.get("output_file"),
				interaction_analysis_data=result.get("output_data"),
			)
		
		return state
		
	except Exception as e:
		_wprint(state, f"[interaction_analysis] EXCEPTION: {e}")
		import traceback
		traceback.print_exc()
		return state


def _node_validate_assembly_sequence(state: Dict[str, Any]) -> Dict[str, Any]:
	"""Validate assembly sequence with LLM-based per-step validation."""
	# Load settings
	settings = load_experiment_settings()
	asv_mode = settings.get("ASV_mode", "disabled")
	
	# Check if ASV is enabled
	if asv_mode == "disabled":
		_wprint(state, "[validate_assembly_sequence] SKIPPED (ASV_mode=disabled)")
		return _carry(state, assembly_sequence_validation_path=None)
	
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
	
	# Check if validate_only mode and output already exists
	if asv_mode == "validate_only":
		exp_output_dir_env = _get_experiment_output_dir()
		if exp_output_dir_env:
			exp_output_path = Path(exp_output_dir_env)
			validation_output = exp_output_path / "assembly_sequence_validation" / "assembly_sequence_validation_merged.json"
			if validation_output.exists():
				_wprint(state, "[validate_assembly_sequence] SKIPPED (validate_only mode and output exists)")
				return _carry(state, assembly_sequence_validation_path=str(validation_output.parent))
	
	# NEW: Extract ASV settings with global image_downscale_factor
	validation_settings = {
		"ASV_json_keywords": settings.get("ASV_json_keywords", ["merged_bom"]),
		"ASV_parts_json_keys": settings.get("ASV_parts_json_keys", ["part_id", "part_name_guess"]),
		"ASV_step_img_keywords": settings.get("ASV_step_img_keywords", ["iso1_transp_0_3"]),
		"ASV_prior_step_img_keywords": settings.get("ASV_prior_step_img_keywords", ["iso1_transp_0_3"]),
		"ASV_finished_assy_keywords": settings.get("ASV_finished_assy_keywords", ["iso1_transp_0_3"]),
		"image_downscale_factor": settings.get("image_downscale_factor", 0.5),  # Global setting
		"ASV_system_prompt_id": settings.get("ASV_system_prompt_id"),
		"ASV_human_prompt_id": settings.get("ASV_human_prompt_id"),
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
	# Ensure output is visible
	import sys
	sys.stdout.flush()
	
	# Load settings – start from YAML defaults, then apply merged overrides passed via state
	settings = load_experiment_settings()
	state_overrides = state.get("experiment_settings_overrides")
	if state_overrides:
		settings.update(state_overrides)
	ffa_mode = settings.get("FFA_mode", "disabled")
	
	_wprint(state, f"[assess_ffa] FFA_mode={ffa_mode}")
	sys.stdout.flush()
	
	# Check if FFA is enabled
	if ffa_mode == "disabled":
		_wprint(state, "[assess_ffa] SKIPPED (FFA_mode=disabled)")
		sys.stdout.flush()
		return _carry(state, ffa_assessment_path=None)
	
	_wprint(state, "[assess_ffa] Starting FFA assessment...")
	sys.stdout.flush()
	
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
	
	# BOM is always in the main experiment folder
	exp_output_root = Path(exp_output_dir_env)
	
	# Sequence/Renderings might be in iteration subfolder (run_dir_override)
	run_dir_override = state.get("current_sequence_run_dir")
	if run_dir_override:
		sequence_dir = Path(run_dir_override)
		_wprint(state, f"[assess_ffa] Using iteration directory: {sequence_dir.name}")
	else:
		sequence_dir = exp_output_root
	
	sequence_dir.mkdir(parents=True, exist_ok=True)
	
	# Find required paths - Sequence/Renderings from iteration folder
	sequence_json_path = sequence_dir / "assembly_sequence.json"
	rendered_steps_dir = sequence_dir / "sequence_renderings"
	
	# BOM and enriched_parts from main experiment folder
	enriched_dir = exp_output_root / "enriched_parts"
	output_dir = exp_output_root / "ffa_assessment"  # Save FFA in main assembly folder, not in iteration subfolder
	
	# Find BOM file - always in experiment root
	_wprint(state, f"[assess_ffa] Searching for BOM in: {exp_output_root}")
	bom_files = list(exp_output_root.glob("*_BOM_enriched.json"))
	if not bom_files:
		# Fallback: try BOM_enriched.json without assembly prefix
		bom_files = list(exp_output_root.glob("BOM_enriched.json"))
	
	_wprint(state, f"[assess_ffa] Found BOM files: {[f.name for f in bom_files]}")
	
	if not bom_files:
		_wprint(state, f"[assess_ffa] ERROR: No BOM_enriched.json found in {exp_output_root}")
		_wprint(state, f"[assess_ffa] Directory contents: {list(exp_output_root.glob('*'))[:10]}")
		return _carry(state, ffa_assessment_path=None)
	
	bom_json_path = bom_files[0]
	_wprint(state, f"[assess_ffa] Using BOM: {bom_json_path.name}")
	
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
		"prompt_id": settings.get("FFA_human_prompt_id", "ffa_assessment_task_v1"),
		"base_metadata_keys": settings.get("FFA_base_part_json_keys", ["part_id", "part_name_guess"]),
		"joining_metadata_keys": settings.get("FFA_joining_part_json_keys", ["part_id", "part_name_guess"]),
		"image_downscale": settings.get("image_downscale_factor", 0.5),  # Use global setting (fallback to FFA_image_downscale for backward compatibility)
		"step_img_keywords": settings.get("FFA_step_img_keywords", ["iso1_transp_0_0"]),
		"prior_step_img_keywords": settings.get("FFA_prior_step_img_keywords", ["iso1_transp_0_0"]),
		"parallel": bool(settings.get("FFA_parallel", False)),
		"max_workers": int(settings.get("FFA_max_workers", 4)),
	}
	
	_wprint(state, f"[assess_ffa] Assembly: {assembly_name}")
	_wprint(state, f"[assess_ffa] BOM: {bom_json_path.name}")
	_wprint(state, f"[assess_ffa] Settings: {ffa_settings}")
	
	try:
		# Run FFA assessment
		# Check if interaction analysis should be included
		interaction_data = None
		include_interaction = settings.get("FFA_include_interaction_analysis", False)
		_wprint(state, f"[assess_ffa] FFA_include_interaction_analysis = {include_interaction}")
		if include_interaction:
			# Prefer data already in state (set by IA node in full workflow)
			interaction_data = state.get("interaction_analysis_data")
			if interaction_data:
				_wprint(state, f"[assess_ffa] Including interaction analysis context (from state)")
			else:
				# Fallback: load from checkpoint path (set by run_assess_ffa_only)
				ia_ckpt_path = state.get("interaction_analysis_checkpoint_path")
				if ia_ckpt_path:
					try:
						with open(ia_ckpt_path, "r", encoding="utf-8") as f:
							interaction_data = json.load(f)
						_wprint(state, f"[assess_ffa] Including interaction analysis context (loaded from {Path(ia_ckpt_path).name})")
					except Exception as e:
						_wprint(state, f"[assess_ffa] Failed to load IA from path: {e}")
				else:
					_wprint(state, f"[assess_ffa] Flag enabled but no interaction analysis data or path in state")
		
		# Check if step information should be included in LLM prompt
		include_step_info = settings.get("FFA_include_step_info", True)
		_wprint(state, f"[assess_ffa] FFA_include_step_info = {include_step_info}")
		
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
			interaction_analysis_data=interaction_data,
			include_step_info=include_step_info,
			parallel=ffa_settings["parallel"],
			max_workers=ffa_settings["max_workers"],
			settings=settings,
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


def _append_validation_marker(text: Any) -> str:
	"""Append validation marker while preserving source wording."""
	value = str(text or "").strip()
	if not value:
		return "[]"
	if value.endswith("[]") or value.endswith("[x]"):
		return value
	return f"{value} []"


def _build_exact_ffa_report_steps(ffa_assessment: Dict[str, Any]) -> List[Dict[str, Any]]:
	"""Build saved report steps directly from ffa_assessment.overall_ffa."""
	field_by_subprocess = {
		"separation": ("separation_potential", "separation_risks"),
		"handling": ("handling_potential", "handling_risks"),
		"positioning": ("positioning_potential", "positioning_risks"),
		"joining": ("joining_potential", "joining_risks"),
	}
	empty_fields = {
		field: []
		for fields in field_by_subprocess.values()
		for field in fields
	}
	report_steps: List[Dict[str, Any]] = []

	for source_step in ffa_assessment.get("step_assessments", []):
		if not isinstance(source_step, dict):
			continue

		report_step: Dict[str, Any] = {
			"step_id": source_step.get("step_id"),
			"step_description": [_append_validation_marker(source_step.get("step_description"))],
			**{key: list(value) for key, value in empty_fields.items()},
		}

		overall_ffa = (source_step.get("assessment") or {}).get("overall_ffa") or []
		for item in overall_ffa:
			if not isinstance(item, dict):
				continue
			subprocess = str(item.get("subprocess", "")).strip().lower()
			fields = field_by_subprocess.get(subprocess)
			if not fields:
				continue
			potential_field, risks_field = fields
			report_step[potential_field] = [_append_validation_marker(item.get("automation_potential"))]
			report_step[risks_field] = [_append_validation_marker(item.get("risks"))]

		report_steps.append(report_step)

	return sorted(report_steps, key=lambda step: step.get("step_id") or 0)


def _finalize_ffa_report_data(report_data: Dict[str, Any], ffa_assessment: Dict[str, Any]) -> Dict[str, Any]:
	"""Add deterministic step summaries while preserving the saved report shape."""
	steps = _build_exact_ffa_report_steps(ffa_assessment)
	final_report: Dict[str, Any] = {}
	for key, value in report_data.items():
		final_report[key] = value
		if key == "total_steps":
			final_report["steps"] = steps
	if "steps" not in final_report:
		final_report["steps"] = steps
	return final_report


def _compact_ffa_assessment_for_reporter(ffa_assessment: Dict[str, Any]) -> Dict[str, Any]:
	"""Keep only reporter-relevant assessment fields to reduce prompt tokens."""
	compact_steps: List[Dict[str, Any]] = []
	for step in ffa_assessment.get("step_assessments", []):
		if not isinstance(step, dict):
			continue
		assessment = step.get("assessment") or {}
		compact_steps.append({
			"step_id": step.get("step_id"),
			"step_description": step.get("step_description"),
			"base_part_id": step.get("base_part_id"),
			"joining_part_id": step.get("joining_part_id"),
			"joining_process": step.get("joining_process"),
			"overall_ffa": assessment.get("overall_ffa") or [],
			"design_drawbacks_base_part": assessment.get("design_drawbacks_base_part") or [],
			"design_drawbacks_joining_parts": assessment.get("design_drawbacks_joining_parts") or [],
			"design_drawbacks_assembly": assessment.get("design_drawbacks_assembly") or [],
		})

	return {
		"assembly_name": ffa_assessment.get("assembly_name"),
		"total_steps": ffa_assessment.get("total_steps"),
		"assessed_steps": ffa_assessment.get("assessed_steps"),
		"step_assessments": compact_steps,
	}


def _node_ffa_reporter(state: Dict[str, Any]) -> Dict[str, Any]:
	"""Summarize FFA Assessment into Step/Assembly/Part-level structured report."""
	import sys
	sys.stdout.flush()
	
	_wprint(state, "[ffa_reporter] Starting FFA Report generation...")
	sys.stdout.flush()
	
	# Load settings
	settings = load_experiment_settings()
	state_overrides = state.get("experiment_settings_overrides")
	if state_overrides:
		settings.update(state_overrides)
	
	# Get FFA assessment path from state
	ffa_assessment_dir = state.get("ffa_assessment_path")
	if not ffa_assessment_dir:
		_wprint(state, "[ffa_reporter] SKIPPED: No FFA assessment path in state")
		return _carry(state, ffa_report_path=None)
	
	ffa_assessment_path = Path(ffa_assessment_dir) / "ffa_assessment.json"
	if not ffa_assessment_path.exists():
		_wprint(state, f"[ffa_reporter] ERROR: FFA assessment not found: {ffa_assessment_path}")
		return _carry(state, ffa_report_path=None)
	
	try:
		# Load FFA assessment
		with open(ffa_assessment_path, "r", encoding="utf-8") as f:
			ffa_assessment = json.load(f)
		
		assembly_name = ffa_assessment.get("assembly_name", state.get("assembly_name", "unknown"))
		total_steps = ffa_assessment.get("total_steps", 0)
		
		_wprint(state, f"[ffa_reporter] Assembly: {assembly_name}")
		_wprint(state, f"[ffa_reporter] Total steps: {total_steps}")
		
		# Load Assembly Overview Enriched JSON (one level up from ffa_assessment dir)
		script_dir = Path(ffa_assessment_dir).parent
		overview_files = list(script_dir.glob(f"assembly_{assembly_name}_Overview_Enriched.json"))
		
		assembly_overview = {}
		if overview_files:
			overview_path = overview_files[0]
			_wprint(state, f"[ffa_reporter] Loading assembly overview: {overview_path.name}")
			with open(overview_path, "r", encoding="utf-8") as f:
				assembly_overview = json.load(f)
		else:
			_wprint(state, f"[ffa_reporter] WARNING: Assembly overview not found, skipping overview data")
		
		# Load BOM enriched JSON
		bom_files = list(script_dir.glob(f"{assembly_name}_BOM_enriched.json"))
		bom_enriched = {"parts": []}
		if bom_files:
			bom_path = bom_files[0]
			_wprint(state, f"[ffa_reporter] Loading BOM enriched: {bom_path.name}")
			with open(bom_path, "r", encoding="utf-8") as f:
				bom_enriched = json.load(f)
		else:
			_wprint(state, f"[ffa_reporter] WARNING: BOM enriched not found, skipping BOM data")
		
		# Load prompts from prompt_store
		from agent.prompt_store import load_prompt_library
		prompt_library = load_prompt_library()
		
		system_prompt = prompt_library.get("ffa_reporter_workflow_system_prompt", "")
		human_template = prompt_library.get("ffa_reporter_workflow_human_message_template", "")
		
		if not system_prompt or not human_template:
			_wprint(state, "[ffa_reporter] ERROR: Prompts not found in prompt library")
			return _carry(state, ffa_report_path=None)
		
		# Extract assembly overview fields
		total_parts = assembly_overview.get("total_parts", "unknown")
		unique_parts = assembly_overview.get("unique_parts", "unknown")
		assembly_description = assembly_overview.get("assembly_description", "")
		assembly_name_guess = assembly_overview.get("assembly_name_guess", assembly_name)
		primary_function = assembly_overview.get("primary_function", "")
		
		_wprint(state, f"[ffa_reporter] Assembly overview: {unique_parts} unique parts (total {total_parts})")
		
		# Prepare human message
		human_message = human_template.format(
			assembly_name=assembly_name,
			total_steps=total_steps,
			total_parts=total_parts,
			unique_parts=unique_parts,
			assembly_description=assembly_description,
			assembly_name_guess=assembly_name_guess,
			primary_function=primary_function,
			ffa_assessment_json=json.dumps(_compact_ffa_assessment_for_reporter(ffa_assessment), indent=2).replace('{', '{{').replace('}', '}}'),
			bom_enriched_json=json.dumps(bom_enriched, indent=2).replace('{', '{{').replace('}', '}}')
		)
		
		# Call LLM to generate FFA report
		from langchain_openai import ChatOpenAI, AzureChatOpenAI
		from langchain_core.messages import SystemMessage, HumanMessage
		from agent.structured_output import FFAReportSynthesisOnly
		
		# Read LLM settings (default to 5.4 for FFA Reporter)
		llm_model = settings.get("FFA_reporter_model", settings.get("LLM_model", "5.4"))
		temperature = float(settings.get("LLM_temperature", 0))
		max_tokens = int(settings.get("FFA_reporter_max_tokens", settings.get("LLM_max_tokens", 16384)))
		
		_wprint(state, f"[ffa_reporter] Using model: {llm_model}")
		_wprint(state, f"[ffa_reporter] Max completion tokens: {max_tokens}")
		
		# Model Registry (matching tools.py pattern)
		_MODEL_REGISTRY = {
			"4o":  {"env_key": "AZURE_ENDPOINT_4O",  "deployment": "gpt-4o",  "api_key_env": "API_KEY_GPT_4", "api_version": "2024-12-01-preview", "use_v1_api": False},
			"4.1": {"env_key": "AZURE_ENDPOINT_41",  "deployment": "gpt-4.1", "api_key_env": "API_KEY_GPT_4", "api_version": "2024-12-01-preview", "use_v1_api": False},
			"5.4": {"env_key": "AZURE_ENDPOINT_54",  "deployment": "gpt-5.4", "api_key_env": "API_KEY_GPT_5", "api_version": "2025-04-01-preview", "use_v1_api": True,
		        "deployment_env": "AZURE_DEPLOYMENT_54"},
		}
		
		# Get model config
		cfg = _MODEL_REGISTRY.get(llm_model, _MODEL_REGISTRY.get("5.4"))
		
		# Load endpoint and API key from environment
		raw_endpoint = (
			os.getenv(cfg["env_key"])
			or os.getenv("AZURE_ENDPOINT_4O")
			or os.getenv("AZURE_ENDPOINT")
			or ""
		)
		api_key = (
			os.getenv(cfg.get("api_key_env", "API_KEY_GPT_4"))
			or os.getenv("API_KEY_GPT_4")
		)
		api_version = os.getenv("AZURE_API_VERSION") or cfg.get("api_version", "2024-12-01-preview")
		deployment_env_key = cfg.get("deployment_env")
		deployment = (
			(os.getenv(deployment_env_key) if deployment_env_key else None)
			or cfg["deployment"]
		)
		
		if not api_key:
			_wprint(state, f"[ffa_reporter] ERROR: No API key found (checked {cfg.get('api_key_env', 'API_KEY_GPT_4')} and API_KEY_GPT_4)")
			return _carry(state, ffa_report_path=None)
		
		if not raw_endpoint:
			_wprint(state, f"[ffa_reporter] ERROR: No endpoint found (checked {cfg['env_key']}, AZURE_ENDPOINT_4O, AZURE_ENDPOINT)")
			return _carry(state, ffa_report_path=None)
		
		# Create LLM instance
		if cfg.get("use_v1_api"):
			# GPT-5.x: Responses API via /openai/v1/
			import re as _re
			base = _re.match(r"(https?://[^/]+)", raw_endpoint)
			base_url = (base.group(1) if base else raw_endpoint.rstrip("/")) + "/openai/v1/"
			_wprint(state, f"[ffa_reporter] Creating ChatOpenAI (v1/Responses): model={llm_model}, deployment='{deployment}', base_url='{base_url}'")
			llm = ChatOpenAI(
				base_url=base_url,
				api_key=api_key,
				model=deployment,
				temperature=temperature,
				max_completion_tokens=max_tokens,
			)
		else:
			# GPT-4.x: Chat Completions via AzureChatOpenAI
			_wprint(state, f"[ffa_reporter] Creating AzureChatOpenAI: model={llm_model}, deployment='{deployment}', api_version='{api_version}'")
			llm = AzureChatOpenAI(
				azure_endpoint=raw_endpoint,
				api_key=api_key,
				api_version=api_version,
				azure_deployment=deployment,
				temperature=temperature,
				max_completion_tokens=max_tokens,
			)
		
		# Bind structured output
		llm_with_schema = llm.with_structured_output(FFAReportSynthesisOnly)
		
		# Generate report
		messages = [
			SystemMessage(content=system_prompt),
			HumanMessage(content=human_message),
		]
		
		response = llm_with_schema.invoke(messages)
		
		# Save report
		output_dir = Path(ffa_assessment_dir).parent / "ffa_report"
		output_dir.mkdir(parents=True, exist_ok=True)
		
		report_path = output_dir / f"{assembly_name}_ffa_report.json"
		with open(report_path, "w", encoding="utf-8") as f:
			# Convert Pydantic model to dict
			if hasattr(response, "model_dump"):
				report_data = response.model_dump()
			else:
				report_data = response
			report_data = _finalize_ffa_report_data(report_data, ffa_assessment)
			json.dump(report_data, f, indent=2, ensure_ascii=False)
		
		_wprint(state, f"[ffa_reporter] COMPLETE")
		_wprint(state, f"[ffa_reporter] Report saved: {report_path}")
		
		return _carry(
			state,
			ffa_report_path=str(output_dir),
			ffa_report_result=report_data if isinstance(report_data, dict) else report_data.model_dump(),
		)
		
	except Exception as e:
		_wprint(state, f"[ffa_reporter] EXCEPTION: {e}")
		import traceback
		traceback.print_exc()
		return _carry(state, ffa_report_path=None)


def _node_ffa_post_processing(state: Dict[str, Any]) -> Dict[str, Any]:
	"""Create metrics + plots + PDF package after ffa_reporter."""
	_wprint(state, "[ffa_post_processing] Starting post-processing...")

	ffa_assessment_dir_raw = state.get("ffa_assessment_path")
	if not ffa_assessment_dir_raw:
		_wprint(state, "[ffa_post_processing] SKIPPED: No ffa_assessment_path in state")
		return _carry(state, ffa_post_processing_path=None)

	try:
		ffa_assessment_dir = Path(ffa_assessment_dir_raw)
		assembly_name = str(state.get("assembly_name") or ffa_assessment_dir.parent.name)
		report_dir_raw = state.get("ffa_report_path")
		ffa_report_dir = Path(report_dir_raw) if report_dir_raw else (ffa_assessment_dir.parent / "ffa_report")
		step_renderings_dir = Path(state.get("assembly_renderings_path")) if state.get("assembly_renderings_path") else (ffa_assessment_dir.parent / "assembly_sequence_run1" / "sequence_renderings")
		parts_root_dir = Path(state.get("datasource_root")) if state.get("datasource_root") else None

		# Save all post-processing artifacts directly in the assembly ffa_report folder.
		output_root = ffa_report_dir

		from agent.ffa_post_processing import run_ffa_post_processing

		result = run_ffa_post_processing(
			ffa_assessment_dir=ffa_assessment_dir,
			ffa_report_dir=ffa_report_dir,
			assembly_name=assembly_name,
			output_root=output_root,
			step_renderings_dir=step_renderings_dir,
			parts_root_dir=parts_root_dir,
		)

		_wprint(state, "[ffa_post_processing] COMPLETE")
		_wprint(state, f"[ffa_post_processing] Output dir: {output_root}")
		_wprint(state, f"[ffa_post_processing] PDF: {result.get('pdf_report')}")

		return _carry(
			state,
			ffa_post_processing_path=str(output_root),
			ffa_post_processing_result=result,
		)

	except Exception as e:
		_wprint(state, f"[ffa_post_processing] EXCEPTION: {e}")
		import traceback
		traceback.print_exc()
		return _carry(state, ffa_post_processing_path=None)


def build_ffa_only_workflow():
	"""Build workflow that only runs FFA assessment (Node 10).
	
	Used by run_assess_ffa_only() to re-assess with different settings.
	Input state must already contain checkpoint data (sequence, renderings, BOM, etc.)
	"""
	graph = StateGraph(dict)
	graph.add_node("assess_ffa", _node_assess_ffa)
	
	graph.set_entry_point("assess_ffa")
	graph.add_edge("assess_ffa", END)
	
	return graph.compile(checkpointer=InMemorySaver())


def run_assess_ffa_only(
	checkpoint_path: str,
	ffa_settings_overrides: Optional[Dict[str, Any]] = None,
	experiment_name: str = "ffa_only",
	run_root_dir: Optional[Path] = None,
	experiment_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
	"""Run FFA assessment for ALL assemblies in a checkpoint.
	
	Assembly sequences and renderings are loaded from ground_truth_assembly_sequence/
	All other data (BOM, enriched_parts) come from checkpoint.
	This workflow re-runs only the FFA assessment node with potentially different settings.
	
	Args:
		checkpoint_path: Path to checkpoint root (e.g., data/checkpoints/{timestamp}/)
		ffa_settings_overrides: Optional dict with FFA setting overrides (e.g., {"FFA_mode": "enabled"})
		experiment_name: Name for this FFA experiment (default: "ffa_only"), used in directory structure
		run_root_dir: Optional run root directory. If not provided, creates new run directory with timestamp
		experiment_config: Optional experiment config dict (loaded from experiment.yaml) - overrides defaults
		run_root_dir: Optional run root directory. If not provided, creates new run directory with timestamp
		
	Returns:
		Dict with summary: {"processed": int, "successful": int, "failed": int, "details": List}
	"""
	from agent.checkpoint_utils import (
		load_checkpoint_assemblies, 
		validate_checkpoint,
		load_ground_truth_sequence,
		get_ground_truth_renderings_path
	)
	
	checkpoint_path = Path(checkpoint_path)
	
	print(f"\n[run_assess_ffa_only] Starting FFA assessment from checkpoint: {checkpoint_path}")
	
	# Validate checkpoint
	is_valid, errors = validate_checkpoint(str(checkpoint_path))
	if not is_valid:
		print(f"[run_assess_ffa_only] ERROR: Checkpoint validation failed")
		for error in errors:
			print(f"  ✗ {error}")
		return {
			"processed": 0,
			"successful": 0,
			"failed": 0,
			"details": errors
		}
	
	# Load assemblies from checkpoint
	assemblies = load_checkpoint_assemblies(str(checkpoint_path))
	print(f"[run_assess_ffa_only] Found {len(assemblies)} assemblies: {assemblies}")
	
	# Build FFA-only workflow
	app = build_ffa_only_workflow()
	
	# Settings - Merge: defaults < experiment_config < ffa_settings_overrides
	settings = load_experiment_settings()
	if experiment_config:
		print(f"[run_assess_ffa_only] Merging experiment config ({len(experiment_config)} keys)")
		settings.update(experiment_config)
	if ffa_settings_overrides:
		print(f"[run_assess_ffa_only] Applying FFA settings overrides ({len(ffa_settings_overrides)} keys)")
		settings.update(ffa_settings_overrides)
	print(f"[run_assess_ffa_only] Final settings: FFA_include_interaction_analysis={settings.get('FFA_include_interaction_analysis')}")
	
	# Process each assembly
	results = {
		"processed": 0,
		"successful": 0,
		"failed": 0,
		"details": []
	}
	
	# Create experiment output directory for this run
	# Structure: data/experiments/run_{timestamp}/{experiment_name}/{assembly_name}/
	# This is consistent with run_all_nodes
	if run_root_dir is None:
		# Create new run directory if not provided
		exp_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
		experiments_root = Path(__file__).resolve().parents[1] / "data" / "experiments"
		run_root_dir = experiments_root / f"run_{exp_timestamp}"
	
	run_root_dir = Path(run_root_dir)
	run_root_dir.mkdir(parents=True, exist_ok=True)
	ffa_exp_dir = run_root_dir / experiment_name
	
	for assembly_name in assemblies:
		print(f"\n[run_assess_ffa_only] Processing: {assembly_name}")
		results["processed"] += 1
		
		try:
			# Load checkpoint assembly data
			checkpoint_assembly_dir = checkpoint_path / assembly_name
			metadata_path = checkpoint_assembly_dir / "metadata.json"
			
			if not metadata_path.exists():
				error_msg = f"{assembly_name}: metadata.json not found"
				print(f"  ✗ {error_msg}")
				results["failed"] += 1
				results["details"].append(error_msg)
				continue
			
			with open(metadata_path, "r", encoding="utf-8") as f:
				checkpoint_metadata = json.load(f)
			
			# Load sequence and renderings from GROUND TRUTH
			sequence_dict = load_ground_truth_sequence(assembly_name)
			if not sequence_dict:
				error_msg = f"{assembly_name}: Failed to load sequence from ground_truth"
				print(f"  ✗ {error_msg}")
				results["failed"] += 1
				results["details"].append(error_msg)
				continue
			
			rendered_steps_dir = get_ground_truth_renderings_path(assembly_name)
			if not rendered_steps_dir:
				error_msg = f"{assembly_name}: Failed to load renderings from ground_truth"
				print(f"  ✗ {error_msg}")
				results["failed"] += 1
				results["details"].append(error_msg)
				continue
			
			# Load other files from CHECKPOINT
			# BOM can be named either BOM_enriched.json or {assembly_name}_BOM_enriched.json
			bom_candidates = list(checkpoint_assembly_dir.glob("BOM_enriched.json")) + list(checkpoint_assembly_dir.glob("*_BOM_enriched.json"))
			bom_json_path = bom_candidates[0] if bom_candidates else None
			enriched_dir = checkpoint_assembly_dir / "enriched_parts"
			
			# Verify checkpoint files exist
			missing = []
			if not bom_json_path:
				missing.append("BOM_enriched.json")
			for path, name in [
				(enriched_dir, "enriched_parts/"),
			]:
				if not path.exists():
					missing.append(name)
			
			if missing:
				error_msg = f"{assembly_name}: Missing checkpoint files: {', '.join(missing)}"
				print(f"  ✗ {error_msg}")
				results["failed"] += 1
				results["details"].append(error_msg)
				continue
			
			# Create experiment output directory for this assembly
			# Under experiment directory in the run directory (same structure as run_all_nodes)
			exp_output_dir = ffa_exp_dir / assembly_name
			exp_output_dir.mkdir(parents=True, exist_ok=True)
			
			# Copy data to experiment directory (from BOTH ground_truth and checkpoint)
			import shutil
			
			# Write sequence.json from ground_truth dict
			sequence_json_path = exp_output_dir / "assembly_sequence.json"
			with open(sequence_json_path, "w", encoding="utf-8") as f:
				json.dump(sequence_dict, f, indent=2, ensure_ascii=False)
			
			# Copy renderings from ground_truth
			shutil.copytree(rendered_steps_dir, exp_output_dir / "sequence_renderings", dirs_exist_ok=True)
			
			# Copy BOM and enriched_parts from checkpoint
			shutil.copy2(bom_json_path, exp_output_dir / "BOM_enriched.json")
			shutil.copytree(enriched_dir, exp_output_dir / "enriched_parts", dirs_exist_ok=True)
			
			# Resolve interaction_analysis.json path – the node loads the file itself
			# (avoids passing large dicts through LangGraph state / InMemorySaver)
			ia_path = checkpoint_assembly_dir / "interaction_analysis.json"
			print(f"  [IA] Looking for: {ia_path}")
			ia_checkpoint_path = str(ia_path) if ia_path.exists() else None
			if ia_checkpoint_path:
				print(f"  ✓ interaction_analysis.json found – will be loaded by FFA node")
			else:
				print(f"  ℹ️  interaction_analysis.json not found in checkpoint (skipped)")
			
			# Set environment variable for experiment output directory
			os.environ["APA_EXPERIMENT_OUTPUT_DIR"] = str(exp_output_dir)
			
			# Create state for FFA-only workflow
			run_id = str(uuid.uuid4())
			state = {
				"run_id": run_id,
				"datasource_root": "",  # Not needed for FFA-only
				"assembly_name": assembly_name,
				"experiment_name": experiment_name,
				"workflow_print": True,
				"workflow_print_prompt_preview_chars": 800,
				
				# FFA Assessment inputs (from experiment directory)
				"assembly_sequence_path": str(sequence_json_path),
				"rendered_steps_dir": str(exp_output_dir / "sequence_renderings"),
				"current_sequence_run_dir": str(exp_output_dir),
				
				# Path to interaction_analysis.json – loaded fresh by _node_assess_ffa
				"interaction_analysis_checkpoint_path": ia_checkpoint_path,
				
				# Pass merged settings so _node_assess_ffa uses them instead of re-reading YAML
				"experiment_settings_overrides": settings,
			}
			
			# Run FFA-only workflow
			config = {"configurable": {"thread_id": run_id}}
			result = app.invoke(state, config=config)
			
			# Check result
			if result.get("ffa_assessment_path"):
				print(f"  ✓ FFA assessment complete: {result['ffa_assessment_path']}")
				results["successful"] += 1
				results["details"].append({
					"assembly": assembly_name,
					"status": "success",
					"output_dir": result["ffa_assessment_path"]
				})
			else:
				error_msg = f"{assembly_name}: FFA assessment failed or returned None"
				print(f"  ✗ {error_msg}")
				results["failed"] += 1
				results["details"].append(error_msg)
		
		except Exception as e:
			error_msg = f"{assembly_name}: {str(e)}"
			print(f"  ✗ EXCEPTION: {error_msg}")
			results["failed"] += 1
			results["details"].append(error_msg)
			import traceback
			traceback.print_exc()
	
	# Print summary
	print(f"\n[run_assess_ffa_only] SUMMARY")
	print(f"  Processed: {results['processed']}")
	print(f"  Successful: {results['successful']}")
	print(f"  Failed: {results['failed']}")
	print(f"[run_assess_ffa_only] Experiment: {experiment_name}")
	print(f"[run_assess_ffa_only] Run root: {run_root_dir}")
	print(f"[run_assess_ffa_only] Experiment directory: {ffa_exp_dir}")
	
	return results


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
	graph.add_node("interaction_analysis", _node_interaction_analysis)
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
	graph.add_edge("render_assembly_steps", "interaction_analysis")
	graph.add_edge("interaction_analysis", "validate_assembly_sequence")
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


def build_workflow_sequence_gt():
	"""Build workflow that uses GT sequence structure instead of free LLM generation.

	Identical to build_workflow() but:
	  - generate_assembly_sequence  →  generate_assembly_sequence_from_gt
	  - No validation/retry loop  (GT defines the structure – no need to retry)

	Node order:
	  resolve_paths → run_assembly → list_parts → run_monoparts →
	  merge_copy_part_data → merge_bom →
	  generate_assembly_sequence_from_gt → render_assembly_steps →
	  interaction_analysis → assess_ffa → ffa_reporter → ffa_post_processing
	"""
	graph = StateGraph(dict)
	graph.add_node("resolve_paths",                        _node_resolve_paths)
	graph.add_node("run_assembly",                         _node_run_assembly)
	graph.add_node("list_parts",                           _node_list_parts)
	graph.add_node("run_monoparts",                        _node_run_monoparts)
	graph.add_node("merge_bom",                            _node_merge_bom)
	graph.add_node("merge_copy_part_data",                 _node_merge_copy_part_data)
	graph.add_node("generate_assembly_sequence_from_gt",   _node_generate_assembly_sequence_from_gt)
	graph.add_node("render_assembly_steps",                _node_render_assembly_steps)
	graph.add_node("interaction_analysis",                 _node_interaction_analysis)
	graph.add_node("assess_ffa",                           _node_assess_ffa)
	graph.add_node("ffa_reporter",                         _node_ffa_reporter)
	graph.add_node("ffa_post_processing",                  _node_ffa_post_processing)

	graph.set_entry_point("resolve_paths")
	graph.add_edge("resolve_paths",                      "run_assembly")
	graph.add_edge("run_assembly",                        "list_parts")
	graph.add_edge("list_parts",                          "run_monoparts")
	graph.add_edge("run_monoparts",                       "merge_copy_part_data")
	graph.add_edge("merge_copy_part_data",                "merge_bom")
	graph.add_edge("merge_bom",                           "generate_assembly_sequence_from_gt")
	graph.add_edge("generate_assembly_sequence_from_gt",  "render_assembly_steps")
	graph.add_edge("render_assembly_steps",               "interaction_analysis")
	graph.add_edge("interaction_analysis",                "assess_ffa")
	graph.add_edge("assess_ffa",                          "ffa_reporter")
	graph.add_edge("ffa_reporter",                        "ffa_post_processing")
	graph.add_edge("ffa_post_processing",                 END)

	return graph.compile(checkpointer=InMemorySaver())


def build_workflow_sequence_gt_prerendered():
	"""Identical to build_workflow_sequence_gt() but skips the OCC renderer.

	render_assembly_steps is replaced by load_gt_renderings, which copies
	pre-existing renderings from:
	    data/ground_truth/assembly_sequence_ground_truth/{assembly_name}/renderings/

	Node order:
	  resolve_paths → run_assembly → list_parts → run_monoparts →
	  merge_copy_part_data → merge_bom →
	  generate_assembly_sequence_from_gt → load_gt_renderings →
	  interaction_analysis → assess_ffa → ffa_reporter → ffa_post_processing
	"""
	graph = StateGraph(dict)
	graph.add_node("resolve_paths",                        _node_resolve_paths)
	graph.add_node("run_assembly",                         _node_run_assembly)
	graph.add_node("list_parts",                           _node_list_parts)
	graph.add_node("run_monoparts",                        _node_run_monoparts)
	graph.add_node("merge_bom",                            _node_merge_bom)
	graph.add_node("merge_copy_part_data",                 _node_merge_copy_part_data)
	graph.add_node("generate_assembly_sequence_from_gt",   _node_generate_assembly_sequence_from_gt)
	graph.add_node("load_gt_renderings",                   _node_load_gt_renderings)
	graph.add_node("interaction_analysis",                 _node_interaction_analysis)
	graph.add_node("assess_ffa",                           _node_assess_ffa)
	graph.add_node("ffa_reporter",                         _node_ffa_reporter)
	graph.add_node("ffa_post_processing",                  _node_ffa_post_processing)

	graph.set_entry_point("resolve_paths")
	graph.add_edge("resolve_paths",                      "run_assembly")
	graph.add_edge("run_assembly",                        "list_parts")
	graph.add_edge("list_parts",                          "run_monoparts")
	graph.add_edge("run_monoparts",                       "merge_copy_part_data")
	graph.add_edge("merge_copy_part_data",                "merge_bom")
	graph.add_edge("merge_bom",                           "generate_assembly_sequence_from_gt")
	graph.add_edge("generate_assembly_sequence_from_gt",  "load_gt_renderings")
	graph.add_edge("load_gt_renderings",                  "interaction_analysis")
	graph.add_edge("interaction_analysis",                "assess_ffa")
	graph.add_edge("assess_ffa",                          "ffa_reporter")
	graph.add_edge("ffa_reporter",                        "ffa_post_processing")
	graph.add_edge("ffa_post_processing",                 END)

	return graph.compile(checkpointer=InMemorySaver())


def run_all_nodes(
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
	experiment_settings_overrides: Optional[Dict[str, Any]] = None,
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


def run_all_nodes_sequence_gt(
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
	experiment_settings_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
	"""Run the full workflow with GT-structured assembly sequence generation.

	Identical signature and return value to run_all_nodes().
	The only difference is that build_workflow_sequence_gt() is used instead of
	build_workflow(), so the LLM only writes step descriptions – the sequence
	structure comes from ground truth.
	"""
	start_t = time.perf_counter()
	app = build_workflow_sequence_gt()
	run_id = str(uuid.uuid4())
	config = {"configurable": {"thread_id": run_id}}
	settings = load_experiment_settings()
	if workflow_print is None:
		workflow_print = bool(settings.get("workflow_print", False))

	try:
		preview_chars = int(settings.get("workflow_print_prompt_preview_chars") or 800)
	except Exception:
		preview_chars = 800

	assembly_name  = Path(datasource_root).name
	experiment_name = os.environ.get("APA_EXPERIMENT_NAME", "direct_run")

	state: Dict[str, Any] = {
		"run_id":                      run_id,
		"datasource_root":             str(datasource_root),
		"assembly_name":               assembly_name,
		"experiment_name":             experiment_name,
		"use_unique_parts":            bool(use_unique_parts),
		"workflow_print":              bool(workflow_print),
		"workflow_print_prompt_preview_chars": int(preview_chars),
		"parallel":                    bool(parallel),
		"max_workers":                 int(max_workers),
		"assembly_keywords":           assembly_keywords,
		"assembly_limit":              int(assembly_limit),
		"overwrite_assembly_metadata": bool(overwrite_assembly_metadata),
		"part_keywords":               part_keywords,
		"part_limit":                  int(part_limit),
		# Guard: prevents create_checkpoint() from writing back into data/ground_truth/.
		# In the sequence_gt workflow the GT directory is the READ-ONLY input source —
		# any write-back would silently overwrite the curated reference data.
		"is_sequence_gt_workflow":     True,
		"experiment_settings_overrides": dict(experiment_settings_overrides or {}),
	}
	result = app.invoke(state, config=config)
	runtime_seconds = float(time.perf_counter() - start_t)

	total_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
	assembly_res = result.get("assembly_result") if isinstance(result, dict) else None
	parts_res    = (result.get("part_results") or []) if isinstance(result, dict) else []
	for tr in [assembly_res, *parts_res]:
		u = _token_usage_from_tool_result(tr)
		total_usage["input_tokens"]  += u["input_tokens"]
		total_usage["output_tokens"] += u["output_tokens"]
		total_usage["total_tokens"]  += u["total_tokens"]

	if isinstance(result, dict):
		result["runtime_seconds"]    = runtime_seconds
		result["token_usage_total"]  = total_usage

	if workflow_print:
		print(
			"[run_summary] runtime_seconds=" + f"{runtime_seconds:.3f}"
			+ " | token_usage_total=" + json.dumps(total_usage)
		)

	return result


def run_all_nodes_sequence_gt_prerendered(
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
	experiment_settings_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
	"""Run the GT-sequence workflow using pre-existing GT renderings (no OCC renderer).

	Identical to run_all_nodes_sequence_gt() except that render_assembly_steps is
	replaced by load_gt_renderings.  Renderings are read from:

	    data/ground_truth/assembly_sequence_ground_truth/{assembly_name}/renderings/

	This is the fastest variant: no STEP parsing for rendering, no Win32 window.
	"""
	start_t = time.perf_counter()
	app = build_workflow_sequence_gt_prerendered()
	run_id = str(uuid.uuid4())
	config = {"configurable": {"thread_id": run_id}}
	settings = load_experiment_settings()
	if workflow_print is None:
		workflow_print = bool(settings.get("workflow_print", False))

	try:
		preview_chars = int(settings.get("workflow_print_prompt_preview_chars") or 800)
	except Exception:
		preview_chars = 800

	assembly_name  = Path(datasource_root).name
	experiment_name = os.environ.get("APA_EXPERIMENT_NAME", "direct_run")

	state: Dict[str, Any] = {
		"run_id":                      run_id,
		"datasource_root":             str(datasource_root),
		"assembly_name":               assembly_name,
		"experiment_name":             experiment_name,
		"use_unique_parts":            bool(use_unique_parts),
		"workflow_print":              bool(workflow_print),
		"workflow_print_prompt_preview_chars": int(preview_chars),
		"parallel":                    bool(parallel),
		"max_workers":                 int(max_workers),
		"assembly_keywords":           assembly_keywords,
		"assembly_limit":              int(assembly_limit),
		"overwrite_assembly_metadata": bool(overwrite_assembly_metadata),
		"part_keywords":               part_keywords,
		"part_limit":                  int(part_limit),
		# Ground truth is read-only input — never write back into GT directory
		"is_sequence_gt_workflow":     True,
		"experiment_settings_overrides": dict(experiment_settings_overrides or {}),
	}
	result = app.invoke(state, config=config)
	runtime_seconds = float(time.perf_counter() - start_t)

	total_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
	assembly_res = result.get("assembly_result") if isinstance(result, dict) else None
	parts_res    = (result.get("part_results") or []) if isinstance(result, dict) else []
	for tr in [assembly_res, *parts_res]:
		u = _token_usage_from_tool_result(tr)
		total_usage["input_tokens"]  += u["input_tokens"]
		total_usage["output_tokens"] += u["output_tokens"]
		total_usage["total_tokens"]  += u["total_tokens"]

	if isinstance(result, dict):
		result["runtime_seconds"]    = runtime_seconds
		result["token_usage_total"]  = total_usage

	if workflow_print:
		print(
			"[run_summary] runtime_seconds=" + f"{runtime_seconds:.3f}"
			+ " | token_usage_total=" + json.dumps(total_usage)
		)

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
