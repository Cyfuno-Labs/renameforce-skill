import copy
import http.client
import io
import json
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fixtures
from fixtures import FIXTURE_DATA

import get_data
from get_data import HttpResult, load_data

NOW = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
SNAP_STAMP = "2026-10-10T00:00:00Z"
OLDER = "2026-09-01T00:00:00Z"
NEWER = "2026-10-18T00:00:00Z"


def data_with(stamp):
    d = copy.deepcopy(FIXTURE_DATA)
    d["generated_at"] = stamp
    return d


def body(stamp):
    return json.dumps(data_with(stamp)).encode("utf-8")


class FakeFetch:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, etag):
        self.calls.append((url, etag))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.cache_dir = root / "cache"
        self.snapshot = root / "snapshot.json"
        self.snapshot.write_text(json.dumps(data_with(SNAP_STAMP)), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def seed_cache(self, stamp, fetched_at, etag="abc"):
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "renameforce-data.json").write_text(
            json.dumps(data_with(stamp)), encoding="utf-8"
        )
        (self.cache_dir / "meta.json").write_text(
            json.dumps(
                {"etag": etag, "fetched_at": fetched_at.isoformat(), "url": get_data.SOURCES[0]}
            ),
            encoding="utf-8",
        )

    def load(self, fetch, **kwargs):
        return load_data(
            cache_dir=self.cache_dir,
            fetch=fetch,
            snapshot_path=self.snapshot,
            now=lambda: NOW,
            **kwargs,
        )


class TestLoadData(Base):
    def test_fresh_cache_makes_no_request(self):
        self.seed_cache(NEWER, NOW - timedelta(days=1))
        fetch = FakeFetch()
        result = self.load(fetch)
        self.assertEqual(result.source, "cache")
        self.assertEqual(result.generated_at, NEWER)
        self.assertEqual(fetch.calls, [])

    def test_stale_cache_sends_etag_and_304_renews(self):
        self.seed_cache(NEWER, NOW - timedelta(days=10), etag="abc")
        fetch = FakeFetch(HttpResult(304, None, "abc"))
        result = self.load(fetch)
        self.assertEqual(result.source, "cache")
        self.assertEqual(fetch.calls, [(get_data.SOURCES[0], "abc")])
        meta = json.loads((self.cache_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(datetime.fromisoformat(meta["fetched_at"]), NOW)

    def test_200_writes_cache_and_returns_live(self):
        fetch = FakeFetch(HttpResult(200, body(NEWER), "e1"))
        result = self.load(fetch)
        self.assertEqual(result.source, "live")
        self.assertEqual(result.generated_at, NEWER)
        self.assertEqual(Path(result.path), self.cache_dir / "renameforce-data.json")
        meta = json.loads((self.cache_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["etag"], "e1")
        self.assertEqual(fetch.calls[0], (get_data.SOURCES[0], None))

    def test_first_source_fails_second_used(self):
        fetch = FakeFetch(OSError("boom"), HttpResult(200, body(NEWER), None))
        result = self.load(fetch)
        self.assertEqual(result.source, "live")
        self.assertEqual([c[0] for c in fetch.calls], list(get_data.SOURCES))

    def test_all_sources_fail_uses_snapshot_with_note(self):
        fetch = FakeFetch(OSError("a"), OSError("b"))
        result = self.load(fetch)
        self.assertEqual(result.source, "snapshot")
        self.assertEqual(Path(result.path), self.snapshot)
        self.assertTrue(result.notes)

    def test_all_sources_fail_uses_stale_cache_when_newer_than_snapshot(self):
        self.seed_cache(NEWER, NOW - timedelta(days=30))
        result = self.load(FakeFetch(OSError("a"), OSError("b")))
        self.assertEqual(result.source, "cache")
        self.assertTrue(any("stale" in n for n in result.notes))

    def test_cache_older_than_snapshot_ignored(self):
        self.seed_cache(OLDER, NOW - timedelta(days=1))
        fetch = FakeFetch(OSError("a"), OSError("b"))
        result = self.load(fetch)
        self.assertEqual(result.source, "snapshot")
        self.assertEqual(len(fetch.calls), 2)

    def test_refresh_bypasses_ttl(self):
        self.seed_cache(NEWER, NOW - timedelta(days=1), etag="abc")
        fetch = FakeFetch(HttpResult(304, None, "abc"))
        result = self.load(fetch, refresh=True)
        self.assertEqual(result.source, "cache")
        self.assertEqual(len(fetch.calls), 1)

    def test_malformed_remote_body_falls_back(self):
        bad = HttpResult(200, b'{"nope": 1}', None)
        result = self.load(FakeFetch(bad, bad))
        self.assertEqual(result.source, "snapshot")
        self.assertTrue(any("invalid" in n for n in result.notes))

    def test_remote_older_than_snapshot_not_used(self):
        old = HttpResult(200, body(OLDER), None)
        result = self.load(FakeFetch(old, old))
        self.assertEqual(result.source, "snapshot")

    def test_unwritable_cache_dir_still_returns_data(self):
        blocker = Path(self.tmp.name) / "not-a-dir"
        blocker.write_text("x", encoding="utf-8")
        result = load_data(
            cache_dir=blocker,
            fetch=FakeFetch(HttpResult(200, body(NEWER), None)),
            snapshot_path=self.snapshot,
            now=lambda: NOW,
        )
        self.assertEqual(result.source, "live")
        self.assertEqual(result.generated_at, NEWER)
        self.assertTrue(Path(result.path).exists())
        self.assertTrue(any("cache" in n for n in result.notes))

    def test_corrupt_meta_json_ignored(self):
        self.seed_cache(NEWER, NOW - timedelta(days=1))
        (self.cache_dir / "meta.json").write_bytes(b"\x00\x01 not json")
        fetch = FakeFetch(HttpResult(200, body(NEWER), "z"))
        result = self.load(fetch)
        self.assertEqual(result.source, "live")
        self.assertEqual(fetch.calls[0][1], None)

    def test_corrupt_cache_file_ignored(self):
        self.seed_cache(NEWER, NOW - timedelta(days=1))
        (self.cache_dir / "renameforce-data.json").write_bytes(b"\xff\xfe garbage")
        fetch = FakeFetch(HttpResult(200, body(NEWER), "z"))
        result = self.load(fetch)
        self.assertEqual(result.source, "live")


class TestHardening(Base):
    """Cases found in review: bad metadata, odd network errors, shallow validation."""

    def test_unsafe_etag_is_not_sent(self):
        for bad in ("a" + chr(10) + "b", "tab" + chr(9) + "bed", {"x": 1}, 7, ""):
            self.seed_cache(NEWER, NOW - timedelta(days=10))
            meta_path = self.cache_dir / "meta.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["etag"] = bad
            meta_path.write_text(json.dumps(meta), encoding="utf-8")
            fetch = FakeFetch(HttpResult(200, body(NEWER), "z"))
            self.load(fetch)
            self.assertIsNone(fetch.calls[0][1], repr(bad))

    def test_http_get_wraps_http_client_errors(self):
        with mock.patch("urllib.request.urlopen", side_effect=http.client.IncompleteRead(b"x")):
            with self.assertRaises(OSError):
                get_data.http_get("https://example.com/x", None)

    def test_cached_data_with_malformed_products_is_ignored(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        bad = {"version": 1, "generated_at": NEWER, "products": [{"id": 1}]}
        (self.cache_dir / "renameforce-data.json").write_text(json.dumps(bad), encoding="utf-8")
        (self.cache_dir / "meta.json").write_text(
            json.dumps({"etag": "e", "fetched_at": (NOW - timedelta(days=1)).isoformat()}),
            encoding="utf-8",
        )
        fetch = FakeFetch(HttpResult(200, body(NEWER), "z"))
        result = self.load(fetch)
        self.assertEqual(result.source, "live")
        self.assertEqual(len(fetch.calls), 1)

    def test_remote_with_malformed_products_falls_back(self):
        bad = json.dumps(
            {"generated_at": NEWER, "products": [{"id": "x", "timeline": "nope"}]}
        ).encode("utf-8")
        result = self.load(FakeFetch(HttpResult(200, bad, None), HttpResult(200, bad, None)))
        self.assertEqual(result.source, "snapshot")
        self.assertTrue(any("invalid" in n for n in result.notes))

    def test_unwritable_cache_reuses_one_temp_file(self):
        blocker = Path(self.tmp.name) / "not-a-dir"
        blocker.write_text("x", encoding="utf-8")
        scratch = Path(self.tmp.name) / "tmp"
        scratch.mkdir()
        with mock.patch("tempfile.gettempdir", return_value=str(scratch)):
            paths = []
            for _ in range(3):
                result = load_data(
                    cache_dir=blocker,
                    fetch=FakeFetch(HttpResult(200, body(NEWER), None)),
                    snapshot_path=self.snapshot,
                    now=lambda: NOW,
                )
                paths.append(result.path)
        self.assertEqual(len(set(paths)), 1)
        self.assertEqual(len(list(scratch.iterdir())), 1)

    def test_future_fetched_at_is_not_treated_as_fresh(self):
        self.seed_cache(NEWER, NOW + timedelta(days=30), etag="abc")
        fetch = FakeFetch(HttpResult(304, None, "abc"))
        result = self.load(fetch)
        self.assertEqual(len(fetch.calls), 1)
        self.assertEqual(result.source, "cache")

    def test_parse_iso_accepts_fractional_seconds_and_rejects_junk(self):
        parsed = get_data._parse_iso("2026-10-10T00:00:00.5Z")
        self.assertEqual(parsed, datetime(2026, 10, 10, 0, 0, 0, 500000, tzinfo=timezone.utc))
        long_fraction = get_data._parse_iso("2026-10-10T00:00:00.123456789Z")
        self.assertEqual(long_fraction.microsecond, 123456)
        self.assertIsNone(get_data._parse_iso("yesterday"))
        self.assertIsNone(get_data._parse_iso(None))


class TestMain(Base):
    def test_cli_prints_summary_json(self):
        out = io.StringIO()
        code = get_data.main(
            ["--ttl-days", "7"],
            fetch=FakeFetch(HttpResult(200, body(NEWER), "e")),
            out=out,
            cache_dir=self.cache_dir,
            snapshot_path=self.snapshot,
            now=lambda: NOW,
        )
        self.assertEqual(code, 0)
        summary = json.loads(out.getvalue())
        self.assertEqual(summary["source"], "live")
        self.assertEqual(summary["generated_at"], NEWER)
        self.assertTrue(Path(summary["path"]).exists())
        self.assertIsInstance(summary["notes"], list)


if __name__ == "__main__":
    unittest.main()
