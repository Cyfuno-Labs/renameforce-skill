"""Guards against generic words and acronym collisions in the real data causing false 'outdated' flags."""
import json
import subprocess
import sys
import unittest

import fixtures
from fixtures import SCRIPTS_DIR

GENERIC = ["chat", "flow", "insights", "wave", "einstein", "engage", "starter", "MCP"]


class TestGenericWordsNeverAutoFlagged(unittest.TestCase):
    def test_generic_words_are_never_outdated_or_silently_current(self):
        text = "\n".join(f"We talk about {w} a lot." for w in GENERIC)
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "scan.py"), "-"],
            input=text.encode("utf-8"),
            capture_output=True,
            check=True,
        )
        for finding in json.loads(proc.stdout.decode("utf-8")):
            self.assertEqual(
                finding["classification"],
                "ambiguous",
                f"{finding['matched']!r} classified {finding['classification']}",
            )


if __name__ == "__main__":
    unittest.main()
