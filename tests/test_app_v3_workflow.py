import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assembly_automation.workflows.definitions import AssemblyAssessmentWorkflow, NodeRegistry
from assembly_automation.workflows.nodes.bom_merge import run_bom_merge


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def registry(calls):
    def preprocessing(step_file, output_dir, settings, progress=None):
        calls.append("step_preprocessing"); root = Path(output_dir); root.mkdir(parents=True)
        write(root / "assembly.json", {"name": "Fixture", "total_parts": 2, "unique_parts": 2})
        write(root / "bom.json", {"parts": [{"part_id": "part_001"}, {"part_id": "part_002"}],
            "instances": [{"instance_id": "part_001", "part_id": "part_001"},
                          {"instance_id": "part_002", "part_id": "part_002"}]})
        write(root / "spatial_relations.json", {"pairs": []}); write(root / "interlocking.json", {"parts": []})
        for name in ("assembly/collage_assembly.png", "parts/part_001/collage_part_001.png",
                     "parts/part_002/collage_part_002.png"):
            path = root / "images" / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b"png")
        write(root / "manifest.json", {"status": "complete"})
        return {"status": "complete"}

    def assembly_analysis(**kwargs):
        calls.append("assembly_analysis"); value = {"assembly_name_guess": "Fixture",
            "assembly_description": "Fixture", "primary_function": ["Locate parts"], "partslist": ["Two parts"]}
        write(kwargs["output_path"], value); return {"status": "complete", "result": value}

    def monopart_analysis(**kwargs):
        part_id = kwargs["part_id"]; calls.append(f"monopart:{part_id}")
        value = {"part_identification": "Fixture component", "part_name_guess": part_id,
                 "part_color": "blue", "intrinsic_summary": ["Rigid part."]}
        write(kwargs["output_path"], value); return {"status": "complete", "result": value}

    def sequence_generation(**kwargs):
        calls.append("sequence_generation")
        value = {"assembly_name": "Fixture", "steps": [
            {"step_id": 1, "step_description": "Place base", "belongs_to": "Main",
             "base_part": None, "joining_part": "part_001", "joining_process": "Place"},
            {"step_id": 2, "step_description": "Insert pin", "belongs_to": "Main",
             "base_part": "part_001", "joining_part": "part_002", "joining_process": "Insert"}]}
        write(kwargs["output_path"], value); return {"status": "complete", "result": value}

    def sequence_rendering(**kwargs):
        calls.append("sequence_rendering"); root = Path(kwargs["output_dir"]); root.mkdir(parents=True)
        for step_id in (1, 2): (root / f"collage_step_{step_id:02d}.png").write_bytes(b"png")
        write(root / "rendering_summary.json", {"status": "complete"})
        return {"status": "complete"}

    def interaction_analysis(**kwargs):
        step_id = kwargs["step_id"]; calls.append(f"interaction:{step_id}")
        value = {"step": {"step_id": step_id}, "interaction_analysis": {"summary": "Contact"}}
        write(kwargs["output_path"], value); return {"status": "complete", "result": value}

    def ffa_assessment(**kwargs):
        step_id = kwargs["step_id"]; calls.append(f"ffa:{step_id}")
        value = {"step": {"step_id": step_id, "step_description": f"Step {step_id}"},
                 "ffa_assessment": {"overall_ffa": [], "additional_information_required": []}}
        write(kwargs["output_path"], value); return {"status": "complete", "result": value}

    def ffa_scoring(**kwargs):
        calls.append("ffa_scoring")
        value = {"mapping": {"id": "ffa_scoring_v1"}, "steps": [
            {"step_id": step_id, "subprocess_scores": {}, "total_ffa": 0.5} for step_id in (1, 2)],
            "aggregate": {"mean_total_ffa": 0.5}}
        write(kwargs["output_path"], value); return {"status": "complete", "result": value}

    def report_synthesis(**kwargs):
        calls.append("report_synthesis"); value = {"assembly_overview": {"assembly_name": "Fixture"},
            "executive_summary": [], "scorecard": {}, "key_findings": [], "recommendations": [],
            "steps": [], "parts": [], "assumptions_and_unknowns": [], "provenance": {}}
        write(kwargs["output_path"], value); return {"status": "complete", "result": value}

    def report_rendering(**kwargs):
        calls.append("report_rendering"); root = Path(kwargs["output_dir"]); root.mkdir(parents=True)
        html = root / "Fixture_ffa_executive.html"; html.write_text("<html></html>", encoding="utf-8")
        manifest = root / "rendering_manifest.json"; write(manifest, {"status": "complete"})
        return {"status": "complete", "manifest": str(manifest)}

    return NodeRegistry(preprocessing, assembly_analysis, monopart_analysis, run_bom_merge,
                        sequence_generation, sequence_rendering, interaction_analysis,
                        ffa_assessment, ffa_scoring, report_synthesis, report_rendering)


class AppV3WorkflowTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.settings = yaml.safe_load((root / "configs/appsettingsv3.yaml").read_text(encoding="utf-8"))

    def test_stops_at_sequence_approval_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / "fixture.STEP"; source.write_text("STEP", encoding="utf-8")
            calls = []
            result = AssemblyAssessmentWorkflow(session_root=root / "session", settings=self.settings,
                nodes=registry(calls)).run(step_file=source)
            manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "awaiting_sequence_approval")
        self.assertEqual(manifest["active_sequence_revision"], "r001")
        self.assertNotIn("sequence_rendering", calls)

    def test_public_phases_stop_at_assembly_and_bom_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / "fixture.STEP"; source.write_text("STEP", encoding="utf-8")
            calls = []
            workflow = AssemblyAssessmentWorkflow(session_root=root / "session", settings=self.settings,
                nodes=registry(calls))
            workflow.preprocess(step_file=source)
            assembly = workflow.analyze_assembly(user_context="Known fixture")
            self.assertEqual(assembly["status"], "awaiting_assembly_review")
            self.assertNotIn("monopart:part_001", calls)
            bom = workflow.analyze_monoparts(user_context="Known fixture")
            self.assertEqual(bom["status"], "awaiting_bom_review")
            self.assertNotIn("sequence_generation", calls)

    def test_review_reruns_archive_outputs_and_only_repeat_selected_parts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / "fixture.STEP"; source.write_text("STEP", encoding="utf-8")
            calls = []
            workflow = AssemblyAssessmentWorkflow(session_root=root / "session", settings=self.settings,
                nodes=registry(calls))
            workflow.preprocess(step_file=source)
            workflow.analyze_assembly()
            rerun = workflow.analyze_assembly(user_context="Corrected function", force=True)
            self.assertEqual(rerun["revision_id"], "r002")
            self.assertTrue(Path(rerun["assembly_overview"]).is_file())
            workflow.analyze_monoparts()
            before_part_1 = calls.count("monopart:part_001")
            before_part_2 = calls.count("monopart:part_002")
            rerun_parts = workflow.analyze_monoparts(
                user_context="part_001 is steel", part_ids=["part_001"], force=True)
            self.assertEqual(calls.count("monopart:part_001"), before_part_1 + 1)
            self.assertEqual(calls.count("monopart:part_002"), before_part_2)
            self.assertTrue(rerun_parts["archived"])

    def test_runs_end_to_end_and_publishes_relative_manifest_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / "fixture.stp"; source.write_text("STEP", encoding="utf-8")
            calls, events = [], []
            workflow = AssemblyAssessmentWorkflow(session_root=root / "session", settings=self.settings,
                nodes=registry(calls), event_callback=events.append)
            result = workflow.run(step_file=source, approve_sequence=True)
            manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
            session = Path(result["session_root"])
            interaction_partial = session / "sequence/revisions/r001/interaction_analysis/interaction_analysis.partial.json"
            ffa_partial = session / "ffa_assessment/r001/ffa_assessment.partial.json"
            self.assertFalse(interaction_partial.exists())
            self.assertFalse(ffa_partial.exists())
            self.assertTrue(Path(result["report"]).exists())
            interaction_final = session / "05_sequence/revisions/r001/interaction_analysis/interaction_analysis.json"
            interaction_final.unlink()
            interaction_calls = len([item for item in calls if item.startswith("interaction:")])
            workflow.complete_from_sequence(revision_id="r001", approved_sequence=result["sequence"])
            self.assertEqual(len([item for item in calls if item.startswith("interaction:")]),
                             interaction_calls)
            self.assertTrue(interaction_final.exists())
        self.assertEqual(result["status"], "complete")
        self.assertEqual(manifest["status"], "complete")
        self.assertTrue(all(not Path(path).is_absolute() for path in manifest["artifacts"].values()))
        self.assertEqual(calls.count("report_synthesis"), 1)
        self.assertEqual(len([item for item in calls if item.startswith("interaction:")]), 2)
        self.assertEqual(len([item for item in calls if item.startswith("ffa:")]), 2)
        self.assertEqual(events[-1]["type"], "workflow_completed")


if __name__ == "__main__":
    unittest.main()
