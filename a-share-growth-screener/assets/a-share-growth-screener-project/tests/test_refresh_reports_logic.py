from __future__ import annotations

import unittest

from stock_screener.config import RulesConfig, TextAnalysisConfig
from stock_screener.refresh_reports import _finalize_fallback_row, _q1_mdna_ready, previous_annual_period


class RefreshReportsLogicTest(unittest.TestCase):
    def test_previous_annual_period(self) -> None:
        self.assertEqual(previous_annual_period("20260331"), "20251231")
        self.assertEqual(previous_annual_period("20260630"), "20251231")

    def test_q1_mdna_ready_requires_heading_and_min_chars(self) -> None:
        rules = RulesConfig(text_analysis=TextAnalysisConfig(min_primary_section_chars=800))
        row = {
            "download_status": "ok",
            "parse_status": "ok",
            "section_status": "heading",
            "section_chars": 900,
            "section_path": "data/reports/sections/20260331_000001.SZ.txt",
        }
        self.assertTrue(_q1_mdna_ready(row, rules))
        row["section_status"] = "keyword_window"
        self.assertFalse(_q1_mdna_ready(row, rules))

    def test_fallback_row_uses_annual_report_when_available(self) -> None:
        rules = RulesConfig()
        primary = {
            "ts_code": "000001.SZ",
            "name": "TestCo",
            "report_period": "20260331",
            "pdf_url": "q1.pdf",
            "download_status": "ok",
            "parse_status": "ok",
            "section_status": "keyword_window",
            "section_chars": 1000,
            "section_path": "data/reports/sections/20260331_000001.SZ.txt",
        }
        annual = {
            "ts_code": "000001.SZ",
            "name": "TestCo",
            "report_period": "20251231",
            "pdf_url": "annual.pdf",
            "download_status": "ok",
            "parse_status": "ok",
            "section_status": "heading",
            "section_chars": 3000,
            "section_path": "data/reports/sections/20251231_000001.SZ.txt",
        }
        final = _finalize_fallback_row(primary, annual, "20260331", "20251231", "q1_section_keyword_window", rules)
        self.assertEqual(final["analysis_report_period"], "20251231")
        self.assertEqual(final["analysis_source"], "annual_mdna_fallback")
        self.assertEqual(final["primary_section_status"], "keyword_window")
        self.assertEqual(final["fallback_section_status"], "heading")


if __name__ == "__main__":
    unittest.main()
