"""Shared test fixtures. Importing this module also puts the skill scripts on sys.path."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "renameforce" / "scripts"
DATA_DIR = ROOT / "renameforce" / "data"
SNAPSHOT_PATH = DATA_DIR / "renameforce-data.json"
INDEX_PATH = DATA_DIR / "names-index.json"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _d(y, m=None):
    return {"y": y} if m is None else {"y": y, "m": m}


def _product(pid, current, timeline, aliases=(), status="active"):
    return {
        "id": pid,
        "category": "Test",
        "vendor_origin": "Salesforce",
        "aliases": list(aliases),
        "status": status,
        "notes": "",
        "timeline": [{"name": n, "start": s, "end": e} for n, s, e in timeline],
        "current_name": current,
        "first_used": timeline[0][1],
        "last_updated": _d(2026, 9),
    }


FIXTURE_DATA = {
    "version": 1,
    "generated_at": "2026-10-10T00:00:00Z",
    "products": [
        _product(
            "account-engagement",
            "Account Engagement",
            [
                ("Pardot", _d(2007), _d(2022, 4)),
                ("Marketing Cloud Account Engagement", _d(2022, 4), _d(2023, 3)),
                ("Account Engagement", _d(2023, 3), None),
            ],
            aliases=["MCAE"],
        ),
        _product(
            "sales-cloud",
            "Sales Cloud",
            [
                ("Sales Cloud", _d(2015), _d(2025, 10)),
                ("Agentforce Sales", _d(2025, 10), _d(2026, 9)),
                ("Sales Cloud", _d(2026, 9), None),
            ],
        ),
        _product(
            "core-edition",
            "Core Edition",
            [
                ("Enterprise Edition", _d(2000), _d(2026, 9)),
                ("Core Edition", _d(2026, 9), None),
            ],
        ),
        _product(
            "connect-a",
            "Alpha Hub",
            [("Connect", _d(2010), _d(2020)), ("Alpha Hub", _d(2020), None)],
        ),
        _product(
            "retired-studio",
            "Retired Studio",
            [
                ("Old Studio", _d(2006), _d(2012)),
                ("Retired Studio", _d(2014), _d(2024, 11)),
            ],
            status="deprecated",
        ),
        _product(
            "connect-b",
            "Beta Hub",
            [("Connect", _d(2012), _d(2021, 6)), ("Beta Hub", _d(2021, 6), None)],
        ),
    ],
}
