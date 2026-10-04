import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assembly_automation.workflows.runtime.environment import load_project_environment


class RuntimeEnvironmentTests(unittest.TestCase):
    def test_loads_root_then_legacy_without_overriding_existing_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("ROOT_ONLY=from-root\nSHARED=root\n", encoding="utf-8")
            (root / "agent").mkdir()
            (root / "agent/.env").write_text(
                "LEGACY_ONLY=from-agent\nSHARED=agent\nPROCESS_VALUE=file\n", encoding="utf-8"
            )
            clean = {key: value for key, value in os.environ.items()
                     if key not in {"ROOT_ONLY", "LEGACY_ONLY", "SHARED", "PROCESS_VALUE"}}
            clean["PROCESS_VALUE"] = "process"
            with patch.dict(os.environ, clean, clear=True):
                loaded = load_project_environment(root)
                self.assertEqual(os.environ["ROOT_ONLY"], "from-root")
                self.assertEqual(os.environ["LEGACY_ONLY"], "from-agent")
                self.assertEqual(os.environ["SHARED"], "root")
                self.assertEqual(os.environ["PROCESS_VALUE"], "process")

        self.assertEqual(loaded, (root / ".env", root / "agent/.env"))


if __name__ == "__main__":
    unittest.main()
