# Anime Streaming Platform Analytics

*Analyzing viewer behaviour, revenue, retention and content performance for a
fictional anime streaming service — a Data Analyst portfolio project.*

> 🚧 **Work in progress.** Module 1 (dataset generation) is complete; cleaning,
> EDA, SQL analysis, KPIs, business questions, and Power BI dashboards follow.
> The full README (architecture, screenshots, results, interview Q&A) lands in
> the final module.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python scripts\generate_dataset.py   # build data/raw/anime_streaming_raw.csv (~41.5k rows)
python scripts\validate_dataset.py   # 26 realism + data-quality checks
```

## Project layout

```
├── data/raw|processed/   generated data (git-ignored, reproducible from seed)
├── scripts/              dataset generator + validation harness
├── notebooks/            01 cleaning · 02 EDA · 03 SQL · 04 business questions
├── sql/                  40+ interview-level queries
├── database/             SQLite star schema
├── powerbi/              model-ready exports, DAX measures, build guide
├── reports/              final business report
└── docs/                 data dictionary, KPI definitions, cleaning log
```

See [docs/data_dictionary.md](docs/data_dictionary.md) for all 41 columns and
the intentional data-quality issues baked into the raw file.
