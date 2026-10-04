"""Deterministic ingestion of user-authorized supporting documents."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
from typing import Any, Iterable
import xml.etree.ElementTree as ET
import zipfile


class DocumentStore:
    """Copy supporting files into the session and extract reviewable text."""

    def __init__(self, session_root: str | Path, *, max_file_bytes: int = 20_000_000,
                 max_return_chars: int = 30000):
        self.root = Path(session_root).resolve() / "09_user_agent" / "documents"
        self.raw = self.root / "raw"
        self.extracted = self.root / "extracted"
        self.max_file_bytes = max_file_bytes
        self.max_return_chars = max_return_chars

    def ingest(self, paths: Iterable[str | Path]) -> dict[str, Any]:
        self.raw.mkdir(parents=True, exist_ok=True)
        self.extracted.mkdir(parents=True, exist_ok=True)
        documents, warnings = [], []
        for source_value in paths:
            source = Path(source_value).resolve(strict=True)
            if not source.is_file():
                raise ValueError(f"Supporting document is not a file: {source}")
            if source.stat().st_size > self.max_file_bytes:
                raise ValueError(f"Supporting document exceeds size limit: {source.name}")
            target = self.raw / source.name
            if target.exists() and target.read_bytes() != source.read_bytes():
                target = self.raw / f"{source.stem}_{len(documents) + 1}{source.suffix}"
            if not target.exists():
                shutil.copy2(source, target)
            try:
                text, backend = self._extract(target)
                warning = None if text.strip() else "No text was extracted."
            except Exception as exc:
                text, backend, warning = "", "failed", f"{type(exc).__name__}: {exc}"
            extracted_path = self.extracted / f"{target.name}.md"
            extracted_path.write_text(text, encoding="utf-8")
            record = {"file_name": target.name, "source_path": str(source),
                      "stored_path": str(target), "extracted_path": str(extracted_path),
                      "backend": backend, "characters": len(text), "warning": warning,
                      "excerpt": text[:6000]}
            documents.append(record)
            if warning:
                warnings.append(f"{target.name}: {warning}")
        manifest = {"documents": [{key: value for key, value in item.items() if key != "excerpt"}
                                   for item in documents], "warnings": warnings}
        (self.root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        returned = {"documents": documents, "warnings": warnings}
        serialized = json.dumps(returned, ensure_ascii=False)
        if len(serialized) > self.max_return_chars:
            remaining = max(0, self.max_return_chars // max(1, len(documents)))
            for item in documents:
                item["excerpt"] = item["excerpt"][:remaining]
            returned["truncated"] = True
        return returned

    @staticmethod
    def _extract(path: Path) -> tuple[str, str]:
        suffix = path.suffix.lower()
        if suffix in {".txt", ".md", ".json", ".yaml", ".yml", ".csv", ".tsv"}:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            if suffix == ".json":
                text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
            elif suffix in {".csv", ".tsv"}:
                delimiter = "\t" if suffix == ".tsv" else ","
                rows = list(csv.reader(text.splitlines(), delimiter=delimiter))
                text = "\n".join(" | ".join(cell.strip() for cell in row) for row in rows)
            return text, "standard_library"
        if suffix == ".docx":
            with zipfile.ZipFile(path) as archive:
                root = ET.fromstring(archive.read("word/document.xml"))
            namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            paragraphs = []
            for paragraph in root.iter(namespace + "p"):
                values = [node.text or "" for node in paragraph.iter(namespace + "t")]
                if values:
                    paragraphs.append("".join(values))
            return "\n".join(paragraphs), "docx_xml"
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError as exc:
                raise RuntimeError("Install pypdf to ingest PDF documents") from exc
            reader = PdfReader(str(path))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages), "pypdf"
        raise ValueError(f"Unsupported supporting-document type: {suffix or '(none)'}")
