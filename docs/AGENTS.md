# Repository Guidelines

## Project Layout

- `app.py` hosts the Flask app, routes, and page rendering.
- `analyzer.py`, `ml_predictor.py`, `locations.py`, and `utils.py` hold analytics, forecast logic, location metadata, and shared helpers.
- `templates/` and `static/` contain the UI.
- `scripts/refresh_data.py` orchestrates refreshes; `scripts/validation_pipeline.py` handles staged validation output.
- `scripts/manual_checks/` contains opt-in smoke checks and data probes that may depend on the live site, a local server, Playwright, or the committed production DB.

## Development Commands

- Create a virtual environment: `python -m venv .venv`
- Activate it on Windows: `.venv\Scripts\activate`
- Install runtime and test deps: `pip install -r requirements.txt pytest`
- Run the app locally: `python app.py`
- Run automated tests: `pytest -q`
- Refresh tracked artifacts: `python scripts/refresh_data.py refresh`
- Validate refresh outputs: `python scripts/refresh_data.py validate`
- Run row-level validation against the current DB: `python scripts/refresh_data.py validate-records`

## Testing Conventions

- `pytest.ini` constrains automated collection to `tests/`.
- `tests/test_*.py` must stay deterministic, self-contained, and safe for CI.
- Do not add live HTTP, real Playwright browsing, or committed-DB audit probes to `tests/`.
- Put opt-in checks under `scripts/manual_checks/`; examples include `scripts/manual_checks/verify_ids.py` and `scripts/manual_checks/verify_location.py`.
- For route coverage, prefer Flask test-client assertions and monkeypatched dependencies over background servers or print-only scripts.

## Coding Notes

- Follow PEP 8 with 4-space indentation.
- Prefer small functions and explicit data-shaping helpers over inline route logic.
- Keep shared styling centralized in `templates/base.html`.
- Treat tracked data artifacts as intentional repo contents unless a task explicitly changes that policy.

## Docs Sources Of Truth

- Canonical current-state docs: `README.md`, this file, and `docs/IMPLEMENTATION_STATUS.md`.
- Historical planning docs: `docs/FEATURE_AUDIT.md`, `docs/ROADMAP.md`, and `docs/archive/AUDIT_SUMMARY_2025-11-23.md`.
