"""
Config loading utilities for experiments.

Handles loading experiment configurations from structured directories with fallback support.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional


def load_experiment_config(
    experiment_name: str,
    workflow_type: str,  # "full_workflow" or "ffa_only"
    config_base_path: Path = None
) -> Dict[str, Any]:
    """
    Load experiment configuration with fallback strategy.
    
    Priority:
    1. configs/{workflow_type}/{experiment_name}.yaml
    2. configs/default.yaml
    
    Args:
        experiment_name: Name of experiment (e.g., "exp1", "exp2")
        workflow_type: Type of workflow ("full_workflow" or "ffa_only")
        config_base_path: Base path for configs (default: workspace/configs)
    
    Returns:
        Dict with experiment configuration
        
    Raises:
        FileNotFoundError: If no config found (neither specific nor default)
        ValueError: If workflow_type is invalid
    """
    if workflow_type not in ["full_workflow", "ffa_only", "sequence_gt"]:
        raise ValueError(f"Invalid workflow_type: {workflow_type}. Must be 'full_workflow', 'ffa_only', or 'sequence_gt'")
    
    if config_base_path is None:
        config_base_path = Path(__file__).resolve().parents[1] / "configs"
    else:
        config_base_path = Path(config_base_path)
    
    # Primary: workflow-specific config
    specific_config = config_base_path / workflow_type / f"{experiment_name}.yaml"
    
    if specific_config.exists():
        with open(specific_config, 'r') as f:
            config = yaml.safe_load(f)
        print(f"✓ Loaded config: {specific_config.relative_to(config_base_path.parent)}")
        return config if config else {}
    
    # Fallback: default config
    default_config = config_base_path / "default.yaml"
    
    if default_config.exists():
        with open(default_config, 'r') as f:
            config = yaml.safe_load(f)
        print(f"⚠️  Using default config: {default_config.relative_to(config_base_path.parent)}")
        return config if config else {}
    
    # Error: no config found
    raise FileNotFoundError(
        f"No config found for experiment '{experiment_name}' in {workflow_type}.\n"
        f"Searched: {specific_config}\n"
        f"Fallback: {default_config}"
    )


def discover_experiments(
    workflow_type: str,
    config_base_path: Path = None
) -> List[str]:
    """
    Auto-discover experiments from workflow-specific directory.
    
    Finds all .yaml files in configs/{workflow_type}/ (excluding default.yaml).
    
    Args:
        workflow_type: Type of workflow ("full_workflow" or "ffa_only")
        config_base_path: Base path for configs (default: workspace/configs)
    
    Returns:
        List of experiment names
    """
    if workflow_type not in ["full_workflow", "ffa_only", "sequence_gt"]:
        raise ValueError(f"Invalid workflow_type: {workflow_type}")
    
    if config_base_path is None:
        config_base_path = Path(__file__).resolve().parents[1] / "configs"
    else:
        config_base_path = Path(config_base_path)
    
    workflow_dir = config_base_path / workflow_type
    
    if not workflow_dir.exists():
        print(f"⚠️  Directory not found: {workflow_dir}")
        return []
    
    # Find all .yaml files (excluding any that start with .)
    experiments = []
    for yaml_file in workflow_dir.glob("*.yaml"):
        if not yaml_file.name.startswith("."):
            exp_name = yaml_file.stem  # filename without .yaml
            experiments.append(exp_name)
    
    return sorted(experiments)


def load_all_experiment_configs(
    experiment_names: List[str],
    workflow_type: str,
    config_base_path: Path = None
) -> Dict[str, Dict[str, Any]]:
    """
    Load multiple experiment configurations.
    
    Args:
        experiment_names: List of experiment names
        workflow_type: Type of workflow ("full_workflow" or "ffa_only")
        config_base_path: Base path for configs
    
    Returns:
        Dict mapping experiment_name → config
    """
    configs = {}
    
    for exp_name in experiment_names:
        try:
            config = load_experiment_config(exp_name, workflow_type, config_base_path)
            configs[exp_name] = config
        except FileNotFoundError as e:
            print(f"❌ Failed to load config for {exp_name}: {e}")
            raise
    
    return configs
