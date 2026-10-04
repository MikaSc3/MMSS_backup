"""
FFA Reporter Node: Summarizes and consolidates FFA assessments per assembly.

Processes complete FFA assessment data for an assembly and generates
aggregated, deduplicated reports of automation challenges and opportunities.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from langchain_core.language_model.llm import LLM
from pydantic import ValidationError

from agent.structured_output import FFAReportDestilled, PartDrawbacks
from config_utils import setup_logging


def discover_runs(base_experiment_dir: Path, keyword: str) -> List[Path]:
    """
    Discover all run directories matching keyword pattern.
    
    Args:
        base_experiment_dir: Base experiment directory
        keyword: Keyword to match in folder names (e.g., "54_54")
        
    Returns:
        List of run directories sorted by name
    """
    runs = []
    for config_dir in base_experiment_dir.iterdir():
        if config_dir.is_dir() and keyword in config_dir.name:
            runs.append(config_dir)
    
    return sorted(runs, key=lambda x: x.name)


def discover_assemblies(run_dir: Path) -> List[str]:
    """
    Discover all assembly folders in a run directory.
    
    Looks for ffa_assessment.json files to identify valid assemblies.
    
    Args:
        run_dir: Run directory to search
        
    Returns:
        List of assembly names (directory names containing ffa_assessment.json)
    """
    assemblies = []
    
    for item in run_dir.rglob("ffa_assessment.json"):
        assembly_dir = item.parent.parent  # Navigate up from ffa_assessment/
        assembly_name = assembly_dir.name
        if assembly_name not in assemblies:
            assemblies.append(assembly_name)
    
    return sorted(assemblies)


def load_ffa_assessment(assembly_dir: Path) -> Optional[Dict[str, Any]]:
    """
    Load and parse FFA assessment JSON file.
    
    Args:
        assembly_dir: Assembly directory containing ffa_assessment/ subfolder
        
    Returns:
        Parsed JSON dict, or None if file not found
    """
    ffa_file = assembly_dir / "ffa_assessment" / "ffa_assessment.json"
    
    if not ffa_file.exists():
        logging.warning(f"FFA assessment not found: {ffa_file}")
        return None
    
    try:
        with open(ffa_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logging.error(f"Failed to load FFA assessment {ffa_file}: {e}")
        return None


def delete_keys_from_dict(data: Dict[str, Any], delete_keys: List[str]) -> Dict[str, Any]:
    """
    Recursively delete specified keys from a dictionary.
    
    Args:
        data: Dictionary to process
        delete_keys: List of keys to delete
        
    Returns:
        Modified dictionary (modifies in place, also returns for convenience)
    """
    for key in delete_keys:
        if key in data:
            del data[key]
    
    # Recursively process nested dictionaries and lists
    for value in data.values():
        if isinstance(value, dict):
            delete_keys_from_dict(value, delete_keys)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    delete_keys_from_dict(item, delete_keys)
    
    return data


def call_ffa_reporter_llm(
    ffa_assessment_json: Dict[str, Any],
    assembly_name: str,
    llm: LLM,
    system_prompt: str,
    human_template: str,
) -> Optional[FFAReportDestilled]:
    """
    Call LLM node to generate FFA report.
    
    Args:
        ffa_assessment_json: Processed FFA assessment data
        assembly_name: Assembly name for context
        llm: LLM instance to use
        system_prompt: System prompt defining role
        human_template: Human message template with {ffa_assessment_json} and {assembly_name} placeholders
        
    Returns:
        Parsed FFAReportDestilled object, or None if LLM call failed
    """
    try:
        # Format human message
        human_message = human_template.format(
            ffa_assessment_json=json.dumps(ffa_assessment_json, indent=2),
            assembly_name=assembly_name
        )
        
        # Call LLM
        response = llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": human_message}
        ])
        
        # Extract JSON from response
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # Try to parse as JSON
        try:
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                report_data = json.loads(json_str)
            else:
                report_data = json.loads(response_text)
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse LLM response as JSON: {e}\nResponse: {response_text[:500]}")
            return None
        
        # Validate against Pydantic model
        report = FFAReportDestilled(**report_data)
        return report
        
    except ValidationError as e:
        logging.error(f"Pydantic validation error for assembly {assembly_name}: {e}")
        return None
    except Exception as e:
        logging.error(f"LLM call failed for assembly {assembly_name}: {e}")
        return None


def generate_ffa_reports_per_config(
    base_experiment_dir: Path,
    keyword: str,
    delete_keys: Optional[List[str]] = None,
    llm: Optional[LLM] = None,
    system_prompt: Optional[str] = None,
    human_template: Optional[str] = None,
    dataset_key: str = "eval",
    output_dir: Optional[Path] = None,
) -> Dict[str, Dict[str, FFAReportDestilled]]:
    """
    Generate FFA reports for all assemblies across all matching runs.
    
    Main node function. Discovers runs and assemblies, loads FFA assessments,
    calls LLM to generate consolidated reports, and aggregates results.
    
    Args:
        base_experiment_dir: Root experiment directory
        keyword: Keyword to filter runs (e.g., "54_54")
        delete_keys: List of keys to remove from FFA assessment before LLM call
        llm: LLM instance (will be injected by caller if not provided)
        system_prompt: System prompt from configs/prompts.yaml
        human_template: Human message template from configs/prompts.yaml
        dataset_key: Dataset key for path navigation (default: "eval")
        output_dir: Optional output directory for saving reports
        
    Returns:
        Dict[assembly_name][run_id] = FFAReportDestilled
        
    Raises:
        ValueError: If LLM, system_prompt, or human_template are not provided
    """
    # Validate required inputs
    if llm is None:
        raise ValueError("LLM instance must be provided")
    if system_prompt is None:
        raise ValueError("system_prompt must be provided")
    if human_template is None:
        raise ValueError("human_template must be provided")
    
    if delete_keys is None:
        delete_keys = []
    
    base_experiment_dir = Path(base_experiment_dir)
    
    logging.info(f"Discovering runs matching keyword '{keyword}' in {base_experiment_dir}")
    
    # Discover runs
    runs = discover_runs(base_experiment_dir, keyword)
    if not runs:
        logging.warning(f"No runs found matching keyword '{keyword}'")
        return {}
    
    logging.info(f"Found {len(runs)} runs: {[r.name for r in runs]}")
    
    # Discover assemblies from first run
    first_run = runs[0]
    assemblies = discover_assemblies(first_run)
    if not assemblies:
        logging.warning(f"No assemblies found in first run {first_run.name}")
        return {}
    
    logging.info(f"Found {len(assemblies)} assemblies: {assemblies}")
    
    # Results aggregator
    results: Dict[str, Dict[str, FFAReportDestilled]] = {
        asm: {} for asm in assemblies
    }
    
    # Process each assembly × run combination
    for assembly_name in assemblies:
        logging.info(f"Processing assembly: {assembly_name}")
        
        for run_dir in runs:
            run_id = run_dir.name
            
            # Construct assembly directory path
            assembly_dir = run_dir / dataset_key / assembly_name
            
            if not assembly_dir.exists():
                logging.warning(f"Assembly directory not found: {assembly_dir}")
                continue
            
            # Load FFA assessment
            ffa_data = load_ffa_assessment(assembly_dir)
            if ffa_data is None:
                logging.warning(f"Skipping {assembly_name} in {run_id}: FFA assessment not found")
                continue
            
            # Delete specified keys
            ffa_data_cleaned = delete_keys_from_dict(ffa_data.copy(), delete_keys)
            
            # Call LLM
            logging.info(f"Calling LLM for {assembly_name} in {run_id}")
            report = call_ffa_reporter_llm(
                ffa_data_cleaned,
                assembly_name,
                llm,
                system_prompt,
                human_template
            )
            
            if report is not None:
                results[assembly_name][run_id] = report
                logging.info(f"✓ Generated report for {assembly_name} / {run_id}")
                
                # Optionally save report to disk
                if output_dir:
                    report_path = (
                        output_dir /
                        assembly_name /
                        f"ffa_report_destilled_{assembly_name}_{run_id}.json"
                    )
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    try:
                        with open(report_path, 'w', encoding='utf-8') as f:
                            f.write(report.model_dump_json(indent=2))
                        logging.info(f"Saved report to {report_path}")
                    except IOError as e:
                        logging.error(f"Failed to save report to {report_path}: {e}")
            else:
                logging.error(f"✗ Failed to generate report for {assembly_name} / {run_id}")
    
    # Summary
    total_assemblies = len(assemblies)
    generated_count = sum(len(runs_dict) for runs_dict in results.values())
    expected_count = len(assemblies) * len(runs)
    
    logging.info(
        f"FFA Reports Generated: {generated_count}/{expected_count} "
        f"({total_assemblies} assemblies × {len(runs)} runs)"
    )
    
    return results


# ============================================================================
# Public Node Interface
# ============================================================================

def ffa_reporter(
    base_experiment_dir: Path,
    keyword: str,
    delete_keys: Optional[List[str]] = None,
    **kwargs
) -> Dict[str, Dict[str, FFAReportDestilled]]:
    """
    Public node interface for FFA report generation.
    
    Called by app_workflow with LLM, prompts, and other dependencies injected.
    
    Args:
        base_experiment_dir: Experiment root directory
        keyword: Run filter keyword
        delete_keys: Keys to remove from FFA assessment
        **kwargs: Additional arguments including 'llm', 'system_prompt', 'human_template'
        
    Returns:
        Dict[assembly_name][run_id] = FFAReportDestilled
    """
    logger = setup_logging(__name__)
    
    return generate_ffa_reports_per_config(
        base_experiment_dir=base_experiment_dir,
        keyword=keyword,
        delete_keys=delete_keys,
        llm=kwargs.get('llm'),
        system_prompt=kwargs.get('system_prompt'),
        human_template=kwargs.get('human_template'),
        dataset_key=kwargs.get('dataset_key', 'eval'),
        output_dir=kwargs.get('output_dir'),
    )
