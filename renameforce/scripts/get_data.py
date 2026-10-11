#!/usr/bin/env python3
"""Resolve Renameforce data: fresh cache, conditional live fetch, or bundled snapshot.

Usage: python get_data.py [--refresh] [--ttl-days N]
Prints {"source", "generated_at", "path", "notes"} as JSON. `path` is the file to
pass to scan.py --data.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, List, Optional

SOURCES = (
    "https://cdn.jsdelivr.net/gh/Cyfuno-Labs/renameforce-skill@main/renameforce/data/renameforce-data.json",
    "https://renameforce.com/renameforce-data.json",
)
SNAPSHOT = Path(__file__).resolve().parent.parent / "data" / "renameforce-data.json"
DEFAULT_TTL_DAYS = 7
CACHE_FILE = "renameforce-data.json"
META_FILE = "meta.json"
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass
class HttpResult:
    status: int
    body: Optional[bytes]
    etag: Optional[str]


@dataclass
class DataResult:
    data: dict
    source: str  # "cache" | "live" | "snapshot"
    generated_at: str
    path: str
    notes: List[str] = field(default_factory=list)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def http_get(url: str, etag: Optional[str]) -> HttpResult:
    """GET url (10 s timeout), sending If-None-Match when an ETag is known."""
    request = urllib.request.Request(url, headers={"User-Agent": "renameforce-skill"})
    if etag:
        request.add_header("If-None-Match", etag)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return HttpResult(response.status, response.read(), response.headers.get("ETag"))
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return HttpResult(304, None, etag)
        return HttpResult(exc.code, None, None)
    except (urllib.error.URLError, TimeoutError, http.client.HTTPException) as exc:
        raise OSError(f"{type(exc).__name__}: {exc}") from exc


def default_cache_dir() -> Path:
    override = os.environ.get("RENAMEFORCE_CACHE_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Caches")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "renameforce"


def _valid_product(product: object) -> bool:
    """Enough structure that build_index/scan can use the product without crashing."""
    if not isinstance(product, dict):
        return False
    for key in ("id", "current_name"):
        if not isinstance(product.get(key), str) or not product[key].strip():
            return False
    timeline = product.get("timeline")
    if not isinstance(timeline, list):
        return False
    for entry in timeline:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            return False
        end = entry.get("end")
        if end is not None and not (isinstance(end, dict) and isinstance(end.get("y"), int)):
            return False
    return True


def _is_valid(data: object) -> bool:
    return (
        isinstance(data, dict)
        and isinstance(data.get("generated_at"), str)
        and isinstance(data.get("products"), list)
        and len(data["products"]) > 0
        and all(_valid_product(p) for p in data["products"])
    )


_FRACTION = re.compile(r"\.(\d+)")


def _parse_iso(text: object) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp (Python 3.9-safe fractional seconds); None if invalid."""
    if not isinstance(text, str):
        return None
    normalized = text.strip().replace("Z", "+00:00")
    normalized = _FRACTION.sub(lambda m: "." + m.group(1).ljust(6, "0")[:6], normalized, count=1)
    try:
        value = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _clean_etag(value: object) -> Optional[str]:
    """An ETag safe to send as a header value, else None."""
    if not isinstance(value, str) or not value or len(value) > 256:
        return None
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        return None
    return value


def _stamp(data: dict) -> datetime:
    return _parse_iso(data.get("generated_at")) or _EPOCH


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _write_atomic(path: Path, payload: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_cache(cache_dir: Path):
    """Return (data, meta) for a valid cache, else (None, {})."""
    data = _read_json(cache_dir / CACHE_FILE)
    if not _is_valid(data):
        return None, {}
    meta = _read_json(cache_dir / META_FILE)
    return data, meta if isinstance(meta, dict) else {}


def _fetched_at(meta: dict) -> datetime:
    return _parse_iso(meta.get("fetched_at")) or _EPOCH


def load_data(
    *,
    cache_dir: Optional[Path] = None,
    ttl_days: int = DEFAULT_TTL_DAYS,
    refresh: bool = False,
    fetch: Callable[[str, Optional[str]], HttpResult] = http_get,
    snapshot_path: Path = SNAPSHOT,
    now: Callable[[], datetime] = utcnow,
) -> DataResult:
    notes: List[str] = []
    snapshot = _read_json(snapshot_path)
    if not _is_valid(snapshot):
        raise RuntimeError(f"bundled snapshot is missing or invalid: {snapshot_path}")
    snapshot_stamp = _stamp(snapshot)

    cache_dir = Path(cache_dir) if cache_dir is not None else default_cache_dir()
    cached, meta = _read_cache(cache_dir)
    if cached is not None and _stamp(cached) < snapshot_stamp:
        notes.append("cache is older than the bundled snapshot; ignored")
        cached, meta = None, {}

    current_time = now()
    cache_path = cache_dir / CACHE_FILE
    if cached is not None and not refresh:
        age = current_time - _fetched_at(meta)
        # A negative age (clock skew, or a bad timestamp) is not trusted as fresh.
        if timedelta(0) <= age < timedelta(days=ttl_days):
            return DataResult(cached, "cache", cached["generated_at"], str(cache_path), notes)

    etag = _clean_etag(meta.get("etag")) if cached is not None else None
    for url in SOURCES:
        try:
            response = fetch(url, etag)
        except OSError as exc:
            notes.append(f"{url}: {exc}")
            continue
        if response.status == 304 and cached is not None:
            _try_write_meta(cache_dir, etag, current_time, url, notes)
            return DataResult(cached, "cache", cached["generated_at"], str(cache_path), notes)
        if response.status != 200 or response.body is None:
            notes.append(f"{url}: HTTP {response.status}")
            continue
        try:
            fresh = json.loads(response.body.decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError):
            fresh = None
        if not _is_valid(fresh):
            notes.append(f"{url}: response was invalid; ignored")
            continue
        if _stamp(fresh) < snapshot_stamp:
            notes.append(f"{url}: data is older than the bundled snapshot; ignored")
            continue
        path = _persist(cache_dir, response.body, response.etag, current_time, url, notes)
        if path is None:
            notes.append("could not store the fetched data anywhere; using the bundled snapshot")
            break
        return DataResult(fresh, "live", fresh["generated_at"], str(path), notes)

    # Every source failed: the newer of the stale cache and the snapshot wins.
    if cached is not None and _stamp(cached) >= snapshot_stamp:
        notes.append("using stale cache because no source could be reached")
        return DataResult(cached, "cache", cached["generated_at"], str(cache_path), notes)
    notes.append("using the bundled snapshot")
    return DataResult(snapshot, "snapshot", snapshot["generated_at"], str(snapshot_path), notes)


def _meta_payload(etag: Optional[str], fetched_at: datetime, url: str) -> bytes:
    return json.dumps({"etag": etag, "fetched_at": fetched_at.isoformat(), "url": url}).encode("utf-8")


def _try_write_meta(cache_dir: Path, etag, fetched_at: datetime, url: str, notes: List[str]) -> None:
    try:
        _write_atomic(cache_dir / META_FILE, _meta_payload(etag, fetched_at, url))
    except OSError as exc:
        notes.append(f"cache metadata not updated: {exc}")


def _persist(cache_dir: Path, payload: bytes, etag, fetched_at, url, notes: List[str]) -> Optional[Path]:
    """Store fetched data in the cache dir (or a temp file); return its path or None."""
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        _write_atomic(cache_dir / CACHE_FILE, payload)
        _write_atomic(cache_dir / META_FILE, _meta_payload(etag, fetched_at, url))
        return cache_dir / CACHE_FILE
    except OSError as exc:
        notes.append(f"cache not writable ({exc}); used a temporary file")
    # One fixed file, overwritten each run, so an unwritable cache does not litter the temp dir.
    try:
        target = Path(tempfile.gettempdir()) / "renameforce-data-cache.json"
        _write_atomic(target, payload)
        return target
    except OSError:
        return None


def main(
    argv: Optional[List[str]] = None,
    *,
    fetch: Callable[[str, Optional[str]], HttpResult] = http_get,
    out=None,
    cache_dir: Optional[Path] = None,
    snapshot_path: Path = SNAPSHOT,
    now: Callable[[], datetime] = utcnow,
) -> int:
    parser = argparse.ArgumentParser(description="Resolve Renameforce data (cache, live, snapshot).")
    parser.add_argument("--refresh", action="store_true", help="ignore the cache TTL and fetch now")
    parser.add_argument("--ttl-days", type=int, default=DEFAULT_TTL_DAYS)
    args = parser.parse_args(argv)

    result = load_data(
        cache_dir=cache_dir,
        ttl_days=args.ttl_days,
        refresh=args.refresh,
        fetch=fetch,
        snapshot_path=snapshot_path,
        now=now,
    )
    summary = {
        "source": result.source,
        "generated_at": result.generated_at,
        "path": result.path,
        "notes": result.notes,
    }
    stream = out if out is not None else sys.stdout
    if out is None and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")
    json.dump(summary, stream, indent=2, ensure_ascii=False)
    stream.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
