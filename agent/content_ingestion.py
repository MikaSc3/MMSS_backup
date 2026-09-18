"""Document ingestion helpers for the agent-driven app workflow v3."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, List, Optional


TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}
JSON_EXTENSIONS = {".json"}
CSV_EXTENSIONS = {".csv"}
EXCEL_EXTENSIONS = {".xls", ".xlsx"}
MARKITDOWN_EXTENSIONS = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".html", ".htm"}


@dataclass
class IngestedDocument:
    source_path: str
    file_name: str
    file_type: str
    extraction_backend: str
    text: str
    tables: List[dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class DocumentBundle:
    documents: List[IngestedDocument] = field(default_factory=list)
    combined_markdown: str = ""
    warnings: List[str] = field(default_factory=list)


def ingest_documents(
    paths: Iterable[str | Path],
    output_dir: Optional[str | Path] = None,
    *,
    prefer_markitdown: bool = True,
) -> DocumentBundle:
    """Ingest user-provided documents into markdown/text.

    Optional converters are best-effort. Missing MarkItDown never breaks direct
    TXT/MD/JSON/CSV/Excel ingestion.
    """
    out_dir = Path(output_dir) if output_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    bundle = DocumentBundle()
    for raw_path in paths or []:
        path = Path(raw_path)
        try:
            doc = ingest_document(path, prefer_markitdown=prefer_markitdown)
        except Exception as exc:
            doc = IngestedDocument(
                source_path=str(path),
                file_name=path.name,
                file_type=path.suffix.lower(),
                extraction_backend="error",
                text="",
                warnings=[f"Could not ingest document: {exc}"],
            )
        bundle.documents.append(doc)
        bundle.warnings.extend(doc.warnings)

        if out_dir:
            safe_stem = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in path.stem)
            target = out_dir / f"{safe_stem}.md"
            target.write_text(_document_to_markdown(doc), encoding="utf-8")

    bundle.combined_markdown = "\n\n".join(_document_to_markdown(doc) for doc in bundle.documents)
    return bundle


def ingest_document(path: Path, *, prefer_markitdown: bool = True) -> IngestedDocument:
    """Ingest a single file."""
    path = Path(path)
    suffix = path.suffix.lower()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(path)

    if suffix in TEXT_EXTENSIONS:
        return _read_text(path)
    if suffix in JSON_EXTENSIONS:
        return _read_json(path)
    if suffix in CSV_EXTENSIONS:
        return _read_csv(path)
    if suffix in EXCEL_EXTENSIONS:
        return _read_excel(path)
    if prefer_markitdown and suffix in MARKITDOWN_EXTENSIONS:
        return _read_markitdown(path)

    return IngestedDocument(
        source_path=str(path),
        file_name=path.name,
        file_type=suffix,
        extraction_backend="unsupported",
        text="",
        warnings=[f"Unsupported document type '{suffix}' for {path.name}"],
    )


def _read_text(path: Path) -> IngestedDocument:
    text = path.read_text(encoding="utf-8", errors="replace")
    return IngestedDocument(str(path), path.name, path.suffix.lower(), "text", text)


def _read_json(path: Path) -> IngestedDocument:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    text = "```json\n" + json.dumps(data, indent=2, ensure_ascii=False) + "\n```"
    return IngestedDocument(str(path), path.name, path.suffix.lower(), "json", text)


def _read_csv(path: Path) -> IngestedDocument:
    warnings: List[str] = []
    try:
        import pandas as pd

        df = pd.read_csv(path)
        text = df.to_markdown(index=False)
        tables = [{"columns": list(df.columns), "rows": len(df)}]
        backend = "pandas_csv"
    except Exception as exc:
        warnings.append(f"pandas CSV read failed, using csv fallback: {exc}")
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
            rows = list(csv.reader(f))
        text = "\n".join([", ".join(row) for row in rows])
        tables = [{"rows": max(0, len(rows) - 1)}]
        backend = "csv"
    return IngestedDocument(str(path), path.name, path.suffix.lower(), backend, text, tables, warnings)


def _read_excel(path: Path) -> IngestedDocument:
    try:
        import pandas as pd

        sheets = pd.read_excel(path, sheet_name=None)
    except Exception as exc:
        return IngestedDocument(
            str(path),
            path.name,
            path.suffix.lower(),
            "excel_error",
            "",
            warnings=[f"Could not read Excel file with pandas: {exc}"],
        )

    chunks: List[str] = []
    tables: List[dict] = []
    for sheet_name, df in sheets.items():
        chunks.append(f"## Sheet: {sheet_name}\n\n{df.to_markdown(index=False)}")
        tables.append({"sheet": str(sheet_name), "columns": list(df.columns), "rows": len(df)})
    return IngestedDocument(str(path), path.name, path.suffix.lower(), "pandas_excel", "\n\n".join(chunks), tables)


def _read_markitdown(path: Path) -> IngestedDocument:
    try:
        from markitdown import MarkItDown
    except Exception as exc:
        return IngestedDocument(
            str(path),
            path.name,
            path.suffix.lower(),
            "markitdown_missing",
            "",
            warnings=[f"MarkItDown is not installed; could not convert {path.name}: {exc}"],
        )

    try:
        result: Any = MarkItDown().convert(str(path))
        text = getattr(result, "text_content", None) or str(result)
        return IngestedDocument(str(path), path.name, path.suffix.lower(), "markitdown", text)
    except Exception as exc:
        return IngestedDocument(
            str(path),
            path.name,
            path.suffix.lower(),
            "markitdown_error",
            "",
            warnings=[f"MarkItDown failed for {path.name}: {exc}"],
        )


def _document_to_markdown(doc: IngestedDocument) -> str:
    warnings = "\n".join(f"- {w}" for w in doc.warnings)
    warning_block = f"\n\n### Warnings\n{warnings}" if warnings else ""
    body = doc.text.strip() if doc.text else "(no extracted text)"
    return (
        f"# {doc.file_name}\n\n"
        f"- Source: `{doc.source_path}`\n"
        f"- Type: `{doc.file_type}`\n"
        f"- Backend: `{doc.extraction_backend}`"
        f"{warning_block}\n\n"
        f"## Extracted Content\n\n{body}"
    )
