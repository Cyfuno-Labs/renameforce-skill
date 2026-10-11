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

    def test_skill_detects_the_python_interpreter(self):
        text = skill_text()
        for probe in ("python3 --version", "python --version", "py -3 --version"):
            self.assertIn(probe, text)
        self.assertIn("<python>", text)
        self.assertNotIn("python scripts/", text, "commands must use <python>, not a fixed interpreter name")

    def test_skill_explains_data_sources(self):
        text = skill_text()
        for source in ("`cache`", "`live`", "`snapshot`"):
            self.assertIn(source, text)
        self.assertIn("just now", text)

    def test_matching_rules_cover_mixed_old_and_new_names(self):
        rules = (SKILL_DIR / "references" / "matching-rules.md").read_text(encoding="utf-8")
        self.assertIn("mixes old and new", rules)
        self.assertIn("mixed", skill_text().lower())

    def test_skill_defines_the_findings_table(self):
        text = skill_text()
        self.assertIn("| Where | Found | Change to | Since | Action |", text)
        for action in ("**Update**", "**Keep**", "**Ask**"):
            self.assertIn(action, text)
        self.assertIn("already current", text.lower())

    def test_skill_is_agent_neutral(self):
        text = skill_text()
        self.assertIn("AGENTS.md", text)
        self.assertIn("a Drive search tool", text)
        self.assertIn("a Drive read tool", text)

    def test_readme_has_other_agents_section(self):
        readme = (fixtures.ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("## Other agents", readme)
        self.assertIn("AGENTS.md", readme)
        self.assertIn("verified in Claude Code", readme)

    def test_skill_documents_legacy_aliases(self):
        text = skill_text()
        self.assertIn("legacy alias", text.lower())
        section = text.split("### Without scripts")[1].split("###")[0]
        self.assertIn("legacy_aliases", section)

    def test_matching_rules_explain_legacy_aliases(self):
        rules = (SKILL_DIR / "references" / "matching-rules.md").read_text(encoding="utf-8")
        self.assertIn("legacy alias", rules.lower())
        self.assertIn("SFMC", rules)
        self.assertIn("MCE", rules)

    def test_findings_table_covers_unknown_since(self):
        self.assertIn("when the date is unknown", skill_text())


if __name__ == "__main__":
    unittest.main()
