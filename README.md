# A-Share Growth Screener Skill

中文说明：[README.zh-CN.md](README.zh-CN.md)

This repository contains the `a-share-growth-screener` Codex skill.

The skill bundles a complete Tushare-based A-share research workflow for:

- quantitative screening of low-valuation growth candidates;
- quarterly/interim report download and parsing;
- optional OpenAI-compatible LLM text validation;
- Excel/CSV output generation;
- Streamlit dashboard review.

Skill entrypoint:

```text
a-share-growth-screener/SKILL.md
```

Standalone Python program:

```text
python-program/
```

Bundled project template:

```text
a-share-growth-screener/assets/a-share-growth-screener-project/
```

Materialize the project:

```powershell
python a-share-growth-screener\scripts\materialize_project.py .\a-share-growth-screener-project
```

Run the standalone program:

```powershell
cd python-program
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

This is a research workflow only. It does not provide investment advice, buy/sell points, position sizing, or automated trading.
