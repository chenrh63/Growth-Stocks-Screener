from __future__ import annotations

import unittest
from pathlib import Path

from stock_screener.paths import period_output_path, safe_run_name


class PathsTest(unittest.TestCase):
    def test_period_output_path_can_use_run_output_dir(self) -> None:
        output_dir = Path("data/outputs/runs/test_run")
        path = period_output_path("report_analysis_tag", "20260331", ".csv", output_dir=output_dir)
        self.assertEqual(path, output_dir / "report_analysis_tag_20260331.csv")

    def test_safe_run_name_strips_unsafe_characters(self) -> None:
        self.assertEqual(safe_run_name(" theme growth / 20260331 "), "theme_growth_20260331")


if __name__ == "__main__":
    unittest.main()
