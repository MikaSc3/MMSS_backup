"""
Count annotation statistics from annotated FFA report JSON files.

Supported markers at the end of statements:
    []   = correct statement
    [d]  = diskutabel
    [f]  = falsch
    [x]  = legacy alias for falsch

The script aggregates counts for:
    - basic_info
    - steps
    - parts

It writes machine-readable summaries and creates overview plots.

Usage:
    python agent/count_validation_stats.py <input_path>
    python agent/count_validation_stats.py <input_dir> --pattern "*_ffa_report.json"
    python agent/count_validation_stats.py <input_path> --output-dir <target_dir>
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Tuple

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ModuleNotFoundError:
    matplotlib = None
    plt = None


MARKER_RE = re.compile(r"\[(?P<marker>[^\]]*)\]\s*$")
COUNT_KEYS = ["correct", "diskutabel", "falsch", "unmarked", "unknown_marker", "total"]
PRIMARY_LABELS = ["correct", "diskutabel", "falsch"]
SECTION_ORDER = ["basic_info", "steps", "parts"]
SECTION_LABELS = {
    "basic_info": "Basic Info",
    "steps": "Steps",
    "parts": "Parts",
}
LABEL_LABELS = {
    "correct": "Correct []",
    "diskutabel": "Diskutabel [d]",
    "falsch": "Falsch [f]",
    "unmarked": "No Marker",
    "unknown_marker": "Unknown Marker",
}
LABEL_COLORS = {
    "correct": "#179C7D",
    "diskutabel": "#FDB913",
    "falsch": "#F58220",
    "unmarked": "#7A7A7A",
    "unknown_marker": "#7B61FF",
}

# Optional defaults for running the script directly from the IDE.
# Set these to a JSON file or a directory containing `*_ffa_report.json` files.
DEFAULT_INPUT_PATH = Path(r"C:\Users\KAB-MS\Desktop\FfA_report_annotated")
# Example alternatives:
# DEFAULT_INPUT_PATH = Path(r"C:\Users\KAB-MS\Desktop\FfA_report_annotated\End-to-End")
# DEFAULT_INPUT_PATH = Path(r"C:\Users\KAB-MS\Desktop\FfA_report_annotated\FfA Only")
DEFAULT_OUTPUT_DIR = Path(r"C:\Users\KAB-MS\Desktop\FfA_report_annotated\eval")
# Example:
# DEFAULT_OUTPUT_DIR = Path(r"C:\Users\KAB-MS\Desktop\FfA_report_annotated\stats_output")


def empty_counts() -> Dict[str, int]:
    return {key: 0 for key in COUNT_KEYS}


def add_count(target: Dict[str, int], label: str) -> None:
    if label not in target:
        target[label] = 0
    target[label] += 1
    target["total"] += 1


def merge_counts(target: Dict[str, int], source: Dict[str, int]) -> None:
    for key in COUNT_KEYS:
        target[key] += source.get(key, 0)


def extract_marker_label(statement: str) -> str:
    if not isinstance(statement, str):
        return "unmarked"

    match = MARKER_RE.search(statement.rstrip())
    if not match:
        return "unmarked"

    marker = match.group("marker").strip().lower()
    if marker == "":
        return "correct"
    if marker == "d":
        return "diskutabel"
    if marker in {"f", "x"}:
        return "falsch"
    return "unknown_marker"


def clean_statement(statement: str) -> str:
    return MARKER_RE.sub("", statement).rstrip()


def iter_strings(node: object, path_parts: Tuple[str, ...] = ()) -> Iterator[Tuple[Tuple[str, ...], str]]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield from iter_strings(value, path_parts + (str(key),))
        return

    if isinstance(node, list):
        for index, item in enumerate(node):
            if isinstance(item, str):
                yield path_parts + (str(index),), item
            else:
                yield from iter_strings(item, path_parts + (str(index),))


def path_without_indexes(path_parts: Tuple[str, ...]) -> Tuple[str, ...]:
    return tuple(part for part in path_parts if not part.isdigit())


def make_field_name(section_name: str, path_parts: Tuple[str, ...]) -> str:
    path_no_idx = path_without_indexes(path_parts)
    if section_name == "basic_info":
        return ".".join(path_no_idx)
    if len(path_no_idx) >= 2:
        return path_no_idx[-1]
    if path_no_idx:
        return path_no_idx[0]
    return section_name


def detect_report_files(input_path: Path, pattern: str) -> List[Path]:
    if input_path.is_file():
        return [input_path]
    return sorted(path for path in input_path.rglob(pattern) if path.is_file())


def summarize_counts(counts: Dict[str, int]) -> Dict[str, float]:
    total = counts["total"]
    summary = dict(counts)
    summary["correct_rate"] = round((counts["correct"] / total) * 100, 2) if total else 0.0
    summary["diskutabel_rate"] = round((counts["diskutabel"] / total) * 100, 2) if total else 0.0
    summary["falsch_rate"] = round((counts["falsch"] / total) * 100, 2) if total else 0.0
    return summary


def analyze_report(report_path: Path) -> Dict[str, object]:
    with report_path.open("r", encoding="utf-8") as handle:
        report = json.load(handle)

    section_nodes = {
        "basic_info": {
            key: value
            for key, value in report.items()
            if key not in {"steps", "parts"}
        },
        "steps": report.get("steps", []),
        "parts": report.get("parts", []),
    }

    section_counts = {section: empty_counts() for section in SECTION_ORDER}
    field_counts = defaultdict(empty_counts)
    flagged_statements = []

    for section_name, node in section_nodes.items():
        for path_parts, statement in iter_strings(node):
            label = extract_marker_label(statement)
            add_count(section_counts[section_name], label)

            field_name = make_field_name(section_name, path_parts)
            add_count(field_counts[f"{section_name}/{field_name}"], label)

            if label in {"diskutabel", "falsch", "unknown_marker", "unmarked"}:
                flagged_statements.append(
                    {
                        "section": section_name,
                        "field": field_name,
                        "label": label,
                        "statement": clean_statement(statement),
                    }
                )

    overall = empty_counts()
    for counts in section_counts.values():
        merge_counts(overall, counts)

    return {
        "report_path": str(report_path),
        "report_name": report.get("assembly_name", report_path.stem),
        "overall": summarize_counts(overall),
        "by_section": {
            section: summarize_counts(counts)
            for section, counts in section_counts.items()
        },
        "by_field": {
            field_name: summarize_counts(counts)
            for field_name, counts in sorted(field_counts.items())
        },
        "flagged_statements": flagged_statements,
    }


def aggregate_reports(report_summaries: List[Dict[str, object]]) -> Dict[str, object]:
    overall = empty_counts()
    by_section = {section: empty_counts() for section in SECTION_ORDER}
    by_field = defaultdict(empty_counts)

    for report_summary in report_summaries:
        merge_counts(overall, report_summary["overall"])
        for section, counts in report_summary["by_section"].items():
            merge_counts(by_section[section], counts)
        for field_name, counts in report_summary["by_field"].items():
            merge_counts(by_field[field_name], counts)

    return {
        "report_count": len(report_summaries),
        "overall": summarize_counts(overall),
        "by_section": {
            section: summarize_counts(counts)
            for section, counts in by_section.items()
        },
        "by_field": {
            field_name: summarize_counts(counts)
            for field_name, counts in sorted(by_field.items())
        },
        "reports": report_summaries,
    }


def ensure_output_dir(input_path: Path, output_dir: Path | None) -> Path:
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    if input_path.is_file():
        target = input_path.parent / f"{input_path.stem}_annotation_stats"
    else:
        target = input_path / "annotation_stats"
    target.mkdir(parents=True, exist_ok=True)
    return target


def write_json_summary(summary: Dict[str, object], output_dir: Path) -> Path:
    output_path = output_dir / "annotation_summary.json"
    output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


def write_section_csv(summary: Dict[str, object], output_dir: Path) -> Path:
    output_path = output_dir / "section_counts.csv"
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["section", "total", "correct", "diskutabel", "falsch", "unmarked", "unknown_marker"])
        for section in SECTION_ORDER:
            counts = summary["by_section"][section]
            writer.writerow(
                [
                    section,
                    counts["total"],
                    counts["correct"],
                    counts["diskutabel"],
                    counts["falsch"],
                    counts["unmarked"],
                    counts["unknown_marker"],
                ]
            )
    return output_path


def write_field_csv(summary: Dict[str, object], output_dir: Path) -> Path:
    output_path = output_dir / "field_counts.csv"
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["field", "total", "correct", "diskutabel", "falsch", "unmarked", "unknown_marker"])
        for field_name, counts in summary["by_field"].items():
            writer.writerow(
                [
                    field_name,
                    counts["total"],
                    counts["correct"],
                    counts["diskutabel"],
                    counts["falsch"],
                    counts["unmarked"],
                    counts["unknown_marker"],
                ]
            )
    return output_path


def write_report_csv(summary: Dict[str, object], output_dir: Path) -> Path:
    output_path = output_dir / "report_counts.csv"
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["report", "total", "correct", "diskutabel", "falsch", "unmarked", "unknown_marker"])
        for report in summary["reports"]:
            counts = report["overall"]
            writer.writerow(
                [
                    report["report_name"],
                    counts["total"],
                    counts["correct"],
                    counts["diskutabel"],
                    counts["falsch"],
                    counts["unmarked"],
                    counts["unknown_marker"],
                ]
            )
    return output_path


def write_report_section_csv(summary: Dict[str, object], output_dir: Path) -> Path:
    output_path = output_dir / "report_section_counts.csv"
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["report", "section", "total", "correct", "diskutabel", "falsch", "unmarked", "unknown_marker"]
        )
        for report in summary["reports"]:
            for section in SECTION_ORDER:
                counts = report["by_section"][section]
                writer.writerow(
                    [
                        report["report_name"],
                        section,
                        counts["total"],
                        counts["correct"],
                        counts["diskutabel"],
                        counts["falsch"],
                        counts["unmarked"],
                        counts["unknown_marker"],
                    ]
                )
    return output_path


def write_flagged_statements_csv(summary: Dict[str, object], output_dir: Path) -> Path:
    output_path = output_dir / "flagged_statements.csv"
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["report", "section", "field", "label", "statement"])
        for report in summary["reports"]:
            for item in report["flagged_statements"]:
                writer.writerow(
                    [
                        report["report_name"],
                        item["section"],
                        item["field"],
                        item["label"],
                        item["statement"],
                    ]
                )
    return output_path


def active_labels_from_summaries(summaries: Iterable[Dict[str, int]]) -> List[str]:
    active = []
    materialized = list(summaries)
    for label in PRIMARY_LABELS + ["unmarked", "unknown_marker"]:
        if any(summary.get(label, 0) > 0 for summary in materialized):
            active.append(label)
    return active or PRIMARY_LABELS


def plot_section_overview(summary: Dict[str, object], output_dir: Path) -> Path:
    if plt is None:
        raise RuntimeError("matplotlib is not installed in the current Python environment.")

    section_summaries = [summary["by_section"][section] for section in SECTION_ORDER if summary["by_section"][section]["total"] > 0]
    if not section_summaries:
        return output_dir / "section_overview.png"

    active_sections = [section for section in SECTION_ORDER if summary["by_section"][section]["total"] > 0]
    active_labels = active_labels_from_summaries(section_summaries)

    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5))

    left_offsets = [0.0] * len(active_sections)
    for label in active_labels:
        values = [summary["by_section"][section][label] for section in active_sections]
        axes[0].barh(
            [SECTION_LABELS[section] for section in active_sections],
            values,
            left=left_offsets,
            color=LABEL_COLORS[label],
            edgecolor="white",
            linewidth=0.8,
            label=LABEL_LABELS[label],
        )
        left_offsets = [offset + value for offset, value in zip(left_offsets, values)]

    for index, section in enumerate(active_sections):
        total = summary["by_section"][section]["total"]
        axes[0].text(total + max(1, total * 0.01), index, str(total), va="center", fontsize=9, fontweight="bold")

    axes[0].set_title("Statement Counts by Section", fontweight="bold")
    axes[0].set_xlabel("Number of Statements")
    axes[0].grid(axis="x", alpha=0.25)

    left_offsets = [0.0] * len(active_sections)
    for label in active_labels:
        values = []
        for section in active_sections:
            total = summary["by_section"][section]["total"]
            value = summary["by_section"][section][label]
            values.append((value / total) * 100 if total else 0.0)
        axes[1].barh(
            [SECTION_LABELS[section] for section in active_sections],
            values,
            left=left_offsets,
            color=LABEL_COLORS[label],
            edgecolor="white",
            linewidth=0.8,
            label=LABEL_LABELS[label],
        )
        left_offsets = [offset + value for offset, value in zip(left_offsets, values)]

    axes[1].set_xlim(0, 100)
    axes[1].set_title("Section Share by Label", fontweight="bold")
    axes[1].set_xlabel("Share of Statements (%)")
    axes[1].grid(axis="x", alpha=0.25)

    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=min(len(labels), 5), frameon=False)
    fig.suptitle(
        f"Annotation Overview ({summary['report_count']} report{'s' if summary['report_count'] != 1 else ''})",
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0.08, 1, 0.95))

    output_path = output_dir / "section_overview.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_report_overview(summary: Dict[str, object], output_dir: Path) -> Path | None:
    if plt is None:
        raise RuntimeError("matplotlib is not installed in the current Python environment.")

    reports = summary["reports"]
    if len(reports) <= 1:
        return None

    active_labels = active_labels_from_summaries(report["overall"] for report in reports)
    report_names = [report["report_name"] for report in reports]
    figure_height = min(max(4.5, 0.32 * len(reports) + 1.8), 30)
    fig, ax = plt.subplots(figsize=(14, figure_height))

    left_offsets = [0.0] * len(reports)
    for label in active_labels:
        values = [report["overall"][label] for report in reports]
        ax.barh(
            report_names,
            values,
            left=left_offsets,
            color=LABEL_COLORS[label],
            edgecolor="white",
            linewidth=0.6,
            label=LABEL_LABELS[label],
        )
        left_offsets = [offset + value for offset, value in zip(left_offsets, values)]

    ax.set_title("Annotation Counts per Report", fontweight="bold")
    ax.set_xlabel("Number of Statements")
    ax.grid(axis="x", alpha=0.25)
    ax.legend(loc="lower right", frameon=True)
    fig.tight_layout()

    output_path = output_dir / "report_overview.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_report_section_breakdown(summary: Dict[str, object], output_dir: Path) -> Path | None:
    if plt is None:
        raise RuntimeError("matplotlib is not installed in the current Python environment.")

    reports = summary["reports"]
    if len(reports) <= 1:
        return None

    active_labels = active_labels_from_summaries(
        report["by_section"][section]
        for report in reports
        for section in SECTION_ORDER
    )
    fig, axes = plt.subplots(
        len(SECTION_ORDER),
        1,
        figsize=(14, max(7.5, 2.8 * len(SECTION_ORDER))),
        sharex=True,
    )

    if len(SECTION_ORDER) == 1:
        axes = [axes]

    report_names = [report["report_name"] for report in reports]
    for ax, section in zip(axes, SECTION_ORDER):
        left_offsets = [0.0] * len(reports)
        for label in active_labels:
            values = [report["by_section"][section][label] for report in reports]
            ax.barh(
                report_names,
                values,
                left=left_offsets,
                color=LABEL_COLORS[label],
                edgecolor="white",
                linewidth=0.6,
                label=LABEL_LABELS[label],
            )
            left_offsets = [offset + value for offset, value in zip(left_offsets, values)]

        ax.set_title(f"{SECTION_LABELS[section]}: Annotation Counts", fontweight="bold", loc="left")
        ax.grid(axis="x", alpha=0.25)

    axes[-1].set_xlabel("Number of Statements")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=min(len(labels), 5), frameon=False)
    fig.suptitle("Per-Report Breakdown by Section", fontweight="bold")
    fig.tight_layout(rect=(0, 0.07, 1, 0.96))

    output_path = output_dir / "report_section_breakdown.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def print_console_summary(summary: Dict[str, object]) -> None:
    overall = summary["overall"]
    print("\n" + "=" * 88)
    print("ANNOTATION SUMMARY")
    print("=" * 88)
    print(f"Reports analyzed: {summary['report_count']}")
    print(
        f"Overall statements: {overall['total']} | "
        f"correct: {overall['correct']} | "
        f"diskutabel: {overall['diskutabel']} | "
        f"falsch: {overall['falsch']}"
    )
    if overall["unmarked"] or overall["unknown_marker"]:
        print(
            f"Additional markers: unmarked={overall['unmarked']}, "
            f"unknown={overall['unknown_marker']}"
        )
    print("-" * 88)
    print(f"{'SECTION':<15} {'TOTAL':>8} {'CORRECT':>10} {'DISKUT.':>10} {'FALSCH':>8}")
    print("-" * 88)
    for section in SECTION_ORDER:
        counts = summary["by_section"][section]
        print(
            f"{SECTION_LABELS[section]:<15} "
            f"{counts['total']:>8} "
            f"{counts['correct']:>10} "
            f"{counts['diskutabel']:>10} "
            f"{counts['falsch']:>8}"
        )
    print("=" * 88)


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Count [] / [d] / [f] markers in annotated FFA reports.")
    parser.add_argument(
        "input_path",
        nargs="?",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help="Single JSON file or directory containing report JSON files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Target directory for summaries and plots. Defaults to a sibling output folder.",
    )
    parser.add_argument(
        "--pattern",
        default="*_ffa_report.json",
        help="Glob pattern used when the input path is a directory.",
    )
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Skip PNG plot generation.",
    )
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    input_path = args.input_path

    if not input_path.exists():
        print(f"Input path not found: {input_path}", file=sys.stderr)
        return 1

    report_files = detect_report_files(input_path, args.pattern)
    if not report_files:
        print(f"No report JSON files found at: {input_path}", file=sys.stderr)
        return 1

    output_dir = ensure_output_dir(input_path, args.output_dir)
    report_summaries = [analyze_report(report_path) for report_path in report_files]
    summary = aggregate_reports(report_summaries)
    summary["input_path"] = str(input_path)

    print_console_summary(summary)

    json_path = write_json_summary(summary, output_dir)
    section_csv = write_section_csv(summary, output_dir)
    field_csv = write_field_csv(summary, output_dir)
    report_csv = write_report_csv(summary, output_dir)
    report_section_csv = write_report_section_csv(summary, output_dir)
    flagged_csv = write_flagged_statements_csv(summary, output_dir)

    print(f"Saved JSON summary:   {json_path}")
    print(f"Saved section CSV:    {section_csv}")
    print(f"Saved field CSV:      {field_csv}")
    print(f"Saved report CSV:     {report_csv}")
    print(f"Saved report+section: {report_section_csv}")
    print(f"Saved flagged CSV:    {flagged_csv}")

    if not args.no_plots and plt is not None:
        section_plot = plot_section_overview(summary, output_dir)
        print(f"Saved section plot:   {section_plot}")
        report_plot = plot_report_overview(summary, output_dir)
        if report_plot is not None:
            print(f"Saved report plot:    {report_plot}")
        report_section_plot = plot_report_section_breakdown(summary, output_dir)
        if report_section_plot is not None:
            print(f"Saved section detail: {report_section_plot}")
    elif not args.no_plots and plt is None:
        print("Skipped plot generation: matplotlib is not installed in the current Python environment.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
