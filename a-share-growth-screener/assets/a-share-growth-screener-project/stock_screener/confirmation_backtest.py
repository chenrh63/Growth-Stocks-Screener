from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .backtest_common import load_analysis, load_manifest, make_weekly_bars, select_universe, summarize_trades
from .env import get_env
from .io import write_table
from .paths import DATA_DIR, ensure_data_dirs, period_output_path
from .screening import latest_trade_date


@dataclass(frozen=True)
class ConfirmationBacktestConfig:
    period: str = "20260331"
    statuses: tuple[str, ...] = ("A_confirmed", "B_watch")
    start_date: str = "20250101"
    end_date: str | None = None
    breakout_weeks: int = 4
    volume_ratio_min: float = 1.0
    stop_loss: float = 0.10
    slippage_bps: float = 10.0
    commission_bps: float = 3.0
    max_hold_weeks: int | None = 8
    max_signal_wait_weeks: int | None = 12
    output_tag: str = "confirmation"


FRESH_DIR = DATA_DIR / "backtest_data" / "tushare_fresh"


def _pro_api():
    token = get_env("TUSHARE_TOKEN")
    if not token:
        raise RuntimeError("TUSHARE_TOKEN missing in .env or .env.txt")
    try:
        import tushare as ts  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"tushare import failed: {exc}") from exc
    return ts.pro_api(token)


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


def fetch_fresh_daily(ts_codes: list[str], start_date: str, end_date: str, period: str) -> pd.DataFrame:
    pro = _pro_api()
    FRESH_DIR.mkdir(parents=True, exist_ok=True)
    frames: list[pd.DataFrame] = []
    for index, ts_code in enumerate(ts_codes, start=1):
        try:
            daily = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            if daily is None or daily.empty:
                print(f"No daily data: {ts_code}")
                continue
            try:
                adj = pro.adj_factor(ts_code=ts_code, start_date=start_date, end_date=end_date)
                daily = _adjust_ohlc(daily, adj)
            except Exception as exc:
                print(f"adj_factor failed for {ts_code}: {exc}")
            frames.append(daily)
        except Exception as exc:
            print(f"daily fetch failed for {ts_code}: {exc}")
        if index % 10 == 0:
            print(f"Fetched fresh daily {index}/{len(ts_codes)}")
    if not frames:
        raise RuntimeError("No fresh daily data fetched from Tushare")
    result = pd.concat(frames, ignore_index=True)
    keep = [column for column in ["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"] if column in result.columns]
    result = result[keep].copy()
    path = FRESH_DIR / f"daily_{period}_{start_date}_{end_date}.csv"
    result.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Saved fresh daily: {path}")
    return normalize_daily(result)


def normalize_daily(daily: pd.DataFrame) -> pd.DataFrame:
    work = daily.copy()
    work["trade_date"] = pd.to_datetime(work["trade_date"].astype(str), format="%Y%m%d", errors="coerce")
    if "vol" not in work.columns:
        work["vol"] = 0.0
    for column in ["open", "high", "low", "close", "vol"]:
        work[column] = pd.to_numeric(work[column], errors="coerce")
    return work.dropna(subset=["ts_code", "trade_date", "open", "high", "low", "close"]).sort_values(["ts_code", "trade_date"])


def add_confirmation_indicators(weekly: pd.DataFrame, breakout_weeks: int) -> pd.DataFrame:
    work = weekly.copy()
    work["ma5"] = work.groupby("ts_code")["close"].transform(lambda s: s.shift(1).rolling(5, min_periods=5).mean())
    work["ma10"] = work.groupby("ts_code")["close"].transform(lambda s: s.shift(1).rolling(10, min_periods=10).mean())
    work["ma10_slope"] = work.groupby("ts_code")["ma10"].diff()
    work["prior_high"] = work.groupby("ts_code")["high"].transform(
        lambda s: s.shift(1).rolling(breakout_weeks, min_periods=breakout_weeks).max()
    )
    work["volume_ma5"] = work.groupby("ts_code")["volume"].transform(lambda s: s.shift(1).rolling(5, min_periods=5).mean())
    work["volume_ratio"] = work["volume"] / work["volume_ma5"]
    return work


def is_confirmation_signal(row: pd.Series, config: ConfirmationBacktestConfig) -> bool:
    required = ["ma5", "ma10", "ma10_slope", "prior_high", "volume_ratio"]
    if any(pd.isna(row.get(column)) for column in required):
        return False
    return bool(
        row["close"] > row["ma5"]
        and row["close"] > row["ma10"]
        and row["ma5"] > row["ma10"]
        and row["ma10_slope"] > 0
        and row["close"] > row["prior_high"]
        and row["volume_ratio"] >= config.volume_ratio_min
    )


def simulate_confirmation_stock(info: pd.Series, weekly: pd.DataFrame, config: ConfirmationBacktestConfig) -> list[dict[str, Any]]:
    ts_code = str(info["ts_code"])
    stock_weekly = weekly[weekly["ts_code"] == ts_code].sort_values("week").reset_index(drop=True)
    if stock_weekly.empty:
        return []
    ann_date = info.get("ann_date")
    if pd.isna(ann_date):
        ann_date = stock_weekly["week_end"].min()

    signal_deadline = None
    if config.max_signal_wait_weeks:
        signal_deadline = pd.Timestamp(ann_date) + pd.Timedelta(weeks=config.max_signal_wait_weeks)

    pending_signal: dict[str, Any] | None = None
    current_trade: dict[str, Any] | None = None
    trades: list[dict[str, Any]] = []

    for idx, row in stock_weekly.iterrows():
        week_start = row["week_start"]
        week_end = row["week_end"]
        if pd.isna(week_end) or week_end <= ann_date:
            continue

        if pending_signal is not None and current_trade is None:
            entry_price = float(row["open"]) * (1 + config.slippage_bps / 10000)
            current_trade = {
                "ts_code": ts_code,
                "name": info.get("name", ""),
                "industry": info.get("industry", ""),
                "event_period": info.get("event_period", info.get("screen_period", info.get("financial_period", ""))),
                "screen_trade_date": info.get("screen_trade_date", info.get("trade_date", "")),
                "ann_date": ann_date,
                "candidate_status": info.get("candidate_status", ""),
                "total_score": info.get("total_score", np.nan),
                "growth_score": info.get("growth_score", np.nan),
                "valuation_score": info.get("valuation_score", np.nan),
                "mispricing_score": info.get("mispricing_score", np.nan),
                "quality_score": info.get("quality_score", np.nan),
                "verification_total_score": info.get("verification_total_score", np.nan),
                "signal_week": pending_signal["signal_week"],
                "signal_close": pending_signal["signal_close"],
                "signal_prior_high": pending_signal["prior_high"],
                "signal_volume_ratio": pending_signal["volume_ratio"],
                "entry_date": week_start,
                "entry_price": entry_price,
                "hold_weeks": 0,
            }
            pending_signal = None

        if current_trade is not None:
            current_trade["hold_weeks"] += 1
            entry_price = float(current_trade["entry_price"])
            stop_price = entry_price * (1 - config.stop_loss)
            exit_price: float | None = None
            exit_reason = ""
            if float(row["low"]) <= stop_price:
                exit_reason = "stop_loss"
                exit_price = stop_price * (1 - config.slippage_bps / 10000)
            elif pd.notna(row.get("ma10")) and float(row["close"]) < float(row["ma10"]):
                exit_reason = "weekly_close_below_ma10"
                exit_price = float(row["close"]) * (1 - config.slippage_bps / 10000)
            elif config.max_hold_weeks and current_trade["hold_weeks"] >= config.max_hold_weeks:
                exit_reason = "max_hold_weeks"
                exit_price = float(row["close"]) * (1 - config.slippage_bps / 10000)
            elif idx == len(stock_weekly) - 1:
                exit_reason = "end_of_data"
                exit_price = float(row["close"]) * (1 - config.slippage_bps / 10000)

            if exit_price is not None:
                cost = 2 * config.commission_bps / 10000
                current_trade.update(
                    {
                        "exit_date": week_end,
                        "exit_price": exit_price,
                        "exit_reason": exit_reason,
                        "return_pct": exit_price / entry_price - 1 - cost,
                    }
                )
                trades.append(current_trade)
                break

        if current_trade is None and pending_signal is None:
            if signal_deadline is not None and pd.notna(week_end) and week_end > signal_deadline:
                break
            if not is_confirmation_signal(row, config):
                continue
            pending_signal = {
                "signal_week": week_end,
                "signal_close": row["close"],
                "prior_high": row["prior_high"],
                "volume_ratio": row["volume_ratio"],
            }
    return trades


def run_confirmation_backtest(config: ConfirmationBacktestConfig) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ensure_data_dirs()
    analysis = load_analysis(config.period)
    manifest = load_manifest(config.period)
    universe = select_universe(analysis, manifest, config)  # type: ignore[arg-type]
    pro = _pro_api()
    end_date = config.end_date or latest_trade_date(pro)
    daily = fetch_fresh_daily(universe["ts_code"].astype(str).tolist(), config.start_date, end_date, config.period)
    weekly = add_confirmation_indicators(make_weekly_bars(daily), config.breakout_weeks)

    trades: list[dict[str, Any]] = []
    for _, info in universe.iterrows():
        trades.extend(simulate_confirmation_stock(info, weekly, config))
    trades_df = pd.DataFrame(trades)
    if not trades_df.empty:
        for column in ["signal_week", "entry_date", "exit_date"]:
            trades_df[column] = pd.to_datetime(trades_df[column]).dt.strftime("%Y-%m-%d")
        trades_df["return_pct"] = trades_df["return_pct"].round(6)
        trades_df["return_pct_display"] = (trades_df["return_pct"] * 100).round(2)
    summary = summarize_trades(trades_df, len(universe))
    prefix = f"backtest_{config.output_tag}"
    write_table(trades_df, period_output_path(f"{prefix}_trades", config.period, ".xlsx"))
    write_table(trades_df, period_output_path(f"{prefix}_trades", config.period, ".csv"))
    write_table(summary, period_output_path(f"{prefix}_summary", config.period, ".xlsx"))
    write_table(universe, period_output_path(f"{prefix}_universe", config.period, ".xlsx"))
    return trades_df, summary, universe


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest post-report weekly confirmation breakout strategy.")
    parser.add_argument("--period", default="20260331")
    parser.add_argument("--statuses", default="A_confirmed,B_watch")
    parser.add_argument("--start-date", default="20250101")
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--breakout-weeks", type=int, default=4)
    parser.add_argument("--volume-ratio-min", type=float, default=1.0)
    parser.add_argument("--stop-loss", type=float, default=0.10)
    parser.add_argument("--max-hold-weeks", type=int, default=8)
    parser.add_argument("--max-signal-wait-weeks", type=int, default=12)
    parser.add_argument("--output-tag", default="confirmation")
    args = parser.parse_args()
    config = ConfirmationBacktestConfig(
        period=args.period,
        statuses=tuple(item.strip() for item in args.statuses.split(",") if item.strip()),
        start_date=args.start_date,
        end_date=args.end_date,
        breakout_weeks=args.breakout_weeks,
        volume_ratio_min=args.volume_ratio_min,
        stop_loss=args.stop_loss,
        max_hold_weeks=args.max_hold_weeks or None,
        max_signal_wait_weeks=args.max_signal_wait_weeks or None,
        output_tag=args.output_tag,
    )
    trades, summary, universe = run_confirmation_backtest(config)
    print(f"Universe: {len(universe)}")
    print(f"Trades: {len(trades)}")
    print(summary.to_string(index=False))
    if not trades.empty:
        cols = ["ts_code", "name", "candidate_status", "entry_date", "exit_date", "exit_reason", "return_pct"]
        print(trades[cols].to_string(index=False))
    print(period_output_path(f"backtest_{config.output_tag}_trades", config.period, ".xlsx"))
    print(period_output_path(f"backtest_{config.output_tag}_summary", config.period, ".xlsx"))


if __name__ == "__main__":
    main()


