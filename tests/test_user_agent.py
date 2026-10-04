import json
from pathlib import Path
import sys
import tempfile
import unittest
import yaml
from pydantic import PrivateAttr

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assembly_automation.user_agent.agent import UserFacingAgent, generate_introduction
from assembly_automation.user_agent.artifacts import ArtifactEditor
from assembly_automation.user_agent.artifact_change import resolve_target
from assembly_automation.user_agent.feedback import FeedbackStore
from assembly_automation.user_agent.tools import WorkflowAgentTools
from assembly_automation.workflows.definitions.app_v3 import WorkflowPaths
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


OVERVIEW = {"assembly_description": "Fixture assembly",
            "partslist": ["Base and pin"], "assembly_name_guess": "Fixture",
            "primary_function": ["Locate a component"]}
BOM = {"parts": [{"part_id": "part_001", "name": "Base"}],
       "instances": [{"instance_id": "part_001", "part_id": "part_001"}]}
SEQUENCE = {"assembly_name": "Fixture", "assembly_description": "Fixture",
                          "sequence_rationale": "The base is placed first.",
                          "sequence_notation": "part_001", "steps": [
                              {"step_id": 1, "step_description": "Place base",
                               "belongs_to": "Main", "base_part": None,
                               "joining_part": "part_001", "joining_process": "Place"}]}
PART_ANALYSIS = {
    "part_identification": "Base component",
    "part_name_guess": "Base",
    "part_color": "blue",
    "material_and_mechanical_behavior": ["Rigid part."],
    "bulk_behavior": ["Stable in bulk."],
    "magazine_behavior": ["Stored upright in a tray."],
    "nature_of_provision_guess": ["Provided upright in a tray."],
    "geometric_characteristics": ["Rectangular body."],
    "gripping_analysis": ["Grip the side faces."],
    "handling_implications": ["Stable during transfer."],
    "intrinsic_summary": ["Rigid locating base."],
}


class FakeWorkflow:
    def __init__(self, root):
        self.paths = WorkflowPaths(Path(root))
        self.calls = []
        write(self.paths.root / "manifest.json",
              {"workflow": "assembly_assessment", "status": "created",
               "active_sequence_revision": None, "stages": {}, "artifacts": {}})

    def preprocess(self, *, step_file):
        self.calls.append(("preprocess", str(step_file)))
        write(self.paths.preprocessing / "assembly.json", {"name": "Fixture"})
        write(self.paths.preprocessing / "bom.json", BOM)
        write(self.paths.preprocessing / "spatial_relations.json", {})
        write(self.paths.preprocessing / "interlocking.json", {})
        (self.paths.preprocessing / "images").mkdir(parents=True, exist_ok=True)
        return {"status": "complete"}

    def analyze_assembly(self, *, user_context, force):
        self.calls.append(("assembly", user_context, force))
        write(self.paths.assembly("r001") / "assembly_overview.json", OVERVIEW)
        return {"status": "awaiting_assembly_review",
                "assembly_overview": str(self.paths.assembly_overview)}

    def analyze_monoparts(self, *, user_context, part_ids, force):
        self.calls.append(("monoparts", user_context, part_ids, force))
        write(self.paths.monoparts("r001") / "bom.json", BOM)
        return {"status": "awaiting_bom_review",
                "bom": str(self.paths.monoparts("r001") / "bom.json"),
                "revision_id": "r001"}

    def generate_sequence(self, *, revision_id, mode, initial_sequence=None,
                          user_context="", sequence_constraints="",
                          user_feedback_summary=""):
        self.calls.append(("sequence", revision_id, mode, user_feedback_summary))
        path = self.paths.revision(revision_id) / "assembly_sequence.json"
        write(path, SEQUENCE)
        manifest = json.loads((self.paths.root / "manifest.json").read_text())
        manifest.update({"status": "awaiting_sequence_approval",
                         "active_sequence_revision": revision_id})
        write(self.paths.root / "manifest.json", manifest)
        return {"status": "awaiting_sequence_approval", "revision_id": revision_id,
                "sequence": str(path)}

    def complete_from_sequence(self, *, revision_id, approved_sequence, user_context):
        self.calls.append(("final", revision_id, user_context))
        report = self.paths.reports(revision_id) / "report.json"
        write(report, {"assembly_overview": {"assembly_name": "Fixture"}})
        return {"status": "complete", "revision_id": revision_id, "report": str(report)}


class FakeAutomationPlanning:
    def create_idea(self, instruction, *, revision_id):
        return {"status": "awaiting_idea_review",
                "artifact": f"08_planning/01_ideas/{revision_id}/planning_brief.json"}


class FeedbackTests(unittest.TestCase):
    def test_context_is_scoped_and_targeted(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FeedbackStore(directory)
            store.append(scope="assembly", raw_user_message="It locates shafts",
                         agent_summary="Primary function is shaft location.")
            store.append(scope="part", targets=["part_002"], raw_user_message="This is steel",
                         agent_summary="part_002 is steel.", feedback_type="correction")
            assembly = store.compile_context(scopes=["global", "assembly"])
            part_1 = store.compile_context(scopes=["part"], targets=["part_001"])
            part_2 = store.compile_context(scopes=["part"], targets=["part_002"])
        self.assertIn("shaft location", assembly)
        self.assertEqual(part_1, "")
        self.assertIn("part_002 is steel", part_2)


class ArtifactEditorTests(unittest.TestCase):
    def test_edit_is_validated_and_backed_up(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = WorkflowPaths(Path(directory))
            write(paths.assembly_overview, OVERVIEW)
            editor = ArtifactEditor(directory)
            result = editor.edit("assembly_overview",
                                 {"primary_function": ["Support a shaft"]},
                                 reason="User correction")
            edited = json.loads(paths.assembly_overview.read_text())
            self.assertEqual(edited["primary_function"], ["Support a shaft"])
            self.assertTrue(Path(result["backup"]).is_file())
            with self.assertRaises(Exception):
                editor.edit("assembly_overview", {"primary_function": None},
                            reason="Invalid removal")

    def test_field_edits_use_hash_and_reject_read_only_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = WorkflowPaths(Path(directory))
            write(paths.assembly_overview, OVERVIEW)
            editor = ArtifactEditor(directory)
            original_hash = editor.content_hash(paths.assembly_overview)

            result = editor.edit_fields(
                "assembly_overview", entity_id="assembly",
                changes={"primary_function": ["Support and locate a shaft"]},
                expected_sha256=original_hash, reason="User correction")
            self.assertNotEqual(result["sha256"], original_hash)
            self.assertEqual(json.loads(paths.assembly_overview.read_text())["primary_function"],
                             ["Support and locate a shaft"])
            with self.assertRaisesRegex(RuntimeError, "changed after"):
                editor.edit_fields(
                    "assembly_overview", entity_id="assembly",
                    changes={"assembly_description": "Stale edit"},
                    expected_sha256=original_hash, reason="Stale browser draft")
            current_hash = editor.content_hash(paths.assembly_overview)
            with self.assertRaisesRegex(ValueError, "read-only or unknown"):
                editor.edit_fields(
                    "assembly_overview", entity_id="assembly",
                    changes={"schema_version": "2"}, expected_sha256=current_hash,
                    reason="Unsupported edit")


class WorkflowAgentToolTests(unittest.TestCase):
    def test_semantic_part_change_resolves_alias_and_skips_monopart_rerun(self):
        class Planner:
            def plan(self, resolved, change):
                self.resolved, self.change = resolved, change
                return {
                    "changes": {
                        "nature_of_provision_guess": ["Provided face down in a tray."],
                        "handling_implications": ["Approach the upward-facing rear surface before reorientation."],
                    },
                    "plan": {"edits": [], "summary": "Updated the provision orientation."},
                    "execution": {"llm_profile": "test", "token_usage": None,
                                  "elapsed_seconds": 0.01},
                    "input": {"user_change": change},
                }

        with tempfile.TemporaryDirectory() as directory:
            workflow = FakeWorkflow(Path(directory) / "session")
            bom = {"parts": [{"part_id": "part_001", "name": "Base", "quantity": 1,
                              "part_analysis": dict(PART_ANALYSIS)}],
                   "instances": [{"instance_id": "part_001", "part_id": "part_001"}]}
            write(workflow.paths.enriched_bom, bom)
            tools = WorkflowAgentTools(workflow=workflow)
            planner = Planner()
            tools.artifact_change_planner = planner
            tools.current_user_message = "The part is provisioned face down."

            result = tools.change_artifact("part001", "The part is provisioned face down.")
            updated = json.loads(workflow.paths.enriched_bom.read_text())
            state = json.loads(tools.state_path.read_text())

            self.assertEqual(planner.resolved.entity_id, "part_001")
            self.assertEqual(updated["parts"][0]["part_analysis"]["nature_of_provision_guess"],
                             ["Provided face down in a tray."])
            self.assertFalse(state["stale"]["monoparts"])
            self.assertTrue(state["stale"]["sequence"])
            self.assertTrue(Path(result["run_record_path"]).is_file())
            self.assertEqual(result["target"], "part part_001")

    def test_semantic_target_exposes_only_editable_part_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = FakeWorkflow(Path(directory) / "session")
            write(workflow.paths.enriched_bom, {
                "parts": [{"part_id": "part_001", "quantity": 1,
                           "geometry": {"volume": 20},
                           "part_analysis": dict(PART_ANALYSIS)}],
                "instances": [{"instance_id": "part_001", "part_id": "part_001"}],
            })
            resolved = resolve_target(ArtifactEditor(workflow.paths.root), "part:part001")
            self.assertIn("nature_of_provision_guess", resolved.editable_fields)
            self.assertNotIn("part_color", resolved.editable_fields)
            self.assertNotIn("quantity", resolved.editable_fields)
            self.assertNotIn("geometry", resolved.current)

    def test_part_context_tools_are_bounded_and_address_parts_by_id(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = FakeWorkflow(Path(directory) / "session")
            bom = {
                "parts": [
                    {"part_id": "part_001", "name": "Base", "quantity": 1,
                     "part_analysis": {"part_name_guess": "Housing",
                                       "intrinsic_summary": ["Rigid locating base."]}},
                    {"part_id": "part_002", "name": "Pin", "quantity": 2,
                     "part_analysis": {"part_name_guess": "Pin",
                                       "intrinsic_summary": ["Cylindrical joining part."]}},
                ],
                "instances": [],
            }
            write(workflow.paths.enriched_bom, bom)
            tools = WorkflowAgentTools(workflow=workflow)

            summary = tools.summarize_parts(page=1, page_size=1)
            selected = tools.summarize_parts(part_ids=["part_002"])
            detail = tools.read_part("part_001")

            self.assertEqual(summary["total"], 2)
            self.assertTrue(summary["has_more"])
            self.assertEqual(summary["parts"][0]["part_id"], "part_001")
            self.assertEqual(selected["parts"][0]["intrinsic_summary"],
                             ["Cylindrical joining part."])
            self.assertEqual(detail["part"]["part_id"], "part_001")
            with self.assertRaisesRegex(ValueError, "Unknown part IDs"):
                tools.summarize_parts(part_ids=["part_999"])

    def test_read_artifact_returns_hash_required_for_field_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = FakeWorkflow(Path(directory) / "session")
            write(workflow.paths.assembly_overview, OVERVIEW)
            tools = WorkflowAgentTools(workflow=workflow)
            result = tools.read_artifact("assembly_context")
            self.assertEqual(result["sha256"],
                             tools.artifacts.content_hash(workflow.paths.assembly_overview))

    def test_read_artifact_uses_fixed_requests_and_internal_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = FakeWorkflow(Path(directory) / "session")
            write(workflow.paths.assembly_overview, OVERVIEW)
            write(workflow.paths.enriched_bom, BOM)
            tools = WorkflowAgentTools(workflow=workflow)

            assembly = tools.read_artifact("assembly_context")
            bom = tools.read_artifact("BOM")
            part = tools.read_artifact("part", "part_001")

            self.assertEqual(assembly["data"], OVERVIEW)
            self.assertEqual(bom["data"], BOM)
            self.assertEqual(part["data"], BOM["parts"][0])
            with self.assertRaisesRegex(ValueError, "Unknown artifact request"):
                tools.read_artifact("assembly_overview", "function")
            with self.assertRaisesRegex(ValueError, "Unknown part ID"):
                tools.read_artifact("part", "circlip")

    def test_read_artifact_selects_versioned_entities(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = FakeWorkflow(Path(directory) / "session")
            write(workflow.paths.root / "manifest.json", {
                "workflow": "assembly_assessment", "status": "created",
                "active_sequence_revision": "r002",
            })
            write(workflow.paths.root / "user_agent/state.json", {
                "active_sequence_revision": "r002",
                "stale": {"assembly": False, "monoparts": False, "sequence": False,
                          "renderings": False, "final": False},
            })
            write(workflow.paths.revision("r002") / "assembly_sequence.json", {
                "steps": [{"step_id": 3, "step_description": "Install circlip"}],
            })
            planning_root = workflow.paths.planning_root
            write(planning_root / "planning_manifest.json", {
                "active_concept_revision": "concept_r002",
                "active_layout_revision": "layout_r001",
                "artifacts": {},
            })
            write(planning_root / "05_detailed_plans/concept_r002/detailed_step_plans.json", {
                "steps": [{"step_id": 3, "plan": "Feed circlip from bulk hopper"}],
            })
            write(planning_root / "03_layouts/layout_r001/layout.json", {
                "equipment": [{"name": "Circlip feeder", "function": "Orient circlips"}],
            })
            tools = WorkflowAgentTools(workflow=workflow)

            sequence_step = tools.read_artifact("sequence_step", "r002:step_003")
            detailed_plan = tools.read_artifact("detailed_plan", "concept_r002:step_003")
            layout_item = tools.read_artifact("layout_item", "layout_r001:Circlip feeder")

            self.assertEqual(sequence_step["data"]["step_id"], 3)
            self.assertEqual(detailed_plan["data"]["step_id"], 3)
            self.assertEqual(layout_item["data"]["name"], "Circlip feeder")
            with self.assertRaisesRegex(ValueError, "Unknown sequence step"):
                tools.read_artifact("sequence_step", "r002:step_004")

    def test_inspect_session_lists_available_part_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = FakeWorkflow(Path(directory) / "session")
            write(workflow.paths.enriched_bom, {
                "parts": [
                    {"part_id": "part_001", "name": "Pillow block", "quantity": 1},
                    {"part_id": "part_003", "name": "Circlip", "quantity": 2},
                ],
                "instances": [],
            })
            tools = WorkflowAgentTools(workflow=workflow)

            result = tools.inspect_session()

            self.assertEqual(result["available_parts"], [
                {"part_id": "part_001", "name": "Pillow block", "quantity": 1},
                {"part_id": "part_003", "name": "Circlip", "quantity": 2},
            ])

    def test_inspect_session_lists_active_and_historical_revisions(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = FakeWorkflow(Path(directory) / "session")
            sequence_root = workflow.paths.sequence_root / "revisions"
            for revision_id in ("r001", "r002"):
                write(sequence_root / revision_id / "assembly_sequence.json", SEQUENCE)
            planning_root = workflow.paths.planning_root
            write(planning_root / "planning_manifest.json", {
                "active_idea_revision": "idea_r001",
                "active_concept_revision": "concept_r002",
                "active_layout_revision": "layout_r001",
                "active_cost_revision": "cost_r001",
                "artifacts": {},
            })
            write(planning_root / "01_ideas/idea_r001/planning_brief.json", {})
            write(planning_root / "02_concepts/concept_r001/concept.json", {})
            write(planning_root / "02_concepts/concept_r002/concept.json", {})
            write(planning_root / "03_layouts/layout_r001/layout.json", {})
            write(planning_root / "04_costs/cost_r001/cost_estimate.json", {})
            write(planning_root / "05_detailed_plans/concept_r002/detailed_step_plans.json", {})
            tools = WorkflowAgentTools(workflow=workflow)
            state = tools._state()
            state["active_sequence_revision"] = "r002"
            tools._write_state(state)

            revisions = tools.inspect_session()["available_revisions"]

            self.assertEqual(revisions["sequence"], [
                {"revision_id": "r001", "active": False},
                {"revision_id": "r002", "active": True},
            ])
            self.assertEqual(revisions["automation_concept"], [
                {"revision_id": "concept_r001", "active": False},
                {"revision_id": "concept_r002", "active": True},
            ])
            self.assertEqual(revisions["layout"], [
                {"revision_id": "layout_r001", "active": True},
            ])

    def test_only_authorized_supporting_documents_can_be_ingested(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allowed = root / "instructions.md"
            allowed.write_text("Install the retaining ring last.", encoding="utf-8")
            workflow = FakeWorkflow(root / "session")
            tools = WorkflowAgentTools(workflow=workflow, supporting_files=[allowed])
            result = tools.ingest_documents(["instructions.md"])
            self.assertIn("retaining ring", result["documents"][0]["excerpt"])
            with self.assertRaisesRegex(ValueError, "not authorized"):
                tools.ingest_documents(["other.md"])

    def test_tools_enforce_feedback_dependencies_and_sequence_evaluation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            step = root / "fixture.step"
            step.write_text("STEP")
            workflow = FakeWorkflow(root / "session")
            tools = WorkflowAgentTools(workflow=workflow, step_file=step)

            tools.analyse_assembly()
            tools.analyse_monoparts()
            generated = tools.generate_sequence()
            self.assertEqual(generated["revision_id"], "r001")
            completed = tools.ffa_evaluation()
            self.assertEqual(completed["status"], "complete")

            tools.record_context_change(scope="assembly", raw_user_message="It is a bearing support",
                                        agent_summary="Assembly is a bearing support.",
                                        feedback_type="correction")
            self.assertTrue(tools.inspect_session()["stale"]["assembly"])
            rerun = tools.ffa_evaluation()
            self.assertEqual(rerun["status"], "complete")

    def test_bom_handling_feedback_uses_part_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            step = root / "fixture.step"
            step.write_text("STEP")
            workflow = FakeWorkflow(root / "session")
            tools = WorkflowAgentTools(workflow=workflow, step_file=step)

            result = tools.record_context_change(
                scope="part",
                raw_user_message="Circlips will be delivered in bulk",
                agent_summary="Circlips are supplied in bulk and require bulk-feeding analysis.",
                feedback_type="correction",
            )

            self.assertEqual(result["feedback"]["scope"], "part")
            self.assertTrue(tools.inspect_session()["stale"]["monoparts"])

            with self.assertRaisesRegex(ValueError, "Unknown feedback scope"):
                tools.record_context_change(
                    scope="automation_planning_premise",
                    raw_user_message="Another correction",
                    agent_summary="Invalid legacy scope.",
                )

    def test_automation_planning_can_use_existing_report_after_ffa_disagreement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            step = root / "fixture.step"; step.write_text("STEP")
            workflow = FakeWorkflow(root / "session")
            tools = WorkflowAgentTools(workflow=workflow, step_file=step)
            tools.analyse_assembly(); tools.analyse_monoparts(); tools.generate_sequence()
            tools.ffa_evaluation()
            tools.record_context_change(
                scope="ffa_report", raw_user_message="The ring steps should be equal",
                agent_summary="Treat both ring steps as equally difficult.",
                feedback_type="correction")
            self.assertTrue(tools.inspect_session()["stale"]["final"])
            tools._automation_workflow = FakeAutomationPlanning()
            tools.current_user_message = "Plan both ring steps as manual"

            result = tools.automation_concept_idea_generator(
                "Plan both ring steps as manual",
                "Use the existing FfA as evidence, but treat both ring steps as manual.")

        self.assertEqual(result["status"], "awaiting_idea_review")

    def test_sequence_revision_uses_initial_sequence_and_cumulative_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            step = root / "fixture.step"; step.write_text("STEP")
            workflow = FakeWorkflow(root / "session")
            tools = WorkflowAgentTools(workflow=workflow, step_file=step)
            tools.analyse_assembly(); tools.analyse_monoparts(); tools.generate_sequence()
            result = tools.revise_sequence("Insert it second", "Insert the pin in step two.")
            self.assertEqual(result["revision_id"], "r002")
            call = workflow.calls[-1]
            self.assertEqual(call[2], "revise")
            self.assertIn("Insert the pin", call[3])


class FakeToolCallingModel:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    def invoke(self, messages):
        from langchain_core.messages import AIMessage
        self.calls += 1
        if self.calls == 1:
            return AIMessage(content="I will inspect the current session.", tool_calls=[
                {"name": "inspect_session", "args": {}, "id": "call_1"}])
        return AIMessage(content="The session is ready for assembly analysis.")


class IntroductionModel:
    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        from langchain_core.messages import AIMessage
        return AIMessage(content=(
            "Hi, I am FfA Navigator. I will guide preprocessing, assembly and part review, "
            "sequence review, and the final automation assessment."))


class DeterministicChatModel(BaseChatModel):
    """Network-free real LangChain model used to exercise create_agent."""

    _bound_tool_sets: list[list[str]] = PrivateAttr(default_factory=list)
    _received_messages: list[list[str]] = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "deterministic-test"

    def bind_tools(self, tools, **kwargs):
        self._bound_tool_sets.append([tool.name for tool in tools])
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._received_messages.append([str(message.content) for message in messages])
        return ChatResult(generations=[ChatGeneration(
            message=AIMessage(content="Current workflow state reviewed."))])


class UserFacingAgentTests(unittest.TestCase):
    def test_real_langchain_agent_exposes_configured_tools_and_resumes_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = FakeWorkflow(Path(directory) / "session")
            toolbox = WorkflowAgentTools(workflow=workflow)
            settings = {"llm": {"profile": "test"}, "prompt": "system_v1",
                        "tools": ["inspect_session", "analyse_assembly", "analyse_monoparts",
                                  "generate_sequence", "revise_sequence", "ffa_evaluation"],
                        "max_tool_rounds": 2}
            profiles = {"test": {"provider": "openai", "model": "test", "api_key_env": "UNUSED"}}
            first_model = DeterministicChatModel()
            first = UserFacingAgent(toolbox=toolbox, settings=settings,
                                    llm_profiles=profiles, llm=first_model)
            first.invoke("What should happen next?")
            self.assertIn("analyse_assembly", first_model._bound_tool_sets[-1])
            self.assertIn("ffa_evaluation", first_model._bound_tool_sets[-1])
            self.assertTrue(first.checkpoint_path.is_file())
            history = json.loads(first.history_path.read_text(encoding="utf-8"))
            self.assertEqual(history[-1], {"role": "assistant",
                                           "content": "Current workflow state reviewed."})
            first.close()

            write(workflow.paths.assembly_overview, OVERVIEW)
            write(workflow.paths.enriched_bom, BOM)
            write(workflow.paths.revision("r001") / "assembly_sequence.json", SEQUENCE)
            toolbox._write_state({"active_sequence_revision": "r001",
                                  "stale": {"assembly": False, "monoparts": False,
                                            "sequence": False, "renderings": True, "final": True}})
            resumed_model = DeterministicChatModel()
            resumed = UserFacingAgent(toolbox=toolbox, settings=settings,
                                      llm_profiles=profiles, llm=resumed_model)
            resumed.invoke("The sequence is accepted; continue.")
            self.assertIn("ffa_evaluation", resumed_model._bound_tool_sets[-1])
            self.assertIn("analyse_assembly", resumed_model._bound_tool_sets[-1])
            self.assertTrue(any("What should happen next?" in message
                                for message in resumed_model._received_messages[-1]))
            resumed.close()

    def test_pre_session_introduction_uses_agent_without_tools(self):
        text = generate_introduction(
            {"llm": {"profile": "test"}, "prompt": "system_v1",
             "introduction": {"max_completion_tokens": 300}},
            {"test": {"provider": "openai", "model": "test", "api_key_env": "UNUSED"}},
            llm=IntroductionModel())

        self.assertIn("FfA Navigator", text)

    def test_product_configuration_enables_semantic_change_tool(self):
        workspace = Path(__file__).resolve().parents[1]
        config = yaml.safe_load((workspace / "configs/appsettingsv3.yaml").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            workflow = FakeWorkflow(Path(directory) / "session")
            agent = UserFacingAgent(
                toolbox=WorkflowAgentTools(workflow=workflow),
                settings=config["user_agent"], llm_profiles=config["llms"]["profiles"],
                llm=FakeToolCallingModel())
        self.assertIn("change_artifact", agent.tool_map)
        self.assertIn("record_context_change", agent.tool_map)
        self.assertNotIn("set_user_context", agent.tool_map)
        self.assertIsNotNone(agent.toolbox.artifact_change_planner)

    def test_system_prompt_delegates_operational_policy_to_tools(self):
        prompt = UserFacingAgent._load_prompt("system_v1")
        self.assertIn("There are no analysis, monopart_analysis, or sequence wrapper objects", prompt)
        self.assertIn("Tool descriptions define their eligibility", prompt)
        self.assertIn("Do not narrate tool selection", prompt)
        self.assertIn("Do not rerun FfA", prompt)
        self.assertIn("Minor wording corrections use the artifact-editing tools", prompt)

    def test_announcement_is_persisted_and_emitted_before_other_turns(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = FakeWorkflow(Path(directory) / "session")
            events = []
            agent = UserFacingAgent(
                toolbox=WorkflowAgentTools(workflow=workflow),
                settings={"llm": {"profile": "test"}, "prompt": "system_v1",
                          "tools": ["inspect_session"], "max_tool_rounds": 2},
                llm_profiles={"test": {"provider": "openai", "model": "test",
                                        "api_key_env": "UNUSED"}},
                llm=FakeToolCallingModel(), event_callback=events.append)
            agent.announce("Hi, I am FfA Navigator. Here are the next steps.")
            history = json.loads(agent.history_path.read_text())

        self.assertEqual(history, [{"role": "assistant",
                                    "content": "Hi, I am FfA Navigator. Here are the next steps."}])
        self.assertEqual(events[0]["type"], "assistant_message")

    def test_hidden_introduction_persists_only_the_agent_response(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = FakeWorkflow(Path(directory) / "session")
            events = []
            agent = UserFacingAgent(
                toolbox=WorkflowAgentTools(workflow=workflow),
                settings={"llm": {"profile": "test"}, "prompt": "system_v1",
                          "tools": ["inspect_session"], "max_tool_rounds": 2},
                llm_profiles={"test": {"provider": "openai", "model": "test",
                                        "api_key_env": "UNUSED"}},
                llm=IntroductionModel(), event_callback=events.append)

            result = agent.invoke("Introduce yourself", visible_user_message=False,
                                  allow_tools=False)
            history = json.loads(agent.history_path.read_text())

        self.assertEqual([item["role"] for item in history], ["assistant"])
        self.assertNotIn("Introduce yourself", json.dumps(history))
        self.assertIn("FfA Navigator", result["response"])
        self.assertEqual(events[0]["type"], "assistant_message")

    def test_agent_executes_tools_and_persists_dialogue(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = FakeWorkflow(Path(directory) / "session")
            toolbox = WorkflowAgentTools(workflow=workflow)
            model = FakeToolCallingModel()
            agent = UserFacingAgent(
                toolbox=toolbox,
                settings={"llm": {"profile": "test"}, "prompt": "system_v1",
                          "tools": ["inspect_session"], "max_tool_rounds": 2},
                llm_profiles={"test": {"provider": "openai", "model": "test",
                                        "api_key_env": "UNUSED"}}, llm=model)
            result = agent.invoke("What is the current status?")
            history = json.loads(agent.history_path.read_text())
        self.assertEqual(result["tool_calls"][0]["tool"], "inspect_session")
        self.assertIn("ready", result["response"])
        self.assertEqual([item["role"] for item in history], ["user", "assistant"])
        self.assertNotIn("I will inspect", json.dumps(history))

    def test_explicit_ui_action_uses_enabled_tool_and_persists_dialogue(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = FakeWorkflow(Path(directory) / "session")
            toolbox = WorkflowAgentTools(workflow=workflow)
            agent = UserFacingAgent(
                toolbox=toolbox,
                settings={"llm": {"profile": "test"}, "prompt": "system_v1",
                          "tools": ["inspect_session"], "max_tool_rounds": 2},
                llm_profiles={"test": {"provider": "openai", "model": "test",
                                        "api_key_env": "UNUSED"}}, llm=FakeToolCallingModel())

            result = agent.execute_tool("inspect_session", {}, user_message="Refresh the status")
            history = json.loads(agent.history_path.read_text())

        self.assertEqual(result["tool_calls"][0]["tool"], "inspect_session")
        self.assertEqual(history[0], {"role": "user", "content": "Refresh the status"})
        with self.assertRaisesRegex(ValueError, "not enabled"):
            agent.execute_tool("ffa_evaluation", {}, user_message="Run evaluation")


if __name__ == "__main__":
    unittest.main()
