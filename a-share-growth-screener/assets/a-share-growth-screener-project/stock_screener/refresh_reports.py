from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from .config import RulesConfig, load_rules
from .data_sources.cninfo import fetch_cninfo_announcements
from .data_sources.tushare_announcements import fetch_tushare_announcements, merge_manual_pdf_urls
from .io import load_candidates, write_table
from .paths import REPORT_PDF_DIR, REPORT_SECTION_DIR, REPORT_TEXT_DIR, ensure_data_dirs, period_output_path
from .reports.downloader import download_file, safe_filename
from .reports.pdf_text import extract_text_from_pdf, write_extracted_text
from .reports.section_extractor import extract_relevant_sections


def _manifest_paths(period: str, output_prefix: str = "report_manifest", output_dir: Path | None = None) -> tuple[Path, Path]:
    return period_output_path(output_prefix, period, ".xlsx", output_dir=output_dir), period_output_path(output_prefix, period, ".csv", output_dir=output_dir)


def _build_pdf_path(period: str, ts_code: str, title: str) -> Path:
    filename = safe_filename(f"{period}_{ts_code}_{title or 'periodic_report'}") + ".pdf"
    return REPORT_PDF_DIR / filename


def previous_annual_period(period: str) -> str:
    return f"{int(period[:4]) - 1}1231"


def _clean_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _fetch_announcements(candidates: pd.DataFrame, period: str, source: str) -> pd.DataFrame:
    if source == "cninfo":
        return fetch_cninfo_announcements(candidates, period)

    announcements = fetch_tushare_announcements(candidates, period)
    announcements = merge_manual_pdf_urls(candidates, announcements)
    if "pdf_url" not in announcements.columns:
        announcements["pdf_url"] = ""
    needs_fallback = announcements["pdf_url"].fillna("").astype(str).str.strip().isin(["", "nan"])
    if source == "auto" and needs_fallback.any():
        fallback = fetch_cninfo_announcements(candidates.loc[needs_fallback.values], period)
        announcements = announcements.set_index("ts_code")
        fallback = fallback.set_index("ts_code")
        for ts_code, row in fallback.iterrows():
            if ts_code in announcements.index and _clean_str(row.get("pdf_url", "")):
                for column in fallback.columns:
                    announcements.loc[ts_code, column] = row[column]
        announcements = announcements.reset_index()
    return announcements


def _process_report_rows(
    announcements: pd.DataFrame,
    report_period: str,
    rules: RulesConfig,
    skip_download: bool,
    prefer_primary_sections: bool,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in announcements.to_dict(orient="records"):
        ts_code = _clean_str(row.get("ts_code", ""))
        title = _clean_str(row.get("title", ""))
        pdf_url = _clean_str(row.get("pdf_url", ""))
        pdf_path = _build_pdf_path(report_period, ts_code, title)
        text_path = REPORT_TEXT_DIR / f"{report_period}_{ts_code}.txt"
        section_path = REPORT_SECTION_DIR / f"{report_period}_{ts_code}.txt"

        download_status = "skipped" if skip_download else "pending"
        parse_status = "pending"
        section_status = "pending"
        section_chars = 0
        error = _clean_str(row.get("error", ""))

        if not skip_download and pdf_url:
            ok, download_error = download_file(pdf_url, pdf_path)
            if ok:
                download_status = "ok"
                extraction = extract_text_from_pdf(pdf_path)
                parse_status = extraction.status
                if extraction.text:
                    write_extracted_text(extraction.text, text_path)
                    titles = rules.text_analysis.primary_section_titles if prefer_primary_sections else rules.text_analysis.section_titles
                    sections = extract_relevant_sections(
                        extraction.text,
                        rules.text_analysis,
                        section_path,
                        section_titles=titles,
                        require_heading=False,
                    )
                    section_status = sections.method
                    section_chars = sections.char_count
                if extraction.error:
                    error = ";".join(part for part in [error, extraction.error] if part)
            else:
                download_status = "failed"
                error = ";".join(part for part in [error, download_error] if part)
        elif not pdf_url:
            download_status = "no_pdf_url"
            error = ";".join(part for part in [error, "no_pdf_url"] if part)

        rows.append(
            {
                **row,
                "report_period": report_period,
                "pdf_path": str(pdf_path) if pdf_path.exists() else "",
                "text_path": str(text_path) if text_path.exists() else "",
                "section_path": str(section_path) if section_path.exists() else "",
                "download_status": download_status,
                "parse_status": parse_status,
                "section_status": section_status,
                "section_chars": section_chars,
                "error": error,
            }
        )
    return rows


def _q1_mdna_ready(row: dict[str, object], rules: RulesConfig) -> bool:
    return (
        _clean_str(row.get("download_status")) == "ok"
        and _clean_str(row.get("parse_status")).startswith("ok")
        and _clean_str(row.get("section_status")) == "heading"
        and int(row.get("section_chars") or 0) >= rules.text_analysis.min_primary_section_chars
        and bool(_clean_str(row.get("section_path")))
    )


def _has_usable_sections(row: dict[str, object]) -> bool:
    return bool(_clean_str(row.get("section_path"))) and _clean_str(row.get("section_status")) not in {"", "pending", "empty_text"}


def _fallback_reason(row: dict[str, object], rules: RulesConfig) -> str:
    if not _clean_str(row.get("pdf_url")):
        return "q1_no_pdf_url"
    if _clean_str(row.get("download_status")) != "ok":
        return f"q1_download_{_clean_str(row.get('download_status'))}"
    if not _clean_str(row.get("parse_status")).startswith("ok"):
        return f"q1_parse_{_clean_str(row.get('parse_status'))}"
    if _clean_str(row.get("section_status")) != "heading":
        return f"q1_section_{_clean_str(row.get('section_status'))}"
    if int(row.get("section_chars") or 0) < rules.text_analysis.min_primary_section_chars:
        return "q1_mdna_too_short"
    return "q1_not_ready"


def _finalize_primary_row(row: dict[str, object], period: str, rules: RulesConfig, fallback_reason: str = "") -> dict[str, object]:
    source = "q1_mdna" if _q1_mdna_ready(row, rules) else "keyword_window" if _has_usable_sections(row) else "D_pending"
    return {
        **row,
        "period": period,
        "analysis_report_period": row.get("report_period", period),
        "analysis_source": source,
        "fallback_reason": fallback_reason,
        "primary_section_status": row.get("section_status", ""),
        "fallback_section_status": "",
    }


def _finalize_fallback_row(
    primary: dict[str, object],
    fallback: dict[str, object] | None,
    period: str,
    annual_period: str,
    reason: str,
    rules: RulesConfig,
) -> dict[str, object]:
    if fallback and _has_usable_sections(fallback):
        return {
            **fallback,
            "period": period,
            "analysis_report_period": annual_period,
            "analysis_source": "annual_mdna_fallback",
            "fallback_reason": reason,
            "primary_section_status": primary.get("section_status", ""),
            "fallback_section_status": fallback.get("section_status", ""),
        }
    return _finalize_primary_row(primary, period, rules, fallback_reason=f"{reason};annual_fallback_failed")


def refresh_reports(
    period: str,
    candidate_path: Path | None = None,
    source: str = "auto",
    limit: int | None = None,
    skip_download: bool = False,
    output_prefix: str = "report_manifest",
    fallback_annual_report: bool = False,
    output_dir: Path | None = None,
) -> pd.DataFrame:
    ensure_data_dirs()
    rules = load_rules()
    candidates = load_candidates(period, candidate_path)
    if limit:
        candidates = candidates.head(limit).copy()

    if source not in {"auto", "tushare", "cninfo"}:
        raise ValueError("source must be auto, tushare, or cninfo")

    primary_announcements = _fetch_announcements(candidates, period, source)
    primary_rows = _process_report_rows(primary_announcements, period, rules, skip_download, prefer_primary_sections=True)
    primary_by_code = {str(row.get("ts_code")): row for row in primary_rows}

    final_rows: list[dict[str, object]] = []
    fallback_by_code: dict[str, dict[str, object]] = {}
    annual_period = previous_annual_period(period)

    needs_fallback = [row for row in primary_rows if fallback_annual_report and not _q1_mdna_ready(row, rules)]
    if needs_fallback:
        fallback_codes = {str(row.get("ts_code")) for row in needs_fallback}
        fallback_candidates = candidates[candidates["ts_code"].astype(str).isin(fallback_codes)].copy()
        annual_announcements = _fetch_announcements(fallback_candidates, annual_period, source)
        fallback_rows = _process_report_rows(annual_announcements, annual_period, rules, skip_download, prefer_primary_sections=False)
        fallback_by_code = {str(row.get("ts_code")): row for row in fallback_rows}

    for ts_code, primary in primary_by_code.items():
        if fallback_annual_report and not _q1_mdna_ready(primary, rules):
            reason = _fallback_reason(primary, rules)
            final_rows.append(_finalize_fallback_row(primary, fallback_by_code.get(ts_code), period, annual_period, reason, rules))
        else:
            final_rows.append(_finalize_primary_row(primary, period, rules))

    manifest = pd.DataFrame(final_rows)
    xlsx_path, csv_path = _manifest_paths(period, output_prefix, output_dir=output_dir)
    write_table(manifest, xlsx_path)
    write_table(manifest, csv_path)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh periodic report PDFs and extracted sections.")
    parser.add_argument("--period", default="20260630")
    parser.add_argument("--candidates", type=Path, default=None)
    parser.add_argument("--source", choices=["auto", "tushare", "cninfo"], default="auto")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--output-prefix", default="report_manifest")
    parser.add_argument("--fallback-annual-report", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    manifest = refresh_reports(
        period=args.period,
        candidate_path=args.candidates,
        source=args.source,
        limit=args.limit,
        skip_download=args.skip_download,
        output_prefix=args.output_prefix,
        fallback_annual_report=args.fallback_annual_report,
        output_dir=args.output_dir,
    )
    print(f"Refreshed {len(manifest)} report rows.")
    print(period_output_path(args.output_prefix, args.period, ".xlsx", output_dir=args.output_dir))


if __name__ == "__main__":
    main()


