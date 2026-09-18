"""
Configuration Management für APA_from_CAD.

Zentrale Konfiguration basierend auf Pydantic BaseSettings.
Lädt Default-Settings aus YAML und überschreibt mit Experiment-Configs.
"""

import os
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


class WorkflowConfig(BaseSettings):
    """Workflow-Konfiguration mit Pydantic BaseSettings.
    
    Lädt Werte aus:
    1. configs/default_settings.yaml (Basis)
    2. configs/experiments/{experiment_name}.yaml (Override)
    3. Umgebungsvariablen (höchste Priorität)
    """
    
    # ===== Azure OpenAI Settings (aus .env) =====
    azure_endpoint_4o: str = Field(
        default="",
        description="Azure OpenAI Endpoint für GPT-4o",
        alias="AZURE_ENDPOINT_4O"
    )
    azure_endpoint_41: str = Field(
        default="",
        description="Azure OpenAI Endpoint für GPT-4.1",
        alias="AZURE_ENDPOINT_41"
    )
    azure_endpoint_54: str = Field(
        default="",
        description="Azure OpenAI Endpoint für GPT-5.4",
        alias="AZURE_ENDPOINT_54"
    )
    api_key_gpt_4: str = Field(
        default="",
        description="API Key für GPT-4o / GPT-4.1",
        alias="API_KEY_GPT_4"
    )
    api_key_gpt_5: str = Field(
        default="",
        description="API Key für GPT-5.4",
        alias="API_KEY_GPT_5"
    )
    api_version: str = Field(
        default="2024-02-15-preview",
        description="Azure OpenAI API Version"
    )
    llm_model: str = Field(
        default="5.4",
        description="Active LLM model alias: '4o', '4.1' or '5.4'"
    )
    llm_model_ffa: Optional[str] = Field(
        default=None,
        description="Optional FFA-specific LLM model. If not set, falls back to llm_model"
    )
    
    # ===== Experiment Settings =====
    experiment_name: str = Field(
        default="default",
        description="Name des Experiments (für Output-Ordner)"
    )
    
    # ===== Image Processing =====
    img_to_analyse_assy: List[str] = Field(
        default=["explosion", "isometric"],
        description="Keywords für Assembly-Bilder"
    )
    img_to_analyse_monopart: List[str] = Field(
        default=["top", "isometric"],
        description="Keywords für Monopart-Bilder"
    )
    downscaling_factor: float = Field(
        default=1.0,
        ge=0.1,
        le=1.0,
        description="Downscaling-Faktor für Bilder (1.0 = kein Scaling)"
    )
    max_images_per_call: Optional[int] = Field(
        default=None,
        description="Max. Anzahl Bilder pro LLM-Call"
    )
    
    # ===== LLM Settings =====
    img_describer_tokens_per_img: int = Field(
        default=2500,
        description="Completion Tokens pro Bild"
    )
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="LLM Temperature"
    )
    
    # ===== Workflow Settings =====
    use_assembly_context: bool = Field(
        default=True,
        description="Assembly-Kontext in Part-Prompts injizieren"
    )
    use_unique_parts: bool = Field(
        default=True,
        description="Nur unique Parts verarbeiten (Duplikate überspringen)"
    )
    workflow_print: bool = Field(
        default=False,
        description="Debug-Output aktivieren"
    )
    workflow_print_prompt_preview_chars: int = Field(
        default=800,
        description="Anzahl Zeichen für Prompt-Preview"
    )
    workflow_save_run_manifest: bool = Field(
        default=True,
        description="Run-Manifest als JSON speichern"
    )
    workflow_save_run_manifest_include_prompt_text: bool = Field(
        default=False,
        description="Prompt-Templates im Manifest speichern"
    )
    workflow_save_run_manifest_include_rendered_prompts: bool = Field(
        default=False,
        description="Gerenderte Prompts im Manifest speichern"
    )
    workflow_save_run_manifest_include_step_details: bool = Field(
        default=True,
        description="Step-Details im Manifest speichern"
    )
    
    # ===== Feature Flags =====
    use_additional_assembly_info: bool = Field(
        default=False,
        description="Load .txt from data/input/Additional_info/"
    )
    enable_merge_bom: bool = Field(
        default=False,
        description="Enable BOM merge node"
    )
    enable_ffa_assessment: bool = Field(
        default=False,
        description="Enable FFA assessment node"
    )
    enable_assembly_sequence: bool = Field(
        default=False,
        description="Enable assembly sequence generation node"
    )
    enable_sequence_validation: bool = Field(
        default=False,
        description="Enable assembly sequence validation node"
    )
    
    # ===== Assembly Sequence Configuration =====
    assembly_sequence_image_keywords: List[str] = Field(
        default_factory=lambda: ["exploded", "Top"],
        description="Image keywords for assembly sequence generation"
    )
    assembly_sequence_json_keywords: List[str] = Field(
        default_factory=lambda: ["merged_bom"],
        description="JSON keywords for assembly sequence generation"
    )
    sequence_validation_view_keywords: List[str] = Field(
        default_factory=lambda: ["isometric", "front"],
        description="View keywords for sequence validation (which views to send to LLM)"
    )
    finished_assembly_image_keywords: List[str] = Field(
        default_factory=lambda: ["isometric", "explosion"],
        description="Keywords for finished assembly reference images"
    )
    render_all_views: bool = Field(
        default=True,
        description="Render all views (isometric, front, top, side) for validation"
    )
    
    # ===== Prompt Selection =====
    prompt_id_assy: str = Field(
        default="assembly_describer_v1",
        description="Prompt ID für Assembly Analysis"
    )
    prompt_id_monopart: str = Field(
        default="monopart_describer_v1",
        description="Prompt ID für Monopart Analysis"
    )
    prompt_id_system: str = Field(
        default="system_prompt_v1",
        description="System Prompt ID"
    )
    prompt_id_user_bootstrap: str = Field(
        default="user_bootstrap_v1",
        description="User Bootstrap Prompt ID"
    )
    prompt_id_merge_bom: str = Field(
        default="merge_bom_v1",
        description="Prompt ID für BOM Merge"
    )
    prompt_id_ffa: str = Field(
        default="ffa_detailed_v1",
        description="Prompt ID für FFA Assessment"
    )
    
    # ===== Computed Properties =====
    @property
    def experiment_output_root(self) -> Path:
        """Returns: data/experiments/{experiment_name}/"""
        return Path("data/experiments") / self.experiment_name
    
    @property
    def textbased_data_root(self) -> Path:
        """Returns: data/input/Textbased_Data/"""
        return Path("data/input/Textbased_Data")
    
    @property
    def additional_info_root(self) -> Path:
        """Deprecated: Use textbased_data_root instead. Returns: data/input/Textbased_Data/"""
        return self.textbased_data_root
    
    @property
    def assembly_order_root(self) -> Path:
        """Deprecated: Use textbased_data_root instead. Returns: data/input/Textbased_Data/"""
        return self.textbased_data_root
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Allow field population from environment
        case_sensitive = False
        extra = "allow"  # Allow extra fields from YAML
    
    @classmethod
    def from_yaml(
        cls, 
        yaml_path: Optional[Path] = None,
        base_config_path: Path = Path("configs/default_settings.yaml")
    ) -> "WorkflowConfig":
        """Load configuration from YAML files + env overrides.
        
        Loading Order:
        1. base_config_path (default_settings.yaml)
        2. yaml_path (experiment-specific YAML, if provided)
        3. .env file (secrets like API keys)
        4. Environment variables (highest priority)
        
        Args:
            yaml_path: Path to experiment YAML (optional)
            base_config_path: Path to base config YAML
            
        Returns:
            WorkflowConfig instance
            
        Example:
            >>> # Load default settings
            >>> config = WorkflowConfig.from_yaml()
            
            >>> # Load experiment-specific settings
            >>> config = WorkflowConfig.from_yaml(
            ...     Path("configs/experiments/exp1_baseline.yaml")
            ... )
        """
        # Load base config
        base_data = {}
        if base_config_path.exists():
            with open(base_config_path, "r", encoding="utf-8") as f:
                base_data = yaml.safe_load(f) or {}
        
        # Load experiment config (overrides base)
        exp_data = {}
        if yaml_path and yaml_path.exists():
            with open(yaml_path, "r", encoding="utf-8") as f:
                exp_data = yaml.safe_load(f) or {}
        
        # Merge configs (exp overrides base)
        merged_data = {**base_data, **exp_data}
        
        # Load from merged YAML + env vars
        # Environment variables take precedence via Pydantic
        return cls(**merged_data)
    
    def to_dict(self) -> dict:
        """Export config as dictionary."""
        return self.model_dump()
    
    def save_to_yaml(self, output_path: Path) -> None:
        """Save current config to YAML file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.to_dict(), f, indent=2, default_flow_style=False)


# Global default config (lazy-loaded)
_default_config: Optional[WorkflowConfig] = None


def get_default_config() -> WorkflowConfig:
    """Get or create default config singleton."""
    global _default_config
    if _default_config is None:
        _default_config = WorkflowConfig.from_yaml()
    return _default_config
