import json
from pathlib import Path

import eval_system
import eval_metrics


def test_safe_name():
    assert eval_system._safe_name(" prompt test / v2 ") == "prompt_test_v2"
    assert eval_system._safe_name("***") == "evaluation"


def test_assessment_to_enum(tmp_path: Path):
    mapping, _ = eval_system.load_mapping()
    assessment = {name: {} for name in mapping["subprocess_weights"]}
    expected = {}
    for field, definition in mapping["criteria"].items():
        subprocess = definition["subprocess"]
        option_id = min(definition["labels_by_id"])
        assessment[subprocess][field] = definition["labels_by_id"][option_id]
        expected.setdefault(subprocess, {})[field] = option_id
    source, target = tmp_path / "ffa.json", tmp_path / "enum.json"
    source.write_text(json.dumps({"steps": [{"step": {"step_id": 1, "step_description": "Place"},
        "ffa_assessment": assessment}]}), encoding="utf-8")
    eval_system._assessment_to_enum(source, target, "demo")
    converted = json.loads(target.read_text(encoding="utf-8"))
    assert converted == [{"step_id": 1, "step_description": "Place", "assessment": expected}]


def test_metrics_metadata_validation(tmp_path: Path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "run_metadata.json").write_text(json.dumps({
        "assemblies": ["demo"], "repetitions": 4,
    }), encoding="utf-8")
    resolved, metadata = eval_metrics._metadata(run)
    assert resolved == run.resolve()
    assert metadata["assemblies"] == ["demo"]


def test_clone_assets_does_not_share_stochastic_context(tmp_path: Path):
    prepared = tmp_path / "prepared"
    run = tmp_path / "run"
    for relative in ("input", "preprocessing", "assembly_analysis", "monopart_analysis"):
        folder = prepared / relative
        folder.mkdir(parents=True)
        (folder / "marker.json").write_text("{}", encoding="utf-8")
    revision = prepared / "sequence/revisions/r001"
    (revision / "renderings").mkdir(parents=True)
    (revision / "assembly_sequence.json").write_text("{}", encoding="utf-8")
    (revision / "renderings/rendering_summary.json").write_text("{}", encoding="utf-8")

    eval_system._clone_assets(prepared, run)

    assert (run / "input/marker.json").exists()
    assert (run / "preprocessing/marker.json").exists()
    assert not (run / "assembly_analysis").exists()
    assert not (run / "monopart_analysis").exists()
    assert (run / "sequence/revisions/r001/renderings/rendering_summary.json").exists()
