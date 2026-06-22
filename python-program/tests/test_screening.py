from __future__ import annotations

import unittest

import pandas as pd

from stock_screener.config import CandidateFiltersConfig, RulesConfig, ScreeningConfig
from stock_screener.llm import CONSUMER_THEME, EXPORT_THEME, MEDICAL_THEME
from stock_screener.screening import (
    apply_hard_metric_filters,
    apply_main_board_filter,
    apply_universe_filters,
    default_financial_period,
    score_candidates,
)

CHEMICAL = "\u5316\u5de5\u539f\u6599"
MACHINERY = "\u4e13\u7528\u673a\u68b0"
MAIN_BOARD = "\u4e3b\u677f"
BJ_MARKET = "\u5317\u4ea4\u6240"
DATA_CENTER = "\u6570\u636e\u4e2d\u5fc3"
BIO_PHARMA = "\u751f\u7269\u5236\u836f"
BANK = "\u94f6\u884c"
FOOD = "\u98df\u54c1"
MEDICAL_CARE = "\u533b\u7597\u4fdd\u5065"


class ScreeningTest(unittest.TestCase):
    def test_default_financial_period_for_half_year_tracking(self) -> None:
        self.assertEqual(default_financial_period("20260630"), "20260331")

    def test_filters_keep_recent_listing_when_min_listing_days_zero(self) -> None:
        df = pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "name": "Normal", "industry": CHEMICAL, "market": MAIN_BOARD, "list_date": "20100101"},
                {"ts_code": "000003.SZ", "name": "Recent", "industry": MACHINERY, "market": MAIN_BOARD, "list_date": "20260101"},
                {"ts_code": "000002.SZ", "name": "ST Risk", "industry": CHEMICAL, "market": MAIN_BOARD, "list_date": "20100101"},
                {"ts_code": "430001.BJ", "name": "BJ Stock", "industry": MACHINERY, "market": BJ_MARKET, "list_date": "20100101"},
                {"ts_code": "000004.SZ", "name": "AI Stock", "industry": DATA_CENTER, "market": MAIN_BOARD, "list_date": "20100101"},
                {"ts_code": "000005.SZ", "name": "Bio-U", "industry": BIO_PHARMA, "market": MAIN_BOARD, "list_date": "20100101"},
            ]
        )
        rules = RulesConfig(candidate_filters=CandidateFiltersConfig(min_listing_days=0))
        result = apply_universe_filters(df, rules, "20260605")
        self.assertEqual(result["ts_code"].tolist(), ["000001.SZ", "000003.SZ"])
        self.assertTrue(bool(result.loc[result["ts_code"] == "000003.SZ", "is_recent_listing"].iloc[0]))

    def test_filters_can_still_remove_recent_listing_when_threshold_positive(self) -> None:
        df = pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "name": "Normal", "industry": CHEMICAL, "market": MAIN_BOARD, "list_date": "20100101"},
                {"ts_code": "000003.SZ", "name": "Recent", "industry": MACHINERY, "market": MAIN_BOARD, "list_date": "20260101"},
            ]
        )
        rules = RulesConfig(candidate_filters=CandidateFiltersConfig(min_listing_days=730))
        result = apply_universe_filters(df, rules, "20260605")
        self.assertEqual(result["ts_code"].tolist(), ["000001.SZ"])

    def test_filters_remove_financial_industries(self) -> None:
        df = pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "name": "Bank", "industry": BANK, "market": MAIN_BOARD, "list_date": "20100101"},
                {"ts_code": "000002.SZ", "name": "Food", "industry": FOOD, "market": MAIN_BOARD, "list_date": "20100101"},
            ]
        )
        result = apply_universe_filters(df, RulesConfig(), "20260605")
        self.assertEqual(result["ts_code"].tolist(), ["000002.SZ"])

    def test_main_board_filter_keeps_only_shenzhen_and_shanghai_main_board(self) -> None:
        df = pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "name": "SZ Main", "industry": FOOD, "market": MAIN_BOARD},
                {"ts_code": "600001.SH", "name": "SH Main", "industry": CHEMICAL, "market": MAIN_BOARD},
                {"ts_code": "300001.SZ", "name": "ChiNext", "industry": MACHINERY, "market": "\u521b\u4e1a\u677f"},
                {"ts_code": "688001.SH", "name": "STAR", "industry": MACHINERY, "market": "\u79d1\u521b\u677f"},
                {"ts_code": "430001.BJ", "name": "BJ", "industry": MACHINERY, "market": BJ_MARKET},
            ]
        )
        result = apply_main_board_filter(df)
        self.assertEqual(result["ts_code"].tolist(), ["000001.SZ", "600001.SH"])

    def test_hard_metric_filters_apply_market_cap_and_turnover(self) -> None:
        df = pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "total_mv": 300000, "circ_mv": 150000, "turnover_rate": 0.3},
                {"ts_code": "000002.SZ", "total_mv": 299999, "circ_mv": 150000, "turnover_rate": 0.3},
                {"ts_code": "000003.SZ", "total_mv": 300000, "circ_mv": 149999, "turnover_rate": 0.3},
                {"ts_code": "000004.SZ", "total_mv": 300000, "circ_mv": 150000, "turnover_rate": 0.29},
            ]
        )
        result = apply_hard_metric_filters(df, RulesConfig())
        self.assertEqual(result["ts_code"].tolist(), ["000001.SZ"])
        self.assertTrue(bool(result["hard_filter_pass"].iloc[0]))

    def test_score_candidates_prefers_value_and_low_position_with_new_weights(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "name": "GrowthExpensive",
                    "industry": CHEMICAL,
                    "tr_yoy": 100,
                    "q_netprofit_yoy": 120,
                    "roe": 18,
                    "grossprofit_margin": 45,
                    "ocf_to_or": 0.8,
                    "pe_ttm": 80,
                    "pb": 8,
                    "ps_ttm": 8,
                    "total_mv": 500000,
                    "circ_mv": 400000,
                    "turnover_rate": 1.0,
                    "drawdown_250d": -0.05,
                    "return_120d": 0.25,
                    "industry_return_120d": 0.04,
                    "profit_dedt": 1000,
                },
                {
                    "ts_code": "000002.SZ",
                    "name": "ValueLow",
                    "industry": CHEMICAL,
                    "tr_yoy": 25,
                    "q_netprofit_yoy": 35,
                    "roe": 10,
                    "grossprofit_margin": 30,
                    "ocf_to_or": 0.35,
                    "pe_ttm": 8,
                    "pb": 1,
                    "ps_ttm": 1,
                    "total_mv": 500000,
                    "circ_mv": 400000,
                    "turnover_rate": 1.0,
                    "drawdown_250d": -0.45,
                    "return_120d": -0.20,
                    "industry_return_120d": -0.15,
                    "profit_dedt": 1000,
                },
            ]
        )
        rules = RulesConfig(
            screening=ScreeningConfig(weights={"growth": 0.35, "theme": 0.20, "valuation": 0.20, "mispricing": 0.15, "quality": 0.10})
        )
        scored = score_candidates(df, rules)
        self.assertEqual(set(scored["ts_code"]), {"000001.SZ", "000002.SZ"})
        self.assertIn("financial_missing_fields", scored.columns)
        self.assertIn("theme_score", scored.columns)
        self.assertTrue((scored["theme_score"] == 0).all())

    def test_theme_scores_mark_consumer_medical_and_export(self) -> None:
        df = pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "name": "Food", "industry": FOOD, "tr_yoy": 35, "q_netprofit_yoy": 80, "roe": 12, "grossprofit_margin": 35, "ocf_to_or": 0.4, "pe_ttm": 20, "pb": 2, "ps_ttm": 2, "total_mv": 500000, "circ_mv": 300000, "turnover_rate": 1, "drawdown_250d": -0.3, "return_120d": -0.1, "industry_return_120d": -0.1, "profit_dedt": 1000},
                {"ts_code": "000002.SZ", "name": "Med", "industry": MEDICAL_CARE, "tr_yoy": 20, "q_netprofit_yoy": 70, "roe": 10, "grossprofit_margin": 45, "ocf_to_or": 0.3, "pe_ttm": 20, "pb": 2, "ps_ttm": 2, "total_mv": 500000, "circ_mv": 300000, "turnover_rate": 1, "drawdown_250d": -0.3, "return_120d": -0.1, "industry_return_120d": -0.1, "profit_dedt": 1000},
                {"ts_code": "000003.SZ", "name": "Machine", "industry": MACHINERY, "tr_yoy": 30, "q_netprofit_yoy": 90, "roe": 11, "grossprofit_margin": 30, "ocf_to_or": 0.3, "pe_ttm": 20, "pb": 2, "ps_ttm": 2, "total_mv": 500000, "circ_mv": 300000, "turnover_rate": 1, "drawdown_250d": -0.3, "return_120d": -0.1, "industry_return_120d": -0.1, "profit_dedt": 1000},
            ]
        )
        scored = score_candidates(df, RulesConfig()).set_index("ts_code")
        self.assertEqual(scored.loc["000001.SZ", "primary_theme"], CONSUMER_THEME)
        self.assertEqual(scored.loc["000002.SZ", "primary_theme"], MEDICAL_THEME)
        self.assertEqual(scored.loc["000003.SZ", "primary_theme"], EXPORT_THEME)
        self.assertGreater(scored.loc["000001.SZ", "theme_score"], 0)


if __name__ == "__main__":
    unittest.main()


