# A-Share Growth Screener Skill

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

Bundled project template:

```text
a-share-growth-screener/assets/a-share-growth-screener-project/
```

Materialize the project:

```powershell
python a-share-growth-screener\scripts\materialize_project.py .\a-share-growth-screener-project
```

This is a research workflow only. It does not provide investment advice, buy/sell points, position sizing, or automated trading.
