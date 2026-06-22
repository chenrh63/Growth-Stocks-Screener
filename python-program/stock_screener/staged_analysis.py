from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd

from .analysis import analyze_candidates
from .config import load_rules
from .io import read_table, write_table
from .paths import create_run_output_dir, period_output_path
from .refresh_reports import refresh_reports
from .screening import ScreenRunConfig, default_financial_period, run_market_screen


DEFAULT_TAG = "theme_growth_deepseek_v4_pro"
DEFAULT_LLM_MODEL = "deepseek-v4-pro"


def _read_period_output(prefix: str, period: str, output_dir: Path | None = None) -> pd.DataFrame:
    for suffix in [".xlsx", ".csv"]:
        path = period_output_path(prefix, period, suffix, output_dir=output_dir)
        if path.exists():
            return read_table(path)
    raise FileNotFoundError(f"Missing output: {prefix}_{period}")


def _markdown_table(df: pd.DataFrame, columns: list[str]) -> str:
    if df.empty:
        return "-"
    view = df[[column for column in columns if column in df.columns]].copy()
    header = "| " + " | ".join(view.columns) + " |"
    sep = "| " + " | ".join(["---"] * len(view.columns)) + " |"
    rows: list[str] = []
    for _, row in view.iterrows():
        values = []
        for column in view.columns:
            value = row.get(column, "")
            if isinstance(value, float):
                values.append(f"{value:.4f}")
            else:
                values.append(str(value))
        rows.append("| " + " | ".join(values) + " |")
    return "\n".join([header, sep, *rows])


def write_analysis_markdown(result: pd.DataFrame, period: str, tag: str, path: Path, output_dir: Path | None = None) -> None:
    lines: list[str] = []
    lines.append(f"# Report Text Analysis Result ({period})")
    lines.append("")
    lines.append(f"Run tag: `{tag}`")
    if output_dir is not None:
        lines.append(f"Output directory: `{output_dir}`")
    lines.append("Pipeline: Tushare full-market data -> Shanghai/Shenzhen main-board filter -> hard metrics -> theme financial scoring -> report text/LLM analysis.")
    lines.append("")
    if result.empty:
        lines.append("No candidates analyzed.")
    else:
        lines.append("## Status Counts")
        status_counts = result.get("candidate_status", pd.Series(dtype=object)).value_counts(dropna=False).reset_index()
        status_counts.columns = ["candidate_status", "count"]
        lines.append(_markdown_table(status_counts, ["candidate_status", "count"]))
        lines.append("")
        if "analysis_source" in result.columns:
            lines.append("## Analysis Source Counts")
            source_counts = result["analysis_source"].value_counts(dropna=False).reset_index()
            source_counts.columns = ["analysis_source", "count"]
            lines.append(_markdown_table(source_counts, ["analysis_source", "count"]))
            lines.append("")
        lines.append("## Top Candidates")
        cols = [
            "candidate_status",
            "ts_code",
            "name",
            "industry",
            "market",
            "primary_theme",
            "total_score",
            "growth_score",
            "theme_score",
            "valuation_score",
            "mispricing_score",
            "verification_total_score",
            "text_verdict",
            "analysis_source",
            "llm_model",
            "total_tokens",
        ]
        lines.append(_markdown_table(result.head(100), cols))
        lines.append("")
        token_cols = ["prompt_tokens", "completion_tokens", "total_tokens"]
        if all(column in result.columns for column in token_cols):
            lines.append("## Token Summary")
            token_summary = pd.DataFrame(
                [
                    {
                        "prompt_tokens": pd.to_numeric(result["prompt_tokens"], errors="coerce").sum(),
                        "completion_tokens": pd.to_numeric(result["completion_tokens"], errors="coerce").sum(),
                        "total_tokens": pd.to_numeric(result["total_tokens"], errors="coerce").sum(),
                    }
                ]
            )
            lines.append(_markdown_table(token_summary, token_cols))
            lines.append("")
    lines.append("## Notes")
    lines.append("- This is research support only, not trading advice.")
    lines.append("- `analysis_source=q1_mdna` means Q1 MD&A was usable; `annual_mdna_fallback` means the previous annual report was used as fallback.")
    lines.append("- `D_pending` means report download/parse or LLM analysis was not completed.")
    path.write_text("\n".join(lines), encoding="utf-8")


def run_staged_analysis(
    period: str,
    financial_period: str | None = None,
    trade_date: str | None = None,
    target_count: int = 100,
    output_tag: str = DEFAULT_TAG,
    limit: int | None = None,
    source: str = "auto",
    skip_refresh: bool = False,
    disable_llm: bool = False,
    stock_list_status: str = "L",
    refresh_stock_list: bool = False,
    fallback_annual_report: bool = False,
    run_name: str | None = None,
    flat_output: bool = False,
    main_board_only: bool = True,
    llm_model: str | None = DEFAULT_LLM_MODEL,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rules = load_rules()
    financial_period = financial_period or default_financial_period(period)
    financial_prefix = f"financial_candidates_{output_tag}"
    scored_prefix = f"screened_universe_top500_{output_tag}"
    manifest_prefix = f"report_manifest_{output_tag}"
    analysis_prefix = f"report_analysis_{output_tag}"
    output_dir = None if flat_output else create_run_output_dir(output_tag, period, run_name)

    if llm_model:
        os.environ["LLM_MODEL"] = llm_model

    financial_candidates, _ = run_market_screen(
        ScreenRunConfig(
            period=period,
            financial_period=financial_period,
            trade_date=trade_date,
            target_count=target_count,
            price_history_days=rules.screening.price_history_days,
            include_price_history=True,
            stock_list_status=stock_list_status,
            candidate_output_prefix=financial_prefix,
            scored_output_prefix=scored_prefix,
            refresh_stock_list=refresh_stock_list,
            output_dir=output_dir,
            main_board_only=main_board_only,
        ),
        rules=rules,
    )
    candidate_path = period_output_path(financial_prefix, period, ".xlsx", output_dir=output_dir)

    if skip_refresh:
        manifest = _read_period_output(manifest_prefix, period, output_dir=output_dir)
    else:
        manifest = refresh_reports(
            period=period,
            candidate_path=candidate_path,
            source=source,
            limit=limit,
            output_prefix=manifest_prefix,
            fallback_annual_report=fallback_annual_report,
            output_dir=output_dir,
        )

    candidates_for_analysis = financial_candidates.head(limit).copy() if limit else financial_candidates.copy()
    merged = candidates_for_analysis.merge(manifest, on=["ts_code", "name"], how="left", suffixes=("", "_report"))
    result = analyze_candidates(merged, period=period, rules=rules, enable_llm=not disable_llm)

    xlsx_path = period_output_path(analysis_prefix, period, ".xlsx", output_dir=output_dir)
    csv_path = period_output_path(analysis_prefix, period, ".csv", output_dir=output_dir)
    md_path = period_output_path(analysis_prefix, period, ".md", output_dir=output_dir)
    write_table(result, xlsx_path)
    write_table(result, csv_path)
    write_analysis_markdown(result, period, output_tag, md_path, output_dir=output_dir)

    attrs = {"output_dir": str(output_dir) if output_dir else "", "llm_model": llm_model or ""}
    financial_candidates.attrs.update(attrs)
    manifest.attrs.update(attrs)
    result.attrs.update(attrs)
    return financial_candidates, manifest, result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run theme-growth financial-first report analysis with annual fallback.")
    parser.add_argument("--period", default="20260331")
    parser.add_argument("--financial-period", default=None)
    parser.add_argument("--trade-date", default=None)
    parser.add_argument("--target-count", type=int, default=100)
    parser.add_argument("--output-tag", default=DEFAULT_TAG)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--source", choices=["auto", "tushare", "cninfo"], default="auto")
    parser.add_argument("--skip-refresh", action="store_true")
    parser.add_argument("--disable-llm", action="store_true")
    parser.add_argument("--stock-list-status", default="L", help="Tushare stock_basic list_status, e.g. L or L,D.")
    parser.add_argument("--refresh-stock-list", action="store_true", help="Refetch Tushare stock_basic before downstream filtering.")
    parser.add_argument("--fallback-annual-report", action="store_true", help="Use previous annual report when Q1 MD&A is missing or too short.")
    parser.add_argument("--run-name", default=None, help="Optional fixed output folder name under data/outputs/runs.")
    parser.add_argument("--flat-output", action="store_true", help="Write outputs to data/outputs instead of creating a new run folder.")
    parser.add_argument("--all-boards", action="store_true", help="Disable the default Shanghai/Shenzhen main-board-only universe filter.")
    parser.add_argument("--llm-model", default=DEFAULT_LLM_MODEL, help="LLM model name written into LLM_MODEL for this run.")
    args = parser.parse_args()

    financial_candidates, manifest, result = run_staged_analysis(
        period=args.period,
        financial_period=args.financial_period,
        trade_date=args.trade_date,
        target_count=args.target_count,
        output_tag=args.output_tag,
        limit=args.limit,
        source=args.source,
        skip_refresh=args.skip_refresh,
        disable_llm=args.disable_llm,
        stock_list_status=args.stock_list_status,
        refresh_stock_list=args.refresh_stock_list,
        fallback_annual_report=args.fallback_annual_report,
        run_name=args.run_name,
        flat_output=args.flat_output,
        main_board_only=not args.all_boards,
        llm_model=args.llm_model,
    )
    output_dir_value = result.attrs.get("output_dir", "")
    output_dir = Path(output_dir_value) if output_dir_value else None

    print(f"Financial candidates: {len(financial_candidates)}")
    print(f"Manifest rows: {len(manifest)}")
    print(f"Analyzed rows: {len(result)}")
    print(f"Output directory: {output_dir or 'data/outputs'}")
    print(f"LLM model: {result.attrs.get('llm_model', '')}")
    print(period_output_path(f"financial_candidates_{args.output_tag}", args.period, ".xlsx", output_dir=output_dir))
    print(period_output_path(f"report_analysis_{args.output_tag}", args.period, ".xlsx", output_dir=output_dir))
    if not result.empty:
        cols = ["ts_code", "name", "market", "primary_theme", "candidate_status", "verification_total_score", "text_verdict", "analysis_source", "llm_model", "llm_error", "total_tokens"]
        print(result[[column for column in cols if column in result.columns]].to_string(index=False))


if __name__ == "__main__":
    main()
