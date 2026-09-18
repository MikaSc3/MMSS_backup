from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, List
from functools import lru_cache

import os
import re
import yaml


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_yaml_prompts(filename: str) -> Dict[str, str]:
    """Load prompts from a specific YAML file.
    
    Args:
        filename: Filename in configs/ directory (normally "prompts.yaml")
    
    Returns:
        Dict mapping prompt_id -> prompt_template. Empty dict if file not found.
    """
    cfg_path = _workspace_root() / "configs" / filename
    try:
        if not cfg_path.exists() or not cfg_path.is_file():
            return {}
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8", errors="replace"))
        if not isinstance(data, dict):
            return {}
        prompts = data.get("prompts")
        if not isinstance(prompts, dict):
            return {}

        out: Dict[str, str] = {}
        for prompt_id, entry in prompts.items():
            if not isinstance(prompt_id, str):
                continue
            if isinstance(entry, str):
                text = entry
            elif isinstance(entry, dict):
                text = entry.get("text")
            else:
                text = None
            if isinstance(text, str) and text.strip():
                out[prompt_id] = text.strip()
        return out
    except Exception:
        return {}


@lru_cache(maxsize=1)
def load_prompt_library() -> Dict[str, str]:
    """Load prompt texts from the consolidated prompt library (cached).
    
    Returns a dict: prompt_id -> prompt_template.
    Result is cached after first call to avoid repeated file I/O.
    
    Call load_prompt_library.cache_clear() if config changes at runtime.
    """
    return _load_yaml_prompts("prompts.yaml")


def get_prompt_template(prompt_id: str) -> Optional[str]:
    """Get a prompt template by id. Returns None if not found."""
    if not isinstance(prompt_id, str) or not prompt_id.strip():
        return None
    lib = load_prompt_library()
    return lib.get(prompt_id)


def get_prompt_text(prompt_id: str) -> Optional[str]:
    """Backward-compatible alias for get_prompt_template()."""
    return get_prompt_template(prompt_id)


def render_prompt(prompt_id: str, **kwargs: Any) -> Optional[str]:
    """Render a prompt template with str.format(**kwargs).

    Returns rendered text, or None if the template id is missing.
    If formatting fails, returns the raw template plus a best-effort appendix.
    """
    template = get_prompt_template(prompt_id)
    if not template:
        return None
    try:
        return template.format(**kwargs)
    except Exception:
        appendix_lines: List[str] = []
        for k, v in (kwargs or {}).items():
            appendix_lines.append(f"{k}: {v}")
        appendix = "\n".join(appendix_lines)
        if appendix:
            return f"{template}\n\n{appendix}"
        return template


def get_system_and_human_prompts(
    node_prefix: str,
    settings: Dict[str, Any]
) -> tuple[str, str]:
    """
    Load system and human prompts for a node with fallback logic.
    
    Args:
        node_prefix: Node prefix (e.g., "AAI", "AMI", "ASG", "ASV", "FFA")
        settings: Experiment settings dict
    
    Returns:
        (system_prompt, human_prompt) tuple
    
    Raises:
        ValueError: If human_prompt_id is missing or prompt not found
    
    Example:
        settings = {
            "base_system_prompt_id": "cad_analysis_expert_v1",
            "AAI_system_prompt_id": None,
            "AAI_human_prompt_id": "assembly_analysis_task_v1"
        }
        system, human = get_system_and_human_prompts("AAI", settings)
    """
    # Get system prompt (with fallback to base)
    system_id = settings.get(f"{node_prefix}_system_prompt_id")
    if not system_id:
        system_id = settings.get("base_system_prompt_id", "cad_analysis_expert_v1")
    
    system_prompt = get_prompt_template(system_id)
    if not system_prompt:
        raise ValueError(f"System prompt not found: {system_id}")
    
    # Get human prompt (required, no fallback)
    human_id = settings.get(f"{node_prefix}_human_prompt_id")
    if not human_id:
        raise ValueError(f"Missing {node_prefix}_human_prompt_id in settings")
    
    human_prompt = get_prompt_template(human_id)
    if not human_prompt:
        raise ValueError(f"Human prompt not found: {human_id}")
    
    return system_prompt, human_prompt


def load_examples_library() -> Dict[str, Dict[str, str]]:
    """Load examples from configs/prompts.yaml.

    Returns a dict: example_id -> {"input": str, "output": str}
    Silent fallback to empty dict if file is missing/invalid.
    """
    cfg_path = _workspace_root() / "configs" / "prompts.yaml"
    try:
        if not cfg_path.exists() or not cfg_path.is_file():
            return {}
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8", errors="replace"))
        if not isinstance(data, dict):
            return {}
        examples = data.get("examples")
        if not isinstance(examples, dict):
            return {}

        out: Dict[str, Dict[str, str]] = {}
        for ex_id, entry in examples.items():
            if not isinstance(ex_id, str):
                continue
            if not isinstance(entry, dict):
                continue
            ex_in = entry.get("input")
            ex_out = entry.get("output")
            if isinstance(ex_in, str) and isinstance(ex_out, str) and ex_in.strip() and ex_out.strip():
                out[ex_id] = {"input": ex_in.strip(), "output": ex_out.strip()}
        return out
    except Exception:
        return {}


def render_examples_block(example_ids: List[str]) -> str:
    """Render a few-shot examples block for injection into the instruction prompt."""
    ids = [str(x).strip() for x in (example_ids or []) if str(x).strip()]
    if not ids:
        return ""
    lib = load_examples_library()
    chunks: List[str] = []
    for ex_id in ids:
        ex = lib.get(ex_id)
        if not ex:
            continue
        chunks.append(
            "EXAMPLE\n"
            f"Input:\n{ex.get('input','').strip()}\n\n"
            f"Output:\n{ex.get('output','').strip()}"
        )
    if not chunks:
        return ""
    return "\n\n".join(chunks)


def load_experiment_settings() -> Dict[str, Any]:
    """Load experiment settings (code-only) used to select prompt variants.

    Precedence (lowest -> highest):
      1) configs/default_settings.yaml
      2) experiment.yaml (legacy, workspace root)
      3) APA_EXPERIMENT_YAML (preferred explicit selection)
    """
    workspace_root = _workspace_root()
    settings: Dict[str, Any] = {}

    def _merge_yaml(path: Path) -> None:
        try:
            if not path.exists() or not path.is_file():
                return
            data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
            if isinstance(data, dict):
                settings.update(data)
        except Exception:
            return

    _merge_yaml(workspace_root / "configs" / "default_settings.yaml")
    _merge_yaml(workspace_root / "experiment.yaml")

    exp_env = os.getenv("APA_EXPERIMENT_YAML")
    if exp_env and str(exp_env).strip():
        exp_path = Path(str(exp_env))
        if not exp_path.is_absolute():
            exp_path = (workspace_root / exp_path).resolve()
        else:
            exp_path = exp_path.resolve()
        try:
            exp_path.relative_to(workspace_root)
            _merge_yaml(exp_path)
        except Exception:
            pass

    return settings


def _resolve_stepparser_layout_vars(datasource_root: str | Path) -> Dict[str, Any]:
    """Resolve deterministic stepparser output paths in Python (no agent tool calls).

    Returns a dict of prompt formatting variables:
      - assembly_parent_dir
      - assembly_dir
      - bom_json_path
      - assembly_metadata_path
      - part_numbers (comma-separated string)
      - part_count
      - part_dir_template (string path with '{n}' placeholder)

    If anything cannot be resolved, values are empty strings / 0.
    """
    workspace_root = _workspace_root().resolve()

    # Resolve + workspace-scope guard
    p = Path(str(datasource_root))
    if not p.is_absolute():
        p = (workspace_root / p).resolve()
    else:
        p = p.resolve()
    try:
        p.relative_to(workspace_root)
    except Exception:
        return {
            "assembly_parent_dir": "",
            "assembly_dir": "",
            "bom_json_path": "",
            "assembly_metadata_path": "",
            "part_numbers": "",
            "part_count": 0,
            "part_dir_template": "",
        }

    def _is_step_dir(d: Path) -> bool:
        # New convention: assembly_{name} folders (e.g., "assembly_worm gear demonstrator")
        # Legacy: {name}.STEP folders
        return d.is_dir() and (d.name.lower().startswith("assembly_") or d.name.lower().endswith(".step"))

    assembly_dir: Optional[Path] = None
    assembly_parent: Optional[Path] = None

    if _is_step_dir(p):
        assembly_dir = p
        assembly_parent = p.parent
    else:
        assembly_parent = p
        try:
            step_dirs = sorted([d for d in p.iterdir() if _is_step_dir(d)], key=lambda d: d.name.lower())
        except Exception:
            step_dirs = []
        assembly_dir = step_dirs[0] if step_dirs else None

    bom_json_path = ""
    assembly_metadata_path = ""
    if assembly_dir and assembly_dir.exists() and assembly_dir.is_dir():
        try:
            # New naming: {assembly}_BOM.json (no hyphens)
            # Legacy: *-BOM.json or *BOM*.json
            bom_candidates = sorted([x for x in assembly_dir.glob("*_BOM.json") if x.is_file()], key=lambda x: x.name.lower())
            if not bom_candidates:
                bom_candidates = sorted([x for x in assembly_dir.glob("*-BOM.json") if x.is_file()], key=lambda x: x.name.lower())
            if not bom_candidates:
                bom_candidates = sorted([x for x in assembly_dir.glob("*BOM*.json") if x.is_file()], key=lambda x: x.name.lower())
            if bom_candidates:
                bom_json_path = str(bom_candidates[0])
        except Exception:
            bom_json_path = ""

        try:
            # New naming: {assembly}_Overview_Stepparser.json
            # Legacy: *-Metadata_assembly_stepparser.json or *-Metadata_assembly.json
            meta_candidates = sorted(
                [x for x in assembly_dir.glob("*_Overview_Stepparser.json") if x.is_file()],
                key=lambda x: x.name.lower(),
            )
            if not meta_candidates:
                meta_candidates = sorted(
                    [x for x in assembly_dir.glob("*-Metadata_assembly_stepparser.json") if x.is_file()],
                    key=lambda x: x.name.lower(),
                )
            if not meta_candidates:
                meta_candidates = sorted(
                    [x for x in assembly_dir.glob("*-Metadata_assembly.json") if x.is_file()],
                    key=lambda x: x.name.lower(),
                )
            if meta_candidates:
                assembly_metadata_path = str(meta_candidates[0])
        except Exception:
            assembly_metadata_path = ""

    part_numbers: List[int] = []
    unique_part_numbers: List[int] = []
    part_dirs: List[Path] = []
    unique_part_dirs: List[Path] = []
    if assembly_parent and assembly_parent.exists() and assembly_parent.is_dir():
        try:
            for d in assembly_parent.iterdir():
                if not d.is_dir():
                    continue
                name = d.name.strip()
                # Accept common stepparser part folder conventions:
                # - Part_1
                # - Part_1_copy
                # - Part_1-copy-2
                m = re.match(r"(?i)^part_(\d+)(?:$|[._-].*)", name)
                if not m:
                    continue
                try:
                    n = int(m.group(1))
                    part_numbers.append(n)
                    part_dirs.append(d)

                    # Determine whether this is a duplicate copy via the stepparser metadata JSON.
                    # New convention: <folder>/<folder>_Data_stepparser.json
                    # Legacy: <folder>/<folder>-Metadata_stepparser.json
                    meta_path = d / f"{d.name}_Data_stepparser.json"
                    if not meta_path.exists():
                        meta_path = d / f"{d.name}-Metadata_stepparser.json"
                    
                    is_copy = False
                    try:
                        if meta_path.exists() and meta_path.is_file():
                            import json
                            data = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
                            pid = data.get("part_id")
                            if isinstance(pid, str) and "_copy" in pid:
                                is_copy = True
                    except Exception:
                        # If we cannot read metadata, treat as unique to avoid accidentally skipping.
                        is_copy = False

                    if not is_copy:
                        unique_part_numbers.append(n)
                        unique_part_dirs.append(d)
                except Exception:
                    continue
        except Exception:
            part_numbers = []
            unique_part_numbers = []
            part_dirs = []
            unique_part_dirs = []
    part_numbers = sorted(set(part_numbers))
    unique_part_numbers = sorted(set(unique_part_numbers))

    def _part_sort_key(p: Path) -> int:
        m = re.match(r"(?i)^part_(\d+)(?:$|[._-].*)", p.name.strip())
        try:
            return int(m.group(1)) if m else 10**9
        except Exception:
            return 10**9

    part_dirs = sorted(part_dirs, key=_part_sort_key)
    unique_part_dirs = sorted(unique_part_dirs, key=_part_sort_key)

    return {
        "assembly_parent_dir": str(assembly_parent) if assembly_parent else "",
        "assembly_dir": str(assembly_dir) if assembly_dir else "",
        "bom_json_path": bom_json_path,
        "assembly_metadata_path": assembly_metadata_path,
        "part_numbers": ",".join(str(n) for n in part_numbers),
        "part_count": len(part_numbers),
        "unique_part_numbers": ",".join(str(n) for n in unique_part_numbers),
        "unique_part_count": len(unique_part_numbers),
        "part_dir_template": str((assembly_parent / "Part_{n}") if assembly_parent else ""),
        # Internal helpers for Python orchestration (not intended for prompt templates)
        "part_dirs": [str(p) for p in part_dirs],
        "unique_part_dirs": [str(p) for p in unique_part_dirs],
    }


def resolve_stepparser_layout_vars(datasource_root: str | Path) -> Dict[str, Any]:
    """Public alias for the deterministic layout resolver.

    Intended for Python orchestration code (e.g. LangGraph workflows) to avoid duplicating
    directory discovery logic.
    """
    return _resolve_stepparser_layout_vars(datasource_root)


def get_system_prompt(datasource_root: str | Path) -> str:
    """Return the system prompt selected by experiment settings.

    Uses `prompt_id_system` (configs/default_settings.yaml / experiment.yaml / APA_EXPERIMENT_YAML)
    and falls back to `system_prompt_v1`.
    """
    settings = load_experiment_settings()
    prompt_id = str(settings.get("prompt_id_system") or "").strip() or "system_prompt_v1"
    fmt_vars: Dict[str, Any] = {}
    try:
        if isinstance(settings, dict):
            fmt_vars.update(settings)
    except Exception:
        pass
    # datasource_root should always win
    fmt_vars["datasource_root"] = str(datasource_root)
    # ensure a stable default even if configs are edited
    if "bom_update_mode" not in fmt_vars:
        fmt_vars["bom_update_mode"] = "batch"

    # Precompute deterministic stepparser paths (avoid agent file-finding tool calls)
    fmt_vars.update(_resolve_stepparser_layout_vars(datasource_root))

    rendered = render_prompt(prompt_id, **fmt_vars)
    if not rendered:
        rendered = render_prompt("system_prompt_v1", **fmt_vars)

    if not rendered:
        return f"You are a helpful engineering assistant for CAD/assemblies. Datasource root: {datasource_root}"

    return rendered


def get_user_bootstrap_prompt(datasource_root: str | Path) -> str:
    """Return the initial (user) bootstrap message selected by experiment settings.

    Uses `prompt_id_user_bootstrap` and falls back to `user_bootstrap_v1`.
    """
    settings = load_experiment_settings()
    prompt_id = str(settings.get("prompt_id_user_bootstrap") or "").strip() or "user_bootstrap_v1"
    fmt_vars: Dict[str, Any] = {}
    try:
        if isinstance(settings, dict):
            fmt_vars.update(settings)
    except Exception:
        pass
    fmt_vars["datasource_root"] = str(datasource_root)
    if "bom_update_mode" not in fmt_vars:
        fmt_vars["bom_update_mode"] = "batch"

    fmt_vars.update(_resolve_stepparser_layout_vars(datasource_root))

    rendered = render_prompt(prompt_id, **fmt_vars)
    if not rendered:
        rendered = render_prompt("user_bootstrap_v1", **fmt_vars)
    return rendered or f"Datasource root: {datasource_root}"
