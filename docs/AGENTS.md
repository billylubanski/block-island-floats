# Repository Guidelines

## Project Structure & Module Organization
- `app.py` hosts the Flask app, routes, and DB access; `templates/` and `static/` contain the UI.
- Core helpers live in `analyzer.py`, `ml_predictor.py`, `locations.py`, and `utils.py`.
- The canonical refresh workflow lives in `scripts/refresh_data.py`; staged row validation lives in `scripts/validation_pipeline.py`.
- Manual probes that may hit the live site, require Playwright, expect a local server, or inspect the committed production DB live in `scripts/manual_checks/`.
- Generated artifacts include `all_floats_final.json`, `scraped_data/`, committed refresh outputs in `generated/`, and `floats.db`.
- Forecast predictions train from `floats.db` in memory; no committed model binary is part of the repo state.
- Deterministic HTML fixtures for parser tests live in `tests/fixtures/`.

## Build, Test, and Development Commands
- Create a venv and install deps: `python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt`.
- Run the app locally: `python app.py` (serves http://localhost:5000).
- Enable Flask debug mode explicitly when needed: `$env:FLASK_DEBUG='1'; python app.py`.
- Refresh the canonical dataset and rebuild derived artifacts: `python scripts/refresh_data.py refresh`.
- Validate canonical JSON, snapshots, manifest, and SQLite outputs: `python scripts/refresh_data.py validate`.
- Run staged record validation on the current database: `python scripts/refresh_data.py validate-records`.
- Run the automated test suite once Python and pytest are available: `pytest -q`.

## Testing Guidelines
- `pytest.ini` constrains automated collection to `tests/`.
- Keep `tests/test_*.py` deterministic and fixture-driven; do not rely on live HTTP or a manually started local server.
- Prefer Flask test-client assertions and monkeypatched dependencies over background servers or print-only scripts.
- Put opt-in checks under `scripts/manual_checks/`; examples include `scripts/manual_checks/verify_ids.py`, `scripts/manual_checks/verify_location.py`, and `scripts/manual_checks/verify_requests.py`.
- For UI changes, capture screenshots of `/` and `/search` and note any data filters used.

## Coding Notes
- Follow PEP 8; use 4-space indentation and descriptive snake_case names.
- Favor small, pure helper functions over inline route logic.
- Prefer explicit mappings/constants for normalization rules and keep shared UI styles in `templates/base.html`.
- Treat tracked data artifacts as intentional repo contents unless a task explicitly changes that policy.

## Commit & Pull Request Guidelines
- Commits: short, imperative subject (<=72 chars), include the reason in the body if non-obvious.
- PRs: summarize the change, note testing commands run, call out data impact, and include screenshots for UI updates when relevant.

## Docs Sources Of Truth
- Canonical current-state docs: `README.md`, this file, and `docs/IMPLEMENTATION_STATUS.md`.
- Historical reference docs: `docs/FEATURE_AUDIT.md`, `docs/ROADMAP.md`, and the archived notes under `docs/archive/`.
