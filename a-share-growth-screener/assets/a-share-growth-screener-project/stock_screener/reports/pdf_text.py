from __future__ import annotations

from pathlib import Path

from .models import TextExtractionResult


def extract_text_from_pdf(pdf_path: Path) -> TextExtractionResult:
    if not pdf_path.exists():
        return TextExtractionResult(text="", status="missing_pdf", error=str(pdf_path))

    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        parts: list[str] = []
        for index, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception as exc:
                page_text = f"\n[page_{index}_extract_error:{exc}]\n"
            if page_text:
                parts.append(page_text)
        text = "\n".join(parts)
        status = "ok" if len(text.strip()) >= 500 else "scan_or_empty"
        return TextExtractionResult(text=text, status=status, page_count=len(reader.pages))
    except Exception as pdf_exc:
        # Test fixtures and occasional malformed filings may be plain text or partially readable bytes.
        try:
            raw = pdf_path.read_bytes()
            text = raw.decode("utf-8", errors="ignore")
            status = "ok_text_fallback" if len(text.strip()) >= 100 else "pdf_parse_failed"
            return TextExtractionResult(text=text, status=status, error=str(pdf_exc))
        except Exception as fallback_exc:
            return TextExtractionResult(text="", status="pdf_parse_failed", error=f"{pdf_exc}; {fallback_exc}")


def write_extracted_text(text: str, text_path: Path) -> None:
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(text, encoding="utf-8")

