"""Standalone smoke-test launcher for the new parser; no LLM calls."""

import argparse
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sys
import uuid

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE_ROOT / "src"))

from assembly_automation.stepparser.processor import StepProcessor
from assembly_automation.stepparser.settings import StepParserSettings
from assembly_automation.workflows.runtime.configuration import load_settings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step-file", type=Path,
                        help="STEP file override; defaults to the single STEP file in data/input/lager")
    parser.add_argument("--config", type=Path, default=WORKSPACE_ROOT / "configs" / "appsettingsv3.yaml")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--no-render", action="store_true")
    args = parser.parse_args(argv)
    try:
        step_file = args.step_file
        if step_file is None:
            input_dir = WORKSPACE_ROOT / "data" / "input" / "lager"
            candidates = sorted(path for path in input_dir.iterdir()
                                if path.is_file() and path.suffix.lower() in (".step", ".stp"))
            if len(candidates) != 1:
                raise ValueError(f"Expected one STEP file in {input_dir}, found {len(candidates)}. "
                                 "Use --step-file to select a file explicitly.")
            step_file = candidates[0]
        print(f"Input: {step_file}", flush=True)
        config = load_settings(args.config)
        settings = StepParserSettings.from_mapping(config.get("nodes", {}).get("step_preprocessing", {}))
        if not Path(settings.sam.checkpoint).is_absolute():
            settings = replace(settings, sam=replace(settings.sam,
                               checkpoint=str(WORKSPACE_ROOT / settings.sam.checkpoint)))
        if args.no_render:
            settings = replace(settings, rendering=replace(settings.rendering, enabled=False))
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        output = args.output_dir or WORKSPACE_ROOT / "data" / "stepparser_tests" / f"{timestamp}_{uuid.uuid4().hex[:8]}"
        print(f"Output: {output}", flush=True)
        print(f"SAM: {'enabled' if settings.sam.enabled else 'disabled (sam.enabled: false)'}", flush=True)

        def progress(stage, completed, total):
            print(f"[{stage}] {completed}" + (f"/{total}" if total is not None else ""), flush=True)

        result = StepProcessor(settings).process_step_file(step_file, output, progress=progress)
        print(f"Result: {result['status']} ({result['elapsed_seconds']:.2f}s)")
        return 0 if result["status"] == "complete" else 1
    except Exception as exc:
        print(f"STEP parser failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
