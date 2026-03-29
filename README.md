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
# PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements-dev.txt
python app.py
```

The app serves at `http://localhost:5000`.

Set `FLASK_DEBUG=1` before `python app.py` if you want the Flask debug server locally (PowerShell: `$env:FLASK_DEBUG = "1"`).

`requirements.txt` mirrors the production install. Use `requirements-dev.txt` for local development, tests, and refresh tooling.

## Cloud Deploy

The repo now includes checked-in deployment/runtime files:

- `.python-version` pins the cloud Python major/minor version to the tested `3.12` line.
- `.env.example` documents the runtime knobs used by the app, Gunicorn, and optional offline forecast refresh tooling.
- `.env.render.example` trims that list to the settings you would actually manage in the Render dashboard.
- `render.yaml` defines a Render web service with the correct build/start commands and `/healthz` health check.
- `gunicorn.conf.py` centralizes the Render/container runtime settings so the web process behaves the same across deploy paths.
- `Dockerfile` and `.dockerignore` provide a container path for any Docker-compatible cloud host.
- `Procfile` matches the same Gunicorn command shape used by the other deploy paths.

### Render

```bash
pip install -r requirements.txt
```

Render can use the included `render.yaml` Blueprint, or the equivalent native service settings:

- Region: `oregon`
- Instance type: `free`
- Build command: `pip install --upgrade pip && pip install -r requirements.txt`
- Start command: `gunicorn -c gunicorn.conf.py app:app`
- Health check path: `/healthz`

`requirements.txt` still resolves to the lean production dependency set and keeps test and refresh-only tooling such as `pytest`, `playwright`, and BeautifulSoup out of the production image.

No secret environment variables are required to serve the Flask app itself. `PORT` is platform-managed on Render. The checked-in [`.env.render.example`](./.env.render.example) values are the knobs you would mirror into the Render dashboard if you want to override the defaults. `NOAA_CDO_TOKEN` is optional and is only used when you run the offline forecast/data refresh pipeline.

### Docker / Container Hosts

```bash
docker build -t bi-float-tracker .
docker run --rm -p 5000:5000 --env-file .env bi-float-tracker
```

For local container runs, copy `.env.example` to `.env` and adjust values only if needed.

## Automated Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

- Automated test collection is limited to `tests/` via `pytest.ini`.
- `tests/test_*.py` should stay deterministic and network-free.
- Browser-backed UI smoke tests live in `tests/test_ui_smoke.py`, start their own local server, and stub third-party assets so they stay network-free.
- Install Chromium once locally if you want the Playwright smoke checks to run instead of skip: `python -m playwright install chromium`
- Enable the browser smoke layer with `$env:RUN_UI_SMOKE='1'`, then run `pytest -q -m ui`.
- Manual probes live under `scripts/manual_checks/` and are opt-in only.

### Optional: Chrome DevTools MCP

If you use Codex on Windows and want interactive browser debugging beyond the deterministic Playwright smoke layer, add Chrome DevTools MCP to `C:\Users\Billy\.codex\config.toml`:

```toml
[mcp_servers.chrome-devtools]
command = 'cmd'
args = [
    '/c',
    'npx',
    '-y',
    'chrome-devtools-mcp@latest',
]
env = { SystemRoot='C:\\Windows', PROGRAMFILES='C:\\Program Files' }
startup_timeout_ms = 20_000
```

Restart Codex after updating the config. Use the `chrome-devtools` server for exploratory checks against a local `python app.py` session when you need DOM snapshots, screenshots, console logs, network inspection, or performance traces. This is manual/debug tooling only; keep automated coverage in `tests/`.

## Repo Hygiene Quick Checks

Use these before pushing larger refresh or feature branches:

```bash
pip install -r requirements-dev.txt
pytest -q
python scripts/refresh_data.py validate
python scripts/refresh_data.py validate-records
```

- `pytest -q` catches route/parser regressions and local data-shape assumptions.
- `validate` checks pipeline-level integrity and report generation.
- `validate-records` runs record-level auditing focused on suspicious or malformed rows.

## Data Refresh

```bash
pip install -r requirements-dev.txt
python scripts/refresh_data.py refresh
python scripts/refresh_data.py refresh --full
python scripts/refresh_data.py validate
python scripts/refresh_data.py validate-records
```

- `all_floats_final.json` is the canonical dataset committed to the repo.
- `floats.db`, `scraped_data/floats_*.json`, and refresh outputs under `generated/` are rebuilt from that canonical data.
- Forecast predictions are generated offline during refresh and committed as `generated/forecast_artifact.json`.
- `.github/workflows/refresh-data.yml` is currently manual-only while the upstream source is blocking automated archive access.
- `refresh` is the normal incremental path. `refresh --full` refetches every sitemap detail page so new parser, forecast, and validation features are applied across the full historical dataset.
- For local long-running rebuilds, run `.\scripts\start_full_refresh.ps1`. It launches the full refresh in the background and writes timestamped stdout/stderr logs plus `output/refresh/latest-full-refresh.json` status metadata.

## Repository Map

- `app.py` contains Flask routes and page-level wiring, including loading the committed forecast artifact.
- `analyzer.py`, `ml_predictor.py`, `locations.py`, and `utils.py` contain analytics, offline ML generation, lookup data, and shared helpers.
- `scripts/refresh_data.py` and `scripts/validation_pipeline.py` drive refresh and validation.
- `tests/` contains automated pytest coverage.
- `scripts/manual_checks/` contains manual checks that may hit the live site, expect a local server, or inspect the committed production DB (see `scripts/manual_checks/README.md`).
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
