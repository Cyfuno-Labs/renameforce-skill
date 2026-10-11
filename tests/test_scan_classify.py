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


class TestReviewFindings(unittest.TestCase):
    """Regressions found in the final whole-branch review."""

    def setUp(self):
        self.index = build_index(FIXTURE_DATA, ambiguous_names=["Enterprise Edition"])

    def test_retired_product_name_is_not_reported_current(self):
        findings = scan_text("Retired Studio", self.index)
        self.assertEqual([f.classification for f in findings], ["ambiguous"])
        self.assertIn("retired", findings[0].reason)

    def test_old_name_of_retired_product_is_not_auto_replaced(self):
        findings = scan_text("Old Studio", self.index)
        self.assertEqual([f.classification for f in findings], ["ambiguous"])
        self.assertIn("retired", findings[0].reason)

    def test_name_wrapped_across_lines_is_found(self):
        text = "We use Marketing Cloud\n  Account Engagement today"
        findings = scan_text(text, self.index)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].classification, "outdated")
        self.assertEqual((findings[0].line, findings[0].column), (1, 8))

    def test_name_with_nbsp_and_double_space_is_found(self):
        for text in ("Marketing Cloud Account Engagement", "Marketing  Cloud  Account Engagement"):
            findings = scan_text(text, self.index)
            self.assertEqual(len(findings), 1, repr(text))
            self.assertEqual(findings[0].classification, "outdated")

    def test_wrapped_crlf_name_is_found(self):
        findings = scan_text("Marketing Cloud\r\nAccount Engagement", self.index)
        self.assertEqual([f.product_id for f in findings], ["account-engagement"])
        self.assertEqual(findings[0].classification, "outdated")

    def test_case_folding_mismatch_does_not_crash(self):
        data = {
            "generated_at": "2026-10-10T00:00:00Z",
            "products": [
                {
                    "id": "e",
                    "current_name": "Agentforce",
                    "status": "active",
                    "aliases": [],
                    "timeline": [
                        {"name": "Einstein", "start": {"y": 2016}, "end": {"y": 2025}},
                        {"name": "Agentforce", "start": {"y": 2025}, "end": None},
                    ],
                }
            ],
        }
        index = build_index(data)
        findings = scan_text("EİNSTEİN and Einstein", index)
        self.assertIsInstance(findings, list)
        self.assertIn("Einstein", [f.matched for f in findings])


class TestLegacyAliases(unittest.TestCase):
    """Aliases that come from earlier names are outdated, not current."""

    @staticmethod
    def _data(*products):
        return {"version": 1, "generated_at": "2026-10-10T00:00:00Z", "products": list(products)}

    def test_legacy_alias_is_outdated(self):
        index = build_index(FIXTURE_DATA)
        findings = scan_text("I want SFMC to live forever!", index)
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f.classification, "outdated")
        self.assertEqual(f.current_name, "Marketing Cloud Engagement")
        self.assertIsNone(f.changed_on)
        self.assertIn("legacy", f.reason)
        self.assertEqual((f.line, f.column), (1, 8))

    def test_plain_alias_still_current(self):
        findings = scan_text("MCE", build_index(FIXTURE_DATA))
        self.assertEqual([f.classification for f in findings], ["current"])

    def test_legacy_alias_matching_a_timeline_name_follows_timeline(self):
        from fixtures import _product, _d
        product = _product(
            "ae",
            "Account Engagement",
            [("Pardot", _d(2007), _d(2022, 4)), ("Account Engagement", _d(2022, 4), None)],
            legacy_aliases=["Pardot"],
        )
        findings = scan_text("Pardot", build_index(self._data(product)))
        self.assertEqual(findings[0].classification, "outdated")
        self.assertEqual(findings[0].changed_on, "2022-04")

    def test_legacy_alias_equal_to_current_name_is_current(self):
        from fixtures import _product, _d
        product = _product(
            "ae", "Account Engagement", [("Account Engagement", _d(2022), None)],
            legacy_aliases=["Account Engagement"],
        )
        findings = scan_text("Account Engagement", build_index(self._data(product)))
        self.assertEqual([f.classification for f in findings], ["current"])

    def test_legacy_alias_shared_by_two_products_is_ambiguous(self):
        from fixtures import _product, _d
        a = _product("a", "Alpha Hub", [("Alpha Hub", _d(2020), None)], legacy_aliases=["ABC"])
        b = _product("b", "Beta Hub", [("Beta Hub", _d(2020), None)], legacy_aliases=["ABC"])
        findings = scan_text("ABC", build_index(self._data(a, b)))
        self.assertEqual([f.classification for f in findings], ["ambiguous"])

    def test_legacy_alias_of_retired_product_is_ambiguous(self):
        from fixtures import _product, _d
        p = _product(
            "old", "Retired Thing", [("Retired Thing", _d(2010), _d(2024))],
            status="deprecated", legacy_aliases=["RT"],
        )
        findings = scan_text("RT", build_index(self._data(p)))
        self.assertEqual([f.classification for f in findings], ["ambiguous"])
        self.assertIn("retired", findings[0].reason)

    def test_bad_alias_values_do_not_crash_the_scanner(self):
        product = {
            "id": "p",
            "current_name": "Marketing Cloud Engagement",
            "status": "active",
            "aliases": None,
            "legacy_aliases": [None, 7, "", "SFMC"],
            "timeline": [{"name": "Marketing Cloud Engagement", "start": {"y": 2022}, "end": None}],
        }
        other = {
            "id": "q",
            "current_name": "Q",
            "status": "active",
            "aliases": "oops",
            "legacy_aliases": "also oops",
            "timeline": [{"name": "Q", "start": {"y": 2020}, "end": None}],
        }
        index = build_index(self._data(product, other))
        findings = scan_text("SFMC", index)
        self.assertEqual([f.classification for f in findings], ["outdated"])

    def test_legacy_alias_in_ambiguous_list_is_ambiguous(self):
        index = build_index(FIXTURE_DATA, ambiguous_names=["SFMC"])
        findings = scan_text("SFMC", index)
        self.assertEqual([f.classification for f in findings], ["ambiguous"])
