from __future__ import annotations

import re
from pathlib import Path

from .models import SectionExtractionResult
from ..config import TextAnalysisConfig


SECTION_BOUNDARY_RE = re.compile(
    r"(?m)^\s*(?:\u7b2c[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e\d]+[\u7ae0\u8282]|[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+[\u3001\uff0e.]|\d+[\u3001\uff0e.])\s*[\u4e00-\u9fa5A-Za-z0-9\uff08\uff09()\u300a\u300b\u3001\u00b7\- ]{2,60}\s*$"
)


def normalize_text(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _title_regex(titles: list[str]) -> re.Pattern[str]:
    escaped = [re.escape(title) for title in titles if title]
    if not escaped:
        return re.compile(r"a^")
    return re.compile("|".join(escaped), flags=re.IGNORECASE)


def _next_boundary(text: str, start: int) -> int:
    match = SECTION_BOUNDARY_RE.search(text, pos=start)
    return match.start() if match else len(text)


def _dedupe_snippets(snippets: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for snippet in snippets:
        normalized = re.sub(r"\s+", "", snippet[:180])
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(snippet.strip())
    return unique


def extract_relevant_sections(
    text: str,
    config: TextAnalysisConfig,
    output_path: Path | None = None,
    section_titles: list[str] | None = None,
    fallback_keywords: list[str] | None = None,
    require_heading: bool = False,
) -> SectionExtractionResult:
    normalized = normalize_text(text)
    if not normalized:
        return SectionExtractionResult("", "empty_text", [], 0, output_path)

    titles = section_titles if section_titles is not None else config.section_titles
    keywords = fallback_keywords if fallback_keywords is not None else config.fallback_keywords
    title_pattern = _title_regex(titles)
    snippets: list[str] = []
    matched_titles: list[str] = []

    for match in title_pattern.finditer(normalized):
        title = match.group(0)
        start = max(0, match.start() - 120)
        end = _next_boundary(normalized, match.end())
        if end <= match.end():
            end = min(len(normalized), match.end() + 5000)
        snippet = normalized[start:end]
        if snippet:
            snippets.append(snippet)
            matched_titles.append(title)
        if sum(len(item) for item in snippets) >= config.max_section_chars:
            break

    method = "heading"
    if not snippets and require_heading:
        return SectionExtractionResult("", "heading_missing", [], 0, output_path)

    if not snippets:
        method = "keyword_window"
        for keyword in keywords:
            for match in re.finditer(re.escape(keyword), normalized, flags=re.IGNORECASE):
                start = max(0, match.start() - config.keyword_window_chars)
                end = min(len(normalized), match.end() + config.keyword_window_chars)
                snippets.append(normalized[start:end])
                matched_titles.append(keyword)
                if sum(len(item) for item in snippets) >= config.max_section_chars:
                    break
            if sum(len(item) for item in snippets) >= config.max_section_chars:
                break

    if not snippets:
        method = "head_truncation"
        snippets = [normalized[: config.max_section_chars]]

    unique = _dedupe_snippets(snippets)
    sections_text = "\n\n--- SECTION BREAK ---\n\n".join(unique)[: config.max_section_chars]
    if output_path and sections_text:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(sections_text, encoding="utf-8")
    return SectionExtractionResult(
        sections_text=sections_text,
        method=method,
        matched_titles=list(dict.fromkeys(matched_titles)),
        char_count=len(sections_text),
        section_path=output_path,
    )
