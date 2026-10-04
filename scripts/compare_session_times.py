"""Compare cumulative per-node execution time and tokens across workflow sessions."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


# Set this to the folder containing the session directories.
SESSIONS_FOLDER = Path(r"C:\Users\Mika\Desktop\apa_from_cad_save\data\comparesessions")
OUTPUT_CSV_NAME = "session_comparison.csv"

# Leave this as None to include every session directory in SESSIONS_FOLDER.
# To select or order specific sessions, provide their directory names here.
SESSION_NAMES: list[str] | None = None


def select_sessions(folder: Path) -> list[Path]:
    if not folder.is_dir():
        raise FileNotFoundError(f"Sessions folder does not exist: {folder}")

    if SESSION_NAMES is not None:
        sessions = [folder / name for name in SESSION_NAMES]
        missing = [str(path) for path in sessions if not path.is_dir()]
        if missing:
            raise FileNotFoundError(f"Session directories do not exist: {missing}")
        return sessions

    sessions = sorted(
        path for path in folder.iterdir()
        if path.is_dir() and (path / "runlog").is_dir()
    )
    if not sessions:
        raise ValueError(f"No session directories containing runlog folders found in {folder}")
    return sessions


@dataclass
class Usage:
    calls: int = 0
    elapsed_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


def read_node_usage(session: Path) -> dict[str, Usage]:
    runlog = session / "runlog"
    if not runlog.is_dir():
        raise FileNotFoundError(f"Runlog folder does not exist: {runlog}")

    usage: dict[str, Usage] = defaultdict(Usage)
    for path in runlog.rglob("*.run.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            execution = record.get("execution", {})
            node = execution.get("node")
            elapsed = execution.get("elapsed_seconds")
            tokens = execution.get("token_usage", {})
            if isinstance(node, str):
                item = usage[node]
                item.calls += 1
                if isinstance(elapsed, (int, float)):
                    item.elapsed_seconds += float(elapsed)
                if isinstance(tokens, dict):
                    item.input_tokens += int(tokens.get("input_tokens") or 0)
                    item.output_tokens += int(tokens.get("output_tokens") or 0)
                    item.total_tokens += int(tokens.get("total_tokens") or 0)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Warning: skipping {path}: {exc}")
    return dict(usage)


def format_duration(seconds: float, *, include_clock: bool = False) -> str:
    seconds_text = f"{seconds:.1f} s"
    if not include_clock:
        return seconds_text
    rounded = round(seconds)
    minutes, remaining_seconds = divmod(rounded, 60)
    return f"{seconds_text} ({minutes}:{remaining_seconds:02d})"


def format_calls(count: int) -> str:
    return f"{count} call" if count == 1 else f"{count} calls"


def format_clock(seconds: float) -> str:
    rounded = round(seconds)
    hours, remainder = divmod(rounded, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"


def write_csv(
    output_path: Path,
    session_ids: list[str],
    nodes: list[str],
    usage_by_session: dict[str, dict[str, Usage]],
) -> None:
    metrics = [
        "Calls", "Time consumption (HH:MM:SS)", "Time (seconds)", "Time (minutes)",
        "Input tokens", "Output tokens", "Total tokens",
    ]
    fieldnames = ["Node"] + [
        f"{session_id} | {metric}"
        for session_id in session_ids
        for metric in metrics
    ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for node in nodes:
            row: dict[str, str | int] = {"Node": node}
            for session_id in session_ids:
                item = usage_by_session[session_id].get(node, Usage())
                prefix = f"{session_id} | "
                row.update({
                    prefix + "Calls": item.calls,
                    prefix + "Time consumption (HH:MM:SS)": format_clock(item.elapsed_seconds),
                    prefix + "Time (seconds)": f"{item.elapsed_seconds:.3f}",
                    prefix + "Time (minutes)": f"{item.elapsed_seconds / 60:.3f}",
                    prefix + "Input tokens": item.input_tokens,
                    prefix + "Output tokens": item.output_tokens,
                    prefix + "Total tokens": item.total_tokens,
                })
            writer.writerow(row)

        total_row: dict[str, str | int] = {"Node": "TOTAL"}
        for session_id in session_ids:
            values = list(usage_by_session[session_id].values())
            elapsed = sum(item.elapsed_seconds for item in values)
            prefix = f"{session_id} | "
            total_row.update({
                prefix + "Calls": sum(item.calls for item in values),
                prefix + "Time consumption (HH:MM:SS)": format_clock(elapsed),
                prefix + "Time (seconds)": f"{elapsed:.3f}",
                prefix + "Time (minutes)": f"{elapsed / 60:.3f}",
                prefix + "Input tokens": sum(item.input_tokens for item in values),
                prefix + "Output tokens": sum(item.output_tokens for item in values),
                prefix + "Total tokens": sum(item.total_tokens for item in values),
            })
        writer.writerow(total_row)


def main() -> None:
    sessions = select_sessions(SESSIONS_FOLDER)
    usage_by_session = {session.name: read_node_usage(session) for session in sessions}
    session_ids = list(usage_by_session)
    nodes = sorted({node for usage in usage_by_session.values() for node in usage})
    output_path = SESSIONS_FOLDER / OUTPUT_CSV_NAME
    write_csv(output_path, session_ids, nodes, usage_by_session)

    header = "| Node | " + " | ".join(f"`{session_id}`" for session_id in session_ids) + " |"
    separator = "|---|" + "---:|" * len(session_ids)

    print("## Execution time and calls")
    print()
    print(header)
    print(separator)

    for node in nodes:
        cells = []
        for session_id in session_ids:
            item = usage_by_session[session_id].get(node, Usage())
            cells.append(f"{format_duration(item.elapsed_seconds)}; {format_calls(item.calls)}")
        print(f"| `{node}` | " + " | ".join(cells) + " |")

    total_cells = []
    for session_id in session_ids:
        values = usage_by_session[session_id].values()
        elapsed = sum(item.elapsed_seconds for item in values)
        calls = sum(item.calls for item in values)
        total_cells.append(f"**{format_duration(elapsed, include_clock=True)}; {format_calls(calls)}**")
    print("| **Total** | " + " | ".join(total_cells) + " |")
    print()
    print("## Time and token usage (HH:MM:SS; total tokens; input / output)")
    print()
    print(header)
    print(separator)
    for node in nodes:
        cells = []
        for session_id in session_ids:
            item = usage_by_session[session_id].get(node, Usage())
            cells.append(
                f"{format_clock(item.elapsed_seconds)}; {item.total_tokens:,}; "
                f"{item.input_tokens:,} / {item.output_tokens:,}"
            )
        print(f"| `{node}` | " + " | ".join(cells) + " |")

    total_cells = []
    for session_id in session_ids:
        values = usage_by_session[session_id].values()
        input_tokens = sum(item.input_tokens for item in values)
        output_tokens = sum(item.output_tokens for item in values)
        total_tokens = sum(item.total_tokens for item in values)
        elapsed = sum(item.elapsed_seconds for item in values)
        total_cells.append(
            f"**{format_clock(elapsed)}; {total_tokens:,}; "
            f"{input_tokens:,} / {output_tokens:,}**"
        )
    print("| **Total** | " + " | ".join(total_cells) + " |")
    print()
    print(f"CSV written to: {output_path}")


if __name__ == "__main__":
    main()
