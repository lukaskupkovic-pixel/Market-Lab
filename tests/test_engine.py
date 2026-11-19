"""Offline tests: deterministic input, no third-party market API needed."""
import unittest

import numpy as np
import pandas as pd

from engine import (
    analyze, empirical_seven_day_range, features, independent_indices, labels,
    market_regime, validate_history,
)


def candles(n=900):
    rng = np.random.default_rng(14)
    dates = pd.bdate_range("2021-01-01", periods=n)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, n)))
    return pd.DataFrame({
        "Open": close * .999, "High": close * 1.012,
        "Low": close * .987, "Close": close, "Volume": 1000 + rng.integers(0, 500, n),
    }, index=dates)


class EngineTests(unittest.TestCase):
    def test_labels_use_first_close_on_or_after_calendar_day_seven(self):
        df = candles(50)
        y, ends = labels(df)
        self.assertEqual(ends.iloc[0], df.index[5])  # Friday -> next Friday.
        self.assertEqual(y.iloc[0], float(df.Close.iloc[5] > df.Close.iloc[0]))
        self.assertTrue(pd.isna(y.iloc[-1]))

    def test_quality_requires_mature_history_and_fresh_complete_bars(self):
        df = candles()
        quality = validate_history(df, "SI=F", today=df.index[-1] + pd.Timedelta(days=1))
        self.assertEqual(quality["bars"], len(df))
        bad = df.copy()
        bad.loc[bad.index[-1], "High"] = bad.Close.iloc[-1] * .8
        with self.assertRaisesRegex(ValueError, "OHLC"):
            validate_history(bad, "SI=F", today=bad.index[-1])
        with self.assertRaisesRegex(ValueError, "Neaktuální"):
            validate_history(df, "SI=F", today=df.index[-1] + pd.Timedelta(days=10))

    def test_rollover_history_can_have_negative_futures_prices(self):
        df = candles()
        df.loc[df.index[5], ["Open", "High", "Low", "Close"]] = [-35, -33, -37, -35]
        validate_history(df, "CL=F", today=df.index[-1] + pd.Timedelta(days=1))

    def test_independent_outcomes_and_cutoff(self):
        df = candles(80)
        _, ends = labels(df)
        dates = df.index[:-10]
        selected = independent_indices(dates, ends, 0, len(dates), known_before=df.index[60])
        self.assertGreater(len(selected), 2)
        for prior, later in zip(selected[:-1], selected[1:]):
            self.assertGreater(dates[later], ends.iloc[prior])
        self.assertLess(ends.iloc[selected[-1]], df.index[60])

    def test_full_walk_forward_has_distinct_validation_and_test(self):
        df = candles()
        analysis = analyze(df)
        b = analysis["metrics"]
        self.assertIn(b["selected_model"], ["linear", "boosted", "blend"])
        self.assertGreater(b["test_count"], 10)
        self.assertTrue(0 <= analysis["probability"] <= 1)
        self.assertEqual(set(b["validation_brier"]), {"linear", "boosted", "blend"})
        self.assertEqual(set(b["test_candidates_brier"]), {"linear", "boosted", "blend"})
        self.assertEqual(len(b["improvement_ci"]), 2)
        self.assertTrue(np.isfinite(b["brier"]))
        self.assertIsInstance(market_regime(features(df).iloc[-1]), str)
        self.assertIn("probability", analysis["test"])

    def test_historical_range_is_descriptive_and_ordered(self):
        result = empirical_seven_day_range(candles())
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result["count"], 40)
        self.assertEqual(result["kind"], "historical_not_forecast")
        self.assertLess(result["low"], result["high"])


if __name__ == "__main__":
    unittest.main()
