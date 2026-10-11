import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import fixtures
from fixtures import FIXTURE_DATA, SCRIPTS_DIR


class TestScanCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.data = self.dir / "data.json"
        self.data.write_text(json.dumps(FIXTURE_DATA), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, stdin=None):
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "scan.py"), "--data", str(self.data), *args],
            input=stdin,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        return json.loads(proc.stdout.decode("utf-8"))

    def write(self, name, content):
        path = self.dir / name
        path.write_bytes(content)
        return str(path)

    def test_cli_finds_outdated_name_in_file(self):
        path = self.write("a.md", b"We use Pardot.\n")
        result = self.run_cli(path)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["classification"], "outdated")
        self.assertEqual(result[0]["path"], path)

    def test_cli_empty_file_returns_empty_array(self):
        self.assertEqual(self.run_cli(self.write("e.md", b"")), [])

    def test_cli_bom_file_scanned(self):
        result = self.run_cli(self.write("b.md", b"\xef\xbb\xbfPardot rocks"))
        self.assertEqual((result[0]["line"], result[0]["column"]), (1, 1))

    def test_cli_binary_file_reported_skipped(self):
        path = self.write("x.bin", b"Pardot\x00\x01\x02")
        result = self.run_cli(path)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["path"], path)
        self.assertIn("skipped", result[0])

    def test_cli_invalid_utf8_is_decoded_with_a_note_not_skipped(self):
        result = self.run_cli(self.write("l.txt", b"Pardot \xff\xfe"))
        self.assertEqual([r for r in result if "skipped" in r], [])
        self.assertEqual(len([r for r in result if "note" in r]), 1)
        self.assertEqual(len([r for r in result if "classification" in r]), 1)

    def test_cli_missing_file_reported_skipped(self):
        result = self.run_cli(str(self.dir / "nope.md"))
        self.assertIn("skipped", result[0])

    def test_cli_stdin(self):
        result = self.run_cli("-", stdin=b"Pardot")
        self.assertEqual(result[0]["path"], "<stdin>")
        self.assertEqual(result[0]["classification"], "outdated")

    def test_cli_directory_is_walked_for_text_files(self):
        root = self.dir / "docs"
        (root / "sub").mkdir(parents=True)
        (root / "node_modules").mkdir()
        (root / ".git").mkdir()
        (root / "a.md").write_bytes(b"Pardot here")
        (root / "sub" / "b.txt").write_bytes(b"Pardot there")
        (root / "node_modules" / "x.md").write_bytes(b"Pardot hidden")
        (root / ".git" / "c.md").write_bytes(b"Pardot hidden")
        (root / "pic.png").write_bytes(b"Pardot\x89PNG")
        result = self.run_cli(str(root))
        paths = sorted(Path(f["path"]).relative_to(root).as_posix() for f in result)
        self.assertEqual(paths, ["a.md", "sub/b.txt"])

    def test_cli_explicit_file_is_scanned_regardless_of_extension(self):
        path = self.write("notes.weird", b"Pardot")
        self.assertEqual(len(self.run_cli(path)), 1)

    def test_cli_utf16_file_with_bom_is_scanned(self):
        path = self.write("u16.txt", "We use Pardot here".encode("utf-16"))
        result = self.run_cli(path)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["classification"], "outdated")
        self.assertNotIn("skipped", result[0])

    def test_cli_cp1252_file_is_scanned_with_a_note(self):
        path = self.write("w1252.txt", ("Pardot caf" + chr(233)).encode("cp1252"))
        result = self.run_cli(path)
        findings = [r for r in result if "classification" in r]
        notes = [r for r in result if "note" in r]
        self.assertEqual(len(findings), 1)
        self.assertEqual(len(notes), 1)
        self.assertIn("1252", notes[0]["note"])
        self.assertEqual(notes[0]["path"], path)

    def test_cli_real_binary_without_bom_is_still_skipped(self):
        path = self.write("blob.bin", bytes([0, 1, 2, 3, 80, 97, 114, 100, 111, 116]))
        result = self.run_cli(path)
        self.assertEqual(len(result), 1)
        self.assertIn("skipped", result[0])

    def test_cli_include_code_flag(self):
        path = self.write("c.md", b"`Pardot`")
        self.assertEqual(self.run_cli(path), [])
        self.assertEqual(len(self.run_cli("--include-code", path)), 1)


if __name__ == "__main__":
    unittest.main()
