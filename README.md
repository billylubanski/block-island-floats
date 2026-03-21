# Block Island Glass Float Tracker

Flask app for exploring historical Block Island Glass Float finds, field-planning on mobile, and refreshing the tracked data artifacts that power the site.

## Core Features

- Dashboard with year filtering, recovery-rate tables, and a Leaflet heatmap.
- Field mode with GPS-aware distance sorting and weather context.
- Location detail pages with find history and photo galleries.
- Forecast page backed by seasonality scoring and an in-memory model trained from the local database.
- Search, about page, and PWA assets for installable mobile use.
- Refresh pipeline that rebuilds the canonical JSON, SQLite database, and generated reports.

## Local Development

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python app.py
```

The app serves at `http://localhost:5000`.

Set `$env:FLASK_DEBUG = "1"` before `python app.py` if you want the Flask debug server locally.

`requirements.txt` mirrors the production install. Use `requirements-dev.txt` for local development, tests, and refresh tooling.

## Render Deploy

Render can keep using the default build command:

```bash
pip install -r requirements.txt
```

That resolves to the lean production dependency set and keeps test and refresh-only tooling such as `pytest`, `playwright`, and BeautifulSoup out of the production image.

## Automated Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

- Automated test collection is limited to `tests/` via `pytest.ini`.
- `tests/test_*.py` should stay deterministic and network-free.
- Manual probes live under `scripts/manual_checks/` and are opt-in only.

## Data Refresh

```bash
pip install -r requirements-dev.txt
python scripts/refresh_data.py refresh
python scripts/refresh_data.py validate
python scripts/refresh_data.py validate-records
```

- `all_floats_final.json` is the canonical dataset committed to the repo.
- `floats.db`, `scraped_data/floats_*.json`, and refresh outputs under `generated/` are rebuilt from that canonical data.
- Forecast predictions train in memory from `floats.db` on first use; no model binary is committed.
- `.github/workflows/refresh-data.yml` runs the refresh flow weekly and opens or updates an automated PR when source data changes.

## Repository Map

- `app.py` contains Flask routes and page-level wiring.
- `analyzer.py`, `ml_predictor.py`, `locations.py`, and `utils.py` contain analytics, ML, lookup data, and shared helpers.
- `scripts/refresh_data.py` and `scripts/validation_pipeline.py` drive refresh and validation.
- `tests/` contains automated pytest coverage.
- `scripts/manual_checks/` contains manual checks that may hit the live site, expect a local server, or inspect the committed production DB.
- `docs/IMPLEMENTATION_STATUS.md`, `docs/AGENTS.md`, and this README are the canonical current-state docs.

## Validation Pipeline

- Validation stages data through `finds_raw`, `finds_normalized`, and `validation_report`.
- Rows may include `is_valid`, `validation_errors`, `confidence_score`, `source`, and `suspicious_flags`.
- App routes support `?valid_only=1` to ignore invalid rows when validation metadata exists.
- Validation reports are written to `generated/validation_report.json` and `generated/validation_report.csv` as local validation outputs and are not committed.

## Historical Docs

- `docs/FEATURE_AUDIT.md` and `docs/ROADMAP.md` are preserved as historical planning/reference docs.
- `docs/archive/AUDIT_SUMMARY_2025-11-23.md` archives the original November 23, 2025 summary snapshot.
- Archived point-in-time notes such as `docs/archive/date_analysis_summary.md`, `docs/archive/alltrails_research.md`, and `docs/archive/RECOVERY_RATE_UPDATE.md` live under `docs/archive/`.

## Data Source

All float data is sourced from the official [Block Island Glass Float Project](https://www.blockislandinfo.com/glass-float-project/) website.
