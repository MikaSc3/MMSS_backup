#!/usr/bin/env python3
"""
Consolidate FFA Reports from Experiments

Workflow orchestration script that:
1. Task 1 (ffa_reporter): Generate per-run FFA reports from FFA assessments
2. Task 2 (ffa_aggregator): Aggregate per-run reports into assembly-level consolidated reports

Usage:
    python consolidate_ffa_reports_from_experiments.py \\
        --base-dir data/experiments/_Full_Workflow_Modelcomparison \\
        --output-dir outputs/ffa_consolidated \\
        --keyword "GPT-4o" \\
        --run-task1 \\
        --run-task2

Or use defaults:
    python consolidate_ffa_reports_from_experiments.py
"""

import argparse
import logging
import json
import sys
from pathlib import Path
from typing import Optional, Dict, List

import yaml
from langchain_openai import ChatOpenAI

from evaluation.ffa_reporter import ffa_reporter
from evaluation.ffa_aggregator import ffa_aggregator
from config_utils import setup_logging


# ============================================================================
# Configuration Defaults
# ============================================================================

DEFAULT_BASE_DIR = Path("data/experiments/FfA_Reporter")
DEFAULT_OUTPUT_DIR = Path("data/ffa_consolidated")
DEFAULT_KEYWORD = "GPT-4o"
DEFAULT_DATASET_KEY = "eval"
DEFAULT_DELETE_KEYS = ["image_paths", "images"]
DEFAULT_PROMPTS_FILE = Path("configs/prompts.yaml")


# ============================================================================
# Prompt Loading
# ============================================================================

def load_prompts(prompts_file: Path) -> Dict[str, str]:
    """
    Load prompts from YAML configuration file.
    
    Args:
        prompts_file: Path to prompts.yaml
        
    Returns:
        Dict with unified reporter prompt pair used by workflow and consolidation
        
    Raises:
        FileNotFoundError: If prompts file not found
        KeyError: If required prompts not in file
    """
    if not prompts_file.exists():
        raise FileNotFoundError(f"Prompts file not found: {prompts_file}")
    
    with open(prompts_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    prompts = config.get('prompts', {})
    
    # Use the same prompt pair as the workflow node to keep one single source of truth.
    system_prompt = prompts.get('ffa_reporter_workflow_system_prompt', {}).get('text')
    human_template = prompts.get('ffa_reporter_workflow_human_message_template', {}).get('text')
    
    if not system_prompt:
        raise KeyError("ffa_reporter_workflow_system_prompt not found in prompts.yaml")
    if not human_template:
        raise KeyError("ffa_reporter_workflow_human_message_template not found in prompts.yaml")
    
    return {
        'system_prompt': system_prompt,
        'human_template': human_template
    }


# ============================================================================
# LLM Initialization
# ============================================================================

def initialize_llm(model: str = "gpt-4o") -> ChatOpenAI:
    """
    Initialize LLM instance.
    
    Args:
        model: Model name (default: gpt-4o)
        
    Returns:
        Initialized ChatOpenAI instance
    """
    logging.info(f"Initializing LLM: {model}")
    
    llm = ChatOpenAI(
        model=model,
        temperature=0.2,  # Low temperature for consistent extraction
        max_tokens=2000
    )
    
    return llm


# ============================================================================
# Task 1: FFA Reporter
# ============================================================================

def run_task1_ffa_reporter(
    base_dir: Path,
    output_dir: Path,
    keyword: str,
    dataset_key: str,
    delete_keys: List[str],
    prompts: Dict[str, str],
    llm,
    logger: logging.Logger
) -> bool:
    """
    Run Task 1: Generate per-run FFA reports.
    
    Args:
        base_dir: Base experiment directory
        output_dir: Output directory
        keyword: Keyword to filter runs
        dataset_key: Dataset key (eval/test)
        delete_keys: Keys to delete from FFA assessment
        prompts: Prompt dictionary
        llm: LLM instance
        logger: Logger instance
        
    Returns:
        True if successful, False otherwise
    """
    logger.info("=" * 80)
    logger.info("TASK 1: FFA Reporter (Generate Per-Run Reports)")
    logger.info("=" * 80)
    
    logger.info(f"Configuration:")
    logger.info(f"  Base Directory: {base_dir}")
    logger.info(f"  Output Directory: {output_dir}")
    logger.info(f"  Keyword Filter: {keyword}")
    logger.info(f"  Dataset Key: {dataset_key}")
    logger.info(f"  Delete Keys: {delete_keys}")
    
    try:
        results = ffa_reporter(
            base_experiment_dir=base_dir,
            keyword=keyword,
            delete_keys=delete_keys,
            llm=llm,
            system_prompt=prompts['system_prompt'],
            human_template=prompts['human_template'],
            dataset_key=dataset_key,
            output_dir=output_dir
        )
        
        # Summary
        total_reports = sum(len(runs) for runs in results.values())
        logger.info("")
        logger.info(f"✓ TASK 1 COMPLETE")
        logger.info(f"  Generated {total_reports} per-run reports")
        logger.info(f"  Saved to: {output_dir}")
        logger.info("")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ TASK 1 FAILED: {e}", exc_info=True)
        return False


# ============================================================================
# Task 2: FFA Aggregator
# ============================================================================

def run_task2_ffa_aggregator(
    task1_output_dir: Path,
    logger: logging.Logger
) -> bool:
    """
    Run Task 2: Aggregate per-run reports into assembly-level reports.
    
    Args:
        task1_output_dir: Task 1 output directory (contains per-assembly subdirs)
        logger: Logger instance
        
    Returns:
        True if successful, False otherwise
    """
    logger.info("=" * 80)
    logger.info("TASK 2: FFA Aggregator (Consolidate to Assembly-Level)")
    logger.info("=" * 80)
    
    logger.info(f"Configuration:")
    logger.info(f"  Task 1 Output Directory: {task1_output_dir}")
    logger.info(f"  Target Directory (FINAL_REPORTS): {task1_output_dir}/FINAL_REPORTS")
    
    try:
        results = ffa_aggregator(
            task1_output_dir=task1_output_dir,
            output_dir=task1_output_dir
        )
        
        # Summary
        logger.info("")
        logger.info(f"✓ TASK 2 COMPLETE")
        logger.info(f"  Consolidated {len(results)} assemblies")
        logger.info(f"  Saved to: {task1_output_dir}/FINAL_REPORTS/")
        logger.info("")
        
        # List output files
        final_reports_dir = task1_output_dir / "FINAL_REPORTS"
        if final_reports_dir.exists():
            reports = list(final_reports_dir.glob("*.json"))
            logger.info(f"  Generated files:")
            for report in sorted(reports):
                logger.info(f"    - {report.name}")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ TASK 2 FAILED: {e}", exc_info=True)
        return False


# ============================================================================
# Main Workflow
# ============================================================================

def main():
    """Main entry point."""
    
    # ========================================================================
    # Argument Parsing
    # ========================================================================
    
    parser = argparse.ArgumentParser(
        description="Consolidate FFA Reports: Task 1 (per-run) + Task 2 (assembly-level)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:

  # Run both tasks with defaults
  python consolidate_ffa_reports_from_experiments.py

  # Custom directories and keyword
  python consolidate_ffa_reports_from_experiments.py \\
    --base-dir data/experiments/custom_run \\
    --output-dir outputs/my_ffa_reports \\
    --keyword "GPT-5"

  # Run only Task 1 (skip aggregation)
  python consolidate_ffa_reports_from_experiments.py \\
    --run-task1 --skip-task2

  # Run only Task 2 (use existing Task 1 outputs)
  python consolidate_ffa_reports_from_experiments.py \\
    --run-task2 --skip-task1 \\
    --output-dir outputs/existing_task1_output
        """
    )
    
    # Main directories
    parser.add_argument(
        '--base-dir',
        type=Path,
        default=DEFAULT_BASE_DIR,
        help=f"Base experiment directory (default: {DEFAULT_BASE_DIR})"
    )
    
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for Task 1 + Task 2 (default: {DEFAULT_OUTPUT_DIR})"
    )
    
    # Query parameters
    parser.add_argument(
        '--keyword',
        type=str,
        default=DEFAULT_KEYWORD,
        help=f"Keyword to filter runs (default: {DEFAULT_KEYWORD})"
    )
    
    parser.add_argument(
        '--dataset-key',
        type=str,
        default=DEFAULT_DATASET_KEY,
        choices=['eval', 'test'],
        help=f"Dataset key to use (default: {DEFAULT_DATASET_KEY})"
    )
    
    parser.add_argument(
        '--delete-keys',
        type=str,
        nargs='+',
        default=DEFAULT_DELETE_KEYS,
        help=f"Keys to remove from FFA assessment before LLM (default: {DEFAULT_DELETE_KEYS})"
    )
    
    # Task selection
    parser.add_argument(
        '--run-task1',
        action='store_true',
        default=True,
        help="Run Task 1 (FFA Reporter) - default: enabled"
    )
    
    parser.add_argument(
        '--skip-task1',
        action='store_true',
        help="Skip Task 1 (FFA Reporter)"
    )
    
    parser.add_argument(
        '--run-task2',
        action='store_true',
        default=True,
        help="Run Task 2 (FFA Aggregator) - default: enabled"
    )
    
    parser.add_argument(
        '--skip-task2',
        action='store_true',
        help="Skip Task 2 (FFA Aggregator)"
    )
    
    # LLM configuration
    parser.add_argument(
        '--model',
        type=str,
        default='gpt-4o',
        help="LLM model to use (default: gpt-4o)"
    )
    
    # Prompts file
    parser.add_argument(
        '--prompts-file',
        type=Path,
        default=DEFAULT_PROMPTS_FILE,
        help=f"Path to prompts.yaml (default: {DEFAULT_PROMPTS_FILE})"
    )
    
    # Logging
    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help="Logging level (default: INFO)"
    )
    
    args = parser.parse_args()
    
    # ========================================================================
    # Setup Logging
    # ========================================================================
    
    logger = setup_logging(__name__, level=args.log_level)
    
    logger.info("=" * 80)
    logger.info("FFA CONSOLIDATION WORKFLOW")
    logger.info("=" * 80)
    logger.info("")
    
    # ========================================================================
    # Validate and Prepare
    # ========================================================================
    
    # Handle skip flags
    run_task1 = args.run_task1 and not args.skip_task1
    run_task2 = args.run_task2 and not args.skip_task2
    
    if not run_task1 and not run_task2:
        logger.error("Error: At least one task must be enabled (--skip-task1 and --skip-task2 cannot both be set)")
        sys.exit(1)
    
    # Validate directories
    if run_task1:
        if not args.base_dir.exists():
            logger.error(f"Base directory not found: {args.base_dir}")
            sys.exit(1)
        logger.info(f"✓ Base directory exists: {args.base_dir}")
    
    args.output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"✓ Output directory ready: {args.output_dir}")
    
    # Load prompts
    if run_task1:
        try:
            prompts = load_prompts(args.prompts_file)
            logger.info(f"✓ Prompts loaded from {args.prompts_file}")
        except (FileNotFoundError, KeyError) as e:
            logger.error(f"Failed to load prompts: {e}")
            sys.exit(1)
    
    # Initialize LLM
    if run_task1:
        try:
            llm = initialize_llm(args.model)
            logger.info(f"✓ LLM initialized: {args.model}")
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}")
            sys.exit(1)
    
    logger.info("")
    
    # ========================================================================
    # Execute Workflow
    # ========================================================================
    
    tasks_passed = []
    tasks_failed = []
    
    # Task 1: FFA Reporter
    if run_task1:
        task1_success = run_task1_ffa_reporter(
            base_dir=args.base_dir,
            output_dir=args.output_dir,
            keyword=args.keyword,
            dataset_key=args.dataset_key,
            delete_keys=args.delete_keys,
            prompts=prompts,
            llm=llm,
            logger=logger
        )
        
        if task1_success:
            tasks_passed.append("Task 1: FFA Reporter")
        else:
            tasks_failed.append("Task 1: FFA Reporter")
    
    # Task 2: FFA Aggregator
    if run_task2:
        task2_success = run_task2_ffa_aggregator(
            task1_output_dir=args.output_dir,
            logger=logger
        )
        
        if task2_success:
            tasks_passed.append("Task 2: FFA Aggregator")
        else:
            tasks_failed.append("Task 2: FFA Aggregator")
    
    # ========================================================================
    # Summary
    # ========================================================================
    
    logger.info("=" * 80)
    logger.info("WORKFLOW SUMMARY")
    logger.info("=" * 80)
    
    if tasks_passed:
        logger.info(f"✓ PASSED ({len(tasks_passed)}):")
        for task in tasks_passed:
            logger.info(f"  - {task}")
    
    if tasks_failed:
        logger.error(f"✗ FAILED ({len(tasks_failed)}):")
        for task in tasks_failed:
            logger.error(f"  - {task}")
    
    logger.info("")
    logger.info(f"Output Directory: {args.output_dir}")
    logger.info(f"Final Reports: {args.output_dir}/FINAL_REPORTS/")
    
    # Exit code
    if tasks_failed:
        logger.error("Workflow completed with errors.")
        sys.exit(1)
    else:
        logger.info("✓ Workflow completed successfully!")
        sys.exit(0)


if __name__ == '__main__':
    main()
