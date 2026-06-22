from __future__ import annotations

import unittest

from stock_screener.config import ScoringConfig
from stock_screener.llm import CONTINUE, LLMAnalysis
from stock_screener.scoring import classify_candidate, compute_verification_score, financial_continuation_score


class ScoringTest(unittest.TestCase):
    def test_confirmed_candidate_when_financial_and_text_are_strong(self) -> None:
        row = {"growth_score": 82}
        analysis = LLMAnalysis(
            growth_continues_score=84,
            visibility_score=76,
            quality_of_growth_score=80,
            risk_deterioration_score=22,
            text_verdict=CONTINUE,
        )
        financial = financial_continuation_score(row)
        total = compute_verification_score(financial, analysis, ScoringConfig())
        self.assertIsNotNone(total)
        self.assertEqual(classify_candidate(financial, analysis, total, report_ready=True), "A_confirmed")

    def test_missing_llm_or_report_is_pending(self) -> None:
        analysis = LLMAnalysis(error="LLM_API_KEY or LLM_MODEL missing")
        self.assertIsNone(compute_verification_score(70, analysis, ScoringConfig()))
        self.assertEqual(classify_candidate(70, analysis, None, report_ready=False), "D_pending")


if __name__ == "__main__":
    unittest.main()
