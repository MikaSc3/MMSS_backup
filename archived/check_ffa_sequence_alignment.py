"""
check_ffa_sequence_alignment.py

Cross-checks FFA ground truth assessments against assembly sequence ground truths.

For each assembly that exists in BOTH sources, matches steps by step_id and reports
any mismatch in base_part or joining_part.
"""
import json
from pathlib import Path

FFA_GT_DIR = Path(r"C:\Users\KAB-MS\VSCode\apa_from_cad\data\ground_truth\ffa_ground_truth_evaluierungsdaten")
SEQ_GT_DIR = Path(r"C:\Users\KAB-MS\VSCode\apa_from_cad\data\ground_truth\assembly_sequence_ground_truth")

# ── helpers ────────────────────────────────────────────────────────────────────

def norm(value) -> str:
    """Normalise a part-id value: None / empty-string → '<none>'."""
    if value is None:
        return "<none>"
    v = str(value).strip()
    return v if v else "<none>"


def assembly_name_from_ffa_file(ffa_path: Path) -> str:
    """Strip the '_ffa_assessment_enum_gt' suffix to get the assembly name."""
    return ffa_path.stem.replace("_ffa_assessment_enum_gt", "")


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    ffa_files = sorted(FFA_GT_DIR.glob("*_ffa_assessment_enum_gt.json"))

    total_assemblies = 0
    total_steps_checked = 0
    total_mismatches = 0
    assemblies_with_mismatches = []

    print("=" * 72)
    print("FFA ↔ SEQUENCE GROUND TRUTH ALIGNMENT REPORT")
    print("=" * 72)

    for ffa_file in ffa_files:
        assembly_name = assembly_name_from_ffa_file(ffa_file)

        # ── locate sequence.json ──────────────────────────────────────────────
        seq_file = SEQ_GT_DIR / assembly_name / "sequence.json"
        if not seq_file.exists():
            print(f"\n[SKIP] {assembly_name}")
            print(f"       No sequence.json found at {seq_file}")
            continue

        total_assemblies += 1

        # ── load data ─────────────────────────────────────────────────────────
        with open(ffa_file, encoding="utf-8") as f:
            ffa_raw = json.load(f)

        # Two known FFA formats:
        #   Format A (most files): top-level list  [{step_id, ...}, ...]
        #   Format B (some files): top-level dict  {step_assessments: [{step_id, ...}, ...]}
        if isinstance(ffa_raw, list):
            ffa_steps: list = ffa_raw
        elif isinstance(ffa_raw, dict):
            ffa_steps = ffa_raw.get("step_assessments") or ffa_raw.get("steps") or []
        else:
            print(f"\n[SKIP] {assembly_name} — unrecognised FFA JSON structure")
            continue

        with open(seq_file, encoding="utf-8") as f:
            seq_data: dict = json.load(f)

        seq_steps: list = seq_data.get("steps", [])

        # Build lookup: step_id → step dict
        ffa_by_id  = {s["step_id"]: s for s in ffa_steps}
        seq_by_id  = {s["step_id"]: s for s in seq_steps}

        mismatches = []

        # FFA is master → iterate over FFA step IDs
        for step_id, ffa_step in sorted(ffa_by_id.items()):
            total_steps_checked += 1

            ffa_base    = norm(ffa_step.get("base_part_id"))
            ffa_joining = norm(ffa_step.get("joining_part_id"))

            seq_step = seq_by_id.get(step_id)
            if seq_step is None:
                mismatches.append({
                    "step_id": step_id,
                    "reason": "step missing in sequence",
                    "ffa_base": ffa_base,
                    "ffa_joining": ffa_joining,
                    "seq_base": "—",
                    "seq_joining": "—",
                })
                continue

            seq_base    = norm(seq_step.get("base_part"))
            seq_joining = norm(seq_step.get("joining_part"))

            if ffa_base != seq_base or ffa_joining != seq_joining:
                mismatches.append({
                    "step_id": step_id,
                    "reason": "mismatch",
                    "ffa_base": ffa_base,
                    "ffa_joining": ffa_joining,
                    "seq_base": seq_base,
                    "seq_joining": seq_joining,
                })

        # ── print per-assembly results ────────────────────────────────────────
        print(f"\n{'─' * 72}")
        status = "✗  MISMATCHES FOUND" if mismatches else "✓  OK"
        print(f"ASSEMBLY: {assembly_name}   [{status}]")
        print(f"  FFA steps: {len(ffa_by_id)}   |   Sequence steps: {len(seq_by_id)}")

        if mismatches:
            assemblies_with_mismatches.append(assembly_name)
            total_mismatches += len(mismatches)
            col = "{:<8} {:<30} {:<30}"
            print()
            print("  NOT MATCHING:")
            print(f"  {'Step':<8} {'FFA  base_part_id → joining_part_id':<38}   {'Sequence  base_part → joining_part'}")
            print(f"  {'─'*7} {'─'*38}   {'─'*38}")
            for m in mismatches:
                ffa_side = f"{m['ffa_base']} → {m['ffa_joining']}"
                seq_side = f"{m['seq_base']} → {m['seq_joining']}"
                note = f"  [{m['reason']}]" if m["reason"] != "mismatch" else ""
                print(f"  {m['step_id']:<8} {ffa_side:<40}  {seq_side}{note}")
        else:
            print("  All steps match.")

    # ── summary ───────────────────────────────────────────────────────────────
    print(f"\n{'=' * 72}")
    print("SUMMARY")
    print(f"  Assemblies checked : {total_assemblies}")
    print(f"  Steps checked      : {total_steps_checked}")
    print(f"  Total mismatches   : {total_mismatches}")
    if assemblies_with_mismatches:
        print(f"  Assemblies affected: {', '.join(assemblies_with_mismatches)}")
    else:
        print("  All assemblies fully aligned ✓")
    print("=" * 72)


if __name__ == "__main__":
    main()
