import argparse
import concurrent.futures
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analyzer import normalize_location, split_extreme_float_numbers  # noqa: E402
from scripts.validation_pipeline import (  # noqa: E402
    DEFAULT_REPORT_CSV as VALIDATION_REPORT_CSV,
    DEFAULT_REPORT_JSON as VALIDATION_REPORT_JSON,
    run_validation_pipeline,
)

BASE_URL = "https://www.blockislandinfo.com/glass-float-project/found-floats/"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
PAGE_SIZE = 24
CANONICAL_KEYS = ("id", "year", "title", "url", "image", "location", "date_found")
CANONICAL_JSON_PATH = REPO_ROOT / "all_floats_final.json"
DB_PATH = REPO_ROOT / "floats.db"
SCRAPED_DATA_DIR = REPO_ROOT / "scraped_data"
GENERATED_DIR = REPO_ROOT / "generated"
MANIFEST_PATH = GENERATED_DIR / "refresh_manifest.json"
SUMMARY_PATH = GENERATED_DIR / "refresh_summary.md"
AUDIT_PATH = GENERATED_DIR / "legacy_row_audit.json"
REPORT_DATE_FORMAT = "%B %d, %Y at %I:%M %p %Z"


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    return session


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def numeric_sort_key(value: Any) -> tuple[int, str]:
    text = "" if value is None else str(value)
    if text.isdigit():
        return (0, f"{int(text):012d}")
    return (1, text)


def sort_records(records: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        records,
        key=lambda item: (
            int(item["year"]) if str(item["year"]).isdigit() else -1,
            int(item["id"]) if str(item["id"]).isdigit() else -1,
        ),
        reverse=True,
    )


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def canonicalize_date(date_value: str | None) -> str:
    if not date_value:
        return ""

    value = date_value.strip()
    if not value:
        return ""

    if "T" in value:
        value = value.split("T", 1)[0]

    iso_match = re.match(r"^\d{4}-\d{2}-\d{2}$", value)
    if iso_match:
        return "" if value.endswith("-01-01") else value

    for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%m/%d/%y"):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return ""


def parse_title(title: str) -> tuple[str, str]:
    normalized = " ".join((title or "").strip().split())
    if not normalized:
        return "", ""

    match = re.match(r"^#?(?P<number>\d+)(?:\s*-\s*|\s+)(?P<finder>.+)$", normalized)
    if match:
        return match.group("number"), match.group("finder").strip()

    return "", normalized


def absolute_url(url: str) -> str:
    if not url:
        return ""
    return urljoin(BASE_URL, url)


def normalize_record(record: dict[str, Any]) -> dict[str, str]:
    normalized = {key: "" for key in CANONICAL_KEYS}
    normalized["id"] = str(record.get("id", "")).strip()
    normalized["year"] = str(record.get("year", "")).strip()
    normalized["title"] = " ".join(str(record.get("title", "")).split())
    normalized["url"] = absolute_url(str(record.get("url", "")).strip())
    normalized["image"] = absolute_url(str(record.get("image", "")).strip())
    normalized["location"] = " ".join(str(record.get("location", "")).split())
    normalized["date_found"] = canonicalize_date(record.get("date_found"))
    return normalized


def extract_attr_value(tag: Any) -> str:
    if not tag:
        return ""

    for attr in ("data-cat-id", "data-category-id", "data-value", "value"):
        value = tag.get(attr)
        if value and str(value).strip().isdigit():
            return str(value).strip()

    href = tag.get("href", "")
    if href:
        parsed = parse_qs(urlparse(href).query)
        for key in ("categories", "category"):
            values = parsed.get(key, [])
            if values and values[0].isdigit():
                return values[0]

    return ""


def discover_year_filters_from_html(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    year_filters: dict[str, str] = {}

    for label in soup.find_all("label"):
        text = label.get_text(" ", strip=True)
        year_match = re.search(r"\b(20\d{2})\b", text)
        if not year_match:
            continue

        candidates = [label]
        target_id = label.get("for")
        if target_id:
            candidates.append(soup.find(id=target_id))
        parent = label.find_parent()
        if parent:
            candidates.append(parent)
            if target_id:
                candidates.append(parent.find(id=target_id))
            candidates.extend(parent.find_all(["input", "a"], recursive=True))

        category_id = next((extract_attr_value(candidate) for candidate in candidates if extract_attr_value(candidate)), "")
        if category_id:
            year_filters[year_match.group(1)] = category_id

    return dict(sorted(year_filters.items(), key=lambda item: item[0], reverse=True))


def discover_year_filters(session: requests.Session, page_html: str | None = None) -> dict[str, str]:
    html = page_html
    if html is None:
        response = session.get(BASE_URL, timeout=30)
        response.raise_for_status()
        html = response.text

    filters = discover_year_filters_from_html(html)
    if filters:
        return filters

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - exercised only when dependency is absent.
        raise RuntimeError("Could not discover year filters from HTML and Playwright is unavailable.") from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
        html = page.content()
        browser.close()

    filters = discover_year_filters_from_html(html)
    if not filters:
        raise RuntimeError("Could not discover year filters from the source site.")
    return filters


def extract_years_from_label_texts(texts: list[str]) -> list[str]:
    years = sorted(
        {
            match.group(1)
            for text in texts
            for match in [re.search(r"\b(20\d{2})\b", text)]
            if match
        },
        reverse=True,
    )
    if not years:
        raise RuntimeError("Could not discover any year labels from the rendered source page.")
    return years


def collect_rendered_page_records(page: Any, year: str, seen_ids: set[str]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    item_locator = page.locator('.item[data-type="events"]')

    for idx in range(item_locator.count()):
        item = item_locator.nth(idx)
        record_id = (item.get_attribute("data-recid") or "").strip()
        if not record_id or record_id in seen_ids:
            continue

        title_node = item.locator(".title").first
        link_node = item.locator("a[href]").first
        image_node = item.locator("img").first
        location_node = item.locator(".locations").first

        image = ""
        if image_node.count():
            image = image_node.get_attribute("data-lazy-src") or image_node.get_attribute("src") or ""

        records.append(
            normalize_record(
                {
                    "id": record_id,
                    "year": year,
                    "title": title_node.inner_text().strip() if title_node.count() else "",
                    "url": link_node.get_attribute("href") if link_node.count() else "",
                    "image": image,
                    "location": location_node.inner_text().strip() if location_node.count() else "",
                    "date_found": "",
                }
            )
        )

    return records


def group_records_by_year(records: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for record in records:
        grouped.setdefault(record["year"], []).append(record)
    return grouped


def exclude_extreme_float_number_records(
    records: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    outlier_ids: set[str] = set()

    for year_records in group_records_by_year(records).values():
        record_numbers: list[tuple[str, int]] = []
        for record in year_records:
            float_number, _ = parse_title(record.get("title", ""))
            if float_number.isdigit():
                record_numbers.append((record["id"], int(float_number)))

        _, outlier_numbers = split_extreme_float_numbers(number for _, number in record_numbers)
        if not outlier_numbers:
            continue

        year_outliers = set(outlier_numbers)
        for record_id, number in record_numbers:
            if number in year_outliers:
                outlier_ids.add(record_id)

    kept_records = [record for record in records if record["id"] not in outlier_ids]
    dropped_records = [record for record in records if record["id"] in outlier_ids]
    return sort_records(kept_records), sort_records(dropped_records)


def scrape_records_with_playwright(
    cached_by_year: dict[str, list[dict[str, str]]] | None = None,
) -> list[dict[str, str]]:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

    all_records: list[dict[str, str]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
        years = extract_years_from_label_texts(page.locator("label").all_text_contents())

        for year in years:
            print(f"Scraping rendered archive for {year}...", flush=True)
            seen_ids: set[str] = set()
            page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
            label = page.locator(f"xpath=//label[starts-with(normalize-space(.), '{year}')]").first
            if label.count() == 0:
                print(f"Skipping {year}: label not found.", flush=True)
                continue

            label.scroll_into_view_if_needed()
            label.click()
            page.wait_for_timeout(2000)

            while True:
                try:
                    page.wait_for_selector('.item[data-type="events"]', timeout=15000)
                except PlaywrightTimeoutError:
                    cached_records = sort_records(cached_by_year.get(year, [])) if cached_by_year else []
                    if cached_records:
                        print(
                            f"No rendered results for {year}; using {len(cached_records)} cached records.",
                            flush=True,
                        )
                        all_records.extend(cached_records)
                    else:
                        print(f"No rendered results for {year}; skipping year.", flush=True)
                    break
                page.wait_for_timeout(1000)
                page_records = collect_rendered_page_records(page, year, seen_ids)
                if not page_records:
                    break

                all_records.extend(page_records)
                seen_ids.update(record["id"] for record in page_records)

                next_btn = page.locator(".pager .nxt").first
                if next_btn.count() == 0:
                    break

                next_btn.scroll_into_view_if_needed()
                next_btn.click()
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(1000)

            print(f"Collected {len(seen_ids)} rendered records for {year}.", flush=True)

        browser.close()

    return sort_records(all_records)


def parse_listing_page(html: str, year: str) -> tuple[list[dict[str, str]], int | None]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict[str, str]] = []

    for item in soup.select('.item[data-type="events"]'):
        record_id = (item.get("data-recid") or "").strip()
        if not record_id:
            continue

        title_node = item.select_one(".title")
        link_node = item.select_one("a[href]")
        image_node = item.select_one("img")
        location_node = item.select_one(".locations")

        image = ""
        if image_node:
            image = image_node.get("data-lazy-src") or image_node.get("src") or ""

        items.append(
            normalize_record(
                {
                    "id": record_id,
                    "year": year,
                    "title": title_node.get_text(" ", strip=True) if title_node else "",
                    "url": link_node.get("href", "") if link_node else "",
                    "image": image,
                    "location": location_node.get_text(" ", strip=True) if location_node else "",
                    "date_found": "",
                }
            )
        )

    next_skip = None
    next_link = soup.select_one(".pager .nxt[href]")
    if next_link:
        query = parse_qs(urlparse(next_link["href"]).query)
        skip_values = query.get("skip", [])
        if skip_values and skip_values[0].isdigit():
            next_skip = int(skip_values[0])

    return items, next_skip


def scrape_year_records(session: requests.Session, year: str, category_id: str) -> list[dict[str, str]]:
    year_records: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    next_skip = 0

    while next_skip is not None:
        params = {
            "categories": category_id,
            "skip": next_skip,
            "bounds": "false",
            "view": "grid",
            "sort": "date",
        }
        response = session.get(BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        page_records, derived_next_skip = parse_listing_page(response.text, year)
        new_records = [record for record in page_records if record["id"] not in seen_ids]
        if not new_records:
            break

        year_records.extend(new_records)
        seen_ids.update(record["id"] for record in new_records)

        if derived_next_skip is None:
            break
        if derived_next_skip <= next_skip:
            break
        next_skip = derived_next_skip

    return sort_records(year_records)


def extract_date_from_detail_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    saw_json_ld = False

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        saw_json_ld = True
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue

        candidates = payload if isinstance(payload, list) else [payload]
        for candidate in candidates:
            if isinstance(candidate, dict):
                date_value = canonicalize_date(candidate.get("startDate"))
                if date_value:
                    return date_value

    if saw_json_ld:
        return ""

    text = soup.get_text(" ", strip=True)
    month_match = re.search(
        r"Date Found:\s*([A-Z][a-z]+ \d{1,2}, \d{4})",
        text,
    )
    if month_match:
        return canonicalize_date(month_match.group(1))

    return ""


def fetch_detail_date(session: requests.Session, url: str) -> str:
    if not url:
        return ""
    response = session.get(url, timeout=30)
    response.raise_for_status()
    return extract_date_from_detail_html(response.text)


def load_existing_canonical_records() -> dict[str, dict[str, str]]:
    existing_records = load_json(CANONICAL_JSON_PATH, [])
    if not existing_records:
        snapshot_records: list[dict[str, str]] = []
        for snapshot_path in sorted(SCRAPED_DATA_DIR.glob("floats_*.json")):
            snapshot_records.extend(load_json(snapshot_path, []))
        existing_records = snapshot_records
    return {str(record["id"]): normalize_record(record) for record in existing_records}


def enrich_records_with_details(
    records: list[dict[str, str]],
    existing_by_id: dict[str, dict[str, str]],
    session: requests.Session,
    max_workers: int = 32,
) -> list[dict[str, str]]:
    enriched = [dict(record) for record in records]
    pending_indices: list[int] = []

    for idx, record in enumerate(enriched):
        cached = existing_by_id.get(record["id"])
        if cached:
            for field in ("url", "image", "location", "title"):
                if not record[field] and cached.get(field):
                    record[field] = cached[field]
            if cached.get("date_found"):
                record["date_found"] = cached["date_found"]

        if not record["date_found"] and record["url"]:
            pending_indices.append(idx)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_detail_date, session, enriched[idx]["url"]): idx for idx in pending_indices
        }
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            idx = futures[future]
            try:
                enriched[idx]["date_found"] = future.result()
            except Exception:
                enriched[idx]["date_found"] = ""
            completed += 1
            if completed % 250 == 0 or completed == len(pending_indices):
                print(f"Fetched detail pages: {completed}/{len(pending_indices)}")

    return sort_records([normalize_record(record) for record in enriched])


def write_per_year_snapshots(records: list[dict[str, str]]) -> None:
    by_year: dict[str, list[dict[str, str]]] = {}
    for record in records:
        by_year.setdefault(record["year"], []).append(record)

    SCRAPED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for year, year_records in by_year.items():
        write_json(SCRAPED_DATA_DIR / f"floats_{year}.json", sort_records(year_records))


def rebuild_database(records: list[dict[str, str]], db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS finds")
    cursor.execute(
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
            image_url TEXT,
            is_valid INTEGER DEFAULT 1,
            validation_errors TEXT DEFAULT '[]',
            confidence_score REAL DEFAULT 1.0,
            source TEXT DEFAULT '',
            suspicious_flags TEXT DEFAULT '[]'
        )
        """
    )

    rows = []
    for record in sort_records(records):
        float_number, finder = parse_title(record["title"])
        rows.append(
            (
                int(record["id"]),
                int(record["year"]) if record["year"].isdigit() else None,
                float_number,
                finder,
                record["location"],
                normalize_location(record["location"]),
                record["date_found"],
                record["url"],
                record["image"],
                "blockislandinfo.com",
            )
        )

    cursor.executemany(
        """
        INSERT INTO finds (
            id,
            year,
            float_number,
            finder,
            location_raw,
            location_normalized,
            date_found,
            url,
            image_url,
            source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def get_legacy_rows(db_path: Path, canonical_ids: set[str]) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = [dict(row) for row in conn.execute("SELECT * FROM finds ORDER BY id")]
    conn.close()

    legacy_rows = [row for row in rows if str(row["id"]) not in canonical_ids]
    return legacy_rows


def build_manifest(
    records: list[dict[str, str]],
    validation_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    counts_by_year = Counter(record["year"] for record in records)
    valid_dates = [record["date_found"] for record in records if record["date_found"]]

    manifest = {
        "refreshed_at": iso_now(),
        "total_records": len(records),
        "latest_source_date": max(valid_dates) if valid_dates else "",
        "records_by_year": {year: counts_by_year[year] for year in sorted(counts_by_year, reverse=True)},
        "missing_dates": sum(1 for record in records if not record["date_found"]),
        "missing_urls": sum(1 for record in records if not record["url"]),
        "missing_images": sum(1 for record in records if not record["image"]),
    }
    if validation_summary:
        manifest["validation"] = {
            "run_id": validation_summary.get("run_id", ""),
            "valid_rows": validation_summary.get("valid_rows", 0),
            "invalid_rows": validation_summary.get("invalid_rows", 0),
            "suspicious_rows": validation_summary.get("suspicious_rows", 0),
            "flagged_rows": validation_summary.get("flagged_rows", 0),
        }
    return manifest


def write_summary(manifest: dict[str, Any], legacy_rows: list[dict[str, Any]]) -> None:
    refreshed_at = datetime.fromisoformat(manifest["refreshed_at"]).strftime(REPORT_DATE_FORMAT)
    lines = [
        "# Data Refresh Summary",
        "",
        f"- Refreshed at: {refreshed_at}",
        f"- Total records: {manifest['total_records']}",
        f"- Latest source date: {manifest['latest_source_date'] or 'Unknown'}",
        f"- Missing dates: {manifest['missing_dates']}",
        f"- Missing URLs: {manifest['missing_urls']}",
        f"- Missing images: {manifest['missing_images']}",
        f"- Legacy DB-only rows excluded: {len(legacy_rows)}",
        "",
        "## Records by Year",
        "",
    ]
    for year, count in manifest["records_by_year"].items():
        lines.append(f"- {year}: {count}")
    validation = manifest.get("validation")
    if validation:
        lines.extend(
            [
                "",
                "## Validation Summary",
                "",
                f"- Valid rows: {validation['valid_rows']}",
                f"- Invalid rows: {validation['invalid_rows']}",
                f"- Suspicious rows: {validation['suspicious_rows']}",
                f"- Flagged rows: {validation['flagged_rows']}",
                f"- Validation report JSON: {VALIDATION_REPORT_JSON}",
                f"- Validation report CSV: {VALIDATION_REPORT_CSV}",
            ]
        )
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_outputs(
    records: list[dict[str, str]],
    db_path: Path = DB_PATH,
    manifest_path: Path = MANIFEST_PATH,
) -> list[str]:
    errors: list[str] = []

    record_ids = [record.get("id", "") for record in records]
    if len(record_ids) != len(set(record_ids)):
        errors.append("Canonical JSON contains duplicate record ids.")

    for record in records:
        missing = [key for key in CANONICAL_KEYS if key not in record]
        if missing:
            errors.append(f"Record {record.get('id', '<missing>')} is missing keys: {', '.join(missing)}")

    if db_path.exists():
        conn = sqlite3.connect(db_path)
        db_ids = {str(row[0]) for row in conn.execute("SELECT id FROM finds")}
        conn.close()
        if db_ids != set(record_ids):
            errors.append(
                f"Canonical JSON / DB id drift detected: json={len(set(record_ids))}, db={len(db_ids)}."
            )
    else:
        errors.append(f"Database file is missing: {db_path}")

    manifest = load_json(manifest_path, {})
    if not manifest:
        errors.append(f"Refresh manifest is missing: {manifest_path}")
    else:
        if manifest.get("total_records") != len(records):
            errors.append("Refresh manifest total_records does not match canonical JSON.")
        valid_dates = [record["date_found"] for record in records if record["date_found"]]
        latest_date = max(valid_dates) if valid_dates else ""
        if manifest.get("latest_source_date", "") != latest_date:
            errors.append("Refresh manifest latest_source_date does not match canonical JSON.")

    for year in {record["year"] for record in records}:
        snapshot_path = SCRAPED_DATA_DIR / f"floats_{year}.json"
        snapshot_records = load_json(snapshot_path, [])
        snapshot_ids = {str(record["id"]) for record in snapshot_records}
        expected_ids = {record["id"] for record in records if record["year"] == year}
        if snapshot_ids != expected_ids:
            errors.append(f"Per-year snapshot drift detected for {year}.")

    return errors


def refresh_data() -> int:
    existing_by_id = load_existing_canonical_records()
    cached_by_year = group_records_by_year(list(existing_by_id.values()))
    session = make_session()
    all_records = scrape_records_with_playwright(cached_by_year=cached_by_year)

    if not all_records:
        print("ERROR: The source site returned zero records. Existing artifacts were left unchanged.")
        return 1

    canonical_records = enrich_records_with_details(
        records=all_records,
        existing_by_id=existing_by_id,
        session=session,
    )
    if not canonical_records:
        print("ERROR: Canonical record generation returned zero records. Existing artifacts were left unchanged.")
        return 1

    canonical_records, dropped_outliers = exclude_extreme_float_number_records(canonical_records)
    if dropped_outliers:
        dropped_labels = ", ".join(
            f"{record['year']} #{parse_title(record['title'])[0]} (id {record['id']})"
            for record in dropped_outliers
        )
        print(f"Excluded {len(dropped_outliers)} extreme float-number outlier record(s): {dropped_labels}")

    canonical_ids = {record["id"] for record in canonical_records}
    legacy_rows = get_legacy_rows(DB_PATH, canonical_ids)

    write_json(CANONICAL_JSON_PATH, canonical_records)
    write_per_year_snapshots(canonical_records)
    rebuild_database(canonical_records, DB_PATH)
    validation_summary = run_validation_pipeline(
        db_path=DB_PATH,
        report_json_path=VALIDATION_REPORT_JSON,
        report_csv_path=VALIDATION_REPORT_CSV,
        default_source="blockislandinfo.com",
    )

    manifest = build_manifest(canonical_records, validation_summary=validation_summary)
    write_json(MANIFEST_PATH, manifest)

    audit_payload = {
        "generated_at": iso_now(),
        "legacy_row_count": len(legacy_rows),
        "rows": legacy_rows,
    }
    write_json(AUDIT_PATH, audit_payload)
    write_summary(manifest, legacy_rows)

    errors = validate_outputs(canonical_records)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(
        f"Refreshed {len(canonical_records)} records across {len(manifest['records_by_year'])} years. "
        f"Latest source date: {manifest['latest_source_date'] or 'Unknown'}. "
        f"Invalid rows: {validation_summary['invalid_rows']}, "
        f"suspicious rows: {validation_summary['suspicious_rows']}."
    )
    return 0


def validate_data() -> int:
    records = load_json(CANONICAL_JSON_PATH, [])
    if not records:
        print(f"ERROR: Canonical JSON is missing or empty: {CANONICAL_JSON_PATH}")
        return 1

    errors = validate_outputs([normalize_record(record) for record in records])
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(
        f"Validated {len(records)} canonical records, {len(load_json(MANIFEST_PATH, {}).get('records_by_year', {}))} years, "
        f"and matching SQLite ids."
    )
    return 0


def validate_records() -> int:
    if not DB_PATH.exists():
        print(f"ERROR: Database file is missing: {DB_PATH}")
        return 1

    summary = run_validation_pipeline(
        db_path=DB_PATH,
        report_json_path=VALIDATION_REPORT_JSON,
        report_csv_path=VALIDATION_REPORT_CSV,
        default_source="legacy_db",
    )
    print(
        f"Validated {summary['total_rows']} DB rows. "
        f"Invalid: {summary['invalid_rows']}, suspicious: {summary['suspicious_rows']}. "
        f"Report: {VALIDATION_REPORT_JSON}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh and validate float tracker data artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("refresh", help="Scrape the source site and rebuild generated data artifacts.")
    subparsers.add_parser("validate", help="Validate canonical JSON, snapshots, manifest, and SQLite outputs.")
    subparsers.add_parser(
        "validate-records",
        help="Run staged row validation against the current SQLite database.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "refresh":
        return refresh_data()
    if args.command == "validate":
        return validate_data()
    if args.command == "validate-records":
        return validate_records()
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
