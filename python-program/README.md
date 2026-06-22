# A-Share Growth Screener Python Program

This directory contains the standalone Python program behind the `a-share-growth-screener` skill.

It screens A-share stocks with Tushare data, downloads and parses quarterly/interim reports, optionally uses an OpenAI-compatible LLM for text confirmation, and reviews results in Excel/CSV outputs or a Streamlit dashboard.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Fill `.env` or `.env.txt` locally:

```env
TUSHARE_TOKEN=your_token_here
LLM_API_KEY=optional_openai_compatible_key
LLM_BASE_URL=optional_openai_compatible_endpoint
LLM_MODEL=optional_model_name
```

Do not commit `.env`, `.env.txt`, downloaded reports, cache files, or generated Excel/CSV outputs.

## Run

```powershell
.\.venv\Scripts\python.exe -m stock_screener.screen_market --period 20260331 --target-count 30
.\.venv\Scripts\python.exe -m stock_screener.refresh_reports --period 20260331
.\.venv\Scripts\python.exe -m stock_screener.analyze_reports --period 20260331
.\.venv\Scripts\python.exe -m streamlit run app.py
```

PowerShell wrappers are included:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\screen_candidates.ps1 -Period 20260331 -TargetCount 30
powershell -NoProfile -ExecutionPolicy Bypass -File .\refresh_reports.ps1 -Period 20260331
powershell -NoProfile -ExecutionPolicy Bypass -File .\analyze_reports.ps1 -Period 20260331
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_dashboard.ps1
```

Outputs are written under `data/outputs/`. The program is a research helper only and does not provide investment advice, position sizing, or automated trading.
