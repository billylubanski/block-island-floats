import json
import sqlite3
from pathlib import Path

from scripts.validation_pipeline import run_validation_pipeline


def setup_finds_table(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE finds (
            id INTEGER PRIMARY KEY,
            year INTEGER,
            float_number TEXT,
            finder TEXT,
            location_raw TEXT,
            location_normalized TEXT,
            date_found TEXT,
            url TEXT,
            image_url TEXT
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO finds (
            id, year, float_number, finder, location_raw, location_normalized, date_found, url, image_url
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                1,
                2025,
                "12",
                "Alice",
                "Clayhead Trail",
                "Clay Head Trail",
                "2025-06-01",
                "https://example.com/1",
                "https://cdn.example.com/1.jpg",
            ),
            (
                2,
                2025,
                "",
                "#421 Bob",
                "Ocean View",
                "Ocean View Pavilion",
                "2025-07-02",
                "https://example.com/2",
                "https://cdn.example.com/2.jpg",
            ),
            (
                3,
                2025,
                "55",
                "Casey",
                "",
                "",
                "13/45/2025",
                "https://example.com/3",
                "not-a-url",
            ),
            (
                4,
                2025,
                "12",
                "Alice",
                "Clayhead Trail",
                "Clay Head Trail",
                "2025-06-01",
                "https://example.com/1",
                "https://cdn.example.com/1.jpg",
            ),
        ],
    )
    conn.commit()
    conn.close()


def test_run_validation_pipeline_creates_stages_and_reports(tmp_path: Path):
    db_path = tmp_path / "floats.db"
    report_json = tmp_path / "generated" / "validation_report.json"
    report_csv = tmp_path / "generated" / "validation_report.csv"
    setup_finds_table(db_path)

    summary = run_validation_pipeline(
        db_path=db_path,
        report_json_path=report_json,
        report_csv_path=report_csv,
        default_source="test_source",
        run_id="test_run",
    )

    assert summary["total_rows"] == 4
    assert summary["invalid_rows"] >= 2
    assert summary["suspicious_rows"] >= 2
    assert summary["flagged_rows"] >= 2
    assert report_json.exists()
    assert report_csv.exists()

    payload = json.loads(report_json.read_text(encoding="utf-8"))
    flagged_ids = {str(row["id"]) for row in payload["flagged_records"]}
    assert {"2", "3"}.issubset(flagged_ids)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    columns = {row[1] for row in conn.execute("PRAGMA table_info(finds)").fetchall()}
    assert {"is_valid", "validation_errors", "confidence_score", "source"}.issubset(columns)

    row_two = conn.execute(
        "SELECT is_valid, validation_errors, suspicious_flags, source FROM finds WHERE id = 2"
    ).fetchone()
    assert row_two["is_valid"] == 0
    assert "invalid_float_number" in row_two["validation_errors"]
    assert "blank_float_with_hash_finder" in row_two["suspicious_flags"]
    assert row_two["source"] == "test_source"

    raw_count = conn.execute("SELECT COUNT(*) FROM finds_raw WHERE run_id = 'test_run'").fetchone()[0]
    normalized_count = conn.execute(
        "SELECT COUNT(*) FROM finds_normalized WHERE run_id = 'test_run'"
    ).fetchone()[0]
    report_count = conn.execute(
        "SELECT COUNT(*) FROM validation_report WHERE run_id = 'test_run'"
    ).fetchone()[0]
    conn.close()

    assert raw_count == 4
    assert normalized_count == 4
    assert report_count == 4
