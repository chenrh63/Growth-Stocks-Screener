from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .io import read_table
from .paths import period_output_path


def load_analysis(period: str) -> pd.DataFrame:
    path = period_output_path("report_analysis", period, ".xlsx")
    if not path.exists():
        path = period_output_path("report_analysis", period, ".csv")
    if not path.exists():
        raise FileNotFoundError(f"Missing report_analysis for {period}: {path}")
    return read_table(path)


def load_manifest(period: str) -> pd.DataFrame:
    path = period_output_path("report_manifest", period, ".xlsx")
    if not path.exists():
        path = period_output_path("report_manifest", period, ".csv")
    if not path.exists():
        return pd.DataFrame(columns=["ts_code", "ann_date"])
    return read_table(path)


def make_weekly_bars(daily: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    daily = daily.copy()
    if "vol" not in daily.columns:
        daily["vol"] = 0.0
    for ts_code, group in daily.groupby("ts_code", sort=False):
        g = group.sort_values("trade_date").set_index("trade_date")
        weekly = pd.DataFrame(
            {
                "open": g["open"].resample("W-FRI").first(),
                "high": g["high"].resample("W-FRI").max(),
                "low": g["low"].resample("W-FRI").min(),
                "close": g["close"].resample("W-FRI").last(),
                "volume": g["vol"].resample("W-FRI").sum(),
                "week_start": g["close"].resample("W-FRI").apply(lambda x: x.index.min() if len(x) else pd.NaT),
                "week_end": g["close"].resample("W-FRI").apply(lambda x: x.index.max() if len(x) else pd.NaT),
            }
        ).dropna(subset=["open", "high", "low", "close"])
        weekly["ts_code"] = ts_code
        frames.append(weekly.reset_index(names="week"))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values(["ts_code", "week"])


def select_universe(analysis: pd.DataFrame, manifest: pd.DataFrame, config: Any) -> pd.DataFrame:
    work = analysis[analysis["candidate_status"].isin(config.statuses)].copy()
    if manifest is not None and not manifest.empty and "ann_date" in manifest.columns:
        ann = manifest[["ts_code", "ann_date"]].copy()
        ann["ann_date"] = pd.to_datetime(ann["ann_date"].astype(str), format="%Y%m%d", errors="coerce")
        work = work.merge(ann, on="ts_code", how="left")
    else:
        work["ann_date"] = pd.NaT
    return work


def summarize_trades(trades: pd.DataFrame, universe_count: int) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(
            [
                {
                    "group": "all",
                    "universe_count": universe_count,
                    "trade_count": 0,
                    "win_rate": np.nan,
                    "avg_return": np.nan,
                    "median_return": np.nan,
                    "equal_weight_return": np.nan,
                    "best_return": np.nan,
                    "worst_return": np.nan,
                }
            ]
        )

    rows: list[dict[str, Any]] = []
    for label, group in [("all", trades), *list(trades.groupby("candidate_status"))]:
        returns = pd.to_numeric(group["return_pct"], errors="coerce").dropna()
        rows.append(
            {
                "group": label,
                "universe_count": universe_count,
                "trade_count": len(returns),
                "win_rate": float((returns > 0).mean()) if len(returns) else np.nan,
                "avg_return": float(returns.mean()) if len(returns) else np.nan,
                "median_return": float(returns.median()) if len(returns) else np.nan,
                "equal_weight_return": float(returns.mean()) if len(returns) else np.nan,
                "best_return": float(returns.max()) if len(returns) else np.nan,
                "worst_return": float(returns.min()) if len(returns) else np.nan,
            }
        )
    return pd.DataFrame(rows)
