#!/usr/bin/env python3
"""Find Salesforce product names in text and classify them against Renameforce data."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
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


@dataclass
class Index:
    pattern: Optional["re.Pattern[str]"]
    candidates: Dict[str, List[_Candidate]] = field(default_factory=dict)
    ambiguous_names: frozenset = frozenset()


def build_index(data: dict, ambiguous_names: Iterable[str] = ()) -> Index:
    candidates: Dict[str, List[_Candidate]] = {}

    def add(name: str, cand: _Candidate) -> None:
        bucket = candidates.setdefault(name.casefold(), [])
        for existing in bucket:
            if existing.product_id == cand.product_id:
                # Same product: current beats past beats alias; latest end wins among past.
                rank = {"current": 3, "past": 2, "alias": 1}
                if rank[cand.kind] > rank[existing.kind]:
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
        add(current, _Candidate(pid, current, "current"))
        for entry in product.get("timeline", []):
            end = entry.get("end")
            if end is None:
                continue
            add(entry["name"], _Candidate(pid, current, "past", end))
        for alias in product.get("aliases", []):
            add(alias, _Candidate(pid, current, "alias"))

    names = sorted((n for n in candidates if n.strip()), key=len, reverse=True)
    pattern = None
    if names:
        alternation = "|".join(re.escape(n) for n in names)
        pattern = re.compile(rf"(?<!\w)(?:{alternation})(?!\w)", re.IGNORECASE)
    return Index(
        pattern=pattern,
        candidates=candidates,
        ambiguous_names=frozenset(n.casefold() for n in ambiguous_names),
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
    if first.kind == "current":
        return first, "current", None, None
    if first.kind == "alias":
        return first, "current", None, f"alias of {first.current_name}"
    return first, "outdated", format_date(first.ended), None


def scan_text(
    text: str,
    index: Index,
    *,
    path: str = "<text>",
    include_code: bool = False,
) -> List[Finding]:
    if index.pattern is None or not text:
        return []
    line_starts = [0]
    for m in re.finditer(r"\n", text):
        line_starts.append(m.end())

    findings: List[Finding] = []
    for m in index.pattern.finditer(text):
        start = m.start()
        line_idx = _line_index(line_starts, start)
        cand, classification, changed_on, reason = _classify(m.group(0).casefold(), index)
        findings.append(
            Finding(
                path=path,
                line=line_idx + 1,
                column=start - line_starts[line_idx] + 1,
                matched=m.group(0),
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
