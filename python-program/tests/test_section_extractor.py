from __future__ import annotations

import unittest

from stock_screener.config import TextAnalysisConfig
from stock_screener.reports.section_extractor import extract_relevant_sections


MDNA = "\u7ba1\u7406\u5c42\u8ba8\u8bba\u4e0e\u5206\u6790"
ORDERS = "\u5728\u624b\u8ba2\u5355\u589e\u957f"
GOVERNANCE = "\u6cbb\u7406\u5185\u5bb9"


class SectionExtractorTest(unittest.TestCase):
    def test_heading_extraction_prefers_relevant_sections(self) -> None:
        text = f"""
\u7b2c\u4e00\u8282 \u91cd\u8981\u63d0\u793a
\u8fd9\u91cc\u662f\u63d0\u793a\u3002
\u7b2c\u4e09\u8282 {MDNA}
\u62a5\u544a\u671f\u5185\uff0c\u516c\u53f8{ORDERS}\uff0c\u4ea7\u80fd\u91ca\u653e\uff0c\u6bdb\u5229\u7387\u4fdd\u6301\u7a33\u5b9a\u3002
\u7b2c\u56db\u8282 \u516c\u53f8\u6cbb\u7406
{GOVERNANCE}\u3002
"""
        result = extract_relevant_sections(text, TextAnalysisConfig(max_section_chars=1000))
        self.assertEqual(result.method, "heading")
        self.assertIn(MDNA, result.sections_text)
        self.assertIn(ORDERS, result.sections_text)
        self.assertNotIn(GOVERNANCE, result.sections_text)

    def test_keyword_window_fallback_when_no_heading(self) -> None:
        keyword = "\u5728\u624b\u8ba2\u5355"
        text = "\u516c\u53f8\u666e\u901a\u63cf\u8ff0\u3002" * 50 + f"\u62a5\u544a\u671f\u5185{keyword}\u589e\u52a0\uff0c\u6d77\u5916\u5ba2\u6237\u5f00\u62d3\u987a\u5229\u3002" + "\u5176\u4ed6\u63cf\u8ff0\u3002" * 50
        result = extract_relevant_sections(text, TextAnalysisConfig(max_section_chars=1000, keyword_window_chars=80))
        self.assertEqual(result.method, "keyword_window")
        self.assertIn(keyword, result.sections_text)
        self.assertTrue(result.char_count <= 1000)

    def test_require_heading_returns_missing_without_keyword_fallback(self) -> None:
        text = "\u62a5\u544a\u671f\u5185\u5728\u624b\u8ba2\u5355\u589e\u52a0\uff0c\u6d77\u5916\u5ba2\u6237\u5f00\u62d3\u987a\u5229\u3002"
        result = extract_relevant_sections(text, TextAnalysisConfig(), require_heading=True)
        self.assertEqual(result.method, "heading_missing")
        self.assertEqual(result.char_count, 0)


if __name__ == "__main__":
    unittest.main()
