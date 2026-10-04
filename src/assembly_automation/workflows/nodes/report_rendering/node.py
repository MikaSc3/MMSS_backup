"""Deterministic multi-profile rendering of the final report model."""

import json
from pathlib import Path
import re
from typing import Any, Mapping

from .html_renderer import render_html
from .model import ImageResolver, load_report
from .settings import ReportRenderingSettings


def _write_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _write_json(path: Path, value: Any) -> None:
    _write_text(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def _slug(value: Any) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "assembly")).strip("._")
    return cleaned or "assembly"


def run_report_rendering(
    *, report: str | Path | Mapping[str, Any], output_dir: str | Path,
    settings: Mapping[str, Any] | None = None,
    image_roots: Mapping[str, str | Path] | None = None,
) -> dict[str, Any]:
    """Render configured HTML/PDF profiles and an atomic manifest."""
    configured = ReportRenderingSettings.from_mapping(settings)
    if not configured.enabled:
        return {"status": "disabled", "artifacts": {}}
    model = load_report(report)
    target = Path(output_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)
    images = ImageResolver(image_roots)
    overview = model["assembly_overview"]
    base_name = _slug(overview.get("assembly_name") or overview.get("assembly_name_guess"))
    artifacts: dict[str, dict[str, str]] = {}
    rendered: dict[str, Any] = {}
    for profile_name, profile in configured.profiles.items():
        if not profile.enabled:
            continue
        profile_artifacts = {}
        profile_info = {"findings_rendered": min(len(model["key_findings"]), profile.max_findings),
                        "recommendations_rendered": min(len(model["recommendations"]),
                                                        profile.max_recommendations),
                        "steps_rendered": len(model["steps"]) if profile.include_steps else 0,
                        "parts_rendered": len(model["parts"]) if profile.include_parts else 0}
        if "html" in configured.formats:
            html_path = target / f"{base_name}_ffa_{profile_name}.html"
            _write_text(html_path, render_html(model, profile_name, profile,
                                               configured.style, images))
            profile_artifacts["html"] = str(html_path)
        artifacts[profile_name] = profile_artifacts
        rendered[profile_name] = profile_info
    manifest = {
        "status": "complete", "profiles": rendered, "artifacts": artifacts,
        "images": {"used": sorted(images.used), "missing": sorted(images.missing)},
        "settings": configured.to_dict(),
    }
    manifest_path = target / "rendering_manifest.json"
    _write_json(manifest_path, manifest)
    return {"status": "complete", "output_dir": str(target), "artifacts": artifacts,
            "manifest": str(manifest_path), "result": manifest}
