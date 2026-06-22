from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .analysis import analyze_candidates
from .env import get_env
from .io import load_candidates, read_table, write_table
from .paths import ensure_data_dirs, period_output_path


def load_manifest(period: str, manifest_path: Path | None = None) -> pd.DataFrame:
    path = manifest_path or period_output_path("report_manifest", period, ".xlsx")
    if not path.exists():
        csv_path = period_output_path("report_manifest", period, ".csv")
        path = csv_path if csv_path.exists() else path
    if not path.exists():
        return pd.DataFrame(columns=["ts_code", "section_path", "download_status", "parse_status"])
    return read_table(path)


def analyze_reports(
    period: str,
    candidate_path: Path | None = None,
    manifest_path: Path | None = None,
    limit: int | None = None,
    enable_llm: bool | None = None,
) -> pd.DataFrame:
    ensure_data_dirs()
    candidates = load_candidates(period, candidate_path)
    manifest = load_manifest(period, manifest_path)
    merged = candidates.merge(manifest, on=["ts_code", "name"], how="left", suffixes=("", "_report"))
    if enable_llm is None:
        enable_llm = bool(get_env("LLM_API_KEY") and get_env("LLM_MODEL"))
    result = analyze_candidates(merged, period=period, limit=limit, enable_llm=enable_llm)
    output_path = period_output_path("report_analysis", period, ".xlsx")
    write_table(result, output_path)
    write_table(result, period_output_path("report_analysis", period, ".csv"))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze cached interim report sections with optional LLM.")
    parser.add_argument("--period", default="20260630")
    parser.add_argument("--candidates", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--disable-llm", action="store_true")
    args = parser.parse_args()

    result = analyze_reports(
        period=args.period,
        candidate_path=args.candidates,
        manifest_path=args.manifest,
        limit=args.limit,
        enable_llm=not args.disable_llm,
    )
    print(f"Analyzed {len(result)} candidates.")
    print(period_output_path("report_analysis", args.period, ".xlsx"))


if __name__ == "__main__":
    main()

