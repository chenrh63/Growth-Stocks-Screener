from __future__ import annotations

import unittest

import pandas as pd

from stock_screener.data_sources.cninfo import _title_matches_period
from stock_screener.data_sources.tushare_announcements import (
    _normalize_anns_df,
    announcement_window,
    report_title_keywords,
)


class ReportPeriodsTest(unittest.TestCase):
    def test_q1_period_window_and_keywords(self) -> None:
        self.assertEqual(announcement_window("20260331"), ("20260401", "20260430"))
        self.assertIn("第一季度报告", report_title_keywords("20260331"))
        self.assertTrue(_title_matches_period("2026年第一季度报告", "20260331"))
        self.assertFalse(_title_matches_period("2026年半年度报告", "20260331"))
        self.assertFalse(_title_matches_period("2025年第三季度报告（更新后）", "20260331"))

    def test_normalize_q1_announcement(self) -> None:
        df = pd.DataFrame(
            [
                {"title": "2026年第一季度报告摘要", "ann_date": "20260420", "pdf_url": "bad.pdf"},
                {"title": "关于2026年第一季度报告披露的提示性公告", "ann_date": "20260420", "pdf_url": "notice.pdf"},
                {"title": "2026年第一季度报告", "ann_date": "20260420", "pdf_url": "ok.pdf"},
            ]
        )
        result = _normalize_anns_df(df, "000001.SZ", "测试公司", "20260331")
        self.assertEqual(result[0].title, "2026年第一季度报告")
        self.assertEqual(result[0].pdf_url, "ok.pdf")


if __name__ == "__main__":
    unittest.main()
