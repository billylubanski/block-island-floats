import argparse
import concurrent.futures
import html
import json
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analyzer import normalize_location, split_extreme_float_numbers  # noqa: E402
import ml_predictor  # noqa: E402
from record_overrides import apply_record_override, load_record_overrides  # noqa: E402
from scripts.validation_pipeline import (  # noqa: E402
    DEFAULT_REPORT_CSV as VALIDATION_REPORT_CSV,
    DEFAULT_REPORT_JSON as VALIDATION_REPORT_JSON,
    run_validation_pipeline,
)

BASE_URL = "https://www.blockislandinfo.com/glass-float-project/found-floats/"
SITE_ROOT = "https://www.blockislandinfo.com/"
ROBOTS_URL = urljoin(SITE_ROOT, "robots.txt")
SITEMAP_URL = urljoin(SITE_ROOT, "sitemap.xml")
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 "
        "BI-Float-Tracker/1.0"
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
FORECAST_PATH = GENERATED_DIR / "forecast_artifact.json"
FORECAST_EVALUATION_PATH = GENERATED_DIR / "forecast_evaluation.json"
FORECAST_EVALUATION_SUMMARY_PATH = GENERATED_DIR / "forecast_evaluation_summary.md"
SITEMAP_STATE_PATH = GENERATED_DIR / "sitemap_state.json"
REFRESH_STATUS_PATH = GENERATED_DIR / "refresh_status.json"
CLEANUP_REPORT_PATH = GENERATED_DIR / "data_cleanup_report.json"
CLEANUP_SUMMARY_PATH = GENERATED_DIR / "data_cleanup_summary.md"
MANUAL_REVIEW_PATH = GENERATED_DIR / "manual_review_queue.json"
MANUAL_REVIEW_SUMMARY_PATH = GENERATED_DIR / "manual_review_summary.md"
REPORT_DATE_FORMAT = "%B %d, %Y at %I:%M %p %Z"
DEFAULT_CRAWL_DELAY_SECONDS = 2.0
REQUEST_TIMEOUT_SECONDS = 30
MAX_REQUEST_RETRIES = 5
HISTORICAL_BACKFILL_BATCH_SIZE = 25
MIN_PLAUSIBLE_SEASON_YEAR = 2010
PLACEHOLDER_IMAGE_TOKEN = "default_image_2__"
EVENT_URL_RE = re.compile(r"/event/.+?/(?P<record_id>\d+)/?$")
SITEMAP_STATE_KEYS = (
    "url",
    "sitemap_lastmod",
    "first_seen_at",
    "last_seen_at",
    "last_fetched_at",
    "fetch_status",
)


class SourceAccessDeniedError(RuntimeError):
    """Raised when the upstream site returns a CDN/WAF access denied page."""


class RefreshProgress:
    """Write a machine-readable status file and human-readable progress lines."""

    def __init__(self, path: Path = REFRESH_STATUS_PATH, *, print_every_seconds: float = 10.0) -> None:
        self.path = path
        self.print_every_seconds = float(print_every_seconds)
        self.started_at = time.monotonic()
        self.run_started_at = iso_now()
        self.last_printed_at = 0.0
        self.payload: dict[str, Any] = {
            "status": "running",
            "phase": "starting",
            "phase_label": "Starting refresh",
            "started_at": self.run_started_at,
            "updated_at": self.run_started_at,
            "elapsed_seconds": 0,
            "completed": 0,
            "total": 0,
            "percent": 0,
            "eta_seconds": None,
            "eta_label": "unknown",
            "message": "",
        }
        self.update("starting", "Starting refresh", force=True)

    def _elapsed_seconds(self) -> float:
        return max(time.monotonic() - self.started_at, 0.0)

    @staticmethod
    def _format_duration(seconds: float | None) -> str:
        if seconds is None:
            return "unknown"
        seconds = max(int(round(seconds)), 0)
        minutes, remaining_seconds = divmod(seconds, 60)
        hours, remaining_minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}h {remaining_minutes}m"
        if minutes:
            return f"{minutes}m {remaining_seconds}s"
        return f"{remaining_seconds}s"

    def _build_payload(
        self,
        phase: str,
        phase_label: str,
        *,
        completed: int | None = None,
        total: int | None = None,
        message: str = "",
        status: str = "running",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        elapsed = self._elapsed_seconds()
        completed_value = max(int(completed or 0), 0)
        total_value = max(int(total or 0), 0)
        percent = round((completed_value / total_value) * 100, 1) if total_value else 0
        eta_seconds = None
        if completed_value > 0 and total_value > completed_value:
            eta_seconds = (elapsed / completed_value) * (total_value - completed_value)

        payload = {
            "status": status,
            "phase": phase,
            "phase_label": phase_label,
            "started_at": self.run_started_at,
            "updated_at": iso_now(),
            "elapsed_seconds": round(elapsed, 1),
            "elapsed_label": self._format_duration(elapsed),
            "completed": completed_value,
            "total": total_value,
            "remaining": max(total_value - completed_value, 0) if total_value else None,
            "percent": percent,
            "eta_seconds": round(eta_seconds, 1) if eta_seconds is not None else None,
            "eta_label": self._format_duration(eta_seconds),
            "message": message,
        }
        if extra:
            payload.update(extra)
        return payload

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _print(self) -> None:
        total = int(self.payload.get("total") or 0)
        completed = int(self.payload.get("completed") or 0)
        progress = (
            f"{completed}/{total} ({self.payload.get('percent', 0)}%)"
            if total
            else self.payload.get("status", "running")
        )
        message = str(self.payload.get("message") or "").strip()
        suffix = f" — {message}" if message else ""
        print(
            f"[refresh] {self.payload['phase_label']}: {progress}; "
            f"elapsed {self.payload.get('elapsed_label', 'unknown')}; "
            f"ETA {self.payload.get('eta_label', 'unknown')}{suffix}",
            flush=True,
        )

    def update(
        self,
        phase: str,
        phase_label: str,
        *,
        completed: int | None = None,
        total: int | None = None,
        message: str = "",
        force: bool = False,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.payload = self._build_payload(
            phase,
            phase_label,
            completed=completed,
            total=total,
            message=message,
            extra=extra,
        )
        self._write()
        now = time.monotonic()
        is_finished_step = bool(total and completed is not None and completed >= total)
        if force or is_finished_step or (now - self.last_printed_at) >= self.print_every_seconds:
            self._print()
            self.last_printed_at = now

    def complete(self, message: str = "") -> None:
        self.payload = self._build_payload(
            "complete",
            "Refresh complete",
            completed=1,
            total=1,
            message=message,
            status="complete",
        )
        self._write()
        self._print()

    def fail(self, message: str, *, interrupted: bool = False) -> None:
        self.payload = self._build_payload(
            "interrupted" if interrupted else "failed",
            "Refresh interrupted" if interrupted else "Refresh failed",
            message=message,
            status="interrupted" if interrupted else "failed",
        )
        self._write()
        self._print()


class PoliteSession:
    """Shared HTTP client with crawl-delay pacing and basic retry/backoff."""

    def __init__(
        self,
        session: requests.Session,
        *,
        min_delay_seconds: float = DEFAULT_CRAWL_DELAY_SECONDS,
        max_retries: int = MAX_REQUEST_RETRIES,
    ) -> None:
        self.session = session
        self.min_delay_seconds = float(min_delay_seconds)
        self.max_retries = int(max_retries)
        self._next_request_at = 0.0

    def set_min_delay_seconds(self, delay_seconds: float) -> None:
        self.min_delay_seconds = max(DEFAULT_CRAWL_DELAY_SECONDS, float(delay_seconds))

    def _wait_for_turn(self) -> None:
        now = time.monotonic()
        if self._next_request_at > now:
            time.sleep(self._next_request_at - now)

    def _mark_request_complete(self) -> None:
        self._next_request_at = time.monotonic() + self.min_delay_seconds

    def _retry_delay_seconds(self, attempt: int, response: requests.Response | None = None) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After", "").strip()
            if retry_after.isdigit():
                return max(float(retry_after), self.min_delay_seconds)
        return min(float(2**attempt), 60.0)

    def get(self, url: str, *, context: str, timeout: int = REQUEST_TIMEOUT_SECONDS) -> requests.Response:
        last_response: requests.Response | None = None
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            self._wait_for_turn()
            try:
                response = self.session.get(url, timeout=timeout)
            except requests.RequestException as exc:
                self._mark_request_complete()
                last_error = exc
                if attempt == self.max_retries - 1:
                    raise RuntimeError(f"Failed to fetch {context}: {exc}") from exc
                time.sleep(self._retry_delay_seconds(attempt))
                continue

            self._mark_request_complete()
            last_response = response

            if response.status_code == 403:
                raise SourceAccessDeniedError(f"Source access denied while fetching {context}.")
            if is_access_denied_html(response.text):
                raise SourceAccessDeniedError(f"Source access denied while fetching {context}.")

            if response.status_code == 429:
                if attempt == self.max_retries - 1:
                    return response
                time.sleep(self._retry_delay_seconds(attempt, response=response))
                continue

            if 500 <= response.status_code < 600:
                if attempt == self.max_retries - 1:
                    return response
                time.sleep(self._retry_delay_seconds(attempt, response=response))
                continue

            return response

        if last_response is not None:
            return last_response
        raise RuntimeError(f"Failed to fetch {context}: {last_error}")


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    return session


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def extract_record_id_from_url(url: str) -> str:
    match = EVENT_URL_RE.search(urlparse(url).path)
    return match.group("record_id") if match else ""


def normalize_sitemap_state_entry(entry: dict[str, Any] | None = None) -> dict[str, str]:
    normalized = {key: "" for key in SITEMAP_STATE_KEYS}
    if not isinstance(entry, dict):
        return normalized

    for key in SITEMAP_STATE_KEYS:
        value = entry.get(key, "")
        normalized[key] = "" if value is None else str(value).strip()
    return normalized


def load_sitemap_state(path: Path = SITEMAP_STATE_PATH) -> dict[str, dict[str, str]]:
    try:
        payload = load_json(path, {})
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Sitemap state is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        return {}
    return {str(record_id): normalize_sitemap_state_entry(entry) for record_id, entry in payload.items()}


def parse_robots_policy(robots_txt: str, *, user_agent: str = "*") -> dict[str, Any]:
    parser = RobotFileParser()
    parser.parse((robots_txt or "").splitlines())
    crawl_delay = parser.crawl_delay(user_agent)
    if crawl_delay is None:
        crawl_delay = parser.crawl_delay("*")
    effective_delay = max(DEFAULT_CRAWL_DELAY_SECONDS, float(crawl_delay or DEFAULT_CRAWL_DELAY_SECONDS))
    return {
        "parser": parser,
        "crawl_delay_seconds": effective_delay,
    }


def fetch_robots_policy(fetcher: PoliteSession) -> dict[str, Any]:
    response = fetcher.get(ROBOTS_URL, context=ROBOTS_URL)
    if response.status_code != 200:
        raise RuntimeError(f"Could not fetch robots.txt: {ROBOTS_URL} (status {response.status_code})")
    policy = parse_robots_policy(response.text)
    fetcher.set_min_delay_seconds(policy["crawl_delay_seconds"])
    return policy


def can_fetch_url(robots_policy: dict[str, Any], url: str) -> bool:
    parser = robots_policy.get("parser")
    if not isinstance(parser, RobotFileParser):
        return True
    return parser.can_fetch("*", url)


def parse_sitemap_xml(xml_text: str) -> dict[str, dict[str, str]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise RuntimeError("Could not parse sitemap XML.") from exc

    namespace = ""
    if root.tag.startswith("{") and "}" in root.tag:
        namespace = root.tag[1 : root.tag.find("}")]
    ns = {"sm": namespace} if namespace else {}
    url_nodes = root.findall("sm:url", ns) if ns else root.findall("url")

    entries: dict[str, dict[str, str]] = {}
    for url_node in url_nodes:
        loc_node = url_node.find("sm:loc", ns) if ns else url_node.find("loc")
        lastmod_node = url_node.find("sm:lastmod", ns) if ns else url_node.find("lastmod")
        loc_text = (loc_node.text or "").strip() if loc_node is not None else ""
        if "/event/" not in loc_text:
            continue
        record_id = extract_record_id_from_url(loc_text)
        if not record_id:
            continue
        entries[record_id] = {
            "url": loc_text,
            "sitemap_lastmod": (lastmod_node.text or "").strip() if lastmod_node is not None else "",
        }

    return dict(sorted(entries.items(), key=lambda item: numeric_sort_key(item[0]), reverse=True))


def discover_sitemap_entries(fetcher: PoliteSession, robots_policy: dict[str, Any]) -> tuple[dict[str, dict[str, str]], int]:
    if not can_fetch_url(robots_policy, SITEMAP_URL):
        raise RuntimeError(f"robots.txt disallows sitemap access: {SITEMAP_URL}")

    response = fetcher.get(SITEMAP_URL, context=SITEMAP_URL)
    if response.status_code != 200:
        raise RuntimeError(f"Could not fetch sitemap XML: {SITEMAP_URL} (status {response.status_code})")

    all_entries = parse_sitemap_xml(response.text)
    allowed_entries: dict[str, dict[str, str]] = {}
    disallowed_count = 0
    for record_id, entry in all_entries.items():
        if can_fetch_url(robots_policy, entry["url"]):
            allowed_entries[record_id] = entry
        else:
            disallowed_count += 1

    if not allowed_entries:
        raise RuntimeError("The sitemap did not yield any allowed event URLs.")
    return allowed_entries, disallowed_count


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


def is_access_denied_html(html: str) -> bool:
    normalized = " ".join((html or "").lower().split())
    if "access denied" not in normalized:
        return False
    denial_signals = (
        "you don't have permission to access",
        "reference #",
        "errors.edgesuite.net",
        "access denied",
    )
    return any(signal in normalized for signal in denial_signals)


def assert_access_allowed_html(html: str, *, context: str) -> None:
    if is_access_denied_html(html):
        raise SourceAccessDeniedError(f"Source access denied while fetching {context}.")


def validate_source_response(response: requests.Response, *, context: str) -> str:
    if response.status_code == 403:
        raise SourceAccessDeniedError(f"Source access denied while fetching {context}.")
    response.raise_for_status()
    assert_access_allowed_html(response.text, context=context)
    return response.text


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


def normalize_title_text(title: str) -> str:
    replacements = {
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2026": "...",
    }
    normalized = str(title or "")
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return " ".join(normalized.strip().split())


def parse_title(title: str) -> tuple[str, str]:
    normalized = normalize_title_text(title)
    if not normalized:
        return "", ""

    match = re.match(
        r"^(?:number\s+)?#?(?P<number>\d+)(?:\??\s*(?:[-,/:.!]\s*|\s+)(?P<finder>.+))?$",
        normalized,
        re.IGNORECASE,
    )
    if match:
        finder = (match.group("finder") or "").lstrip("?- ").strip()
        return match.group("number"), finder

    match = re.match(r"^(?P<finder>.+?)\s+#(?P<number>\d+)\??$", normalized)
    if match and "unclear" not in match.group("finder").lower():
        return match.group("number"), match.group("finder").strip()

    match = re.match(r"^(?P<finder>.+?)\s+(?P<number>\d{1,4})\??$", normalized)
    if match:
        finder = match.group("finder").strip()
        lowered_finder = finder.lower()
        if not lowered_finder.startswith(("number ", "no number")) and "unclear" not in lowered_finder:
            return match.group("number"), finder

    match = re.match(r"^number\s+(?P<number>\d+)(?:\s*[-,/:.!]\s*|\s+)(?P<finder>.+)$", normalized, re.IGNORECASE)
    if match:
        return match.group("number"), match.group("finder").strip()

    return "", normalized


def is_placeholder_image_url(image_url: str) -> bool:
    return PLACEHOLDER_IMAGE_TOKEN in str(image_url or "")


def compose_title(float_number: str, finder: str, fallback_title: str = "") -> str:
    float_number = str(float_number or "").strip()
    finder = " ".join(str(finder or "").split())
    fallback_title = " ".join(str(fallback_title or "").split())
    if not float_number:
        return fallback_title
    if not finder:
        return fallback_title if fallback_title and parse_title(fallback_title)[0] == float_number else float_number
    if fallback_title and parse_title(fallback_title) == (float_number, finder):
        return fallback_title
    return f"{float_number} {finder}".strip()


def absolute_url(url: str) -> str:
    if not url:
        return ""
    return urljoin(BASE_URL, url)


def normalize_record(record: dict[str, Any]) -> dict[str, str]:
    normalized = {key: "" for key in CANONICAL_KEYS}
    normalized["id"] = str(record.get("id", "")).strip()
    normalized["year"] = str(record.get("year", "")).strip()
    normalized["title"] = " ".join(html.unescape(str(record.get("title", ""))).split())
    normalized["url"] = absolute_url(str(record.get("url", "")).strip())
    normalized["image"] = absolute_url(str(record.get("image", "")).strip())
    normalized["location"] = " ".join(html.unescape(str(record.get("location", ""))).split())
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

    if year_filters:
        return dict(sorted(year_filters.items(), key=lambda item: item[0], reverse=True))

    script_pairs = re.findall(r'"label":"(20\d{2})","value":"(\d+)"', html)
    if script_pairs:
        for year, category_id in script_pairs:
            year_filters[year] = category_id

    return dict(sorted(year_filters.items(), key=lambda item: item[0], reverse=True))


def discover_year_filters(session: requests.Session, page_html: str | None = None) -> dict[str, str]:
    html = page_html
    if html is None:
        response = session.get(BASE_URL, timeout=30)
        html = validate_source_response(response, context=BASE_URL)
    else:
        assert_access_allowed_html(html, context=BASE_URL)

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
        assert_access_allowed_html(html, context=BASE_URL)
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
        assert_access_allowed_html(page.content(), context=BASE_URL)
        years = extract_years_from_label_texts(page.locator("label").all_text_contents())

        for year in years:
            print(f"Scraping rendered archive for {year}...", flush=True)
            seen_ids: set[str] = set()
            page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
            assert_access_allowed_html(page.content(), context=f"{BASE_URL} [{year}]")
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
                    assert_access_allowed_html(page.content(), context=f"{BASE_URL} [{year}]")
                    cached_records = sort_records(cached_by_year.get(year, [])) if cached_by_year else []
                    if cached_records:
                        raise RuntimeError(
                            f"Rendered archive for {year} returned no results; refusing cached fallback while source access is unstable."
                        )
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
                assert_access_allowed_html(page.content(), context=f"{BASE_URL} [{year}]")

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
        html = validate_source_response(response, context=f"{BASE_URL}?categories={category_id}&skip={next_skip}")
        page_records, derived_next_skip = parse_listing_page(html, year)
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


def scrape_records(
    session: requests.Session,
    cached_by_year: dict[str, list[dict[str, str]]] | None = None,
) -> list[dict[str, str]]:
    try:
        year_filters = discover_year_filters(session)
    except SourceAccessDeniedError:
        raise
    except Exception:
        return scrape_records_with_playwright(cached_by_year=cached_by_year)

    all_records: list[dict[str, str]] = []
    for year, category_id in year_filters.items():
        print(f"Scraping request archive for {year}...", flush=True)
        try:
            year_records = scrape_year_records(session, year, category_id)
        except SourceAccessDeniedError:
            raise
        except Exception:
            year_records = []

        if year_records:
            all_records.extend(year_records)
            print(f"Collected {len(year_records)} request records for {year}.", flush=True)
            continue

        cached_records = sort_records(cached_by_year.get(year, [])) if cached_by_year else []
        if cached_records:
            raise RuntimeError(
                f"Request archive for {year} returned no results; refusing cached fallback while source access is unstable."
            )
        print(f"No request results for {year}; skipping year.", flush=True)

    if all_records:
        return sort_records(all_records)
    return scrape_records_with_playwright(cached_by_year=cached_by_year)


def extract_json_ld_candidates(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[dict[str, Any]] = []

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue

        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if isinstance(item, dict):
                candidates.append(item)

    return candidates


def extract_date_from_detail_html(html: str) -> str:
    json_ld_candidates = extract_json_ld_candidates(html)
    for candidate in json_ld_candidates:
        date_value = canonicalize_date(candidate.get("startDate"))
        if date_value:
            return date_value

    if json_ld_candidates:
        return ""

    dates_match = re.search(r'var\s+dates\s*=\s*"([^"]+)"', html)
    if dates_match:
        date_value = canonicalize_date(dates_match.group(1))
        if date_value:
            return date_value

    soup = BeautifulSoup(html, "html.parser")
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
    html = validate_source_response(response, context=url)
    return extract_date_from_detail_html(html)


def extract_event_data_from_html(html: str) -> dict[str, Any] | None:
    patterns = (
        r"var\s+data\s*=\s*(\{.*?\});\s*var\s+dates",
        r"var\s+data\s*=\s*(\{.*?\});",
    )
    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL)
        if not match:
            continue
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def extract_detail_year(event_data: dict[str, Any] | None) -> str:
    if not isinstance(event_data, dict):
        return ""
    categories = event_data.get("categories", [])
    if not isinstance(categories, list):
        return ""
    for category in categories:
        if not isinstance(category, dict):
            continue
        match = re.search(r"\b(20\d{2})\b", str(category.get("catName", "")).strip())
        if match:
            return match.group(1)
    return ""


def resolve_detail_year(event_data: dict[str, Any] | None, *, date_found: str = "") -> tuple[str, str]:
    year = extract_detail_year(event_data)
    if not year:
        return "", "non_float_event"

    if not year.isdigit():
        return "", "non_float_event"

    year_value = int(year)
    max_reasonable_year = datetime.now(timezone.utc).year + 1
    if MIN_PLAUSIBLE_SEASON_YEAR <= year_value <= max_reasonable_year:
        return year, ""

    if date_found:
        normalized_year = date_found.split("-", 1)[0].strip()
        if normalized_year.isdigit():
            return normalized_year, "implausible_season_year"

    return "", "implausible_season_year"


def extract_location_from_json_ld(candidate: dict[str, Any]) -> str:
    location = candidate.get("location")
    if isinstance(location, dict):
        return str(location.get("name", "")).strip()
    return ""


def extract_image_from_json_ld(candidates: list[dict[str, Any]]) -> str:
    for candidate in candidates:
        image = candidate.get("image")
        if isinstance(image, str) and image.strip():
            return image.strip()
        if isinstance(image, list):
            for value in image:
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return ""


def extract_image_from_meta(soup: BeautifulSoup) -> str:
    for attrs in (
        {"property": "og:image"},
        {"name": "og:image"},
        {"property": "twitter:image"},
        {"name": "twitter:image"},
    ):
        tag = soup.find("meta", attrs=attrs)
        if tag:
            value = str(tag.get("content", "")).strip()
            if value:
                return value
    return ""


def extract_text_from_html_fragment(fragment: Any) -> str:
    if not fragment:
        return ""
    text = BeautifulSoup(str(fragment), "html.parser").get_text(" ", strip=True)
    return " ".join(text.split())


def extract_location_from_description(description_html: Any) -> str:
    text = extract_text_from_html_fragment(description_html)
    if not text:
        return ""

    sentences = [segment.strip(" -") for segment in re.split(r"(?<=[.!?])\s+", text) if segment.strip()]
    location_tokens = (" near ", " on ", " in ", " under ", " behind ", " at ", " by ", " between ", " off ", " amongst ")

    for sentence in sentences:
        candidate = sentence
        candidate = re.sub(r"^while [^,]+,\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(
            r"^(?:i|we)\s+found(?:\s+(?:an\s+orb|the\s+orb|it))?\s+",
            "",
            candidate,
            flags=re.IGNORECASE,
        )
        candidate = re.sub(r"^found(?:\s+(?:an\s+orb|the\s+orb|it))?\s+", "", candidate, flags=re.IGNORECASE)
        lowered = f" {candidate.lower()} "
        if any(token in lowered for token in location_tokens):
            return candidate.strip().rstrip(".!?")

    if len(text) <= 120:
        return text.rstrip(".!?")
    return ""


def parse_detail_record_result_from_html(html: str, url: str) -> dict[str, Any]:
    record_id = extract_record_id_from_url(url)
    event_data = extract_event_data_from_html(html)
    json_ld_candidates = extract_json_ld_candidates(html)
    soup = BeautifulSoup(html, "html.parser")

    data_record_id = ""
    if isinstance(event_data, dict):
        data_record_id = str(event_data.get("recid", "")).strip()
    if data_record_id and record_id and data_record_id != record_id:
        return {
            "record": None,
            "rejection_reason": "parse_error",
            "warning": "",
        }
    record_id = data_record_id or record_id

    title = ""
    if isinstance(event_data, dict):
        title = str(event_data.get("title", "")).strip()
    if not title:
        title = next((str(candidate.get("name", "")).strip() for candidate in json_ld_candidates if candidate.get("name")), "")
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True).split("|", 1)[0].strip()

    location = ""
    if isinstance(event_data, dict):
        location = str(event_data.get("location", "")).strip()
    if not location:
        location = next((extract_location_from_json_ld(candidate) for candidate in json_ld_candidates if extract_location_from_json_ld(candidate)), "")
    if not location and isinstance(event_data, dict):
        location = extract_location_from_description(event_data.get("description"))

    image = ""
    if isinstance(event_data, dict):
        for key in ("image", "imageUrl", "image_url", "thumb", "img"):
            value = event_data.get(key)
            if isinstance(value, str) and value.strip():
                image = value.strip()
                break
    if not image:
        image = extract_image_from_json_ld(json_ld_candidates)
    if not image:
        image = extract_image_from_meta(soup)

    date_found = extract_date_from_detail_html(html)
    year, anomaly_key = resolve_detail_year(event_data, date_found=date_found)
    record = normalize_record(
        {
            "id": record_id,
            "year": year,
            "title": title,
            "url": url,
            "image": image,
            "location": location,
            "date_found": date_found,
        }
    )
    if not record["id"] or not record["year"] or not record["title"]:
        return {
            "record": None,
            "rejection_reason": anomaly_key or "parse_error",
            "warning": "",
        }
    return {
        "record": record,
        "rejection_reason": "",
        "warning": anomaly_key,
    }


def parse_detail_record_from_html(html: str, url: str) -> dict[str, str] | None:
    result = parse_detail_record_result_from_html(html, url)
    record = result.get("record")
    return record if isinstance(record, dict) else None


def record_is_complete(record: dict[str, str]) -> bool:
    return all(record.get(key, "").strip() for key in CANONICAL_KEYS)


def should_bootstrap_existing_state(
    previous_entry: dict[str, str] | None,
    existing_record: dict[str, str] | None,
    sitemap_entry: dict[str, str],
) -> bool:
    if not previous_entry or not existing_record:
        return False
    if previous_entry.get("sitemap_lastmod", "").strip():
        return False
    if previous_entry.get("fetch_status", "").strip() not in {"", "bootstrap"}:
        return False
    existing_url = existing_record.get("url", "").strip()
    return not existing_url or existing_url == sitemap_entry["url"]


def backfill_sort_key(
    record_id: str,
    previous_state: dict[str, dict[str, str]],
    order_positions: dict[str, int],
) -> tuple[int, str, int]:
    previous_entry = normalize_sitemap_state_entry(previous_state.get(record_id))
    last_fetched_at = previous_entry.get("last_fetched_at", "")
    return (0 if not last_fetched_at else 1, last_fetched_at, order_positions.get(record_id, 0))


def select_sitemap_fetch_ids(
    sitemap_entries: dict[str, dict[str, str]],
    existing_by_id: dict[str, dict[str, str]],
    previous_state: dict[str, dict[str, str]],
    *,
    backfill_batch_size: int = HISTORICAL_BACKFILL_BATCH_SIZE,
    full_refresh: bool = False,
) -> dict[str, list[str]]:
    ordered_ids = list(sitemap_entries)
    order_positions = {record_id: position for position, record_id in enumerate(ordered_ids)}
    new_ids: list[str] = []
    changed_ids: list[str] = []
    incomplete_ids: list[str] = []

    for record_id in ordered_ids:
        existing_record = existing_by_id.get(record_id)
        previous_entry = previous_state.get(record_id)
        sitemap_entry = sitemap_entries[record_id]

        if existing_record is None:
            new_ids.append(record_id)
            continue

        if previous_entry and not should_bootstrap_existing_state(previous_entry, existing_record, sitemap_entry) and (
            previous_entry.get("url", "") != sitemap_entry["url"]
            or previous_entry.get("sitemap_lastmod", "") != sitemap_entry["sitemap_lastmod"]
        ):
            changed_ids.append(record_id)
            continue

        if not record_is_complete(existing_record):
            incomplete_ids.append(record_id)

    incomplete_ids = sorted(
        incomplete_ids,
        key=lambda record_id: backfill_sort_key(record_id, previous_state, order_positions),
    )
    forced_refetch_ids: list[str] = []
    if full_refresh:
        backfill_ids = incomplete_ids
        forced_refetch_ids = [
            record_id
            for record_id in ordered_ids
            if record_id in existing_by_id
            and record_id not in changed_ids
            and record_id not in backfill_ids
        ]
        fetch_ids = ordered_ids
    else:
        backfill_ids = incomplete_ids[:backfill_batch_size]
        fetch_ids = new_ids + changed_ids + [record_id for record_id in backfill_ids if record_id not in changed_ids]
    return {
        "fetch_ids": fetch_ids,
        "new_ids": new_ids,
        "changed_ids": changed_ids,
        "backfill_ids": backfill_ids,
        "forced_refetch_ids": forced_refetch_ids,
    }


def fetch_detail_page_result(fetcher: PoliteSession, url: str) -> dict[str, Any]:
    try:
        response = fetcher.get(url, context=url)
    except SourceAccessDeniedError:
        raise
    except RuntimeError:
        return {"status_code": 0, "body": ""}
    return {"status_code": int(response.status_code), "body": response.text}


def apply_sitemap_updates(
    existing_by_id: dict[str, dict[str, str]],
    sitemap_entries: dict[str, dict[str, str]],
    previous_state: dict[str, dict[str, str]],
    fetch_detail_page: Any,
    *,
    refreshed_at: str | None = None,
    backfill_batch_size: int = HISTORICAL_BACKFILL_BATCH_SIZE,
    full_refresh: bool = False,
    disallowed_count: int = 0,
    progress: RefreshProgress | None = None,
) -> tuple[list[dict[str, str]], dict[str, dict[str, str]], dict[str, Any]]:
    refreshed_at = refreshed_at or iso_now()
    canonical_by_id = {record_id: normalize_record(record) for record_id, record in existing_by_id.items()}
    next_state = {record_id: normalize_sitemap_state_entry(entry) for record_id, entry in previous_state.items()}
    scheduling = select_sitemap_fetch_ids(
        sitemap_entries,
        existing_by_id,
        previous_state,
        backfill_batch_size=backfill_batch_size,
        full_refresh=full_refresh,
    )

    source_discovery = {
        "refresh_scope": "full" if full_refresh else "incremental",
        "sitemap_urls_seen": len(sitemap_entries),
        "detail_pages_fetched": 0,
        "reused_rows": 0,
        "new_ids": len(scheduling["new_ids"]),
        "changed_ids": len(scheduling["changed_ids"]),
        "backfilled_ids": len(scheduling["backfill_ids"]),
        "forced_refetch_ids": len(scheduling["forced_refetch_ids"]),
        "anomaly_counts": {
            "missing_from_sitemap": 0,
            "detail_404": 0,
            "parse_error": 0,
            "request_error": 0,
            "disallowed_by_robots": int(disallowed_count),
            "non_float_event": 0,
            "implausible_season_year": 0,
        },
    }
    fetch_ids = scheduling["fetch_ids"]
    if progress:
        progress.update(
            "detail_fetch",
            "Fetching detail pages",
            completed=0,
            total=len(fetch_ids),
            message=(
                f"{len(scheduling['new_ids'])} new, "
                f"{len(scheduling['changed_ids'])} changed, "
                f"{len(scheduling['backfill_ids'])} backfill, "
                f"{len(scheduling['forced_refetch_ids'])} forced"
            ),
            force=True,
            extra={
                "sitemap_urls_seen": len(sitemap_entries),
                "new_ids": len(scheduling["new_ids"]),
                "changed_ids": len(scheduling["changed_ids"]),
                "backfilled_ids": len(scheduling["backfill_ids"]),
                "forced_refetch_ids": len(scheduling["forced_refetch_ids"]),
            },
        )

    for record_id, sitemap_entry in sitemap_entries.items():
        previous_entry = next_state.get(record_id, normalize_sitemap_state_entry(previous_state.get(record_id)))
        fetch_status = previous_entry.get("fetch_status", "")
        if not fetch_status:
            fetch_status = "bootstrap" if record_id in existing_by_id else "discovered"
        next_state[record_id] = {
            "url": sitemap_entry["url"],
            "sitemap_lastmod": sitemap_entry["sitemap_lastmod"],
            "first_seen_at": previous_entry.get("first_seen_at", "") or refreshed_at,
            "last_seen_at": refreshed_at,
            "last_fetched_at": previous_entry.get("last_fetched_at", ""),
            "fetch_status": fetch_status,
        }

    missing_from_sitemap_ids = [
        record_id for record_id in existing_by_id if record_id not in sitemap_entries
    ]
    source_discovery["anomaly_counts"]["missing_from_sitemap"] = len(missing_from_sitemap_ids)
    for record_id in missing_from_sitemap_ids:
        previous_entry = next_state.get(record_id, normalize_sitemap_state_entry(previous_state.get(record_id)))
        next_state[record_id] = {
            "url": previous_entry.get("url", "") or existing_by_id[record_id].get("url", ""),
            "sitemap_lastmod": previous_entry.get("sitemap_lastmod", ""),
            "first_seen_at": previous_entry.get("first_seen_at", ""),
            "last_seen_at": previous_entry.get("last_seen_at", ""),
            "last_fetched_at": previous_entry.get("last_fetched_at", ""),
            "fetch_status": "missing_from_sitemap",
        }

    fetched_ids = set(fetch_ids)
    total_fetches = len(fetch_ids)
    for index, record_id in enumerate(fetch_ids, start=1):
        sitemap_entry = sitemap_entries[record_id]
        if progress:
            progress.update(
                "detail_fetch",
                "Fetching detail pages",
                completed=index - 1,
                total=total_fetches,
                message=f"next id {record_id}",
                extra={"current_record_id": record_id, "current_url": sitemap_entry["url"]},
            )
        result = fetch_detail_page(sitemap_entry["url"])
        source_discovery["detail_pages_fetched"] += 1
        next_state[record_id]["last_fetched_at"] = refreshed_at

        status_code = int(result.get("status_code", 0))
        body = str(result.get("body", "") or "")
        if status_code == 404:
            next_state[record_id]["fetch_status"] = "http_404"
            source_discovery["anomaly_counts"]["detail_404"] += 1
            if progress:
                progress.update(
                    "detail_fetch",
                    "Fetching detail pages",
                    completed=index,
                    total=total_fetches,
                    message=f"id {record_id} returned 404",
                    extra={"current_record_id": record_id, "last_status": "http_404"},
                )
            continue
        if status_code != 200:
            next_state[record_id]["fetch_status"] = f"http_{status_code}" if status_code else "request_error"
            source_discovery["anomaly_counts"]["request_error"] += 1
            if progress:
                progress.update(
                    "detail_fetch",
                    "Fetching detail pages",
                    completed=index,
                    total=total_fetches,
                    message=f"id {record_id} returned {next_state[record_id]['fetch_status']}",
                    extra={"current_record_id": record_id, "last_status": next_state[record_id]["fetch_status"]},
                )
            continue

        detail_result = parse_detail_record_result_from_html(body, sitemap_entry["url"])
        record = detail_result.get("record")
        rejection_reason = str(detail_result.get("rejection_reason", "") or "parse_error")
        warning = str(detail_result.get("warning", "") or "")
        if not record:
            next_state[record_id]["fetch_status"] = rejection_reason
            source_discovery["anomaly_counts"][rejection_reason] = (
                source_discovery["anomaly_counts"].get(rejection_reason, 0) + 1
            )
            if progress:
                progress.update(
                    "detail_fetch",
                    "Fetching detail pages",
                    completed=index,
                    total=total_fetches,
                    message=f"id {record_id} rejected: {rejection_reason}",
                    extra={"current_record_id": record_id, "last_status": rejection_reason},
                )
            continue

        canonical_by_id[record_id] = record
        next_state[record_id]["url"] = record["url"]
        next_state[record_id]["fetch_status"] = "ok"
        if warning:
            source_discovery["anomaly_counts"][warning] = source_discovery["anomaly_counts"].get(warning, 0) + 1
        if progress:
            progress.update(
                "detail_fetch",
                "Fetching detail pages",
                completed=index,
                total=total_fetches,
                message=f"id {record_id} ok",
                extra={"current_record_id": record_id, "last_status": "ok"},
            )

    source_discovery["reused_rows"] = sum(
        1 for record_id in sitemap_entries if record_id in existing_by_id and record_id not in fetched_ids
    )
    for record_id in sitemap_entries:
        if record_id in existing_by_id and record_id not in fetched_ids:
            current_status = next_state[record_id].get("fetch_status", "")
            if current_status in {"", "bootstrap"}:
                next_state[record_id]["fetch_status"] = "cached"
    return sort_records(list(canonical_by_id.values())), next_state, source_discovery


def load_existing_canonical_records() -> dict[str, dict[str, str]]:
    existing_records = load_json(CANONICAL_JSON_PATH, [])
    if not existing_records:
        snapshot_records: list[dict[str, str]] = []
        for snapshot_path in sorted(SCRAPED_DATA_DIR.glob("floats_*.json")):
            snapshot_records.extend(load_json(snapshot_path, []))
        existing_records = snapshot_records
    record_overrides = load_record_overrides()
    return {
        str(record["id"]): normalize_record(apply_record_override(record, record_overrides.get(str(record["id"]))))
        for record in existing_records
    }


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


def duplicate_group_key(record: dict[str, str]) -> tuple[str, str, str] | None:
    year = str(record.get("year", "")).strip()
    float_number, _ = parse_title(record.get("title", ""))
    location_normalized = normalize_location(record.get("location", ""))
    if not year or not float_number or not location_normalized or location_normalized == "Other/Unknown":
        return None
    return year, float_number, location_normalized


def choose_best_duplicate_record(records: list[dict[str, str]]) -> dict[str, str]:
    def score(record: dict[str, str]) -> tuple[int, int, int, int, int]:
        _, finder = parse_title(record.get("title", ""))
        image = record.get("image", "")
        image_score = 2 if image and not is_placeholder_image_url(image) else 1 if image else 0
        finder_score = 1 if finder and finder.lower() not in {"not specified"} else 0
        return (
            1 if record.get("date_found", "") else 0,
            image_score,
            finder_score,
            len(record.get("location", "")),
            int(record.get("id", "0")) if str(record.get("id", "")).isdigit() else 0,
        )

    return max(records, key=score)


def merge_duplicate_group(records: list[dict[str, str]]) -> dict[str, str]:
    representative = dict(choose_best_duplicate_record(records))
    float_number, representative_finder = parse_title(representative.get("title", ""))

    finder_candidates = []
    for record in records:
        _, finder = parse_title(record.get("title", ""))
        if finder and finder.lower() not in {"not specified"}:
            finder_candidates.append(finder)
    finder = max(finder_candidates, key=lambda value: (len(value), value), default=representative_finder)

    location_candidates = [record.get("location", "").strip() for record in records if record.get("location", "").strip()]
    image_candidates = [record.get("image", "").strip() for record in records if record.get("image", "").strip()]
    actual_images = [image for image in image_candidates if not is_placeholder_image_url(image)]
    dated_candidates = [record.get("date_found", "").strip() for record in records if record.get("date_found", "").strip()]

    representative["title"] = compose_title(float_number, finder, representative.get("title", ""))
    if location_candidates:
        representative["location"] = max(location_candidates, key=lambda value: (len(value), value))
    if actual_images:
        representative["image"] = max(actual_images, key=len)
    elif image_candidates and not representative.get("image", "").strip():
        representative["image"] = max(image_candidates, key=len)
    if dated_candidates:
        representative["date_found"] = max(dated_candidates)

    return normalize_record(representative)


def merge_duplicate_records(records: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    passthrough: list[dict[str, str]] = []

    for record in sort_records(records):
        key = duplicate_group_key(record)
        if key is None:
            passthrough.append(normalize_record(record))
            continue
        grouped.setdefault(key, []).append(normalize_record(record))

    merged_records = list(passthrough)
    merge_report: list[dict[str, Any]] = []
    for (year, float_number, location_normalized), group in grouped.items():
        if len(group) == 1:
            merged_records.extend(group)
            continue

        merged = merge_duplicate_group(group)
        merged_records.append(merged)
        merge_report.append(
            {
                "year": year,
                "float_number": float_number,
                "location_normalized": location_normalized,
                "kept_id": merged["id"],
                "merged_ids": sorted((record["id"] for record in group), key=numeric_sort_key),
            }
        )

    return sort_records(merged_records), merge_report


def write_per_year_snapshots(records: list[dict[str, str]]) -> None:
    by_year: dict[str, list[dict[str, str]]] = {}
    for record in records:
        by_year.setdefault(record["year"], []).append(record)

    SCRAPED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for year, year_records in by_year.items():
        write_json(SCRAPED_DATA_DIR / f"floats_{year}.json", sort_records(year_records))


def rebuild_database(
    records: list[dict[str, str]],
    db_path: Path,
    *,
    sitemap_state: dict[str, dict[str, str]] | None = None,
    record_overrides: dict[str, dict[str, Any]] | None = None,
) -> None:
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
            source_lastmod TEXT DEFAULT '',
            source_first_seen_at TEXT DEFAULT '',
            source_last_seen_at TEXT DEFAULT '',
            source_fetch_status TEXT DEFAULT '',
            suspicious_flags TEXT DEFAULT '[]'
        )
        """
    )

    rows = []
    for record in sort_records(records):
        float_number, finder = parse_title(record["title"])
        override = (record_overrides or {}).get(record["id"], {})
        if "float_number_override" in override:
            float_number = str(override.get("float_number_override", "")).strip()
        if "finder_override" in override:
            finder = str(override.get("finder_override", "")).strip()
        source_entry = normalize_sitemap_state_entry((sitemap_state or {}).get(record["id"]))
        location_normalized = normalize_location(record["location"])
        if "location_normalized_override" in override:
            location_normalized = str(override.get("location_normalized_override", "")).strip()
        rows.append(
            (
                int(record["id"]),
                int(record["year"]) if record["year"].isdigit() else None,
                float_number,
                finder,
                record["location"],
                location_normalized,
                record["date_found"],
                record["url"],
                record["image"],
                "blockislandinfo.com",
                source_entry["sitemap_lastmod"],
                source_entry["first_seen_at"],
                source_entry["last_seen_at"],
                source_entry["fetch_status"],
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
            source,
            source_lastmod,
            source_first_seen_at,
            source_last_seen_at,
            source_fetch_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def build_forecast_summary(forecast_artifact: dict[str, Any]) -> dict[str, Any]:
    seasonal_priors_by_day = forecast_artifact.get("seasonal_priors_by_day", {})
    populated_zone_days = 0
    if isinstance(seasonal_priors_by_day, dict):
        populated_zone_days = sum(1 for predictions in seasonal_priors_by_day.values() if predictions)

    source = forecast_artifact.get("source", {})
    training_rows = source.get("training_rows", 0) if isinstance(source, dict) else 0
    cluster_training_rows = source.get("cluster_training_rows", 0) if isinstance(source, dict) else 0
    primary_model = (
        forecast_artifact.get("evaluation", {})
        .get("selection", {})
        .get("primary_model", "")
    )
    return {
        "training_rows": int(training_rows),
        "cluster_training_rows": int(cluster_training_rows),
        "populated_zone_days": int(populated_zone_days),
        "primary_model": primary_model,
    }


def build_manifest(
    records: list[dict[str, str]],
    validation_summary: dict[str, Any] | None = None,
    forecast_summary: dict[str, Any] | None = None,
    source_discovery: dict[str, Any] | None = None,
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
    if forecast_summary:
        manifest["forecast"] = {
            "training_rows": forecast_summary.get("training_rows", 0),
            "cluster_training_rows": forecast_summary.get("cluster_training_rows", 0),
            "populated_zone_days": forecast_summary.get("populated_zone_days", 0),
            "primary_model": forecast_summary.get("primary_model", ""),
        }
    if source_discovery:
        manifest["source_discovery"] = {
            "refresh_scope": source_discovery.get("refresh_scope", "incremental"),
            "sitemap_urls_seen": source_discovery.get("sitemap_urls_seen", 0),
            "detail_pages_fetched": source_discovery.get("detail_pages_fetched", 0),
            "reused_rows": source_discovery.get("reused_rows", 0),
            "new_ids": source_discovery.get("new_ids", 0),
            "changed_ids": source_discovery.get("changed_ids", 0),
            "backfilled_ids": source_discovery.get("backfilled_ids", 0),
            "forced_refetch_ids": source_discovery.get("forced_refetch_ids", 0),
            "anomaly_counts": dict(source_discovery.get("anomaly_counts", {})),
        }
    return manifest


def build_cleanup_report(
    records: list[dict[str, str]],
    *,
    validation_report: dict[str, Any] | None = None,
    duplicate_merge_report: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    by_year: dict[str, dict[str, int]] = {}
    placeholder_rows: list[dict[str, str]] = []
    blank_location_rows: list[dict[str, str]] = []
    blank_image_rows: list[dict[str, str]] = []
    bucketed_unknown_counts: Counter[str] = Counter()

    for record in sort_records(records):
        year = record["year"] or "unknown"
        bucket = by_year.setdefault(
            year,
            {
                "total": 0,
                "missing_dates": 0,
                "blank_images": 0,
                "placeholder_images": 0,
                "blank_locations": 0,
            },
        )
        bucket["total"] += 1
        if not record["date_found"]:
            bucket["missing_dates"] += 1
        if not record["image"]:
            bucket["blank_images"] += 1
            blank_image_rows.append(record)
        elif is_placeholder_image_url(record["image"]):
            bucket["placeholder_images"] += 1
            placeholder_rows.append(record)
        if not record["location"]:
            bucket["blank_locations"] += 1
            blank_location_rows.append(record)
        else:
            normalized_location = normalize_location(record["location"])
            if normalized_location == "Other/Unknown":
                bucketed_unknown_counts[record["location"]] += 1

    flagged_records = []
    validation_summary = {}
    if isinstance(validation_report, dict):
        flagged_records = validation_report.get("flagged_records", [])
        validation_summary = validation_report.get("summary", {})

    unresolved_title_rows: list[dict[str, Any]] = []
    hash_only_rows: list[dict[str, Any]] = []

    for row in flagged_records if isinstance(flagged_records, list) else []:
        validation_errors = row.get("validation_errors", [])
        suspicious_flags = row.get("suspicious_flags", [])
        if "invalid_float_number" in validation_errors and len(unresolved_title_rows) < 25:
            unresolved_title_rows.append(
                {
                    "id": str(row.get("id", "")),
                    "year": str(row.get("year", "")),
                    "finder": str(row.get("finder", "")),
                    "url": str(row.get("url", "")),
                }
            )
        if "blank_float_with_hash_finder" in suspicious_flags and len(hash_only_rows) < 25:
            hash_only_rows.append(
                {
                    "id": str(row.get("id", "")),
                    "year": str(row.get("year", "")),
                    "finder": str(row.get("finder", "")),
                    "url": str(row.get("url", "")),
                }
            )

    return {
        "generated_at": iso_now(),
        "totals": {
            "records": len(records),
            "missing_dates": sum(1 for record in records if not record["date_found"]),
            "blank_images": len(blank_image_rows),
            "placeholder_images": len(placeholder_rows),
            "blank_locations": len(blank_location_rows),
            "bucketed_unknown_locations": sum(bucketed_unknown_counts.values()),
            "merged_duplicate_groups": len(duplicate_merge_report or []),
        },
        "by_year": {year: by_year[year] for year in sorted(by_year, reverse=True)},
        "validation": {
            "summary": validation_summary,
            "top_bucketed_unknown_locations": bucketed_unknown_counts.most_common(50),
            "unresolved_title_rows": unresolved_title_rows,
            "hash_only_title_rows": hash_only_rows,
        },
        "examples": {
            "recent_blank_location_rows": blank_location_rows[:25],
            "recent_blank_image_rows": blank_image_rows[:25],
            "recent_placeholder_image_rows": placeholder_rows[:25],
        },
        "duplicate_merges": duplicate_merge_report or [],
    }


def write_cleanup_summary(cleanup_report: dict[str, Any]) -> None:
    totals = cleanup_report.get("totals", {})
    validation = cleanup_report.get("validation", {})
    by_year = cleanup_report.get("by_year", {})
    unknown_locations = validation.get("top_bucketed_unknown_locations", [])
    title_rows = validation.get("unresolved_title_rows", [])
    recent_blank_locations = cleanup_report.get("examples", {}).get("recent_blank_location_rows", [])

    lines = [
        "# Data Cleanup Summary",
        "",
        f"- Generated at: {cleanup_report.get('generated_at', '')}",
        f"- Records reviewed: {totals.get('records', 0)}",
        f"- Missing dates: {totals.get('missing_dates', 0)}",
        f"- Blank images: {totals.get('blank_images', 0)}",
        f"- Placeholder images (treated as complete/no-photo posts): {totals.get('placeholder_images', 0)}",
        f"- Blank locations: {totals.get('blank_locations', 0)}",
        f"- Bucketed unknown/off-island locations: {totals.get('bucketed_unknown_locations', 0)}",
        f"- Merged duplicate groups: {totals.get('merged_duplicate_groups', 0)}",
        "",
        "## Can Fill",
        "",
        "- Placeholder-image rows stay classified as complete entries rather than missing-image holes.",
        "- Title parsing now recovers obvious numeric-only and hash-prefixed float numbers during DB rebuild.",
        "- Vague, off-island, and unknown locations are bucketed into `Other/Unknown` for modeling exclusion.",
        f"- Remaining unresolved title rows for manual review: {len(title_rows)}",
        "",
        "## Probably Source Missing",
        "",
    ]
    for year, bucket in by_year.items():
        if bucket["missing_dates"] or bucket["blank_images"] or bucket["placeholder_images"]:
            lines.append(
                f"- {year}: dates {bucket['missing_dates']}, blank images {bucket['blank_images']}, placeholder images {bucket['placeholder_images']}"
            )

    lines.extend(
        [
            "",
            "## Manual Review",
            "",
        ]
    )
    for location_raw, count in unknown_locations[:15]:
        label = location_raw or "(blank)"
        lines.append(f"- Bucketed location `{label}`: {count}")

    if recent_blank_locations:
        lines.extend(
            [
                "",
                "## Blank Location Examples",
                "",
            ]
        )
        for record in recent_blank_locations[:10]:
            lines.append(f"- {record['year']} #{record['id']}: {record['title']} ({record['url']})")

    CLEANUP_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    CLEANUP_SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_manual_review_queue(validation_report: dict[str, Any] | None = None) -> dict[str, Any]:
    flagged_records = []
    if isinstance(validation_report, dict):
        flagged_records = validation_report.get("flagged_records", [])

    unresolved_titles: list[dict[str, Any]] = []
    duplicate_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}

    for row in flagged_records if isinstance(flagged_records, list) else []:
        validation_errors = row.get("validation_errors", [])
        suspicious_flags = row.get("suspicious_flags", [])

        if "invalid_float_number" in validation_errors:
            unresolved_titles.append(
                {
                    "id": str(row.get("id", "")),
                    "year": str(row.get("year", "")),
                    "finder": str(row.get("finder", "")),
                    "location_raw": str(row.get("location_raw", "")),
                    "url": str(row.get("url", "")),
                }
            )

        if "duplicate_float_year_location" in suspicious_flags:
            key = (
                str(row.get("year", "")),
                str(row.get("float_number", "")),
                str(row.get("location_normalized", "")),
            )
            duplicate_groups.setdefault(key, []).append(
                {
                    "id": str(row.get("id", "")),
                    "finder": str(row.get("finder", "")),
                    "location_raw": str(row.get("location_raw", "")),
                    "date_found": str(row.get("date_found", "")),
                    "url": str(row.get("url", "")),
                }
            )

    grouped_duplicates = [
        {
            "year": year,
            "float_number": float_number,
            "location_normalized": location_normalized,
            "records": records,
        }
        for (year, float_number, location_normalized), records in sorted(duplicate_groups.items())
    ]

    return {
        "generated_at": iso_now(),
        "counts": {
            "unresolved_titles": len(unresolved_titles),
            "duplicate_groups": len(grouped_duplicates),
        },
        "unresolved_titles": unresolved_titles,
        "duplicate_groups": grouped_duplicates,
    }


def write_manual_review_summary(manual_review_queue: dict[str, Any]) -> None:
    counts = manual_review_queue.get("counts", {})
    lines = [
        "# Manual Review Queue",
        "",
        f"- Generated at: {manual_review_queue.get('generated_at', '')}",
        f"- Unresolved titles: {counts.get('unresolved_titles', 0)}",
        f"- Duplicate groups: {counts.get('duplicate_groups', 0)}",
        "",
        "## Titles",
        "",
    ]
    for row in manual_review_queue.get("unresolved_titles", [])[:15]:
        lines.append(f"- {row['year']} #{row['id']}: {row['finder']} ({row['url']})")

    lines.extend(
        [
            "",
            "## Duplicate Groups",
            "",
        ]
    )
    for group in manual_review_queue.get("duplicate_groups", [])[:15]:
        lines.append(
            f"- {group['year']} float {group['float_number']} at {group['location_normalized']}: {len(group['records'])} records"
        )

    MANUAL_REVIEW_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANUAL_REVIEW_SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
                f"- Cleanup report JSON: {CLEANUP_REPORT_PATH}",
                f"- Cleanup summary: {CLEANUP_SUMMARY_PATH}",
                f"- Manual review queue: {MANUAL_REVIEW_PATH}",
                f"- Manual review summary: {MANUAL_REVIEW_SUMMARY_PATH}",
            ]
        )
    forecast = manifest.get("forecast")
    if forecast:
        lines.extend(
            [
                "",
                "## Forecast Artifact",
                "",
                f"- Training rows: {forecast['training_rows']}",
                f"- Cluster training rows: {forecast.get('cluster_training_rows', 0)}",
                f"- Populated zone days: {forecast.get('populated_zone_days', 0)}/366",
                f"- Primary model: {forecast.get('primary_model', 'Unknown')}",
                f"- Artifact JSON: {FORECAST_PATH}",
                f"- Evaluation JSON: {FORECAST_EVALUATION_PATH}",
                f"- Evaluation summary: {FORECAST_EVALUATION_SUMMARY_PATH}",
            ]
        )
    source_discovery = manifest.get("source_discovery")
    if source_discovery:
        lines.extend(
            [
                "",
                "## Source Discovery",
                "",
                f"- Refresh scope: {source_discovery.get('refresh_scope', 'incremental')}",
                f"- Sitemap URLs seen: {source_discovery['sitemap_urls_seen']}",
                f"- Detail pages fetched: {source_discovery['detail_pages_fetched']}",
                f"- Reused rows: {source_discovery['reused_rows']}",
                f"- New IDs: {source_discovery['new_ids']}",
                f"- Changed IDs: {source_discovery['changed_ids']}",
                f"- Backfilled IDs: {source_discovery['backfilled_ids']}",
                f"- Forced refetch IDs: {source_discovery.get('forced_refetch_ids', 0)}",
            ]
        )
        anomaly_counts = source_discovery.get("anomaly_counts", {})
        if anomaly_counts:
            lines.extend(
                [
                    "",
                    "## Source Anomalies",
                    "",
                ]
            )
            for key, count in sorted(anomaly_counts.items()):
                lines.append(f"- {key}: {count}")
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_forecast_evaluation_summary(evaluation: dict[str, Any]) -> None:
    cluster_metrics = evaluation.get("targets", {}).get("cluster", {}) if isinstance(evaluation, dict) else {}
    selection = evaluation.get("selection", {}) if isinstance(evaluation, dict) else {}

    lines = [
        "# Forecast Evaluation Summary",
        "",
        f"- Primary model: {selection.get('primary_model', 'Unknown')}",
        f"- Gating reason: {selection.get('gating_reason', 'Unavailable')}",
    ]

    if cluster_metrics:
        lines.extend(["", "## Cluster Backtests", ""])
        for model_name, metrics in cluster_metrics.items():
            lines.append(
                f"- {model_name}: top-1 {metrics.get('top1_accuracy', 0)}, "
                f"top-3 {metrics.get('top3_accuracy', 0)}, "
                f"log loss {metrics.get('log_loss', 0)}, "
                f"calibration gap {metrics.get('calibration_gap', 0)}"
            )

    FORECAST_EVALUATION_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    FORECAST_EVALUATION_SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_forecast_artifact(
    manifest: dict[str, Any],
    forecast_path: Path = FORECAST_PATH,
    evaluation_path: Path = FORECAST_EVALUATION_PATH,
) -> list[str]:
    expected_months = {str(month) for month in range(1, 13)}
    expected_days = {str(day) for day in range(1, 367)}

    if not forecast_path.exists():
        return [f"Forecast artifact is missing: {forecast_path}"]

    try:
        forecast_artifact = load_json(forecast_path, {})
    except json.JSONDecodeError:
        return [f"Forecast artifact is invalid JSON: {forecast_path}"]

    errors: list[str] = []
    if forecast_artifact.get("version") != 2:
        errors.append("Forecast artifact version must be 2.")
    source = forecast_artifact.get("source", {})
    if not isinstance(source, dict):
        errors.append("Forecast artifact source payload is missing or invalid.")
    else:
        if source.get("total_records") != manifest.get("total_records"):
            errors.append("Forecast artifact total_records does not match refresh manifest.")
        if source.get("latest_source_date", "") != manifest.get("latest_source_date", ""):
            errors.append("Forecast artifact latest_source_date does not match refresh manifest.")

    seasonality_by_month = forecast_artifact.get("seasonality_by_month", {})
    if not isinstance(seasonality_by_month, dict) or set(seasonality_by_month) != expected_months:
        errors.append("Forecast artifact seasonality_by_month must contain months 1..12.")

    activity_index_by_day = forecast_artifact.get("activity_index_by_day", {})
    if not isinstance(activity_index_by_day, dict) or set(activity_index_by_day) != expected_days:
        errors.append("Forecast artifact activity_index_by_day must contain days 1..366.")

    seasonal_priors_by_day = forecast_artifact.get("seasonal_priors_by_day", {})
    if not isinstance(seasonal_priors_by_day, dict) or set(seasonal_priors_by_day) != expected_days:
        errors.append("Forecast artifact seasonal_priors_by_day must contain days 1..366.")
    elif any(not isinstance(priors, dict) for priors in seasonal_priors_by_day.values()):
        errors.append("Forecast artifact seasonal_priors_by_day entries must be objects.")

    cluster_profiles = forecast_artifact.get("cluster_profiles", {})
    if not isinstance(cluster_profiles, dict):
        errors.append("Forecast artifact cluster_profiles payload is missing or invalid.")

    feature_sources = forecast_artifact.get("feature_sources", {})
    if not isinstance(feature_sources, dict):
        errors.append("Forecast artifact feature_sources payload is missing or invalid.")

    evaluation = forecast_artifact.get("evaluation", {})
    if not isinstance(evaluation, dict):
        errors.append("Forecast artifact evaluation payload is missing or invalid.")
    else:
        selection = evaluation.get("selection", {})
        if not isinstance(selection, dict) or not selection.get("primary_model"):
            errors.append("Forecast artifact evaluation.selection.primary_model is missing.")
        targets = evaluation.get("targets", {})
        if not isinstance(targets, dict) or not isinstance(targets.get("cluster", {}), dict):
            errors.append("Forecast artifact evaluation.targets.cluster is missing or invalid.")

    if not evaluation_path.exists():
        errors.append(f"Forecast evaluation JSON is missing: {evaluation_path}")
    else:
        evaluation_payload = load_json(evaluation_path, {})
        if evaluation_payload != evaluation:
            errors.append("Forecast evaluation JSON does not match artifact evaluation payload.")

    return errors


def validate_sitemap_state(
    records: list[dict[str, str]],
    sitemap_state_path: Path = SITEMAP_STATE_PATH,
) -> list[str]:
    if not sitemap_state_path.exists():
        return [f"Sitemap state is missing: {sitemap_state_path}"]

    try:
        sitemap_state = load_json(sitemap_state_path, {})
    except json.JSONDecodeError:
        return [f"Sitemap state is invalid JSON: {sitemap_state_path}"]

    if not isinstance(sitemap_state, dict):
        return [f"Sitemap state payload is invalid: {sitemap_state_path}"]

    errors: list[str] = []
    required_ids = {record["id"] for record in records}
    missing_ids = sorted(required_ids - {str(record_id) for record_id in sitemap_state}, key=numeric_sort_key)
    if missing_ids:
        errors.append(f"Sitemap state is missing canonical ids: {len(missing_ids)} missing.")

    for record_id, entry in sitemap_state.items():
        if not isinstance(entry, dict):
            errors.append(f"Sitemap state entry is invalid for id {record_id}.")
            continue
        missing_keys = [key for key in SITEMAP_STATE_KEYS if key not in entry]
        if missing_keys:
            errors.append(f"Sitemap state entry {record_id} is missing keys: {', '.join(missing_keys)}")

    return errors


def validate_outputs(
    records: list[dict[str, str]],
    db_path: Path = DB_PATH,
    manifest_path: Path = MANIFEST_PATH,
    forecast_path: Path = FORECAST_PATH,
    evaluation_path: Path = FORECAST_EVALUATION_PATH,
    sitemap_state_path: Path = SITEMAP_STATE_PATH,
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
        errors.extend(
            validate_forecast_artifact(
                manifest,
                forecast_path=forecast_path,
                evaluation_path=evaluation_path,
            )
        )
    errors.extend(validate_sitemap_state(records, sitemap_state_path=sitemap_state_path))

    for year in {record["year"] for record in records}:
        snapshot_path = SCRAPED_DATA_DIR / f"floats_{year}.json"
        snapshot_records = load_json(snapshot_path, [])
        snapshot_ids = {str(record["id"]) for record in snapshot_records}
        expected_ids = {record["id"] for record in records if record["year"] == year}
        if snapshot_ids != expected_ids:
            errors.append(f"Per-year snapshot drift detected for {year}.")

    return errors


def refresh_data(*, full_refresh: bool = False) -> int:
    progress = RefreshProgress()
    existing_by_id = load_existing_canonical_records()
    record_overrides = load_record_overrides()
    session = make_session()
    try:
        progress.update("robots", "Fetching robots policy", force=True)
        fetcher = PoliteSession(session)
        robots_policy = fetch_robots_policy(fetcher)
        progress.update("sitemap", "Discovering sitemap entries", force=True)
        sitemap_entries, disallowed_count = discover_sitemap_entries(fetcher, robots_policy)
        progress.update(
            "sitemap",
            "Discovering sitemap entries",
            completed=len(sitemap_entries),
            total=len(sitemap_entries),
            message=f"{disallowed_count} disallowed by robots",
            force=True,
        )
        previous_sitemap_state = load_sitemap_state()
        canonical_records, sitemap_state, source_discovery = apply_sitemap_updates(
            existing_by_id,
            sitemap_entries,
            previous_sitemap_state,
            lambda url: fetch_detail_page_result(fetcher, url),
            refreshed_at=iso_now(),
            backfill_batch_size=HISTORICAL_BACKFILL_BATCH_SIZE,
            full_refresh=full_refresh,
            disallowed_count=disallowed_count,
            progress=progress,
        )
    except SourceAccessDeniedError as exc:
        progress.fail(str(exc))
        print(f"ERROR: {exc}")
        return 1
    except RuntimeError as exc:
        progress.fail(str(exc))
        print(f"ERROR: {exc}")
        return 1
    except KeyboardInterrupt:
        progress.fail("Interrupted by user.", interrupted=True)
        return 130

    if not canonical_records:
        progress.fail("The source site returned zero records. Existing artifacts were left unchanged.")
        print("ERROR: The source site returned zero records. Existing artifacts were left unchanged.")
        return 1

    progress.update("normalize", "Normalizing and merging records", force=True)
    canonical_records = [
        normalize_record(apply_record_override(record, record_overrides.get(record["id"])))
        for record in canonical_records
    ]
    canonical_records, duplicate_merge_report = merge_duplicate_records(canonical_records)
    canonical_records, dropped_outliers = exclude_extreme_float_number_records(canonical_records)
    if dropped_outliers:
        dropped_labels = ", ".join(
            f"{record['year']} #{parse_title(record['title'])[0]} (id {record['id']})"
            for record in dropped_outliers
        )
        print(f"Excluded {len(dropped_outliers)} extreme float-number outlier record(s): {dropped_labels}")

    canonical_ids = {record["id"] for record in canonical_records}
    legacy_rows = get_legacy_rows(DB_PATH, canonical_ids)

    progress.update("write", "Writing canonical artifacts", completed=0, total=3, force=True)
    write_json(CANONICAL_JSON_PATH, canonical_records)
    progress.update("write", "Writing canonical artifacts", completed=1, total=3, message=str(CANONICAL_JSON_PATH))
    write_json(SITEMAP_STATE_PATH, sitemap_state)
    progress.update("write", "Writing canonical artifacts", completed=2, total=3, message=str(SITEMAP_STATE_PATH))
    write_per_year_snapshots(canonical_records)
    progress.update("write", "Writing canonical artifacts", completed=3, total=3, message=str(SCRAPED_DATA_DIR), force=True)
    progress.update("database", "Rebuilding SQLite database", force=True)
    rebuild_database(
        canonical_records,
        DB_PATH,
        sitemap_state=sitemap_state,
        record_overrides=record_overrides,
    )
    progress.update("validate_records", "Validating rebuilt rows", force=True)
    validation_summary = run_validation_pipeline(
        db_path=DB_PATH,
        report_json_path=VALIDATION_REPORT_JSON,
        report_csv_path=VALIDATION_REPORT_CSV,
        default_source="blockislandinfo.com",
    )

    progress.update("forecast", "Building forecast artifact", force=True)
    valid_dates = [record["date_found"] for record in canonical_records if record["date_found"]]
    forecast_artifact = ml_predictor.build_forecast_artifact(
        db_name=str(DB_PATH),
        total_records=len(canonical_records),
        latest_source_date=max(valid_dates) if valid_dates else "",
        generated_at=iso_now(),
    )
    progress.update("forecast", "Writing forecast artifact", completed=0, total=3, force=True)
    write_json(FORECAST_PATH, forecast_artifact)
    progress.update("forecast", "Writing forecast artifact", completed=1, total=3, message=str(FORECAST_PATH))
    write_json(FORECAST_EVALUATION_PATH, forecast_artifact.get("evaluation", {}))
    progress.update("forecast", "Writing forecast artifact", completed=2, total=3, message=str(FORECAST_EVALUATION_PATH))
    write_forecast_evaluation_summary(forecast_artifact.get("evaluation", {}))
    progress.update("forecast", "Writing forecast artifact", completed=3, total=3, message=str(FORECAST_EVALUATION_SUMMARY_PATH), force=True)

    progress.update("reports", "Writing refresh reports", force=True)
    forecast_summary = build_forecast_summary(forecast_artifact)
    manifest = build_manifest(
        canonical_records,
        validation_summary=validation_summary,
        forecast_summary=forecast_summary,
        source_discovery=source_discovery,
    )
    write_json(MANIFEST_PATH, manifest)
    validation_report = load_json(VALIDATION_REPORT_JSON, {})
    cleanup_report = build_cleanup_report(
        canonical_records,
        validation_report=validation_report,
        duplicate_merge_report=duplicate_merge_report,
    )
    write_json(CLEANUP_REPORT_PATH, cleanup_report)
    write_cleanup_summary(cleanup_report)
    manual_review_queue = build_manual_review_queue(validation_report)
    write_json(MANUAL_REVIEW_PATH, manual_review_queue)
    write_manual_review_summary(manual_review_queue)

    audit_payload = {
        "generated_at": iso_now(),
        "legacy_row_count": len(legacy_rows),
        "rows": legacy_rows,
    }
    write_json(AUDIT_PATH, audit_payload)
    write_summary(manifest, legacy_rows)

    progress.update("validate_outputs", "Validating final artifacts", force=True)
    errors = validate_outputs(canonical_records)
    if errors:
        progress.fail(f"{len(errors)} final validation error(s).")
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    progress.complete(
        f"Rebuilt {len(canonical_records)} records; fetched {source_discovery['detail_pages_fetched']} detail pages."
    )
    print(
        f"{'Full' if full_refresh else 'Incremental'} refresh rebuilt {len(canonical_records)} records across "
        f"{len(manifest['records_by_year'])} years. "
        f"Latest source date: {manifest['latest_source_date'] or 'Unknown'}. "
        f"Fetched {source_discovery['detail_pages_fetched']} detail pages. "
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


def show_refresh_status() -> int:
    status = load_json(REFRESH_STATUS_PATH, {})
    if not status:
        print(f"No refresh status found at {REFRESH_STATUS_PATH}.")
        return 1

    label = status.get("phase_label", status.get("phase", "Unknown"))
    completed = int(status.get("completed") or 0)
    total = int(status.get("total") or 0)
    progress = f"{completed}/{total} ({status.get('percent', 0)}%)" if total else str(status.get("status", "unknown"))
    message = str(status.get("message") or "").strip()
    print(f"Status: {status.get('status', 'unknown')}")
    print(f"Phase: {label}")
    print(f"Progress: {progress}")
    print(f"Elapsed: {status.get('elapsed_label', 'unknown')}")
    print(f"ETA: {status.get('eta_label', 'unknown')}")
    if message:
        print(f"Message: {message}")
    print(f"Updated: {status.get('updated_at', '')}")
    print(f"File: {REFRESH_STATUS_PATH}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh and validate float tracker data artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    refresh_parser = subparsers.add_parser("refresh", help="Scrape the source site and rebuild generated data artifacts.")
    refresh_parser.add_argument(
        "--full",
        action="store_true",
        help="Refetch every sitemap detail page instead of only new, changed, and capped backfill records.",
    )
    subparsers.add_parser("validate", help="Validate canonical JSON, snapshots, manifest, and SQLite outputs.")
    subparsers.add_parser(
        "validate-records",
        help="Run staged row validation against the current SQLite database.",
    )
    subparsers.add_parser("status", help="Show the latest refresh progress status.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "refresh":
        return refresh_data(full_refresh=bool(args.full))
    if args.command == "validate":
        return validate_data()
    if args.command == "validate-records":
        return validate_records()
    if args.command == "status":
        return show_refresh_status()
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
