from __future__ import annotations

from typing import Any

import pandas as pd

from .config import ScoringConfig
from .llm import LLMAnalysis


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return min(high, max(low, value))


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        return float(value)
    except Exception:
        return None


def normalize_growth_yoy(value: float | None) -> float | None:
    if value is None:
        return None
    if value <= -30:
        return 0.0
    if value >= 80:
        return 100.0
    return clamp((value + 30) / 110 * 100)


def financial_continuation_score(row: pd.Series | dict[str, Any]) -> float:
    getter = row.get if isinstance(row, dict) else row.get
    existing = as_float(getter("financial_continuation_score", None))
    if existing is not None:
        return clamp(existing)
    for column in ["growth_score", "total_score"]:
        score = as_float(getter(column, None))
        if score is not None:
            return clamp(score)

    components: list[float] = []
    for column in ["revenue_yoy_h1", "profit_dedt_yoy_h1", "profit_yoy_h1", "netprofit_yoy_h1"]:
        score = normalize_growth_yoy(as_float(getter(column, None)))
        if score is not None:
            components.append(score)
    roe = as_float(getter("roe_h1", None))
    if roe is not None:
        components.append(clamp((roe + 5) / 25 * 100))
    ocf_to_np = as_float(getter("ocf_to_np", None))
    if ocf_to_np is not None:
        components.append(clamp(ocf_to_np * 70))

    if not components:
        return 50.0
    return sum(components) / len(components)


def text_confirmation_score(analysis: LLMAnalysis) -> float | None:
    scores = [
        analysis.growth_continues_score,
        analysis.quality_of_growth_score,
    ]
    valid = [float(score) for score in scores if score is not None]
    if not valid:
        return None
    return sum(valid) / len(valid)


def compute_verification_score(
    financial_score: float,
    analysis: LLMAnalysis,
    config: ScoringConfig,
) -> float | None:
    text_score = text_confirmation_score(analysis)
    visibility = analysis.visibility_score
    risk = analysis.risk_deterioration_score
    if text_score is None or visibility is None or risk is None:
        return None
    risk_quality = 100.0 - risk
    return clamp(
        financial_score * config.financial_weight
        + text_score * config.text_confirmation_weight
        + visibility * config.visibility_weight
        + risk_quality * config.risk_quality_weight
    )


def classify_candidate(
    financial_score: float,
    analysis: LLMAnalysis,
    verification_score: float | None,
    report_ready: bool,
) -> str:
    if not report_ready or verification_score is None or analysis.text_verdict == "D_pending":
        return "D_pending"
    text_score = text_confirmation_score(analysis) or 0.0
    visibility = analysis.visibility_score or 0.0
    risk = analysis.risk_deterioration_score if analysis.risk_deterioration_score is not None else 100.0

    if (
        financial_score >= 65
        and text_score >= 70
        and visibility >= 60
        and risk <= 55
        and analysis.text_verdict == "继续跟踪"
    ):
        return "A_confirmed"
    if financial_score >= 55 and text_score >= 45 and risk <= 75 and analysis.text_verdict != "剔除":
        return "B_watch"
    return "C_reject"

