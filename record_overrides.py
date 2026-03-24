import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent
RECORD_OVERRIDES_PATH = REPO_ROOT / "data" / "record_overrides.json"

RECORD_OVERRIDE_FIELDS = {
    "title_override": "title",
    "location_override": "location",
    "date_found_override": "date_found",
    "year_override": "year",
    "url_override": "url",
    "image_override": "image",
}
DB_OVERRIDE_FIELDS = (
    "float_number_override",
    "finder_override",
    "location_normalized_override",
)


def normalize_override_entry(entry: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {}

    normalized: dict[str, Any] = {}
    for key in (*RECORD_OVERRIDE_FIELDS, *DB_OVERRIDE_FIELDS, "notes"):
        if key in entry:
            value = entry.get(key, "")
            normalized[key] = "" if value is None else str(value).strip()

    waivers = entry.get("validation_waivers", [])
    if isinstance(waivers, list):
        normalized["validation_waivers"] = [
            str(value).strip() for value in waivers if str(value or "").strip()
        ]
    elif waivers:
        normalized["validation_waivers"] = [str(waivers).strip()]
    else:
        normalized["validation_waivers"] = []

    return normalized


def load_record_overrides(path: Path = RECORD_OVERRIDES_PATH) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        return {}
    return {
        str(record_id): normalize_override_entry(entry)
        for record_id, entry in payload.items()
        if isinstance(entry, dict)
    }


def apply_record_override(record: dict[str, Any], override: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}

    override = normalize_override_entry(override)
    updated = dict(record)
    for override_key, record_key in RECORD_OVERRIDE_FIELDS.items():
        if override_key in override:
            updated[record_key] = override.get(override_key, "")
    return updated


def get_validation_waivers(
    record_id: str,
    overrides: dict[str, dict[str, Any]] | None = None,
) -> set[str]:
    if not overrides:
        return set()
    override = normalize_override_entry(overrides.get(str(record_id)))
    return set(override.get("validation_waivers", []))
