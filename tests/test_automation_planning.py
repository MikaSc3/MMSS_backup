import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assembly_automation.workflows.definitions.automation_planning import (
    AutomationPlanningNodeRegistry,
    AutomationPlanningWorkflow,
    default_node_registry,
)
from assembly_automation.workflows.definitions.app_v3 import WorkflowPaths
from assembly_automation.workflows.runtime.prompting import _select_json
from assembly_automation.workflows.nodes.automation_concept_synthesis import structured_output as concept_output
from assembly_automation.workflows.nodes.automation_idea.structured_output import (
    AutomationPlanningBrief,
)
from assembly_automation.workflows.nodes.step_planner_detailed.structured_output import DetailedStepPlan
from assembly_automation.workflows.nodes.step_planner_detailed.structured_output import (
    AutomationPlannerEquipment, AutomationPlannerSubprozesse)
from assembly_automation.workflows.nodes.layout_planner.node import run_layout_planner
from assembly_automation.workflows.nodes.layout_planner.renderer import render_layout
from assembly_automation.workflows.nodes.layout_planner.structured_output import EquipmentLayout, get_schema as get_layout_schema
from assembly_automation.workflows.nodes.cost_planner.node import run_cost_planner


class CliTests(unittest.TestCase):
    def test_cli_accepts_reviewed_idea_instead_of_regenerating_it(self):
        from run_automation_concept_planning import parser
        args = parser().parse_args(["--session-root", "session", "--idea-path", "idea.json"])
        self.assertIsNone(args.instruction)
        self.assertEqual(args.idea_path, Path("idea.json"))


def _write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class AutomationPlanningTests(unittest.TestCase):
    def test_default_registry_embeds_layout_planner(self):
        registry = default_node_registry()
        self.assertTrue(callable(registry.layout_planner))

    def test_cost_planner_joins_catalogue_prices_and_calculates_total_deterministically(self):
        class CostModel:
            def with_structured_output(self, schema, include_raw=True):
                self.schema = schema
                return self
            def invoke(self, messages):
                parsed = self.schema.model_validate({"matches": [
                    {"equipment_name": "Assembly robot", "catalogue_id": "R-01",
                     "quantity": 2, "match_confidence": "high",
                     "matching_reasoning": "Matching robot class and function."}]})
                return {"parsed": parsed, "raw": SimpleNamespace(usage_metadata={
                    "input_tokens": 10, "output_tokens": 5, "total_tokens": 15})}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalogue = root / "prices.csv"
            catalogue.write_text(
                "catalogue_id,equipment_class,manufacturer,model,description,unit_price,currency,price_date,source,notes\n"
                "R-01,robot,ExampleCo,R6,6-axis robot,12500.00,EUR,2026-09-01,quote-17,Base unit\n",
                encoding="utf-8")
            concept = root / "concept.json"; _write(concept, {})
            layout = root / "layout.json"; _write(layout, {"equipment": [
                {"name": "Assembly robot", "class": "robot", "x": 0, "y": 0}]})
            output = root / "cost_estimate.json"
            response = run_cost_planner(
                artifacts={"automation_concept": concept, "layout": layout},
                settings={"enabled": True, "catalogue_path": str(catalogue),
                          "llm": {"profile": "test"},
                          "prompts": {"system": "system_v1", "human": "human_v1"},
                          "structured_output": "cost_planner_matches_v1", "tools": [],
                          "execution": {"max_tool_rounds": 1},
                          "inputs": {
                              "automation_concept": {"enabled": True, "required": True, "kind": "json", "source": "automation_concept"},
                              "layout": {"enabled": True, "required": True, "kind": "json", "source": "layout"},
                              "price_catalogue": {"enabled": True, "required": True, "kind": "text", "source": "price_catalogue_csv"},
                              "cost_context": {"enabled": True, "kind": "text", "source": "cost_context"}}},
                llm_profiles={"test": {}}, context={"cost_context": "Use base units"},
                output_path=output, llm=CostModel())

        self.assertEqual(response["result"]["priced_subtotal"], 25000.0)
        self.assertTrue(response["result"]["is_complete"])
        self.assertEqual(response["result"]["line_items"][0]["unit_price"], 12500.0)

    def test_layout_schema_and_deterministic_rectangle_renderer(self):
        layout = EquipmentLayout.model_validate({"equipment": [
            {"name": "Assembly robot", "class": "robot", "x": 0, "y": 0, "size": 180},
            {"name": "Operator HMI", "class": "hmi", "x": 140, "y": 0, "size": 45},
        ]}).model_dump()
        self.assertEqual(layout["equipment"][0]["class"], "robot")
        self.assertEqual(layout["equipment"][0]["size"], 180.0)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "layout.svg"
            render_layout(layout, target)
            svg = target.read_text(encoding="utf-8")
        self.assertIn("Assembly robot", svg)
        self.assertIn("Operator HMI", svg)
        self.assertIn('width="180.0" height="180.0"', svg)
        self.assertIn('width="45.0" height="45.0"', svg)
        self.assertEqual(svg.count("<rect "), 3)  # background plus two equipment rectangles

    def test_layout_node_consumes_synthesized_equipment_and_renders_svg(self):
        class LayoutModel:
            def with_structured_output(self, schema, include_raw=True):
                self.schema = schema
                return self

            def invoke(self, messages):
                parsed = self.schema.model_validate({"equipment": [
                    {"name": "Assembly robot", "class": "robot", "x": 0, "y": 0,
                     "size": 180},
                    {"name": "Indexing fixture", "class": "fixture", "x": 0,
                     "y": 0, "size": 100},
                ]})
                return {"parsed": parsed, "raw": SimpleNamespace(usage_metadata={
                    "input_tokens": 10, "output_tokens": 5, "total_tokens": 15})}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            concept = root / "concept.json"
            _write(concept, {"equipment": [
                {"name": "Assembly robot", "step_ids": [1], "specimen": []},
                {"name": "Indexing fixture", "step_ids": [1, 2], "specimen": []},
            ], "conflicts": []})
            output = root / "layout.json"
            response = run_layout_planner(
                artifacts={"automation_concept": concept},
                settings={"enabled": True, "llm": {"profile": "test"},
                          "prompts": {"system": "system_v1", "human": "human_v1"},
                          "structured_output": "layout_planner_v1", "tools": [],
                          "execution": {"max_tool_rounds": 1},
                          "inputs": {
                              "automation_concept": {"enabled": True, "required": True,
                                                     "kind": "json", "source": "automation_concept"},
                              "layout_context": {"enabled": True, "kind": "text",
                                                 "source": "layout_context"}}},
                llm_profiles={"test": {}}, context={"layout_context": "Compact cell"},
                output_path=output, llm=LayoutModel())

            self.assertTrue(output.is_file())
            self.assertTrue(Path(response["rendering"]).is_file())
            svg = Path(response["rendering"]).read_text(encoding="utf-8")
            self.assertIn("Assembly robot", svg)
            self.assertIn("Indexing fixture", svg)

    def test_minor_layout_revision_changes_coordinates_and_rerenders_without_llm(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = object.__new__(AutomationPlanningWorkflow)
            workflow.output_root = root
            workflow.planning_root = root / "08_planning"
            workflow.paths = WorkflowPaths(root)
            workflow.manifest_path = workflow.planning_root / "planning_manifest.json"
            concept = root / "concept.json"
            layout = root / "layout.json"
            _write(concept, {"equipment": [
                {"name": "Assembly robot", "step_ids": [1], "specimen": []},
                {"name": "Indexing fixture", "step_ids": [1], "specimen": []}],
                "conflicts": []})
            _write(layout, {"equipment": [
                {"name": "Assembly robot", "class": "robot", "x": 0, "y": 0},
                {"name": "Indexing fixture", "class": "fixture", "x": 100, "y": 0}]})
            _write(workflow.manifest_path, {"status": "awaiting_layout_review",
                                           "artifacts": {"automation_concept": "concept.json",
                                                         "layout": "layout.json"}})

            response = workflow.revise_layout(
                layout_path=layout, concept_path=concept,
                changes=[{"name": "Assembly robot", "x": -40, "y": 25, "size": 210}],
                revision_id="layout_r002")

            revised = json.loads(Path(response["artifact"]).read_text(encoding="utf-8"))
            self.assertEqual(revised["equipment"][0]["x"], -40)
            self.assertEqual(revised["equipment"][0]["y"], 25)
            self.assertEqual(revised["equipment"][0]["size"], 210.0)
            self.assertTrue(Path(response["rendering"]).is_file())

    def test_automation_idea_fields_have_descriptions(self):
        for model in (AutomationPlanningBrief, DetailedStepPlan,
                      AutomationPlannerSubprozesse,
                      concept_output.AutomationEquipmentList, EquipmentLayout):
            self.assertTrue(all(field.description for field in model.model_fields.values()), model.__name__)

    def test_detailed_equipment_uses_station_style_fields(self):
        self.assertEqual(
            list(AutomationPlannerEquipment.model_fields),
            ["name", "function", "step_id", "specimen"],
        )

    def test_active_concept_and_layout_schema_registries_match_configuration(self):
        self.assertIs(
            concept_output.get_schema("automation_equipment_list_v1"),
            concept_output.AutomationEquipmentList,
        )
        self.assertIs(
            get_layout_schema("layout_planner_v1"),
            EquipmentLayout,
        )

    def test_typed_selector_supports_nested_step_ids(self):
        value = {"steps": [{"step": {"step_id": 1}}, {"step": {"step_id": 2}}]}
        selected = _select_json(value, {
            "select": {"path": "steps", "field": "step.step_id", "equals": "{step_id}"}
        }, {"step_id": 2})
        self.assertEqual(selected["step"]["step_id"], 2)

    def test_existing_session_artifacts_fan_out_then_consolidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "session"
            artifacts = {
                "assembly_overview": "assembly.json", "enriched_bom": "bom.json",
                "assembly_sequence": "sequence.json", "interaction_analysis": "interaction.json",
                "ffa_assessment": "ffa.json", "ffa_scores": "scores.json", "report": "report.json",
            }
            for key, relative in artifacts.items():
                value = {"steps": [{"step_id": 1}, {"step_id": 2}]} if key == "assembly_sequence" else {}
                _write(root / relative, value)
            _write(root / "manifest.json", {"workflow": "assembly_assessment", "artifacts": artifacts})

            calls = []
            def idea(**kwargs):
                result = {"objective": "Automate consistently"}
                _write(Path(kwargs["output_path"]), result)
                return {"status": "complete", "result": result, "artifact": str(kwargs["output_path"])}
            def step(**kwargs):
                calls.append(kwargs["step_id"])
                result = {"step_id": kwargs["step_id"]}
                _write(Path(kwargs["output_path"]), result)
                return {"status": "complete", "result": result, "artifact": str(kwargs["output_path"])}
            def concept(**kwargs):
                aggregate = json.loads(Path(kwargs["artifacts"]["detailed_step_plans"]).read_text())
                result = {"planned_steps": [item["step_id"] for item in aggregate["steps"]]}
                _write(Path(kwargs["output_path"]), result)
                return {"status": "complete", "result": result, "artifact": str(kwargs["output_path"])}

            settings = {"llms": {"profiles": {"test": {}}}, "nodes": {
                "automation_idea": {}, "step_planner_detailed": {"fanout": {"parallel": True, "max_workers": 2}},
                "automation_concept_synthesis": {},
            }}
            workflow = AutomationPlanningWorkflow(
                session_root=root, settings=settings,
                nodes=AutomationPlanningNodeRegistry(idea, step, concept))
            response = workflow.run("Automate step 1")

            self.assertEqual(response["result"]["planned_steps"], [1, 2])
            self.assertEqual(sorted(calls), [1, 2])
            planning_manifest = json.loads((root / "08_planning/planning_manifest.json").read_text())
            self.assertEqual(planning_manifest["status"], "awaiting_concept_review")


if __name__ == "__main__":
    unittest.main()
