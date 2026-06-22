from __future__ import annotations

import argparse
from datetime import datetime

import pandas as pd

from .io import write_table
from .paths import OUTPUT_DIR, ensure_data_dirs
from .screening import _require_tushare, fetch_stock_basic


def _status_tag(list_status: str) -> str:
    return str(list_status or "L").replace(",", "_").replace(" ", "")


def refresh_stock_list(
    list_status: str = "L",
    as_of: str | None = None,
    output_prefix: str = "tushare_stock_list",
    use_cache: bool = False,
) -> pd.DataFrame:
    """Fetch the Tushare stock_basic universe before downstream filtering."""
    ensure_data_dirs()
    pro = _require_tushare()
    data = fetch_stock_basic(pro, list_status=list_status, refresh=not use_cache)
    stamp = as_of or datetime.now().strftime("%Y%m%d")
    base = OUTPUT_DIR / f"{output_prefix}_{_status_tag(list_status)}_{stamp}"
    write_table(data, base.with_suffix(".xlsx"))
    write_table(data, base.with_suffix(".csv"))
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh the A-share stock list from Tushare stock_basic.")
    parser.add_argument("--list-status", default="L", help="Tushare list_status, e.g. L or L,D.")
    parser.add_argument("--as-of", default=None, help="Output date tag, defaults to today as YYYYMMDD.")
    parser.add_argument("--output-prefix", default="tushare_stock_list")
    parser.add_argument("--use-cache", action="store_true", help="Reuse cached stock_basic instead of refetching Tushare.")
    args = parser.parse_args()

    data = refresh_stock_list(
        list_status=args.list_status,
        as_of=args.as_of,
        output_prefix=args.output_prefix,
        use_cache=args.use_cache,
    )
    stamp = args.as_of or datetime.now().strftime("%Y%m%d")
    base = OUTPUT_DIR / f"{args.output_prefix}_{_status_tag(args.list_status)}_{stamp}"
    print(f"Fetched {len(data)} stock_basic rows from Tushare.")
    print(base.with_suffix(".xlsx"))


if __name__ == "__main__":
    main()
