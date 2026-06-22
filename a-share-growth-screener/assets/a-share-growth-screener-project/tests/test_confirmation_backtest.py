from __future__ import annotations

import unittest

import pandas as pd

from stock_screener.confirmation_backtest import ConfirmationBacktestConfig, is_confirmation_signal


class ConfirmationBacktestTest(unittest.TestCase):
    def test_confirmation_signal_requires_breakout_trend_and_volume(self) -> None:
        row = pd.Series(
            {
                "close": 12.0,
                "ma5": 11.0,
                "ma10": 10.0,
                "ma10_slope": 0.1,
                "prior_high": 11.8,
                "volume_ratio": 1.2,
            }
        )
        self.assertTrue(is_confirmation_signal(row, ConfirmationBacktestConfig()))

        no_breakout = row.copy()
        no_breakout["close"] = 11.7
        self.assertFalse(is_confirmation_signal(no_breakout, ConfirmationBacktestConfig()))

        weak_trend = row.copy()
        weak_trend["ma10_slope"] = -0.1
        self.assertFalse(is_confirmation_signal(weak_trend, ConfirmationBacktestConfig()))

        weak_volume = row.copy()
        weak_volume["volume_ratio"] = 0.8
        self.assertFalse(is_confirmation_signal(weak_volume, ConfirmationBacktestConfig()))


if __name__ == "__main__":
    unittest.main()
