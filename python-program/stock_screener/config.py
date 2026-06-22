from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .paths import DEFAULT_RULES_PATH


DEFAULT_SECTION_TITLES = [
    "\u7ba1\u7406\u5c42\u8ba8\u8bba\u4e0e\u5206\u6790",
    "\u7ecf\u8425\u60c5\u51b5\u8ba8\u8bba\u4e0e\u5206\u6790",
    "\u8463\u4e8b\u4f1a\u62a5\u544a",
    "\u4e3b\u8425\u4e1a\u52a1\u5206\u6790",
    "\u6838\u5fc3\u7ade\u4e89\u529b",
    "\u516c\u53f8\u672a\u6765\u53d1\u5c55\u7684\u5c55\u671b",
    "\u672a\u6765\u5c55\u671b",
    "\u98ce\u9669\u56e0\u7d20",
    "\u53ef\u80fd\u9762\u5bf9\u7684\u98ce\u9669",
]

DEFAULT_PRIMARY_SECTION_TITLES = [
    "\u7ba1\u7406\u5c42\u8ba8\u8bba\u4e0e\u5206\u6790",
    "\u7ecf\u8425\u60c5\u51b5\u8ba8\u8bba\u4e0e\u5206\u6790",
    "\u4e3b\u8425\u4e1a\u52a1\u5206\u6790",
    "\u8463\u4e8b\u4f1a\u62a5\u544a",
]

DEFAULT_FALLBACK_KEYWORDS = [
    "\u8ba2\u5355",
    "\u5728\u624b\u8ba2\u5355",
    "\u4ea7\u80fd",
    "\u4ea7\u80fd\u5229\u7528\u7387",
    "\u5ba2\u6237",
    "\u6bdb\u5229\u7387",
    "\u4ef7\u683c",
    "\u9500\u91cf",
    "\u6d77\u5916",
    "\u5883\u5916",
    "\u51fa\u53e3",
    "\u5916\u9500",
    "\u65b0\u4ea7\u54c1",
    "\u52df\u6295",
    "\u5408\u540c\u8d1f\u503a",
    "\u9700\u6c42",
    "\u4ea4\u4ed8",
    "\u5e02\u5360\u7387",
    "\u7814\u53d1",
    "\u6269\u4ea7",
    "\u96c6\u91c7",
    "\u533b\u4fdd",
    "\u4e2d\u6807",
]

DEFAULT_AI_KEYWORDS = [
    "\u4eba\u5de5\u667a\u80fd",
    "AI",
    "AIGC",
    "\u5927\u6a21\u578b",
    "\u7b97\u529b",
    "\u6570\u636e\u4e2d\u5fc3",
    "\u534a\u5bfc\u4f53",
    "\u82af\u7247",
    "GPU",
    "\u5149\u6a21\u5757",
    "\u4e92\u8054\u7f51",
    "\u6e38\u620f",
    "\u901a\u4fe1\u8bbe\u5907",
    "\u5143\u5668\u4ef6",
    "IT\u8bbe\u5907",
    "\u7535\u4fe1\u8fd0\u8425",
    "\u8f6f\u4ef6\u5f00\u53d1",
    "\u8f6f\u4ef6\u670d\u52a1",
    "\u4fe1\u521b",
]

DEFAULT_FINANCIAL_INDUSTRIES = ["\u94f6\u884c", "\u8bc1\u5238", "\u4fdd\u9669", "\u591a\u5143\u91d1\u878d"]


@dataclass(frozen=True)
class CandidateFiltersConfig:
    exclude_st: bool = True
    exclude_bj: bool = True
    exclude_financial: bool = True
    min_listing_days: int = 0
    financial_industries: list[str] = field(default_factory=lambda: list(DEFAULT_FINANCIAL_INDUSTRIES))


@dataclass(frozen=True)
class TextAnalysisConfig:
    max_section_chars: int = 18000
    keyword_window_chars: int = 900
    min_primary_section_chars: int = 800
    section_titles: list[str] = field(default_factory=lambda: list(DEFAULT_SECTION_TITLES))
    primary_section_titles: list[str] = field(default_factory=lambda: list(DEFAULT_PRIMARY_SECTION_TITLES))
    fallback_keywords: list[str] = field(default_factory=lambda: list(DEFAULT_FALLBACK_KEYWORDS))


@dataclass(frozen=True)
class ScoringConfig:
    financial_weight: float = 0.45
    text_confirmation_weight: float = 0.35
    visibility_weight: float = 0.15
    risk_quality_weight: float = 0.05


@dataclass(frozen=True)
class ScreeningConfig:
    target_count: int = 100
    min_total_mv: float = 300000
    min_circ_mv: float = 150000
    min_avg_turnover_rate: float = 0.3
    price_history_days: int = 260
    min_financial_score: float = 50
    min_drawdown_250d: float = -0.20
    max_return_120d: float = 0.35
    max_industry_return_120d: float = 0.05
    require_positive_profit_dedt: bool = True
    weights: dict[str, float] = field(
        default_factory=lambda: {"growth": 0.35, "theme": 0.20, "valuation": 0.20, "mispricing": 0.15, "quality": 0.10}
    )


@dataclass(frozen=True)
class RulesConfig:
    period: str = "20260630"
    candidate_filters: CandidateFiltersConfig = field(default_factory=CandidateFiltersConfig)
    screening: ScreeningConfig = field(default_factory=ScreeningConfig)
    text_analysis: TextAnalysisConfig = field(default_factory=TextAnalysisConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    ai_exclusion_keywords: list[str] = field(default_factory=lambda: list(DEFAULT_AI_KEYWORDS))


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore
    except Exception:
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def _list_value(data: dict[str, Any], key: str, default: list[str]) -> list[str]:
    value = data.get(key, default)
    return list(value) if isinstance(value, list) else list(default)


def load_rules(path: Path | None = None) -> RulesConfig:
    data = _read_yaml(path or DEFAULT_RULES_PATH)
    candidate_filter_data = data.get("candidate_filters", {}) if isinstance(data.get("candidate_filters", {}), dict) else {}
    screening_data = data.get("screening", {}) if isinstance(data.get("screening", {}), dict) else {}
    text_data = data.get("text_analysis", {}) if isinstance(data.get("text_analysis", {}), dict) else {}
    scoring_data = data.get("scoring", {}) if isinstance(data.get("scoring", {}), dict) else {}
    ai_data = data.get("ai_exclusion", {}) if isinstance(data.get("ai_exclusion", {}), dict) else {}

    return RulesConfig(
        period=str(data.get("period", "20260630")),
        candidate_filters=CandidateFiltersConfig(
            exclude_st=bool(candidate_filter_data.get("exclude_st", True)),
            exclude_bj=bool(candidate_filter_data.get("exclude_bj", True)),
            exclude_financial=bool(candidate_filter_data.get("exclude_financial", True)),
            min_listing_days=int(candidate_filter_data.get("min_listing_days", 0)),
            financial_industries=_list_value(candidate_filter_data, "financial_industries", DEFAULT_FINANCIAL_INDUSTRIES),
        ),
        screening=ScreeningConfig(
            target_count=int(screening_data.get("target_count", 100)),
            min_total_mv=float(screening_data.get("min_total_mv", 300000)),
            min_circ_mv=float(screening_data.get("min_circ_mv", 150000)),
            min_avg_turnover_rate=float(screening_data.get("min_avg_turnover_rate", 0.3)),
            price_history_days=int(screening_data.get("price_history_days", 260)),
            min_financial_score=float(screening_data.get("min_financial_score", 50)),
            min_drawdown_250d=float(screening_data.get("min_drawdown_250d", -0.20)),
            max_return_120d=float(screening_data.get("max_return_120d", 0.35)),
            max_industry_return_120d=float(screening_data.get("max_industry_return_120d", 0.05)),
            require_positive_profit_dedt=bool(screening_data.get("require_positive_profit_dedt", True)),
            weights=dict(
                screening_data.get(
                    "weights",
                    {"growth": 0.35, "theme": 0.20, "valuation": 0.20, "mispricing": 0.15, "quality": 0.10},
                )
            ),
        ),
        text_analysis=TextAnalysisConfig(
            max_section_chars=int(text_data.get("max_section_chars", 18000)),
            keyword_window_chars=int(text_data.get("keyword_window_chars", 900)),
            min_primary_section_chars=int(text_data.get("min_primary_section_chars", 800)),
            section_titles=_list_value(text_data, "section_titles", DEFAULT_SECTION_TITLES),
            primary_section_titles=_list_value(text_data, "primary_section_titles", DEFAULT_PRIMARY_SECTION_TITLES),
            fallback_keywords=_list_value(text_data, "fallback_keywords", DEFAULT_FALLBACK_KEYWORDS),
        ),
        scoring=ScoringConfig(
            financial_weight=float(scoring_data.get("financial_weight", 0.45)),
            text_confirmation_weight=float(scoring_data.get("text_confirmation_weight", 0.35)),
            visibility_weight=float(scoring_data.get("visibility_weight", 0.15)),
            risk_quality_weight=float(scoring_data.get("risk_quality_weight", 0.05)),
        ),
        ai_exclusion_keywords=_list_value(ai_data, "hard_exclude_keywords", DEFAULT_AI_KEYWORDS),
    )
