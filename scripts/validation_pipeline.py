import argparse
import csv
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analyzer import normalize_location, split_extreme_float_numbers  # noqa: E402

DEFAULT_DB_PATH = REPO_ROOT / "floats.db"
DEFAULT_REPORT_JSON = REPO_ROOT / "generated" / "validation_report.json"
DEFAULT_REPORT_CSV = REPO_ROOT / "generated" / "validation_report.csv"

DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%Y/%m/%d",
)
FLOAT_NUMBER_RE = re.compile(r"^\d{1,5}[A-Za-z]?$")
ORDINAL_SUFFIX_RE = re.compile(r"(\d{1,2})(st|nd|rd|th)", re.IGNORECASE)


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def make_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def ensure_finds_validation_columns(conn: sqlite3.Connection) -> None:
    columns = table_columns(conn, "finds")
    if "is_valid" not in columns:
        conn.execute("ALTER TABLE finds ADD COLUMN is_valid INTEGER DEFAULT 1")
    if "validation_errors" not in columns:
        conn.execute("ALTER TABLE finds ADD COLUMN validation_errors TEXT DEFAULT '[]'")
    if "confidence_score" not in columns:
        conn.execute("ALTER TABLE finds ADD COLUMN confidence_score REAL DEFAULT 1.0")
    if "source" not in columns:
        conn.execute("ALTER TABLE finds ADD COLUMN source TEXT DEFAULT ''")
    if "suspicious_flags" not in columns:
        conn.execute("ALTER TABLE finds ADD COLUMN suspicious_flags TEXT DEFAULT '[]'")


def ensure_stage_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS finds_raw (
            run_id TEXT NOT NULL,
            row_id TEXT NOT NULL,
            year_raw TEXT,
            float_number_raw TEXT,
            finder_raw TEXT,
            location_raw TEXT,
            location_normalized_raw TEXT,
            date_found_raw TEXT,
            url_raw TEXT,
            image_url_raw TEXT,
            source TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (run_id, row_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS finds_normalized (
            run_id TEXT NOT NULL,
            row_id TEXT NOT NULL,
            year INTEGER,
            float_number TEXT,
            finder TEXT,
            location_raw TEXT,
            location_normalized TEXT,
            date_found TEXT,
            url TEXT,
            image_url TEXT,
            source TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (run_id, row_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS validation_report (
            run_id TEXT NOT NULL,
            row_id TEXT NOT NULL,
            is_valid INTEGER NOT NULL,
            validation_errors TEXT NOT NULL,
            suspicious_flags TEXT NOT NULL,
            confidence_score REAL NOT NULL,
            source TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (run_id, row_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_validation_report_run_valid "
        "ON validation_report (run_id, is_valid)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_finds_normalized_run ON finds_normalized (run_id)"
    )


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def parse_year(year_raw: str) -> int | None:
    value = clean_text(year_raw)
    if not value:
        return None

    if value.isdigit():
        return int(value)

    match = re.search(r"\b(20\d{2})\b", value)
    if match:
        return int(match.group(1))
    return None


def normalize_date(date_raw: str) -> tuple[str, bool]:
    value = clean_text(date_raw)
    if not value:
        return "", False

    value = value.split("T", 1)[0].strip()
    value = ORDINAL_SUFFIX_RE.sub(r"\1", value)

    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.strftime("%Y-%m-%d"), False
        except ValueError:
            continue

    return value, True


def normalize_float_number(float_raw: str) -> str:
    value = clean_text(float_raw)
    if value.startswith("#"):
        value = value[1:].strip()
    return value


def is_valid_image_url(image_url: str) -> bool:
    value = clean_text(image_url)
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def infer_source(source_raw: str, url_raw: str, default_source: str) -> str:
    source = clean_text(source_raw)
    if source:
        return source

    parsed = urlparse(clean_text(url_raw))
    if parsed.netloc:
        host = parsed.netloc.lower()
        return host[4:] if host.startswith("www.") else host

    return default_source


def add_flag(flags: list[str], flag: str) -> None:
    if flag not in flags:
        flags.append(flag)


def compute_confidence(errors: list[str], suspicious_flags: list[str]) -> float:
    penalty = (0.25 * len(errors)) + (0.10 * len(suspicious_flags))
    score = max(0.0, 1.0 - penalty)
    return round(score, 2)


def fetch_finds_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    columns = table_columns(conn, "finds")

    def column_expr(column_name: str, alias: str | None = None) -> str:
        label = alias or column_name
        if column_name in columns:
            return f"CAST({column_name} AS TEXT) AS {label}"
        return f"'' AS {label}"

    query = f"""
        SELECT
            CAST(id AS TEXT) AS id,
            {column_expr('year')},
            {column_expr('float_number')},
            {column_expr('finder')},
            {column_expr('location_raw')},
            {column_expr('location_normalized')},
            {column_expr('date_found')},
            {column_expr('url')},
            {column_expr('image_url')},
            {column_expr('source')}
        FROM finds
        ORDER BY id
    """
    return conn.execute(query).fetchall()


def prepare_validation_rows(
    rows: list[sqlite3.Row],
    default_source: str,
) -> list[dict[str, Any]]:
    now_year = datetime.now().year
    prepared: list[dict[str, Any]] = []
    exact_counter: Counter[tuple[str, ...]] = Counter()
    repeated_float_counter: Counter[tuple[int, str, str]] = Counter()

    for row in rows:
        row_id = clean_text(row["id"])
        year_raw = clean_text(row["year"])
        float_raw = clean_text(row["float_number"])
        finder_raw = clean_text(row["finder"])
        location_raw = clean_text(row["location_raw"])
        location_normalized_raw = clean_text(row["location_normalized"])
        date_raw = clean_text(row["date_found"])
        url_raw = clean_text(row["url"])
        image_url_raw = clean_text(row["image_url"])
        source_raw = clean_text(row["source"])

        year_value = parse_year(year_raw)
        float_value = normalize_float_number(float_raw)
        finder_value = finder_raw
        location_normalized = normalize_location(location_raw) if location_raw else location_normalized_raw
        date_value, malformed_date = normalize_date(date_raw)
        source = infer_source(source_raw, url_raw, default_source)

        errors: list[str] = []
        suspicious: list[str] = []

        if year_value is None or year_value < 2010 or year_value > (now_year + 1):
            add_flag(errors, "invalid_year")

        if date_raw and malformed_date:
            add_flag(errors, "invalid_date")
            add_flag(suspicious, "malformed_date_string")

        if not float_value or not FLOAT_NUMBER_RE.fullmatch(float_value):
            add_flag(errors, "invalid_float_number")

        if not location_normalized or location_normalized == "Other/Unknown":
            add_flag(errors, "missing_normalized_location")

        if not is_valid_image_url(image_url_raw):
            add_flag(errors, "invalid_image_url")

        if not float_value and finder_value.startswith("#"):
            add_flag(suspicious, "blank_float_with_hash_finder")

        exact_key = (
            year_raw,
            float_raw,
            finder_raw,
            location_raw,
            date_raw,
            url_raw,
            image_url_raw,
        )
        exact_counter[exact_key] += 1

        repeated_float_key: tuple[int, str, str] | None = None
        float_number_value = None
        if float_value:
            match = re.search(r"(\d+)", float_value)
            if match:
                float_number_value = int(match.group(1))

        if year_value is not None and float_value and location_normalized:
            repeated_float_key = (year_value, float_value, location_normalized)
            repeated_float_counter[repeated_float_key] += 1

        prepared.append(
            {
                "row_id": row_id,
                "year_raw": year_raw,
                "float_raw": float_raw,
                "finder_raw": finder_raw,
                "location_raw": location_raw,
                "location_normalized_raw": location_normalized_raw,
                "date_raw": date_raw,
                "url_raw": url_raw,
                "image_url_raw": image_url_raw,
                "year": year_value,
                "float_number": float_value,
                "float_number_value": float_number_value,
                "finder": finder_value,
                "location_normalized": location_normalized,
                "date_found": date_value,
                "source": source,
                "errors": errors,
                "suspicious_flags": suspicious,
                "exact_key": exact_key,
                "repeated_float_key": repeated_float_key,
            }
        )

    outlier_numbers_by_year: dict[int, set[int]] = {}
    for year in {item["year"] for item in prepared if item["year"] is not None}:
        year_numbers = [
            item["float_number_value"]
            for item in prepared
            if item["year"] == year and item["float_number_value"] is not None
        ]
        _, outlier_numbers = split_extreme_float_numbers(year_numbers)
        if outlier_numbers:
            outlier_numbers_by_year[year] = set(outlier_numbers)

    for item in prepared:
        if (
            item["year"] is not None
            and item["float_number_value"] is not None
            and item["float_number_value"] in outlier_numbers_by_year.get(item["year"], set())
        ):
            add_flag(item["errors"], "extreme_float_number_outlier")

        if exact_counter[item["exact_key"]] > 1:
            add_flag(item["suspicious_flags"], "duplicate_exact_row")
        repeat_key = item["repeated_float_key"]
        if repeat_key and repeated_float_counter[repeat_key] > 1:
            add_flag(item["suspicious_flags"], "duplicate_float_year_location")

        item["is_valid"] = 0 if item["errors"] else 1
        item["confidence_score"] = compute_confidence(item["errors"], item["suspicious_flags"])

    return prepared


def stage_validation_rows(
    conn: sqlite3.Connection,
    prepared: list[dict[str, Any]],
    run_id: str,
    created_at: str,
) -> None:
    raw_rows = []
    normalized_rows = []
    report_rows = []
    update_rows = []

    for item in prepared:
        row_id = item["row_id"]
        source = item["source"]
        errors_json = json.dumps(item["errors"], ensure_ascii=True)
        suspicious_json = json.dumps(item["suspicious_flags"], ensure_ascii=True)

        raw_rows.append(
            (
                run_id,
                row_id,
                item["year_raw"],
                item["float_raw"],
                item["finder_raw"],
                item["location_raw"],
                item["location_normalized_raw"],
                item["date_raw"],
                item["url_raw"],
                item["image_url_raw"],
                source,
                created_at,
            )
        )
        normalized_rows.append(
            (
                run_id,
                row_id,
                item["year"],
                item["float_number"],
                item["finder"],
                item["location_raw"],
                item["location_normalized"],
                item["date_found"],
                item["url_raw"],
                item["image_url_raw"],
                source,
                created_at,
            )
        )
        report_rows.append(
            (
                run_id,
                row_id,
                item["is_valid"],
                errors_json,
                suspicious_json,
                item["confidence_score"],
                source,
                created_at,
            )
        )
        update_rows.append(
            (
                item["is_valid"],
                errors_json,
                item["confidence_score"],
                source,
                suspicious_json,
                row_id,
            )
        )

    conn.execute("DELETE FROM finds_raw WHERE run_id = ?", (run_id,))
    conn.execute("DELETE FROM finds_normalized WHERE run_id = ?", (run_id,))
    conn.execute("DELETE FROM validation_report WHERE run_id = ?", (run_id,))

    conn.executemany(
        """
        INSERT INTO finds_raw (
            run_id,
            row_id,
            year_raw,
            float_number_raw,
            finder_raw,
            location_raw,
            location_normalized_raw,
            date_found_raw,
            url_raw,
            image_url_raw,
            source,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        raw_rows,
    )
    conn.executemany(
        """
        INSERT INTO finds_normalized (
            run_id,
            row_id,
            year,
            float_number,
            finder,
            location_raw,
            location_normalized,
            date_found,
            url,
            image_url,
            source,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        normalized_rows,
    )
    conn.executemany(
        """
        INSERT INTO validation_report (
            run_id,
            row_id,
            is_valid,
            validation_errors,
            suspicious_flags,
            confidence_score,
            source,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        report_rows,
    )
    conn.executemany(
        """
        UPDATE finds
        SET
            is_valid = ?,
            validation_errors = ?,
            confidence_score = ?,
            source = ?,
            suspicious_flags = ?
        WHERE CAST(id AS TEXT) = ?
        """,
        update_rows,
    )


def build_summary(prepared: list[dict[str, Any]], run_id: str, generated_at: str) -> dict[str, Any]:
    error_counts: Counter[str] = Counter()
    suspicious_counts: Counter[str] = Counter()
    invalid_rows = 0
    suspicious_rows = 0
    flagged_rows = 0

    for item in prepared:
        if item["is_valid"] == 0:
            invalid_rows += 1
        if item["suspicious_flags"]:
            suspicious_rows += 1
        if item["is_valid"] == 0 or item["suspicious_flags"]:
            flagged_rows += 1

        for error in item["errors"]:
            error_counts[error] += 1
        for flag in item["suspicious_flags"]:
            suspicious_counts[flag] += 1

    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "total_rows": len(prepared),
        "valid_rows": len(prepared) - invalid_rows,
        "invalid_rows": invalid_rows,
        "suspicious_rows": suspicious_rows,
        "flagged_rows": flagged_rows,
        "error_counts": dict(sorted(error_counts.items())),
        "suspicious_counts": dict(sorted(suspicious_counts.items())),
    }


def write_report_files(
    prepared: list[dict[str, Any]],
    summary: dict[str, Any],
    report_json_path: Path,
    report_csv_path: Path,
) -> None:
    flagged_records: list[dict[str, Any]] = []
    for item in prepared:
        if item["is_valid"] == 1 and not item["suspicious_flags"]:
            continue
        flagged_records.append(
            {
                "id": item["row_id"],
                "year": item["year"],
                "float_number": item["float_number"],
                "finder": item["finder"],
                "location_raw": item["location_raw"],
                "location_normalized": item["location_normalized"],
                "date_found": item["date_found"],
                "url": item["url_raw"],
                "image_url": item["image_url_raw"],
                "is_valid": bool(item["is_valid"]),
                "validation_errors": item["errors"],
                "suspicious_flags": item["suspicious_flags"],
                "confidence_score": item["confidence_score"],
                "source": item["source"],
            }
        )

    report_json_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"summary": summary, "flagged_records": flagged_records}
    with report_json_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    report_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with report_csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "id",
                "year",
                "float_number",
                "finder",
                "location_raw",
                "location_normalized",
                "date_found",
                "is_valid",
                "validation_errors",
                "suspicious_flags",
                "confidence_score",
                "source",
                "url",
                "image_url",
            ],
        )
        writer.writeheader()
        for row in flagged_records:
            writer.writerow(
                {
                    **row,
                    "validation_errors": ",".join(row["validation_errors"]),
                    "suspicious_flags": ",".join(row["suspicious_flags"]),
                }
            )


def run_validation_pipeline(
    db_path: Path = DEFAULT_DB_PATH,
    report_json_path: Path = DEFAULT_REPORT_JSON,
    report_csv_path: Path = DEFAULT_REPORT_CSV,
    default_source: str = "legacy_db",
    run_id: str | None = None,
) -> dict[str, Any]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    resolved_run_id = run_id or make_run_id()
    generated_at = iso_now()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        ensure_finds_validation_columns(conn)
        ensure_stage_tables(conn)
        rows = fetch_finds_rows(conn)
        prepared = prepare_validation_rows(rows, default_source=default_source)
        stage_validation_rows(
            conn=conn,
            prepared=prepared,
            run_id=resolved_run_id,
            created_at=generated_at,
        )
        summary = build_summary(prepared, run_id=resolved_run_id, generated_at=generated_at)
        write_report_files(
            prepared=prepared,
            summary=summary,
            report_json_path=report_json_path,
            report_csv_path=report_csv_path,
        )
        conn.commit()
        return summary
    finally:
        conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run staged data validation and generate invalid/suspicious row reports."
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help="Path to the SQLite database (default: floats.db).",
    )
    parser.add_argument(
        "--report-json",
        default=str(DEFAULT_REPORT_JSON),
        help="Path to write the JSON report.",
    )
    parser.add_argument(
        "--report-csv",
        default=str(DEFAULT_REPORT_CSV),
        help="Path to write the CSV report.",
    )
    parser.add_argument(
        "--source",
        default="legacy_db",
        help="Fallback source tag when rows do not include source/url metadata.",
    )
    parser.add_argument(
        "--run-id",
        default="",
        help="Optional run identifier (default: UTC timestamp).",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    summary = run_validation_pipeline(
        db_path=Path(args.db),
        report_json_path=Path(args.report_json),
        report_csv_path=Path(args.report_csv),
        default_source=args.source,
        run_id=args.run_id or None,
    )

    print(
        f"Validated {summary['total_rows']} rows: "
        f"{summary['valid_rows']} valid, "
        f"{summary['invalid_rows']} invalid, "
        f"{summary['suspicious_rows']} suspicious."
    )
    print(f"Flagged rows: {summary['flagged_rows']}")
    print(f"JSON report: {args.report_json}")
    print(f"CSV report: {args.report_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
