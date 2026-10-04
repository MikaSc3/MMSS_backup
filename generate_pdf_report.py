"""Generate the FFA PDF for an existing completed product session."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from assembly_automation.workflows.nodes.pdf_report import run_pdf_report


def _active_revision(session: Path) -> str:
    manifest = session / "manifest.json"
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        revision = data.get("active_sequence_revision")
        if isinstance(revision, str) and revision:
            return revision
    reports = sorted((session / "reports").glob("r*/report.json"))
    if not reports:
        raise FileNotFoundError(f"No synthesized report found in session: {session}")
    return reports[-1].parent.name


def generate(session: Path, revision: str | None = None, output_dir: Path | None = None) -> dict:
    session = session.resolve(strict=True)
    revision = revision or _active_revision(session)
    report = session / "reports" / revision / "report.json"
    if not report.is_file():
        raise FileNotFoundError(f"Report not found: {report}")
    target = output_dir.resolve() if output_dir else session / "reports" / revision / "rendered"
    return run_pdf_report(report=report, output_dir=target, image_roots={
        "preprocessing_images": session / "preprocessing/images",
        "sequence_renderings": session / "sequence/revisions" / revision / "renderings",
    })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    parser.add_argument("--revision")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        result = generate(args.session, args.revision, args.output_dir)
    except Exception as exc:
        print(f"PDF generation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"PDF: {result['artifact']}")
    print(f"Manifest: {result['manifest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
