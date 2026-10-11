import unittest

import fixtures
from fixtures import FIXTURE_DATA

from scan import build_index, scan_text


class TestScanClassify(unittest.TestCase):
    def setUp(self):
        self.index = build_index(FIXTURE_DATA, ambiguous_names=["Enterprise Edition"])

    def scan(self, text):
        return scan_text(text, self.index)

    def test_outdated_name(self):
        findings = self.scan("We use Pardot daily.")
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f.classification, "outdated")
        self.assertEqual(f.current_name, "Account Engagement")
        self.assertEqual(f.changed_on, "2022-04")
        self.assertEqual(f.product_id, "account-engagement")

    def test_current_name_not_flagged(self):
        findings = self.scan("Account Engagement is great.")
        self.assertEqual([f.classification for f in findings], ["current"])

    def test_reverted_name(self):
        findings = self.scan("Agentforce Sales")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].classification, "outdated")
        self.assertEqual(findings[0].current_name, "Sales Cloud")
        self.assertEqual(findings[0].changed_on, "2026-09")

    def test_longest_match_wins(self):
        findings = self.scan("Marketing Cloud Account Engagement")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].matched, "Marketing Cloud Account Engagement")

    def test_multi_product_name_ambiguous(self):
        findings = self.scan("Connect")
        self.assertEqual([f.classification for f in findings], ["ambiguous"])

    def test_generic_phrase_ambiguous(self):
        findings = self.scan("Enterprise Edition")
        self.assertEqual([f.classification for f in findings], ["ambiguous"])

    def test_generic_phrase_outdated_without_ambiguous_list(self):
        index = build_index(FIXTURE_DATA)
        findings = scan_text("Enterprise Edition", index)
        self.assertEqual([f.classification for f in findings], ["outdated"])

    def test_alias_is_current(self):
        findings = self.scan("MCAE")
        self.assertEqual([f.classification for f in findings], ["current"])
        self.assertIn("alias", findings[0].reason)

    def test_case_insensitive(self):
        findings = self.scan("pardot")
        self.assertEqual(findings[0].classification, "outdated")
        self.assertEqual(findings[0].matched, "pardot")

    def test_word_boundary(self):
        self.assertEqual(self.scan("Pardotville"), [])
        self.assertEqual(self.scan("Prepardot"), [])

    def test_possessive_matches(self):
        findings = self.scan("Pardot's roadmap")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].matched, "Pardot")
        self.assertEqual(findings[0].column, 1)

    def test_unknown_name_ignored(self):
        self.assertEqual(self.scan("Acme Cloud"), [])

    def test_line_and_column(self):
        findings = self.scan("intro\nWe use Pardot")
        self.assertEqual((findings[0].line, findings[0].column), (2, 8))

    def test_to_dict_has_all_fields(self):
        d = self.scan("Pardot")[0].to_dict()
        self.assertEqual(
            set(d),
            {"path", "line", "column", "matched", "product_id", "classification",
             "current_name", "changed_on", "reason"},
        )


if __name__ == "__main__":
    unittest.main()
