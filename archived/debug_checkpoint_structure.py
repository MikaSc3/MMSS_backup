"""
Debug script to verify checkpoint and ground truth structure.

Checks if all required data for FFA-only workflow exists:
- Checkpoint assemblies
- Ground truth sequences
- Ground truth renderings
- Checkpoint BOM, enriched_parts, stepparser_renderings

Usage:
    python debug_checkpoint_structure.py

Edit at top:
    CHECKPOINT_PATH: Path to checkpoint
"""

import json
from pathlib import Path
from typing import Dict, List

# ============================================================================
# CONFIGURATION
# ============================================================================

CHECKPOINT_PATH = "data/checkpoints/MASTER"
GROUND_TRUTH_BASE = "data/ground_truth"

# ============================================================================
# MAIN DEBUG FUNCTION
# ============================================================================

def debug_checkpoint_structure(checkpoint_path: str, ground_truth_base: str) -> None:
    """
    Debug checkpoint and ground truth structure.
    
    Args:
        checkpoint_path: Path to checkpoint
        ground_truth_base: Path to ground truth base
    """
    workspace_root = Path(__file__).resolve().parent
    checkpoint_path = Path(checkpoint_path)
    ground_truth_base = Path(ground_truth_base)
    
    # Make absolute if needed
    if not checkpoint_path.is_absolute():
        checkpoint_path = workspace_root / checkpoint_path
    if not ground_truth_base.is_absolute():
        ground_truth_base = workspace_root / ground_truth_base
    
    print(f"\n{'='*80}")
    print(f"DEBUG: CHECKPOINT & GROUND TRUTH STRUCTURE")
    print(f"{'='*80}")
    print(f"Workspace root: {workspace_root}")
    print(f"Checkpoint: {checkpoint_path}")
    print(f"Ground truth: {ground_truth_base}")
    
    # ========================================================================
    # 1. Check checkpoint exists
    # ========================================================================
    print(f"\n{'─'*80}")
    print(f"1. CHECKPOINT VALIDATION")
    print(f"{'─'*80}")
    
    if not checkpoint_path.exists():
        print(f"❌ Checkpoint does not exist: {checkpoint_path}")
        return
    
    print(f"✓ Checkpoint exists: {checkpoint_path}")
    
    # ========================================================================
    # 2. Discover assemblies
    # ========================================================================
    print(f"\n{'─'*80}")
    print(f"2. DISCOVER ASSEMBLIES IN CHECKPOINT")
    print(f"{'─'*80}")
    
    assemblies = []
    for item in checkpoint_path.iterdir():
        if item.is_dir() and not item.name.startswith("_"):
            assemblies.append(item.name)
    
    assemblies = sorted(assemblies)
    
    if not assemblies:
        print(f"❌ No assemblies found in checkpoint")
        print(f"   Subdirectories:")
        for item in checkpoint_path.iterdir():
            print(f"     - {item.name} (dir={item.is_dir()})")
        return
    
    print(f"✓ Found {len(assemblies)} assemblies:")
    for asm in assemblies:
        print(f"   - {asm}")
    
    # ========================================================================
    # 3. Check each assembly
    # ========================================================================
    print(f"\n{'─'*80}")
    print(f"3. CHECK EACH ASSEMBLY")
    print(f"{'─'*80}")
    
    assembly_summary = {}
    
    for assembly_name in assemblies:
        print(f"\n[{assembly_name}]")
        assembly_ok = True
        issues = []
        
        # 3.1 Checkpoint files
        print(f"  Checkpoint files:")
        
        asm_checkpoint_dir = checkpoint_path / assembly_name
        print(f"    Directory: {asm_checkpoint_dir}")
        
        # BOM
        bom_files = list(asm_checkpoint_dir.glob("*BOM_enriched.json"))
        if bom_files:
            print(f"    ✓ BOM: {bom_files[0].name}")
        else:
            print(f"    ❌ BOM: NOT FOUND")
            issues.append("Missing BOM_enriched.json")
            assembly_ok = False
        
        # enriched_parts
        enriched_dir = asm_checkpoint_dir / "enriched_parts"
        if enriched_dir.exists() and enriched_dir.is_dir():
            part_files = list(enriched_dir.glob("*.json"))
            print(f"    ✓ enriched_parts: {len(part_files)} files")
        else:
            print(f"    ❌ enriched_parts: NOT FOUND")
            issues.append("Missing enriched_parts/")
            assembly_ok = False
        
        # stepparser_renderings
        stepparser_dir = asm_checkpoint_dir / "stepparser_renderings"
        if stepparser_dir.exists() and stepparser_dir.is_dir():
            rend_files = list(stepparser_dir.glob("*"))
            print(f"    ✓ stepparser_renderings: {len(rend_files)} files")
        else:
            print(f"    ❌ stepparser_renderings: NOT FOUND")
            issues.append("Missing stepparser_renderings/")
            assembly_ok = False
        
        # 3.2 Ground truth files
        print(f"  Ground truth files:")
        
        gt_asm_dir = ground_truth_base / "assembly_sequence_ground_truth" / assembly_name
        print(f"    Directory: {gt_asm_dir}")
        
        # sequence.json
        seq_file = gt_asm_dir / "sequence.json"
        if seq_file.exists():
            try:
                with open(seq_file, 'r') as f:
                    seq_data = json.load(f)
                steps = seq_data.get("steps", [])
                print(f"    ✓ sequence.json: {len(steps)} steps")
            except Exception as e:
                print(f"    ⚠️  sequence.json: EXISTS but ERROR reading: {e}")
                issues.append(f"Error reading sequence.json: {e}")
                assembly_ok = False
        else:
            print(f"    ❌ sequence.json: NOT FOUND")
            issues.append("Missing sequence.json in ground_truth")
            assembly_ok = False
        
        # renderings
        rend_dir = gt_asm_dir / "renderings"
        if rend_dir.exists() and rend_dir.is_dir():
            rend_files = list(rend_dir.glob("*"))
            print(f"    ✓ renderings: {len(rend_files)} files")
        else:
            print(f"    ❌ renderings: NOT FOUND")
            issues.append("Missing renderings/ in ground_truth")
            assembly_ok = False
        
        # Summary
        if assembly_ok:
            print(f"  ✓ Assembly OK")
        else:
            print(f"  ❌ Assembly has issues:")
            for issue in issues:
                print(f"     - {issue}")
        
        assembly_summary[assembly_name] = {
            "ok": assembly_ok,
            "issues": issues
        }
    
    # ========================================================================
    # 4. Final summary
    # ========================================================================
    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}")
    
    ok_count = sum(1 for v in assembly_summary.values() if v["ok"])
    total_count = len(assembly_summary)
    
    print(f"Assemblies OK: {ok_count}/{total_count}")
    
    if ok_count == total_count:
        print(f"\n✅ All assemblies ready for FFA-only workflow!")
    else:
        print(f"\n⚠️  Some assemblies have issues:")
        for asm_name, status in assembly_summary.items():
            if not status["ok"]:
                print(f"   - {asm_name}:")
                for issue in status["issues"]:
                    print(f"       • {issue}")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    debug_checkpoint_structure(
        checkpoint_path=CHECKPOINT_PATH,
        ground_truth_base=GROUND_TRUTH_BASE
    )
