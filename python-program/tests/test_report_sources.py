from __future__ import annotations

import unittest

from stock_screener.data_sources.cninfo import _normalize_cninfo_pdf_url, _stock_query_value, _title_matches_period
from stock_screener.data_sources.tushare_announcements import report_title_keywords


class ReportSourceTest(unittest.TestCase):
    def test_cninfo_title_matches_formal_q1_report(self) -> None:
        self.assertTrue(_title_matches_period("2026年一季度报告", "20260331"))
        self.assertTrue(_title_matches_period("2026年第一季度报告", "20260331"))
        self.assertFalse(_title_matches_period("2026年一季度报告摘要", "20260331"))
        self.assertFalse(_title_matches_period("关于2026年一季度报告的更正公告", "20260331"))

    def test_cninfo_pdf_url_normalization(self) -> None:
        self.assertEqual(
            _normalize_cninfo_pdf_url("finalpage/2026-04-22/1225135105.PDF"),
            "http://static.cninfo.com.cn/finalpage/2026-04-22/1225135105.PDF",
        )

    def test_cninfo_stock_query_uses_org_id_when_available(self) -> None:
        self.assertEqual(_stock_query_value("300970.SZ", {"300970": "gfbj0832838"}), "300970,gfbj0832838")
        self.assertEqual(_stock_query_value("300970.SZ", {}), "300970")

    def test_tushare_title_keywords_are_readable_unicode(self) -> None:
        self.assertIn("一季度报告", report_title_keywords("20260331"))
        self.assertIn("半年度报告", report_title_keywords("20260630"))


if __name__ == "__main__":
    unittest.main()
