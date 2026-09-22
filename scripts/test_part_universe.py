"""Generate part universes for all assemblies in the latest STEP-parser run."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE_ROOT / "src"))

from assembly_automation.stepparser.io.metadata_manager import write_json
from assembly_automation.stepparser.rendering.distance_diagram import create_distance_diagram
from assembly_automation.stepparser.analysis.interlocking import analyze_interlocking
from assembly_automation.stepparser.io.step_loader import load_step
from assembly_automation.stepparser.settings import InterlockingSettings


def latest_run(root):
    candidates = sorted((p for p in root.iterdir() if p.is_dir()
                         and re.match(r"^\d{4}-\d{2}-\d{2}_\d{6}", p.name)), reverse=True)
    for candidate in candidates:
        if (candidate / "batch_summary.json").is_file() or (candidate / "manifest.json").is_file():
            return candidate
        if any(candidate.rglob("manifest.json")):
            return candidate
    raise ValueError(f"No timestamped parser runs found in {root}; use --run-dir PATH")


def assembly_folders(run):
    """Discover nested assembly runs without letting a root manifest hide them."""
    folders = set()
    for name in ("manifest.json", "bom.json", "assembly.json"):
        folders.update(path.parent for path in run.rglob(name))
    # Include assembly folders that failed before writing a manifest or exports.
    folders.update(path for path in run.rglob("*") if path.is_dir() and re.match(r"^\d{3}_", path.name))
    batch_file = run / "batch_summary.json"
    if batch_file.is_file():
        batch = json.loads(batch_file.read_text(encoding="utf-8-sig"))
        for entry in batch.get("runs", []):
            output = Path(entry["output"])
            candidate = output.resolve() if output.is_absolute() else (run / output).resolve()
            if candidate.is_relative_to(run):
                folders.add(candidate)
    # A batch manifest describes the container, not an assembly itself.
    if any(path != run for path in folders) and not (run / "bom.json").is_file() and not (run / "assembly.json").is_file():
        folders.discard(run)
    return sorted(folders)


def ensure_interlocking(session, manifest):
    path = session / "interlocking.json"
    if path.is_file():
        return
    settings = InterlockingSettings(**manifest.get("settings", {}).get("interlocking", {}))
    relations = json.loads((session / "spatial_relations.json").read_text(encoding="utf-8-sig"))
    if settings.mode == "contact_direction_proxy":
        from types import SimpleNamespace
        bom = json.loads((session / "bom.json").read_text(encoding="utf-8-sig"))
        loaded_instances = [SimpleNamespace(instance_id=item["instance_id"],
                                            center_of_mass=item["center_of_mass"])
                            for item in bom["instances"]]
        print("Calculating missing contact-direction interlocking proxy", flush=True)
    else:
        name, expected = manifest.get("input", {}).get("name"), manifest.get("input", {}).get("sha256")
        candidates = list((WORKSPACE_ROOT / "data/input").rglob(name)) if name else []
        source = next((item for item in candidates if item.is_file() and expected
                       and hashlib.sha256(item.read_bytes()).hexdigest() == expected), None)
        if source is None:
            raise FileNotFoundError("Original STEP not found or hash does not match; cannot calculate interlocking")
        print(f"Calculating sampled-clearance interlocking from: {source.name}", flush=True)
        loaded_instances = load_step(source).instances
    def progress(stage, complete, total):
        if complete == total or complete % 6 == 0:
            print(f"[{stage}] {complete}/{total}", flush=True)
    result = analyze_interlocking(loaded_instances, settings, relations, progress=progress)
    write_json(path, result)
    if "interlocking.json" not in manifest.setdefault("artifacts", []):
        manifest["artifacts"].append("interlocking.json")
    manifest.setdefault("stages", {})["interlocking"] = result["status"]
    write_json(session / "manifest.json", manifest)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", "--session-dir", dest="run_dir", type=Path,
                        help="Override with a batch directory or an individual assembly run")
    parser.add_argument("--min-dot-radius", type=float, default=6, help="Minimum dot radius in pixels")
    parser.add_argument("--max-dot-radius", type=float, default=36, help="Maximum dot radius in pixels")
    args = parser.parse_args(argv)
    try:
        run = (args.run_dir or latest_run(WORKSPACE_ROOT / "data/stepparser_tests")).resolve()
        sessions = assembly_folders(run)
        if not sessions:
            raise ValueError(f"No assembly manifests in {run}")
        print(f"Run: {run}\nAssemblies: {len(sessions)}", flush=True)
        results = []
        for index, session in enumerate(sessions, 1):
            item = {"assembly": session.name, "session_dir": str(session)}
            results.append(item)
            print(f"\n[{index}/{len(sessions)}] {session.name}", flush=True)
            try:
                manifest_path = session / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig")) if manifest_path.is_file() else {}
                missing = [name for name in ("bom.json", "assembly.json", "manifest.json") if not (session / name).is_file()]
                if missing:
                    reason = f"Missing metadata: {', '.join(missing)}"
                    if manifest.get("error"):
                        reason += f"; parser error: {manifest['error']}"
                    item.update(status="skipped", reason=reason)
                    print(f"Skipped: {item['reason']}", flush=True)
                    continue
                ensure_interlocking(session, manifest)
                graph = create_distance_diagram(session, workspace_root=WORKSPACE_ROOT, layout="universe",
                                                min_dot_radius=args.min_dot_radius, max_dot_radius=args.max_dot_radius)
                item.update(status="complete", reference_part=graph["start_instance"],
                            image=str(session / "parts_distance_diagram.png"),
                            legend=str(session / graph["legend_file"]))
            except Exception as exc:
                item.update(status="failed", error=f"{type(exc).__name__}: {exc}")
                print(f"Universe failed: {item['error']}", file=sys.stderr, flush=True)
        counts = {status: sum(r["status"] == status for r in results) for status in ("complete", "skipped", "failed")}
        summary = run / "part_universe_summary.json"
        write_json(summary, {"run_dir": str(run), "counts": counts, "assemblies": results})
        print(f"\nFinished: {counts['complete']} complete, {counts['skipped']} skipped, {counts['failed']} failed.")
        print(f"Summary: {summary}")
        return 0 if counts["complete"] and not counts["failed"] else 1
    except Exception as exc:
        print(f"Part universe failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
