"""Official-source parsing and live-monitor tests, entirely offline."""
import io
import json
import unittest
from datetime import datetime, timedelta, timezone

from external_data import bls_upcoming, cot_snapshot
from monitor import degradation_report


class Response(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *_): self.close()


class IntegrationTests(unittest.TestCase):
    def test_cot_has_holdback_and_never_claims_pit(self):
        now = datetime(2026, 11, 19, tzinfo=timezone.utc)
        record = {"report_date_as_yyyy_mm_dd": "2026-11-03T00:00:00.000",
                  "open_interest_all": "1000", "m_money_positions_long_all": "200",
                  "m_money_positions_short_all": "120"}
        urls = []
        def open_mock(req, timeout):
            urls.append(req.full_url)
            return Response(json.dumps([record]).encode())
        report = cot_snapshot("SI=F", now, opener=open_mock)
        self.assertFalse(report["used_in_model"])
        self.assertFalse(report["release_timestamp_verified"])
        self.assertEqual(report["managed_money_net"], 80)
        self.assertIn("2026-11-05", urls[0])

    def test_bls_calendar_respects_new_york_timezone(self):
        text = "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:CPI\nDTSTART;TZID=America/New_York:20261120T083000\nEND:VEVENT\nEND:VCALENDAR"
        result = bls_upcoming(datetime(2026, 11, 19, tzinfo=timezone.utc),
                              opener=lambda *args, **kwargs: Response(text.encode()))
        self.assertEqual(result[0]["scheduled_utc"], "2026-11-20T13:30:00+00:00")

    def test_monitor_ignores_overlapping_and_other_versions(self):
        start = datetime(2025, 1, 1)
        history = {}
        for i in range(25):
            day = start + timedelta(days=i * 8)
            entry = {"symbol": "BTC-USD", "date": day.date().isoformat(),
                     "outcome_date": (day + timedelta(days=7)).date().isoformat(),
                     "outcome": "flat_or_down", "up": .99}
            history[f"BTC-USD/{i}/v4"] = entry
            history[f"BTC-USD/{i}/v3"] = entry
        result = degradation_report(history, "BTC-USD", "v4")
        self.assertEqual(result["count"], 25)
        self.assertTrue(result["blocks_signal"])
        insufficient = degradation_report(history, "BTC-USD", "v3", minimum=26)
        self.assertEqual(insufficient["status"], "insufficient")


if __name__ == "__main__":
    unittest.main()
