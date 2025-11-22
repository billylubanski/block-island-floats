# Repository Guidelines

## Project Structure & Module Organization
- `app.py` hosts the Flask app, routes, and DB access; `templates/` contains Jinja views (`base.html`, `index.html`, `search.html`).
- Data lives in `floats.db`; helper logic sits in `analyzer.py`, `utils.py`, and `locations.py` (location lookup data).
- Scraping/import scripts (e.g., `scrape_dates_complete.py`, `scrape_floats_playwright.py`, `populate_db.py`, `add_urls_to_db.py`) keep the database current; `scraped_data/` stores pulled artifacts.
- Debug/reference HTML/text files capture scrape results and should not be shipped to production.

## Build, Test, and Development Commands
- Create venv and install deps: `python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt`.
- Run the app locally: `python app.py` (serves http://localhost:5000).
- Smoke-check scrapers (as needed): `python scrape_dates_complete.py` or other `scrape_*.py` scripts; ensure respectful concurrency before running.
- Ad-hoc verifications: `python test_regex.py` (date parsing), `python test_requests.py` / `test_api.py` (endpoint reachability). No formal pytest suite yet—add one when modifying logic.

## Coding Style & Naming Conventions
- Follow PEP 8; 4-space indents; favor small, pure functions over inline logic in routes.
- Use descriptive snake_case for Python and lower-hyphen/semantic class names in templates; keep Jinja expressions readable and side-effect free.
- Prefer explicit mappings/constants for data normalization (see `analyzer.py`), and keep shared UI styles in `base.html`.

## Testing Guidelines
- Add unit tests around date parsing, location normalization, and any new analytics before merging; keep fixtures deterministic (no live HTTP in tests—mock or use saved HTML in `scraped_data/`).
- For UI changes, capture screenshots of `/` and `/search` and note any data filters used.
- Validate scrape updates by comparing row counts and spot-checking recent entries in `floats.db`.

## Commit & Pull Request Guidelines
- Commits: short, imperative subject (≤72 chars), include “why” in the body if non-obvious.
- PRs: summary of change, testing notes (commands run), data impact (DB schema or scrape changes), and screenshots for UI updates; link related issues/tasks when available.
