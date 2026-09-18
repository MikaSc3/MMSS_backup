#!/usr/bin/env python3
"""
Batch Renderer for Assembly Sequences

Lädt sequence.json aus LOADDIR (Ordnerstruktur: {assembly_name}/sequence.json)
Rendert diese mit render_assembly_steps und speichert in OUTPUTDIR.

WICHTIG: LOADDIR wird NICHT GEÄNDERT
"""

import json
import shutil
import sys
from pathlib import Path
from typing import Dict, List

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

# ──────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────

LOADDIR = Path(r"C:\Users\KAB-MS\VSCode\apa_from_cad\data\RENDERSHIT\assembly_sequence_ground_truth")
OUTPUTDIR = Path(r"C:\Users\KAB-MS\VSCode\apa_from_cad\data\RENDERSHIT\NEU2")

# Optional: Welche Baugruppengruppen rendern? (None = alle)
ASSEMBLIES_FILTER = None  # z.B. ["IPA_Cranfield", "pump_assembly"]


# ──────────────────────────────────────────────────────────────────────
# FUNCTIONS
# ──────────────────────────────────────────────────────────────────────

def find_sequence_dirs(load_dir: Path) -> List[Path]:
    """
    Findet alle Ordner mit sequence.json in LOADDIR.
    Assembly-Name = Ordnername
    """
    if not load_dir.exists():
        print(f"[ERROR] LOADDIR existiert nicht: {load_dir}")
        return []
    
    dirs = []
    for item in load_dir.iterdir():
        if item.is_dir():
            seq_file = item / "sequence.json"
            if seq_file.exists():
                dirs.append(item)
    
    return sorted(dirs)



def render_assembly(assembly_name: str, sequence_file: Path, output_assembly_dir: Path) -> Dict:
    """
    Ruft render_assembly_steps auf und speichert direkt in OUTPUTDIR.
    
    Die Funktion sucht nach:
    - assembly_sequence.json im exp_output_dir
    - STEP Datei in data/input/ALL oder data/input/STEP
    
    Erzeugt: sequence_renderings/ im exp_output_dir (direkt, nicht in temp!)
    """
    try:
        from agent.Assembly_sequence_validation import render_assembly_steps
    except ImportError as import_error:
        return {
            "status": "error",
            "message": f"Konnte render_assembly_steps nicht importieren: {import_error}"
        }
    
    # Kopiere sequence.json zu output_assembly_dir/assembly_sequence.json
    # (render_assembly_steps sucht danach)
    assembly_seq_file = output_assembly_dir / "assembly_sequence.json"
    shutil.copy2(sequence_file, assembly_seq_file)
    
    print(f"  → Rendern direkt nach: {output_assembly_dir}")
    
    try:
        result = render_assembly_steps(
            assembly_name=assembly_name,
            experiment_name="batch_render",
            exp_output_dir=output_assembly_dir,
            transparency_values=[0.0],
            headless_mode=False
        )
        return result
    except Exception as e:
        return {
            "status": "error",
            "message": f"Exception während render_assembly_steps: {e}"
        }


def rename_renderings_folder(output_assembly_dir: Path) -> bool:
    """
    Benennt sequence_renderings/ nach renderings/ um.
    """
    source = output_assembly_dir / "sequence_renderings"
    target = output_assembly_dir / "renderings"
    
    if not source.exists():
        print(f"  ⚠ Keine sequence_renderings gefunden in {output_assembly_dir}")
        return False
    
    # Zielordner löschen falls vorhanden
    if target.exists():
        shutil.rmtree(target)
    
    # Umbenennen
    source.rename(target)
    
    # Zähle Bilder
    png_count = len(list(target.glob("*.png")))
    print(f"  ✓ {png_count} Renderings gespeichert in renderings/")
    
    return True


def main():
    print("=" * 80)
    print("BATCH RENDERER FÜR ASSEMBLY SEQUENCES")
    print("=" * 80)
    print(f"\nLOADDIR:  {LOADDIR}")
    print(f"OUTPUTDIR: {OUTPUTDIR}")
    print(f"Filter:    {ASSEMBLIES_FILTER if ASSEMBLIES_FILTER else 'ALLE'}")
    print()
    
    # ──────────────────────────────────────────────────────────────────
    # Schritt 1: Assembly-Ordner finden
    # ──────────────────────────────────────────────────────────────────
    
    assembly_dirs = find_sequence_dirs(LOADDIR)
    if not assembly_dirs:
        print("[ERROR] Keine Assembly-Ordner mit sequence.json gefunden!")
        return 1
    
    # Filter anwenden falls gesetzt
    if ASSEMBLIES_FILTER:
        assembly_dirs = [d for d in assembly_dirs if d.name in ASSEMBLIES_FILTER]
    
    print(f"[OK] Gefunden: {len(assembly_dirs)} Assembly(ies)\n")
    for d in assembly_dirs:
        print(f"  - {d.name}")
    print()
    
    # ──────────────────────────────────────────────────────────────────
    # Schritt 2: Für jede Assembly rendern
    # ──────────────────────────────────────────────────────────────────
    
    OUTPUTDIR.mkdir(parents=True, exist_ok=True)
    
    results = {
        "success": [],
        "failed": [],
        "skipped": []
    }
    
    for assembly_dir in assembly_dirs:
        assembly_name = assembly_dir.name
        print(f"\n{'─' * 80}")
        print(f"Processing: {assembly_name}")
        print(f"{'─' * 80}")
        
        seq_file = assembly_dir / "sequence.json"
        output_assembly_dir = OUTPUTDIR / assembly_name
        
        # 1. Create output directory for this assembly
        output_assembly_dir.mkdir(parents=True, exist_ok=True)
        
        # 2. Copy sequence.json to output (LOADDIR wird nicht geändert!)
        try:
            output_seq_file = output_assembly_dir / "sequence.json"
            shutil.copy2(seq_file, output_seq_file)
            print(f"  ✓ sequence.json kopiert")
        except Exception as e:
            print(f"  [ERROR] Fehler beim Kopieren: {e}")
            results["failed"].append(f"{assembly_name}: copy failed")
            continue
        
        # 3. Render DIREKT nach OUTPUTDIR (nicht in tempdir!)
        print(f"  → Starten Rendering...")
        render_result = render_assembly(assembly_name, seq_file, output_assembly_dir)
        
        if render_result.get("status") == "error":
            print(f"  [ERROR] {render_result.get('message')}")
            results["failed"].append(f"{assembly_name}: {render_result.get('message')}")
            continue
        
        if render_result.get("status") == "warning":
            print(f"  [WARNING] {render_result.get('message')}")
            results["skipped"].append(f"{assembly_name}: {render_result.get('message')}")
            continue
        
        # 4. Rename sequence_renderings -> renderings
        if not rename_renderings_folder(output_assembly_dir):
            print(f"  [WARNING] Keine Renderings generiert")
            results["skipped"].append(f"{assembly_name}: no renderings")
            continue
        
        print(f"  ✓ COMPLETE")
        results["success"].append(assembly_name)
    
    # ──────────────────────────────────────────────────────────────────
    # Summary
    # ──────────────────────────────────────────────────────────────────
    
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    print(f"✓ Success:  {len(results['success'])}")
    for name in results['success']:
        print(f"    - {name}")
    
    if results['skipped']:
        print(f"⚠ Skipped:  {len(results['skipped'])}")
        for item in results['skipped']:
            print(f"    - {item}")
    
    if results['failed']:
        print(f"✗ Failed:   {len(results['failed'])}")
        for item in results['failed']:
            print(f"    - {item}")
    
    print(f"\nOutput directory: {OUTPUTDIR}")
    print()
    
    return 0 if not results['failed'] else 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n[INTERRUPTED]")
        sys.exit(130)
    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
