# Repository Guidelines

## Project Structure & Module Organization
- `app.py` hosts the Flask app, routes, and DB access; `templates/` contains Jinja views (`base.html`, `index.html`, `search.html`).
- Data lives in `floats.db`; helper logic sits in `analyzer.py`, `utils.py`, and `locations.py`.
- The canonical refresh workflow lives in `scripts/refresh_data.py`; staged row validation lives in `scripts/validation_pipeline.py`.
- Generated artifacts include `all_floats_final.json`, `scraped_data/`, `generated/`, `floats.db`, and `float_model.pkl`.
- Deterministic HTML fixtures for parser tests live in `tests/fixtures/`.

## Build, Test, and Development Commands
- Create a venv and install deps: `python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt`.
- Run the app locally: `python app.py` (serves http://localhost:5000).
- Refresh the canonical dataset and rebuild derived artifacts: `python scripts/refresh_data.py refresh`.
- Validate canonical JSON, snapshots, manifest, and SQLite outputs: `python scripts/refresh_data.py validate`.
- Run staged record validation on the current database: `python scripts/refresh_data.py validate-records`.
- Run the deterministic test suite once `pytest` is installed: `python -m pytest tests/test_refresh_pipeline.py tests/test_validation_pipeline.py`.

## Coding Style & Naming Conventions
- Follow PEP 8; 4-space indents; favor small, pure functions over inline logic in routes.
- Use descriptive snake_case for Python and lower-hyphen/semantic class names in templates; keep Jinja expressions readable and side-effect free.
- Prefer explicit mappings/constants for data normalization (see `analyzer.py`), and keep shared UI styles in `base.html`.

## Testing Guidelines
- Keep tests deterministic and fixture-driven; do not rely on live HTTP or a manually started local server.
- Add unit tests around date parsing, location normalization, refresh-data transforms, and validation rules when modifying those areas.
- For UI changes, capture screenshots of `/` and `/search` and note any data filters used.
- Validate scrape updates by comparing row counts and spot-checking recent entries in `floats.db`.

## Commit & Pull Request Guidelines
- Commits: short, imperative subject (<=72 chars), include "why" in the body if non-obvious.
- PRs: summary of change, testing notes (commands run), data impact (DB schema or scrape changes), and screenshots for UI updates; link related issues/tasks when available.
