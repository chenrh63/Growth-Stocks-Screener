from __future__ import annotations

import unittest

from stock_screener.llm import build_report_prompt, report_label


Q1_LABEL = "2026\u5e74\u4e00\u5b63\u62a5"


class LLMPromptTest(unittest.TestCase):
    def test_report_label_for_q1(self) -> None:
        self.assertEqual(report_label("20260331"), Q1_LABEL)
        prompt = build_report_prompt("TestCo", "000001.SZ", "20260331", "excerpt")
        self.assertIn(Q1_LABEL, prompt)
        self.assertNotIn("2026\u5e74\u534a\u5e74\u62a5", prompt)


if __name__ == "__main__":
    unittest.main()
