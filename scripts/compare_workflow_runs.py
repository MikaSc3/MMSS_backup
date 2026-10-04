"""Compare workflow duration and LLM token usage across product sessions.

Examples:
    python scripts/compare_workflow_runs.py
    python scripts/compare_workflow_runs.py --latest 3
    python scripts/compare_workflow_runs.py --include-incomplete --session Stehlager
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SESSIONS = ROOT / "data" / "sessions"
DEFAULT_OUTPUT = ROOT / "data" / "analytics" / "run_comparison"

NODE_ORDER = (
    "step_preprocessing",
    "assembly_analysis",
    "monopart_analysis",
    "bom_merge",
    "sequence_generation",
    "sequence_rendering",
    "interaction_analysis",
    "ffa_assessment",
    "ffa_scoring",
    "report_synthesis",
    "report_rendering",
)


@dataclass(frozen=True)
class CallRecord:
    session_id: str
    assembly: str
    status: str
    node: str
    call_id: str
    elapsed_seconds: float
    input_tokens: int
    output_tokens: int
    total_tokens: int
    llm_profile: str
    schema: str
    mode: str
    input_blocks: int
    images_used: int
    runlog: str


@dataclass(frozen=True)
class StageRecord:
    session_id: str
    node: str
    stage_id: str
    wall_seconds: float


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


def _integer(value: Any) -> int:
    return int(_number(value))


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _stage_node(stage_id: str) -> str:
    return stage_id.split(":", 1)[0]


def _assembly_name(manifest: dict[str, Any], session_id: str) -> str:
    source = manifest.get("input") if isinstance(manifest.get("input"), dict) else {}
    step_file = source.get("step_file")
    if isinstance(step_file, str) and step_file:
        return Path(step_file).stem
    components = session_id.split("_", 3)
    return components[3].rsplit("_", 1)[0] if len(components) == 4 else session_id


def load_session(session_root: Path) -> tuple[dict[str, Any], list[StageRecord], list[CallRecord]]:
    manifest = _read_json(session_root / "manifest.json")
    session_id = str(manifest.get("session_id") or session_root.name)
    status = str(manifest.get("status") or "unknown")
    assembly = _assembly_name(manifest, session_id)
    stages: list[StageRecord] = []
    stage_values = manifest.get("stages") if isinstance(manifest.get("stages"), dict) else {}
    for stage_id, value in stage_values.items():
        if not isinstance(value, dict):
            continue
        started = _timestamp(value.get("started_at"))
        finished = _timestamp(value.get("finished_at"))
        duration = max(0.0, (finished - started).total_seconds()) if started and finished else 0.0
        stages.append(StageRecord(session_id, _stage_node(str(stage_id)), str(stage_id), duration))

    calls: list[CallRecord] = []
    runlog_root = session_root / "runlog"
    for path in sorted(runlog_root.glob("**/*.run.json")) if runlog_root.is_dir() else []:
        payload = _read_json(path)
        execution = payload.get("execution") if isinstance(payload.get("execution"), dict) else {}
        usage = execution.get("token_usage") if isinstance(execution.get("token_usage"), dict) else {}
        try:
            fallback_node = path.relative_to(runlog_root).parts[0]
            relative = path.relative_to(session_root).as_posix()
        except ValueError:
            fallback_node, relative = "unknown", str(path)
        calls.append(CallRecord(
            session_id=session_id,
            assembly=assembly,
            status=status,
            node=str(execution.get("node") or fallback_node),
            call_id=path.name.removesuffix(".run.json"),
            elapsed_seconds=_number(execution.get("elapsed_seconds")),
            input_tokens=_integer(usage.get("input_tokens", usage.get("prompt_tokens"))),
            output_tokens=_integer(usage.get("output_tokens", usage.get("completion_tokens"))),
            total_tokens=_integer(usage.get("total_tokens")),
            llm_profile=str(execution.get("llm_profile") or "unknown"),
            schema=str(execution.get("schema") or ""),
            mode=str(execution.get("mode") or ""),
            input_blocks=len(payload.get("inputs") or []),
            images_used=len(payload.get("images_used") or []),
            runlog=relative,
        ))
    return manifest, stages, calls


def discover_sessions(
    root: Path, *, include_incomplete: bool, include_without_runlogs: bool,
    filters: list[str], latest: int,
) -> list[Path]:
    sessions = []
    if not root.is_dir():
        raise FileNotFoundError(f"Sessions directory does not exist: {root}")
    for path in sorted(item for item in root.iterdir() if item.is_dir() and item.name != ".drafts"):
        manifest_path = path / "manifest.json"
        if not manifest_path.is_file() or filters and not any(value.casefold() in path.name.casefold()
                                                              for value in filters):
            continue
        manifest = _read_json(manifest_path)
        if not include_incomplete and manifest.get("status") != "complete":
            continue
        if not include_without_runlogs and not any((path / "runlog").glob("**/*.run.json")):
            continue
        sessions.append(path)
    if latest > 0:
        sessions = sessions[-latest:]
    return sessions


def summarize_nodes(
    manifests: dict[str, dict[str, Any]], stages: Iterable[StageRecord],
    calls: Iterable[CallRecord],
) -> list[dict[str, Any]]:
    stage_map: dict[tuple[str, str], list[StageRecord]] = {}
    call_map: dict[tuple[str, str], list[CallRecord]] = {}
    for stage in stages:
        stage_map.setdefault((stage.session_id, stage.node), []).append(stage)
    for call in calls:
        call_map.setdefault((call.session_id, call.node), []).append(call)
    keys = set(stage_map) | set(call_map)
    rows = []
    for session_id, node in sorted(keys, key=lambda item: (item[0], _node_sort(item[1]))):
        node_stages = stage_map.get((session_id, node), [])
        node_calls = call_map.get((session_id, node), [])
        manifest = manifests[session_id]
        elapsed = [call.elapsed_seconds for call in node_calls]
        total_tokens = sum(call.total_tokens for call in node_calls)
        rows.append({
            "session_id": session_id,
            "assembly": _assembly_name(manifest, session_id),
            "status": str(manifest.get("status") or "unknown"),
            "node": node,
            "stage_wall_seconds": round(sum(stage.wall_seconds for stage in node_stages), 3),
            "stage_wall_minutes": round(sum(stage.wall_seconds for stage in node_stages) / 60, 3),
            "llm_calls": len(node_calls),
            "llm_elapsed_sum_seconds": round(sum(elapsed), 3),
            "llm_elapsed_max_seconds": round(max(elapsed, default=0.0), 3),
            "llm_elapsed_avg_seconds": round(sum(elapsed) / len(elapsed), 3) if elapsed else 0.0,
            "input_tokens": sum(call.input_tokens for call in node_calls),
            "output_tokens": sum(call.output_tokens for call in node_calls),
            "total_tokens": total_tokens,
            "tokens_per_call": round(total_tokens / len(node_calls), 1) if node_calls else 0.0,
            "llm_profiles": ", ".join(sorted({call.llm_profile for call in node_calls})),
        })
    return rows


def summarize_sessions(manifests: dict[str, dict[str, Any]], node_rows: list[dict[str, Any]],
                       stages: list[StageRecord], calls: list[CallRecord]) -> list[dict[str, Any]]:
    rows = []
    for session_id, manifest in sorted(manifests.items()):
        current_nodes = [row for row in node_rows if row["session_id"] == session_id]
        current_stages = [stage for stage in stages if stage.session_id == session_id]
        current_calls = [call for call in calls if call.session_id == session_id]
        stage_entries = manifest.get("stages") if isinstance(manifest.get("stages"), dict) else {}
        starts = [_timestamp(value.get("started_at")) for value in stage_entries.values()
                  if isinstance(value, dict)]
        finishes = [_timestamp(value.get("finished_at")) for value in stage_entries.values()
                    if isinstance(value, dict)]
        starts = [value for value in starts if value]
        finishes = [value for value in finishes if value]
        span = max(0.0, (max(finishes) - min(starts)).total_seconds()) if starts and finishes else 0.0
        rows.append({
            "session_id": session_id,
            "assembly": _assembly_name(manifest, session_id),
            "status": str(manifest.get("status") or "unknown"),
            "workflow_span_seconds": round(span, 3),
            "workflow_span_minutes": round(span / 60, 3),
            "stage_wall_sum_seconds": round(sum(stage.wall_seconds for stage in current_stages), 3),
            "llm_calls": len(current_calls),
            "llm_elapsed_sum_seconds": round(sum(call.elapsed_seconds for call in current_calls), 3),
            "input_tokens": sum(call.input_tokens for call in current_calls),
            "output_tokens": sum(call.output_tokens for call in current_calls),
            "total_tokens": sum(call.total_tokens for call in current_calls),
            "nodes": len(current_nodes),
        })
    return rows


def _node_sort(node: str) -> tuple[int, str]:
    try:
        return NODE_ORDER.index(node), node
    except ValueError:
        return len(NODE_ORDER), node


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    def cell(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")
    return [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
        *("| " + " | ".join(cell(value) for value in row) + " |" for row in rows),
    ]


def write_markdown(path: Path, sessions: list[dict[str, Any]], nodes: list[dict[str, Any]]) -> None:
    lines = [
        "# Workflow run comparison", "",
        "Stage wall time comes from manifest start/finish timestamps and represents user-visible phase time. "
        "LLM elapsed sum adds every model call; it can exceed stage wall time when part or step calls run concurrently. "
        "Tokens are provider-reported usage summed across all recorded calls.", "",
        "## Session totals", "",
        *_markdown_table(
            ["Session", "Assembly", "Status", "Workflow min", "Stage min", "LLM calls",
             "Input tokens", "Output tokens", "Total tokens"],
            [[row["session_id"], row["assembly"], row["status"], row["workflow_span_minutes"],
              round(row["stage_wall_sum_seconds"] / 60, 3), row["llm_calls"],
              row["input_tokens"], row["output_tokens"], row["total_tokens"]]
             for row in sessions]), "", "## Node detail", "",
        *_markdown_table(
            ["Session", "Node", "Stage s", "LLM sum s", "LLM max s", "Calls",
             "Input", "Output", "Total"],
            [[row["session_id"], row["node"], row["stage_wall_seconds"],
              row["llm_elapsed_sum_seconds"], row["llm_elapsed_max_seconds"],
              row["llm_calls"], row["input_tokens"], row["output_tokens"],
              row["total_tokens"]] for row in nodes]), "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _short_label(row: dict[str, Any]) -> str:
    session = str(row["session_id"])
    timestamp = session[:15].replace("_", " ")
    assembly = str(row["assembly"])
    assembly = assembly if len(assembly) <= 24 else assembly[:21] + "…"
    return f"{timestamp}\n{assembly}"


def create_chart(path: Path, sessions: list[dict[str, Any]], nodes: list[dict[str, Any]],
                 *, show: bool) -> None:
    from PIL import Image, ImageDraw, ImageFont

    def font(size: int, *, bold: bool = False):
        candidates = [
            Path("C:/Windows/Fonts/seguisb.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        ]
        for candidate in candidates:
            if candidate.is_file():
                return ImageFont.truetype(str(candidate), size)
        return ImageFont.load_default()

    session_ids = [row["session_id"] for row in sessions]
    node_names = sorted({row["node"] for row in nodes}, key=_node_sort)
    lookup = {(row["session_id"], row["node"]): row for row in nodes}
    palette = ["#315B7D", "#3F88C5", "#44A1A0", "#65B96E", "#A2C14E",
               "#E6B44A", "#E4853D", "#D95D5D", "#A85DA5", "#765FA8",
               "#64748B", "#9A7B58", "#2D7D6E", "#C45A84"]
    colors = {node: palette[index % len(palette)] for index, node in enumerate(node_names)}
    width = max(1500, 330 + len(sessions) * 210)
    height = 1120
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font, panel_font = font(30, bold=True), font(22, bold=True)
    label_font, small_font, small_bold = font(16), font(13), font(14, bold=True)
    draw.text((70, 34), "Assembly workflow run comparison", fill="#17212B", font=title_font)
    plot_left, plot_right = 105, width - 360
    plot_width = plot_right - plot_left
    bar_width = min(110, max(34, plot_width // max(1, len(sessions)) // 2))
    centers = [plot_left + plot_width * (index + 0.5) / len(sessions)
               for index in range(len(sessions))]

    time_values = {node: [lookup.get((session_id, node), {}).get("stage_wall_seconds", 0) / 60
                          for session_id in session_ids] for node in node_names}
    token_values = {node: [lookup.get((session_id, node), {}).get("total_tokens", 0) / 1000
                           for session_id in session_ids] for node in node_names}

    def panel(top: int, bottom: int, title: str, unit: str,
              values: dict[str, list[float]], total_format) -> None:
        totals = [sum(values[node][index] for node in node_names)
                  for index in range(len(sessions))]
        maximum = max(totals, default=0.0) * 1.12 or 1.0
        draw.text((plot_left, top - 48), title, fill="#17212B", font=panel_font)
        draw.text((plot_left, top - 20), unit, fill="#586574", font=small_font)
        for tick in range(6):
            value = maximum * tick / 5
            y = bottom - (bottom - top) * tick / 5
            draw.line((plot_left, y, plot_right, y), fill="#DCE3EA", width=1)
            draw.text((plot_left - 12, y), f"{value:.0f}", fill="#667585",
                      font=small_font, anchor="rm")
        for index, center in enumerate(centers):
            accumulated = 0.0
            for node in node_names:
                value = values[node][index]
                if value <= 0:
                    continue
                y_bottom = bottom - (bottom - top) * accumulated / maximum
                accumulated += value
                y_top = bottom - (bottom - top) * accumulated / maximum
                draw.rectangle((center - bar_width / 2, y_top,
                                center + bar_width / 2, y_bottom),
                               fill=colors[node], outline="white", width=1)
            y_total = bottom - (bottom - top) * accumulated / maximum
            draw.text((center, y_total - 8), total_format(accumulated),
                      fill="#24313D", font=small_bold, anchor="mb")

    panel(145, 465, "Workflow time by node", "Stage wall time (minutes)", time_values,
          lambda value: f"{value:.1f} min")
    panel(610, 930, "LLM token usage by node", "Tokens (thousands)", token_values,
          lambda value: f"{value:.1f}k")
    for center, row in zip(centers, sessions):
        draw.multiline_text((center, 950), _short_label(row), fill="#344250",
                            font=small_font, anchor="ma", align="center", spacing=3)
    legend_x, legend_y = plot_right + 45, 150
    draw.text((legend_x, legend_y - 40), "Nodes", fill="#17212B", font=panel_font)
    for index, node in enumerate(node_names):
        y = legend_y + index * 32
        draw.rounded_rectangle((legend_x, y, legend_x + 20, y + 20), radius=3,
                               fill=colors[node])
        draw.text((legend_x + 30, y + 10), node.replace("_", " "),
                  fill="#344250", font=label_font, anchor="lm")
    draw.text((70, height - 35),
              "Wall time uses manifest stage timestamps. Token usage sums all recorded LLM calls.",
              fill="#667585", font=small_font)
    image.save(path, format="PNG", optimize=True)
    if show:
        image.show()


def print_summary(rows: list[dict[str, Any]]) -> None:
    headers = ("Session", "Assembly", "Wall min", "Calls", "Input", "Output", "Total")
    values = [[row["session_id"], row["assembly"], f'{row["workflow_span_minutes"]:.2f}',
               str(row["llm_calls"]), f'{row["input_tokens"]:,}',
               f'{row["output_tokens"]:,}', f'{row["total_tokens"]:,}'] for row in rows]
    widths = [max(len(headers[index]), *(len(row[index]) for row in values))
              for index in range(len(headers))]
    print("  ".join(value.ljust(widths[index]) for index, value in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in values:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sessions-root", type=Path, default=DEFAULT_SESSIONS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--session", action="append", default=[],
                        help="Include session names containing this value; repeatable.")
    parser.add_argument("--latest", type=int, default=0,
                        help="Use only the newest N matching sessions (0 means all).")
    parser.add_argument("--include-incomplete", action="store_true",
                        help="Include partial and failed sessions in addition to complete sessions.")
    parser.add_argument("--include-without-runlogs", action="store_true",
                        help="Include sessions with stage timing but no LLM runlogs.")
    parser.add_argument("--show", action="store_true", help="Open the chart after writing it.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.latest < 0:
        raise ValueError("--latest must be zero or positive")
    sessions = discover_sessions(
        args.sessions_root.resolve(), include_incomplete=args.include_incomplete,
        include_without_runlogs=args.include_without_runlogs,
        filters=args.session, latest=args.latest)
    if not sessions:
        raise SystemExit("No matching workflow sessions found.")
    manifests: dict[str, dict[str, Any]] = {}
    stages: list[StageRecord] = []
    calls: list[CallRecord] = []
    for session_root in sessions:
        manifest, session_stages, session_calls = load_session(session_root)
        session_id = str(manifest.get("session_id") or session_root.name)
        manifests[session_id] = manifest
        stages.extend(session_stages)
        calls.extend(session_calls)
    node_rows = summarize_nodes(manifests, stages, calls)
    session_rows = summarize_sessions(manifests, node_rows, stages, calls)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    _write_csv(output / "runlog_calls.csv", [asdict(call) for call in calls])
    _write_csv(output / "session_node_summary.csv", node_rows)
    _write_csv(output / "session_summary.csv", session_rows)
    write_markdown(output / "comparison.md", session_rows, node_rows)
    create_chart(output / "stacked_time_and_tokens.png", session_rows, node_rows,
                 show=args.show)
    print_summary(session_rows)
    print(f"\nWrote comparison files to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
