"""
Build an HTML overview of eval/test assemblies with preview images and counts.

Output:
    - evaluation/dataset_overview.html

Columns:
    Name der Baugruppe | ISO-1 | ISO-1 Explosionsansicht | Anz. Bauteile | Anz. Montageschritte
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Iterable, List

try:
    from PIL import Image
except ModuleNotFoundError:
    Image = None


REPO_ROOT = Path(__file__).resolve().parents[1]

EVAL_GT_DIR = REPO_ROOT / "data" / "ground_truth" / "ffa_ground_truth_evaluierungsdatenMASTER"
TEST_GT_DIR = REPO_ROOT / "data" / "ground_truth" / "ffa_ground_truth_testdatenMASTER"

EVAL_PROCESSED_ROOTS = [
    REPO_ROOT / "data" / "processed" / "Evaluierungsset",
    REPO_ROOT / "data" / "processed" / "EVALSET_RED",
]
TEST_PROCESSED_ROOTS = [
    REPO_ROOT / "data" / "processed" / "Testset",
]

OUTPUT_HTML = REPO_ROOT / "evaluation" / "dataset_overview.html"
THUMB_DIR = REPO_ROOT / "evaluation" / "dataset_overview_assets"
THUMB_WIDTH_PX = 140
THUMB_HEIGHT_PX = 116


@dataclass
class AssemblyRow:
    assembly_name: str
    iso1_path: Path | None
    iso1_exp_path: Path | None
    total_parts: int | str
    total_steps: int | str
    source_dir: Path | None


def load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def gt_report_paths(gt_dir: Path) -> List[Path]:
    return sorted(
        path for path in gt_dir.glob("*_ffa_assessment_enum_gt.json")
        if path.is_file()
    )


def assembly_name_from_gt(path: Path) -> str:
    suffix = "_ffa_assessment_enum_gt"
    stem = path.stem
    return stem[:-len(suffix)] if stem.endswith(suffix) else stem


def find_processed_dir(assembly_name: str, candidate_roots: Iterable[Path]) -> Path | None:
    for root in candidate_roots:
        candidate = root / assembly_name / f"assembly_{assembly_name}"
        if candidate.exists():
            return candidate
    return None


def pick_image(assembly_dir: Path | None, pattern: str) -> Path | None:
    if assembly_dir is None:
        return None
    matches = sorted(assembly_dir.glob(pattern))
    return matches[0] if matches else None


def load_total_parts(assembly_dir: Path | None, assembly_name: str) -> int | str:
    if assembly_dir is None:
        return "?"

    overview_path = assembly_dir / f"{assembly_name}_Overview_Stepparser.json"
    if overview_path.exists():
        data = load_json(overview_path)
        if isinstance(data, dict):
            total_parts = data.get("total_parts")
            if isinstance(total_parts, int):
                return total_parts

    bom_path = assembly_dir / f"{assembly_name}_BOM.json"
    if bom_path.exists():
        data = load_json(bom_path)
        if isinstance(data, list):
            total = 0
            for item in data:
                if isinstance(item, dict):
                    qty = item.get("quantity_in_assembly", 1)
                    total += qty if isinstance(qty, int) else 1
            return total

    return "?"


def load_total_steps(gt_path: Path) -> int | str:
    data = load_json(gt_path)
    if isinstance(data, list):
        return len(data)
    return "?"


def build_rows(gt_dir: Path, candidate_roots: Iterable[Path]) -> List[AssemblyRow]:
    rows: List[AssemblyRow] = []
    for gt_path in gt_report_paths(gt_dir):
        assembly_name = assembly_name_from_gt(gt_path)
        assembly_dir = find_processed_dir(assembly_name, candidate_roots)
        rows.append(
            AssemblyRow(
                assembly_name=assembly_name,
                iso1_path=pick_image(assembly_dir, "*-iso1_transp_0_0.png"),
                iso1_exp_path=pick_image(assembly_dir, "*-iso1_exp_transp_0_0.png"),
                total_parts=load_total_parts(assembly_dir, assembly_name),
                total_steps=load_total_steps(gt_path),
                source_dir=assembly_dir,
            )
        )
    return rows


def rel_href(path: Path | None) -> str:
    if path is None:
        return ""
    return path.resolve().as_uri()


def ensure_thumbnail(path: Path | None, max_height_px: int = THUMB_HEIGHT_PX, max_width_px: int = THUMB_WIDTH_PX) -> Path | None:
    if path is None:
        return None
    if Image is None:
        return path

    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    thumb_name = f"{path.parent.parent.name}__w{max_width_px}_h{max_height_px}__{path.name}"
    thumb_path = THUMB_DIR / thumb_name

    try:
        source_mtime = path.stat().st_mtime
        if thumb_path.exists() and thumb_path.stat().st_mtime >= source_mtime:
            return thumb_path

        with Image.open(path) as img:
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            else:
                img = img.convert("RGBA")
            img.thumbnail((max_width_px, max_height_px))
            canvas = Image.new("RGBA", (max_width_px, max_height_px), (255, 255, 255, 0))
            offset_x = (max_width_px - img.width) // 2
            offset_y = (max_height_px - img.height) // 2
            canvas.paste(img, (offset_x, offset_y), img)
            canvas.save(thumb_path)
        return thumb_path
    except Exception:
        return path


def image_cell(path: Path | None, alt: str) -> str:
    if path is None:
        return '<span class="missing">-</span>'
    href = rel_href(path)
    thumb = ensure_thumbnail(path)
    src = rel_href(thumb)
    return (
        f'<a class="img-link" href="{href}" target="_blank" rel="noopener noreferrer">'
        f'<img src="{src}" alt="{escape(alt)}" loading="lazy" '
        f'width="{THUMB_WIDTH_PX}" height="{THUMB_HEIGHT_PX}" '
        f'style="width:{THUMB_WIDTH_PX}px;height:{THUMB_HEIGHT_PX}px;display:block;margin:0 auto;object-fit:contain;"></a>'
    )


def row_html(row: AssemblyRow) -> str:
    name = escape(row.assembly_name)
    return (
        "<tr>"
        f"<td class=\"col-name\"><div class=\"name\">{name}</div></td>"
        f"<td class=\"separator\"></td>"
        f"<td class=\"image\">{image_cell(row.iso1_path, f'{row.assembly_name} ISO1')}</td>"
        f"<td class=\"separator\"></td>"
        f"<td class=\"image\">{image_cell(row.iso1_exp_path, f'{row.assembly_name} ISO1 exp')}</td>"
        f"<td class=\"separator\"></td>"
        f"<td class=\"num\">{row.total_parts}</td>"
        f"<td class=\"separator\"></td>"
        f"<td class=\"num\">{row.total_steps}</td>"
        "</tr>"
    )


def sum_value(values: List[int | str]) -> str:
    ints = [value for value in values if isinstance(value, int)]
    return str(sum(ints)) if ints else "-"


def summary_row_html(rows: List[AssemblyRow]) -> str:
    return (
        "<tr class=\"summary-row\">"
        "<td class=\"col-name\"><div class=\"name\">Summe</div></td>"
        "<td class=\"separator\"></td>"
        "<td class=\"image\">-</td>"
        "<td class=\"separator\"></td>"
        "<td class=\"image\">-</td>"
        "<td class=\"separator\"></td>"
        f"<td class=\"num\">{sum_value([row.total_parts for row in rows])}</td>"
        f"<td class=\"separator\"></td>"
        f"<td class=\"num\">{sum_value([row.total_steps for row in rows])}</td>"
        "</tr>"
    )


def table_html(title: str, rows: List[AssemblyRow]) -> str:
    body = "\n".join(row_html(row) for row in rows)
    summary = summary_row_html(rows)
    return f"""
    <section>
      <h2>{escape(title)}</h2>
      <table>
        <thead>
          <tr>
            <th class="col-name">Name der Baugruppe</th>
            <th class="separator"></th>
            <th class="col-image">ISO-1</th>
            <th class="separator"></th>
            <th class="col-image">ISO-1 Explosionsansicht</th>
            <th class="separator"></th>
            <th class="col-num">Anz. Bauteile</th>
            <th class="separator"></th>
            <th class="col-num">Anz. Montageschritte</th>
          </tr>
        </thead>
        <tbody>
          {body}
          {summary}
        </tbody>
      </table>
    </section>
    """


def build_html(eval_rows: List[AssemblyRow], test_rows: List[AssemblyRow]) -> str:
    return f"""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dataset Overview</title>
  <style>
    @page {{
      size: A4 portrait;
      margin: 1.2cm;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      font-family: 'LM Roman 12', serif;
      margin: 0 auto;
      width: 18.6cm;
      color: black;
      background: #ffffff;
      line-height: 1.0;
      padding: 0;
    }}
    h1 {{
      margin: 0 0 0.35cm 0;
      font-size: 12pt;
      text-align: center;
      font-weight: bold;
    }}
    h2 {{
      margin: 0.45cm 0 0.12cm 0;
      font-size: 10pt;
      page-break-after: avoid;
      text-align: center;
      font-weight: bold;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      border-spacing: 0;
      margin: 0.15cm 0 0.45cm 0;
      table-layout: fixed;
      line-height: 1.0;
    }}
    th, td {{
      border: none;
      padding: 2px 4pt;
      vertical-align: middle;
      overflow-wrap: anywhere;
      font-size: 9pt;
      text-align: center;
      color: black;
      background-color: white;
    }}
    th {{
      background-color: white;
      font-size: 9pt;
      line-height: 1.15;
      font-weight: bold;
      white-space: nowrap;
      border-bottom: 1px solid black;
    }}
    tr {{
      page-break-inside: avoid;
    }}
    th.col-name, td.col-name {{
      width: 3cm;
    }}
    th.col-image, td.image {{
      width: 3.3cm;
    }}
    th.col-num, td.num {{
      width: 1.5cm;
    }}
    th.separator, td.separator {{
      width: 0.1cm;
      min-width: 0.1cm;
      max-width: 0.1cm;
      padding: 0;
      border: none;
      background-color: white;
    }}
    td.num {{
      font-weight: 600;
    }}
    td.image {{
      padding: 1px 2pt;
      text-align: center;
      vertical-align: middle;
    }}
    td.image a.img-link {{
      display: flex;
      justify-content: center;
      align-items: center;
      width: 100%;
      height: 100%;
    }}
    td img {{
      display: block;
      width: 70px;
      height: 58px;
      max-width: 70px;
      margin: 0 auto;
      border: none;
      background: white;
      object-fit: contain;
    }}
    .name {{
      font-weight: 700;
      font-size: 9pt;
      white-space: normal;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .summary-row td {{
      font-weight: 700;
      border-top: 1px solid black;
      background-color: white;
    }}
    .summary-row td.separator {{
      border-top: none;
    }}
    .missing {{
      color: black;
    }}
  </style>
</head>
<body>
  <h1>Dataset Overview</h1>
  {table_html("Evaluierungsdatensatz", eval_rows)}
  {table_html("Testdatensatz", test_rows)}
</body>
</html>
"""


def main() -> int:
    eval_rows = build_rows(EVAL_GT_DIR, EVAL_PROCESSED_ROOTS)
    test_rows = build_rows(TEST_GT_DIR, TEST_PROCESSED_ROOTS)
    OUTPUT_HTML.write_text(build_html(eval_rows, test_rows), encoding="utf-8")
    print(f"Saved HTML overview: {OUTPUT_HTML}")
    print(f"Eval rows: {len(eval_rows)}")
    print(f"Test rows: {len(test_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
