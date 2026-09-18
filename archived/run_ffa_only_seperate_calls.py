"""
Run FFA Assessment (Separate Calls) – aligned with run_ffa_only_experiments.py.

This runner keeps the same experiment/repetition/config orchestration as
run_ffa_only_experiments.py, but executes the dedicated split-calls path:
one LLM call each for Separation, Handling, Positioning, Joining.

Usage:
    python run_ffa_only_seperate_calls.py --checkpoint <path> --config-source <source>
    python run_ffa_only_seperate_calls.py \
        --checkpoint data/checkpoints/2026-03-03_133817-4o/exp_baseline_seq_gt_run1 \
        --config-source sequence_gt

Configuration:
    - Auto-discovers experiments from configs/{config_source}/
    - Loads settings (FFA_parallel, FFA_max_workers, etc.) from experiment YAML
    - Handles repetitions as defined in config (e.g., repetitions: 2)
    - Sets APA_EXPERIMENT_YAML for proper LLM model detection
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from agent.config_utils import load_experiment_config, discover_experiments
from agent.FFA_assessment import assess_assembly_sequence_ffa_separate_calls
from agent.checkpoint_utils import validate_checkpoint
from run_name_utils import get_run_name

# ============================================================================
# SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _ffa_run_exists(run_dir: Path, prefix: str, exp_name: str, rep_id: int) -> bool:
    """Return True if a completed FFA-run folder for this exp+rep already exists."""
    if not run_dir.exists():
        return False
    suffix = f"_{prefix}_{exp_name}_run{rep_id}"
    for candidate in run_dir.iterdir():
        if not candidate.is_dir():
            continue
        if not candidate.name.endswith(suffix):
            continue
        # Verify at least one completed assembly
        for asm_dir in candidate.iterdir():
            if not asm_dir.is_dir():
                continue
            ffa_file = asm_dir / "ffa_assessment" / "ffa_assessment.json"
            if ffa_file.exists():
                return True
    return False


def run_ffa_separate_calls(
    checkpoint_path: str,
    experiments_to_run: List[str],
    run_root_dir: Path,
    config_source: str = "sequence_gt",
    output_dir: Optional[Path] = None,
    experiment_name_prefix: str = "ffa_separate_calls",
) -> Dict[str, Any]:
    """
    Run FFA assessment with separate calls across multiple experiments.

    Args:
        checkpoint_path: Path to checkpoint
        experiments_to_run: List of experiment names (empty = auto-discover)
        run_root_dir: Base directory for results
        config_source: Config folder to use ("sequence_gt" or "ffa_only")
        output_dir: Fixed output folder; if None, creates timestamped subfolder
        experiment_name_prefix: Prefix for run folder names

    Returns:
        Summary dict with results
    """
    start_time = time.time()
    workspace_root = Path(__file__).resolve().parent
    checkpoint_path = Path(checkpoint_path)
    run_root_dir = Path(run_root_dir)

    # Make paths absolute
    if not checkpoint_path.is_absolute():
        checkpoint_path = workspace_root / checkpoint_path
    if not run_root_dir.is_absolute():
        run_root_dir = workspace_root / run_root_dir

    # Create timestamped run directory
    run_timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    run_name = get_run_name()
    
    if output_dir is not None:
        run_dir = Path(output_dir)
        if not run_dir.is_absolute():
            run_dir = workspace_root / run_dir
        logger.info(f"📁 Output directory (fixed): {run_dir}")
        if run_dir.exists():
            existing = [
                d.name for d in run_dir.iterdir()
                if d.is_dir() and not d.name.startswith("_") and d.name != "evaluation"
            ]
            if existing:
                logger.info(f"   Already in target folder ({len(existing)} folder(s)):")
                for e in sorted(existing):
                    logger.info(f"     - {e}")
    else:
        run_dir = run_root_dir / f"run_{run_timestamp}_{run_name}_{experiment_name_prefix}"
    
    run_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"\n{'='*80}")
    logger.info(f"FFA ASSESSMENT (SEPARATE CALLS)")
    logger.info(f"{'='*80}")
    logger.info(f"Checkpoint: {checkpoint_path.relative_to(workspace_root)}")
    logger.info(f"Run name:   {run_name}")
    logger.info(f"Run dir:    {run_dir.relative_to(workspace_root)}")

    # Validate checkpoint
    is_valid, errors = validate_checkpoint(str(checkpoint_path))
    if not is_valid:
        logger.error(f"❌ Invalid checkpoint: {errors}")
        return {
            "success": False,
            "error": "Checkpoint validation failed",
            "experiments_processed": 0,
            "experiments_successful": 0,
            "experiments_failed": 0
        }

    # Auto-discover experiments if not specified
    if not experiments_to_run:
        logger.info(f"Auto-discovering experiments from configs/{config_source}/...")
        experiments_to_run = discover_experiments(config_source, config_base_path=Path("configs"))
        if not experiments_to_run:
            logger.error(f"❌ No experiments found in configs/{config_source}/")
            return {
                "success": False,
                "error": "No experiments found",
                "experiments_processed": 0,
                "experiments_successful": 0,
                "experiments_failed": 0
            }

    logger.info(f"✓ Found {len(experiments_to_run)} experiments: {', '.join(experiments_to_run)}")

    # Summary tracking
    experiments_processed = 0
    experiments_successful = 0
    experiments_failed = 0
    experiment_results = {}

    # Process each experiment
    for exp_name in experiments_to_run:
        logger.info(f"\n{'─'*80}")
        logger.info(f"Processing experiment: {exp_name}")
        logger.info(f"{'─'*80}")

        try:
            # Load experiment config
            try:
                exp_config = load_experiment_config(
                    exp_name,
                    config_source,
                    config_base_path=Path("configs")
                )
                logger.info(f"✓ Loaded config for {exp_name}")
            except FileNotFoundError as e:
                logger.error(f"❌ Failed to load config: {e}")
                raise

            # Read repetitions from config
            repetitions = int(exp_config.get("repetitions", 1))
            logger.info(f"✓ Repetitions for {exp_name}: {repetitions}")

            experiment_results[exp_name] = {}

            # Process each repetition
            for rep_id in range(1, repetitions + 1):
                rep_label = f"{exp_name}_run{rep_id}"
                logger.info(f"\n  ▶ Repetition {rep_id}/{repetitions}: {rep_label}")

                try:
                    # Create FFA experiment name
                    ffa_exp_name = f"{run_name}_{experiment_name_prefix}_{rep_label}"

                    # Skip check: if run already exists, skip it
                    if _ffa_run_exists(run_dir, experiment_name_prefix, exp_name, rep_id):
                        logger.info(f"  ⏭  {rep_label} already exists, skipping")
                        experiments_processed += 1
                        experiment_results[exp_name][rep_label] = {
                            "status": "skipped",
                            "reason": "already_exists"
                        }
                        continue

                    # Set environment variable so tools.py picks up correct LLM model
                    exp_yaml_path = Path("configs") / config_source / f"{exp_name}.yaml"
                    os.environ["APA_EXPERIMENT_YAML"] = str(exp_yaml_path)
                    logger.info(f"  APA_EXPERIMENT_YAML set to: {exp_yaml_path}")

                    # Run split-calls path: 4 separate LLM calls per step
                    result = assess_assembly_sequence_ffa_separate_calls(
                        checkpoint_path=str(checkpoint_path),
                        run_root_dir=str(run_dir),
                        experiment_name=ffa_exp_name,
                        assemblies_to_process=None,
                        settings=exp_config,
                    )

                    experiments_processed += 1

                    # Check result
                    if result.get("successful", 0) > 0:
                        experiments_successful += 1
                        logger.info(f"  ✓ Rep {rep_id} completed: {result['successful']}/{result['processed']} assemblies successful")
                    else:
                        experiments_failed += 1
                        logger.error(f"  ❌ Rep {rep_id} failed: 0/{result['processed']} assemblies successful")

                    experiment_results[exp_name][rep_label] = result

                except Exception as e:
                    experiments_processed += 1
                    experiments_failed += 1
                    logger.error(f"  ❌ Error in repetition {rep_id} of {exp_name}: {e}", exc_info=True)
                    experiment_results[exp_name][rep_label] = {
                        "success": False,
                        "error": str(e),
                        "processed": 0,
                        "successful": 0,
                        "failed": 0
                    }

        except Exception as e:
            experiments_processed += 1
            experiments_failed += 1
            logger.error(f"❌ Error processing experiment {exp_name}: {e}", exc_info=True)
            experiment_results[exp_name] = {
                "success": False,
                "error": str(e),
                "processed": 0,
                "successful": 0,
                "failed": 0
            }

    runtime = time.time() - start_time

    # Final summary
    skipped = sum(
        1 for exp_res in experiment_results.values()
        for rep_res in (exp_res.values() if isinstance(exp_res, dict) else [exp_res])
        if isinstance(rep_res, dict) and rep_res.get("status") == "skipped"
    )

    logger.info(f"\n{'='*80}")
    logger.info(f"FFA ASSESSMENT (SEPARATE CALLS) COMPLETE")
    logger.info(f"{'='*80}")
    logger.info(f"Processed:   {experiments_processed}")
    logger.info(f"Successful:  {experiments_successful}")
    logger.info(f"Failed:      {experiments_failed}")
    logger.info(f"Skipped:     {skipped}")
    logger.info(f"Runtime:     {runtime:.1f}s")
    logger.info(f"{'='*80}\n")

    return {
        "success": experiments_failed == 0,
        "experiments_processed": experiments_processed,
        "experiments_successful": experiments_successful,
        "experiments_failed": experiments_failed,
        "experiments_skipped": skipped,
        "run_dir": str(run_dir),
        "timestamp": datetime.now().isoformat(),
        "details": experiment_results,
    }


# ============================================================================
# MAIN
# ============================================================================

def main():
    """CLI entry point for FFA separate-calls workflow."""
    parser = argparse.ArgumentParser(
        description="Run FFA Assessment with separate LLM calls across experiments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_ffa_only_seperate_calls.py \\
    --checkpoint data/checkpoints/2026-03-03_133817 -4o/exp_baseline_seq_gt_run1

  python run_ffa_only_seperate_calls.py \\
    --checkpoint data/checkpoints/latest/ \\
    --experiments exp_baseline_seq_gt_41 exp_baseline_seq_gt_54

  python run_ffa_only_seperate_calls.py \\
    --checkpoint data/checkpoints/latest/ \\
    --config-source ffa_only \\
    --output-dir data/experiments/my_ffa_run

Environment:
  - Loads LLM credentials from .env
  - Loads experiment configs from configs/{config-source}/
        """
    )
    
    parser.add_argument(
        "--checkpoint",
        type=str,
        required=True,
        help="Path to checkpoint directory"
    )
    
    parser.add_argument(
        "--experiments",
        type=str,
        nargs="*",
        default=[],
        help="Experiment name(s) to process. If not provided, auto-discovers from config folder"
    )
    
    parser.add_argument(
        "--config-source",
        type=str,
        default="sequence_gt",
        choices=["sequence_gt", "ffa_only"],
        help="Config folder to use (default: sequence_gt)"
    )
    
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Fixed output directory. If not provided, creates timestamped subfolder in --run-root-dir"
    )
    
    parser.add_argument(
        "--run-root-dir",
        type=str,
        default="data/experiments",
        help="Base directory for timestamped runs (default: data/experiments)"
    )

    args = parser.parse_args()
    
    # Run the workflow
    result = run_ffa_separate_calls(
        checkpoint_path=args.checkpoint,
        experiments_to_run=args.experiments,
        run_root_dir=Path(args.run_root_dir),
        config_source=args.config_source,
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )
    
    # Exit code based on result
    if result.get("success"):
        logger.info("✓ All experiments processed successfully")
        sys.exit(0)
    else:
        if result.get("error"):
            logger.error(f"❌ Workflow failed: {result['error']}")
        logger.error("❌ Workflow completed with errors")
        sys.exit(1)


if __name__ == "__main__":
    main()
