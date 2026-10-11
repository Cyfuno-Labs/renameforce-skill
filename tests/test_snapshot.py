import json
import unittest
from pathlib import Path

SNAPSHOT = Path(__file__).resolve().parent.parent / "renameforce" / "data" / "renameforce-data.json"


class TestSnapshot(unittest.TestCase):
    def test_snapshot_is_valid(self):
        data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        self.assertIsInstance(data["generated_at"], str)
        self.assertGreater(len(data["products"]), 0)
        for product in data["products"]:
            self.assertIn("id", product)
            self.assertIn("current_name", product)
            self.assertTrue(product["timeline"], product.get("id"))


if __name__ == "__main__":
    unittest.main()
