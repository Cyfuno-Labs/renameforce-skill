import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import fixtures
from fixtures import FIXTURE_DATA, SCRIPTS_DIR

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def docx_bytes(path, body_xml):
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{W_NS}"><w:body>{body_xml}</w:body></w:document>'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)


def pptx_file(path, slides, notes=None):
    notes = notes or {}
    with zipfile.ZipFile(path, "w") as z:
        for number, paragraphs in slides.items():
            body = "".join(f"<a:p><a:r><a:t>{p}</a:t></a:r></a:p>" for p in paragraphs)
            z.writestr(
                f"ppt/slides/slide{number}.xml",
                f'<p:sld xmlns:p="{P_NS}" xmlns:a="{A_NS}"><p:cSld><p:spTree>{body}</p:spTree></p:cSld></p:sld>',
            )
        for number, paragraphs in notes.items():
            body = "".join(f"<a:p><a:r><a:t>{p}</a:t></a:r></a:p>" for p in paragraphs)
            z.writestr(
                f"ppt/notesSlides/notesSlide{number}.xml",
                f'<p:notes xmlns:p="{P_NS}" xmlns:a="{A_NS}"><p:cSld><p:spTree>{body}</p:spTree></p:cSld></p:notes>',
            )


class TestExtractText(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "extract_text.py"), *args],
            capture_output=True,
        )

    def test_docx_runs_are_joined_and_paragraphs_are_lines(self):
        path = self.dir / "a.docx"
        docx_bytes(
            path,
            '<w:p><w:r><w:t xml:space="preserve">We use </w:t></w:r><w:r><w:t>Pardot</w:t></w:r></w:p>'
            "<w:p><w:r><w:t>Second line</w:t></w:r></w:p>",
        )
        out = self.cli(str(path))
        self.assertEqual(out.returncode, 0, out.stderr.decode())
        self.assertEqual(out.stdout.decode("utf-8").splitlines(), ["We use Pardot", "Second line"])

    def test_docx_table_cells_and_breaks_are_included(self):
        path = self.dir / "t.docx"
        docx_bytes(
            path,
            "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Datorama</w:t></w:r></w:p></w:tc>"
            "<w:tc><w:p><w:r><w:t>cell two</w:t><w:br/><w:t>after break</w:t></w:r></w:p></w:tc></w:tr></w:tbl>",
        )
        text = self.cli(str(path)).stdout.decode("utf-8")
        self.assertIn("Datorama", text)
        self.assertIn("cell two", text)
        self.assertIn("after break", text)

    def test_pptx_slides_in_numeric_order_with_markers(self):
        path = self.dir / "d.pptx"
        pptx_file(
            path,
            {10: ["Tenth"], 2: ["Second slide", "Pardot reports"], 1: ["Title"]},
            notes={2: ["Speaker note"]},
        )
        lines = self.cli(str(path)).stdout.decode("utf-8").splitlines()
        self.assertEqual(
            lines,
            ["[slide 1]", "Title", "[slide 2]", "Second slide", "Pardot reports",
             "[slide 2 notes]", "Speaker note", "[slide 10]", "Tenth"],
        )

    def test_unsupported_extension_exits_2(self):
        path = self.dir / "x.txt"
        path.write_text("hello", encoding="utf-8")
        out = self.cli(str(path))
        self.assertEqual(out.returncode, 2)
        self.assertIn(b"supported", out.stderr)

    def test_corrupt_file_exits_1_without_traceback(self):
        path = self.dir / "bad.docx"
        path.write_bytes(b"this is not a zip")
        out = self.cli(str(path))
        self.assertEqual(out.returncode, 1)
        self.assertNotIn(b"Traceback", out.stderr)

    def test_output_pipes_into_the_scanner(self):
        path = self.dir / "p.docx"
        docx_bytes(path, "<w:p><w:r><w:t>intro</w:t></w:r></w:p><w:p><w:r><w:t>We use Pardot daily</w:t></w:r></w:p>")
        data = self.dir / "data.json"
        data.write_text(json.dumps(FIXTURE_DATA), encoding="utf-8")
        extracted = self.cli(str(path)).stdout
        scan = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "scan.py"), "--data", str(data), "-"],
            input=extracted,
            capture_output=True,
            check=True,
        )
        findings = json.loads(scan.stdout.decode("utf-8"))
        self.assertEqual([(f["line"], f["classification"]) for f in findings], [(2, "outdated")])


if __name__ == "__main__":
    unittest.main()
