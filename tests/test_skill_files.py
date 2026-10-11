import re
import unittest
from pathlib import Path

import fixtures

SKILL_DIR = fixtures.ROOT / "renameforce"
SKILL_MD = SKILL_DIR / "SKILL.md"


def skill_text():
    return SKILL_MD.read_text(encoding="utf-8")


class TestSkillFiles(unittest.TestCase):
    def test_skill_frontmatter(self):
        text = skill_text()
        match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.DOTALL)
        self.assertIsNotNone(match, "SKILL.md must start with YAML frontmatter")
        front = match.group(1)
        self.assertRegex(front, r"(?m)^name:\s*renameforce\s*$")
        description = re.search(r"(?m)^description:\s*(.+)$", front)
        self.assertIsNotNone(description)
        self.assertGreater(len(description.group(1).strip()), 40)

    def test_skill_mentions_all_modes(self):
        text = skill_text()
        for mode in ("report", "review", "apply"):
            self.assertIn(f"`{mode}`", text)

    def test_skill_references_exist(self):
        refs = set(re.findall(r"\b((?:scripts|references|data)/[\w.\-]+\.(?:py|md|json))\b", skill_text()))
        self.assertTrue(refs, "SKILL.md should name its helper files")
        for ref in refs:
            self.assertTrue((SKILL_DIR / ref).exists(), f"{ref} is referenced but missing")

    def test_skill_documents_python_fallback(self):
        text = skill_text()
        self.assertIn("names-index.json", text)
        self.assertIn("reduced-precision", text)

    def test_skill_documents_drive_limits(self):
        text = skill_text()
        self.assertIn("read_file_content", text)
        self.assertIn("Find and Replace", text)

    def test_skill_documents_invariants(self):
        text = skill_text().lower()
        self.assertIn("never auto-changed", text)
        self.assertIn("generated_at", text)


if __name__ == "__main__":
    unittest.main()
