from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .backtest_common import make_weekly_bars, summarize_trades
from .config import load_rules
from .confirmation_backtest import (
    ConfirmationBacktestConfig,
    add_confirmation_indicators,
    normalize_daily,
    simulate_confirmation_stock,
)
from .env import get_env
from .io import write_table
from .paths import CACHE_DIR, DATA_DIR, OUTPUT_DIR, ensure_data_dirs
from .screening import ScreenRunConfig, latest_trade_date, run_market_screen


HISTORICAL_DAILY_DIR = DATA_DIR / "backtest_data" / "historical_daily"


@dataclass(frozen=True)
class HistoricalBacktestConfig:
    start_period: str = "20210331"
    end_period: str = "20260331"
    quarters: tuple[str, ...] = ("0331",)
    target_count: int = 30
    price_history_days: int = 260
    include_price_history: bool = True
    stock_list_status: str = "L,D"
    start_date: str = "20200101"
    end_date: str | None = None
    strong_score: float = 70.0
    breakout_weeks: tuple[int, ...] = (4, 8)
    volume_ratio_min: tuple[float, ...] = (1.0, 1.2)
    stop_loss: tuple[float, ...] = (0.08, 0.10, 0.12)
    max_hold_weeks: tuple[int, ...] = (6, 8, 12)
    max_signal_wait_weeks: tuple[int, ...] = (4, 8)
    slippage_bps: float = 15.0
    commission_bps: float = 8.0
    min_trades: int = 30
    output_tag: str | None = None
    force_refresh_daily: bool = False


def _pro_api():
    token = get_env("TUSHARE_TOKEN")
    if not token:
        raise RuntimeError("TUSHARE_TOKEN missing in .env or .env.txt")
    try:
        import tushare as ts  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"tushare import failed: {exc}") from exc
    return ts.pro_api(token)


def _parse_items(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _parse_ints(value: str) -> tuple[int, ...]:
    return tuple(int(item) for item in _parse_items(value))


def _parse_floats(value: str) -> tuple[float, ...]:
    return tuple(float(item) for item in _parse_items(value))


def generate_periods(start_period: str, end_period: str, quarters: tuple[str, ...]) -> list[str]:
    start_year = int(start_period[:4])
    end_year = int(end_period[:4])
    periods: list[str] = []
    for year in range(start_year, end_year + 1):
        for quarter in quarters:
            period = f"{year}{quarter}"
            if start_period <= period <= end_period:
                periods.append(period)
    return sorted(periods)


def report_deadline(period: str) -> str:
    year = int(period[:4])
    suffix = period[4:]
    if suffix == "0331":
        return f"{year}0430"
    if suffix == "0630":
        return f"{year}0831"
    if suffix == "0930":
        return f"{year}1031"
    if suffix == "1231":
        return f"{year + 1}0430"
    raise ValueError(f"Unsupported report period suffix: {period}")


def _trade_cal_cache_path(start_date: str, end_date: str) -> Path:
    path = CACHE_DIR / "tushare"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"trade_cal_next_{start_date}_{end_date}.csv"


def next_open_trade_date(pro, start_date: str) -> str:
    end_date = (datetime.strptime(start_date, "%Y%m%d") + timedelta(days=20)).strftime("%Y%m%d")
    path = _trade_cal_cache_path(start_date, end_date)
    if path.exists():
        cal = pd.read_csv(path, dtype={"cal_date": str})
    else:
        cal = pro.trade_cal(exchange="", start_date=start_date, end_date=end_date, is_open="1")
        if cal is None or cal.empty:
            raise RuntimeError(f"No open trade date found after {start_date}")
        cal.to_csv(path, index=False, encoding="utf-8-sig")
    dates = sorted(cal["cal_date"].astype(str).tolist())
    for date in dates:
        if date >= start_date:
            return date
    raise RuntimeError(f"No open trade date found after {start_date}")


def _safe_code(ts_code: str) -> str:
    return str(ts_code).replace(".", "_")


def _adjust_ohlc(df: pd.DataFrame, adj: pd.DataFrame) -> pd.DataFrame:
    if df.empty or adj.empty or "adj_factor" not in adj.columns:
        return df
    work = df.merge(adj[["ts_code", "trade_date", "adj_factor"]], on=["ts_code", "trade_date"], how="left")
    work["adj_factor"] = pd.to_numeric(work["adj_factor"], errors="coerce")
    if work["adj_factor"].notna().sum() == 0:
        return df
    latest_factor = work.sort_values("trade_date")["adj_factor"].dropna().iloc[-1]
    scale = work["adj_factor"] / latest_factor
    for column in ["open", "high", "low", "close"]:
        work[column] = pd.to_numeric(work[column], errors="coerce") * scale
    return work.drop(columns=["adj_factor"])


def fetch_historical_daily(
    pro,
    ts_codes: list[str],
    start_date: str,
    end_date: str,
    force_refresh: bool = False,
) -> pd.DataFrame:
    HISTORICAL_DAILY_DIR.mkdir(parents=True, exist_ok=True)
    frames: list[pd.DataFrame] = []
    failed: list[str] = []
    for index, ts_code in enumerate(sorted(set(ts_codes)), start=1):
        cache_path = HISTORICAL_DAILY_DIR / f"{_safe_code(ts_code)}_{start_date}_{end_date}.csv"
        if cache_path.exists() and not force_refresh:
            df = pd.read_csv(cache_path, dtype={"ts_code": str, "trade_date": str})
        else:
            try:
                df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                if df is None or df.empty:
                    failed.append(ts_code)
                    continue
                try:
                    adj = pro.adj_factor(ts_code=ts_code, start_date=start_date, end_date=end_date)
                    df = _adjust_ohlc(df, adj)
                except Exception as exc:
                    print(f"adj_factor failed for {ts_code}: {exc}")
                keep = [column for column in ["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"] if column in df.columns]
                df = df[keep].copy()
                df.to_csv(cache_path, index=False, encoding="utf-8-sig")
            except Exception as exc:
                failed.append(ts_code)
                print(f"daily fetch failed for {ts_code}: {exc}")
                continue
        if not df.empty:
            frames.append(df)
        if index % 20 == 0:
            print(f"Fetched historical daily {index}/{len(set(ts_codes))}; failed={len(failed)}")
    if not frames:
        raise RuntimeError("No historical daily data fetched from Tushare")
    if failed:
        print("Historical daily failed codes: " + ",".join(failed[:30]) + ("..." if len(failed) > 30 else ""))
    return normalize_daily(pd.concat(frames, ignore_index=True))


def _ensure_event_dates(universe: pd.DataFrame, screen_trade_date: str) -> pd.DataFrame:
    work = universe.copy()
    screen_ts = pd.to_datetime(screen_trade_date, format="%Y%m%d", errors="coerce")
    if "ann_date" in work.columns:
        ann = pd.to_datetime(work["ann_date"].astype(str), format="%Y%m%d", errors="coerce")
    else:
        ann = pd.Series(pd.NaT, index=work.index)
    work = work[ann.isna() | (ann <= screen_ts)].copy()
    ann = ann.loc[work.index].fillna(screen_ts)
    work["ann_date"] = ann
    work["screen_trade_date"] = screen_trade_date
    return work


def build_historical_universe(config: HistoricalBacktestConfig, pro) -> pd.DataFrame:
    rules = load_rules()
    end_date = config.end_date or latest_trade_date(pro)
    frames: list[pd.DataFrame] = []
    periods = generate_periods(config.start_period, config.end_period, config.quarters)
    for period in periods:
        deadline = report_deadline(period)
        if deadline > end_date:
            print(f"Skip {period}: report deadline {deadline} after backtest end {end_date}")
            continue
        trade_date = next_open_trade_date(pro, deadline)
        if trade_date > end_date:
            print(f"Skip {period}: screen trade date {trade_date} after backtest end {end_date}")
            continue
        print(f"Screening {period} as of {trade_date}")
        selected, _ = run_market_screen(
            ScreenRunConfig(
                period=period,
                financial_period=period,
                trade_date=trade_date,
                target_count=config.target_count,
                price_history_days=config.price_history_days,
                include_price_history=config.include_price_history,
                stock_list_status=config.stock_list_status,
            ),
            rules=rules,
        )
        if selected.empty:
            continue
        selected = _ensure_event_dates(selected, trade_date)
        if selected.empty:
            continue
        score = pd.to_numeric(selected.get("total_score", pd.Series(np.nan, index=selected.index)), errors="coerce")
        selected["candidate_status"] = np.where(score >= config.strong_score, "A_financial_strong", "B_financial_watch")
        selected["event_period"] = period
        selected["report_deadline"] = deadline
        frames.append(selected)
    if not frames:
        return pd.DataFrame()
    universe = pd.concat(frames, ignore_index=True)
    universe["event_id"] = universe["event_period"].astype(str) + "_" + universe["ts_code"].astype(str)
    return universe.drop_duplicates("event_id", keep="first")


def build_strategy_configs(config: HistoricalBacktestConfig) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for breakout, volume_ratio, stop_loss, hold_weeks, wait_weeks in product(
        config.breakout_weeks,
        config.volume_ratio_min,
        config.stop_loss,
        config.max_hold_weeks,
        config.max_signal_wait_weeks,
    ):
        strategy_id = (
            f"b{breakout}_v{int(volume_ratio * 100):03d}_"
            f"s{int(stop_loss * 100):02d}_h{hold_weeks}_w{wait_weeks}"
        )
        rows.append(
            {
                "strategy_id": strategy_id,
                "breakout_weeks": breakout,
                "volume_ratio_min": volume_ratio,
                "stop_loss": stop_loss,
                "max_hold_weeks": hold_weeks,
                "max_signal_wait_weeks": wait_weeks,
                "slippage_bps": config.slippage_bps,
                "commission_bps": config.commission_bps,
            }
        )
    return pd.DataFrame(rows)


def _strategy_config(row: pd.Series) -> ConfirmationBacktestConfig:
    return ConfirmationBacktestConfig(
        period="historical",
        statuses=("A_financial_strong", "B_financial_watch"),
        breakout_weeks=int(row["breakout_weeks"]),
        volume_ratio_min=float(row["volume_ratio_min"]),
        stop_loss=float(row["stop_loss"]),
        slippage_bps=float(row["slippage_bps"]),
        commission_bps=float(row["commission_bps"]),
        max_hold_weeks=int(row["max_hold_weeks"]),
        max_signal_wait_weeks=int(row["max_signal_wait_weeks"]),
        output_tag=str(row["strategy_id"]),
    )


def _format_trade_dates(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return trades
    work = trades.copy()
    for column in ["ann_date", "signal_week", "entry_date", "exit_date", "screen_trade_date"]:
        if column in work.columns:
            work[column] = pd.to_datetime(work[column], errors="coerce").dt.strftime("%Y-%m-%d")
    work["return_pct"] = pd.to_numeric(work["return_pct"], errors="coerce").round(6)
    work["return_pct_display"] = (work["return_pct"] * 100).round(2)
    return work


def summarize_by_strategy(trades: pd.DataFrame, params: pd.DataFrame, event_count: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, param in params.iterrows():
        strategy_id = str(param["strategy_id"])
        group = trades[trades["strategy_id"] == strategy_id] if not trades.empty else pd.DataFrame()
        base = summarize_trades(group, event_count).iloc[0].to_dict()
        base.update(param.to_dict())
        base["event_count"] = event_count
        base["trade_coverage"] = float(base["trade_count"] / event_count) if event_count else np.nan
        rows.append(base)
    return pd.DataFrame(rows)


def summarize_yearly(trades: pd.DataFrame, params: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    work = trades.copy()
    work["entry_year"] = pd.to_datetime(work["entry_date"], errors="coerce").dt.year
    rows: list[dict[str, Any]] = []
    for (strategy_id, year), group in work.dropna(subset=["entry_year"]).groupby(["strategy_id", "entry_year"]):
        base = summarize_trades(group, group["event_id"].nunique()).iloc[0].to_dict()
        base["strategy_id"] = strategy_id
        base["entry_year"] = int(year)
        rows.append(base)
    yearly = pd.DataFrame(rows)
    if yearly.empty:
        return yearly
    keep = ["strategy_id", "breakout_weeks", "volume_ratio_min", "stop_loss", "max_hold_weeks", "max_signal_wait_weeks"]
    return yearly.merge(params[keep], on="strategy_id", how="left")


def add_robustness_columns(summary: pd.DataFrame, yearly: pd.DataFrame, min_trades: int) -> pd.DataFrame:
    work = summary.copy()
    if yearly.empty:
        work["positive_year_rate"] = np.nan
    else:
        year_rate = yearly.groupby("strategy_id")["avg_return"].apply(lambda s: float((pd.to_numeric(s, errors="coerce") > 0).mean()))
        work = work.merge(year_rate.rename("positive_year_rate"), on="strategy_id", how="left")
    avg_return = pd.to_numeric(work["avg_return"], errors="coerce").fillna(-1)
    median_return = pd.to_numeric(work["median_return"], errors="coerce").fillna(-1)
    win_rate = pd.to_numeric(work["win_rate"], errors="coerce").fillna(0)
    positive_year_rate = pd.to_numeric(work["positive_year_rate"], errors="coerce").fillna(0)
    trade_count = pd.to_numeric(work["trade_count"], errors="coerce").fillna(0)
    work["meets_min_trades"] = trade_count >= min_trades
    work["robust_rank_score"] = (
        avg_return * 100
        + median_return * 50
        + win_rate * 10
        + positive_year_rate * 10
        + np.log1p(trade_count)
        - (~work["meets_min_trades"]).astype(float) * 20
    ).round(4)
    return work.sort_values(["meets_min_trades", "robust_rank_score"], ascending=[False, False])


def _output_tag(config: HistoricalBacktestConfig) -> str:
    if config.output_tag:
        return config.output_tag
    quarters = "".join(config.quarters)
    return f"{config.start_period}_{config.end_period}_Q{quarters}_top{config.target_count}"

def _markdown_table(df: pd.DataFrame, columns: list[str]) -> str:
    if df.empty:
        return "无有效回测结果。"
    view = df[columns].copy()
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = []
    for _, row in view.iterrows():
        values = []
        for column in columns:
            value = row.get(column, "")
            if isinstance(value, float):
                values.append(f"{value:.4f}")
            else:
                values.append(str(value))
        rows.append("| " + " | ".join(values) + " |")
    return "\n".join([header, sep, *rows])




def write_interpretation(
    tag: str,
    config: HistoricalBacktestConfig,
    universe: pd.DataFrame,
    trades: pd.DataFrame,
    summary: pd.DataFrame,
    yearly: pd.DataFrame,
) -> Path:
    path = OUTPUT_DIR / f"historical_confirmation_interpretation_{tag}.md"
    eligible = summary[summary["meets_min_trades"].astype(bool)].copy() if not summary.empty else pd.DataFrame()
    best = eligible.iloc[0] if not eligible.empty else (summary.iloc[0] if not summary.empty else None)
    lines: list[str] = []
    lines.append("# 历史确认突破策略回测解读")
    lines.append("")
    lines.append("## 数据范围")
    lines.append(f"- 财报期：{config.start_period} 至 {config.end_period}，季度：{','.join(config.quarters)}。")
    lines.append(f"- 价格数据：{config.start_date} 至 {config.end_date or 'Tushare最新交易日'}，前复权日线。")
    lines.append(f"- 每期初筛数量：Top {config.target_count}；历史事件数：{len(universe)}。")
    lines.append(f"- 成本假设：滑点 {config.slippage_bps} bps，单边综合费用 {config.commission_bps} bps。")
    lines.append("")
    lines.append("## 策略假设")
    lines.append("公告后不左侧接回踩，只在周线重新转强时买入：收盘站上 5/10 周线、5 周线高于 10 周线、10 周线向上、突破过去 N 周高点，并满足放量阈值。")
    lines.append("信号必须在公告后限定周数内出现，避免把远离财报的走势错误归因到财报。")
    lines.append("")
    if best is not None:
        lines.append("## 当前最稳参数")
        lines.append(f"- strategy_id：{best['strategy_id']}")
        lines.append(f"- 突破窗口：{int(best['breakout_weeks'])} 周；量比阈值：{float(best['volume_ratio_min']):.2f}；止损：{float(best['stop_loss']):.0%}。")
        lines.append(f"- 最长持有：{int(best['max_hold_weeks'])} 周；公告后信号等待：{int(best['max_signal_wait_weeks'])} 周。")
        lines.append(f"- 交易数：{int(best['trade_count'])}；胜率：{float(best['win_rate']):.2%}；平均收益：{float(best['avg_return']):.2%}；中位数收益：{float(best['median_return']):.2%}。")
        if pd.notna(best.get("positive_year_rate", np.nan)):
            lines.append(f"- 年度正收益占比：{float(best['positive_year_rate']):.2%}。")
    lines.append("")
    lines.append("## 排名前 10 参数")
    if summary.empty:
        lines.append("无有效回测结果。")
    else:
        cols = [
            "strategy_id",
            "trade_count",
            "win_rate",
            "avg_return",
            "median_return",
            "positive_year_rate",
            "robust_rank_score",
        ]
        lines.append(_markdown_table(summary.head(10), cols))
    lines.append("")
    lines.append("## 解读原则")
    lines.append("- 如果最优参数交易数不足 30，只能看作线索，不能看作统计结论。")
    lines.append("- 如果收益只集中在少数年份，而多数年份为负，说明策略依赖市场环境。")
    lines.append("- 如果相邻参数表现差异很大，优先判定为过拟合，不应采用纸面最高收益参数。")
    lines.append("- 本结果只用于研究辅助，不构成投资建议，也不自动生成买卖点。")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run_historical_backtest(config: HistoricalBacktestConfig) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ensure_data_dirs()
    pro = _pro_api()
    resolved_end_date = config.end_date or latest_trade_date(pro)
    config = HistoricalBacktestConfig(**{**config.__dict__, "end_date": resolved_end_date})
    tag = _output_tag(config)

    universe = build_historical_universe(config, pro)
    if universe.empty:
        raise RuntimeError("Historical universe is empty; check periods, Tushare permissions, and filters.")
    daily = fetch_historical_daily(
        pro,
        universe["ts_code"].astype(str).tolist(),
        config.start_date,
        resolved_end_date,
        force_refresh=config.force_refresh_daily,
    )
    params = build_strategy_configs(config)
    weekly_cache: dict[int, pd.DataFrame] = {}
    all_trades: list[dict[str, Any]] = []
    for index, param in params.iterrows():
        strategy = _strategy_config(param)
        if strategy.breakout_weeks not in weekly_cache:
            weekly_cache[strategy.breakout_weeks] = add_confirmation_indicators(make_weekly_bars(daily), strategy.breakout_weeks)
        weekly = weekly_cache[strategy.breakout_weeks]
        for _, info in universe.iterrows():
            for trade in simulate_confirmation_stock(info, weekly, strategy):
                trade["strategy_id"] = strategy.output_tag
                trade["event_id"] = info.get("event_id", "")
                trade["breakout_weeks"] = strategy.breakout_weeks
                trade["volume_ratio_min"] = strategy.volume_ratio_min
                trade["stop_loss"] = strategy.stop_loss
                trade["max_hold_weeks"] = strategy.max_hold_weeks
                trade["max_signal_wait_weeks"] = strategy.max_signal_wait_weeks
                trade["slippage_bps"] = strategy.slippage_bps
                trade["commission_bps"] = strategy.commission_bps
                all_trades.append(trade)
        print(f"Backtested strategy {index + 1}/{len(params)}: {strategy.output_tag}")

    trades = _format_trade_dates(pd.DataFrame(all_trades))
    summary = summarize_by_strategy(trades, params, len(universe))
    yearly = summarize_yearly(trades, params)
    summary = add_robustness_columns(summary, yearly, config.min_trades)

    write_table(universe, OUTPUT_DIR / f"historical_confirmation_universe_{tag}.xlsx")
    write_table(universe, OUTPUT_DIR / f"historical_confirmation_universe_{tag}.csv")
    write_table(trades, OUTPUT_DIR / f"historical_confirmation_trades_{tag}.xlsx")
    write_table(trades, OUTPUT_DIR / f"historical_confirmation_trades_{tag}.csv")
    write_table(summary, OUTPUT_DIR / f"historical_confirmation_summary_{tag}.xlsx")
    write_table(summary, OUTPUT_DIR / f"historical_confirmation_summary_{tag}.csv")
    write_table(yearly, OUTPUT_DIR / f"historical_confirmation_yearly_{tag}.xlsx")
    write_table(params, OUTPUT_DIR / f"historical_confirmation_params_{tag}.xlsx")
    interpretation_path = write_interpretation(tag, config, universe, trades, summary, yearly)
    print(f"Saved interpretation: {interpretation_path}")
    return trades, summary, yearly, universe


def main() -> None:
    parser = argparse.ArgumentParser(description="Historical multi-period confirmation-breakout backtest.")
    parser.add_argument("--start-period", default="20210331")
    parser.add_argument("--end-period", default="20260331")
    parser.add_argument("--quarters", default="0331", help="Comma-separated report suffixes, e.g. 0331 or 0331,0630,0930")
    parser.add_argument("--target-count", type=int, default=30)
    parser.add_argument("--price-history-days", type=int, default=260)
    parser.add_argument("--no-price-history", action="store_true")
    parser.add_argument("--stock-list-status", default="L,D")
    parser.add_argument("--start-date", default="20200101")
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--strong-score", type=float, default=70.0)
    parser.add_argument("--breakout-weeks", default="4,8")
    parser.add_argument("--volume-ratio-min", default="1.0,1.2")
    parser.add_argument("--stop-loss", default="0.08,0.10,0.12")
    parser.add_argument("--max-hold-weeks", default="6,8,12")
    parser.add_argument("--max-signal-wait-weeks", default="4,8")
    parser.add_argument("--slippage-bps", type=float, default=15.0)
    parser.add_argument("--commission-bps", type=float, default=8.0)
    parser.add_argument("--min-trades", type=int, default=30)
    parser.add_argument("--output-tag", default=None)
    parser.add_argument("--force-refresh-daily", action="store_true")
    args = parser.parse_args()

    config = HistoricalBacktestConfig(
        start_period=args.start_period,
        end_period=args.end_period,
        quarters=_parse_items(args.quarters),
        target_count=args.target_count,
        price_history_days=args.price_history_days,
        include_price_history=not args.no_price_history,
        stock_list_status=args.stock_list_status,
        start_date=args.start_date,
        end_date=args.end_date,
        strong_score=args.strong_score,
        breakout_weeks=_parse_ints(args.breakout_weeks),
        volume_ratio_min=_parse_floats(args.volume_ratio_min),
        stop_loss=_parse_floats(args.stop_loss),
        max_hold_weeks=_parse_ints(args.max_hold_weeks),
        max_signal_wait_weeks=_parse_ints(args.max_signal_wait_weeks),
        slippage_bps=args.slippage_bps,
        commission_bps=args.commission_bps,
        min_trades=args.min_trades,
        output_tag=args.output_tag,
        force_refresh_daily=args.force_refresh_daily,
    )
    trades, summary, yearly, universe = run_historical_backtest(config)
    print(f"Events: {len(universe)}")
    print(f"Trades: {len(trades)}")
    print(summary.head(10).to_string(index=False))


if __name__ == "__main__":
    main()

