# Implementation Status

Last updated: 2026-03-21

## Current State

- The production app includes the dashboard, field mode, location detail pages, search, about page, forecast page, and PWA assets.
- The repo intentionally tracks the current canonical dataset and generated artifacts: `all_floats_final.json`, `floats.db`, `scraped_data/`, and committed refresh outputs under `generated/`.
- Forecast predictions now train in memory from the current SQLite database on first use; there is no committed model binary.
- `scripts/refresh_data.py` is the supported entrypoint for rebuilding artifacts and validation reports.
- The refresh pipeline supports both incremental runs and an opt-in full historical refetch; `scripts/start_full_refresh.ps1` is the supported detached launcher for the long-running full rebuild.
- The dashboard already includes the "Still Out There!" stat card; older docs describing it as a manual follow-up are stale.

## Testing And Verification

- Automated coverage lives under `tests/` and is meant to run with `pytest -q`.
- `pytest.ini` limits collection to `tests/` so manual probes do not leak into CI.
- Manual checks that depend on the external site, a locally running server, Playwright, or the committed production DB live in `scripts/manual_checks/`.
- Validation reports are generated locally during `validate` runs and are not committed.

## Known Constraints

- Large data artifacts are still part of the tracked repo by design.
- Location normalization remains primarily runtime logic in `analyzer.py`; the `location_normalized` column is not the source of truth.
- Search remains capped at 50 results and the dashboard map still limits marker volume.
- Some records still lack dates, images, or mapped coordinates, which affects forecast and field-mode completeness.

## Current Docs

- Canonical: `README.md`, `docs/AGENTS.md`, and this file.
- Historical reference only: `docs/FEATURE_AUDIT.md`, `docs/ROADMAP.md`, `docs/archive/AUDIT_SUMMARY_2025-11-23.md`, and the archived point-in-time notes under `docs/archive/`.
