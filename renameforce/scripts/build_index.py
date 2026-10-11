#!/usr/bin/env python3
"""Build the compact names index from the full Renameforce data file.

Usage: python build_index.py <data.json> <out.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _format_date(date: dict) -> str:
    year = date["y"]
    month = date.get("m")
    return f"{year}" if month is None else f"{year}-{month:02d}"


def _sort_key(date: dict) -> tuple:
    return (date["y"], date.get("m") or 0)


def build_names_index(data: dict) -> dict:
    products = []
    for product in data["products"]:
        current = product["current_name"]
        latest_end: dict = {}
        for entry in product.get("timeline", []):
            end = entry.get("end")
            if end is None or entry["name"].casefold() == current.casefold():
                continue
            key = entry["name"].casefold()
            if key not in latest_end or _sort_key(end) > _sort_key(latest_end[key][1]):
                latest_end[key] = (entry["name"], end)
        past = sorted(latest_end.values(), key=lambda item: _sort_key(item[1]))
        products.append(
            {
                "id": product["id"],
                "current_name": current,
                "status": product.get("status"),
                "aliases": list(product.get("aliases", [])),
                "past_names": [
                    {"name": name, "ended": _format_date(end)} for name, end in past
                ],
            }
        )
    return {"generated_at": data["generated_at"], "products": products}


def main(argv: list) -> int:
    if len(argv) != 3:
        print("usage: build_index.py <data.json> <out.json>", file=sys.stderr)
        return 2
    data = json.loads(Path(argv[1]).read_text(encoding="utf-8-sig"))
    index = build_names_index(data)
    Path(argv[2]).write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
