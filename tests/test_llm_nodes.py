import json
from base64 import b64decode
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assembly_automation.workflows.nodes.assembly_analysis import run_assembly_analysis
from assembly_automation.workflows.nodes.monopart_analysis import run_monopart_analysis
from assembly_automation.workflows.runtime.prompting import build_prompt
from assembly_automation.workflows.runtime.tools import resolve_tools


PNG_1X1 = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


class _StructuredCall:
    def __init__(self, value):
        self.value = value

    def invoke(self, messages):
        return {"parsed": self.value, "raw": None}


class _FakeLlm:
    def __init__(self, value):
        self.value = value
        self.schema = None

    def with_structured_output(self, schema, include_raw=True):
        self.schema = schema
        return _StructuredCall(schema(**self.value))


class PromptBuilderTests(unittest.TestCase):
    def test_nested_json_fields_and_scoped_part_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompts = root / "prompts.yaml"
            prompts.write_text(
                "prompts:\n  s:\n    role: system\n    text: System\n  h:\n    role: human\n    text: Human\n",
                encoding="utf-8",
            )
            bom = root / "bom.json"
            bom.write_text(json.dumps({"parts": [{"part_id": "part_001", "geometry": {"size": {"x": 4}}, "drop": 9}]}), encoding="utf-8")
            image_dir = root / "images" / "parts" / "part_001"
            image_dir.mkdir(parents=True)
            (image_dir / "iso1.png").write_bytes(PNG_1X1)

            payload = build_prompt(
                prompts_path=prompts,
                system_prompt_id="s",
                human_prompt_id="h",
                input_specs={
                    "part": {"kind": "json", "source": "bom", "select": {"path": "parts", "field": "part_id", "equals": "{part_id}"}, "fields": ["part_id", "geometry.size"]},
                    "part_images": {"kind": "images", "source": "images", "path": "parts/{part_id}", "patterns": ["iso1.png"], "required": True},
                },
                artifacts={"bom": bom, "images": root / "images"},
                context={"part_id": "part_001"},
            )

            text = payload.messages[1]["content"][0]["text"]
            self.assertIn('"part_id": "part_001"', text)
            self.assertIn('"size"', text)
            self.assertNotIn('"drop"', text)
            self.assertEqual([Path(path).name for path in payload.images], ["iso1.png"])

    def test_tools_are_allowlisted(self):
        tool = object()
        self.assertEqual(resolve_tools(["lookup"], {"lookup": tool}), [tool])
        with self.assertRaises(ValueError):
            resolve_tools(["missing"], {})


class AssemblyAnalysisNodeTests(unittest.TestCase):
    def test_configured_node_builds_and_writes_structured_result(self):
        workspace = Path(__file__).resolve().parents[1]
        config = yaml.safe_load((workspace / "configs/appsettingsv3.yaml").read_text(encoding="utf-8"))
        settings = config["nodes"]["assembly_analysis"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            images = root / "images" / "assembly"
            images.mkdir(parents=True)
            (images / "collage_assembly.png").write_bytes(PNG_1X1)
            values = {
                "assembly": {"name": "fixture", "total_parts": 1, "unique_parts": 1, "units": {"length": "mm"}, "geometry": {"size": {"x": 1}, "center_of_mass": [0, 0, 0]}, "hierarchy": []},
                "bom": {"parts": [], "instances": []},
                "spatial_relations": {"contact_map": {}, "close_map": {}, "statistics": {}},
                "interlocking": {"method": "proxy", "parts": [], "blocker_edges": [], "interlocked_groups": [], "limitations": []},
            }
            artifacts = {"images": root / "images"}
            for name, value in values.items():
                path = root / f"{name}.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                artifacts[name] = path
            output = root / "assembly_analysis" / "assembly_overview.json"
            fake = _FakeLlm({"assembly_description": "one part", "partslist": ["part"], "assembly_name_guess": "Fixture", "primary_function": ["Holding"]})

            response = run_assembly_analysis(
                artifacts=artifacts,
                settings=settings,
                llm_profiles=config["llms"]["profiles"],
                context={"user_context": "Used for testing."},
                output_path=output,
                llm=fake,
            )

            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(response["status"], "complete")
            self.assertEqual(saved["assembly_name_guess"], "Fixture")
            self.assertEqual(response["run_record"]["execution"]["llm_profile"], "gpt_5_4")
            self.assertEqual(len(response["run_record"]["images_used"]), 1)
            self.assertTrue(Path(response["run_record_path"]).is_file())
            self.assertEqual(fake.schema.__name__, "AssemblyAnalysis")


class MonopartAnalysisNodeTests(unittest.TestCase):
    def test_one_part_includes_all_placed_instances_and_writes_result(self):
        workspace = Path(__file__).resolve().parents[1]
        config = yaml.safe_load((workspace / "configs/appsettingsv3.yaml").read_text(encoding="utf-8"))
        settings = config["nodes"]["monopart_analysis"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            part_images = root / "images/parts/part_001"
            part_images.mkdir(parents=True)
            (part_images / "collage_part_001.png").write_bytes(PNG_1X1)
            bom = {
                "parts": [{"part_id": "part_001", "name": "ring", "quantity": 2,
                           "color": [1, 2, 3], "geometry": {"volume": 4, "surface_area": 5,
                           "center_of_mass": [0, 0, 0], "size": {"x": 1, "y": 2, "z": 3}}}],
                "instances": [{"instance_id": "part_001", "part_id": "part_001", "assembly_id": "assy_001", "center_of_mass": [0, 0, 0]},
                              {"instance_id": "part_001_002", "part_id": "part_001", "assembly_id": "assy_001", "center_of_mass": [10, 0, 0]}],
            }
            bom_path = root / "bom.json"
            bom_path.write_text(json.dumps(bom), encoding="utf-8")
            overview = root / "assembly_overview.json"
            overview.write_text(json.dumps({"assembly_name_guess": "Fixture", "primary_function": ["Holding"],
                                            "assembly_description": "Description", "partslist": ["ring"]}), encoding="utf-8")
            output = root / "monopart_analysis/parts/part_001.json"
            fake = _FakeLlm({
                "part_identification": "Retaining feature", "part_name_guess": "Ring", "part_color": "blue",
                "material_and_mechanical_behavior": ["Rigid"], "bulk_behavior": ["May tangle"],
                "magazine_behavior": ["Can lie flat"], "nature_of_provision_guess": ["Tray"],
                "geometric_characteristics": ["Annular"], "gripping_analysis": ["External grip"],
                "handling_implications": ["Orientation required"], "intrinsic_summary": ["Small annular part."],
            })

            response = run_monopart_analysis(
                part_id="part_001",
                artifacts={"bom": bom_path, "assembly_overview": overview, "images": root / "images"},
                settings=settings,
                llm_profiles=config["llms"]["profiles"],
                output_path=output,
                llm=fake,
            )

            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(response["status"], "complete")
            self.assertEqual(saved["part_name_guess"], "Ring")
            self.assertEqual(response["run_record"]["execution"]["node"], "monopart_analysis")
            instance_input = next(item for item in response["run_record"]["inputs"] if item["id"] == "part_instances")
            self.assertEqual(instance_input["source"], "bom")
            self.assertEqual(response["run_record"]["images_used"], ["images/parts/part_001/collage_part_001.png"])
            self.assertEqual(fake.schema.__name__, "SinglePartAnalysis")


if __name__ == "__main__":
    unittest.main()
