from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Announcement:
    ts_code: str
    name: str
    title: str = ""
    ann_date: str = ""
    pdf_url: str = ""
    source: str = ""
    status: str = "D_pending"
    error: str = ""


@dataclass(frozen=True)
class TextExtractionResult:
    text: str
    status: str
    page_count: int = 0
    error: str = ""


@dataclass(frozen=True)
class SectionExtractionResult:
    sections_text: str
    method: str
    matched_titles: list[str]
    char_count: int
    section_path: Path | None = None

