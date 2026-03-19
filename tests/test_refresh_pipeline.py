import json
import sqlite3
from pathlib import Path

import pytest

from scripts.refresh_data import (
    AUDIT_PATH,
    CANONICAL_KEYS,
    MANIFEST_PATH,
    build_manifest,
    canonicalize_date,
    discover_year_filters_from_html,
    exclude_extreme_float_number_records,
    extract_date_from_detail_html,
    parse_listing_page,
    parse_title,
    rebuild_database,
    validate_outputs,
    write_json,
    write_per_year_snapshots,
)


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def sample_records() -> list[dict[str, str]]:
    return [
        {
            "id": "6001",
            "year": "2026",
            "title": "321 - Alex P.",
            "url": "https://example.com/6001",
            "image": "https://cdn.example.com/6001.jpg",
            "location": "Clay Head Trail",
            "date_found": "2026-06-12",
        },
        {
            "id": "6000",
            "year": "2025",
            "title": "120 Kim L.",
            "url": "https://example.com/6000",
            "image": "",
            "location": "Rodman's Hollow",
            "date_found": "",
        },
    ]


def test_discover_year_filters_from_html():
    filters = discover_year_filters_from_html(load_fixture("found_floats_page.html"))
    assert filters == {"2026": "31", "2025": "24"}


def test_parse_listing_page_extracts_records_and_next_skip():
    records, next_skip = parse_listing_page(load_fixture("found_floats_page.html"), "2026")
    assert [record["id"] for record in records] == ["6001", "6000"]
    assert records[0]["url"].endswith("/event/321-alex-p/6001/")
    assert next_skip == 24


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("267 - B. Massoia", ("267", "B. Massoia")),
        ("245 Amy K.", ("245", "Amy K.")),
        ("Finder Only", ("", "Finder Only")),
    ],
)
def test_parse_title(title, expected):
    assert parse_title(title) == expected


def test_extract_date_rejects_placeholder_and_parses_valid_date():
    assert extract_date_from_detail_html(load_fixture("event_detail_jsonld.html")) == "2026-06-12"
    assert extract_date_from_detail_html(load_fixture("event_detail_placeholder.html")) == ""
    assert canonicalize_date("2026-01-01T00:00:00-04:00") == ""


def test_build_manifest_counts_records():
    manifest = build_manifest(sample_records())
    assert manifest["total_records"] == 2
    assert manifest["latest_source_date"] == "2026-06-12"
    assert manifest["records_by_year"] == {"2026": 1, "2025": 1}
    assert manifest["missing_dates"] == 1
    assert manifest["missing_images"] == 1


def test_exclude_extreme_float_number_records_drops_isolated_outlier():
    records = [
        {
            "id": "6007",
            "year": "2025",
            "title": "#2044 Susan Farnham",
            "url": "https://example.com/6007",
            "image": "https://cdn.example.com/6007.jpg",
            "location": "Lameshur Bay Trail",
            "date_found": "2026-01-15",
        },
        {
            "id": "6006",
            "year": "2025",
            "title": "558 Cameron",
            "url": "https://example.com/6006",
            "image": "https://cdn.example.com/6006.jpg",
            "location": "Martin Lots",
            "date_found": "2025-10-09",
        },
        {
            "id": "6005",
            "year": "2025",
            "title": "553 Rita",
            "url": "https://example.com/6005",
            "image": "https://cdn.example.com/6005.jpg",
            "location": "Beach Ave Trail",
            "date_found": "2025-10-08",
        },
        {
            "id": "6004",
            "year": "2025",
            "title": "#552 L. Price",
            "url": "https://example.com/6004",
            "image": "https://cdn.example.com/6004.jpg",
            "location": "Rodman's Hollow",
            "date_found": "2025-10-09",
        },
        {
            "id": "6003",
            "year": "2025",
            "title": "551 B. Lavoie",
            "url": "https://example.com/6003",
            "image": "https://cdn.example.com/6003.jpg",
            "location": "Plover Hill",
            "date_found": "2025-10-11",
        },
        {
            "id": "6002",
            "year": "2025",
            "title": "550 D. Ciok",
            "url": "https://example.com/6002",
            "image": "https://cdn.example.com/6002.jpg",
            "location": "Old Mill",
            "date_found": "2025-10-09",
        },
        {
            "id": "6001",
            "year": "2025",
            "title": "546 Kristen B.",
            "url": "https://example.com/6001",
            "image": "https://cdn.example.com/6001.jpg",
            "location": "Rodman's Hollow",
            "date_found": "2025-10-20",
        },
    ]

    kept, dropped = exclude_extreme_float_number_records(records)

    assert {record["id"] for record in dropped} == {"6007"}
    assert {record["id"] for record in kept} == {"6001", "6002", "6003", "6004", "6005", "6006"}


def test_rebuild_database_is_deterministic(tmp_path: Path):
    records = sample_records()
    db_one = tmp_path / "one.db"
    db_two = tmp_path / "two.db"

    rebuild_database(records, db_one)
    rebuild_database(records, db_two)

    def rows_for(path: Path):
        conn = sqlite3.connect(path)
        rows = list(
            conn.execute(
                "SELECT id, year, float_number, finder, location_raw, location_normalized, date_found, url, image_url "
                "FROM finds ORDER BY id DESC"
            )
        )
        conn.close()
        return rows

    assert rows_for(db_one) == rows_for(db_two)


def test_validate_outputs_detects_json_db_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    records = sample_records()
    db_path = tmp_path / "floats.db"
    manifest_path = tmp_path / "refresh_manifest.json"
    snapshot_dir = tmp_path / "scraped_data"

    rebuild_database(records, db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO finds (
            id, year, float_number, finder, location_raw, location_normalized, date_found, url, image_url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (9999, 2024, "1", "Legacy", "Old Trail", "Old Trail", "", "", ""),
    )
    conn.commit()
    conn.close()

    write_json(manifest_path, build_manifest(records))
    monkeypatch.setattr("scripts.refresh_data.SCRAPED_DATA_DIR", snapshot_dir)
    write_per_year_snapshots(records)

    errors = validate_outputs(records, db_path=db_path, manifest_path=manifest_path)
    assert any("drift detected" in error.lower() for error in errors)


def test_canonical_fixture_shape():
    for record in sample_records():
        assert tuple(record.keys()) == CANONICAL_KEYS
