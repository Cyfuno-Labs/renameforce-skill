import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import fixtures
from fixtures import FIXTURE_DATA, INDEX_PATH, SCRIPTS_DIR, SNAPSHOT_PATH

from build_index import build_names_index


def _entry(index, pid):
    return next(p for p in index["products"] if p["id"] == pid)


class TestBuildNamesIndex(unittest.TestCase):
    def test_past_names_exclude_current_entry(self):
        entry = _entry(build_names_index(FIXTURE_DATA), "account-engagement")
        self.assertEqual(
            entry["past_names"],
            [
                {"name": "Pardot", "ended": "2022-04"},
                {"name": "Marketing Cloud Account Engagement", "ended": "2023-03"},
            ],
        )
        self.assertEqual(entry["aliases"], ["MCAE"])
        self.assertEqual(entry["current_name"], "Account Engagement")

    def test_year_only_end_formats_as_year(self):
        entry = _entry(build_names_index(FIXTURE_DATA), "connect-a")
        self.assertEqual(entry["past_names"], [{"name": "Connect", "ended": "2020"}])

    def test_names_deduplicated(self):
        data = {
            "generated_at": "2026-10-10T00:00:00Z",
            "products": [
                {
                    "id": "p",
                    "current_name": "Baz",
                    "status": "active",
                    "aliases": [],
                    "timeline": [
                        {"name": "Foo", "start": {"y": 2000}, "end": {"y": 2005}},
                        {"name": "Bar", "start": {"y": 2005}, "end": {"y": 2008}},
                        {"name": "Foo", "start": {"y": 2008}, "end": {"y": 2010}},
                        {"name": "Baz", "start": {"y": 2010}, "end": None},
                    ],
                }
            ],
        }
        entry = _entry(build_names_index(data), "p")
        self.assertEqual(
            entry["past_names"],
            [{"name": "Bar", "ended": "2008"}, {"name": "Foo", "ended": "2010"}],
        )

    def test_name_equal_to_current_is_not_a_past_name(self):
        entry = _entry(build_names_index(FIXTURE_DATA), "sales-cloud")
        self.assertEqual(
            entry["past_names"], [{"name": "Agentforce Sales", "ended": "2026-09"}]
        )

    def test_generated_at_passed_through(self):
        self.assertEqual(
            build_names_index(FIXTURE_DATA)["generated_at"], "2026-10-10T00:00:00Z"
        )

    def test_legacy_aliases_in_index(self):
        entry = _entry(build_names_index(FIXTURE_DATA), "marketing-engagement")
        self.assertEqual(entry["legacy_aliases"], ["SFMC"])
        self.assertEqual(entry["aliases"], ["MCE"])

    def test_missing_legacy_aliases_is_empty_list(self):
        entry = _entry(build_names_index(FIXTURE_DATA), "account-engagement")
        self.assertEqual(entry["legacy_aliases"], [])

    def test_bad_alias_values_do_not_crash(self):
        data = {
            "generated_at": "2026-10-10T00:00:00Z",
            "products": [
                {
                    "id": "p",
                    "current_name": "Now",
                    "status": "active",
                    "aliases": None,
                    "legacy_aliases": [None, 7, "", " SFMC "],
                    "timeline": [{"name": "Now", "start": {"y": 2020}, "end": None}],
                },
                {
                    "id": "q",
                    "current_name": "Q",
                    "status": "active",
                    "aliases": "oops",
                    "legacy_aliases": None,
                    "timeline": [{"name": "Q", "start": {"y": 2020}, "end": None}],
                },
            ],
        }
        index = build_names_index(data)
        self.assertEqual(_entry(index, "p")["legacy_aliases"], ["SFMC"])
        self.assertEqual(_entry(index, "p")["aliases"], [])
        self.assertEqual(_entry(index, "q")["aliases"], [])
        self.assertEqual(_entry(index, "q")["legacy_aliases"], [])

    def test_cli_writes_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.json"
            out = Path(tmp) / "out.json"
            src.write_text(json.dumps(FIXTURE_DATA), encoding="utf-8")
            subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "build_index.py"), str(src), str(out)],
                check=True,
            )
            self.assertEqual(
                json.loads(out.read_text(encoding="utf-8")),
                build_names_index(FIXTURE_DATA),
            )

    def test_committed_index_matches_snapshot(self):
        snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        committed = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        self.assertEqual(committed, build_names_index(snapshot))


if __name__ == "__main__":
    unittest.main()
