"""
FFA Aggregator Node (Task 2): Consolidates per-run FFA reports into assembly-level reports.

Reads Task 1 per-run reports from disk and aggregates them using union strategy:
- Assembly-level drawbacks: all unique items across all runs
- Assembly-level improvements: all unique items across all runs
- Part-level: union of all part IDs seen, aggregate their drawbacks/improvements
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set
from collections import defaultdict

from pydantic import ValidationError

from agent.structured_output import FFAReportDestilled, PartDrawbacks
from config_utils import setup_logging


def discover_run_reports(task1_output_dir: Path, assembly_name: str) -> Dict[str, Path]:
    """
    Discover all run-level reports for a specific assembly in Task 1 output directory.
    
    Looks for files matching: ffa_report_destilled_{assembly_name}_{run_id}.json
    
    Args:
        task1_output_dir: Task 1 output directory containing per-assembly subdirs
        assembly_name: Assembly name to find reports for
        
    Returns:
        Dict[run_id] = Path to report file
    """
    reports = {}
    
    assembly_reports_dir = task1_output_dir / assembly_name
    
    if not assembly_reports_dir.exists():
        logging.warning(f"Assembly reports directory not found: {assembly_reports_dir}")
        return reports
    
    # Find all JSON files matching pattern
    for report_file in assembly_reports_dir.glob(f"ffa_report_destilled_{assembly_name}_*.json"):
        # Extract run_id from filename
        filename = report_file.stem  # removes .json
        # Pattern: ffa_report_destilled_{assembly_name}_{run_id}
        prefix = f"ffa_report_destilled_{assembly_name}_"
        if filename.startswith(prefix):
            run_id = filename[len(prefix):]
            reports[run_id] = report_file
    
    return reports


def load_ffa_report(report_path: Path) -> Optional[FFAReportDestilled]:
    """
    Load and parse a single FFA report from disk.
    
    Args:
        report_path: Path to report JSON file
        
    Returns:
        Parsed FFAReportDestilled object, or None if load failed
    """
    try:
        with open(report_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        report = FFAReportDestilled(**data)
        return report
        
    except (json.JSONDecodeError, IOError) as e:
        logging.error(f"Failed to load report {report_path}: {e}")
        return None
    except ValidationError as e:
        logging.error(f"Pydantic validation error loading {report_path}: {e}")
        return None


def aggregate_drawbacks(reports: Dict[str, FFAReportDestilled]) -> List[str]:
    """
    Union all unique drawbacks across all run reports.
    
    Args:
        reports: Dict[run_id] = FFAReportDestilled
        
    Returns:
        List of unique drawbacks (deduplicated)
    """
    unique_drawbacks: Set[str] = set()
    
    for report in reports.values():
        unique_drawbacks.update(report.assembly_drawbacks)
    
    return sorted(list(unique_drawbacks))


def aggregate_improvements(reports: Dict[str, FFAReportDestilled]) -> List[str]:
    """
    Union all unique improvements across all run reports.
    
    Args:
        reports: Dict[run_id] = FFAReportDestilled
        
    Returns:
        List of unique improvements (deduplicated)
    """
    unique_improvements: Set[str] = set()
    
    for report in reports.values():
        unique_improvements.update(report.assembly_improvements)
    
    return sorted(list(unique_improvements))


def aggregate_parts(reports: Dict[str, FFAReportDestilled]) -> List[PartDrawbacks]:
    """
    Union all parts and aggregate their drawbacks/improvements.
    
    For each unique part_id seen across all runs:
    - Collect all drawbacks (union)
    - Collect all improvements (union)
    
    Args:
        reports: Dict[run_id] = FFAReportDestilled
        
    Returns:
        List[PartDrawbacks] with unique parts and aggregated constraints
    """
    # Collect parts by part_id
    parts_data: Dict[str, Dict[str, Set[str]]] = defaultdict(
        lambda: {"drawbacks": set(), "improvements": set()}
    )
    
    for report in reports.values():
        for part in report.parts:
            parts_data[part.part_id]["drawbacks"].update(part.part_drawbacks)
            parts_data[part.part_id]["improvements"].update(part.part_improvements)
    
    # Create PartDrawbacks objects
    aggregated_parts = [
        PartDrawbacks(
            part_id=part_id,
            part_drawbacks=sorted(list(data["drawbacks"])),
            part_improvements=sorted(list(data["improvements"]))
        )
        for part_id, data in sorted(parts_data.items())
    ]
    
    return aggregated_parts


def aggregate_ffa_reports(
    task1_output_dir: Path,
    assembly_name: str,
) -> Optional[FFAReportDestilled]:
    """
    Aggregate all run-level reports for one assembly.
    
    Uses union strategy: combines all unique items from all runs.
    
    Args:
        task1_output_dir: Task 1 output directory
        assembly_name: Assembly to aggregate
        
    Returns:
        Consolidated FFAReportDestilled or None if no reports found
    """
    logging.info(f"Aggregating reports for assembly: {assembly_name}")
    
    # Discover all run reports for this assembly
    reports_dict = discover_run_reports(task1_output_dir, assembly_name)
    
    if not reports_dict:
        logging.warning(f"No run reports found for assembly {assembly_name}")
        return None
    
    logging.info(f"Found {len(reports_dict)} run reports for {assembly_name}: {list(reports_dict.keys())}")
    
    # Load all reports
    loaded_reports: Dict[str, FFAReportDestilled] = {}
    
    for run_id, report_path in reports_dict.items():
        report = load_ffa_report(report_path)
        if report is not None:
            loaded_reports[run_id] = report
        else:
            logging.warning(f"Failed to load report for {assembly_name} / {run_id}")
    
    if not loaded_reports:
        logging.error(f"No valid reports could be loaded for assembly {assembly_name}")
        return None
    
    # Aggregate
    aggregated_drawbacks = aggregate_drawbacks(loaded_reports)
    aggregated_improvements = aggregate_improvements(loaded_reports)
    aggregated_parts = aggregate_parts(loaded_reports)
    
    # Create consolidated report
    consolidated = FFAReportDestilled(
        assembly_name=assembly_name,
        assembly_drawbacks=aggregated_drawbacks,
        assembly_improvements=aggregated_improvements,
        parts=aggregated_parts
    )
    
    logging.info(
        f"✓ Aggregated {assembly_name}: "
        f"{len(aggregated_drawbacks)} drawbacks, "
        f"{len(aggregated_improvements)} improvements, "
        f"{len(aggregated_parts)} parts"
    )
    
    return consolidated


def consolidate_all_assemblies(
    task1_output_dir: Path,
    output_dir: Optional[Path] = None,
) -> Dict[str, FFAReportDestilled]:
    """
    Main Task 2 function: Consolidate all assemblies.
    
    Discovers all assemblies in Task 1 output directory, aggregates each,
    and optionally saves consolidated reports to FINAL_REPORTS/ subdirectory.
    
    Args:
        task1_output_dir: Task 1 output directory (contains per-assembly subdirs)
        output_dir: Optional output root (consolidated reports saved to output_dir/FINAL_REPORTS/)
        
    Returns:
        Dict[assembly_name] = consolidated FFAReportDestilled
    """
    task1_output_dir = Path(task1_output_dir)
    
    logging.info(f"Discovering assemblies in Task 1 output: {task1_output_dir}")
    
    # Discover all assembly directories
    assembly_dirs = [d for d in task1_output_dir.iterdir() if d.is_dir()]
    
    if not assembly_dirs:
        logging.warning(f"No assembly directories found in {task1_output_dir}")
        return {}
    
    assembly_names = sorted([d.name for d in assembly_dirs])
    logging.info(f"Found {len(assembly_names)} assemblies: {assembly_names}")
    
    # Aggregate each assembly
    results: Dict[str, FFAReportDestilled] = {}
    
    for assembly_name in assembly_names:
        consolidated = aggregate_ffa_reports(task1_output_dir, assembly_name)
        
        if consolidated is not None:
            results[assembly_name] = consolidated
            
            # Optionally save to disk
            if output_dir:
                final_reports_dir = Path(output_dir) / "FINAL_REPORTS"
                final_reports_dir.mkdir(parents=True, exist_ok=True)
                
                output_file = final_reports_dir / f"{assembly_name}_destilled_ffa_consolidated.json"
                
                try:
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(consolidated.model_dump_json(indent=2))
                    logging.info(f"✓ Saved consolidated report to {output_file}")
                except IOError as e:
                    logging.error(f"Failed to save consolidated report to {output_file}: {e}")
        else:
            logging.error(f"✗ Failed to aggregate assembly {assembly_name}")
    
    # Summary
    logging.info(
        f"Task 2 Consolidation Complete: {len(results)}/{len(assembly_names)} assemblies aggregated"
    )
    
    return results


# ============================================================================
# Public Node Interface
# ============================================================================

def ffa_aggregator(
    task1_output_dir: Path,
    output_dir: Optional[Path] = None,
    **kwargs
) -> Dict[str, FFAReportDestilled]:
    """
    Public node interface for FFA report aggregation (Task 2).
    
    Called by app_workflow with Task 1 output directory.
    Consolidates per-run reports into per-assembly consolidated reports.
    
    Args:
        task1_output_dir: Where Task 1 (ffa_reporter) saved run-level reports
        output_dir: Optional root where to save FINAL_REPORTS/
        **kwargs: Additional arguments (for future extensibility)
        
    Returns:
        Dict[assembly_name] = consolidated FFAReportDestilled
    """
    logger = setup_logging(__name__)
    
    return consolidate_all_assemblies(
        task1_output_dir=task1_output_dir,
        output_dir=output_dir
    )
