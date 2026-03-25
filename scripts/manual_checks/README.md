# Manual Checks

These scripts are intentionally separate from automated pytest coverage. They are helpful for one-off debugging, source verification, and local sanity checks that may rely on network access or a running local app instance.

## Scripts

- `verify_changes.py`
  - Starts the local Flask app on port `5001`.
  - Requests `/` and `/about` and prints simple content/status checks.
- `verify_requests.py`
  - Sends a direct request to the upstream events endpoint used by the refresh pipeline.
  - Prints status code and a truncated response payload.
- `verify_ids.py`
  - Uses Playwright to open curated category-filter URLs and print the first visible event title.
- `verify_location.py`
  - Reads local `floats.db` and prints counts related to `Other/Unknown` normalization.
- `verify_regex.py`
  - Runs sample strings against date-extraction regexes and prints parsed values.

## Usage

From repo root:

```bash
python scripts/manual_checks/verify_changes.py
python scripts/manual_checks/verify_requests.py
python scripts/manual_checks/verify_ids.py
python scripts/manual_checks/verify_location.py
python scripts/manual_checks/verify_regex.py
```

## Notes

- These are manual diagnostics; they are not run in CI.
- `verify_ids.py` requires Playwright + Chromium (`python -m playwright install chromium`).
- `verify_changes.py` and `verify_location.py` expect a valid local environment and committed data artifacts.
