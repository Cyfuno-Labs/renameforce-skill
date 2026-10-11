import unittest

import fixtures
from fixtures import FIXTURE_DATA

from scan import build_index, scan_text


class TestSkippedRegions(unittest.TestCase):
    def setUp(self):
        self.index = build_index(FIXTURE_DATA)

    def check_skipped(self, text):
        self.assertEqual(scan_text(text, self.index), [])
        found = scan_text(text, self.index, include_code=True)
        self.assertEqual(len(found), 1, text)
        return found[0]

    def test_fenced_code_skipped(self):
        self.check_skipped("```\nPardot\n```\n")

    def test_tilde_fence_skipped(self):
        self.check_skipped("~~~python\nPardot\n~~~\n")

    def test_inline_code_skipped(self):
        self.check_skipped("Run `Pardot` now")

    def test_url_skipped(self):
        self.check_skipped("See https://example.com/Pardot/docs for details")

    def test_path_skipped(self):
        self.check_skipped("Edit ./docs/Pardot.md today")
        self.check_skipped(r"Open C:\Users\me\Pardot\notes.txt please")

    def test_slash_separated_names_not_treated_as_path(self):
        findings = scan_text("Pardot/Account Engagement", self.index)
        self.assertEqual(findings[0].matched, "Pardot")

    def test_text_outside_fence_still_found(self):
        findings = scan_text("```\nx\n```\nPardot here", self.index)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].line, 4)

    def test_unclosed_fence_skips_to_end(self):
        self.assertEqual(scan_text("```\nPardot", self.index), [])

    def test_crlf_line_numbers(self):
        findings = scan_text("a\r\nPardot", self.index)
        self.assertEqual((findings[0].line, findings[0].column), (2, 1))
        self.assertNotIn("\r", findings[0].matched)

    def test_crlf_fence(self):
        findings = scan_text("```\r\nPardot\r\n```\r\nPardot", self.index)
        self.assertEqual([f.line for f in findings], [4])


if __name__ == "__main__":
    unittest.main()
