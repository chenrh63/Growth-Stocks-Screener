from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from stock_screener.llm import (
    CONSUMER_THEME,
    CONTINUE,
    EXPORT_THEME,
    LLMConfig,
    LLMResponse,
    UNCLEAR_THEME,
    WATCH,
    analyze_sections_with_llm,
    parse_llm_analysis,
)


class LLMParserTest(unittest.TestCase):
    def test_parse_fenced_json_response(self) -> None:
        payload = {
            "growth_continues_score": 82,
            "visibility_score": 74,
            "quality_of_growth_score": 79,
            "risk_deterioration_score": 25,
            "text_primary_theme": EXPORT_THEME,
            "theme_fit_score": 88,
            "text_verdict": CONTINUE,
            "reasoning": "orders and capacity support growth",
            "evidence_quotes": [{"claim": "orders", "quote": "orders increased"}],
        }
        raw = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
        result = parse_llm_analysis(raw)
        self.assertEqual(result.growth_continues_score, 82)
        self.assertEqual(result.text_verdict, CONTINUE)
        self.assertEqual(result.text_primary_theme, EXPORT_THEME)
        self.assertEqual(result.theme_fit_score, 88)
        self.assertEqual(result.evidence_quotes[0]["claim"], "orders")

    def test_invalid_verdict_is_conservative(self) -> None:
        result = parse_llm_analysis('{"text_verdict":"strong_buy","growth_continues_score":120,"text_primary_theme":"unknown"}')
        self.assertEqual(result.text_verdict, WATCH)
        self.assertEqual(result.text_primary_theme, UNCLEAR_THEME)
        self.assertEqual(result.growth_continues_score, 100)

    def test_analyze_sections_records_usage_metadata(self) -> None:
        payload = {
            "growth_continues_score": 70,
            "visibility_score": 60,
            "quality_of_growth_score": 75,
            "risk_deterioration_score": 20,
            "text_primary_theme": CONSUMER_THEME,
            "theme_fit_score": 80,
            "text_verdict": CONTINUE,
            "evidence_quotes": [{"claim": "sales", "quote": "sales increased"}],
        }
        response = LLMResponse(content=json.dumps(payload, ensure_ascii=False), usage={"prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168})
        config = LLMConfig(api_key="key", base_url="https://api.deepseek.com", model="deepseek-v4-flash")
        with patch("stock_screener.llm.call_openai_compatible_response", return_value=response):
            result = analyze_sections_with_llm("TestCo", "000001.SZ", "20260331", "MD&A: sales volume increased", config=config)
        self.assertEqual(result.total_tokens, 168)
        self.assertEqual(result.prompt_tokens, 123)
        self.assertEqual(result.completion_tokens, 45)
        self.assertEqual(result.llm_model, "deepseek-v4-flash")
        self.assertEqual(result.llm_base_url, "https://api.deepseek.com")
        self.assertEqual(result.text_primary_theme, CONSUMER_THEME)
        self.assertGreater(result.prompt_chars, 0)


if __name__ == "__main__":
    unittest.main()
