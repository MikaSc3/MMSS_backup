"""Export app_workflow sequence output into ASGT ground-truth format.

Input structure:
    data/datapreparation/singletest/appconfig/{assembly_name}/assembly_sequence_runN/
        assembly_sequence.json
        sequence_renderings/

Output structure:
    data/ground_truth/assembly_sequence_ground_truth/{assembly_name}/
        sequence.json
        renderings/

Usage:
    python export_app_sequence_ground_truth.py

Optional:
    Set ASSEMBLIES_FILTER below to export only selected assemblies.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Optional


# ============================================================================
# CONFIGURATION
# ============================================================================

APP_WORKFLOW_OUTPUT_ROOT: str = "data/datapreparation/NEWFILES/appconfig"
GROUND_TRUTH_SEQUENCE_ROOT: str = "data/ground_truth/assembly_sequence_ground_truth"
ASSEMBLIES_FILTER: Optional[list[str]] = None  # Example: ["Coupling O Ring"]
OVERWRITE_EXISTING: bool = True

# ============================================================================


WORKSPACE_ROOT = Path(__file__).resolve().parent


def _resolve(path_like: str | Path) -> Path:
    path = Path(path_like)
    return path if path.is_absolute() else WORKSPACE_ROOT / path


def _assembly_dirs(root: Path) -> list[Path]:
    if not root.exists():
        raise FileNotFoundError(f"App workflow output root not found: {root}")

    dirs = [item for item in root.iterdir() if item.is_dir() and not item.name.startswith("_")]
    if ASSEMBLIES_FILTER:
        wanted = set(ASSEMBLIES_FILTER)
        dirs = [item for item in dirs if item.name in wanted]
    return sorted(dirs, key=lambda p: p.name.lower())


def _run_number(run_dir: Path) -> int:
    match = re.fullmatch(r"assembly_sequence_run(\d+)", run_dir.name)
    return int(match.group(1)) if match else -1


def _latest_sequence_run(assembly_dir: Path) -> Optional[Path]:
    candidates = [
        item for item in assembly_dir.iterdir()
        if item.is_dir()
        and _run_number(item) >= 0
        and (item / "assembly_sequence.json").exists()
    ]
    if not candidates:
        return None
    return max(candidates, key=_run_number)


def _copytree_clean(source: Path, target: Path) -> None:
    if target.exists():
        if not OVERWRITE_EXISTING:
            raise FileExistsError(f"Target already exists: {target}")
        shutil.rmtree(target)
    shutil.copytree(source, target)


def export_assembly(assembly_dir: Path, gt_root: Path) -> tuple[bool, str]:
    assembly_name = assembly_dir.name
    latest_run = _latest_sequence_run(assembly_dir)
    if latest_run is None:
        return False, f"{assembly_name}: no assembly_sequence_runN with assembly_sequence.json found"

    sequence_file = latest_run / "assembly_sequence.json"
    renderings_source = latest_run / "sequence_renderings"
    if not renderings_source.exists():
        renderings_source = latest_run / "renderings"
    if not renderings_source.exists():
        return False, f"{assembly_name}: no sequence_renderings/renderings folder in {latest_run.name}"

    target_dir = gt_root / assembly_name
    target_dir.mkdir(parents=True, exist_ok=True)

    target_sequence = target_dir / "sequence.json"
    if target_sequence.exists() and not OVERWRITE_EXISTING:
        return False, f"{assembly_name}: sequence.json already exists"
    shutil.copy2(sequence_file, target_sequence)

    additional_info_file = target_dir / f"additional_info_{assembly_name}.txt"
    if not additional_info_file.exists():
        additional_info_file.write_text("Additional Info about the assembly\n", encoding="utf-8")

    target_renderings = target_dir / "renderings"
    _copytree_clean(renderings_source, target_renderings)

    png_count = len(list(target_renderings.glob("*.png")))
    return True, (
        f"{assembly_name}: exported {latest_run.name} -> "
        f"{target_dir.relative_to(WORKSPACE_ROOT)} ({png_count} rendering files)"
    )


def export_all() -> int:
    app_root = _resolve(APP_WORKFLOW_OUTPUT_ROOT)
    gt_root = _resolve(GROUND_TRUTH_SEQUENCE_ROOT)
    gt_root.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("EXPORT APP WORKFLOW SEQUENCE GROUND TRUTH")
    print("=" * 80)
    print(f"Input:     {app_root}")
    print(f"Output:    {gt_root}")
    print(f"Overwrite: {OVERWRITE_EXISTING}")
    print(f"Filter:    {ASSEMBLIES_FILTER or 'all'}")
    print()

    assemblies = _assembly_dirs(app_root)
    if not assemblies:
        print("No assemblies found.")
        return 1

    success = 0
    failed = 0
    for assembly_dir in assemblies:
        ok, message = export_assembly(assembly_dir, gt_root)
        print(("OK  " if ok else "ERR ") + message)
        if ok:
            success += 1
        else:
            failed += 1

    print()
    print(f"Done. Success: {success}, Failed: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(export_all())
