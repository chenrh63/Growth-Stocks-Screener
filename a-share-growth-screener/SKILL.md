---
name: a-share-growth-screener
description: A-share quarterly and interim-report growth validation screener. Use when Codex needs to create, run, explain, or adapt a Tushare-based A-share stock screening workflow that filters non-AI/TMT low-valuation growth candidates, downloads official reports, extracts report sections, optionally calls an OpenAI-compatible LLM for text confirmation, produces Excel/CSV outputs, and launches a Streamlit dashboard. Trigger on A股筛选, 季报成长验证, 半年报跟踪, Tushare 股票池, report_analysis, screen_candidates, or stock_screener tasks.
---

# A-Share Growth Screener

## Overview

Use this skill to materialize and operate a complete A-share growth-screening project. The bundled project screens A-share stocks with Tushare data, validates candidates with quarterly or interim-report text, optionally uses an OpenAI-compatible LLM, and presents results through CSV/XLSX outputs plus a Streamlit dashboard.

This is a research assistant, not an investment-advice or trading system. Do not generate buy/sell instructions, position sizing, or automated trades from its outputs.

## Quick Start

Materialize the bundled project into the current workspace:

```powershell
python path\to\a-share-growth-screener\scripts\materialize_project.py .\a-share-growth-screener-project
```

If `python` is unavailable, use the active Codex/runtime Python executable. The script copies `assets/a-share-growth-screener-project/` into the destination and prints the next setup commands.

Set up the project:

```powershell
cd .\a-share-growth-screener-project
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Fill `.env` or `.env.txt` with:

```env
TUSHARE_TOKEN=your_token_here
LLM_API_KEY=optional_openai_compatible_key
LLM_BASE_URL=optional_openai_compatible_endpoint
LLM_MODEL=optional_model_name
```

Run the main workflow:

```powershell
.\.venv\Scripts\python.exe -m stock_screener.screen_market --period 20260331 --target-count 30
.\.venv\Scripts\python.exe -m stock_screener.refresh_reports --period 20260331
.\.venv\Scripts\python.exe -m stock_screener.analyze_reports --period 20260331
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## Workflow

1. Screen the A-share market with `stock_screener.screen_market`.
2. Refresh report artifacts with `stock_screener.refresh_reports`.
3. Analyze cached report sections with `stock_screener.analyze_reports`.
4. Review outputs in `data/outputs/` or launch `app.py` with Streamlit.
5. Tune screening and text-analysis thresholds in `config/rules.yaml`.

Use `--period` for report periods such as `20260331`, `20260630`, `20260930`, or `20261231`. Use `--target-count` to control the candidate-pool size.

## Output Contract

Expected key files:

- `data/outputs/candidates_<period>.xlsx`: first-stage quantitative candidate pool.
- `data/outputs/report_manifest_<period>.xlsx`: report download, parse, and section-extraction status.
- `data/outputs/report_analysis_<period>.xlsx`: final table with financial scores, text confirmation scores, LLM verdicts, evidence, and errors.
- `data/outputs/runs/`: timestamped run folders when `--flat-output` is not used.

Candidate statuses:

- `A_confirmed`: financial and report-text evidence both support continued tracking.
- `B_watch`: growth evidence exists but visibility, quality, cash flow, or risk needs monitoring.
- `C_reject`: growth evidence is weak, contradicted, or risk has worsened.
- `D_pending`: report, PDF parsing, section extraction, or LLM configuration is incomplete.

## Guardrails

- Never commit `.env`, `.env.txt`, API keys, downloaded reports, caches, or generated Excel/CSV outputs.
- Treat Tushare announcement access as permission-dependent. If `anns_d` is unavailable, the project falls back to CNInfo-style announcement lookup where possible.
- If `LLM_API_KEY` or `LLM_MODEL` is missing, the workflow should still run deterministic report parsing and mark text-analysis items as pending instead of failing the whole run.
- For live prices, valuations, and current report availability, rerun data collection instead of relying on old cached outputs.
- Keep output language clear that results are research candidates, not investment recommendations.

## Bundled Resources

- `scripts/materialize_project.py`: copies the full runnable project template into a destination folder.
- `assets/a-share-growth-screener-project/`: the complete Python project, including `stock_screener/`, `config/rules.yaml`, Streamlit dashboard, PowerShell wrappers, requirements, and tests.
- `references/program-usage.md`: detailed command reference, configuration notes, and output interpretation.

Read `references/program-usage.md` when the user asks for setup help, command variations, output interpretation, or troubleshooting.
