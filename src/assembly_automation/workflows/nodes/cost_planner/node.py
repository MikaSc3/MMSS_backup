from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from assembly_automation.workflows.runtime.node import run_llm_node

from .inputs import build_cost_prompt
from .structured_output import get_schema


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _catalogue(path: Path) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"catalogue_id", "equipment_class", "manufacturer", "model", "description",
                "unit_price", "currency", "price_date", "source", "notes"}
    if not rows:
        raise ValueError(f"Price catalogue contains no rows: {path}")
    if not required <= set(rows[0]):
        raise ValueError(f"Price catalogue is missing columns: {sorted(required-set(rows[0]))}")
    by_id = {row["catalogue_id"].strip(): row for row in rows if row["catalogue_id"].strip()}
    if len(by_id) != len(rows):
        raise ValueError("Every price catalogue row requires a unique catalogue_id")
    return rows, by_id


def run_cost_planner(*, artifacts: Mapping[str, Any], settings: Mapping[str, Any],
                     llm_profiles: Mapping[str, Any], context: Mapping[str, Any] | None = None,
                     output_path: str | Path | None = None, llm: Any = None) -> dict[str, Any]:
    catalogue_path = Path(str(settings.get("catalogue_path"))).resolve(strict=True)
    rows, by_id = _catalogue(catalogue_path)
    node_settings = {key: value for key, value in settings.items() if key != "catalogue_path"}
    csv_text = catalogue_path.read_text(encoding="utf-8-sig")
    match_path = Path(output_path).with_name("price_matches.json") if output_path else None
    response = run_llm_node(
        node_id="cost_planner", artifacts=artifacts, settings=node_settings,
        llm_profiles=llm_profiles, build_payload=build_cost_prompt, get_schema=get_schema,
        context={**dict(context or {}), "price_catalogue_csv": csv_text},
        output_path=match_path, llm=llm)
    layout = json.loads(Path(artifacts["layout"]).read_text(encoding="utf-8"))
    expected = {str(item["name"]) for item in layout.get("equipment", [])}
    matches = response["result"]["matches"]
    actual = [str(item["equipment_name"]) for item in matches]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError("Cost matches must cover every layout equipment name exactly once")
    currencies = set()
    total = Decimal("0")
    lines = []
    for match in matches:
        row = by_id.get(match.get("catalogue_id")) if match.get("catalogue_id") else None
        line = dict(match)
        if row is None:
            line.update({"unit_price": None, "currency": None, "subtotal": None,
                         "price_date": None, "source": None})
        else:
            price = Decimal(row["unit_price"])
            subtotal = price * int(match["quantity"])
            total += subtotal
            currencies.add(row["currency"])
            line.update({"manufacturer": row["manufacturer"], "model": row["model"],
                         "unit_price": float(price), "currency": row["currency"],
                         "subtotal": float(subtotal), "price_date": row["price_date"],
                         "source": row["source"]})
        lines.append(line)
    result = {"currency": next(iter(currencies)) if len(currencies) == 1 else None,
              "priced_subtotal": float(total),
              "is_complete": all(line["subtotal"] is not None for line in lines),
              "unpriced_equipment": [line["equipment_name"] for line in lines if line["subtotal"] is None],
              "line_items": lines,
              "catalogue": str(catalogue_path)}
    if output_path:
        _write(Path(output_path).resolve(), result)
    return {**response, "artifact": str(Path(output_path).resolve()) if output_path else None,
            "result": result, "matches_artifact": str(match_path) if match_path else None}
