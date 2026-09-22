"""Thin workflow adapter around the standalone STEP processor."""

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from assembly_automation.stepparser import StepParserSettings, StepProcessor


def run_step_preprocessing(
    step_file: str | Path,
    output_dir: str | Path,
    settings: StepParserSettings | Mapping[str, Any] | None = None,
    *,
    progress: Callable[[str, int, int | None], None] | None = None,
) -> dict[str, Any]:
    """Run the parser once and expose its stable workflow artifact references.

    ``settings`` is the value below ``nodes.step_preprocessing``. Configuration
    file loading and session-directory creation belong to the workflow runtime.
    """
    parser_settings = (
        settings
        if isinstance(settings, StepParserSettings)
        else StepParserSettings.from_mapping(dict(settings or {}))
    )
    source = Path(step_file).resolve()
    output = Path(output_dir).resolve()
    manifest = StepProcessor(parser_settings).process_step_file(
        source, output, progress=progress
    )

    return {
        "status": manifest["status"],
        "step_file": str(source),
        "output_dir": str(output),
        "artifacts": {
            "manifest": str(output / "manifest.json"),
            "assembly": str(output / "assembly.json"),
            "bom": str(output / "bom.json"),
            "spatial_relations": str(output / "spatial_relations.json"),
            "interlocking": str(output / "interlocking.json"),
            "images": str(output / "images"),
        },
    }
