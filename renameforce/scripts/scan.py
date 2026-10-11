#!/usr/bin/env python3
"""Find Salesforce product names in text and classify them against Renameforce data.

Usage: python scan.py [--data PATH] [--include-code] FILE...   (use - for stdin)
Prints a JSON array of findings to stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from build_index import date_sort_key, format_date


@dataclass
class Finding:
    path: str
    line: int
    column: int
    matched: str
    product_id: str
    classification: str  # "current" | "outdated" | "ambiguous"
    current_name: str
    changed_on: Optional[str] = None
    reason: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class _Candidate:
    product_id: str
    current_name: str
    kind: str  # "current" | "past" | "alias"
    ended: Optional[dict] = None
    status: Optional[str] = None


@dataclass
class Index:
    pattern: Optional["re.Pattern[str]"]
    candidates: Dict[str, List[_Candidate]] = field(default_factory=dict)
    ambiguous_names: frozenset = frozenset()


_KIND_RANK = {"current": 3, "past": 2, "alias": 1}


def _normalize(text: str) -> str:
    """Collapse any whitespace run (newlines, NBSP, double spaces) and case-fold."""
    return " ".join(text.split()).casefold()


def build_index(data: dict, ambiguous_names: Iterable[str] = ()) -> Index:
    candidates: Dict[str, List[_Candidate]] = {}

    def add(name: str, cand: _Candidate) -> None:
        bucket = candidates.setdefault(_normalize(name), [])
        for existing in bucket:
            if existing.product_id != cand.product_id:
                continue
            # Same product: current beats past beats alias; latest end wins among past.
            if _KIND_RANK[cand.kind] > _KIND_RANK[existing.kind]:
                existing.kind, existing.ended = cand.kind, cand.ended
            elif (
                cand.kind == "past"
                and existing.kind == "past"
                and date_sort_key(cand.ended) > date_sort_key(existing.ended)
            ):
                existing.ended = cand.ended
            return
        bucket.append(cand)

    for product in data["products"]:
        pid, current = product["id"], product["current_name"]
        status = product.get("status")
        add(current, _Candidate(pid, current, "current", status=status))
        for entry in product.get("timeline", []):
            end = entry.get("end")
            if end is None:
                continue
            add(entry["name"], _Candidate(pid, current, "past", end, status))
        for alias in product.get("aliases", []):
            add(alias, _Candidate(pid, current, "alias", status=status))

    names = sorted((n for n in candidates if n.strip()), key=len, reverse=True)
    pattern = None
    if names:
        # Words are joined with \s+ so names split by a line break, NBSP, or extra
        # spaces still match.
        alternation = "|".join(r"\s+".join(re.escape(w) for w in n.split()) for n in names)
        pattern = re.compile(rf"(?<!\w)(?:{alternation})(?!\w)", re.IGNORECASE)
    return Index(
        pattern=pattern,
        candidates=candidates,
        ambiguous_names=frozenset(_normalize(n) for n in ambiguous_names),
    )


def _classify(key: str, index: Index) -> Tuple[_Candidate, str, Optional[str], Optional[str]]:
    """Return (candidate, classification, changed_on, reason) for a matched name key."""
    cands = index.candidates[key]
    first = cands[0]
    if len(cands) > 1:
        ids = ", ".join(c.product_id for c in cands)
        return first, "ambiguous", None, f"name is used by multiple products: {ids}"
    if key in index.ambiguous_names:
        return first, "ambiguous", None, "generic term that may not refer to this product"
    if first.status == "deprecated":
        return (
            first,
            "ambiguous",
            None,
            f"retired product ({first.current_name}); there is no current replacement name",
        )
    if first.kind == "current":
        return first, "current", None, None
    if first.kind == "alias":
        return first, "current", None, f"alias of {first.current_name}"
    return first, "outdated", format_date(first.ended), None


# --- skipped regions -------------------------------------------------------

_FENCE = re.compile(r"^[ \t]{0,3}(```|~~~)")
_INLINE_CODE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"')\]]+", re.IGNORECASE)
_PATH = re.compile(
    r"(?<![\w/\\.:-])"
    r"(?:(?:[A-Za-z]:[\\/]|\.{1,2}[\\/]|~[\\/]|/(?=[\w.]))[^\s\"'<>|`]+"
    r"|[\w.-]+(?:[\\/][\w.-]+)+\.\w{1,5}(?!\w))"
)


def _blank(chars: List[str], start: int, end: int) -> None:
    for i in range(start, end):
        if chars[i] not in "\r\n":
            chars[i] = " "


def _mask_regions(text: str) -> str:
    """Blank out code, URLs and paths with spaces, keeping offsets and newlines."""
    chars = list(text)
    # Fenced code blocks, line by line (an unclosed fence runs to end of text).
    offset, open_marker, fence_start = 0, None, 0
    for raw in text.splitlines(keepends=True):
        line = raw.rstrip("\r\n")
        m = _FENCE.match(line)
        if open_marker is None:
            if m:
                open_marker, fence_start = m.group(1), offset
        elif m and m.group(1) == open_marker:
            _blank(chars, fence_start, offset + len(line))
            open_marker = None
        offset += len(raw)
    if open_marker is not None:
        _blank(chars, fence_start, len(text))
    masked = "".join(chars)
    for pattern in (_INLINE_CODE, _URL, _PATH):
        for m in pattern.finditer(masked):
            _blank(chars, m.start(), m.end())
        masked = "".join(chars)
    return masked


# --- scanning --------------------------------------------------------------


def scan_text(
    text: str,
    index: Index,
    *,
    path: str = "<text>",
    include_code: bool = False,
) -> List[Finding]:
    if index.pattern is None or not text:
        return []
    line_starts = [0] + [m.end() for m in re.finditer(r"\n", text)]
    searchable = text if include_code else _mask_regions(text)

    findings: List[Finding] = []
    for m in index.pattern.finditer(searchable):
        start = m.start()
        line_idx = _line_index(line_starts, start)
        key = _normalize(m.group(0))
        if key not in index.candidates:
            # re.IGNORECASE can match text whose case-fold differs (e.g. Turkish dotted I).
            key = " ".join(m.group(0).split()).lower()
            if key not in index.candidates:
                continue
        cand, classification, changed_on, reason = _classify(key, index)
        findings.append(
            Finding(
                path=path,
                line=line_idx + 1,
                column=start - line_starts[line_idx] + 1,
                matched=text[start : m.end()],
                product_id=cand.product_id,
                classification=classification,
                current_name=cand.current_name,
                changed_on=changed_on,
                reason=reason,
            )
        )
    return findings


def _line_index(line_starts: List[int], offset: int) -> int:
    lo, hi = 0, len(line_starts) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if line_starts[mid] <= offset:
            lo = mid
        else:
            hi = mid - 1
    return lo


# --- CLI -------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_ambiguous_names() -> List[str]:
    try:
        raw = json.loads((_DATA_DIR / "ambiguous-names.json").read_text(encoding="utf-8"))
        return [str(n) for n in raw.get("names", [])]
    except (OSError, ValueError):
        return []


def _scan_source(label: str, raw: bytes, index: Index, include_code: bool) -> list:
    if b"\x00" in raw:
        return [{"path": label, "skipped": "binary file"}]
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [{"path": label, "skipped": "not valid UTF-8 text"}]
    return [f.to_dict() for f in scan_text(text, index, path=label, include_code=include_code)]


_TEXT_EXTENSIONS = {
    ".md", ".markdown", ".mdx", ".txt", ".rst", ".adoc", ".html", ".htm", ".csv",
}
_SKIP_DIRS = {"node_modules", "__pycache__"}


def _expand(name: str) -> List[str]:
    """A directory becomes its text files (sorted); anything else is passed through."""
    root = Path(name)
    if not root.is_dir():
        return [name]
    found: List[str] = []
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in _SKIP_DIRS)
        for filename in sorted(files):
            if Path(filename).suffix.lower() in _TEXT_EXTENSIONS:
                found.append(str(Path(current) / filename))
    return found


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Scan files for Salesforce product names.")
    parser.add_argument("--data", default=str(_DATA_DIR / "renameforce-data.json"))
    parser.add_argument("--include-code", action="store_true")
    parser.add_argument("files", nargs="+", help="files to scan, or - for stdin")
    args = parser.parse_args(argv)

    data = json.loads(Path(args.data).read_text(encoding="utf-8-sig"))
    index = build_index(data, ambiguous_names=_load_ambiguous_names())
    results: list = []
    targets: List[str] = []
    for name in args.files:
        targets.extend([name] if name == "-" else _expand(name))
    for name in targets:
        if name == "-":
            raw = sys.stdin.buffer.read()
            results.extend(_scan_source("<stdin>", raw, index, args.include_code))
            continue
        try:
            raw = Path(name).read_bytes()
        except OSError as exc:
            results.append({"path": name, "skipped": f"unreadable: {exc.strerror or exc}"})
            continue
        results.extend(_scan_source(name, raw, index, args.include_code))

    sys.stdout.reconfigure(encoding="utf-8")
    json.dump(results, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
