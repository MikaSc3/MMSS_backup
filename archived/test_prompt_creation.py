#!/usr/bin/env python
"""
Test Prompt Creation - Verify Templates, Images, and JSONs are Loaded Correctly

Tests all experiments (default_settings.yaml + configs/experiments/*.yaml)
and prints the actual prompts that would be created for each node.
Also tests actual image and JSON loading for a sample assembly.
"""

import sys
from pathlib import Path
import yaml
import json

# Add workspace to path
workspace_root = Path(__file__).parent
sys.path.insert(0, str(workspace_root))


def load_settings_file(settings_path: Path) -> dict:
    """Load settings from YAML file."""
    with open(settings_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def print_section(title: str, level=1):
    """Print a formatted section header."""
    if level == 1:
        print("\n" + "="*80)
        print(f"  {title}")
        print("="*80)
    elif level == 2:
        print("\n" + "-"*80)
        print(f"  {title}")
        print("-"*80)
    else:
        print(f"\n### {title}")


def test_node_prompts(node_name: str, settings: dict):
    """Test prompt loading for a specific node."""
    from agent.prompt_store import get_system_and_human_prompts
    
    print_section(f"{node_name} Node", level=2)
    
    # Get node-specific settings
    if node_name == "AAI":
        system_id = settings.get("AAI_system_prompt_id") or settings.get("base_system_prompt_id")
        human_id = settings.get("AAI_human_prompt_id")
        img_keywords = settings.get("img_to_analyse_assy", [])
        json_keyword = settings.get("AAI_json_file_keyword")
        json_keys = settings.get("AAI_json_keys", [])
    elif node_name == "AMI":
        system_id = settings.get("AMI_system_prompt_id") or settings.get("base_system_prompt_id")
        human_id = settings.get("AMI_human_prompt_id")
        img_keywords = settings.get("img_to_analyse_monopart", [])
        json_keyword = settings.get("AMI_json_file_keyword")
        json_keys = settings.get("AMI_json_keys", [])
    elif node_name == "ASG":
        system_id = settings.get("ASG_system_prompt_id")
        human_id = settings.get("ASG_human_prompt_id")
        img_keywords = settings.get("ASG_image_keywords", [])
        json_keyword = settings.get("ASG_json_file_keyword")
        json_keys = settings.get("ASG_json_keys", [])
    elif node_name == "ASV":
        system_id = settings.get("ASV_system_prompt_id")
        human_id = settings.get("ASV_human_prompt_id")
        img_keywords = settings.get("ASV_step_img_keywords", [])
        json_keyword = settings.get("ASV_json_keywords", [])
        json_keys = settings.get("ASV_parts_json_keys", [])
    elif node_name == "FFA":
        system_id = settings.get("FFA_system_prompt_id")
        human_id = settings.get("FFA_human_prompt_id")
        img_keywords = settings.get("FFA_step_img_keywords", [])
        json_keys_base = settings.get("FFA_base_part_json_keys", [])
        json_keys_joining = settings.get("FFA_joining_part_json_keys", [])
        json_keys = {"base": json_keys_base, "joining": json_keys_joining}
        json_keyword = "enriched_parts"
    else:
        print(f"  [SKIP] Unknown node: {node_name}")
        return
    
    # Print configuration
    print(f"\n  Configuration:")
    print(f"    System Prompt ID: {system_id}")
    print(f"    Human Prompt ID:  {human_id}")
    print(f"    Image Keywords:   {img_keywords}")
    if node_name == "FFA":
        print(f"    JSON Keys (Base):    {json_keys['base']}")
        print(f"    JSON Keys (Joining): {json_keys['joining']}")
    else:
        print(f"    JSON Keyword:     {json_keyword}")
        print(f"    JSON Keys:        {json_keys}")
    
    # Try to load prompts
    try:
        system_prompt, human_prompt = get_system_and_human_prompts(node_name, settings)
        
        print(f"\n  ✓ Prompts loaded successfully")
        print(f"\n  System Prompt (first 200 chars):")
        print(f"    {system_prompt[:200]}...")
        
        print(f"\n  Human Prompt (first 300 chars):")
        print(f"    {human_prompt[:300]}...")
        
    except Exception as e:
        print(f"\n  ✗ ERROR loading prompts: {e}")
        import traceback
        traceback.print_exc()
    
    # Test actual image and JSON loading with sample data
    test_actual_loading(node_name, settings)


def test_actual_loading(node_name: str, settings: dict):
    """Test actual image and JSON loading for a node with real data."""
    print(f"\n  Testing Actual Data Loading:")
    
    # Find a sample assembly to test with
    data_dir = workspace_root / "data"
    
    # For ASV and FFA, we need sequence renderings
    if node_name in ["ASV", "FFA"]:
        # HARDCODED: Use specific experiment run
        experiments_dir = data_dir / "experiments" / "run_2026-02-01_145221"
        sample_assembly = None
        renderings_dir = None
        
        if experiments_dir.exists():
            # Search through experiment structure
            for assembly_folder in experiments_dir.rglob("*"):
                if assembly_folder.is_dir():
                    # Check for sequence_renderings
                    test_renderings = assembly_folder / "sequence_renderings"
                    if test_renderings.exists():
                        sample_assembly = assembly_folder
                        renderings_dir = test_renderings
                        break
                    # Check for assembly_sequence_run* folders
                    for run_folder in assembly_folder.glob("assembly_sequence_run*"):
                        test_renderings = run_folder / "sequence_renderings"
                        if test_renderings.exists():
                            sample_assembly = assembly_folder
                            renderings_dir = test_renderings
                            break
                if renderings_dir:
                    break
        
        if renderings_dir and renderings_dir.exists():
            print(f"    Sample: {sample_assembly.name}")
            print(f"    Renderings: {renderings_dir}")
            
            # Test image loading with keywords
            img_keywords = settings.get(f"{node_name}_step_img_keywords", [])
            if node_name == "ASV":
                prior_keywords = settings.get("ASV_prior_step_img_keywords", [])
            
            from agent.tools import matches_image_keyword
            
            # Find matching images
            all_images = list(renderings_dir.glob("*.png"))
            matched_images = []
            
            for img_path in all_images[:5]:  # Test first 5 images
                for kw in img_keywords:
                    if matches_image_keyword(img_path.name, kw):
                        matched_images.append(img_path.name)
                        break
            
            print(f"    Total images in folder: {len(all_images)}")
            print(f"    Images matching keywords: {len(matched_images)}")
            if matched_images:
                print(f"    Sample matches: {matched_images[:3]}")
            else:
                print(f"    ⚠ No images matched keywords: {img_keywords}")
                print(f"    Available images (first 5): {[img.name for img in all_images[:5]]}")
            
            # Test JSON loading for FFA
            if node_name == "FFA":
                bom_files = list(sample_assembly.glob("*BOM*.json"))
                if bom_files:
                    print(f"    Found BOM: {bom_files[0].name}")
                    with open(bom_files[0], 'r') as f:
                        bom_data = json.load(f)
                    parts_count = len(bom_data.get("parts", []))
                    print(f"    BOM parts: {parts_count}")
                else:
                    print(f"    ⚠ No BOM file found")
        else:
            print(f"    ⚠ No sequence_renderings folder found for testing")
    
    # For AAI and AMI, we need stepparser outputs
    elif node_name in ["AAI", "AMI"]:
        processed_dir = data_dir / "processed" / "stepparser"
        
        if processed_dir.exists():
            # Find first assembly with images
            sample_assembly = None
            assembly_dir = None
            
            for assy_folder in processed_dir.iterdir():
                if not assy_folder.is_dir():
                    continue
                # Look for assembly_{name} or {name}.STEP folders
                for subfolder in assy_folder.iterdir():
                    if subfolder.is_dir() and subfolder.name.startswith("assembly_"):
                        test_images = list(subfolder.glob("*.png"))
                        if test_images:
                            sample_assembly = assy_folder.name
                            assembly_dir = subfolder
                            break
                if assembly_dir:
                    break
            
            if assembly_dir and assembly_dir.exists():
                print(f"    Sample: {sample_assembly}")
                print(f"    Assembly dir: {assembly_dir}")
                
                # Test image loading
                if node_name == "AAI":
                    img_keywords = settings.get("img_to_analyse_assy", [])
                else:
                    img_keywords = settings.get("img_to_analyse_monopart", [])
                
                from agent.tools import matches_image_keyword
                
                all_images = list(assembly_dir.glob("*.png"))
                matched_images = []
                
                for img_path in all_images:
                    for kw in img_keywords:
                        if matches_image_keyword(img_path.name, kw):
                            matched_images.append(img_path.name)
                            break
                
                print(f"    Total images: {len(all_images)}")
                print(f"    Images matching keywords: {len(matched_images)}")
                if matched_images:
                    print(f"    Sample matches: {matched_images[:3]}")
                else:
                    print(f"    ⚠ No images matched keywords: {img_keywords}")
                    print(f"    Available images (first 5): {[img.name for img in all_images[:5]]}")
            else:
                print(f"    ⚠ No stepparser assembly folder found for testing")
        else:
            print(f"    ⚠ Stepparser processed directory not found")
    
    # For ASG, test BOM loading
    elif node_name == "ASG":
        experiments_dir = data_dir / "experiments"
        
        if experiments_dir.exists():
            # Find any experiment with BOM
            for exp_folder in experiments_dir.iterdir():
                if not exp_folder.is_dir():
                    continue
                for assembly_folder in exp_folder.rglob("*"):
                    if assembly_folder.is_dir():
                        bom_files = list(assembly_folder.glob("*BOM*.json"))
                        if bom_files:
                            print(f"    Sample: {assembly_folder.name}")
                            print(f"    Found BOM: {bom_files[0].name}")
                            
                            with open(bom_files[0], 'r') as f:
                                bom_data = json.load(f)
                            parts_count = len(bom_data.get("parts", []))
                            print(f"    BOM parts: {parts_count}")
                            
                            # Test image loading
                            stepparser_dir = data_dir / "processed" / "stepparser"
                            if stepparser_dir.exists():
                                for assy_folder in stepparser_dir.iterdir():
                                    if assy_folder.name in assembly_folder.name:
                                        for subfolder in assy_folder.iterdir():
                                            if subfolder.is_dir() and subfolder.name.startswith("assembly_"):
                                                img_keywords = settings.get("ASG_image_keywords", [])
                                                from agent.tools import matches_image_keyword
                                                
                                                all_images = list(subfolder.glob("*.png"))
                                                matched_images = []
                                                
                                                for img_path in all_images:
                                                    for kw in img_keywords:
                                                        if matches_image_keyword(img_path.name, kw):
                                                            matched_images.append(img_path.name)
                                                            break
                                                
                                                print(f"    Images matching keywords: {len(matched_images)}")
                                                if matched_images:
                                                    print(f"    Sample matches: {matched_images[:3]}")
                                                break
                                        break
                            return
        print(f"    ⚠ No BOM files found for testing")


def test_experiment(exp_name: str, settings_path: Path):
    """Test prompt creation for a specific experiment."""
    print_section(f"EXPERIMENT: {exp_name}", level=1)
    
    # Load settings
    print(f"\n  Settings file: {settings_path}")
    settings = load_settings_file(settings_path)
    
    # Test each node
    nodes = ["AAI", "AMI", "ASG", "ASV", "FFA"]
    
    for node_name in nodes:
        # Check if node is enabled (for ASV and FFA)
        if node_name == "ASV":
            mode = settings.get("ASV_mode", "enabled")
            if mode == "disabled":
                print_section(f"{node_name} Node", level=2)
                print(f"  [SKIP] ASV_mode = disabled")
                continue
        elif node_name == "FFA":
            mode = settings.get("FFA_mode", "enabled")
            if mode == "disabled":
                print_section(f"{node_name} Node", level=2)
                print(f"  [SKIP] FFA_mode = disabled")
                continue
        
        test_node_prompts(node_name, settings)


def main():
    """Main test function."""
    print("\n" + "="*80)
    print("  PROMPT CREATION TEST")
    print("  Testing all experiments to verify templates, images, and JSONs are loaded")
    print("="*80)
    
    # Find all experiment configs
    configs_dir = workspace_root / "configs"
    default_settings = configs_dir / "default_settings.yaml"
    experiments_dir = configs_dir / "experiments"
    
    # Test default settings first
    if default_settings.exists():
        test_experiment("DEFAULT SETTINGS", default_settings)
    else:
        print(f"\n[ERROR] default_settings.yaml not found at {default_settings}")
    
    # Test all experiment configs
    if experiments_dir.exists():
        experiment_files = sorted(experiments_dir.glob("*.yaml"))
        
        if experiment_files:
            for exp_file in experiment_files:
                exp_name = exp_file.stem.upper()
                test_experiment(exp_name, exp_file)
        else:
            print(f"\n[INFO] No experiment configs found in {experiments_dir}")
    else:
        print(f"\n[INFO] Experiments directory not found: {experiments_dir}")
    
    # Summary
    print("\n" + "="*80)
    print("  TEST COMPLETE")
    print("="*80)
    print("\nReview the output above to verify:")
    print("  1. Correct prompt templates are loaded for each node")
    print("  2. Image keywords match expected values")
    print("  3. JSON keywords and keys are configured correctly")
    print("  4. No errors when loading prompts")
    print("\n")


if __name__ == "__main__":
    main()
