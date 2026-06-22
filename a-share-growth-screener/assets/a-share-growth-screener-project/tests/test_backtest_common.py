from __future__ import annotations

import unittest

import pandas as pd

from stock_screener.backtest_common import make_weekly_bars, summarize_trades


class BacktestCommonTest(unittest.TestCase):
    def test_weekly_resample_uses_completed_prior_weeks_only(self) -> None:
        dates = pd.date_range("2026-01-05", periods=60, freq="B")
        daily = pd.DataFrame(
            {
                "ts_code": "000001.SZ",
                "trade_date": dates,
                "open": range(10, 70),
                "high": range(11, 71),
                "low": range(9, 69),
                "close": range(10, 70),
                "vol": range(100, 160),
            }
        )

        weekly = make_weekly_bars(daily)
        weekly["ma5"] = weekly.groupby("ts_code")["close"].transform(lambda s: s.shift(1).rolling(5, min_periods=5).mean())
        row = weekly[weekly["ma5"].notna()].iloc[0]
        prior = weekly[weekly["week"] < row["week"]].tail(5)["close"].mean()

        self.assertAlmostEqual(row["ma5"], prior)
        self.assertEqual(row["week_start"].weekday(), 0)
        self.assertEqual(row["week_end"].weekday(), 4)

    def test_summarize_trades_includes_all_and_status_groups(self) -> None:
        trades = pd.DataFrame(
            {
                "candidate_status": ["A_confirmed", "A_confirmed", "B_watch"],
                "return_pct": [0.10, -0.05, 0.02],
            }
        )

        summary = summarize_trades(trades, universe_count=5)
        all_row = summary[summary["group"] == "all"].iloc[0]
        a_row = summary[summary["group"] == "A_confirmed"].iloc[0]

        self.assertEqual(all_row["trade_count"], 3)
        self.assertAlmostEqual(all_row["win_rate"], 2 / 3)
        self.assertEqual(a_row["trade_count"], 2)
        self.assertAlmostEqual(a_row["median_return"], 0.025)


if __name__ == "__main__":
    unittest.main()
