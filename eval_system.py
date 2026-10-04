"""Repeatable, ground-truth-sequence evaluation for the product workflow.

Only deterministic STEP preprocessing and fixed sequence renderings are shared.
Each repetition owns its complete stochastic analysis context and BOM.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import sys
import traceback
from typing import Any

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
for import_root in (SRC, ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from assembly_automation.workflows.definitions import AssemblyAssessmentWorkflow
from assembly_automation.workflows.runtime.configuration import load_settings
from assembly_automation.workflows.runtime.environment import load_project_environment
from assembly_automation.workflows.nodes.ffa_scoring.mapping import load_mapping

DEFAULT_INPUT = ROOT / "data/input/Evaluierungsset"
DEFAULT_SEQUENCES = ROOT / "data/ground_truth/assembly_sequence_ground_truth"
DEFAULT_FFA_GT = ROOT / "data/ground_truth/ffa_ground_truth_evaluierungsdaten"
DEFAULT_OUTPUT = ROOT / "data/evaluations"
DEFAULT_CONFIG = ROOT / "configs/appsettingsv3.yaml"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._")
    return value or "evaluation"


def _step_files(root: Path) -> list[Path]:
    if not root.is_dir():
        raise FileNotFoundError(f"Evaluation input directory not found: {root}")
    files = sorted((p.resolve() for p in root.iterdir()
                    if p.is_file() and p.suffix.lower() in {".step", ".stp"}),
                   key=lambda p: p.name.lower())
    if not files:
        raise FileNotFoundError(f"No STEP/STP files found in {root}")
    return files


def _event(prefix: str):
    def emit(event: dict[str, Any]) -> None:
        kind, stage = event.get("type"), event.get("stage", "")
        if kind == "stage_started":
            print(f"[{prefix}] {stage} started", flush=True)
        elif kind == "stage_progress":
            total = event.get("total")
            count = f"{event.get('completed')}/{total}" if total is not None else event.get("completed")
            print(f"[{prefix}] {stage} {count} {event.get('item', '')}", flush=True)
        elif kind == "stage_completed":
            print(f"[{prefix}] {stage} {event.get('status')}", flush=True)
        elif kind == "stage_failed":
            print(f"[{prefix}] {stage} FAILED: {event.get('error')}", file=sys.stderr, flush=True)
    return emit


def _ground_truth_sequence(sequence_root: Path, assembly: str) -> Path:
    path = sequence_root / assembly / "sequence.json"
    if not path.is_file():
        raise FileNotFoundError(f"Ground-truth sequence not found: {path}")
    return path.resolve()


def _prepare_assets(*, step_file: Path, assembly: str, asset_root: Path,
                    sequence_root: Path, settings: dict[str, Any], context: str) -> Path:
    """Cache deterministic STEP artifacts and the authoritative GT visual bundle.

    Ground-truth sequences may contain logical subassembly identifiers which do
    not exist as physical BOM instances. Evaluation therefore deliberately does
    not validate the GT sequence against the newly parsed/enriched BOM.
    """
    workflow = AssemblyAssessmentWorkflow(session_root=asset_root, settings=settings,
        event_callback=_event(f"prepare/{assembly}"))
    workflow.preprocess(step_file=step_file)

    revision = asset_root / "sequence/revisions/r001"
    sequence_path = revision / "assembly_sequence.json"
    sequence_path.parent.mkdir(parents=True, exist_ok=True)
    if not sequence_path.exists():
        shutil.copy2(_ground_truth_sequence(sequence_root, assembly), sequence_path)
    renderings = revision / "renderings"
    summary = renderings / "rendering_summary.json"
    if not summary.exists():
        source_renderings = sequence_root / assembly / "renderings"
        source_summary = source_renderings / "rendering_summary.json"
        if not source_summary.is_file():
            raise FileNotFoundError(
                f"Ground-truth renderings are incomplete (rendering_summary.json missing): "
                f"{source_renderings}")
        if renderings.exists():
            shutil.rmtree(renderings)
        shutil.copytree(source_renderings, renderings)
        print(f"[prepare/{assembly}] installed ground-truth renderings (BOM validation skipped)",
              flush=True)
    return sequence_path


def _clone_assets(asset_root: Path, run_root: Path) -> Path:
    """Clone deterministic inputs only; every LLM artifact remains run-local."""
    for relative in ("input", "preprocessing"):
        source = asset_root / relative
        if not source.exists():
            raise FileNotFoundError(f"Prepared artifact is missing: {source}")
        shutil.copytree(source, run_root / relative)
    source_revision = asset_root / "sequence/revisions/r001"
    target_revision = run_root / "sequence/revisions/r001"
    target_revision.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_revision / "assembly_sequence.json", target_revision / "assembly_sequence.json")
    shutil.copytree(source_revision / "renderings", target_revision / "renderings")
    return target_revision / "assembly_sequence.json"


def _assessment_to_enum(source: Path, target: Path, assembly: str) -> None:
    raw = json.loads(source.read_text(encoding="utf-8"))
    steps = raw.get("steps") if isinstance(raw, dict) else None
    if not isinstance(steps, list):
        raise ValueError(f"Invalid product FFA assessment: {source}")
    mapping, _ = load_mapping()
    converted = []
    for item in steps:
        step, assessment = item.get("step") or {}, item.get("ffa_assessment") or {}
        enum_assessment: dict[str, dict[str, int]] = {}
        for field, definition in mapping["criteria"].items():
            subprocess = definition["subprocess"]
            value = (assessment.get(subprocess) or {}).get(field)
            option_id = value if type(value) is int else next(
                (key for key, label in definition["labels_by_id"].items() if label == value), None)
            if option_id is None:
                raise ValueError(f"{assembly} step {step.get('step_id')}: cannot map {subprocess}.{field}={value!r}")
            enum_assessment.setdefault(subprocess, {})[field] = option_id
        converted.append({"step_id": step.get("step_id"),
                          "step_description": step.get("step_description", ""),
                          "assessment": enum_assessment})
    _write_json(target, converted)


def _enum_steps(path: Path) -> dict[int, dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    values = raw if isinstance(raw, list) else raw.get("step_assessments", [])
    return {int(item["step_id"]): item.get("assessment", {}) for item in values}


def _score_enum_file(path: Path, mapping: dict[str, Any]) -> float | None:
    scores = []
    for assessment in _enum_steps(path).values():
        subprocess_scores = []
        for subprocess, subprocess_weight in mapping["subprocess_weights"].items():
            weighted = 0.0
            covered = 0.0
            for field, definition in mapping["criteria"].items():
                if definition["subprocess"] != subprocess:
                    continue
                option_id = (assessment.get(subprocess) or {}).get(field)
                score = definition["scores_by_id"].get(option_id)
                if score is not None:
                    weight = float(definition["criterion_weight"])
                    weighted += float(score) * weight
                    covered += weight
            if covered:
                subprocess_scores.append((weighted / covered, float(subprocess_weight)))
        total_weight = sum(weight for _, weight in subprocess_scores)
        if total_weight:
            scores.append(sum(value * weight for value, weight in subprocess_scores) / total_weight)
    return round(sum(scores) / len(scores), 4) if scores else None


def _classification_metrics(pairs: list[tuple[int, int]]) -> dict[str, Any]:
    labels = sorted({value for pair in pairs for value in pair})
    per_class = {}
    for label in labels:
        tp = sum(gt == label and pred == label for gt, pred in pairs)
        fp = sum(gt != label and pred == label for gt, pred in pairs)
        fn = sum(gt == label and pred != label for gt, pred in pairs)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[str(label)] = {"precision": precision, "recall": recall, "f1": f1,
                                 "support": sum(gt == label for gt, _ in pairs)}
    total = len(pairs)
    weighted_f1 = (sum(item["f1"] * item["support"] for item in per_class.values()) / total
                   if total else None)
    return {
        "samples": total,
        "accuracy": sum(gt == pred for gt, pred in pairs) / total if total else None,
        "macro_precision": sum(item["precision"] for item in per_class.values()) / len(per_class) if per_class else None,
        "macro_recall": sum(item["recall"] for item in per_class.values()) / len(per_class) if per_class else None,
        "macro_f1": sum(item["f1"] for item in per_class.values()) / len(per_class) if per_class else None,
        "weighted_f1": weighted_f1, "per_class": per_class,
    }


def _evaluate(run_root: Path, assemblies: list[str], repetitions: int, gt_root: Path) -> dict[str, Any]:
    enum_root = run_root / "evaluation/enum_predictions"
    mapping, provenance = load_mapping()
    rows = []
    pairs_by_field: dict[str, list[tuple[int, int]]] = {field: [] for field in mapping["criteria"]}
    missing_gt: list[str] = []
    errors: list[dict[str, str]] = []
    for assembly in assemblies:
        gt_file = gt_root / f"{assembly}_ffa_assessment_enum_gt.json"
        if not gt_file.is_file():
            missing_gt.append(assembly)
            continue
        for run_number in range(1, repetitions + 1):
            pred = run_root / "runs" / f"run_{run_number:02d}" / assembly / "ffa_assessment/r001/ffa_assessment.json"
            if not pred.is_file():
                errors.append({"assembly": assembly, "run": str(run_number), "error": "prediction missing"})
                continue
            enum_file = enum_root / f"run_{run_number:02d}" / f"{assembly}_ffa_assessment_enum.json"
            try:
                _assessment_to_enum(pred, enum_file, assembly)
                gt_steps, pred_steps = _enum_steps(gt_file), _enum_steps(enum_file)
                common = sorted(set(gt_steps) & set(pred_steps))
                criterion_count = 0
                for step_id in common:
                    for field, definition in mapping["criteria"].items():
                        subprocess = definition["subprocess"]
                        gt_value = (gt_steps[step_id].get(subprocess) or {}).get(field)
                        pred_value = (pred_steps[step_id].get(subprocess) or {}).get(field)
                        if type(gt_value) is int and type(pred_value) is int:
                            pairs_by_field[field].append((gt_value, pred_value))
                            criterion_count += 1
                gt_score = _score_enum_file(gt_file, mapping)
                pred_score = _score_enum_file(enum_file, mapping)
                rows.append({"assembly": assembly, "run": run_number,
                    "gt_total_ffa": gt_score, "pred_total_ffa": pred_score,
                    "abs_error": round(abs(gt_score - pred_score), 4)
                    if gt_score is not None and pred_score is not None else None,
                    "n_steps": len(common), "n_criteria": criterion_count})
            except Exception as exc:
                errors.append({"assembly": assembly, "run": str(run_number), "error": str(exc)})
    field_metrics = {field: _classification_metrics(pairs)
                     for field, pairs in pairs_by_field.items() if pairs}
    macro_values = [value["macro_f1"] for value in field_metrics.values()
                    if value["macro_f1"] is not None]
    precision_values = [value["macro_precision"] for value in field_metrics.values()
                        if value["macro_precision"] is not None]
    recall_values = [value["macro_recall"] for value in field_metrics.values()
                     if value["macro_recall"] is not None]
    errors_ffa = [row["abs_error"] for row in rows if row.get("abs_error") is not None]
    metrics = {"mapping": provenance, "fields": field_metrics, "summary": {
        "system_macro_f1": sum(macro_values) / len(macro_values) if macro_values else None,
        "system_macro_precision": sum(precision_values) / len(precision_values) if precision_values else None,
        "system_macro_recall": sum(recall_values) / len(recall_values) if recall_values else None,
        "total_ffa_mae": sum(errors_ffa) / len(errors_ffa) if errors_ffa else None,
        "evaluated_runs": len(rows), "evaluated_assemblies": len({row["assembly"] for row in rows}),
        "criterion_predictions": sum(len(value) for value in pairs_by_field.values()),
    }}
    evaluation = run_root / "evaluation"
    _write_json(evaluation / "metrics.json", metrics)
    _write_json(evaluation / "evaluation_status.json", {
        "evaluated_assemblies": sorted({row["assembly"] for row in rows}),
        "missing_ffa_ground_truth": missing_gt, "errors": errors})
    with (evaluation / "ffa_by_assembly_and_run.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = ["assembly", "run", "gt_total_ffa", "pred_total_ffa", "abs_error", "n_steps", "n_criteria"]
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    _plot_ffa_comparison(rows, evaluation / "ground_truth_ffa_vs_runs.png")
    return {"metrics": metrics, "rows": len(rows), "missing_gt": missing_gt, "errors": errors}


def _plot_ffa_comparison(rows: list[dict[str, Any]], output: Path) -> None:
    if not rows:
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    assemblies = sorted({row["assembly"] for row in rows})
    runs = sorted({int(row["run"]) for row in rows})
    x = np.arange(len(assemblies), dtype=float)
    width = min(0.14, 0.72 / max(len(runs), 1))
    fig, ax = plt.subplots(figsize=(max(10, len(assemblies) * 2.0), 6))
    gt = [next(row["gt_total_ffa"] for row in rows if row["assembly"] == assembly) for assembly in assemblies]
    ax.plot(x, gt, color="black", marker="D", linewidth=2.2, label="Ground truth", zorder=4)
    for index, run_number in enumerate(runs):
        by_assembly = {row["assembly"]: row["pred_total_ffa"] for row in rows if int(row["run"]) == run_number}
        values = [by_assembly.get(assembly, np.nan) for assembly in assemblies]
        offset = (index - (len(runs) - 1) / 2) * width
        ax.bar(x + offset, values, width=width, alpha=0.82, label=f"Run {run_number}")
    ax.set(title="Ground-truth FFA score compared with workflow runs", ylabel="Total FFA score")
    ax.set_xticks(x, assemblies, rotation=30, ha="right")
    ax.set_ylim(0, 1.05)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(ncols=min(5, len(runs) + 1))
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def run_evaluation(args: argparse.Namespace) -> int:
    load_project_environment(ROOT)
    settings = load_settings(args.config.resolve(strict=True))
    step_files = _step_files(args.input_dir.resolve())
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    name = args.name.strip() if args.name is not None else input("Evaluation name: ").strip()
    description = args.description if args.description is not None else input("Evaluation description: ").strip()
    run_root = args.output_root.resolve() / f"{timestamp}_{_safe_name(name)}"
    run_root.mkdir(parents=True, exist_ok=False)
    metadata: dict[str, Any] = {
        "name": name or "evaluation", "description": description,
        "created_at": datetime.now().astimezone().isoformat(), "mode": "direct_workflow",
        "repetitions": args.repetitions, "config": str(args.config.resolve()),
        "input_dir": str(args.input_dir.resolve()), "status": "running",
        "assemblies": [path.stem for path in step_files], "failures": []}
    _write_json(run_root / "run_metadata.json", metadata)
    print(f"\nEvaluation: {run_root}")

    prepared: dict[str, Path] = {}
    for step_file in step_files:
        assembly = step_file.stem
        try:
            asset_root = run_root / "prepared" / assembly
            _prepare_assets(step_file=step_file, assembly=assembly, asset_root=asset_root,
                            sequence_root=args.sequence_root.resolve(), settings=settings, context=args.context)
            prepared[assembly] = asset_root
        except Exception as exc:
            metadata["failures"].append({"phase": "prepare", "assembly": assembly,
                                          "error": f"{type(exc).__name__}: {exc}"})
            traceback.print_exc()
        _write_json(run_root / "run_metadata.json", metadata)

    for run_number in range(1, args.repetitions + 1):
        for assembly, asset_root in prepared.items():
            session = run_root / "runs" / f"run_{run_number:02d}" / assembly
            try:
                sequence = _clone_assets(asset_root, session)
                workflow = AssemblyAssessmentWorkflow(session_root=session, settings=settings,
                    event_callback=_event(f"run{run_number}/{assembly}"))
                # These stochastic stages intentionally run inside every repetition.
                # Their outputs become the context/BOM for this run's downstream nodes.
                workflow.analyze_assembly(user_context=args.context)
                workflow.analyze_monoparts(user_context=args.context)
                print(f"[run{run_number}/{assembly}] fixed ground-truth sequence selected",
                      flush=True)
                workflow.complete_from_sequence(revision_id="r001", approved_sequence=sequence,
                                                user_context=args.context)
            except Exception as exc:
                metadata["failures"].append({"phase": "workflow", "run": run_number,
                                              "assembly": assembly,
                                              "error": f"{type(exc).__name__}: {exc}"})
                traceback.print_exc()
            _write_json(run_root / "run_metadata.json", metadata)
    metadata["status"] = "complete" if not metadata["failures"] else "complete_with_errors"
    metadata["completed_at"] = datetime.now().astimezone().isoformat()
    _write_json(run_root / "run_metadata.json", metadata)
    print(f"\nFinished with status: {metadata['status']}\nResults: {run_root}")
    print(f'Generate metrics separately with: python eval_metrics.py "{run_root}"')
    return 0 if metadata["status"] == "complete" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", help="Run name; prompted when omitted")
    parser.add_argument("--description", help="Run description; prompted when omitted")
    parser.add_argument("-n", "--repetitions", type=int, default=3)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--sequence-root", type=Path, default=DEFAULT_SEQUENCES)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--context", default="", help="Extra context passed to all LLM nodes")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.repetitions < 1:
        raise SystemExit("--repetitions must be at least 1")
    return run_evaluation(args)


if __name__ == "__main__":
    raise SystemExit(main())
