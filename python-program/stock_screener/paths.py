from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
OUTPUT_DIR = DATA_DIR / "outputs"
RUNS_DIR = OUTPUT_DIR / "runs"
REPORT_DIR = DATA_DIR / "reports"
REPORT_PDF_DIR = REPORT_DIR / "pdf"
REPORT_TEXT_DIR = REPORT_DIR / "text"
REPORT_SECTION_DIR = REPORT_DIR / "sections"
CONFIG_DIR = PROJECT_ROOT / "config"
DEFAULT_RULES_PATH = CONFIG_DIR / "rules.yaml"


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def ensure_data_dirs() -> None:
    for path in [
        DATA_DIR,
        CACHE_DIR,
        OUTPUT_DIR,
        RUNS_DIR,
        REPORT_DIR,
        REPORT_PDF_DIR,
        REPORT_TEXT_DIR,
        REPORT_SECTION_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def safe_run_name(value: str) -> str:
    cleaned = _SAFE_NAME_RE.sub("_", value.strip()).strip("._-")
    return cleaned or "run"


def create_run_output_dir(output_tag: str, period: str, run_name: str | None = None) -> Path:
    ensure_data_dirs()
    base_name = run_name or f"{output_tag}_{period}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    base_name = safe_run_name(base_name)
    path = RUNS_DIR / base_name
    if not path.exists():
        path.mkdir(parents=True, exist_ok=False)
        return path

    for index in range(2, 1000):
        candidate = RUNS_DIR / f"{base_name}_{index}"
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
    raise RuntimeError(f"Unable to create unique run output directory for {base_name}")


def period_output_path(prefix: str, period: str, suffix: str = ".xlsx", output_dir: Path | None = None) -> Path:
    base_dir = output_dir or OUTPUT_DIR
    return base_dir / f"{prefix}_{period}{suffix}"
