from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import unittest

import yaml


class PromptMigrationTests(unittest.TestCase):
    def test_every_global_legacy_prompt_has_one_verified_local_copy(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = yaml.safe_load(
            (root / "configs" / "prompts.yaml").read_text(encoding="utf-8")
        )["prompts"]

        entries: list[dict] = []
        node_root = root / "src" / "assembly_automation" / "workflows" / "nodes"
        for path in node_root.glob("*/prompts.yaml"):
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            entries.extend(
                value
                for key, value in (document.get("prompts") or {}).items()
                if key.startswith("legacy_")
            )

        user_prompts = yaml.safe_load(
            (root / "src" / "assembly_automation" / "user_agent" / "prompts.yaml").read_text(
                encoding="utf-8"
            )
        )
        entries.extend((user_prompts.get("legacy_prompts") or {}).values())

        self.assertEqual(len(entries), len(source))
        self.assertEqual({entry["legacy_id"] for entry in entries}, set(source))
        self.assertEqual(len({entry["legacy_id"] for entry in entries}), len(entries))

        for entry in entries:
            original = source[entry["legacy_id"]]
            original_text = original.get("text") if isinstance(original, dict) else original
            original_text = original_text.strip()
            self.assertEqual(
                entry["source_sha256"], sha256(original_text.encode("utf-8")).hexdigest()
            )
            # Local historical variants must remain safe for the shared formatter.
            entry["text"].format_map({"context": "test", "strategy": "manual"})

    def test_active_prompts_exist_for_each_prompt_owning_module(self) -> None:
        root = Path(__file__).resolve().parents[1]
        expected = {
            "assembly_analysis": {"system_v1", "human_v1"},
            "monopart_analysis": {"system_v1", "human_v1"},
            "sequence_generation": {"system_v1", "generate_v1", "revise_v1"},
            "interaction_analysis": {"system_v1", "human_v1"},
            "ffa_assessment": {"system_v1", "human_v1"},
            "report_synthesis": {"system_v1", "human_v1"},
            "document_summary": {"system_v1", "human_v1"},
            "automation_requirements": {"system_v1", "human_v1"},
            "process_principles": {"system_v1", "human_v1"},
            "automation_variants": {
                "generator_system_v1",
                "generator_human_v1",
                "evaluator_system_v1",
                "evaluator_human_v1",
            },
            "layout_planning": {
                "layout_system_v1",
                "layout_human_v1",
                "station_system_v1",
                "station_human_v1",
                "workplace_system_v1",
                "workplace_human_v1",
            },
        }
        node_root = root / "src" / "assembly_automation" / "workflows" / "nodes"
        for module, prompt_ids in expected.items():
            document = yaml.safe_load(
                (node_root / module / "prompts.yaml").read_text(encoding="utf-8")
            )
            prompts = document["prompts"]
            for prompt_id in prompt_ids:
                self.assertIn(prompt_id, prompts, f"{module}: {prompt_id}")
                self.assertTrue(prompts[prompt_id]["text"].strip())


if __name__ == "__main__":
    unittest.main()
