"""Manual PDF-report smoke test for the completed Stehlager session.

Run from the repository root:
    python scripts/test_pdf_report_existing_session.py
"""

from __future__ import annotations

import json
from pathlib import Path
import sys


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = WORKSPACE_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from assembly_automation.workflows.nodes.pdf_report import run_pdf_report


SESSION = Path(
    r"C:\Users\Mika\Desktop\apa_from_cad_save\data\sessions\2026-09-25_103726_Stehlager_Sicherungsring_94fad0a1"
)
REVISION = "r001"


def main() -> int:
    report = SESSION / "reports" / REVISION / "report.json"
    preprocessing_images = SESSION / "preprocessing" / "images"
    sequence_renderings = SESSION / "sequence" / "revisions" / REVISION / "renderings"
    output_dir = SESSION / "reports" / REVISION / "rendered"

    for required in (report, preprocessing_images, sequence_renderings):
        if not required.exists():
            raise FileNotFoundError(f"Required test input is missing: {required}")

    print("Generating FFA PDF report...")
    print(f"Session: {SESSION}")
    result = run_pdf_report(
        report=report,
        output_dir=output_dir,
        image_roots={
            "preprocessing_images": preprocessing_images,
            "sequence_renderings": sequence_renderings,
        },
        filename="Stehlager_Sicherungsring_ffa_report_test.pdf",
    )

    pdf_path = Path(result["artifact"])
    manifest_path = Path(result["manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not pdf_path.is_file() or pdf_path.stat().st_size == 0:
        raise RuntimeError(f"PDF was not created correctly: {pdf_path}")

    print("PDF generation complete.")
    print(f"PDF:      {pdf_path}")
    print(f"Size:     {pdf_path.stat().st_size:,} bytes")
    print(f"Pages:    {manifest['pages']}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
