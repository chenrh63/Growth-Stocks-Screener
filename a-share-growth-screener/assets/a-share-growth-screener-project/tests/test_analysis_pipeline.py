from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from stock_screener.analysis import analyze_candidates
from stock_screener.config import RulesConfig
from stock_screener.llm import LLMAnalysis


class AnalysisPipelineTest(unittest.TestCase):
    def test_analyze_only_uses_cached_section_path(self) -> None:
        section_path = Path.cwd() / "tests" / "_tmp_section.txt"
        section_path.parent.mkdir(parents=True, exist_ok=True)
        evidence = "\u5728\u624b\u8ba2\u5355\u589e\u957f"
        section_path.write_text("\u7ba1\u7406\u5c42\u8ba8\u8bba\u4e0e\u5206\u6790: " + evidence, encoding="utf-8")
        df = pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "name": "TestCo",
                    "growth_score": 80,
                    "section_path": str(section_path),
                }
            ]
        )
        with patch(
            "stock_screener.analysis.analyze_sections_with_llm",
            return_value=LLMAnalysis(
                growth_continues_score=80,
                visibility_score=75,
                quality_of_growth_score=78,
                risk_deterioration_score=20,
                text_verdict="\u7ee7\u7eed\u8ddf\u8e2a",
                evidence_quotes=[{"claim": "orders", "quote": evidence}],
            ),
        ):
            result = analyze_candidates(df, "20260630", rules=RulesConfig(), enable_llm=True)
        self.assertEqual(result.loc[0, "candidate_status"], "A_confirmed")
        self.assertIn(evidence, result.loc[0, "evidence_quotes"])


if __name__ == "__main__":
    unittest.main()
