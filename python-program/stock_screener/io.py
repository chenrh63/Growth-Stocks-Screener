from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from .paths import OUTPUT_DIR


def read_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"Unsupported table format: {path}")


def write_table(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        df.to_excel(path, index=False)
    elif suffix == ".csv":
        df.to_csv(path, index=False, encoding="utf-8-sig")
    else:
        raise ValueError(f"Unsupported table format: {path}")


def first_existing(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def default_candidate_paths(period: str) -> list[Path]:
    return [
        OUTPUT_DIR / f"candidates_{period}.xlsx",
        OUTPUT_DIR / f"candidates_{period}.csv",
        OUTPUT_DIR / f"initial_candidates_{period}.xlsx",
        OUTPUT_DIR / f"initial_candidates_{period}.csv",
    ]


def load_candidates(period: str, candidate_path: Path | None = None) -> pd.DataFrame:
    path = candidate_path or first_existing(default_candidate_paths(period))
    if path is None:
        options = "\n".join(str(p) for p in default_candidate_paths(period))
        raise FileNotFoundError(
            "Candidate file not found. Create one of:\n"
            f"{options}\n"
            "Minimum columns: ts_code,name"
        )

    df = read_table(path)
    required = {"ts_code", "name"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Candidate file {path} missing required columns: {missing}")
    df = df.copy()
    df["ts_code"] = df["ts_code"].astype(str).str.strip()
    df["name"] = df["name"].astype(str).str.strip()
    return df

