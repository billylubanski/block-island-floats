from __future__ import annotations

import asyncio
import copy
import os
import sqlite3
import sys
import threading
from collections import Counter
from pathlib import Path
from socket import socket
from urllib.parse import quote

import app as app_module
import pytest
from werkzeug.serving import make_server


UI_SMOKE_ENABLED = os.getenv("RUN_UI_SMOKE", "").lower() in {"1", "true", "yes", "on"}
pytestmark = [
    pytest.mark.ui,
    pytest.mark.skipif(
        not UI_SMOKE_ENABLED,
        reason="Set RUN_UI_SMOKE=1 to enable Playwright UI smoke tests.",
    ),
]


def sample_forecast_briefing() -> dict[str, object]:
    return {
        "date": "2026-07-01",
        "activity_score": 7.2,
        "activity_label": "Active",
        "confidence_band": "low",
        "conditions": {
            "weather": {
                "temp": 68,
                "condition": "Partly Cloudy",
                "wind": 9,
                "wind_direction": "SW",
                "precip_chance": 20,
                "emoji": "WEATHER",
                "timestamp": "09:30 AM",
                "updated_at": "2026-07-01T09:30:00Z",
            },
            "tide": {
                "stage": "rising",
                "height_now": 1.8,
                "daily_range": 3.1,
                "nearest_event": {
                    "type": "high",
                    "hours_away": 1.5,
                },
                "updated_at": "2026-07-01T09:15:00Z",
            },
            "calendar": {
                "weekday_name": "Wednesday",
                "moon_phase": "full",
                "is_long_weekend": False,
                "is_holiday": False,
            },
        },
        "zones": [
            {
                "label": "Rodman's Hollow",
                "location_href": "/location/Rodman%27s%20Hollow",
                "field_href": "/field",
                "signal_label": "Best signal",
                "support_count": 23,
                "dated_support_count": 12,
                "actual_years": [2024, 2025],
                "supporting_spots": [
                    {"name": "Rodman's Hollow"},
                    {"name": "Meadow Hill Trail"},
                ],
                "reason_tags": ["Strong july history", "Recent finds nearby"],
                "reason_texts": ["Recent reports support this zone."],
                "score": 0.224,
                "primary_spot": "Rodman's Hollow",
            },
            {
                "label": "Clay Head Trail",
                "location_href": "/location/Clay%20Head%20Trail",
                "field_href": "/field",
                "signal_label": "Useful fallback",
                "support_count": 18,
                "dated_support_count": 9,
                "actual_years": [2024, 2025],
                "supporting_spots": [{"name": "Clay Head Trail"}],
                "reason_tags": ["Strong july history"],
                "reason_texts": ["Seasonal support is doing most of the work here."],
                "score": 0.184,
                "primary_spot": "Clay Head Trail",
            },
        ],
        "lead_change_summary": "Lead zone rotated from Clay Head Trail to Rodman's Hollow.",
        "disclaimer": "This briefing is directional.",
        "feature_freshness": {
            "artifact_generated_at": "2026-07-01T08:00:00Z",
            "weather_updated_at": "2026-07-01T09:30:00Z",
            "tide_updated_at": "2026-07-01T09:15:00Z",
            "historical_weather_available": False,
        },
        "selected_model": "kernel_seasonal",
    }


def sample_field_weather() -> dict[str, object]:
    return {
        "temp": 68,
        "condition": "Partly Cloudy",
        "wind": 9,
        "emoji": "WEATHER",
        "timestamp": "09:30 AM",
    }


def create_finds_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE finds (
            id TEXT PRIMARY KEY,
            year TEXT,
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
    conn.commit()
    conn.close()


def insert_find(path: Path, **values) -> None:
    conn = sqlite3.connect(path)
    columns = ", ".join(values.keys())
    placeholders = ", ".join("?" for _ in values)
    conn.execute(
        f"INSERT INTO finds ({columns}) VALUES ({placeholders})",
        tuple(values.values()),
    )
    conn.commit()
    conn.close()


def open_port() -> int:
    with socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _probe_asyncio_subprocess() -> tuple[bool, str | None]:
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "print('ok')",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
    except Exception as exc:
        return False, str(exc)

    if proc.returncode != 0:
        return False, stderr.decode().strip() or f"subprocess exited with {proc.returncode}"

    if stdout.decode().strip() != "ok":
        return False, "subprocess probe returned unexpected output"

    return True, None


def asyncio_subprocess_available() -> tuple[bool, str | None]:
    try:
        return asyncio.run(_probe_asyncio_subprocess())
    except Exception as exc:
        return False, str(exc)


@pytest.fixture
def live_ui_server(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    app_module.weather_cache["data"] = None
    app_module.weather_cache["timestamp"] = None
    app_module.tide_cache["data"] = None
    app_module.tide_cache["timestamp"] = None
    app_module.clear_forecast_cache()

    db_path = tmp_path / "ui-smoke.db"
    create_finds_db(db_path)
    insert_find(
        db_path,
        id="2025-1",
        year="2025",
        float_number="1",
        finder="Tester",
        location_raw="rodman",
        location_normalized="Rodman's Hollow",
        date_found="2025-07-10",
        url="https://example.com/find/2025-1",
        image_url="https://cdn.example.com/2025-1.jpg",
    )
    insert_find(
        db_path,
        id="2024-1",
        year="2024",
        float_number="4",
        finder="Another Tester",
        location_raw="rodman",
        location_normalized="Rodman's Hollow",
        date_found="2024-08-01",
        url="https://example.com/find/2024-1",
        image_url="https://cdn.example.com/2024-1.jpg",
    )

    monkeypatch.setattr(
        app_module,
        "build_daily_forecast_briefing",
        lambda target_date=None: copy.deepcopy(sample_forecast_briefing()),
    )
    monkeypatch.setattr(
        app_module,
        "get_location_counts",
        lambda year_param=None: Counter(
            {
                "Rodman's Hollow": 23,
                "Clay Head Trail": 18,
                "Hodge Family Wildlife Preserve": 11,
            }
        ),
    )
    monkeypatch.setattr(app_module, "DB_NAME", str(db_path))
    monkeypatch.setattr(app_module, "get_last_updated", lambda: "Fixture update")
    monkeypatch.setattr(app_module, "get_weather_data", lambda: sample_field_weather())

    host = "127.0.0.1"
    port = open_port()
    server = make_server(host, port, app_module.app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        app_module.weather_cache["data"] = None
        app_module.weather_cache["timestamp"] = None
        app_module.tide_cache["data"] = None
        app_module.tide_cache["timestamp"] = None
        app_module.clear_forecast_cache()


@pytest.fixture(scope="session")
def chromium_browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    supported, reason = asyncio_subprocess_available()
    if not supported:
        pytest.skip(f"Playwright Chromium is unavailable in this sandbox: {reason}")

    playwright = None
    browser = None

    try:
        playwright = sync_api.sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
    except Exception as exc:  # pragma: no cover - environment dependent
        if playwright is not None:
            playwright.stop()
        pytest.skip(f"Playwright Chromium is unavailable: {exc}")

    try:
        yield browser
    finally:
        browser.close()
        playwright.stop()


@pytest.fixture
def ui_page(chromium_browser, live_ui_server):
    context = chromium_browser.new_context(viewport={"width": 1440, "height": 1600})

    def route_request(route):
        url = route.request.url
        if url.startswith(live_ui_server) or url.startswith("data:") or url == "about:blank":
            route.continue_()
            return

        if url == "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css":
            route.fulfill(status=200, content_type="text/css", body="")
            return

        if url == "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js":
            route.fulfill(status=200, content_type="application/javascript", body="")
            return

        route.abort()

    context.route("**/*", route_request)
    page = context.new_page()
    page.set_default_timeout(10000)

    errors: list[str] = []
    page.on(
        "console",
        lambda message: errors.append(f"console:{message.type}:{message.text}")
        if message.type == "error"
        else None,
    )
    page.on("pageerror", lambda error: errors.append(f"pageerror:{error}"))

    try:
        yield page, errors
    finally:
        context.close()


def test_forecast_page_smoke_renders_zone_briefing(live_ui_server, ui_page):
    page, errors = ui_page

    page.goto(f"{live_ui_server}/forecast", wait_until="domcontentloaded")

    assert page.title() == "Where to start today | Block Island Glass Floats"
    assert page.locator("h1").inner_text() == "Where to start today"
    assert page.locator(".forecast-zone").count() == 2
    assert page.locator(".forecast-context-card h3").all_inner_texts() == [
        "Weather",
        "Tide",
        "Calendar",
    ]
    assert page.locator(".utility-rail .pill").all_inner_texts() == [
        "Today",
        "Strength: Low",
        "History + live conditions",
    ]
    assert page.locator(".utility-rail__summary").inner_text().strip() == "Use this as a starting suggestion, then confirm with access and conditions on the ground."
    assert page.locator(".forecast-zone__heading a").all_inner_texts() == [
        "Rodman's Hollow",
        "Clay Head Trail",
    ]

    body_text = page.locator("body").inner_text()
    assert "Where to go next if you want a backup" in body_text
    assert "Why Rodman's Hollow is up front" in body_text
    assert "Why this stays a starting suggestion" in body_text
    assert "% probability" not in body_text
    assert "probability" not in body_text.lower()
    assert errors == []


def test_forecast_page_hands_off_to_field_mode(live_ui_server, ui_page):
    page, errors = ui_page

    page.goto(f"{live_ui_server}/forecast", wait_until="domcontentloaded")
    page.get_by_role("link", name="Open field view").first().click()

    assert page.url == f"{live_ui_server}/field"
    assert page.title() == "Find the best spots near you | Block Island Glass Floats"
    assert page.locator("h1").inner_text() == "Find the best spots near you"
    assert page.locator(".field-forecast-strip h2").inner_text() == "Best first stop: Rodman's Hollow"
    assert page.locator(".field-forecast-strip .pill").all_inner_texts() == [
        "Active outlook",
        "Strength: Low",
        "Strong july history",
        "Recent finds nearby",
    ]

    spot_badges = page.locator(".spot-card .pill").all_inner_texts()
    assert spot_badges == ["Forecast zone #1", "Forecast zone #2"]

    support_stats = page.locator(".spot-stat").all_inner_texts()
    assert "Backup area for Rodman's Hollow" in support_stats
    assert "Backup area for Clay Head Trail" in support_stats
    assert errors == []


def test_location_page_share_button_uses_native_share(live_ui_server, ui_page):
    page, errors = ui_page
    encoded_location = quote("Rodman's Hollow", safe="")

    page.add_init_script(
        """
        window.__shareCalls = [];
        Object.defineProperty(navigator, 'share', {
            configurable: true,
            value: async (payload) => {
                window.__shareCalls.push(payload);
            }
        });
        Object.defineProperty(navigator, 'sendBeacon', {
            configurable: true,
            value: () => true
        });
        """
    )

    page.goto(f"{live_ui_server}/location/{encoded_location}", wait_until="domcontentloaded")
    page.get_by_role("button", name="Share this spot").click()

    share_status = page.locator("#share-status")
    share_status.wait_for(state="visible")

    assert share_status.inner_text() == "Shared"
    assert page.evaluate("window.__shareCalls") == [
        {
            "title": "Rodman's Hollow | Block Island Glass Floats",
            "text": "Rodman's Hollow has 2 reported finds across 2 seasons. Spot brief:",
            "url": f"{live_ui_server}/location/Rodman's%20Hollow?ref=share",
        }
    ]
    assert errors == []
