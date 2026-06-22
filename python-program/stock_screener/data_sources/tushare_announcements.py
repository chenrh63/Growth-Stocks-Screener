from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from ..env import get_env
from ..reports.models import Announcement


EXCLUDE_TITLE_KEYWORDS = (
    "\u6458\u8981",
    "\u53d6\u6d88",
    "\u66f4\u6b63",
    "\u4fee\u8ba2",
    "\u63d0\u793a\u6027\u516c\u544a",
    "\u5ef6\u671f\u62ab\u9732",
    "\u62ab\u9732\u7684\u63d0\u793a",
    "\u9884\u7ea6\u62ab\u9732",
    "\u53d8\u66f4",
)


def report_title_keywords(period: str) -> tuple[str, ...]:
    if period.endswith("0331"):
        return ("\u7b2c\u4e00\u5b63\u5ea6\u62a5\u544a", "\u4e00\u5b63\u5ea6\u62a5\u544a")
    if period.endswith("0630"):
        return ("\u534a\u5e74\u5ea6\u62a5\u544a", "\u534a\u5e74\u62a5")
    if period.endswith("0930"):
        return ("\u7b2c\u4e09\u5b63\u5ea6\u62a5\u544a", "\u4e09\u5b63\u5ea6\u62a5\u544a")
    if period.endswith("1231"):
        return ("\u5e74\u5ea6\u62a5\u544a", "\u5e74\u62a5")
    return ("\u5b9a\u671f\u62a5\u544a",)


def announcement_window(period: str) -> tuple[str, str]:
    year = int(period[:4])
    if period.endswith("0331"):
        return f"{year}0401", f"{year}0430"
    if period.endswith("0630"):
        return f"{year}0701", f"{year}0831"
    if period.endswith("0930"):
        return f"{year}1001", f"{year}1031"
    if period.endswith("1231"):
        return f"{year + 1}0101", f"{year + 1}0430"
    return f"{year}0101", f"{year}1231"


def _pick_pdf_url(row: pd.Series) -> str:
    for column in ["pdf_url", "url", "ann_url", "file_url", "adjunct_url"]:
        if column in row and pd.notna(row[column]) and str(row[column]).strip():
            return str(row[column]).strip()
    return ""


def _normalize_anns_df(df: pd.DataFrame, ts_code: str, name: str, period: str) -> list[Announcement]:
    if df is None or df.empty:
        return [Announcement(ts_code=ts_code, name=name, status="D_pending", error="no_periodic_report_found")]

    title_column = "title" if "title" in df.columns else "ann_title" if "ann_title" in df.columns else None
    if title_column is None:
        return [Announcement(ts_code=ts_code, name=name, status="D_pending", error="announcement_title_column_missing")]

    pattern = "|".join(report_title_keywords(period))
    filtered = df[df[title_column].astype(str).str.contains(pattern, na=False)].copy()
    for keyword in EXCLUDE_TITLE_KEYWORDS:
        filtered = filtered[~filtered[title_column].astype(str).str.contains(keyword, na=False)]
    if filtered.empty:
        return [Announcement(ts_code=ts_code, name=name, status="D_pending", error="no_formal_periodic_report_found")]

    date_column = "ann_date" if "ann_date" in filtered.columns else "ann_time" if "ann_time" in filtered.columns else None
    if date_column:
        filtered = filtered.sort_values(date_column)
    row = filtered.iloc[0]
    return [
        Announcement(
            ts_code=ts_code,
            name=name,
            title=str(row.get(title_column, "")),
            ann_date=str(row.get(date_column, "")) if date_column else "",
            pdf_url=_pick_pdf_url(row),
            source="tushare_anns_d",
            status="found",
        )
    ]


def fetch_tushare_announcements(candidates: pd.DataFrame, period: str, token: str | None = None) -> pd.DataFrame:
    token = token or get_env("TUSHARE_TOKEN")
    if not token:
        rows = [
            asdict(Announcement(ts_code=str(row.ts_code), name=str(row.name), error="TUSHARE_TOKEN missing"))
            for row in candidates.itertuples(index=False)
        ]
        return pd.DataFrame(rows)

    try:
        import tushare as ts  # type: ignore
    except Exception as exc:
        rows = [
            asdict(Announcement(ts_code=str(row.ts_code), name=str(row.name), error=f"tushare_import_failed:{exc}"))
            for row in candidates.itertuples(index=False)
        ]
        return pd.DataFrame(rows)

    start_date, end_date = announcement_window(period)
    pro = ts.pro_api(token)
    announcements: list[Announcement] = []
    for row in candidates.itertuples(index=False):
        ts_code = str(row.ts_code)
        name = str(row.name)
        try:
            df = pro.anns_d(ts_code=ts_code, start_date=start_date, end_date=end_date)
            announcements.extend(_normalize_anns_df(df, ts_code, name, period))
        except Exception as exc:
            announcements.append(
                Announcement(
                    ts_code=ts_code,
                    name=name,
                    source="tushare_anns_d",
                    status="D_pending",
                    error=f"tushare_anns_d_failed:{exc}",
                )
            )
    return pd.DataFrame(asdict(item) for item in announcements)


def merge_manual_pdf_urls(candidates: pd.DataFrame, announcements: pd.DataFrame) -> pd.DataFrame:
    if "pdf_url" not in candidates.columns:
        return announcements
    manual = candidates[["ts_code", "pdf_url"]].copy()
    manual["pdf_url"] = manual["pdf_url"].fillna("").astype(str).str.strip()
    manual = manual[manual["pdf_url"] != ""]
    if manual.empty:
        return announcements
    merged = announcements.merge(manual, on="ts_code", how="left", suffixes=("", "_manual"))
    use_manual = merged["pdf_url_manual"].fillna("").astype(str).str.strip() != ""
    merged.loc[use_manual, "pdf_url"] = merged.loc[use_manual, "pdf_url_manual"]
    merged.loc[use_manual, "source"] = merged.loc[use_manual, "source"].fillna("") + "+manual_pdf_url"
    merged = merged.drop(columns=["pdf_url_manual"])
    return merged
