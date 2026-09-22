"""Standalone smoke-test launcher for the new parser; no LLM calls."""

import argparse
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import re
import sys
import uuid

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE_ROOT / "src"))

from assembly_automation.stepparser.processor import StepProcessor
from assembly_automation.stepparser.io.metadata_manager import write_json
from assembly_automation.stepparser.rendering.distance_diagram import create_distance_diagram
from assembly_automation.stepparser.settings import StepParserSettings
from assembly_automation.workflows.runtime.configuration import load_settings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step-file", type=Path,
                        help="Process one STEP file instead of all files in the input folder")
    parser.add_argument("--input-dir", type=Path, default=WORKSPACE_ROOT / "data/input/lager")
    parser.add_argument("--config", type=Path, default=WORKSPACE_ROOT / "configs" / "appsettingsv3.yaml")
    parser.add_argument("--output-dir", type=Path, help="Run folder for one input; batch folder for multiple inputs")
    parser.add_argument("--no-render", action="store_true")
    args = parser.parse_args(argv)
    try:
        step_files = [args.step_file] if args.step_file else sorted(path for path in args.input_dir.iterdir()
                                if path.is_file() and path.suffix.lower() in (".step", ".stp"))
        if not step_files:
            raise ValueError(f"No STEP files found in {args.input_dir}")
        print(f"Inputs: {len(step_files)}", flush=True)
        config = load_settings(args.config)
        settings = StepParserSettings.from_mapping(config.get("nodes", {}).get("step_preprocessing", {}))
        print(f"Config: {args.config.resolve()}", flush=True)
        print(f"Assembly views: {', '.join(settings.rendering.assembly_views)}", flush=True)
        print(f"Part views: {', '.join(settings.rendering.part_views)}", flush=True)
        print(f"Exploded views: {', '.join(settings.rendering.exploded_views)}", flush=True)
        if not Path(settings.sam.checkpoint).is_absolute():
            settings = replace(settings, sam=replace(settings.sam,
                               checkpoint=str(WORKSPACE_ROOT / settings.sam.checkpoint)))
        if args.no_render:
            settings = replace(settings, rendering=replace(settings.rendering, enabled=False))
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        output = args.output_dir or WORKSPACE_ROOT / "data" / "stepparser_tests" / f"{timestamp}_{uuid.uuid4().hex[:8]}"
        if output.exists() and any(output.iterdir()):
            raise FileExistsError(f"Use an empty output directory: {output}")
        print(f"Output: {output}", flush=True)
        print(f"SAM: {'enabled' if settings.sam.enabled else 'disabled (sam.enabled: false)'}", flush=True)

        def progress(stage, completed, total):
            print(f"[{stage}] {completed}" + (f"/{total}" if total is not None else ""), flush=True)

        runs = []
        for index, step_file in enumerate(step_files, 1):
            name = re.sub(r'[^\w.-]+', '_', step_file.stem).strip('._')[:100] or 'assembly'
            run_output = output / f"{index:03d}_{name}" if len(step_files) > 1 else output
            entry = {"input": str(step_file.resolve()), "output": str(run_output.resolve())}
            runs.append(entry)
            print(f"\nAssembly {index}/{len(step_files)}: {step_file.name}\nOutput: {run_output}", flush=True)
            try:
                result = StepProcessor(settings).process_step_file(step_file, run_output, progress=progress)
                entry["parser_status"] = result["status"]
                print(f"Result: {result['status']} ({result['elapsed_seconds']:.2f}s)")
                stats = result.get("spatial_relations_statistics")
                if stats:
                    print(f"Spatial relations: {stats['exact_calculations']} exact calculations, "
                          f"{stats['bbox_rejections']} distant pairs filtered, {stats['failed_pairs']} failures")
                if result["status"] == "failed":
                    raise ValueError(result.get("error", "Parser failed"))
                print("[distance_diagram] creating part universe", flush=True)
                create_distance_diagram(run_output, step_file=step_file, workspace_root=WORKSPACE_ROOT)
                entry["diagram_status"] = "complete"
                entry["status"] = result["status"]
            except Exception as exc:
                entry.update(status="failed", error=f"{type(exc).__name__}: {exc}")
                print(f"Assembly failed: {entry['error']}", file=sys.stderr, flush=True)
            if len(step_files) > 1:
                write_json(output / "batch_summary.json", {"runs": runs, "total_inputs": len(step_files)})
        successful = sum(item["status"] == "complete" for item in runs)
        print(f"\nFinished: {successful}/{len(runs)} complete. Output: {output}", flush=True)
        return 0 if successful == len(runs) else 1
    except Exception as exc:
        print(f"STEP parser failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
