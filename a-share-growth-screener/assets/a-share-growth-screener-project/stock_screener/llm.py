from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .env import get_env


CONTINUE = "\u7ee7\u7eed\u8ddf\u8e2a"
WATCH = "\u964d\u6743\u89c2\u5bdf"
REJECT = "\u5254\u9664"
CONSUMER_THEME = "\u6d88\u8d39\u9ad8\u6210\u957f"
MEDICAL_THEME = "\u533b\u836f\u533b\u68b0\u91cf\u4ef7\u6062\u590d"
EXPORT_THEME = "\u5236\u9020\u4e1a\u51fa\u6d77"
UNCLEAR_THEME = "\u4e0d\u660e\u786e"
VALID_VERDICTS = {CONTINUE, WATCH, REJECT, "D_pending"}
VALID_TEXT_THEMES = {CONSUMER_THEME, MEDICAL_THEME, EXPORT_THEME, UNCLEAR_THEME}


@dataclass(frozen=True)
class LLMConfig:
    api_key: str | None
    base_url: str | None
    model: str | None
    timeout: int = 90

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.model)


@dataclass
class LLMAnalysis:
    growth_continues_score: float | None = None
    visibility_score: float | None = None
    quality_of_growth_score: float | None = None
    risk_deterioration_score: float | None = None
    theme_fit_score: float | None = None
    text_primary_theme: str = UNCLEAR_THEME
    text_verdict: str = "D_pending"
    evidence_quotes: list[dict[str, str]] = field(default_factory=list)
    reasoning: str = ""
    raw_response: str = ""
    error: str = ""
    llm_model: str = ""
    llm_base_url: str = ""
    llm_called_at: str = ""
    prompt_chars: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class LLMResponse:
    content: str
    usage: dict[str, Any]


def load_llm_config() -> LLMConfig:
    return LLMConfig(
        api_key=get_env("LLM_API_KEY"),
        base_url=get_env("LLM_BASE_URL", "https://api.openai.com/v1"),
        model=get_env("LLM_MODEL"),
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    if fenced:
        stripped = fenced.group(1)

    start = stripped.find("{")
    if start < 0:
        raise ValueError("No JSON object found")

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(stripped)):
        char = stripped[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(stripped[start : index + 1])
    raise ValueError("Unclosed JSON object")


def _score_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    score = float(value)
    return min(100.0, max(0.0, score))


def parse_llm_analysis(raw: str) -> LLMAnalysis:
    data = _extract_json_object(raw)
    quotes = data.get("evidence_quotes", [])
    if isinstance(quotes, dict):
        quotes = [quotes]
    if not isinstance(quotes, list):
        quotes = []
    normalized_quotes: list[dict[str, str]] = []
    for item in quotes:
        if isinstance(item, str):
            normalized_quotes.append({"claim": "", "quote": item[:180]})
        elif isinstance(item, dict):
            normalized_quotes.append(
                {
                    "claim": str(item.get("claim", ""))[:120],
                    "quote": str(item.get("quote", ""))[:220],
                }
            )

    verdict = str(data.get("text_verdict", "D_pending")).strip()
    if verdict not in VALID_VERDICTS:
        verdict = WATCH
    text_primary_theme = str(data.get("text_primary_theme", UNCLEAR_THEME)).strip()
    if text_primary_theme not in VALID_TEXT_THEMES:
        text_primary_theme = UNCLEAR_THEME

    return LLMAnalysis(
        growth_continues_score=_score_or_none(data.get("growth_continues_score")),
        visibility_score=_score_or_none(data.get("visibility_score")),
        quality_of_growth_score=_score_or_none(data.get("quality_of_growth_score")),
        risk_deterioration_score=_score_or_none(data.get("risk_deterioration_score")),
        theme_fit_score=_score_or_none(data.get("theme_fit_score")),
        text_primary_theme=text_primary_theme,
        text_verdict=verdict,
        evidence_quotes=normalized_quotes,
        reasoning=str(data.get("reasoning", "")),
        raw_response=raw,
    )


def report_label(period: str) -> str:
    if period.endswith("0331"):
        return f"{period[:4]}\u5e74\u4e00\u5b63\u62a5"
    if period.endswith("0630"):
        return f"{period[:4]}\u5e74\u534a\u5e74\u62a5"
    if period.endswith("0930"):
        return f"{period[:4]}\u5e74\u4e09\u5b63\u62a5"
    if period.endswith("1231"):
        return f"{period[:4]}\u5e74\u5e74\u62a5"
    return f"{period}\u5b9a\u671f\u62a5\u544a"


def build_report_prompt(company_name: str, ts_code: str, period: str, sections_text: str) -> str:
    label = report_label(period)
    return f"""You are an A-share periodic report research assistant. Use only the provided {label} excerpts.
Judge whether growth continues, whether visibility is improving, whether growth quality is healthy, and whether risk is deteriorating.

Theme labels to choose from:
- {CONSUMER_THEME}: consumer company with low-cycle high growth, supported by revenue/profit, sales volume, price, channel, traffic, product mix, or recovery evidence.
- {MEDICAL_THEME}: medicine or medical-device company recovering from centralized procurement/medical insurance pressure, supported by volume, price, margin, winning bids, registrations, hospital demand, or similar evidence.
- {EXPORT_THEME}: manufacturer whose overseas/export/international customer/order/capacity evidence is a major growth clue.
- {UNCLEAR_THEME}: evidence is insufficient for the above themes.

Rules:
1. Do not use external knowledge.
2. Every key judgment must cite short original evidence from the report excerpt.
3. If evidence is weak, keep scores conservative and choose {WATCH} or {REJECT}.
4. Output exactly one JSON object and no Markdown.

Company: {company_name}
Code: {ts_code}
Report period: {label}

JSON schema:
{{
  "growth_continues_score": 0-100,
  "visibility_score": 0-100,
  "quality_of_growth_score": 0-100,
  "risk_deterioration_score": 0-100,
  "text_primary_theme": "{CONSUMER_THEME}|{MEDICAL_THEME}|{EXPORT_THEME}|{UNCLEAR_THEME}",
  "theme_fit_score": 0-100,
  "text_verdict": "{CONTINUE}|{WATCH}|{REJECT}",
  "reasoning": "conclusion within 80 Chinese characters",
  "evidence_quotes": [
    {{"claim": "judgment point", "quote": "short quote from report"}}
  ]
}}

Report excerpts:
{sections_text}
"""


def call_openai_compatible_response(prompt: str, config: LLMConfig) -> LLMResponse:
    if not config.enabled:
        raise RuntimeError("LLM_API_KEY or LLM_MODEL missing")
    base_url = (config.base_url or "https://api.openai.com/v1").rstrip("/")
    url = f"{base_url}/chat/completions"
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": "You are a strict A-share financial report analyst. Output JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=config.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"LLM HTTP {exc.code}: {detail[:500]}") from exc
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("LLM response missing choices")
    return LLMResponse(
        content=str(choices[0].get("message", {}).get("content", "")),
        usage=data.get("usage") if isinstance(data.get("usage"), dict) else {},
    )


def call_openai_compatible(prompt: str, config: LLMConfig) -> str:
    return call_openai_compatible_response(prompt, config).content


def _usage_int(usage: dict[str, Any], key: str) -> int | None:
    value = usage.get(key)
    try:
        return int(value) if value is not None else None
    except Exception:
        return None


def analyze_sections_with_llm(
    company_name: str,
    ts_code: str,
    period: str,
    sections_text: str,
    config: LLMConfig | None = None,
) -> LLMAnalysis:
    llm_config = config or load_llm_config()
    if not llm_config.enabled:
        return LLMAnalysis(error="LLM_API_KEY or LLM_MODEL missing")
    if not sections_text.strip():
        return LLMAnalysis(error="empty_sections_text")

    prompt = build_report_prompt(company_name, ts_code, period, sections_text)
    try:
        response = call_openai_compatible_response(prompt, llm_config)
        analysis = parse_llm_analysis(response.content)
        analysis.llm_model = llm_config.model or ""
        analysis.llm_base_url = (llm_config.base_url or "").rstrip("/")
        analysis.llm_called_at = datetime.now(timezone.utc).isoformat()
        analysis.prompt_chars = len(prompt)
        analysis.prompt_tokens = _usage_int(response.usage, "prompt_tokens")
        analysis.completion_tokens = _usage_int(response.usage, "completion_tokens")
        analysis.total_tokens = _usage_int(response.usage, "total_tokens")
        return analysis
    except Exception as exc:
        return LLMAnalysis(
            error=f"llm_analysis_failed:{exc}",
            llm_model=llm_config.model or "",
            llm_base_url=(llm_config.base_url or "").rstrip("/"),
            prompt_chars=len(prompt),
        )
