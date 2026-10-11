#!/usr/bin/env python3
"""Extract plain text from a .docx or .pptx so it can be scanned.

Usage: python extract_text.py FILE.docx|FILE.pptx
Prints UTF-8 text: one paragraph per line; slides are introduced by "[slide N]" lines
(speaker notes by "[slide N notes]"). Pipe it into scan.py:

    python extract_text.py deck.pptx | python scan.py --data <path> -

Exit codes: 0 ok, 1 unreadable or corrupt file, 2 unsupported file type.
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Iterable, List

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_MAX_MEMBER_BYTES = 50 * 1024 * 1024  # refuse zip bombs


def _read_member(archive: zipfile.ZipFile, name: str) -> ET.Element:
    info = archive.getinfo(name)
    if info.file_size > _MAX_MEMBER_BYTES:
        raise ValueError(f"{name} is too large to read safely")
    return ET.fromstring(archive.read(name))


def _paragraphs(root: ET.Element, ns: str, para_tag: str, text_tag: str) -> List[str]:
    """One string per paragraph: text runs joined, <br> as a line break, <tab> as a space."""
    lines: List[str] = []
    for para in root.iter(ns + para_tag):
        parts: List[str] = []
        for node in para.iter():
            if node.tag == ns + text_tag and node.text:
                parts.append(node.text)
            elif node.tag in (ns + "br", ns + "cr"):
                parts.append("\n")
            elif node.tag == ns + "tab":
                parts.append(" ")
        text = "".join(parts)
        lines.extend(text.split("\n"))
    return [line for line in lines if line.strip()]


def _numbered(names: Iterable[str], prefix: str) -> List[tuple]:
    found = []
    for name in names:
        m = re.fullmatch(re.escape(prefix) + r"(\d+)\.xml", name)
        if m:
            found.append((int(m.group(1)), name))
    return sorted(found)


def extract_docx(archive: zipfile.ZipFile) -> List[str]:
    lines: List[str] = []
    names = archive.namelist()
    ordered = ["word/document.xml"]
    ordered += sorted(n for n in names if re.fullmatch(r"word/(header|footer)\d*\.xml", n))
    ordered += [n for n in ("word/footnotes.xml", "word/endnotes.xml") if n in names]
    for name in ordered:
        if name not in names:
            continue
        lines.extend(_paragraphs(_read_member(archive, name), W, "p", "t"))
    return lines


def extract_pptx(archive: zipfile.ZipFile) -> List[str]:
    names = archive.namelist()
    notes = dict(_numbered(names, "ppt/notesSlides/notesSlide"))
    lines: List[str] = []
    for number, name in _numbered(names, "ppt/slides/slide"):
        lines.append(f"[slide {number}]")
        lines.extend(_paragraphs(_read_member(archive, name), A, "p", "t"))
        # notesSlide numbering normally matches the slide file number.
        note_name = notes.get(number)
        if note_name:
            note_lines = _paragraphs(_read_member(archive, note_name), A, "p", "t")
            if note_lines:
                lines.append(f"[slide {number} notes]")
                lines.extend(note_lines)
    return lines


def extract_text(path: str) -> str:
    suffix = Path(path).suffix.lower()
    with zipfile.ZipFile(path) as archive:
        if suffix == ".docx":
            lines = extract_docx(archive)
        elif suffix == ".pptx":
            lines = extract_pptx(archive)
        else:
            raise TypeError(suffix)
    return "\n".join(lines) + ("\n" if lines else "")


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("usage: extract_text.py FILE.docx|FILE.pptx", file=sys.stderr)
        return 2
    path = argv[1]
    if Path(path).suffix.lower() not in (".docx", ".pptx"):
        print("only .docx and .pptx files are supported", file=sys.stderr)
        return 2
    try:
        text = extract_text(path)
    except (OSError, zipfile.BadZipFile, ET.ParseError, ValueError, KeyError) as exc:
        print(f"could not read {path}: {exc}", file=sys.stderr)
        return 1
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
