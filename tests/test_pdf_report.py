import json
from pathlib import Path

from generate_pdf_report import _active_revision


def test_active_revision_from_manifest(tmp_path: Path):
    (tmp_path / "manifest.json").write_text(
        json.dumps({"active_sequence_revision": "r007"}), encoding="utf-8")
    assert _active_revision(tmp_path) == "r007"


def test_active_revision_falls_back_to_latest_report(tmp_path: Path):
    for revision in ("r001", "r003"):
        path = tmp_path / "reports" / revision / "report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
    assert _active_revision(tmp_path) == "r003"
