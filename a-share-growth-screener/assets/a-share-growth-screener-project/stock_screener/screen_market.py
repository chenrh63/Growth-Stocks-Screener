from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_rules
from .paths import create_run_output_dir, period_output_path
from .screening import ScreenRunConfig, default_financial_period, run_market_screen


def main() -> None:
    rules = load_rules()
    parser = argparse.ArgumentParser(description="Screen A-share candidates for report tracking.")
    parser.add_argument("--period", default=rules.period)
    parser.add_argument("--financial-period", default=None, help="Financial report period used for pre-screening.")
    parser.add_argument("--trade-date", default=None, help="Tushare trade date, e.g. 20260605. Defaults to latest open day.")
    parser.add_argument("--target-count", type=int, default=rules.screening.target_count)
    parser.add_argument("--stock-list-status", default="L", help="Tushare stock_basic list_status, e.g. L or L,D.")
    parser.add_argument("--refresh-stock-list", action="store_true", help="Refetch Tushare stock_basic before downstream filtering.")
    parser.add_argument("--price-history-days", type=int, default=rules.screening.price_history_days)
    parser.add_argument("--no-price-history", action="store_true", help="Skip daily price history calls.")
    parser.add_argument("--run-name", default=None, help="Optional fixed output folder name under data/outputs/runs.")
    parser.add_argument("--flat-output", action="store_true", help="Write outputs to data/outputs instead of creating a new run folder.")
    parser.add_argument("--all-boards", action="store_true", help="Disable the default Shanghai/Shenzhen main-board-only universe filter.")
    args = parser.parse_args()

    financial_period = args.financial_period or default_financial_period(args.period)
    output_dir: Path | None = None if args.flat_output else create_run_output_dir("screen_market", args.period, args.run_name)
    selected, scored = run_market_screen(
        ScreenRunConfig(
            period=args.period,
            financial_period=financial_period,
            trade_date=args.trade_date,
            target_count=args.target_count,
            price_history_days=args.price_history_days,
            include_price_history=not args.no_price_history,
            stock_list_status=args.stock_list_status,
            refresh_stock_list=args.refresh_stock_list,
            output_dir=output_dir,
            main_board_only=not args.all_boards,
        ),
        rules=rules,
    )
    print(f"Selected {len(selected)} candidates from {len(scored)} scored stocks.")
    print(f"Output directory: {output_dir or 'data/outputs'}")
    print(period_output_path("candidates", args.period, ".xlsx", output_dir=output_dir))
    if not selected.empty:
        cols = ["ts_code", "name", "market", "industry", "total_score", "growth_score", "valuation_score", "mispricing_score"]
        print(selected[[column for column in cols if column in selected.columns]].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
