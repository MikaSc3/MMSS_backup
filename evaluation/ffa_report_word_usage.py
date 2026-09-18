"""
Analyze and compare word usage across FFA report JSON files.

Single-input outputs:
    - per_report_word_counts.csv
    - top_50_words_per_report.csv
    - overall_word_counts.csv
    - report_word_matrix.csv
    - word_usage_summary.json

Two-system comparison outputs:
    - comparison_report_summary.csv
    - comparison_top_50_words_per_report.csv
    - comparison_top_50_word_categories.csv
    - comparison_category_summary.csv
    - comparison_category_composition.png
    - comparison_shared_words.csv
    - comparison_unique_words.csv
    - comparison_specific_vs_generic.csv
    - comparison_specific_vs_generic.png
    - unique_words_system_a.csv
    - unique_words_system_b.csv
    - unique_words_system_a_gt5.csv
    - unique_words_system_b_gt5.csv
    - comparison_system_overview.png
    - comparison_summary.json

Usage:
    python evaluation/ffa_report_word_usage.py
    python evaluation/ffa_report_word_usage.py <input_path>
    python evaluation/ffa_report_word_usage.py <input_path_a> --input-path-b <input_path_b>
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

try:
    import matplotlib
    from matplotlib import font_manager

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ModuleNotFoundError:
    plt = None


PLOT_COLOR_A = "#F58220"
PLOT_COLOR_B = "#179C7D"
PLOT_FONT_CANDIDATES = [
    "LM Roman 12",
    "Latin Modern Roman",
    "CMU Serif",
    "Computer Modern Roman",
    "STIX Two Text",
    "DejaVu Serif",
]
PLOT_FONT_SIZE = 12
SPECIFICITY_TOP_N = 50

if plt is not None:
    available_fonts = {f.name for f in font_manager.fontManager.ttflist}
    selected_font = next((name for name in PLOT_FONT_CANDIDATES if name in available_fonts), "DejaVu Serif")
    plt.rcParams["font.family"] = "serif"
    plt.rcParams["font.serif"] = [selected_font, *[name for name in PLOT_FONT_CANDIDATES if name != selected_font]]
    plt.rcParams["font.size"] = PLOT_FONT_SIZE
    plt.rcParams["axes.titlesize"] = PLOT_FONT_SIZE
    plt.rcParams["axes.labelsize"] = PLOT_FONT_SIZE
    plt.rcParams["xtick.labelsize"] = PLOT_FONT_SIZE
    plt.rcParams["ytick.labelsize"] = PLOT_FONT_SIZE
    plt.rcParams["legend.fontsize"] = PLOT_FONT_SIZE
    plt.rcParams["figure.titlesize"] = PLOT_FONT_SIZE


DEFAULT_INPUT_PATH = Path(r"C:\Users\KAB-MS\Desktop\FfA_report_annotated\End-to-End")
DEFAULT_INPUT_PATH_B = Path(r"C:\Users\KAB-MS\Desktop\FfA_report_annotated\FfA Only")
DEFAULT_OUTPUT_DIR = Path(r"C:\Users\KAB-MS\Desktop\FfA_report_annotated\wordeval")
DEFAULT_PATTERN = "*_ffa_report.json"

STOPWORDS: set[str] = {}

DEFAULT_EXCLUSIONS = {
    "high",
    "low",
    "moderate",
    "step",
    "steps",
    "part",
    "parts",
    "assembly",
    "assemblies",
    "with",
    "for",
    "and",
    "the",
    "report",
    "reports",
    "automation",
    "assessment",
    "insertion",
    "orientation",
    "gripping",
}

VAGUE_WORDS = {
    "appears",
    "appeared",
    "seem",
    "seems",
    "may",
    "might",
    "could",
    "possible",
    "possibly",
    "potentially",
    "likely",
    "unlikely",
    "probable",
    "probably",
    "conceivable",
    "plausible",
    "if",
    "unspecified",
    "whether",
    "suggests",
}

VAGUE_PHRASES = {
    "depending on",
    "in case",
    "suggests that",
    "does not explicitly",
    "doesn't explicitly",
}

ALL_VAGUE_TERMS = sorted(VAGUE_WORDS | VAGUE_PHRASES)

BOLD_WORDS = {
    "exists",
    "exist",
    "explicitly",
    "ensures",
    "ensured",
    "guarantees",
    "guaranteed",
    "prevents",
    "eliminates",
    "must",
    "cannot",
    "requires",
    "validated",
    "clearly",
    "explicitly",
    "directly",
    "fully",
    "completely",
    "nonfunctional",
    "functional",
    "shows",
}

BOLD_PHRASES = {
    "results in",
    "leads to",
    "will not",
    "is required to",
    "is defined by",
    "is determined by",
}

ALL_BOLD_TERMS = sorted(BOLD_WORDS | BOLD_PHRASES)

SPECIFIC_WORDS = {
    "axle",
    "bearing",
    "base",
    "body",
    "bore",
    "bores",
    "bracket",
    "bushing",
    "circlip",
    "clevis",
    "clocking",
    "collar",
    "crank",
    "cross-hole",
    "gear",
    "groove",
    "housing",
    "internal",
    "keyway",
    "link",
    "lugs",
    "pedestal",
    "pin",
    "piston",
    "pivot",
    "plug",
    "port",
    "retainer",
    "ring",
    "shaft",
    "shank",
    "spring",
    "stem",
    "thread",
    "threaded",
    "valve",
    "wheel",
    "worm",
}

GENERIC_WORDS = {
    "alignment",
    "angular",
    "asymmetric",
    "axis",
    "bulk",
    "control",
    "damage",
    "dedicated",
    "defined",
    "during",
    "elastic",
    "engagement",
    "expansion",
    "feature",
    "features",
    "geometry",
    "handling",
    "insert",
    "installation",
    "joining",
    "later",
    "pickup",
    "placement",
    "pose",
    "presentation",
    "process",
    "retention",
    "risk",
    "rigid",
    "robust",
    "robustness",
    "rotational",
    "seating",
    "singulation",
    "small",
    "stable",
    "standard",
    "supply",
    "visible",
}

CATEGORY_PART_SPECIFIC = {
    "axial",
    "axle",
    "base",
    "bearing",
    "big-end",
    "body",
    "bore",
    "bores",
    "bracket",
    "bushing",
    "bushings",
    "cage",
    "circlip",
    "circlips",
    "clevis",
    "clocking",
    "collar",
    "crank",
    "cross-hole",
    "external",
    "face",
    "flange",
    "flanged",
    "flats",
    "gear",
    "groove",
    "grooves",
    "head",
    "hole",
    "holes",
    "housing",
    "internal",
    "journal",
    "keyed",
    "keyway",
    "link",
    "linkage",
    "lugs",
    "pedestal",
    "pin",
    "piston",
    "pivot",
    "plug",
    "port",
    "retainer",
    "retaining",
    "retaining-ring",
    "ring",
    "rings",
    "screw",
    "shaft",
    "shank",
    "side",
    "slot",
    "spacer",
    "spring",
    "stem",
    "support",
    "surface",
    "surfaces",
    "thread",
    "threaded",
    "valve",
    "wheel",
    "worm",
    "wrist-pin",
}

CATEGORY_GEOMETRY_INTERFACE = {
    "alignment",
    "angular",
    "annular",
    "anti-rotation",
    "area",
    "asymmetric",
    "axis",
    "clearance",
    "coaxial",
    "control",
    "cylindrical",
    "datum",
    "depth",
    "edge",
    "engagement",
    "expansion",
    "feature",
    "features",
    "functional",
    "geometry",
    "helical",
    "indexing",
    "interface",
    "lateral",
    "lead-in",
    "locating",
    "planar",
    "pose",
    "precision",
    "radial",
    "rotational",
    "seat",
    "seats",
    "simple",
    "size",
    "stop",
    "thin",
    "tooling",
}

CATEGORY_PROCESS_HANDLING = {
    "after",
    "automated",
    "before",
    "bulk",
    "contact",
    "controlled",
    "dedicated",
    "feeding",
    "fastening",
    "fixture",
    "from",
    "handling",
    "installation",
    "insert",
    "into",
    "joining",
    "later",
    "main",
    "pickup",
    "placement",
    "pockets",
    "presentation",
    "process",
    "provided",
    "provide",
    "supplied",
    "supply",
    "temporary",
    "through",
    "transfer",
    "tray",
    "trays",
    "under",
    "unordered",
}

CATEGORY_EVALUATION_QUALITY = {
    "automated",
    "because",
    "control",
    "correct",
    "controlled",
    "damage",
    "deformation",
    "defined",
    "depends",
    "downstream",
    "during",
    "element",
    "final",
    "fixation",
    "limited",
    "locking",
    "must",
    "positive",
    "precise",
    "protection",
    "protected",
    "required",
    "require",
    "retention",
    "risk",
    "rigid",
    "robust",
    "robustness",
    "seating",
    "singulation",
    "stable",
    "standard",
}

CATEGORY_DISCOURSE_VAGUE = {
    "about",
    "appears",
    "because",
    "both",
    "depends",
    "during",
    "from",
    "increase",
    "likely",
    "only",
    "reduce",
    "than",
    "this",
    "without",
}

WORD_CATEGORIES = {
    "part_specific": CATEGORY_PART_SPECIFIC,
    "geometry_interface": CATEGORY_GEOMETRY_INTERFACE,
    "process_handling": CATEGORY_PROCESS_HANDLING,
    "evaluation_quality": CATEGORY_EVALUATION_QUALITY,
    "discourse_vague": CATEGORY_DISCOURSE_VAGUE,
}

TOKEN_RE = re.compile(r"\b[\w\-]+\b", re.UNICODE)


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze word usage in FFA report JSON files.")
    parser.add_argument(
        "input_path",
        nargs="?",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help="Single JSON file or directory containing FFA report JSON files.",
    )
    parser.add_argument(
        "--input-path-b",
        type=Path,
        default=DEFAULT_INPUT_PATH_B,
        help="Optional second directory/file for comparing two systems.",
    )
    parser.add_argument(
        "--label-a",
        default="Gesamtes System",
        help="Label for first system in comparison mode.",
    )
    parser.add_argument(
        "--label-b",
        default="Nur FfA Bewertung",
        help="Label for second system in comparison mode.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for CSV/JSON outputs.",
    )
    parser.add_argument(
        "--pattern",
        default=DEFAULT_PATTERN,
        help="Glob pattern used when an input path is a directory.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=250,
        help="Number of top words to include in matrix / shared-word outputs.",
    )
    parser.add_argument(
        "--min-length",
        type=int,
        default=4,
        help="Minimum token length to keep.",
    )
    parser.add_argument(
        "--keep-stopwords",
        action="store_true",
        help="Keep common stopwords in the output.",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=None,
        help="Additional words to exclude (space-separated).",
    )
    return parser.parse_args(argv)


def detect_report_files(input_path: Path, pattern: str) -> List[Path]:
    if input_path.is_file():
        return [input_path]
    return sorted(path for path in input_path.rglob(pattern) if path.is_file())


def iter_strings(node: object) -> Iterator[str]:
    if isinstance(node, dict):
        for value in node.values():
            yield from iter_strings(value)
        return
    if isinstance(node, list):
        for item in node:
            yield from iter_strings(item)
        return
    if isinstance(node, str):
        yield node


def categorize_word(word: str) -> str:
    for category_name, terms in WORD_CATEGORIES.items():
        if word in terms:
            return category_name
    return "other"


def build_exclusion_set(keep_stopwords: bool, extra_exclusions: List[str] | None) -> set[str]:
    excluded = set(DEFAULT_EXCLUSIONS)
    if not keep_stopwords:
        excluded.update(STOPWORDS)
    if extra_exclusions:
        excluded.update(word.lower().strip() for word in extra_exclusions if word.strip())
    return excluded


def tokenize(text: str, min_length: int, excluded_words: set[str]) -> List[str]:
    tokens = []
    for raw_token in TOKEN_RE.findall(text.lower()):
        token = raw_token.strip("-_")
        if len(token) < min_length:
            continue
        if token in excluded_words:
            continue
        if token.isdigit():
            continue
        tokens.append(token)
    return tokens


def extract_vague_words(text: str) -> Counter:
    lowered = text.lower()
    vague_counter: Counter = Counter()

    for raw_token in TOKEN_RE.findall(lowered):
        token = raw_token.strip("-_")
        if token in VAGUE_WORDS:
            vague_counter[token] += 1

    for phrase in VAGUE_PHRASES:
        count = lowered.count(phrase)
        if count:
            vague_counter[phrase] += count

    return vague_counter


def extract_bold_words(text: str) -> Counter:
    lowered = text.lower()
    bold_counter: Counter = Counter()

    for raw_token in TOKEN_RE.findall(lowered):
        token = raw_token.strip("-_")
        if token in BOLD_WORDS:
            bold_counter[token] += 1

    for phrase in BOLD_PHRASES:
        count = lowered.count(phrase)
        if count:
            bold_counter[phrase] += count

    return bold_counter


def analyze_report(report_path: Path, min_length: int, excluded_words: set[str]) -> Tuple[str, Counter, Counter, Counter]:
    with report_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    report_name = data.get("assembly_name") or report_path.stem
    counter: Counter = Counter()
    vague_counter: Counter = Counter()
    bold_counter: Counter = Counter()
    for text in iter_strings(data):
        counter.update(tokenize(text, min_length=min_length, excluded_words=excluded_words))
        vague_counter.update(extract_vague_words(text))
        bold_counter.update(extract_bold_words(text))
    return report_name, counter, vague_counter, bold_counter


def analyze_input(input_path: Path, pattern: str, min_length: int, excluded_words: set[str]) -> Tuple[Dict[str, Counter], Counter, Dict[str, Counter], Counter, Dict[str, Counter], Counter]:
    report_files = detect_report_files(input_path, pattern)
    if not report_files:
        raise FileNotFoundError(f"No FFA report JSON files found at: {input_path}")

    report_counters: Dict[str, Counter] = {}
    overall_counter: Counter = Counter()
    vague_report_counters: Dict[str, Counter] = {}
    overall_vague_counter: Counter = Counter()
    bold_report_counters: Dict[str, Counter] = {}
    overall_bold_counter: Counter = Counter()

    for report_path in report_files:
        report_name, counter, vague_counter, bold_counter = analyze_report(report_path, min_length=min_length, excluded_words=excluded_words)
        report_counters[report_name] = counter
        overall_counter.update(counter)
        vague_report_counters[report_name] = vague_counter
        overall_vague_counter.update(vague_counter)
        bold_report_counters[report_name] = bold_counter
        overall_bold_counter.update(bold_counter)

    return report_counters, overall_counter, vague_report_counters, overall_vague_counter, bold_report_counters, overall_bold_counter


def counter_stats(counter: Counter) -> Dict[str, float]:
    total_words = int(sum(counter.values()))
    unique_words = int(len(counter))
    ratio = round((unique_words / total_words), 4) if total_words else 0.0
    top_word = counter.most_common(1)[0][0] if counter else "-"
    return {
        "total_words": total_words,
        "unique_words": unique_words,
        "unique_total_ratio": ratio,
        "top_word": top_word,
    }


def vague_stats(vague_counter: Counter, total_words: int) -> Dict[str, float]:
    vague_total = int(sum(vague_counter.values()))
    vague_ratio = round((vague_total / total_words), 4) if total_words else 0.0
    return {
        "vague_word_total": vague_total,
        "vague_total_ratio": vague_ratio,
    }


def bold_stats(bold_counter: Counter, total_words: int) -> Dict[str, float]:
    bold_total = int(sum(bold_counter.values()))
    bold_ratio = round((bold_total / total_words), 4) if total_words else 0.0
    return {
        "bold_word_total": bold_total,
        "bold_total_ratio": bold_ratio,
    }


def specificity_stats(counter: Counter, top_n: int = SPECIFICITY_TOP_N) -> Dict[str, float]:
    top_items = counter.most_common(top_n)
    top_total = int(sum(count for _, count in top_items))
    specific_total = int(sum(count for word, count in top_items if word in SPECIFIC_WORDS))
    generic_total = int(sum(count for word, count in top_items if word in GENERIC_WORDS))
    other_total = int(top_total - specific_total - generic_total)
    classified_total = int(specific_total + generic_total)
    return {
        "top_n": top_n,
        "top_total": top_total,
        "specific_total": specific_total,
        "generic_total": generic_total,
        "other_total": other_total,
        "classified_total": classified_total,
        "specific_ratio_top": round((specific_total / top_total), 4) if top_total else 0.0,
        "generic_ratio_top": round((generic_total / top_total), 4) if top_total else 0.0,
        "other_ratio_top": round((other_total / top_total), 4) if top_total else 0.0,
        "specific_ratio_classified": round((specific_total / classified_total), 4) if classified_total else 0.0,
        "generic_ratio_classified": round((generic_total / classified_total), 4) if classified_total else 0.0,
    }


def write_per_report_csv(report_counters: Dict[str, Counter], output_dir: Path) -> Path:
    output_path = output_dir / "per_report_word_counts.csv"
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["report", "word", "count"])
        for report_name in sorted(report_counters):
            for word, count in report_counters[report_name].most_common():
                writer.writerow([report_name, word, count])
    return output_path


def write_top_50_per_report_csv(report_counters: Dict[str, Counter], output_dir: Path) -> Path:
    output_path = output_dir / "top_50_words_per_report.csv"
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["report", "rank", "word", "count"])
        for report_name in sorted(report_counters):
            for rank, (word, count) in enumerate(report_counters[report_name].most_common(50), start=1):
                writer.writerow([report_name, rank, word, count])
    return output_path


def write_vague_words_csv(vague_report_counters: Dict[str, Counter], overall_vague_counter: Counter, output_dir: Path) -> Tuple[Path, Path]:
    per_report_path = output_dir / "vague_words_per_report.csv"
    with per_report_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["report", "word", "count"])
        for report_name in sorted(vague_report_counters):
            for word in ALL_VAGUE_TERMS:
                writer.writerow([report_name, word, vague_report_counters[report_name].get(word, 0)])

    overall_path = output_dir / "vague_words_overall.csv"
    with overall_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["word", "count"])
        for word in ALL_VAGUE_TERMS:
            writer.writerow([word, overall_vague_counter.get(word, 0)])

    return per_report_path, overall_path


def write_bold_words_csv(bold_report_counters: Dict[str, Counter], overall_bold_counter: Counter, output_dir: Path) -> Tuple[Path, Path]:
    per_report_path = output_dir / "bold_words_per_report.csv"
    with per_report_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["report", "word", "count"])
        for report_name in sorted(bold_report_counters):
            for word in ALL_BOLD_TERMS:
                writer.writerow([report_name, word, bold_report_counters[report_name].get(word, 0)])

    overall_path = output_dir / "bold_words_overall.csv"
    with overall_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["word", "count"])
        for word in ALL_BOLD_TERMS:
            writer.writerow([word, overall_bold_counter.get(word, 0)])

    return per_report_path, overall_path


def write_overall_csv(overall_counter: Counter, output_dir: Path) -> Path:
    output_path = output_dir / "overall_word_counts.csv"
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["word", "count"])
        for word, count in overall_counter.most_common():
            writer.writerow([word, count])
    return output_path


def write_matrix_csv(report_counters: Dict[str, Counter], overall_counter: Counter, output_dir: Path, top_n: int) -> Path:
    output_path = output_dir / "report_word_matrix.csv"
    top_words = [word for word, _ in overall_counter.most_common(top_n)]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["report", *top_words])
        for report_name in sorted(report_counters):
            counter = report_counters[report_name]
            writer.writerow([report_name, *[counter.get(word, 0) for word in top_words]])
    return output_path


def write_summary_json(
    report_counters: Dict[str, Counter],
    overall_counter: Counter,
    vague_report_counters: Dict[str, Counter],
    overall_vague_counter: Counter,
    bold_report_counters: Dict[str, Counter],
    overall_bold_counter: Counter,
    output_dir: Path,
    input_path: Path,
    top_n: int,
) -> Path:
    output_path = output_dir / "word_usage_summary.json"
    summary = {
        "input_path": str(input_path),
        "report_count": len(report_counters),
        "reports": {
            report_name: {
                **counter_stats(counter),
                **vague_stats(vague_report_counters[report_name], int(sum(counter.values()))),
                **bold_stats(bold_report_counters[report_name], int(sum(counter.values()))),
                "top_20_words": [{"word": word, "count": count} for word, count in counter.most_common(20)],
                "top_words": [{"word": word, "count": count} for word, count in counter.most_common(25)],
                "vague_words": {word: vague_report_counters[report_name].get(word, 0) for word in ALL_VAGUE_TERMS},
                "bold_words": {word: bold_report_counters[report_name].get(word, 0) for word in ALL_BOLD_TERMS},
            }
            for report_name, counter in sorted(report_counters.items())
        },
        "overall": {
            **counter_stats(overall_counter),
            **vague_stats(overall_vague_counter, int(sum(overall_counter.values()))),
            **bold_stats(overall_bold_counter, int(sum(overall_counter.values()))),
            "top_words": [{"word": word, "count": count} for word, count in overall_counter.most_common(top_n)],
            "vague_words": {word: overall_vague_counter.get(word, 0) for word in ALL_VAGUE_TERMS},
            "bold_words": {word: overall_bold_counter.get(word, 0) for word in ALL_BOLD_TERMS},
        },
    }
    output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


def print_summary(report_counters: Dict[str, Counter], overall_counter: Counter) -> None:
    print("\n" + "=" * 88)
    print("FFA REPORT WORD USAGE")
    print("=" * 88)
    overall_stats = counter_stats(overall_counter)
    print(f"Reports analyzed: {len(report_counters)}")
    print(f"Overall total words: {overall_stats['total_words']}")
    print(f"Overall unique words: {overall_stats['unique_words']}")
    print("-" * 88)
    print(f"{'REPORT':<35} {'TOTAL':>10} {'UNIQUE':>10} {'UNIQUE/TOTAL':>14} {'TOP WORD':>16}")
    print("-" * 88)
    for report_name in sorted(report_counters):
        stats = counter_stats(report_counters[report_name])
        print(
            f"{report_name:<35} {stats['total_words']:>10} {stats['unique_words']:>10} "
            f"{stats['unique_total_ratio']:>14.4f} {stats['top_word']:>16}"
        )
    print("=" * 88)


def intersect_report_names(report_counters_a: Dict[str, Counter], report_counters_b: Dict[str, Counter]) -> List[str]:
    return sorted(set(report_counters_a) & set(report_counters_b))


def write_comparison_report_summary(
    report_counters_a: Dict[str, Counter],
    report_counters_b: Dict[str, Counter],
    vague_report_counters_a: Dict[str, Counter],
    vague_report_counters_b: Dict[str, Counter],
    bold_report_counters_a: Dict[str, Counter],
    bold_report_counters_b: Dict[str, Counter],
    matched_reports: List[str],
    output_dir: Path,
    label_a: str,
    label_b: str,
) -> Path:
    output_path = output_dir / "comparison_report_summary.csv"
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "report",
            f"{label_a}_total",
            f"{label_a}_unique",
            f"{label_a}_unique_total_ratio",
            f"{label_b}_total",
            f"{label_b}_unique",
            f"{label_b}_unique_total_ratio",
            f"{label_a}_vague_total",
            f"{label_a}_vague_total_ratio",
            f"{label_b}_vague_total",
            f"{label_b}_vague_total_ratio",
            f"{label_a}_bold_total",
            f"{label_a}_bold_total_ratio",
            f"{label_b}_bold_total",
            f"{label_b}_bold_total_ratio",
            "shared_unique_words",
            f"unique_to_{label_a}",
            f"unique_to_{label_b}",
        ])
        for report_name in matched_reports:
            counter_a = report_counters_a[report_name]
            counter_b = report_counters_b[report_name]
            stats_a = counter_stats(counter_a)
            stats_b = counter_stats(counter_b)
            vague_a = vague_stats(vague_report_counters_a[report_name], stats_a["total_words"])
            vague_b = vague_stats(vague_report_counters_b[report_name], stats_b["total_words"])
            bold_a = bold_stats(bold_report_counters_a[report_name], stats_a["total_words"])
            bold_b = bold_stats(bold_report_counters_b[report_name], stats_b["total_words"])
            words_a = set(counter_a)
            words_b = set(counter_b)
            writer.writerow([
                report_name,
                stats_a["total_words"],
                stats_a["unique_words"],
                stats_a["unique_total_ratio"],
                stats_b["total_words"],
                stats_b["unique_words"],
                stats_b["unique_total_ratio"],
                vague_a["vague_word_total"],
                vague_a["vague_total_ratio"],
                vague_b["vague_word_total"],
                vague_b["vague_total_ratio"],
                bold_a["bold_word_total"],
                bold_a["bold_total_ratio"],
                bold_b["bold_word_total"],
                bold_b["bold_total_ratio"],
                len(words_a & words_b),
                len(words_a - words_b),
                len(words_b - words_a),
            ])
    return output_path


def write_comparison_top_50(
    report_counters_a: Dict[str, Counter],
    report_counters_b: Dict[str, Counter],
    matched_reports: List[str],
    output_dir: Path,
    label_a: str,
    label_b: str,
) -> Path:
    output_path = output_dir / "comparison_top_50_words_per_report.csv"
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["report", "system", "rank", "word", "count"])
        for report_name in matched_reports:
            for rank, (word, count) in enumerate(report_counters_a[report_name].most_common(50), start=1):
                writer.writerow([report_name, label_a, rank, word, count])
            for rank, (word, count) in enumerate(report_counters_b[report_name].most_common(50), start=1):
                writer.writerow([report_name, label_b, rank, word, count])
    return output_path


def write_comparison_top_50_word_categories(
    report_counters_a: Dict[str, Counter],
    report_counters_b: Dict[str, Counter],
    matched_reports: List[str],
    output_dir: Path,
    label_a: str,
    label_b: str,
) -> Tuple[Path, Path]:
    detailed_path = output_dir / "comparison_top_50_word_categories.csv"
    summary_path = output_dir / "comparison_category_summary.csv"

    with detailed_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["report", "system", "rank", "word", "count", "category"])
        for report_name in matched_reports:
            for system_label, counter in (
                (label_a, report_counters_a[report_name]),
                (label_b, report_counters_b[report_name]),
            ):
                for rank, (word, count) in enumerate(counter.most_common(50), start=1):
                    writer.writerow([report_name, system_label, rank, word, count, categorize_word(word)])

    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["report", "system", "category", "word_count", "share_top_50"])
        for report_name in matched_reports:
            for system_label, counter in (
                (label_a, report_counters_a[report_name]),
                (label_b, report_counters_b[report_name]),
            ):
                top_items = counter.most_common(50)
                top_total = sum(count for _, count in top_items)
                category_counter: Counter = Counter()
                for word, count in top_items:
                    category_counter[categorize_word(word)] += count
                for category_name in [*WORD_CATEGORIES.keys(), "other"]:
                    category_total = int(category_counter.get(category_name, 0))
                    share = round((category_total / top_total), 4) if top_total else 0.0
                    writer.writerow([report_name, system_label, category_name, category_total, share])

    return detailed_path, summary_path


def write_category_composition_plot(
    report_counters_a: Dict[str, Counter],
    report_counters_b: Dict[str, Counter],
    matched_reports: List[str],
    output_dir: Path,
    label_a: str,
    label_b: str,
) -> Path | None:
    if plt is None:
        return None

    category_order = [
        "part_specific",
        "geometry_interface",
        "process_handling",
        "evaluation_quality",
        "discourse_vague",
        "other",
    ]
    category_colors = {
        "part_specific": "#1b9e77",
        "geometry_interface": "#377eb8",
        "process_handling": "#984ea3",
        "evaluation_quality": "#e6ab02",
        "discourse_vague": "#e7298a",
        "other": "#bdbdbd",
    }

    def category_shares(counter: Counter) -> Dict[str, float]:
        top_items = counter.most_common(50)
        top_total = sum(count for _, count in top_items)
        category_counter: Counter = Counter()
        for word, count in top_items:
            category_counter[categorize_word(word)] += count
        return {
            category: (category_counter.get(category, 0) / top_total if top_total else 0.0)
            for category in category_order
        }

    shares_a = [category_shares(report_counters_a[report]) for report in matched_reports]
    shares_b = [category_shares(report_counters_b[report]) for report in matched_reports]

    fig, ax = plt.subplots(figsize=(max(12, len(matched_reports) * 1.6), 7))
    x = list(range(len(matched_reports)))
    width = 0.36

    bottom_a = [0.0] * len(matched_reports)
    bottom_b = [0.0] * len(matched_reports)

    for category in category_order:
        values_a = [share_map[category] for share_map in shares_a]
        values_b = [share_map[category] for share_map in shares_b]
        ax.bar(
            [i - width / 2 for i in x],
            values_a,
            width=width,
            bottom=bottom_a,
            color=category_colors[category],
            edgecolor=PLOT_COLOR_A,
            linewidth=0.9,
            label=category if category == category_order[0] else None,
        )
        ax.bar(
            [i + width / 2 for i in x],
            values_b,
            width=width,
            bottom=bottom_b,
            color=category_colors[category],
            edgecolor=PLOT_COLOR_B,
            linewidth=0.9,
        )
        bottom_a = [b + v for b, v in zip(bottom_a, values_a)]
        bottom_b = [b + v for b, v in zip(bottom_b, values_b)]

    category_handles = [
        plt.Rectangle((0, 0), 1, 1, color=category_colors[category])
        for category in category_order
    ]
    category_labels = [
        "Part specific",
        "Geometry / interface",
        "Process / handling",
        "Evaluation / quality",
        "Discourse / vague",
        "Other",
    ]
    system_handles = [
        plt.Rectangle((0, 0), 1, 1, facecolor="white", edgecolor=PLOT_COLOR_A, linewidth=1.5),
        plt.Rectangle((0, 0), 1, 1, facecolor="white", edgecolor=PLOT_COLOR_B, linewidth=1.5),
    ]

    ax.set_xticks(x)
    ax.set_xticklabels(matched_reports, rotation=25, ha="right")
    ax.set_ylim(0, 1)
    ax.set_ylabel("Relative share within Top 50 words")
    ax.set_title("Category Composition by Assembly", fontweight="bold")
    ax.grid(axis="y", alpha=0.25)

    # System labels under each pair
    for i in x:
        ax.text(i - width / 2, -0.06, "A", ha="center", va="top", transform=ax.get_xaxis_transform(), color=PLOT_COLOR_A, fontweight="bold")
        ax.text(i + width / 2, -0.06, "B", ha="center", va="top", transform=ax.get_xaxis_transform(), color=PLOT_COLOR_B, fontweight="bold")

    legend1 = ax.legend(category_handles, category_labels, loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False)
    ax.add_artist(legend1)
    ax.legend(system_handles, [label_a, label_b], loc="lower left", bbox_to_anchor=(1.01, 0.0), frameon=False)

    fig.tight_layout()
    output_path = output_dir / "comparison_category_composition.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def write_comparison_shared_words(
    report_counters_a: Dict[str, Counter],
    report_counters_b: Dict[str, Counter],
    matched_reports: List[str],
    output_dir: Path,
    top_n: int,
) -> Path:
    output_path = output_dir / "comparison_shared_words.csv"
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["report", "word", "count_a", "count_b", "combined_count"])
        for report_name in matched_reports:
            counter_a = report_counters_a[report_name]
            counter_b = report_counters_b[report_name]
            shared = []
            for word in set(counter_a) & set(counter_b):
                count_a = counter_a[word]
                count_b = counter_b[word]
                shared.append((word, count_a, count_b, count_a + count_b))
            shared.sort(key=lambda item: (-item[3], item[0]))
            for word, count_a, count_b, combined in shared[:top_n]:
                writer.writerow([report_name, word, count_a, count_b, combined])
    return output_path


def write_comparison_unique_words(
    report_counters_a: Dict[str, Counter],
    report_counters_b: Dict[str, Counter],
    matched_reports: List[str],
    output_dir: Path,
    label_a: str,
    label_b: str,
    top_n: int,
) -> Path:
    output_path = output_dir / "comparison_unique_words.csv"
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["report", "system", "word", "count"])
        for report_name in matched_reports:
            counter_a = report_counters_a[report_name]
            counter_b = report_counters_b[report_name]
            unique_a = [(word, counter_a[word]) for word in set(counter_a) - set(counter_b)]
            unique_b = [(word, counter_b[word]) for word in set(counter_b) - set(counter_a)]
            unique_a.sort(key=lambda item: (-item[1], item[0]))
            unique_b.sort(key=lambda item: (-item[1], item[0]))
            for word, count in unique_a[:top_n]:
                writer.writerow([report_name, label_a, word, count])
            for word, count in unique_b[:top_n]:
                writer.writerow([report_name, label_b, word, count])
    return output_path


def write_system_unique_word_lists(
    overall_counter_a: Counter,
    overall_counter_b: Counter,
    output_dir: Path,
    label_a: str,
    label_b: str,
) -> Tuple[Path, Path, Path, Path]:
    """Write full and count-filtered unique-word CSV files for both systems."""
    words_a = sorted(set(overall_counter_a) - set(overall_counter_b))
    words_b = sorted(set(overall_counter_b) - set(overall_counter_a))
    words_a_gt5 = [word for word in words_a if overall_counter_a[word] > 5]
    words_b_gt5 = [word for word in words_b if overall_counter_b[word] > 5]

    safe_label_a = label_a.replace(" ", "_")
    safe_label_b = label_b.replace(" ", "_")

    path_a = output_dir / f"unique_words_{safe_label_a}.csv"
    with path_a.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["word"])
        for word in words_a:
            writer.writerow([word])

    path_b = output_dir / f"unique_words_{safe_label_b}.csv"
    with path_b.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["word"])
        for word in words_b:
            writer.writerow([word])

    path_a_gt5 = output_dir / f"unique_words_{safe_label_a}_gt5.csv"
    with path_a_gt5.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["word"])
        for word in words_a_gt5:
            writer.writerow([word])

    path_b_gt5 = output_dir / f"unique_words_{safe_label_b}_gt5.csv"
    with path_b_gt5.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["word"])
        for word in words_b_gt5:
            writer.writerow([word])

    return path_a, path_b, path_a_gt5, path_b_gt5


def write_comparison_system_overview_plot(
    overall_counter_a: Counter,
    overall_counter_b: Counter,
    overall_vague_counter_a: Counter,
    overall_vague_counter_b: Counter,
    overall_bold_counter_a: Counter,
    overall_bold_counter_b: Counter,
    output_dir: Path,
    label_a: str,
    label_b: str,
) -> Path | None:
    """Create a compact system overview plot for A vs B."""
    if plt is None:
        return None

    stats_a = counter_stats(overall_counter_a)
    stats_b = counter_stats(overall_counter_b)
    vague_a = vague_stats(overall_vague_counter_a, stats_a["total_words"])
    vague_b = vague_stats(overall_vague_counter_b, stats_b["total_words"])
    bold_a = bold_stats(overall_bold_counter_a, stats_a["total_words"])
    bold_b = bold_stats(overall_bold_counter_b, stats_b["total_words"])

    ratio_labels = ["Unique/Total", "Vague/Total", "Bold/Total"]
    ratio_values_a = [
        stats_a["unique_total_ratio"],
        vague_a["vague_total_ratio"],
        bold_a["bold_total_ratio"],
    ]
    ratio_values_b = [
        stats_b["unique_total_ratio"],
        vague_b["vague_total_ratio"],
        bold_b["bold_total_ratio"],
    ]

    count_labels = ["Total Words", "Unique Words", "Vague Words", "Bold Words"]
    count_values_a = [
        stats_a["total_words"],
        stats_a["unique_words"],
        vague_a["vague_word_total"],
        bold_a["bold_word_total"],
    ]
    count_values_b = [
        stats_b["total_words"],
        stats_b["unique_words"],
        vague_b["vague_word_total"],
        bold_b["bold_word_total"],
    ]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    color_a = PLOT_COLOR_A
    color_b = PLOT_COLOR_B
    width = 0.36

    x_ratio = range(len(ratio_labels))
    axes[0].bar([x - width / 2 for x in x_ratio], ratio_values_a, width=width, color=color_a, label=label_a)
    axes[0].bar([x + width / 2 for x in x_ratio], ratio_values_b, width=width, color=color_b, label=label_b)
    axes[0].set_xticks(list(x_ratio))
    axes[0].set_xticklabels(ratio_labels, rotation=12)
    axes[0].set_title("Ratios", fontweight="bold")
    axes[0].set_ylabel("Ratio")
    axes[0].grid(axis="y", alpha=0.25)

    x_count = range(len(count_labels))
    axes[1].bar([x - width / 2 for x in x_count], count_values_a, width=width, color=color_a, label=label_a)
    axes[1].bar([x + width / 2 for x in x_count], count_values_b, width=width, color=color_b, label=label_b)
    axes[1].set_xticks(list(x_count))
    axes[1].set_xticklabels(count_labels, rotation=12)
    axes[1].set_title("Counts", fontweight="bold")
    axes[1].set_ylabel("Count")
    axes[1].grid(axis="y", alpha=0.25)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False)
    fig.suptitle("FFA Report Word Usage: System Comparison", fontweight="bold")
    fig.tight_layout(rect=(0, 0.08, 1, 0.95))

    output_path = output_dir / "comparison_system_overview.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def write_specific_vs_generic_csv(
    report_counters_a: Dict[str, Counter],
    report_counters_b: Dict[str, Counter],
    matched_reports: List[str],
    output_dir: Path,
    label_a: str,
    label_b: str,
    top_n: int = 20,
) -> Path:
    output_path = output_dir / "comparison_specific_vs_generic.csv"
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "report",
            "system",
            "top_n",
            "top_total",
            "specific_total",
            "generic_total",
            "other_total",
            "classified_total",
            "specific_ratio_top",
            "generic_ratio_top",
            "other_ratio_top",
            "specific_ratio_classified",
            "generic_ratio_classified",
        ])
        for report_name in matched_reports:
            for system_label, counter in (
                (label_a, report_counters_a[report_name]),
                (label_b, report_counters_b[report_name]),
            ):
                stats = specificity_stats(counter, top_n=top_n)
                writer.writerow([
                    report_name,
                    system_label,
                    stats["top_n"],
                    stats["top_total"],
                    stats["specific_total"],
                    stats["generic_total"],
                    stats["other_total"],
                    stats["classified_total"],
                    stats["specific_ratio_top"],
                    stats["generic_ratio_top"],
                    stats["other_ratio_top"],
                    stats["specific_ratio_classified"],
                    stats["generic_ratio_classified"],
                ])
    return output_path


def write_specific_vs_generic_plot(
    report_counters_a: Dict[str, Counter],
    report_counters_b: Dict[str, Counter],
    overall_counter_a: Counter,
    overall_counter_b: Counter,
    matched_reports: List[str],
    output_dir: Path,
    label_a: str,
    label_b: str,
    top_n: int = 20,
) -> Path | None:
    if plt is None:
        return None

    report_labels = matched_reports + ["OVERALL"]

    specific_a = []
    generic_a = []
    specific_b = []
    generic_b = []

    # Reports
    for report in matched_reports:
        stats_a = specificity_stats(report_counters_a[report], top_n)
        stats_b = specificity_stats(report_counters_b[report], top_n)

        specific_a.append(stats_a["specific_ratio_classified"])
        generic_a.append(stats_a["generic_ratio_classified"])

        specific_b.append(stats_b["specific_ratio_classified"])
        generic_b.append(stats_b["generic_ratio_classified"])

    # Overall
    stats_a = specificity_stats(overall_counter_a, top_n=top_n)
    stats_b = specificity_stats(overall_counter_b, top_n=top_n)

    specific_a.append(stats_a["specific_ratio_classified"])
    generic_a.append(stats_a["generic_ratio_classified"])
    specific_b.append(stats_b["specific_ratio_classified"])
    generic_b.append(stats_b["generic_ratio_classified"])

    # Plot
    fig, ax = plt.subplots(figsize=(max(12, len(report_labels) * 1.6), 6))

    x = list(range(len(report_labels)))
    width = 0.35

    color_a = PLOT_COLOR_A   # dein Orange
    color_b = PLOT_COLOR_B   # dein Grün

    # Balken A (gestapelt)
    ax.bar([i - width/2 for i in x], generic_a, width=width, color=color_a, alpha=0.4, label=f"{label_a} (generic)")
    ax.bar([i - width/2 for i in x], specific_a, width=width, bottom=generic_a, color=color_a, label=f"{label_a} (specific)")

    # Balken B (gestapelt)
    ax.bar([i + width/2 for i in x], generic_b, width=width, color=color_b, alpha=0.4, label=f"{label_b} (generic)")
    ax.bar([i + width/2 for i in x], specific_b, width=width, bottom=generic_b, color=color_b, label=f"{label_b} (specific)")

    ax.set_xticks(x)
    ax.set_xticklabels(report_labels, rotation=25, ha="right")
    ax.set_ylabel("Relative share (within classified words)")
    ax.set_ylim(0, 1)
    ax.set_title("Relative Composition of Specific vs Generic Terms", fontweight="bold")

    ax.grid(axis="y", alpha=0.25)

    ax.legend(loc="upper center", ncol=2, frameon=False)
    fig.tight_layout()

    output_path = output_dir / "comparison_specific_vs_generic_stacked.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)

    return output_path


def write_comparison_summary_json(
    report_counters_a: Dict[str, Counter],
    report_counters_b: Dict[str, Counter],
    overall_counter_a: Counter,
    overall_counter_b: Counter,
    vague_report_counters_a: Dict[str, Counter],
    vague_report_counters_b: Dict[str, Counter],
    overall_vague_counter_a: Counter,
    overall_vague_counter_b: Counter,
    bold_report_counters_a: Dict[str, Counter],
    bold_report_counters_b: Dict[str, Counter],
    overall_bold_counter_a: Counter,
    overall_bold_counter_b: Counter,
    matched_reports: List[str],
    unmatched_a: List[str],
    unmatched_b: List[str],
    output_dir: Path,
    label_a: str,
    label_b: str,
    input_path_a: Path,
    input_path_b: Path,
) -> Path:
    output_path = output_dir / "comparison_summary.json"
    summary = {
        "inputs": {
            label_a: str(input_path_a),
            label_b: str(input_path_b),
        },
        "matched_reports": matched_reports,
        f"unmatched_{label_a}": unmatched_a,
        f"unmatched_{label_b}": unmatched_b,
        "overall": {
            label_a: {
                **counter_stats(overall_counter_a),
                **vague_stats(overall_vague_counter_a, int(sum(overall_counter_a.values()))),
                **bold_stats(overall_bold_counter_a, int(sum(overall_counter_a.values()))),
                **specificity_stats(overall_counter_a, top_n=SPECIFICITY_TOP_N),
                "top_20_words": [{"word": word, "count": count} for word, count in overall_counter_a.most_common(20)],
                "vague_words": {word: overall_vague_counter_a.get(word, 0) for word in ALL_VAGUE_TERMS},
                "bold_words": {word: overall_bold_counter_a.get(word, 0) for word in ALL_BOLD_TERMS},
            },
            label_b: {
                **counter_stats(overall_counter_b),
                **vague_stats(overall_vague_counter_b, int(sum(overall_counter_b.values()))),
                **bold_stats(overall_bold_counter_b, int(sum(overall_counter_b.values()))),
                **specificity_stats(overall_counter_b, top_n=SPECIFICITY_TOP_N),
                "top_20_words": [{"word": word, "count": count} for word, count in overall_counter_b.most_common(20)],
                "vague_words": {word: overall_vague_counter_b.get(word, 0) for word in ALL_VAGUE_TERMS},
                "bold_words": {word: overall_bold_counter_b.get(word, 0) for word in ALL_BOLD_TERMS},
            },
        },
        "reports": {},
    }

    for report_name in matched_reports:
        counter_a = report_counters_a[report_name]
        counter_b = report_counters_b[report_name]
        words_a = set(counter_a)
        words_b = set(counter_b)
        summary["reports"][report_name] = {
            label_a: {
                **counter_stats(counter_a),
                **vague_stats(vague_report_counters_a[report_name], int(sum(counter_a.values()))),
                **bold_stats(bold_report_counters_a[report_name], int(sum(counter_a.values()))),
                **specificity_stats(counter_a, top_n=SPECIFICITY_TOP_N),
                "top_20_words": [{"word": word, "count": count} for word, count in counter_a.most_common(20)],
                "vague_words": {word: vague_report_counters_a[report_name].get(word, 0) for word in ALL_VAGUE_TERMS},
                "bold_words": {word: bold_report_counters_a[report_name].get(word, 0) for word in ALL_BOLD_TERMS},
            },
            label_b: {
                **counter_stats(counter_b),
                **vague_stats(vague_report_counters_b[report_name], int(sum(counter_b.values()))),
                **bold_stats(bold_report_counters_b[report_name], int(sum(counter_b.values()))),
                **specificity_stats(counter_b, top_n=SPECIFICITY_TOP_N),
                "top_20_words": [{"word": word, "count": count} for word, count in counter_b.most_common(20)],
                "vague_words": {word: vague_report_counters_b[report_name].get(word, 0) for word in ALL_VAGUE_TERMS},
                "bold_words": {word: bold_report_counters_b[report_name].get(word, 0) for word in ALL_BOLD_TERMS},
            },
            "shared_unique_words": len(words_a & words_b),
            f"unique_to_{label_a}": [{"word": word, "count": counter_a[word]} for word in sorted(words_a - words_b, key=lambda w: (-counter_a[w], w))[:20]],
            f"unique_to_{label_b}": [{"word": word, "count": counter_b[word]} for word in sorted(words_b - words_a, key=lambda w: (-counter_b[w], w))[:20]],
        }

    output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


def print_comparison_summary(
    report_counters_a: Dict[str, Counter],
    report_counters_b: Dict[str, Counter],
    overall_counter_a: Counter,
    overall_counter_b: Counter,
    overall_vague_counter_a: Counter,
    overall_vague_counter_b: Counter,
    overall_bold_counter_a: Counter,
    overall_bold_counter_b: Counter,
    matched_reports: List[str],
    label_a: str,
    label_b: str,
) -> None:
    print("\n" + "=" * 110)
    print("FFA REPORT WORD USAGE COMPARISON")
    print("=" * 110)
    print(f"Matched reports: {len(matched_reports)}")
    stats_a = counter_stats(overall_counter_a)
    stats_b = counter_stats(overall_counter_b)
    vague_a = vague_stats(overall_vague_counter_a, stats_a["total_words"])
    vague_b = vague_stats(overall_vague_counter_b, stats_b["total_words"])
    bold_a = bold_stats(overall_bold_counter_a, stats_a["total_words"])
    bold_b = bold_stats(overall_bold_counter_b, stats_b["total_words"])
    print(f"{label_a}: total={stats_a['total_words']}, unique={stats_a['unique_words']}, ratio={stats_a['unique_total_ratio']:.4f}")
    print(f"{label_b}: total={stats_b['total_words']}, unique={stats_b['unique_words']}, ratio={stats_b['unique_total_ratio']:.4f}")
    print(f"{label_a}: vague_total={vague_a['vague_word_total']}, vague_ratio={vague_a['vague_total_ratio']:.4f}")
    print(f"{label_b}: vague_total={vague_b['vague_word_total']}, vague_ratio={vague_b['vague_total_ratio']:.4f}")
    print(f"{label_a}: bold_total={bold_a['bold_word_total']}, bold_ratio={bold_a['bold_total_ratio']:.4f}")
    print(f"{label_b}: bold_total={bold_b['bold_word_total']}, bold_ratio={bold_b['bold_total_ratio']:.4f}")
    print("-" * 110)
    print(
        f"{'REPORT':<30} "
        f"{label_a + ' U/T':>14} "
        f"{label_b + ' U/T':>14} "
        f"{'SHARED':>10} "
        f"{('ONLY ' + label_a):>14} "
        f"{('ONLY ' + label_b):>14}"
    )
    print("-" * 110)
    for report_name in matched_reports:
        counter_a = report_counters_a[report_name]
        counter_b = report_counters_b[report_name]
        stats_a = counter_stats(counter_a)
        stats_b = counter_stats(counter_b)
        words_a = set(counter_a)
        words_b = set(counter_b)
        print(
            f"{report_name:<30} "
            f"{stats_a['unique_total_ratio']:>14.4f} "
            f"{stats_b['unique_total_ratio']:>14.4f} "
            f"{len(words_a & words_b):>10} "
            f"{len(words_a - words_b):>14} "
            f"{len(words_b - words_a):>14}"
        )
    print("=" * 110)


def run_single_mode(args: argparse.Namespace, excluded_words: set[str]) -> int:
    if not args.input_path.exists():
        print(f"Input path not found: {args.input_path}", file=sys.stderr)
        return 1

    try:
        report_counters, overall_counter, vague_report_counters, overall_vague_counter, bold_report_counters, overall_bold_counter = analyze_input(
            args.input_path,
            pattern=args.pattern,
            min_length=args.min_length,
            excluded_words=excluded_words,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    print_summary(report_counters, overall_counter)

    per_report_csv = write_per_report_csv(report_counters, args.output_dir)
    top_50_csv = write_top_50_per_report_csv(report_counters, args.output_dir)
    vague_per_report_csv, vague_overall_csv = write_vague_words_csv(vague_report_counters, overall_vague_counter, args.output_dir)
    bold_per_report_csv, bold_overall_csv = write_bold_words_csv(bold_report_counters, overall_bold_counter, args.output_dir)
    overall_csv = write_overall_csv(overall_counter, args.output_dir)
    matrix_csv = write_matrix_csv(report_counters, overall_counter, args.output_dir, args.top_n)
    summary_json = write_summary_json(
        report_counters,
        overall_counter,
        vague_report_counters,
        overall_vague_counter,
        bold_report_counters,
        overall_bold_counter,
        args.output_dir,
        args.input_path,
        args.top_n,
    )

    print(f"Saved per-report CSV: {per_report_csv}")
    print(f"Saved top-50 CSV:     {top_50_csv}")
    print(f"Saved vague CSV:      {vague_per_report_csv}")
    print(f"Saved vague overall:  {vague_overall_csv}")
    print(f"Saved bold CSV:       {bold_per_report_csv}")
    print(f"Saved bold overall:   {bold_overall_csv}")
    print(f"Saved overall CSV:    {overall_csv}")
    print(f"Saved matrix CSV:     {matrix_csv}")
    print(f"Saved summary JSON:   {summary_json}")
    return 0


def run_comparison_mode(args: argparse.Namespace, excluded_words: set[str]) -> int:
    if not args.input_path.exists():
        print(f"Input path A not found: {args.input_path}", file=sys.stderr)
        return 1
    if not args.input_path_b or not args.input_path_b.exists():
        print(f"Input path B not found: {args.input_path_b}", file=sys.stderr)
        return 1

    try:
        report_counters_a, overall_counter_a, vague_report_counters_a, overall_vague_counter_a, bold_report_counters_a, overall_bold_counter_a = analyze_input(
            args.input_path,
            pattern=args.pattern,
            min_length=args.min_length,
            excluded_words=excluded_words,
        )
        report_counters_b, overall_counter_b, vague_report_counters_b, overall_vague_counter_b, bold_report_counters_b, overall_bold_counter_b = analyze_input(
            args.input_path_b,
            pattern=args.pattern,
            min_length=args.min_length,
            excluded_words=excluded_words,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    matched_reports = intersect_report_names(report_counters_a, report_counters_b)
    unmatched_a = sorted(set(report_counters_a) - set(report_counters_b))
    unmatched_b = sorted(set(report_counters_b) - set(report_counters_a))

    print_comparison_summary(
        report_counters_a,
        report_counters_b,
        overall_counter_a,
        overall_counter_b,
        overall_vague_counter_a,
        overall_vague_counter_b,
        overall_bold_counter_a,
        overall_bold_counter_b,
        matched_reports,
        args.label_a,
        args.label_b,
    )

    summary_csv = write_comparison_report_summary(
        report_counters_a,
        report_counters_b,
        vague_report_counters_a,
        vague_report_counters_b,
        bold_report_counters_a,
        bold_report_counters_b,
        matched_reports,
        args.output_dir,
        args.label_a,
        args.label_b,
    )
    top50_csv = write_comparison_top_50(
        report_counters_a,
        report_counters_b,
        matched_reports,
        args.output_dir,
        args.label_a,
        args.label_b,
    )
    category_detail_csv, category_summary_csv = write_comparison_top_50_word_categories(
        report_counters_a,
        report_counters_b,
        matched_reports,
        args.output_dir,
        args.label_a,
        args.label_b,
    )
    category_plot = write_category_composition_plot(
        report_counters_a,
        report_counters_b,
        matched_reports,
        args.output_dir,
        args.label_a,
        args.label_b,
    )
    shared_csv = write_comparison_shared_words(
        report_counters_a,
        report_counters_b,
        matched_reports,
        args.output_dir,
        args.top_n,
    )
    unique_csv = write_comparison_unique_words(
        report_counters_a,
        report_counters_b,
        matched_reports,
        args.output_dir,
        args.label_a,
        args.label_b,
        args.top_n,
    )
    specific_generic_csv = write_specific_vs_generic_csv(
        report_counters_a,
        report_counters_b,
        matched_reports,
        args.output_dir,
        args.label_a,
        args.label_b,
        top_n=SPECIFICITY_TOP_N,
    )
    unique_list_a, unique_list_b, unique_list_a_gt5, unique_list_b_gt5 = write_system_unique_word_lists(
        overall_counter_a,
        overall_counter_b,
        args.output_dir,
        args.label_a,
        args.label_b,
    )
    specific_generic_plot = write_specific_vs_generic_plot(
        report_counters_a,
        report_counters_b,
        overall_counter_a,
        overall_counter_b,
        matched_reports,
        args.output_dir,
        args.label_a,
        args.label_b,
        top_n=SPECIFICITY_TOP_N,
    )
    overview_plot = write_comparison_system_overview_plot(
        overall_counter_a,
        overall_counter_b,
        overall_vague_counter_a,
        overall_vague_counter_b,
        overall_bold_counter_a,
        overall_bold_counter_b,
        args.output_dir,
        args.label_a,
        args.label_b,
    )
    summary_json = write_comparison_summary_json(
        report_counters_a,
        report_counters_b,
        overall_counter_a,
        overall_counter_b,
        vague_report_counters_a,
        vague_report_counters_b,
        overall_vague_counter_a,
        overall_vague_counter_b,
        bold_report_counters_a,
        bold_report_counters_b,
        overall_bold_counter_a,
        overall_bold_counter_b,
        matched_reports,
        unmatched_a,
        unmatched_b,
        args.output_dir,
        args.label_a,
        args.label_b,
        args.input_path,
        args.input_path_b,
    )

    print(f"Saved comparison summary CSV: {summary_csv}")
    print(f"Saved comparison top-50 CSV:  {top50_csv}")
    print(f"Saved category detail CSV:    {category_detail_csv}")
    print(f"Saved category summary CSV:   {category_summary_csv}")
    if category_plot is not None:
        print(f"Saved category plot:          {category_plot}")
    else:
        print("Skipped category plot:        matplotlib not available")
    print(f"Saved shared-words CSV:       {shared_csv}")
    print(f"Saved unique-words CSV:       {unique_csv}")
    print(f"Saved specific/generic CSV:   {specific_generic_csv}")
    print(f"Saved unique list {args.label_a}: {unique_list_a}")
    print(f"Saved unique list {args.label_b}: {unique_list_b}")
    print(f"Saved unique list {args.label_a} >5: {unique_list_a_gt5}")
    print(f"Saved unique list {args.label_b} >5: {unique_list_b_gt5}")
    if specific_generic_plot is not None:
        print(f"Saved specific/generic plot:  {specific_generic_plot}")
    else:
        print("Skipped specific/generic plot: matplotlib not available")
    if overview_plot is not None:
        print(f"Saved overview plot:          {overview_plot}")
    else:
        print("Skipped overview plot:        matplotlib not available")
    print(f"Saved comparison JSON:        {summary_json}")
    if unmatched_a:
        print(f"Unmatched in {args.label_a}: {len(unmatched_a)}")
    if unmatched_b:
        print(f"Unmatched in {args.label_b}: {len(unmatched_b)}")
    return 0


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    excluded_words = build_exclusion_set(
        keep_stopwords=args.keep_stopwords,
        extra_exclusions=args.exclude,
    )

    if args.input_path_b is not None:
        return run_comparison_mode(args, excluded_words)
    return run_single_mode(args, excluded_words)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
