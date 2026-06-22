from __future__ import annotations

import re
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


CNINFO_BASE = "http://static.cninfo.com.cn/"


def _cninfo_column(stock_code: str) -> str:
    if stock_code.startswith(("6", "9")):
        return "sse"
    if stock_code.startswith(("0", "2", "3")):
        return "szse"
    return ""


def _resolve_cninfo_detail_url(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    if "cninfo.com.cn" not in parsed.netloc or "/new/disclosure/detail" not in parsed.path:
        return value
    params = urllib.parse.parse_qs(parsed.query)
    stock_code = (params.get("stockCode") or [""])[0]
    org_id = (params.get("orgId") or [""])[0]
    announcement_id = (params.get("announcementId") or [""])[0]
    announcement_time = (params.get("announcementTime") or [""])[0]
    if not stock_code or not org_id or not announcement_id or not announcement_time:
        return value

    categories = ["category_yjdbg_szsh;", "category_bndbg_szsh;", "category_sjdbg_szsh;", "category_ndbg_szsh;", ""]
    for category in categories:
        form = {
            "pageNum": "1",
            "pageSize": "30",
            "column": _cninfo_column(stock_code),
            "tabName": "fulltext",
            "plate": "",
            "stock": f"{stock_code},{org_id}",
            "searchkey": "",
            "secid": "",
            "category": category,
            "trade": "",
            "seDate": f"{announcement_time}~{announcement_time}",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        request = urllib.request.Request(
            "http://www.cninfo.com.cn/new/hisAnnouncement/query",
            data=urllib.parse.urlencode(form).encode("utf-8"),
            headers={
                "User-Agent": "Mozilla/5.0 stock-screener/0.1",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Referer": "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8", errors="ignore"))
        except Exception:
            continue

        for item in payload.get("announcements") or []:
            if str(item.get("announcementId", "")) == announcement_id and item.get("adjunctUrl"):
                return urllib.parse.urljoin(CNINFO_BASE, str(item["adjunctUrl"]))
    return value


def normalize_pdf_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    if value.startswith("//"):
        return "https:" + value
    if value.startswith("http://") or value.startswith("https://"):
        return _resolve_cninfo_detail_url(value)
    if value.startswith("/"):
        return urllib.parse.urljoin(CNINFO_BASE, value.lstrip("/"))
    return urllib.parse.urljoin(CNINFO_BASE, value)


def safe_filename(value: str, max_length: int = 90) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", value.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:max_length] or "report"


def download_file(url: str, dest: Path, timeout: int = 30) -> tuple[bool, str]:
    normalized = normalize_pdf_url(url)
    if not normalized:
        return False, "empty_pdf_url"

    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        normalized,
        headers={
            "User-Agent": "Mozilla/5.0 stock-screener/0.1",
            "Accept": "application/pdf,*/*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read()
    except urllib.error.HTTPError as exc:
        return False, f"http_error_{exc.code}"
    except Exception as exc:
        return False, f"download_error:{exc}"

    if len(content) < 1024:
        return False, "downloaded_file_too_small"
    if not content.lstrip().startswith(b"%PDF"):
        return False, "downloaded_content_is_not_pdf"

    dest.write_bytes(content)
    return True, ""
