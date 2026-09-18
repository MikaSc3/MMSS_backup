"""
Experiment Runner für APA_from_CAD.

Führt automatisch alle Experimente aus configs/experiments/ aus.
Schreibt Outputs in data/experiments/run_{timestamp}/{exp_name}/
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Union
from datetime import datetime

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from agent.config import WorkflowConfig
from agent.workflow import run_all_nodes, run_assess_ffa_only
from agent.checkpoint_utils import load_checkpoint_assemblies, validate_checkpoint
from agent.config_utils import load_experiment_config, discover_experiments as discover_experiments_from_config
from run_name_utils import get_run_name


# ============================================================================
# STEUERUNG: Welche Assemblies sollen verarbeitet werden?
# ============================================================================
# Optionen:
#   "all"  -> Alle Assemblies aus data/processed/stepparser/
#   ["IPA_Cranfield", "Gearbox"]  -> Nur diese spezifischen Assemblies
#   None   -> Verwendet step_files aus den YAML-Dateien
# ============================================================================
STEP_FILES_OVERRIDE: Optional[Union[str, List[str]]] = "all"
# ============================================================================


def discover_experiments(experiments_dir: Path = Path("configs/experiments")) -> List[Path]:
    """Finde alle Experiment-YAML-Dateien.
    
    Priority:
    1. configs/full_workflow/ (neu)
    2. configs/experiments/ (alt, fallback)
    
    Args:
        experiments_dir: Ordner mit Experiment-YAMLs (fallback)
        
    Returns:
        Liste von Pfaden zu Experiment-YAMLs
    """
    # Try new structure first
    full_workflow_dir = Path("configs/full_workflow")
    if full_workflow_dir.exists():
        yaml_files = sorted(full_workflow_dir.glob("*.yaml"))
        if yaml_files:
            return yaml_files
    
    # Fallback to old structure
    if not experiments_dir.exists():
        return []
    
    yaml_files = sorted(experiments_dir.glob("*.yaml"))
    # Filter exp_example.yaml aus
    yaml_files = [f for f in yaml_files if f.name != "exp_example.yaml"]
    return yaml_files


def run_single_experiment(
    experiment_yaml: Path,
    stepparser_root: Path = Path("data/processed/stepparser"),
    run_root_dir: Path = None,
    run_name: str = "",
) -> Dict:
    """Führe ein einzelnes Experiment aus.
    
    Args:
        experiment_yaml: Pfad zum Experiment-YAML
        stepparser_root: Root-Ordner mit stepparser outputs
        run_root_dir: Optional - Root-Ordner für diesen Run (run_{timestamp}/)
        
    Returns:
        Dict mit Experiment-Results
    """
    print("=" * 80)
    print(f"EXPERIMENT: {experiment_yaml.name}")
    print("=" * 80)
    
    # Set environment variable for run_root_dir if provided
    if run_root_dir is not None:
        os.environ["APA_EXPERIMENT_OUTPUT_DIR"] = str(run_root_dir)
    
    # Load experiment config
    config = WorkflowConfig.from_yaml(experiment_yaml)
    
    # Use YAML filename as experiment_name if not specified (instead of "default")
    if config.experiment_name == "default":
        config.experiment_name = experiment_yaml.stem  # exp1_baseline.yaml -> exp1_baseline

    # Prefix with run name for identification
    if run_name:
        config.experiment_name = f"{run_name}_{config.experiment_name}"
    
    # Set environment variable for experiment YAML (needed for load_experiment_settings)
    os.environ["APA_EXPERIMENT_YAML"] = str(experiment_yaml)
    
    # Override experiment_output_root if run_root_dir provided
    # (by creating a new nested experiment name path)
    if run_root_dir is not None:
        nested_output_root = run_root_dir / config.experiment_name
    else:
        nested_output_root = config.experiment_output_root
    
    print(f"Experiment Name: {config.experiment_name}")
    print(f"Description: {getattr(config, 'description', 'N/A')}")
    print(f"Output Root: {nested_output_root}")
    print(f"Prompts: {config.prompt_id_assy}, {config.prompt_id_monopart}")
    
    # Log Assembly Sequence Settings
    print(f"\n🔧 Assembly Sequence Settings:")
    enable_asm_seq = getattr(config, 'enable_assembly_sequence', True)
    enable_val_seq = getattr(config, 'enable_sequence_validation', False)
    print(f"   enable_assembly_sequence: {enable_asm_seq}")
    print(f"   enable_sequence_validation: {enable_val_seq}")
    if enable_asm_seq:
        asm_img_kw = getattr(config, 'assembly_sequence_image_keywords', ["exploded", "isometric"])
        asm_json_kw = getattr(config, 'assembly_sequence_json_keywords', ["merged_bom"])
        print(f"   image_keywords: {asm_img_kw}")
        print(f"   json_keywords: {asm_json_kw}")
    if enable_val_seq:
        val_img_kw = getattr(config, 'ASV_step_img_keywords', ["isometric"])
        val_json_kw = getattr(config, 'ASV_json_keywords', ["merged_bom"])
        val_assy_kw = getattr(config, 'ASV_finished_assy_keywords', ["isometric"])
        print(f"   ASV_step_img_keywords: {val_img_kw}")
        print(f"   ASV_json_keywords: {val_json_kw}")
        print(f"   ASV_finished_assy_keywords: {val_assy_kw}")
    
    # Log FFA Settings
    print(f"\n🔧 FFA Assessment Settings:")
    ffa_mode = getattr(config, 'FFA_mode', 'disabled')
    print(f"   FFA_mode: {ffa_mode}")
    if ffa_mode != 'disabled':
        ffa_step_kw = getattr(config, 'FFA_step_img_keywords', ["iso1_transp_0_0"])
        ffa_prior_kw = getattr(config, 'FFA_prior_step_img_keywords', ["iso1_transp_0_0"])
        ffa_downscale = getattr(config, 'FFA_image_downscale', 0.5)
        print(f"   FFA_step_img_keywords: {ffa_step_kw}")
        print(f"   FFA_prior_step_img_keywords: {ffa_prior_kw}")
        print(f"   FFA_image_downscale: {ffa_downscale}")
    
    print()
    
    # Auto-discover all assemblies from stepparser (no step_files in YAML anymore)
    print("🔍 Auto-discovering all assemblies from stepparser...")
    if not stepparser_root.exists():
        print(f"⚠️  Stepparser root not found: {stepparser_root}")
        return {"status": "skipped", "reason": "stepparser_root_not_found"}
    
    # Find all directories in stepparser root
    step_files = sorted([
        d.name for d in stepparser_root.iterdir() 
        if d.is_dir() and not d.name.startswith("_")
    ])
    
    if not step_files:
        print("⚠️  No assemblies found in stepparser root")
        return {"status": "skipped", "reason": "no_assemblies_found"}
    
    print(f"   Found {len(step_files)} assemblies: {step_files}")
    
    results = []
    
    for step_name in step_files:
        # Construct datasource path (stepparser output)
        datasource_root = stepparser_root / step_name
        
        if not datasource_root.exists():
            print(f"⚠️  Datasource not found: {datasource_root}, skipping")
            continue
        
        print(f"\n📦 Processing: {step_name}")
        print(f"   Source: {datasource_root}")
        
        # Create experiment output directory
        # Use nested_output_root if run_root_dir was provided, otherwise use config.experiment_output_root
        experiment_output_dir = nested_output_root / step_name
        experiment_output_dir.mkdir(parents=True, exist_ok=True)
        print(f"   Output: {experiment_output_dir}")
        
        # Set environment variable for output routing
        os.environ["APA_EXPERIMENT_OUTPUT_DIR"] = str(experiment_output_dir)
        os.environ["APA_EXPERIMENT_NAME"] = config.experiment_name
        
        try:
            # Run enrichment
            result = run_all_nodes(
                datasource_root=str(datasource_root),
                use_unique_parts=config.use_unique_parts,
                workflow_print=config.workflow_print,
                parallel=getattr(config, 'parallel', False),
                max_workers=getattr(config, 'max_workers', 4),
                assembly_keywords=config.img_to_analyse_assy,
                assembly_limit=getattr(config, 'assembly_limit', 8),
                part_keywords=config.img_to_analyse_monopart,
                part_limit=getattr(config, 'part_limit', 8),
            )
            
            # Save experiment-specific summary with token tracking
            summary = {
                "experiment_name": config.experiment_name,
                "step_file": step_name,
                "status": "success",
                "assembly_written": result.get("assembly_result", {}).get("metadata_written_path"),
                "parts_count": len(result.get("part_results", [])),
                "runtime_seconds": result.get("runtime_seconds", 0),
                "token_usage": result.get("token_usage_total", {}),
                "warnings": result.get("warnings", []),
                # ⭐ NEW: Assembly Sequence Results
                "assembly_sequence": {
                    "enabled": getattr(config, 'enable_assembly_sequence', True),
                    "path": result.get("assembly_sequence_path"),
                    "image_keywords": getattr(config, 'assembly_sequence_image_keywords', ["exploded", "isometric"]),
                    "json_keywords": getattr(config, 'assembly_sequence_json_keywords', ["merged_bom"]),
                },
                "assembly_sequence_validation": {
                    "enabled": getattr(config, 'enable_sequence_validation', False),
                    "path": result.get("assembly_sequence_validation_path"),
                    "step_img_keywords": getattr(config, 'ASV_step_img_keywords', ["isometric"]),
                    "json_keywords": getattr(config, 'ASV_json_keywords', ["merged_bom"]),
                },
                # ⭐ NEW: FFA Assessment Results
                "ffa_assessment": {
                    "enabled": getattr(config, 'FFA_mode', 'disabled') != 'disabled',
                    "mode": getattr(config, 'FFA_mode', 'disabled'),
                    "path": result.get("ffa_assessment_path"),
                    "step_img_keywords": getattr(config, 'FFA_step_img_keywords', ["iso1_transp_0_0"]),
                    "prior_step_img_keywords": getattr(config, 'FFA_prior_step_img_keywords', ["iso1_transp_0_0"]),
                },
            }
            
            summary_path = experiment_output_dir / "experiment_summary.json"
            summary_path.write_text(
                json.dumps(summary, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            
            results.append(summary)
            
            # Print detailed success message
            ffa_status = "✓" if summary['ffa_assessment']['path'] else "✗"
            print(f"   ✅ Success: {summary['parts_count']} parts processed")
            print(f"      Assembly Sequence: {summary['assembly_sequence']['path'] or 'N/A'}")
            print(f"      FFA Assessment: {ffa_status} {summary['ffa_assessment']['path'] or 'Not generated'}")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            results.append({
                "experiment_name": config.experiment_name,
                "step_file": step_name,
                "status": "error",
                "error": str(e),
            })
    
    print()
    print(f"✅ Experiment {config.experiment_name} completed: {len(results)} assemblies processed")
    print("=" * 80)
    print()
    
    return {
        "experiment_name": config.experiment_name,
        "experiment_yaml": str(experiment_yaml),
        "config": config.model_dump(),
        "results": results,
        "total_assemblies": len(results),
        "successful": sum(1 for r in results if r.get("status") == "success"),
    }


def run_all_experiments(
    experiments_dir: Path = Path("configs/experiments"),
    stepparser_root: Path = Path("data/processed/stepparser"),
) -> Dict:
    """Führe alle Experimente aus in einem timestamped Run-Ordner.
    
    Erstellt Struktur: data/experiments/run_{TIMESTAMP}/
                       ├── run_log.json (alle Logs des Runs)
                       ├── exp1_baseline/
                       │   ├── assembly1/
                       │   └── assembly2/
                       └── exp2/
                           └── assembly/
    
    Args:
        experiments_dir: Ordner mit Experiment-YAMLs
        stepparser_root: Root-Ordner mit stepparser outputs
        
    Returns:
        Dict mit Summary aller Experimente
    """
    start_time = time.time()
    
    # Create timestamped run directory
    run_timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    run_name = get_run_name()
    run_root_dir = Path("data/experiments") / f"run_{run_timestamp}_{run_name}"
    run_root_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"📁 Run name:               {run_name}")
    print(f"📁 Running experiments in: {run_root_dir}")
    print()
    
    # Discover experiments
    experiments = discover_experiments(experiments_dir)
    
    if not experiments:
        print(f"⚠️  No experiments found in {experiments_dir}")
        return {"status": "no_experiments"}
    
    print(f"🔬 Found {len(experiments)} experiments:")
    for exp in experiments:
        print(f"   - {exp.name}")
    print()
    
    # Run each experiment
    all_results = []
    for exp_yaml in experiments:
        try:
            result = run_single_experiment(exp_yaml, stepparser_root, run_root_dir, run_name=run_name)
            all_results.append(result)
        except Exception as e:
            print(f"❌ Experiment {exp_yaml.name} failed: {e}")
            all_results.append({
                "experiment_name": exp_yaml.stem,
                "experiment_yaml": str(exp_yaml),
                "status": "failed",
                "error": str(e),
            })
    
    runtime = time.time() - start_time
    
    # Summary
    summary = {
        "run_timestamp": run_timestamp,
        "run_root_dir": str(run_root_dir),
        "total_experiments": len(all_results),
        "successful_experiments": sum(1 for r in all_results if r.get("successful", 0) > 0),
        "total_runtime_seconds": runtime,
        "experiments": all_results,
    }
    
    # Save run log in run directory
    run_log_path = run_root_dir / "run_log.json"
    run_log_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    
    # Also save to global experiments summary for tracking (legacy)
    summary_path = Path("data/experiments/experiments_summary.json")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    
    print("\n" + "=" * 80)
    print("🎉 ALL EXPERIMENTS COMPLETED")
    print("=" * 80)
    print(f"Total Experiments: {summary['total_experiments']}")
    print(f"Successful: {summary['successful_experiments']}")
    print(f"Runtime: {runtime:.1f}s")
    print(f"Run Log: {run_log_path}")
    print(f"Global Summary: {summary_path}")
    print("=" * 80)
    
    return summary


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Run APA experiments or FFA assessment from checkpoint"
    )
    parser.add_argument(
        "experiment",
        nargs="?",
        help="Experiment YAML file (for full workflow) or 'all' to run all experiments"
    )
    parser.add_argument(
        "--ffa-only",
        action="store_true",
        help="Run only FFA assessment from existing checkpoint (requires --checkpoint-path)"
    )
    parser.add_argument(
        "--checkpoint-path",
        type=str,
        help="Path to checkpoint (e.g., data/checkpoints/20260213_153000/)"
    )
    parser.add_argument(
        "--ffa-setting-overrides",
        type=str,
        help='JSON string with FFA setting overrides (e.g., \'{"FFA_mode": "enabled"}\')'
    )
    parser.add_argument(
        "--ffa-experiment-name",
        type=str,
        default="ffa_only",
        help='Name for FFA experiment directory (default: "ffa_only"). Used in run structure.'
    )
    
    args = parser.parse_args()
    
    # Phase 5: FFA-only mode
    if args.ffa_only:
        print("\n" + "=" * 80)
        print("FFA-ONLY ASSESSMENT MODE")
        print("=" * 80)
        
        # Validate checkpoint-path is provided
        if not args.checkpoint_path:
            print("❌ ERROR: --ffa-only requires --checkpoint-path")
            print("   Usage: python scripts/run_experiments.py --ffa-only --checkpoint-path data/checkpoints/20260213_153000/")
            sys.exit(1)
        
        checkpoint_path = Path(args.checkpoint_path)
        
        # Validate checkpoint exists
        if not checkpoint_path.exists():
            print(f"❌ ERROR: Checkpoint path does not exist: {checkpoint_path}")
            sys.exit(1)
        
        # Validate checkpoint structure
        is_valid, errors = validate_checkpoint(str(checkpoint_path))
        if not is_valid:
            print(f"❌ ERROR: Checkpoint validation failed:")
            for error in errors:
                print(f"   - {error}")
            sys.exit(1)
        
        # Load and display checkpoint info
        assemblies = load_checkpoint_assemblies(str(checkpoint_path))
        print(f"\n✓ Checkpoint valid: {checkpoint_path}")
        print(f"✓ Assemblies found: {len(assemblies)} ({', '.join(assemblies)})")
        
        # Parse FFA setting overrides if provided
        ffa_overrides = None
        if args.ffa_setting_overrides:
            try:
                ffa_overrides = json.loads(args.ffa_setting_overrides)
                print(f"✓ FFA setting overrides: {ffa_overrides}")
            except json.JSONDecodeError as e:
                print(f"❌ ERROR: Invalid JSON in --ffa-setting-overrides: {e}")
                sys.exit(1)
        
        print("\n✓ Ready to process")
        print("=" * 80 + "\n")
        
        # Run FFA assessment from checkpoint
        try:
            result = run_assess_ffa_only(
                checkpoint_path=str(checkpoint_path),
                ffa_settings_overrides=ffa_overrides,
                experiment_name=args.ffa_experiment_name,
            )
            
            # Print results
            print("\n" + "=" * 80)
            print("FFA-ONLY ASSESSMENT COMPLETE")
            print("=" * 80)
            print(f"Processed: {result['processed']}")
            print(f"Successful: {result['successful']}")
            print(f"Failed: {result['failed']}")
            
            if result['failed'] > 0:
                print("\nFailures:")
                for detail in result['details']:
                    if isinstance(detail, str):
                        print(f"  - {detail}")
            
            print("=" * 80)
            
            sys.exit(0 if result['failed'] == 0 else 1)
        
        except Exception as e:
            print(f"❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    # Standard workflow mode (full experiments)
    else:
        if args.experiment and args.experiment.lower() == "all":
            # Run all experiments
            run_all_experiments()
        elif args.experiment:
            # Run specific experiment
            exp_yaml = Path(args.experiment)
            if not exp_yaml.exists():
                exp_yaml = Path("configs/experiments") / args.experiment
                if not exp_yaml.suffix:
                    exp_yaml = exp_yaml.with_suffix(".yaml")
            
            if exp_yaml.exists():
                run_single_experiment(exp_yaml)
            else:
                print(f"❌ Experiment not found: {args.experiment}")
                sys.exit(1)
        else:
            # Run all experiments if no argument provided
            run_all_experiments()
