from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .config import RulesConfig, load_rules
from .llm import LLMAnalysis, analyze_sections_with_llm
from .paths import REPORT_SECTION_DIR
from .scoring import classify_candidate, compute_verification_score, financial_continuation_score, text_confirmation_score


def evidence_to_text(evidence: list[dict[str, str]]) -> str:
    if not evidence:
        return ""
    return "\n".join(
        f"{item.get('claim', '').strip()}: {item.get('quote', '').strip()}".strip(": ")
        for item in evidence
    )


def llm_analysis_to_columns(analysis: LLMAnalysis) -> dict[str, Any]:
    return {
        "growth_continues_score": analysis.growth_continues_score,
        "visibility_score": analysis.visibility_score,
        "quality_of_growth_score": analysis.quality_of_growth_score,
        "risk_deterioration_score": analysis.risk_deterioration_score,
        "text_primary_theme": analysis.text_primary_theme,
        "theme_fit_score": analysis.theme_fit_score,
        "text_verdict": analysis.text_verdict,
        "reasoning": analysis.reasoning,
        "evidence_quotes": evidence_to_text(analysis.evidence_quotes),
        "evidence_json": json.dumps(analysis.evidence_quotes, ensure_ascii=False),
        "llm_error": analysis.error,
        "llm_model": analysis.llm_model,
        "llm_base_url": analysis.llm_base_url,
        "llm_called_at": analysis.llm_called_at,
        "prompt_chars": analysis.prompt_chars,
        "prompt_tokens": analysis.prompt_tokens,
        "completion_tokens": analysis.completion_tokens,
        "total_tokens": analysis.total_tokens,
    }


def analyze_candidate_row(
    row: pd.Series,
    period: str,
    rules: RulesConfig | None = None,
    enable_llm: bool = True,
) -> dict[str, Any]:
    rules = rules or load_rules()
    ts_code = str(row.get("ts_code", ""))
    name = str(row.get("name", ""))
    analysis_report_period = str(row.get("analysis_report_period", period) or period)
    section_path_value = row.get("section_path", "")
    candidate_paths: list[Path] = []
    if section_path_value and str(section_path_value).lower() != "nan":
        candidate_paths.append(Path(str(section_path_value)))
    candidate_paths.append(REPORT_SECTION_DIR / f"{analysis_report_period}_{ts_code}.txt")
    candidate_paths.append(REPORT_SECTION_DIR / f"{period}_{ts_code}.txt")
    section_path = next((path for path in candidate_paths if path.exists()), candidate_paths[0] if candidate_paths else REPORT_SECTION_DIR / f"{period}_{ts_code}.txt")
    sections_text = section_path.read_text(encoding="utf-8") if section_path.exists() else ""
    report_ready = bool(sections_text.strip())

    if enable_llm and report_ready:
        analysis = analyze_sections_with_llm(name, ts_code, analysis_report_period, sections_text)
    else:
        reason = "section_text_missing" if not report_ready else "LLM disabled"
        analysis = LLMAnalysis(error=reason)

    financial_score = financial_continuation_score(row)
    verification_score = compute_verification_score(financial_score, analysis, rules.scoring)
    candidate_status = classify_candidate(financial_score, analysis, verification_score, report_ready)

    return {
        "ts_code": ts_code,
        "name": name,
        "financial_continuation_score": round(financial_score, 2),
        "text_confirmation_score": round(text_confirmation_score(analysis), 2) if text_confirmation_score(analysis) is not None else None,
        "verification_total_score": round(verification_score, 2) if verification_score is not None else None,
        "candidate_status": candidate_status,
        "section_path": str(section_path) if section_path.exists() else "",
        "section_chars": len(sections_text),
        **llm_analysis_to_columns(analysis),
    }


def analyze_candidates(
    merged: pd.DataFrame,
    period: str,
    rules: RulesConfig | None = None,
    limit: int | None = None,
    enable_llm: bool = True,
) -> pd.DataFrame:
    rules = rules or load_rules()
    work = merged.copy()
    if limit:
        work = work.head(limit)
    rows = [analyze_candidate_row(row, period=period, rules=rules, enable_llm=enable_llm) for _, row in work.iterrows()]
    result = pd.DataFrame(rows)
    if result.empty:
        return result

    passthrough_cols = [
        "industry",
        "total_score",
        "growth_score",
        "theme_score",
        "primary_theme",
        "theme_hits",
        "consumer_growth_score",
        "medical_recovery_score",
        "export_growth_score",
        "financial_acceleration_score",
        "valuation_score",
        "mispricing_score",
        "quality_score",
        "listing_days",
        "is_recent_listing",
        "hard_filter_pass",
        "financial_missing_fields",
        "analysis_report_period",
        "analysis_source",
        "fallback_reason",
        "primary_section_status",
        "fallback_section_status",
        "download_status",
        "parse_status",
        "section_status",
    ]
    for column in passthrough_cols:
        if column in work.columns and column not in result.columns:
            result[column] = work[column].values[: len(result)]

    keep_cols = [
        "ts_code",
        "name",
        "industry",
        "total_score",
        "growth_score",
        "theme_score",
        "primary_theme",
        "theme_hits",
        "consumer_growth_score",
        "medical_recovery_score",
        "export_growth_score",
        "financial_acceleration_score",
        "valuation_score",
        "mispricing_score",
        "quality_score",
        "listing_days",
        "is_recent_listing",
        "hard_filter_pass",
        "financial_missing_fields",
        "financial_continuation_score",
        "text_confirmation_score",
        "verification_total_score",
        "candidate_status",
        "growth_continues_score",
        "visibility_score",
        "quality_of_growth_score",
        "risk_deterioration_score",
        "text_primary_theme",
        "theme_fit_score",
        "text_verdict",
        "reasoning",
        "evidence_quotes",
        "analysis_report_period",
        "analysis_source",
        "fallback_reason",
        "primary_section_status",
        "fallback_section_status",
        "download_status",
        "parse_status",
        "section_status",
        "llm_error",
        "llm_model",
        "llm_base_url",
        "llm_called_at",
        "prompt_chars",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "section_path",
        "section_chars",
    ]
    ordered = [column for column in keep_cols if column in result.columns]
    return result[ordered + [column for column in result.columns if column not in ordered]]
