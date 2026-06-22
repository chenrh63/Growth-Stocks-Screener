from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import asdict

import pandas as pd

from ..data_sources.tushare_announcements import announcement_window
from ..paths import CACHE_DIR
from ..reports.models import Announcement


CNINFO_BASE = "http://static.cninfo.com.cn/"
CNINFO_QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_STOCK_LIST_URLS = (
    "http://www.cninfo.com.cn/new/data/szse_stock.json",
    "http://www.cninfo.com.cn/new/data/bj_stock.json",
)


def _cninfo_category(period: str) -> str:
    if period.endswith("0331"):
        return "category_yjdbg_szsh;"
    if period.endswith("0630"):
        return "category_bndbg_szsh;"
    if period.endswith("0930"):
        return "category_sjdbg_szsh;"
    if period.endswith("1231"):
        return "category_ndbg_szsh;"
    return ""


def _title_matches_period(title: str, period: str) -> bool:
    exclude_keywords = (
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
    if any(keyword in title for keyword in exclude_keywords):
        return False
    if period.endswith("0331"):
        return "\u7b2c\u4e00\u5b63\u5ea6\u62a5\u544a" in title or "\u4e00\u5b63\u5ea6\u62a5\u544a" in title
    if period.endswith("0630"):
        return "\u534a\u5e74\u5ea6\u62a5\u544a" in title or "\u534a\u5e74\u62a5" in title
    if period.endswith("0930"):
        return "\u7b2c\u4e09\u5b63\u5ea6\u62a5\u544a" in title or "\u4e09\u5b63\u5ea6\u62a5\u544a" in title
    if period.endswith("1231"):
        return "\u5e74\u5ea6\u62a5\u544a" in title or "\u5e74\u62a5" in title
    return "\u62a5\u544a" in title


def _exchange_column(ts_code: str) -> str:
    if ts_code.endswith(".SH"):
        return "sse"
    if ts_code.endswith(".SZ"):
        return "szse"
    if ts_code.endswith(".BJ"):
        return "bj"
    return ""


def _normalize_cninfo_pdf_url(adjunct_url: object) -> str:
    value = str(adjunct_url or "").strip()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return urllib.parse.urljoin(CNINFO_BASE, value.lstrip("/"))


def _stock_list_cache_path() -> str:
    path = CACHE_DIR / "cninfo"
    path.mkdir(parents=True, exist_ok=True)
    return str(path / "stock_list.csv")


def _download_cninfo_stock_list() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for url in CNINFO_STOCK_LIST_URLS:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 stock-screener/0.1",
                "Referer": "http://www.cninfo.com.cn/new/index",
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
        for item in payload.get("stockList") or []:
            rows.append(
                {
                    "code": str(item.get("code", "")).strip(),
                    "orgId": str(item.get("orgId", "")).strip(),
                    "zwjc": str(item.get("zwjc", "")).strip(),
                    "category": str(item.get("category", "")).strip(),
                }
            )
    if not rows:
        return pd.DataFrame(columns=["code", "orgId", "zwjc", "category"])
    return pd.DataFrame(rows).drop_duplicates("code", keep="first")


def _load_cninfo_stock_map() -> dict[str, str]:
    path = _stock_list_cache_path()
    try:
        df = pd.read_csv(path, dtype={"code": str, "orgId": str})
    except Exception:
        df = _download_cninfo_stock_list()
        df.to_csv(path, index=False, encoding="utf-8-sig")
    if df.empty or "code" not in df.columns or "orgId" not in df.columns:
        return {}
    df = df.dropna(subset=["code", "orgId"])
    return dict(zip(df["code"].astype(str), df["orgId"].astype(str)))


def _stock_query_value(ts_code: str, org_map: dict[str, str]) -> str:
    code = ts_code.split(".")[0]
    org_id = org_map.get(code, "").strip()
    return f"{code},{org_id}" if org_id else code


def fetch_cninfo_announcements(candidates: pd.DataFrame, period: str) -> pd.DataFrame:
    start_date, end_date = announcement_window(period)
    date_range = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}~{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"
    results: list[Announcement] = []
    org_map = _load_cninfo_stock_map()

    for row in candidates.itertuples(index=False):
        ts_code = str(row.ts_code)
        name = str(row.name)
        form = {
            "pageNum": "1",
            "pageSize": "30",
            "column": _exchange_column(ts_code),
            "tabName": "fulltext",
            "plate": "",
            "stock": _stock_query_value(ts_code, org_map),
            "searchkey": "",
            "secid": "",
            "category": _cninfo_category(period),
            "trade": "",
            "seDate": date_range,
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        try:
            data = urllib.parse.urlencode(form).encode("utf-8")
            request = urllib.request.Request(
                CNINFO_QUERY_URL,
                data=data,
                headers={
                    "User-Agent": "Mozilla/5.0 stock-screener/0.1",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Referer": "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
                },
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8", errors="ignore"))
            announcements = payload.get("announcements") or []
            selected = None
            for item in announcements:
                title = str(item.get("announcementTitle", ""))
                if _title_matches_period(title, period):
                    selected = item
                    break
            if not selected:
                results.append(Announcement(ts_code=ts_code, name=name, source="cninfo", error="no_cninfo_report_found"))
                continue
            results.append(
                Announcement(
                    ts_code=ts_code,
                    name=name,
                    title=str(selected.get("announcementTitle", "")),
                    ann_date=str(selected.get("announcementTime", "")),
                    pdf_url=_normalize_cninfo_pdf_url(selected.get("adjunctUrl", "")),
                    source="cninfo",
                    status="found",
                )
            )
        except Exception as exc:
            results.append(Announcement(ts_code=ts_code, name=name, source="cninfo", error=f"cninfo_query_failed:{exc}"))

    return pd.DataFrame(asdict(item) for item in results)
