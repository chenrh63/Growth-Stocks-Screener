from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .io import read_table, write_table
from .paths import OUTPUT_DIR, REPORT_SECTION_DIR, ensure_data_dirs, period_output_path

CONSUMER_INDUSTRIES = {"白酒", "食品", "软饮料", "服饰", "种植业", "旅游景点", "文教休闲"}
MEDICAL_INDUSTRIES = {"化学制药", "生物制药", "中成药", "医疗保健", "医药商业", "医疗器械"}
MANUFACTURING_INDUSTRIES = {"专用机械", "工程机械", "电气设备", "机械基件", "化工机械", "运输设备", "汽车配件", "装修装饰"}

THEMES = {
    "消费周期低位高成长": {
        "industries": CONSUMER_INDUSTRIES,
        "keywords": ["消费", "销售规模", "售价", "价格", "涨价", "客流", "旅游", "门店", "渠道", "金针菇", "白酒", "饮料", "采购"],
    },
    "医药医械集采后修复": {
        "industries": MEDICAL_INDUSTRIES,
        "keywords": ["集采", "医保", "中标", "院内", "注册证", "获批", "临床", "新药", "处方", "销量", "毛利率", "恢复"],
    },
    "制造业出海遗珠": {
        "industries": MANUFACTURING_INDUSTRIES,
        "keywords": ["海外", "境外", "外销", "出口", "印度", "欧洲", "美国", "东南亚", "国际", "全球", "海外订单"],
    },
}
VOLUME_PRICE_KEYWORDS = ["量价", "销量", "售价", "价格", "毛利率", "产能", "产能释放", "订单", "客户", "交付", "销售增长"]
RISK_KEYWORDS = ["现金流", "为负", "恶化", "应收", "存货", "减值", "价格回落", "缺乏", "不明朗", "不确定", "单一项目", "全部交付"]


def _num(row: pd.Series, columns: list[str]) -> float:
    for column in columns:
        if column in row.index:
            value = pd.to_numeric(row[column], errors="coerce")
            if pd.notna(value):
                return float(value)
    return np.nan


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    if pd.isna(value):
        return 0.0
    return float(max(low, min(high, value)))


def _linear(value: float, low: float, high: float) -> float:
    if pd.isna(value):
        return 0.0
    return _clamp((float(value) - low) / (high - low) * 100)


def _keyword_hits(text: str, keywords: list[str]) -> list[str]:
    return [keyword for keyword in keywords if keyword in text]


def _keyword_score(text: str, keywords: list[str]) -> float:
    hits = len(_keyword_hits(text, keywords))
    return _clamp(hits / max(3, len(keywords) * 0.45) * 100)


def _load(prefix: str, period: str) -> pd.DataFrame:
    for suffix in [".xlsx", ".csv"]:
        path = period_output_path(prefix, period, suffix)
        if path.exists():
            return read_table(path)
    raise FileNotFoundError(f"Missing {prefix}_{period}.xlsx/csv")


def _evidence(row: pd.Series) -> str:
    raw = row.get("evidence_json")
    if isinstance(raw, str) and raw.strip():
        try:
            items = json.loads(raw)
            quotes = []
            for item in items[:6]:
                claim = str(item.get("claim", "")).strip()
                quote = str(item.get("quote", "")).strip()
                if quote:
                    quotes.append(f"{claim}: {quote}" if claim else quote)
            if quotes:
                return "\n".join(quotes)
        except Exception:
            pass
    value = row.get("evidence_quotes", "")
    return "" if pd.isna(value) else str(value)


def _section_text(period: str, ts_code: str, section_path: Any) -> str:
    paths = []
    if isinstance(section_path, str) and section_path.strip():
        paths.append(Path(section_path))
    paths.append(REPORT_SECTION_DIR / f"{period}_{ts_code}.txt")
    for path in paths:
        if path.exists():
            return path.read_text(encoding="utf-8", errors="ignore")[:18000]
    return ""


def load_base(period: str) -> pd.DataFrame:
    analysis = _load("report_analysis", period)
    top500 = _load("screened_universe_top500", period)
    analysis["ts_code"] = analysis["ts_code"].astype(str)
    top500["ts_code"] = top500["ts_code"].astype(str)
    cols = [
        "ts_code", "valuation_score", "mispricing_score", "pe_ttm", "pb", "ps_ttm", "total_mv", "circ_mv",
        "drawdown_250d", "return_120d", "return_250d", "q_sales_yoy", "tr_yoy", "or_yoy",
        "dt_netprofit_yoy", "q_netprofit_yoy", "grossprofit_margin", "netprofit_margin", "screen_reason",
    ]
    cols = [column for column in cols if column in top500.columns]
    base = analysis.merge(top500[cols], on="ts_code", how="left", suffixes=("", "_market"))
    texts = []
    evidences = []
    for _, row in base.iterrows():
        evidence = _evidence(row)
        text = "\n".join(
            part for part in [
                str(row.get("reasoning", "")), evidence, _section_text(period, str(row["ts_code"]), row.get("section_path"))
            ] if part and part != "nan"
        )
        texts.append(text)
        evidences.append(evidence)
    base["combined_text"] = texts
    base["source_evidence"] = evidences
    return base


def classify(base: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in base.iterrows():
        text = str(row.get("combined_text", ""))
        industry = str(row.get("industry", ""))
        revenue_yoy = _num(row, ["q_sales_yoy", "tr_yoy", "or_yoy"])
        profit_yoy = _num(row, ["dt_netprofit_yoy", "q_netprofit_yoy"])
        drawdown = _num(row, ["drawdown_250d"])
        ret120 = _num(row, ["return_120d"])
        valuation = _num(row, ["valuation_score"])
        growth_cont = _num(row, ["growth_continues_score"])
        visibility = _num(row, ["visibility_score"])
        quality = _num(row, ["quality_of_growth_score"])
        risk = _num(row, ["risk_deterioration_score"])
        text_verdict = str(row.get("text_verdict", ""))
        candidate_status = str(row.get("candidate_status", ""))

        low_score = max(
            _linear(abs(drawdown), 0.08, 0.35) if pd.notna(drawdown) and drawdown < 0 else 0,
            _linear(-ret120, -0.05, 0.25) if pd.notna(ret120) else 0,
            _linear(valuation, 35, 80),
        )
        growth_score = max(_linear(revenue_yoy, 10, 80), _linear(profit_yoy, 20, 150), _linear(growth_cont, 50, 90))
        volume_price_score = _keyword_score(text, VOLUME_PRICE_KEYWORDS)
        risk_penalty = _linear(risk, 35, 80) + min(25, _keyword_score(text, RISK_KEYWORDS) * 0.25)
        if "剔除" in text_verdict or candidate_status == "C_reject":
            risk_penalty += 30

        for theme, rule in THEMES.items():
            industry_match = industry in rule["industries"]
            keyword_score = _keyword_score(text, rule["keywords"])
            keyword_hits = _keyword_hits(text, rule["keywords"])
            if theme == "消费周期低位高成长":
                hard_match = industry_match and revenue_yoy >= 20
                score = 0.26 * growth_score + 0.24 * low_score + 0.18 * keyword_score + 0.16 * quality + 0.10 * visibility + 0.06 * volume_price_score - 0.22 * risk_penalty
            elif theme == "医药医械集采后修复":
                hard_match = industry_match and (revenue_yoy >= 10 or profit_yoy >= 40)
                score = 0.24 * growth_score + 0.16 * low_score + 0.26 * keyword_score + 0.12 * volume_price_score + 0.12 * quality + 0.10 * visibility - 0.22 * risk_penalty
            else:
                hard_match = industry_match and keyword_score > 0 and revenue_yoy >= 20
                score = 0.24 * growth_score + 0.30 * keyword_score + 0.12 * volume_price_score + 0.12 * visibility + 0.12 * quality + 0.10 * low_score - 0.20 * risk_penalty
            if not hard_match:
                continue
            score = round(_clamp(score), 2)
            if score >= 68 and risk <= 45 and "剔除" not in text_verdict and candidate_status != "C_reject":
                status = "A_key_watch"
            elif score >= 50 and "剔除" not in text_verdict and candidate_status != "C_reject":
                status = "B_watch"
            else:
                status = "C_reject_or_weak"
            rows.append({
                "theme": theme,
                "theme_status": status,
                "theme_score": score,
                "ts_code": row.get("ts_code"),
                "name": row.get("name"),
                "industry": industry,
                "drawdown_250d": drawdown,
                "return_120d": ret120,
                "pe_ttm": _num(row, ["pe_ttm"]),
                "pb": _num(row, ["pb"]),
                "revenue_yoy": revenue_yoy,
                "deducted_profit_yoy": profit_yoy,
                "growth_continues_score": growth_cont,
                "visibility_score": visibility,
                "quality_of_growth_score": quality,
                "risk_deterioration_score": risk,
                "text_verdict": text_verdict,
                "candidate_status": candidate_status,
                "low_position_score": round(low_score, 2),
                "growth_signal_score": round(growth_score, 2),
                "theme_keyword_hits": "、".join(keyword_hits),
                "volume_price_hits": "、".join(_keyword_hits(text, VOLUME_PRICE_KEYWORDS)),
                "risk_hits": "、".join(_keyword_hits(text, RISK_KEYWORDS)),
                "reasoning": row.get("reasoning", ""),
                "evidence_quotes": row.get("source_evidence", ""),
            })
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    return result.sort_values(["theme", "theme_status", "theme_score"], ascending=[True, True, False])


def _fmt_pct(value: Any) -> str:
    value = pd.to_numeric(value, errors="coerce")
    return "" if pd.isna(value) else f"{value:.1%}"


def _fmt_yoy(value: Any) -> str:
    value = pd.to_numeric(value, errors="coerce")
    return "" if pd.isna(value) else f"{value:.1f}%"


def _markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "无"
    columns = list(df.columns)
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return "\n".join(lines)


def write_report(result: pd.DataFrame, period: str) -> Path:
    path = OUTPUT_DIR / f"theme_screen_q1_{period}.md"
    lines = [
        f"# 一季报主题筛选结果（{period}）",
        "",
        "筛选范围：已完成一季报文本分析的 30 只初筛股；财务/估值/低位指标来自 `screened_universe_top500_20260331`。",
        "`A_key_watch` 表示主题和证据较强；`B_watch` 表示逻辑存在但证据或风险有缺口；`C_reject_or_weak` 表示不符合或应剔除。",
        "",
    ]
    if result.empty:
        lines.append("没有匹配结果。")
    else:
        for theme, group in result.groupby("theme", sort=False):
            lines.append(f"## {theme}")
            show = group[["theme_status", "ts_code", "name", "industry", "theme_score", "drawdown_250d", "return_120d", "revenue_yoy", "deducted_profit_yoy", "risk_deterioration_score", "theme_keyword_hits"]].copy()
            show["drawdown_250d"] = show["drawdown_250d"].map(_fmt_pct)
            show["return_120d"] = show["return_120d"].map(_fmt_pct)
            show["revenue_yoy"] = show["revenue_yoy"].map(_fmt_yoy)
            show["deducted_profit_yoy"] = show["deducted_profit_yoy"].map(_fmt_yoy)
            lines.append(_markdown_table(show))
            lines.append("")
            for _, row in group.head(5).iterrows():
                evidence = str(row.get("evidence_quotes", "")).replace("\n", "；")[:450]
                lines.append(f"- {row['name']}（{row['ts_code']}）：{row['theme_status']}，分数 {row['theme_score']}。证据：{evidence}")
            lines.append("")
    lines.extend([
        "## 使用限制",
        "- 这是研究筛选，不是买卖建议。",
        "- 一季报文本较短，很多公司没有管理层讨论，半年报验证更关键。",
        "- 医药主题如未出现“集采/医保/中标”原文，只能视为医药成长候选，不能直接认定为集采反转。",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run(period: str) -> pd.DataFrame:
    ensure_data_dirs()
    result = classify(load_base(period))
    write_table(result, period_output_path("theme_screen_q1", period, ".xlsx"))
    write_table(result, period_output_path("theme_screen_q1", period, ".csv"))
    report = write_report(result, period)
    print(f"Theme rows: {len(result)}")
    print(period_output_path("theme_screen_q1", period, ".xlsx"))
    print(report)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify Q1 report-analysis candidates into custom themes.")
    parser.add_argument("--period", default="20260331")
    args = parser.parse_args()
    result = run(args.period)
    if not result.empty:
        cols = ["theme", "theme_status", "theme_score", "ts_code", "name", "industry", "drawdown_250d", "revenue_yoy", "deducted_profit_yoy"]
        print(result[cols].to_string(index=False))


if __name__ == "__main__":
    main()
