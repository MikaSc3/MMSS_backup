"""
Helper script: rename _-prefixed evaluation folders and their run subfolders.

For each folder in data/experiments/ that starts with "_":
  1. Suggests a random <Color><Fruit> name
  2. User confirms or types a custom name
  3. Renames:
       _OldFolder              → _ColorFruit_OldFolder
       _OldFolder/RunSubfolder → _ColorFruit_OldFolder/ColorFruit_RunSubfolder

Skips:  'evaluation/' directories and loose files (run_log.json etc.)
Dry-run mode available (set DRY_RUN = True below).
"""

import sys
from pathlib import Path
from run_name_utils import generate_run_name

# ── Config ───────────────────────────────────────────────────────────────────
EXPERIMENTS_BASE = Path("data/experiments")
DRY_RUN = False          # True → only print, don't rename
# ─────────────────────────────────────────────────────────────────────────────


def _rename(src: Path, dst: Path) -> None:
    if DRY_RUN:
        print(f"  [DRY] {src.name}  →  {dst.name}")
    else:
        src.rename(dst)
        print(f"  ✓  {src.name}  →  {dst.name}")


def ask_name(folder: Path) -> str:
    suggestion = generate_run_name()
    print(f"\n{'─'*60}")
    print(f"Folder : {folder.name}")
    answer = input(f"Name   [{suggestion}]: ").strip()
    return answer if answer else suggestion


def rename_folder(folder: Path, name: str) -> None:
    # Skip non-run subfolders (evaluation, files)
    run_subdirs = [
        d for d in sorted(folder.iterdir())
        if d.is_dir() and d.name != "evaluation"
    ]

    # 1. Rename run subfolders first (while parent path still valid)
    new_folder = folder.parent / f"_{name}_{folder.name.lstrip('_')}"

    for sub in run_subdirs:
        new_sub = folder / f"{name}_{sub.name}"
        _rename(sub, new_sub)

    # 2. Rename the outer folder
    _rename(folder, new_folder)


def main() -> None:
    folders = sorted(
        d for d in EXPERIMENTS_BASE.iterdir()
        if d.is_dir() and d.name.startswith("_")
    )

    if not folders:
        print(f"No '_'-prefixed folders found in {EXPERIMENTS_BASE}")
        sys.exit(0)

    print(f"\nFound {len(folders)} folder(s) to rename:")
    for f in folders:
        print(f"  - {f.name}")

    if DRY_RUN:
        print("\n[DRY-RUN mode – no files will be changed]\n")

    for folder in folders:
        name = ask_name(folder)
        rename_folder(folder, name)

    print(f"\n{'─'*60}")
    print("Done." if not DRY_RUN else "Dry-run complete – nothing was renamed.")


if __name__ == "__main__":
    main()
