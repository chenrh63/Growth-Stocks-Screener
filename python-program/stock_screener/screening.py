from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import RulesConfig, load_rules
from .env import get_env
from .io import write_table
from .paths import CACHE_DIR, ensure_data_dirs, period_output_path
from .scoring import clamp


from .theme_screen import CONSUMER_INDUSTRIES, MEDICAL_INDUSTRIES, MANUFACTURING_INDUSTRIES as EXPORT_MANUFACTURING_INDUSTRIES


@dataclass(frozen=True)
class ScreenRunConfig:
    period: str
    financial_period: str
    trade_date: str | None = None
    target_count: int = 80
    price_history_days: int = 260
    include_price_history: bool = True
    stock_list_status: str = "L"
    candidate_output_prefix: str = "candidates"
    scored_output_prefix: str = "screened_universe_top500"
    refresh_stock_list: bool = False
    output_dir: Path | None = None
    main_board_only: bool = False


def default_financial_period(target_period: str) -> str:
    year = target_period[:4]
    if target_period.endswith("0630"):
        return f"{year}0331"
    if target_period.endswith("1231"):
        return f"{year}0930"
    return target_period


def _require_tushare():
    token = get_env("TUSHARE_TOKEN")
    if not token:
        raise RuntimeError("TUSHARE_TOKEN missing in .env or .env.txt")
    try:
        import tushare as ts  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"tushare import failed: {exc}") from exc
    return ts.pro_api(token)


def _cache_path(name: str, key: str, suffix: str = ".csv") -> Path:
    path = CACHE_DIR / name
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{key}{suffix}"


def _read_or_fetch_csv(path: Path, fetcher, refresh: bool = False) -> pd.DataFrame:
    if path.exists() and not refresh:
        return pd.read_csv(path, dtype={"ts_code": str, "trade_date": str, "ann_date": str, "end_date": str})
    df = fetcher()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return df


def latest_trade_date(pro, end_date: str | None = None) -> str:
    end = end_date or datetime.now().strftime("%Y%m%d")
    start = (datetime.strptime(end, "%Y%m%d") - timedelta(days=45)).strftime("%Y%m%d")
    try:
        cal = pro.trade_cal(exchange="", start_date=start, end_date=end, is_open="1")
        if cal is not None and not cal.empty:
            dates = cal.sort_values("cal_date")["cal_date"].astype(str).tolist()
            for date in reversed(dates):
                try:
                    df = pro.daily_basic(trade_date=date)
                    if df is not None and not df.empty:
                        return date
                except Exception:
                    continue
    except Exception:
        pass

    cursor = datetime.strptime(end, "%Y%m%d")
    for _ in range(20):
        date = cursor.strftime("%Y%m%d")
        try:
            df = pro.daily_basic(trade_date=date)
            if df is not None and not df.empty:
                return date
        except Exception:
            pass
        cursor -= timedelta(days=1)
    raise RuntimeError("Unable to determine latest trade date")


def fetch_stock_basic(pro, list_status: str = "L", refresh: bool = False) -> pd.DataFrame:
    statuses = [status.strip() for status in str(list_status).split(",") if status.strip()]
    if not statuses:
        statuses = ["L"]
    cache_key = "stock_basic_" + "_".join(statuses)
    path = _cache_path("tushare", cache_key)

    def fetch() -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        for status in statuses:
            df = pro.stock_basic(
                exchange="",
                list_status=status,
                fields="ts_code,symbol,name,area,industry,market,list_date,delist_date",
            )
            if df is not None and not df.empty:
                df = df.copy()
                df["list_status"] = status
                frames.append(df)
        if not frames:
            return pd.DataFrame(columns=["ts_code", "symbol", "name", "area", "industry", "market", "list_date", "delist_date", "list_status"])
        return pd.concat(frames, ignore_index=True).drop_duplicates("ts_code", keep="first")

    return _read_or_fetch_csv(path, fetch, refresh=refresh)


def fetch_daily_basic(pro, trade_date: str) -> pd.DataFrame:
    path = _cache_path("tushare", f"daily_basic_{trade_date}")
    return _read_or_fetch_csv(path, lambda: pro.daily_basic(trade_date=trade_date))


def _normalize_fina_indicator(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "ts_code" not in df.columns:
        return df
    sort_cols = [column for column in ["ts_code", "ann_date", "end_date"] if column in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols)
    return df.drop_duplicates("ts_code", keep="last")


def fetch_fina_indicator(pro, financial_period: str, ts_codes: list[str] | None = None) -> pd.DataFrame:
    path = _cache_path("tushare", f"fina_indicator_{financial_period}")
    if path.exists():
        return _normalize_fina_indicator(pd.read_csv(path, dtype={"ts_code": str, "ann_date": str, "end_date": str}))

    errors: list[str] = []
    for api_name in ["fina_indicator_vip", "fina_indicator"]:
        try:
            method = getattr(pro, api_name)
            df = method(period=financial_period)
            if df is not None and not df.empty:
                df = _normalize_fina_indicator(df)
                path.parent.mkdir(parents=True, exist_ok=True)
                df.to_csv(path, index=False, encoding="utf-8-sig")
                return df
        except Exception as exc:
            errors.append(f"{api_name}:{exc}")

    if not ts_codes:
        raise RuntimeError("Unable to fetch fina_indicator in bulk and no ts_codes provided. " + " | ".join(errors))

    iter_path = _cache_path("tushare", f"fina_indicator_{financial_period}_iter")
    if iter_path.exists():
        return _normalize_fina_indicator(pd.read_csv(iter_path, dtype={"ts_code": str, "ann_date": str, "end_date": str}))

    frames: list[pd.DataFrame] = []
    failed = 0
    for index, ts_code in enumerate(ts_codes, start=1):
        try:
            df = pro.fina_indicator(ts_code=ts_code, period=financial_period)
            if df is not None and not df.empty:
                frames.append(df)
        except Exception:
            failed += 1
        if index % 200 == 0:
            print(f"Fetched fina_indicator {index}/{len(ts_codes)}; failed={failed}")

    if not frames:
        raise RuntimeError("No fina_indicator rows fetched. " + " | ".join(errors))

    result = _normalize_fina_indicator(pd.concat(frames, ignore_index=True))
    iter_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(iter_path, index=False, encoding="utf-8-sig")
    return result


def fetch_daily_for_trade_date(pro, trade_date: str) -> pd.DataFrame:
    path = _cache_path("daily", trade_date)
    return _read_or_fetch_csv(path, lambda: pro.daily(trade_date=trade_date))


def fetch_trade_dates(pro, end_date: str, count: int) -> list[str]:
    start = (datetime.strptime(end_date, "%Y%m%d") - timedelta(days=int(count * 1.7) + 20)).strftime("%Y%m%d")
    cal_path = _cache_path("tushare", f"trade_cal_{start}_{end_date}")
    cal = _read_or_fetch_csv(
        cal_path,
        lambda: pro.trade_cal(exchange="", start_date=start, end_date=end_date, is_open="1"),
    )
    dates = sorted(cal["cal_date"].astype(str).tolist())
    return dates[-count:]


def fetch_price_history(pro, trade_date: str, days: int) -> pd.DataFrame:
    dates = fetch_trade_dates(pro, trade_date, days)
    frames: list[pd.DataFrame] = []
    for date in dates:
        try:
            df = fetch_daily_for_trade_date(pro, date)
            if not df.empty:
                frames.append(df[["ts_code", "trade_date", "close", "pct_chg"]].copy())
        except Exception:
            continue
    if not frames:
        return pd.DataFrame(columns=["ts_code", "drawdown_250d", "return_120d", "return_250d"])

    hist = pd.concat(frames, ignore_index=True)
    hist["trade_date"] = hist["trade_date"].astype(str)
    hist["close"] = pd.to_numeric(hist["close"], errors="coerce")
    hist = hist.dropna(subset=["close"])
    hist = hist.sort_values(["ts_code", "trade_date"])

    rows: list[dict[str, Any]] = []
    for ts_code, group in hist.groupby("ts_code"):
        closes = group["close"].astype(float)
        latest = float(closes.iloc[-1])
        max_close = float(closes.max())
        first = float(closes.iloc[0])
        idx_120 = max(0, len(closes) - 120)
        base_120 = float(closes.iloc[idx_120])
        rows.append(
            {
                "ts_code": ts_code,
                "drawdown_250d": latest / max_close - 1 if max_close > 0 else np.nan,
                "return_120d": latest / base_120 - 1 if base_120 > 0 else np.nan,
                "return_250d": latest / first - 1 if first > 0 else np.nan,
                "price_history_days": len(closes),
            }
        )
    return pd.DataFrame(rows)


def _days_since_list(list_date: Any, as_of: str) -> int:
    try:
        listed = datetime.strptime(str(list_date), "%Y%m%d")
        current = datetime.strptime(as_of, "%Y%m%d")
        return (current - listed).days
    except Exception:
        return 0


def apply_universe_filters(df: pd.DataFrame, rules: RulesConfig, trade_date: str) -> pd.DataFrame:
    work = df.copy()
    work["exclude_reason"] = ""
    name = work["name"].fillna("").astype(str)
    market = work.get("market", "").fillna("").astype(str) if "market" in work.columns else pd.Series("", index=work.index)
    industry = work.get("industry", "").fillna("").astype(str) if "industry" in work.columns else pd.Series("", index=work.index)
    ts_code = work["ts_code"].fillna("").astype(str)

    list_days = (
        work["list_date"].apply(lambda value: _days_since_list(value, trade_date))
        if "list_date" in work.columns
        else pd.Series(9999, index=work.index)
    )
    work["listing_days"] = pd.to_numeric(list_days, errors="coerce").fillna(0).astype(int)
    work["is_recent_listing"] = work["listing_days"] < 730

    st_mask = name.str.contains("ST|\u9000", regex=True, na=False)
    unprofitable_label_mask = name.str.contains("-U", regex=False, na=False)
    bj_mask = ts_code.str.endswith(".BJ") | market.str.contains("\u5317\u4ea4", na=False)
    min_listing_days = int(getattr(rules.candidate_filters, "min_listing_days", 0))
    new_mask = work["listing_days"] < min_listing_days if min_listing_days > 0 else pd.Series(False, index=work.index)
    ai_pattern = "|".join(rules.ai_exclusion_keywords)
    ai_mask = (name + " " + industry).str.contains(ai_pattern, case=False, regex=True, na=False) if ai_pattern else pd.Series(False, index=work.index)
    financial_industries = set(getattr(rules.candidate_filters, "financial_industries", []))
    financial_mask = industry.isin(financial_industries)

    reason_map = [
        (st_mask if rules.candidate_filters.exclude_st else pd.Series(False, index=work.index), "\u0053\u0054/\u9000\u5e02\u98ce\u9669"),
        (unprofitable_label_mask, "\u672a\u76c8\u5229-U\u6807\u8bc6"),
        (bj_mask if rules.candidate_filters.exclude_bj else pd.Series(False, index=work.index), "\u5317\u4ea4\u6240"),
        (financial_mask if rules.candidate_filters.exclude_financial else pd.Series(False, index=work.index), "\u91d1\u878d\u4e1a"),
        (new_mask, f"\u4e0a\u5e02\u672a\u6ee1{min_listing_days}\u5929"),
        (ai_mask, "AI/TMT\u786c\u6392\u9664\u5173\u952e\u8bcd"),
    ]
    for mask, reason in reason_map:
        work.loc[mask, "exclude_reason"] = work.loc[mask, "exclude_reason"].where(
            work.loc[mask, "exclude_reason"].eq(""),
            work.loc[mask, "exclude_reason"] + ";",
        ) + reason

    return work[work["exclude_reason"].eq("")].copy()


def apply_main_board_filter(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    if "ts_code" not in work.columns:
        return work.iloc[0:0].copy()
    ts_code = work["ts_code"].fillna("").astype(str)
    market = work.get("market", "").fillna("").astype(str) if "market" in work.columns else pd.Series("", index=work.index)
    mask = (ts_code.str.endswith(".SH") | ts_code.str.endswith(".SZ")) & market.str.contains("\u4e3b\u677f", na=False)
    return work[mask].copy()

def apply_hard_metric_filters(df: pd.DataFrame, rules: RulesConfig) -> pd.DataFrame:
    work = df.copy()
    for column, threshold in [
        ("total_mv", rules.screening.min_total_mv),
        ("circ_mv", rules.screening.min_circ_mv),
        ("turnover_rate", rules.screening.min_avg_turnover_rate),
    ]:
        if column in work.columns:
            work = work[pd.to_numeric(work[column], errors="coerce").fillna(0) >= threshold]
    if not work.empty:
        work["hard_filter_pass"] = True
    return work


def _first_numeric(row: pd.Series, columns: list[str]) -> float | None:
    for column in columns:
        if column in row.index:
            value = pd.to_numeric(row[column], errors="coerce")
            if pd.notna(value):
                return float(value)
    return None


FINANCIAL_FIELD_GROUPS = [
    ["tr_yoy", "or_yoy", "q_sales_yoy", "revenue_yoy_h1"],
    ["q_netprofit_yoy", "q_profit_yoy", "dt_netprofit_yoy", "profit_dedt_yoy_h1"],
    ["roe_dt", "roe", "roe_waa", "roe_h1"],
    ["grossprofit_margin", "gross_margin", "netprofit_margin"],
    ["ocf_to_or", "salescash_to_or", "ocf_to_np"],
    ["profit_dedt"],
]


def count_missing_financial_groups(row: pd.Series) -> int:
    missing = 0
    for columns in FINANCIAL_FIELD_GROUPS:
        if _first_numeric(row, columns) is None:
            missing += 1
    return missing


def _linear_score(value: float | None, low: float, high: float, inverse: bool = False, missing: float = 50.0) -> float:
    if value is None or pd.isna(value):
        return missing
    score = (float(value) - low) / (high - low) * 100
    if inverse:
        score = 100 - score
    return clamp(score)


def _mean_scores(scores: list[float]) -> float:
    valid = [score for score in scores if pd.notna(score)]
    return float(np.mean(valid)) if valid else 50.0


def compute_growth_score(row: pd.Series) -> float:
    revenue_yoy = _first_numeric(row, ["tr_yoy", "or_yoy", "q_sales_yoy", "revenue_yoy_h1"])
    profit_yoy = _first_numeric(row, ["q_netprofit_yoy", "q_profit_yoy", "dt_netprofit_yoy", "profit_dedt_yoy_h1"])
    roe = _first_numeric(row, ["roe_dt", "roe", "roe_waa", "roe_h1"])
    margin = _first_numeric(row, ["grossprofit_margin", "gross_margin", "netprofit_margin"])
    cash = _first_numeric(row, ["ocf_to_or", "salescash_to_or", "ocf_to_np"])
    scores = [
        _linear_score(revenue_yoy, -5, 70),
        _linear_score(profit_yoy, -10, 150),
        _linear_score(roe, 3, 18),
        _linear_score(margin, 10, 45),
        _linear_score(cash, 0.05, 0.8),
    ]
    return float(np.mean(scores))


def compute_financial_acceleration_score(row: pd.Series) -> float:
    revenue_yoy = _first_numeric(row, ["tr_yoy", "or_yoy", "q_sales_yoy", "revenue_yoy_h1"])
    profit_yoy = _first_numeric(row, ["q_netprofit_yoy", "q_profit_yoy", "dt_netprofit_yoy", "profit_dedt_yoy_h1"])
    cash = _first_numeric(row, ["ocf_to_or", "salescash_to_or", "ocf_to_np"])
    return _mean_scores(
        [
            _linear_score(revenue_yoy, 10, 80, missing=35.0),
            _linear_score(profit_yoy, 20, 180, missing=35.0),
            _linear_score(cash, 0.05, 0.8, missing=45.0),
        ]
    )


def _industry_inverse_percentile(df: pd.DataFrame, column: str) -> pd.Series:
    value = pd.to_numeric(df[column], errors="coerce")
    valid = value.where(value > 0)
    percentile = valid.groupby(df["industry"].fillna("UNKNOWN")).rank(pct=True, ascending=True)
    return (1 - percentile).fillna(0.45) * 100


def compute_valuation_score(df: pd.DataFrame) -> pd.Series:
    parts: list[pd.Series] = []
    for column in ["pe_ttm", "pb", "ps_ttm"]:
        if column in df.columns:
            parts.append(_industry_inverse_percentile(df, column))
    if not parts:
        return pd.Series(50.0, index=df.index)
    return pd.concat(parts, axis=1).mean(axis=1).clip(0, 100)


def compute_mispricing_score(df: pd.DataFrame) -> pd.Series:
    drawdown = pd.to_numeric(df.get("drawdown_250d", pd.Series(np.nan, index=df.index)), errors="coerce")
    industry_return = pd.to_numeric(df.get("industry_return_120d", pd.Series(np.nan, index=df.index)), errors="coerce")
    stock_return = pd.to_numeric(df.get("return_120d", pd.Series(np.nan, index=df.index)), errors="coerce")
    drawdown_score = ((drawdown.abs() - 0.10) / 0.45 * 100).clip(0, 100)
    weak_industry_score = ((-industry_return - 0.05) / 0.30 * 100).clip(0, 100)
    beta_drag_score = ((industry_return - stock_return).abs() / 0.35 * 100).clip(0, 100)
    combined = pd.concat([drawdown_score, weak_industry_score, beta_drag_score], axis=1).mean(axis=1)
    return combined.fillna(50).clip(0, 100)


def compute_quality_score(row: pd.Series, rules: RulesConfig) -> float:
    total_mv = _first_numeric(row, ["total_mv"])
    circ_mv = _first_numeric(row, ["circ_mv"])
    turnover = _first_numeric(row, ["turnover_rate"])
    debt = _first_numeric(row, ["debt_to_assets"])
    roe = _first_numeric(row, ["roe_dt", "roe", "roe_waa"])
    score = 70.0
    if total_mv is not None and total_mv < rules.screening.min_total_mv:
        score -= 20
    if circ_mv is not None and circ_mv < rules.screening.min_circ_mv:
        score -= 15
    if turnover is not None and turnover < rules.screening.min_avg_turnover_rate:
        score -= 15
    if debt is not None and debt > 75:
        score -= 15
    if roe is not None and roe < 0:
        score -= 20
    return clamp(score)


def _theme_base(row: pd.Series) -> tuple[str, float, float, float, float]:
    industry = str(row.get("industry", ""))
    revenue_yoy = _first_numeric(row, ["tr_yoy", "or_yoy", "q_sales_yoy", "revenue_yoy_h1"])
    profit_yoy = _first_numeric(row, ["q_netprofit_yoy", "q_profit_yoy", "dt_netprofit_yoy", "profit_dedt_yoy_h1"])
    margin = _first_numeric(row, ["grossprofit_margin", "gross_margin", "netprofit_margin"])
    roe = _first_numeric(row, ["roe_dt", "roe", "roe_waa", "roe_h1"])
    growth_intensity = _mean_scores(
        [
            _linear_score(revenue_yoy, 10, 80, missing=0.0),
            _linear_score(profit_yoy, 20, 180, missing=0.0),
            _linear_score(roe, 5, 20, missing=0.0),
        ]
    )
    margin_score = _linear_score(margin, 15, 45, missing=35.0)
    return industry, revenue_yoy or np.nan, profit_yoy or np.nan, growth_intensity, margin_score


def compute_theme_scores(row: pd.Series) -> dict[str, Any]:
    industry, revenue_yoy, profit_yoy, growth_intensity, margin_score = _theme_base(row)
    hits: list[str] = []
    consumer = 0.0
    medical = 0.0
    export = 0.0

    if industry in CONSUMER_INDUSTRIES:
        consumer = clamp(growth_intensity * 0.72 + margin_score * 0.18 + 10)
        hits.append("consumer_industry")
        if pd.notna(revenue_yoy) and revenue_yoy >= 20:
            hits.append("consumer_revenue_yoy>=20")
        if pd.notna(profit_yoy) and profit_yoy >= 40:
            hits.append("consumer_profit_yoy>=40")
    if industry in MEDICAL_INDUSTRIES:
        medical = clamp(growth_intensity * 0.68 + margin_score * 0.22 + 10)
        hits.append("medical_industry")
        if pd.notna(revenue_yoy) and revenue_yoy >= 10:
            hits.append("medical_revenue_yoy>=10")
        if pd.notna(profit_yoy) and profit_yoy >= 40:
            hits.append("medical_profit_yoy>=40")
    if industry in EXPORT_MANUFACTURING_INDUSTRIES:
        export = clamp(growth_intensity * 0.75 + margin_score * 0.10 + 10)
        hits.append("export_manufacturing_industry")
        if pd.notna(revenue_yoy) and revenue_yoy >= 20:
            hits.append("export_revenue_yoy>=20")
        if pd.notna(profit_yoy) and profit_yoy >= 50:
            hits.append("export_profit_yoy>=50")

    scores = {
        "\u6d88\u8d39\u9ad8\u6210\u957f": consumer,
        "\u533b\u836f\u533b\u68b0\u91cf\u4ef7\u6062\u590d": medical,
        "\u5236\u9020\u4e1a\u51fa\u6d77": export,
    }
    primary_theme = max(scores, key=scores.get)
    theme_score = scores[primary_theme]
    if theme_score <= 0:
        primary_theme = "\u975e\u4e3b\u9898\u9ad8\u6210\u957f"
    return {
        "consumer_growth_score": round(consumer, 2),
        "medical_recovery_score": round(medical, 2),
        "export_growth_score": round(export, 2),
        "theme_score": round(theme_score, 2),
        "primary_theme": primary_theme,
        "theme_hits": ";".join(dict.fromkeys(hits)),
    }


def score_candidates(df: pd.DataFrame, rules: RulesConfig) -> pd.DataFrame:
    work = df.copy()
    work["growth_score"] = work.apply(compute_growth_score, axis=1).round(2)
    work["financial_acceleration_score"] = work.apply(compute_financial_acceleration_score, axis=1).round(2)
    work["valuation_score"] = compute_valuation_score(work).round(2)
    work["mispricing_score"] = compute_mispricing_score(work).round(2)
    work["quality_score"] = work.apply(lambda row: compute_quality_score(row, rules), axis=1).round(2)
    theme = pd.DataFrame([compute_theme_scores(row) for _, row in work.iterrows()], index=work.index)
    work = pd.concat([work, theme], axis=1)
    work["financial_missing_fields"] = work.apply(count_missing_financial_groups, axis=1)
    weights = rules.screening.weights
    work["total_score"] = (
        work["growth_score"] * float(weights.get("growth", 0.35))
        + work["theme_score"] * float(weights.get("theme", 0.20))
        + work["valuation_score"] * float(weights.get("valuation", 0.20))
        + work["mispricing_score"] * float(weights.get("mispricing", 0.15))
        + work["quality_score"] * float(weights.get("quality", 0.10))
    ).round(2)
    return work.sort_values("total_score", ascending=False)


def prepare_screening_frame(
    basic: pd.DataFrame,
    daily_basic: pd.DataFrame,
    fina: pd.DataFrame,
    price_history: pd.DataFrame,
) -> pd.DataFrame:
    df = basic.merge(daily_basic, on="ts_code", how="inner", suffixes=("", "_daily"))
    df = df.merge(fina, on="ts_code", how="left", suffixes=("", "_fina"))
    df = df.copy()
    if not price_history.empty:
        df = df.merge(price_history, on="ts_code", how="left")
        if "return_120d" in df.columns:
            df = df.assign(industry_return_120d=df.groupby("industry")["return_120d"].transform("median"))
    else:
        df = df.assign(
            drawdown_250d=np.nan,
            return_120d=np.nan,
            return_250d=np.nan,
            industry_return_120d=np.nan,
        )
    return df


def filter_scored_candidates(scored: pd.DataFrame, rules: RulesConfig, target_count: int) -> pd.DataFrame:
    work = apply_hard_metric_filters(scored, rules)
    if "growth_score" in work.columns:
        work = work[pd.to_numeric(work["growth_score"], errors="coerce").fillna(0) >= rules.screening.min_financial_score]
    if "pe_ttm" in work.columns:
        pe = pd.to_numeric(work["pe_ttm"], errors="coerce")
        work = work[(pe > 0) | pe.isna()]
    if "drawdown_250d" in work.columns:
        drawdown = pd.to_numeric(work["drawdown_250d"], errors="coerce")
        work = work[drawdown.isna() | (drawdown <= rules.screening.min_drawdown_250d)]
    if "return_120d" in work.columns:
        ret_120 = pd.to_numeric(work["return_120d"], errors="coerce")
        work = work[ret_120.isna() | (ret_120 <= rules.screening.max_return_120d)]
    if "industry_return_120d" in work.columns:
        industry_ret = pd.to_numeric(work["industry_return_120d"], errors="coerce")
        work = work[industry_ret.isna() | (industry_ret <= rules.screening.max_industry_return_120d)]
    if rules.screening.require_positive_profit_dedt and "profit_dedt" in work.columns:
        profit_dedt = pd.to_numeric(work["profit_dedt"], errors="coerce")
        work = work[profit_dedt > 0]
    return work.head(target_count).copy()


def run_market_screen(config: ScreenRunConfig, rules: RulesConfig | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    ensure_data_dirs()
    rules = rules or load_rules()
    pro = _require_tushare()
    trade_date = config.trade_date or latest_trade_date(pro)

    basic = fetch_stock_basic(pro, config.stock_list_status, refresh=config.refresh_stock_list)
    daily_basic = fetch_daily_basic(pro, trade_date)
    pre_frame = basic.merge(daily_basic, on="ts_code", how="inner", suffixes=("", "_daily"))
    pre_universe = apply_universe_filters(pre_frame, rules, trade_date)
    if config.main_board_only:
        pre_universe = apply_main_board_filter(pre_universe)
    pre_universe = apply_hard_metric_filters(pre_universe, rules)
    fina = fetch_fina_indicator(pro, config.financial_period, pre_universe["ts_code"].astype(str).tolist())
    price_history = (
        fetch_price_history(pro, trade_date, config.price_history_days)
        if config.include_price_history and config.price_history_days > 0
        else pd.DataFrame()
    )

    frame = prepare_screening_frame(basic, daily_basic, fina, price_history)
    universe = apply_universe_filters(frame, rules, trade_date)
    if config.main_board_only:
        universe = apply_main_board_filter(universe)
    universe = apply_hard_metric_filters(universe, rules)
    scored = score_candidates(universe, rules)
    selected = filter_scored_candidates(scored, rules, config.target_count)

    selected["screen_period"] = config.period
    selected["financial_period"] = config.financial_period
    selected["trade_date"] = trade_date
    selected["screen_reason"] = selected.apply(build_screen_reason, axis=1)

    output_cols = [
        "ts_code",
        "name",
        "industry",
        "area",
        "market",
        "list_date",
        "listing_days",
        "is_recent_listing",
        "hard_filter_pass",
        "trade_date",
        "financial_period",
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
        "pe_ttm",
        "pb",
        "ps_ttm",
        "total_mv",
        "circ_mv",
        "turnover_rate",
        "drawdown_250d",
        "return_120d",
        "return_250d",
        "industry_return_120d",
        "tr_yoy",
        "or_yoy",
        "q_sales_yoy",
        "q_netprofit_yoy",
        "q_profit_yoy",
        "roe",
        "roe_dt",
        "grossprofit_margin",
        "netprofit_margin",
        "ocf_to_or",
        "salescash_to_or",
        "debt_to_assets",
        "financial_missing_fields",
        "screen_reason",
    ]
    output_cols = [column for column in output_cols if column in selected.columns]
    selected_output = selected[output_cols + [column for column in selected.columns if column not in output_cols]]

    write_table(selected_output, period_output_path(config.candidate_output_prefix, config.period, ".xlsx", output_dir=config.output_dir))
    write_table(selected_output, period_output_path(config.candidate_output_prefix, config.period, ".csv", output_dir=config.output_dir))
    write_table(scored.head(500), period_output_path(config.scored_output_prefix, config.period, ".xlsx", output_dir=config.output_dir))
    return selected_output, scored


def build_screen_reason(row: pd.Series) -> str:
    parts = [
        f"growth={row.get('growth_score', '')}",
        f"theme={row.get('theme_score', '')}",
        f"theme_name={row.get('primary_theme', '')}",
        f"valuation={row.get('valuation_score', '')}",
        f"mispricing={row.get('mispricing_score', '')}",
        f"quality={row.get('quality_score', '')}",
    ]
    industry_return = row.get("industry_return_120d", np.nan)
    drawdown = row.get("drawdown_250d", np.nan)
    if pd.notna(drawdown):
        parts.append(f"drawdown_250d={float(drawdown):.1%}")
    if pd.notna(industry_return):
        parts.append(f"industry_return_120d={float(industry_return):.1%}")
    return "; ".join(parts)


