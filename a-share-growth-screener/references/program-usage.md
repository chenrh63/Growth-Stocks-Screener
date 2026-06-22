# A-Share Growth Screener Usage

## Configuration

Create `.env` or `.env.txt` in the materialized project root:

```env
TUSHARE_TOKEN=your_token_here
LLM_API_KEY=optional_openai_compatible_key
LLM_BASE_URL=optional_openai_compatible_endpoint
LLM_MODEL=optional_model_name
```

`TUSHARE_TOKEN` is required for market screening and backtests. LLM settings are optional; without them, report parsing still runs and text confirmation is marked pending.

## Main Commands

Run first-stage screening:

```powershell
.\.venv\Scripts\python.exe -m stock_screener.screen_market --period 20260331 --target-count 30
```

Refresh announcement PDFs, parsed text, and extracted sections:

```powershell
.\.venv\Scripts\python.exe -m stock_screener.refresh_reports --period 20260331
```

Analyze cached report sections:

```powershell
.\.venv\Scripts\python.exe -m stock_screener.analyze_reports --period 20260331
```

Launch the dashboard:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

PowerShell wrappers are also included:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\screen_candidates.ps1 -Period 20260331 -TargetCount 30
powershell -NoProfile -ExecutionPolicy Bypass -File .\refresh_reports.ps1 -Period 20260331
powershell -NoProfile -ExecutionPolicy Bypass -File .\analyze_reports.ps1 -Period 20260331
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_dashboard.ps1
```

## Periods

Use report-period strings:

- `YYYY0331`: first quarter.
- `YYYY0630`: half year.
- `YYYY0930`: third quarter.
- `YYYY1231`: annual report.

The default workflow was originally exercised with `20260331` and `20260630`.

## Outputs

- `data/outputs/candidates_<period>.xlsx` and `.csv`: quantitative candidate pool.
- `data/outputs/report_manifest_<period>.xlsx` and `.csv`: report discovery, download, parse, and section status.
- `data/outputs/report_analysis_<period>.xlsx` and `.csv`: final financial and text-confirmation table.
- `data/outputs/runs/`: timestamped runs when `screen_market` does not use `--flat-output`.

## Tuning

Edit `config/rules.yaml` for target count, excluded industries/themes, valuation thresholds, growth scoring, mispricing scoring, text-analysis weights, and final candidate-status thresholds.

Useful `screen_market` flags:

- `--target-count N`: candidate-pool size.
- `--financial-period YYYYMMDD`: financial period used for first-stage screening.
- `--trade-date YYYYMMDD`: fixed Tushare trade date.
- `--refresh-stock-list`: refetch `stock_basic`.
- `--no-price-history`: skip daily price-history calls.
- `--flat-output`: write directly to `data/outputs/`.
- `--all-boards`: disable the default Shanghai/Shenzhen main-board filter.

## Safety

Do not commit `.env`, `.env.txt`, downloaded PDFs, parsed report text, caches, or generated Excel/CSV outputs. Keep all generated conclusions framed as research candidates, not investment advice.
