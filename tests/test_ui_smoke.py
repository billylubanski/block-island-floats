from __future__ import annotations

import copy
import os
import threading
from collections import Counter
from socket import socket

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


def open_port() -> int:
    with socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def live_ui_server(monkeypatch: pytest.MonkeyPatch):
    app_module.weather_cache["data"] = None
    app_module.weather_cache["timestamp"] = None
    app_module.tide_cache["data"] = None
    app_module.tide_cache["timestamp"] = None
    app_module.clear_forecast_cache()

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

    try:
        playwright = sync_api.sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
    except Exception as exc:  # pragma: no cover - environment dependent
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

    assert page.title() == "Forecast briefing | Block Island Glass Floats"
    assert page.locator("h1").inner_text() == "Forecast briefing"
    assert page.locator(".forecast-zone").count() == 2
    assert page.locator(".forecast-context-card h3").all_inner_texts() == [
        "Weather",
        "Tide",
        "Calendar",
    ]
    assert page.locator(".utility-rail .pill").all_inner_texts() == [
        "Today",
        "Confidence: Low",
        "Primary spine: kernel seasonal",
    ]
    assert page.locator(".utility-rail__summary").inner_text().strip() == "Directional only."
    assert page.locator(".forecast-zone__heading a").all_inner_texts() == [
        "Rodman's Hollow",
        "Clay Head Trail",
    ]

    body_text = page.locator("body").inner_text()
    assert "Top zones for a first loop" in body_text
    assert "Start with the zone" in body_text
    assert "Why confidence stays bounded" in body_text
    assert "% probability" not in body_text
    assert "probability" not in body_text.lower()
    assert errors == []


def test_forecast_page_hands_off_to_field_mode(live_ui_server, ui_page):
    page, errors = ui_page

    page.goto(f"{live_ui_server}/forecast", wait_until="domcontentloaded")
    page.get_by_role("link", name="Open field mode").first().click()

    assert page.url == f"{live_ui_server}/field"
    assert page.title() == "Field mode | Block Island Glass Floats"
    assert page.locator("h1").inner_text() == "Field mode"
    assert page.locator(".field-forecast-strip h2").inner_text() == "Start with Rodman's Hollow"
    assert page.locator(".field-forecast-strip .pill").all_inner_texts() == [
        "Active read",
        "Confidence: Low",
        "Strong july history",
        "Recent finds nearby",
    ]

    spot_badges = page.locator(".spot-card .pill").all_inner_texts()
    assert spot_badges == ["Forecast zone #1", "Forecast zone #2"]

    support_stats = page.locator(".spot-stat").all_inner_texts()
    assert "Supports Rodman's Hollow" in support_stats
    assert "Supports Clay Head Trail" in support_stats
    assert errors == []
