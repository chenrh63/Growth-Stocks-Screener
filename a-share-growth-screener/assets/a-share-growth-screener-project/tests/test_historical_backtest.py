from __future__ import annotations

import unittest

import pandas as pd

from stock_screener.confirmation_backtest import ConfirmationBacktestConfig, simulate_confirmation_stock
from stock_screener.historical_backtest import generate_periods, report_deadline


class HistoricalBacktestTest(unittest.TestCase):
    def test_generate_periods_and_report_deadlines(self) -> None:
        periods = generate_periods("20210331", "20220331", ("0331", "0630"))
        self.assertEqual(periods, ["20210331", "20210630", "20220331"])
        self.assertEqual(report_deadline("20210331"), "20210430")
        self.assertEqual(report_deadline("20210630"), "20210831")
        self.assertEqual(report_deadline("20210930"), "20211031")
        self.assertEqual(report_deadline("20211231"), "20220430")

    def test_signal_wait_window_rejects_late_breakout(self) -> None:
        weeks = pd.date_range("2026-01-09", periods=18, freq="W-FRI")
        weekly = pd.DataFrame(
            {
                "ts_code": ["000001.SZ"] * len(weeks),
                "week": weeks,
                "week_start": weeks - pd.Timedelta(days=4),
                "week_end": weeks,
                "open": [10.0] * len(weeks),
                "high": [10.5] * len(weeks),
                "low": [9.5] * len(weeks),
                "close": [10.0] * len(weeks),
                "ma5": [11.0] * len(weeks),
                "ma10": [10.0] * len(weeks),
                "ma10_slope": [0.1] * len(weeks),
                "prior_high": [10.4] * len(weeks),
                "volume_ratio": [1.2] * len(weeks),
            }
        )
        signal_idx = 14
        weekly.loc[signal_idx, ["close", "ma5", "ma10", "prior_high"]] = [12.0, 11.0, 10.0, 11.5]
        weekly.loc[signal_idx + 1, ["open", "low", "close", "ma5", "ma10", "prior_high"]] = [12.2, 12.0, 12.4, 11.2, 10.2, 12.1]
        info = pd.Series(
            {
                "ts_code": "000001.SZ",
                "name": "TEST",
                "industry": "TEST",
                "candidate_status": "A_financial_strong",
                "ann_date": pd.Timestamp("2026-01-01"),
            }
        )

        late_rejected = simulate_confirmation_stock(info, weekly, ConfirmationBacktestConfig(max_signal_wait_weeks=4))
        self.assertEqual(late_rejected, [])

        late_allowed = simulate_confirmation_stock(
            info,
            weekly,
            ConfirmationBacktestConfig(max_signal_wait_weeks=20, max_hold_weeks=1),
        )
        self.assertEqual(len(late_allowed), 1)
        self.assertEqual(pd.Timestamp(late_allowed[0]["signal_week"]), weeks[signal_idx])


if __name__ == "__main__":
    unittest.main()
