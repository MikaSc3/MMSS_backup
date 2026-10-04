import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assembly_automation.user_agent.storage import atomic_write_json


class UserAgentStorageTests(unittest.TestCase):
    def test_atomic_write_retries_transient_windows_permission_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conversation.json"
            real_replace = os.replace
            calls = 0

            def flaky_replace(source, target):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise PermissionError(5, "Access denied")
                return real_replace(source, target)

            with patch("assembly_automation.user_agent.storage.os.replace",
                       side_effect=flaky_replace):
                atomic_write_json(path, [{"role": "user", "content": "continue"}])

            self.assertEqual(calls, 2)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))[0]["content"],
                             "continue")
            self.assertEqual(list(path.parent.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
