"""Ensure the optional research preview never disguises itself as live production."""
import json
from pathlib import Path
import unittest

from engine import ASSETS


class PreviewTests(unittest.TestCase):
    def test_research_preview_is_explicitly_static_and_complete(self):
        payload = json.loads(Path("public/research-v2.json").read_text(encoding="utf-8"))
        self.assertTrue(payload["research"])
        self.assertFalse(payload["forecasts"])  # No unpublished model predictions in the live report history.
        self.assertEqual(set(payload["markets"]), set(ASSETS.values()))
        for market in payload["markets"].values():
            self.assertEqual(market["model_version"], "daily-ensemble-v3")
            self.assertEqual(len(market["metrics"]["improvement_ci"]), 2)
            self.assertIn("quality", market)


if __name__ == "__main__":
    unittest.main()
