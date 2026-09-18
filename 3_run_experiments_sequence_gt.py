"""
Experiment Runner – Assembly Sequence from Ground Truth (ASGT)

Identical to run_experiments.py in structure and output, EXCEPT:
  - Node "generate_assembly_sequence" is replaced by "generate_assembly_sequence_from_gt"
  - The LLM only writes step_description + joining_process per step.
  - The step order (step_id, belongs_to, base_part, joining_part) comes from
    data/ground_truth/assembly_sequence_ground_truth/{assembly_name}/sequence.json

Run folder naming:
  data/experiments/run_{TIMESTAMP}_seq_gt/

Everything else – output structure, experiment configs, FFA assessment, evaluation
compatibility – is identical to run_experiments.py.

Usage:
    python run_experiments_sequence_gt.py
    python run_experiments_sequence_gt.py my_experiment.yaml
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Union
from datetime import datetime

from agent.config import WorkflowConfig
from agent.workflow import run_all_nodes_sequence_gt, run_all_nodes_sequence_gt_prerendered
from agent.checkpoint_utils import load_checkpoint_assemblies, validate_checkpoint, create_checkpoint
from agent.config_utils import load_experiment_config, discover_experiments as discover_experiments_from_config


# ============================================================================
# STEUERUNG: Welche Assemblies sollen verarbeitet werden?
# ============================================================================
MASTER_STEP_INPUT_FOLDER: str = "data/input/test"
STEPPARSER_OUTPUT_FOLDER: str = "data/processed/stepparser"
LLM_OUTPUT_FOLDER: str = "data/experiments/NEWEXPERIMENT"
EXPERIMENT_CONFIG_FOLDER: str = "configs/GEH"
EXPERIMENT_CONFIG_NAME: Optional[str] = None  # YAML stem/name, .yaml path, or None/"all"
GROUND_TRUTH_SEQUENCE_ROOT: str = "data/ground_truth/assembly_sequence_ground_truth"
EXPERIMENT_SUMMARY_PATH: str = "data/experiments/experiments_summary.json"
STEP_FILES_OVERRIDE: Optional[Union[str, List[str]]] = "all"
FORCE_LOAD_GT_ADDITIONAL_INFO: bool = True

# Selective rendering controls
ENABLE_SELECTIVE_ASSEMBLY_RENDERING: bool = True
SKIP_ALREADY_RENDERED_ASSEMBLIES: bool = True
STEPPARSER_COLOR_MODE: str = "geometry"
STEPPARSER_TRANSPARENCY_VALUES: List[float] = [0.0, 0.3]
STEPPARSER_HEADLESS_MODE: bool = True

# Checkpoint creation control
ENABLE_CHECKPOINT_CREATION: bool = False  # Checkpoint creation disabled by default
# ============================================================================


def get_step_files(input_folder: Path = Path(MASTER_STEP_INPUT_FOLDER)) -> Dict[str, Path]:
    """Return assembly_name -> STEP path from the configured master input folder."""
    input_folder = Path(input_folder)
    if not input_folder.exists():
        return {}

    step_files: Dict[str, Path] = {}
    for pattern in ("*.STEP", "*.step"):
        for step_file in sorted(input_folder.glob(pattern)):
            step_files[step_file.stem] = step_file
    return step_files


def get_rendered_assemblies(stepparser_root: Path) -> set:
    """Return assemblies that already have required stepparser metadata/BOM."""
    try:
        from stepparser.io.metadata_manager import MetadataManager
    except Exception:
        return {
            d.name for d in Path(stepparser_root).iterdir()
            if d.is_dir() and not d.name.startswith("_")
        } if Path(stepparser_root).exists() else set()

    rendered = set()
    stepparser_root = Path(stepparser_root)
    if not stepparser_root.exists():
        return rendered

    for assembly_dir in stepparser_root.iterdir():
        if not assembly_dir.is_dir() or assembly_dir.name.startswith("_"):
            continue
        if MetadataManager.check_if_processed(assembly_dir.name, str(stepparser_root)):
            rendered.add(assembly_dir.name)
    return rendered


def render_missing_assemblies(
    input_folder: Path = Path(MASTER_STEP_INPUT_FOLDER),
    output_folder: Path = Path(STEPPARSER_OUTPUT_FOLDER),
) -> int:
    """Run stepparser only for assemblies whose renderings/metadata are missing."""
    if not ENABLE_SELECTIVE_ASSEMBLY_RENDERING:
        return 0

    input_folder = Path(input_folder)
    output_folder = Path(output_folder)
    step_files = get_step_files(input_folder)
    if not step_files:
        print(f"⚠️  No STEP files found in {input_folder}; skipping pre-render phase")
        return 0

    rendered = get_rendered_assemblies(output_folder)
    missing = sorted(set(step_files) - rendered)

    print("\n" + "=" * 80)
    print("SELECTIVE ASSEMBLY RENDERING")
    print("=" * 80)
    print(f"Input:   {input_folder}")
    print(f"Output:  {output_folder}")
    print(f"STEP files:        {len(step_files)}")
    print(f"Already rendered:  {len(rendered)}")
    print(f"Missing:           {len(missing)}")

    if not missing:
        print("✓ All assembly renderings already exist; skipping stepparser")
        return 0

    print(f"Rendering missing assemblies: {', '.join(missing)}")
    from stepparser.processor import StepProcessor

    processor = StepProcessor(
        input_folder=str(input_folder),
        output_folder=str(output_folder),
        skip_if_processed=SKIP_ALREADY_RENDERED_ASSEMBLIES,
        color_mode=STEPPARSER_COLOR_MODE,
        transparency_values=STEPPARSER_TRANSPARENCY_VALUES,
        headless_mode=STEPPARSER_HEADLESS_MODE,
    )
    processor.process_all_step_files()
    return len(missing)


def discover_experiments(experiments_dir: Path = Path(EXPERIMENT_CONFIG_FOLDER)) -> List[Path]:
    """Find all experiment YAML files.

    Priority:
    1. configs/sequence_gt/  (dedicated GT-workflow folder)
    2. configs/full_workflow/ (shared full-workflow folder)
    3. configs/experiments/  (legacy fallback)
    """
    config_name = EXPERIMENT_CONFIG_NAME
    if config_name and str(config_name).lower() not in {"all", "*"}:
        config_path = Path(str(config_name))
        if not config_path.suffix:
            config_path = Path(EXPERIMENT_CONFIG_FOLDER) / f"{config_path.name}.yaml"
        elif not config_path.is_absolute() and config_path.parent == Path("."):
            config_path = Path(EXPERIMENT_CONFIG_FOLDER) / config_path
        return [config_path] if config_path.exists() else []

    if not experiments_dir.exists():
        return []
    yaml_files = sorted(experiments_dir.glob("*.yaml"))
    yaml_files = [f for f in yaml_files if f.name != "exp_example.yaml"]
    return yaml_files


def discover_completed_assemblies_in_experiment(experiment_output_dir: Path) -> List[str]:
    """
    Return list of assemblies already successfully completed in this experiment.
    
    A completed assembly is one that has ffa_assessment/ffa_assessment.json
    (indicative of full workflow completion).
    """
    completed = []
    if not experiment_output_dir.exists():
        return completed
    
    for asm_dir in experiment_output_dir.iterdir():
        if not asm_dir.is_dir():
            continue
        ffa_file = asm_dir / "ffa_assessment" / "ffa_assessment.json"
        if ffa_file.exists():
            completed.append(asm_dir.name)
    
    return sorted(completed)


def run_single_experiment(
    experiment_yaml: Path,
    stepparser_root: Path = Path(STEPPARSER_OUTPUT_FOLDER),
    run_root_dir: Path = None,
    rep_id: Optional[int] = None,
    checkpoint_root: Optional[Path] = None,
    run_name: str = "",
) -> Dict:
    """Run a single experiment using the GT-sequence workflow.

    Drop-in replacement for run_experiments.py::run_single_experiment –
    only difference is the call to run_all_nodes_sequence_gt().
    """
    print("=" * 80)
    print(f"EXPERIMENT (SEQ-GT): {experiment_yaml.name}")
    print("=" * 80)

    if run_root_dir is not None:
        os.environ["APA_EXPERIMENT_OUTPUT_DIR"] = str(run_root_dir)

    os.environ["APA_MASTER_STEP_INPUT_FOLDER"] = str(Path(MASTER_STEP_INPUT_FOLDER))
    os.environ["APA_GROUND_TRUTH_SEQUENCE_ROOT"] = str(Path(GROUND_TRUTH_SEQUENCE_ROOT))

    if ENABLE_SELECTIVE_ASSEMBLY_RENDERING:
        render_missing_assemblies(Path(MASTER_STEP_INPUT_FOLDER), Path(stepparser_root))

    config = WorkflowConfig.from_yaml(experiment_yaml)
    if config.experiment_name == "default":
        config.experiment_name = experiment_yaml.stem

    # Append repetition suffix to experiment name when running multiple reps
    if rep_id is not None:
        config.experiment_name = f"{config.experiment_name}_run{rep_id}"

    # Prefix with run name for identification
    if run_name:
        config.experiment_name = f"{run_name}_{config.experiment_name}"

    os.environ["APA_EXPERIMENT_YAML"] = str(experiment_yaml)

    if run_root_dir is not None:
        nested_output_root = run_root_dir / config.experiment_name
    else:
        nested_output_root = config.experiment_output_root

    print(f"Experiment Name: {config.experiment_name}")
    print(f"Description:     {getattr(config, 'description', 'N/A')}")
    print(f"Output Root:     {nested_output_root}")

    checkpoint_dir_override = None
    if ENABLE_CHECKPOINT_CREATION:
        # Determine checkpoint dir for this experiment run.
        # Structure: data/checkpoints/{exp_name_with_run_suffix}/
        if checkpoint_root is not None:
            checkpoint_dir_override = checkpoint_root / config.experiment_name
        else:
            # For single runs (CLI): create checkpoint per run grouping all assemblies together.
            checkpoint_dir_override = Path(CHECKPOINT_OUTPUT_FOLDER) / config.experiment_name
        checkpoint_dir_override.mkdir(parents=True, exist_ok=True)
        print(f"Checkpoint Dir:  {checkpoint_dir_override}")
    else:
        print("Checkpoint Dir:  DISABLED")

    # Log FFA settings
    ffa_mode = getattr(config, "FFA_mode", "disabled")
    print(f"\n🔧 FFA Assessment:  FFA_mode={ffa_mode}")

    use_gt_renderings = bool(getattr(config, "use_gt_renderings", False))
    if use_gt_renderings:
        print(f"🔧 Sequence source: Ground Truth (ASGT workflow, pre-rendered — OCC renderer SKIPPED)")
        _run_fn = run_all_nodes_sequence_gt_prerendered
    else:
        print(f"🔧 Sequence source: Ground Truth (ASGT workflow)")
        _run_fn = run_all_nodes_sequence_gt

    # Auto-discover assemblies
    print("\n🔍 Auto-discovering assemblies from stepparser...")
    if not stepparser_root.exists():
        print(f"⚠️  Stepparser root not found: {stepparser_root}")
        return {"status": "skipped", "reason": "stepparser_root_not_found"}

    step_files = sorted([
        d.name for d in stepparser_root.iterdir()
        if d.is_dir() and not d.name.startswith("_")
    ])
    if not step_files:
        print("⚠️  No assemblies found in stepparser root")
        return {"status": "skipped", "reason": "no_assemblies_found"}

    print(f"   Found {len(step_files)} assemblies in stepparser root")

    # Check which assemblies have already been completed in this experiment
    completed_assemblies = discover_completed_assemblies_in_experiment(nested_output_root)
    step_files_to_process = [s for s in step_files if s not in completed_assemblies]
    
    if completed_assemblies:
        print(f"   ✅ Already completed ({len(completed_assemblies)}): {completed_assemblies}")
    if step_files_to_process:
        print(f"   ⏳ Still to process ({len(step_files_to_process)}): {step_files_to_process}")
    else:
        print(f"   ✨ All assemblies already completed for this experiment!")
        return {
            "experiment_name":  config.experiment_name,
            "experiment_yaml":  str(experiment_yaml),
            "status":           "completed",
            "reason":           "all_assemblies_already_processed",
            "results":          [],
        }

    results = []

    for step_name in step_files_to_process:
        datasource_root = stepparser_root / step_name
        if not datasource_root.exists():
            print(f"⚠️  Datasource not found: {datasource_root}, skipping")
            continue

        print(f"\n📦 Processing: {step_name}")
        print(f"   Source: {datasource_root}")

        experiment_output_dir = nested_output_root / step_name
        experiment_output_dir.mkdir(parents=True, exist_ok=True)
        print(f"   Output: {experiment_output_dir}")

        os.environ["APA_EXPERIMENT_OUTPUT_DIR"] = str(experiment_output_dir)
        os.environ["APA_EXPERIMENT_NAME"]        = config.experiment_name
        experiment_settings_overrides = {}
        if FORCE_LOAD_GT_ADDITIONAL_INFO:
            experiment_settings_overrides.update({
                "AAI_use_additional_info": True,
                "ASGT_use_additional_info": True,
            })

        try:
            # KEY DIFFERENCE: GT-based sequence workflow (with or without OCC renderer)
            result = _run_fn(
                datasource_root=str(datasource_root),
                use_unique_parts=config.use_unique_parts,
                workflow_print=config.workflow_print,
                parallel=getattr(config, "parallel", False),
                max_workers=getattr(config, "max_workers", 4),
                assembly_keywords=config.img_to_analyse_assy,
                assembly_limit=getattr(config, "assembly_limit", 8),
                part_keywords=config.img_to_analyse_monopart,
                part_limit=getattr(config, "part_limit", 8),
                experiment_settings_overrides=experiment_settings_overrides,
            )

            summary = {
                "experiment_name": config.experiment_name,
                "step_file":       step_name,
                "status":          "success",
                "assembly_written": result.get("assembly_result", {}).get("metadata_written_path"),
                "parts_count":     len(result.get("part_results", [])),
                "runtime_seconds": result.get("runtime_seconds", 0),
                "token_usage":     result.get("token_usage_total", {}),
                "warnings":        result.get("warnings", []),
                "assembly_sequence": {
                    "source":  "ground_truth",
                    "path":    result.get("assembly_sequence_path"),
                },
                "ffa_assessment": {
                    "enabled": ffa_mode != "disabled",
                    "mode":    ffa_mode,
                    "path":    result.get("ffa_assessment_path"),
                },
            }

            summary_path = experiment_output_dir / "experiment_summary.json"
            summary_path.write_text(
                json.dumps(summary, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            results.append(summary)

            # Create checkpoint after full assembly processing is complete
            if ENABLE_CHECKPOINT_CREATION:
                try:
                    # Convert config to dict to capture full experiment configuration
                    current_settings = {**config.__dict__}
                    # Ensure runtime flags are included
                    current_settings["use_gt_renderings"] = use_gt_renderings
                    
                    cp_path = create_checkpoint(
                        exp_output_dir=experiment_output_dir,
                        assembly_name=step_name,
                        checkpoint_base_path=CHECKPOINT_OUTPUT_FOLDER,
                        current_settings=current_settings,
                        protect_ground_truth=True,
                        checkpoint_dir_override=checkpoint_dir_override,
                    )
                    print(f"      Checkpoint: {cp_path}")
                except Exception as cp_err:
                    print(f"   ⚠️  Checkpoint creation failed (non-fatal): {cp_err}")
            else:
                print(f"      Checkpoint: DISABLED (ENABLE_CHECKPOINT_CREATION=False)")

            ffa_status = "✓" if summary["ffa_assessment"]["path"] else "✗"
            print(f"   ✅ Success: {summary['parts_count']} parts processed")
            print(f"      Assembly Sequence (GT): {summary['assembly_sequence']['path'] or 'N/A'}")
            print(f"      FFA Assessment: {ffa_status} {summary['ffa_assessment']['path'] or 'N/A'}")

        except Exception as e:
            print(f"   ❌ Error: {e}")
            results.append({
                "experiment_name": config.experiment_name,
                "step_file":       step_name,
                "status":          "error",
                "error":           str(e),
            })

    print()
    print(f"✅ Experiment {config.experiment_name} completed: {len(results)} assemblies processed")
    print("=" * 80)
    print()

    return {
        "experiment_name":  config.experiment_name,
        "experiment_yaml":  str(experiment_yaml),
        "config":           config.model_dump(),
        "results":          results,
        "total_assemblies": len(results),
        "successful":       sum(1 for r in results if r.get("status") == "success"),
    }


def _experiment_run_exists(output_dir: Path, exp_stem: str, rep_id: Optional[int]) -> bool:
    """Return True if a completed run folder for this experiment+rep already exists.

    Matches any folder whose name matches {exp_stem}_run{rep_id} or _{exp_stem}_run{rep_id}
    (run_name-agnostic) and that contains at least one assembly sub-folder with experiment_summary.json.
    If rep_id is None the stem is matched as-is (single-rep experiment).
    """
    if not output_dir.exists():
        return False
    # Try both patterns: with and without underscore prefix (for run_name compatibility)
    if rep_id is not None:
        suffixes = [f"{exp_stem}_run{rep_id}", f"_{exp_stem}_run{rep_id}"]
    else:
        suffixes = [f"{exp_stem}", f"_{exp_stem}"]
    
    for candidate in output_dir.iterdir():
        if not candidate.is_dir():
            continue
        if not any(candidate.name.endswith(suffix) for suffix in suffixes):
            continue
        # Verify it contains at least one assembly with results
        if any(
            (asm_dir / "experiment_summary.json").exists()
            for asm_dir in candidate.iterdir()
            if asm_dir.is_dir()
        ):
            return True
    return False


def run_all_experiments(
    experiments_dir: Path = Path(EXPERIMENT_CONFIG_FOLDER),
    stepparser_root: Path = Path(STEPPARSER_OUTPUT_FOLDER),
    output_dir: Optional[Path] = None,
) -> Dict:
    """Run all experiments using the GT-sequence workflow.

    Creates:  data/experiments/run_{TIMESTAMP}_seq_gt/   (default)
    Or uses:  output_dir/                                (when --output-dir is given)
              ├── run_log.json
              ├── {run_name}_exp1_baseline_run1/
              │   ├── assembly1/
              │   └── assembly2/
              └── {run_name}_exp2_run1/
                  └── assembly/

    Already-completed run folders are skipped automatically.
    """
    start_time = time.time()

    run_timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    run_name = ""  # Disable color+fruit naming; use experiment name directly

    if output_dir is not None:
        run_root_dir = Path(output_dir)
        print(f"📁 Output directory (fixed): {run_root_dir}")
    else:
        # Auto-generate folder name based on timestamp and run_name (if available)
        folder_suffix = f"_{run_name}" if run_name else ""
        run_root_dir = Path(LLM_OUTPUT_FOLDER) / f"run_{run_timestamp}{folder_suffix}_seq_gt"
    run_root_dir.mkdir(parents=True, exist_ok=True)

    # Shared checkpoint root aligned with this run's timestamp, only when enabled.
    workspace_root = Path(__file__).resolve().parent
    checkpoint_root = None
    if ENABLE_CHECKPOINT_CREATION:
        checkpoint_root = workspace_root / CHECKPOINT_OUTPUT_FOLDER / run_timestamp
        checkpoint_root.mkdir(parents=True, exist_ok=True)

    print(f"📁 Run name:             {run_name}")
    print(f"📁 Run directory:        {run_root_dir}")
    print(f"📁 Checkpoint directory: {checkpoint_root if checkpoint_root else 'DISABLED'}")
    if output_dir is not None:
        existing = [
            d.name for d in run_root_dir.iterdir()
            if d.is_dir() and not d.name.startswith("_") and d.name != "evaluation"
        ]
        if existing:
            print(f"   Already in target folder ({len(existing)} folder(s)):")
            for e in sorted(existing):
                print(f"     - {e}")
    print()

    experiments = discover_experiments(experiments_dir)
    if not experiments:
        print(f"⚠️  No experiments found in {experiments_dir}")
        return {"status": "no_experiments"}

    print(f"🔬 Found {len(experiments)} experiment(s):")
    for exp in experiments:
        print(f"   - {exp.name}")
    print()

    all_results = []
    for exp_yaml in experiments:
        # Read repetitions from config (default: 1)
        try:
            _cfg = WorkflowConfig.from_yaml(exp_yaml)
            repetitions = int(getattr(_cfg, "repetitions", 1))
        except Exception:
            repetitions = 1

        print(f"🔁 {exp_yaml.stem}: {repetitions} repetition(s)")

        for rep_id in range(1, repetitions + 1):
            rep_label = f"{exp_yaml.stem}_run{rep_id}" if repetitions > 1 else exp_yaml.stem
            effective_rep_id = rep_id if repetitions > 1 else None

            # ── Skip check ──────────────────────────────────────────────────
            if _experiment_run_exists(run_root_dir, exp_yaml.stem, effective_rep_id):
                print(f"   ⏭  Repetition {rep_id}/{repetitions}: {rep_label}  ← bereits vorhanden, wird übersprungen")
                all_results.append({
                    "experiment_name": rep_label,
                    "experiment_yaml": str(exp_yaml),
                    "status":          "skipped",
                    "reason":          "already_exists",
                })
                continue
            # ────────────────────────────────────────────────────────────────

            print(f"   ▶ Repetition {rep_id}/{repetitions}: {rep_label}")
            try:
                result = run_single_experiment(
                    exp_yaml,
                    stepparser_root,
                    run_root_dir,
                    rep_id=effective_rep_id,
                    checkpoint_root=checkpoint_root,
                    run_name=run_name,
                )
                all_results.append(result)
            except Exception as e:
                print(f"❌ Experiment {exp_yaml.name} rep {rep_id} failed: {e}")
                all_results.append({
                    "experiment_name": rep_label,
                    "experiment_yaml": str(exp_yaml),
                    "status":          "failed",
                    "error":           str(e),
                })

    runtime = time.time() - start_time

    skipped = sum(1 for r in all_results if r.get("status") == "skipped")
    summary = {
        "run_timestamp":            run_timestamp,
        "run_root_dir":             str(run_root_dir),
        "workflow_mode":            "sequence_from_ground_truth",
        "total_experiments":        len(all_results),
        "successful_experiments":   sum(1 for r in all_results if r.get("successful", 0) > 0),
        "skipped_experiments":      skipped,
        "total_runtime_seconds":    runtime,
        "experiments":              all_results,
    }

    run_log_path = run_root_dir / "run_log.json"
    run_log_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Update global tracking file
    summary_path = Path(EXPERIMENT_SUMMARY_PATH)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n" + "=" * 80)
    print("🎉 ALL EXPERIMENTS COMPLETED  (GT sequence workflow)")
    print("=" * 80)
    print(f"Total Experiments: {summary['total_experiments']}")
    print(f"Successful:        {summary['successful_experiments']}")
    if skipped:
        print(f"Skipped (exists):  {skipped}")
    print(f"Runtime:           {runtime:.1f}s")
    print(f"Run Log:           {run_log_path}")
    print("=" * 80)

    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run APA experiments with GT-structured assembly sequences"
    )
    parser.add_argument(
        "experiment",
        nargs="?",
        help="Experiment YAML file, or 'all' to run all experiments"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(LLM_OUTPUT_FOLDER),
        help="Fixed output folder (skips auto-timestamped subfolder). Runs already present are skipped.",
    )
    args = parser.parse_args()

    if args.experiment and args.experiment.lower() != "all":
        exp_yaml = Path(args.experiment)
        if not exp_yaml.exists():
            exp_yaml = Path(EXPERIMENT_CONFIG_FOLDER) / args.experiment
            if not exp_yaml.suffix:
                exp_yaml = exp_yaml.with_suffix(".yaml")
        if exp_yaml.exists():
            try:
                _cfg = WorkflowConfig.from_yaml(exp_yaml)
                repetitions = int(getattr(_cfg, "repetitions", 1))
            except Exception:
                repetitions = 1
            
            # Determine output directory for skip check
            output_dir_for_check = args.output_dir if args.output_dir else Path(LLM_OUTPUT_FOLDER)
            
            for rep_id in range(1, repetitions + 1):
                effective_rep_id = rep_id if repetitions > 1 else None
                
                # Skip if run already exists
                if _experiment_run_exists(output_dir_for_check, exp_yaml.stem, effective_rep_id):
                    rep_label = f"{exp_yaml.stem}_run{rep_id}" if repetitions > 1 else exp_yaml.stem
                    print(f"   ⏭  Repetition {rep_id}/{repetitions}: {rep_label}  ← bereits vorhanden, wird übersprungen")
                    continue
                
                print(f"▶ Repetition {rep_id}/{repetitions}")
                run_single_experiment(
                    exp_yaml,
                    rep_id=effective_rep_id,
                    checkpoint_root=None,  # no shared root for CLI single-run
                    run_root_dir=args.output_dir,
                )
        else:
            print(f"❌ Experiment not found: {args.experiment}")
            sys.exit(1)
    else:
        run_all_experiments(output_dir=args.output_dir)
