import copy
import datetime
import sqlite3
from pathlib import Path
from urllib.parse import quote

import analyzer
import app as app_module
import pytest
from flask import template_rendered


def create_finds_db(path: Path, *, include_image_url: bool = True) -> None:
    columns = [
        "id TEXT PRIMARY KEY",
        "year TEXT",
        "float_number TEXT",
        "finder TEXT",
        "location_raw TEXT",
        "location_normalized TEXT",
        "date_found TEXT",
        "url TEXT",
    ]
    if include_image_url:
        columns.append("image_url TEXT")

    conn = sqlite3.connect(path)
    conn.execute(f"CREATE TABLE finds ({', '.join(columns)})")
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


@pytest.fixture(autouse=True)
def clear_weather_cache():
    app_module.weather_cache["data"] = None
    app_module.weather_cache["timestamp"] = None
    app_module.tide_cache["data"] = None
    app_module.tide_cache["timestamp"] = None
    yield
    app_module.weather_cache["data"] = None
    app_module.weather_cache["timestamp"] = None
    app_module.tide_cache["data"] = None
    app_module.tide_cache["timestamp"] = None


@pytest.fixture(autouse=True)
def clear_forecast_artifact_cache():
    app_module.clear_forecast_cache()
    yield
    app_module.clear_forecast_cache()


@pytest.fixture
def capture_templates():
    recorded = []

    def record(sender, template, context, **extra):
        recorded.append((template, context))

    template_rendered.connect(record, app_module.app)
    try:
        yield recorded
    finally:
        template_rendered.disconnect(record, app_module.app)


@pytest.fixture
def sample_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "floats.db"
    create_finds_db(db_path)

    rows = [
        {
            "id": "2025-1",
            "year": "2025",
            "float_number": "1",
            "finder": "Tester",
            "location_raw": "rodman",
            "location_normalized": "Rodman's Hollow",
            "date_found": "2025-07-10",
            "url": "https://example.com/find/2025-1",
            "image_url": "https://cdn.example.com/2025-1.jpg",
        },
        {
            "id": "2025-3",
            "year": "2025",
            "float_number": "3",
            "finder": "Another Tester",
            "location_raw": "clayhead",
            "location_normalized": "Clay Head Trail",
            "date_found": "2025-07-15",
            "url": "https://example.com/find/2025-3",
            "image_url": "https://cdn.example.com/2025-3.jpg",
        },
        {
            "id": "2024-1",
            "year": "2024",
            "float_number": "1",
            "finder": "Tester",
            "location_raw": "rodman",
            "location_normalized": "Rodman's Hollow",
            "date_found": "2024-08-01",
            "url": "https://example.com/find/2024-1",
            "image_url": "https://cdn.example.com/2024-1.jpg",
        },
    ]
    for row in rows:
        insert_find(db_path, **row)

    monkeypatch.setattr(app_module, "DB_NAME", str(db_path))
    monkeypatch.setattr(analyzer, "DB_NAME", str(db_path))
    monkeypatch.setattr(app_module, "get_last_updated", lambda: "Test fixture")
    return db_path


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


def test_index_route_renders_dashboard_controls(sample_db: Path, capture_templates):
    with app_module.app.test_client() as client:
        response = client.get("/?year=2025")

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert 'class="utility-rail"' in text
    assert 'id="map-loading"' in text
    assert "<div id=\"map\"" in text
    assert 'id="dashboard-map-data"' in text
    assert '/static/dashboard-map.js' in text
    assert "Top mapped clusters" in text
    assert "Hide controls" in text
    assert "Show hotspots" in text
    assert "Reset" in text
    assert "Year focus" in text
    assert "Floats still unreported" in text
    assert "Read the island before you head out" in text

    _, context = capture_templates[-1]
    assert context["selected_year"] == "2025"
    assert context["still_out_there"] == 1
    assert context["total_finds"] == 2
    assert context["dashboard_map"]["cluster_count"] >= 1


def test_about_route_renders_project_copy():
    with app_module.app.test_client() as client:
        response = client.get("/about")

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "Use the tracker when location choice starts to matter" in text
    assert "Project background and mechanics" in text
    assert "Use each source for the right job" in text
    assert "Official links to keep open" in text
    assert "Open Greenway guide" in text
    assert "2011" in text
    assert "2023" not in text
    assert "2025" not in text


def test_healthcheck_route_returns_ok():
    with app_module.app.test_client() as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_favicon_route_returns_icon():
    with app_module.app.test_client() as client:
        response = client.get("/favicon.ico")

    assert response.status_code == 200
    assert response.mimetype == "image/png"


def test_field_route_renders_json_backed_official_guidance(sample_db: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(app_module, "get_weather_data", lambda: None)
    monkeypatch.setattr(app_module, "build_daily_forecast_briefing", lambda target_date=None: sample_forecast_briefing())

    with app_module.app.test_client() as client:
        response = client.get("/field")

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "Field reminders" in text
    assert "Register your float so the official archive can attach your find" in text
    assert "Greenway trail guide" in text
    assert app_module.OFFICIAL_LINKS["register"] in text


def test_field_route_renders_fallback_guidance_payload(sample_db: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(app_module, "get_weather_data", lambda: None)
    monkeypatch.setattr(app_module, "build_daily_forecast_briefing", lambda target_date=None: sample_forecast_briefing())
    monkeypatch.setattr(app_module, "FIELD_ETIQUETTE", copy.deepcopy(app_module.DEFAULT_FIELD_ETIQUETTE))

    with app_module.app.test_client() as client:
        response = client.get("/field")

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "Field reminders" in text
    assert "Leave no trace" in text
    assert "Register floats" in text


def test_search_route_includes_official_report_links(sample_db: Path):
    with app_module.app.test_client() as client:
        response = client.get("/search?q=Tester")

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert text.count("Showing up to 50 matches.") == 1
    assert "Open location detail" in text
    assert "Open official report" in text
    assert "Register Floats" in text
    assert "https://example.com/find/2025-1" in text


def test_search_route_hides_official_report_link_when_url_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "missing-url.db"
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
        url="",
        image_url="https://cdn.example.com/2025-1.jpg",
    )

    monkeypatch.setattr(app_module, "DB_NAME", str(db_path))

    with app_module.app.test_client() as client:
        response = client.get("/search?q=Tester")

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "Open location detail" in text
    assert "Open official report" not in text


def test_location_detail_renders_recent_find_official_report_links(sample_db: Path):
    encoded_location = quote("Rodman's Hollow", safe="")

    with app_module.app.test_client() as client:
        response = client.get(f"/location/{encoded_location}")

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "Open official report" in text
    assert app_module.OFFICIAL_LINKS["register"] in text
    assert "Open the original report below" in text


def test_location_detail_builds_share_payload_and_meta(sample_db: Path, capture_templates):
    encoded_location = quote("Rodman's Hollow", safe="")

    with app_module.app.test_client() as client:
        response = client.get(f"/location/{encoded_location}")

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "Share this spot" in text
    assert 'property="og:description"' in text
    assert 'property="og:image" content="https://cdn.example.com/2025-1.jpg"' in text
    assert 'property="og:url"' in text

    _, context = capture_templates[-1]
    assert context["share_payload"] == {
        "share_url": "http://localhost/location/Rodman's%20Hollow?ref=share",
        "share_text": "Rodman's Hollow has 2 reported finds across 2 seasons. Spot brief:",
        "location_name": "Rodman's Hollow",
    }
    assert context["shared_ref"] is False
    assert context["page_meta"]["description"] == (
        "Rodman's Hollow has 2 reported finds across 2 seasons. Spot brief: "
        "Latest dated report: 2025-07-10."
    )
    assert context["page_meta"]["image"] == "https://cdn.example.com/2025-1.jpg"
    assert context["page_meta"]["url"] == "http://localhost/location/Rodman's%20Hollow"


def test_location_detail_renders_shared_banner_for_share_ref(sample_db: Path, capture_templates):
    encoded_location = quote("Rodman's Hollow", safe="")

    with app_module.app.test_client() as client:
        response = client.get(f"/location/{encoded_location}?ref=share")

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "Shared by a hunting partner" in text

    _, context = capture_templates[-1]
    assert context["shared_ref"] is True


def test_api_events_route_persists_allowed_events_to_metrics_db(
    sample_db: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    metrics_path = tmp_path / "output" / "metrics.db"
    monkeypatch.setattr(app_module, "METRICS_DB_PATH", str(metrics_path))

    with app_module.app.test_client() as client:
        share_response = client.post(
            "/api/events",
            json={
                "event_name": "share_clicked",
                "location_name": "Rodman's Hollow",
                "share_method": "native",
            },
        )
        visit_response = client.post(
            "/api/events",
            json={
                "event_name": "shared_location_view",
                "location_name": "Rodman's Hollow",
            },
        )

    assert share_response.status_code == 204
    assert visit_response.status_code == 204
    assert metrics_path.exists()

    conn = sqlite3.connect(metrics_path)
    try:
        rows = conn.execute(
            "SELECT event_name, location_name, share_method FROM growth_events ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    assert rows == [
        ("share_clicked", "Rodman's Hollow", "native"),
        ("shared_location_view", "Rodman's Hollow", None),
    ]

    source_conn = sqlite3.connect(sample_db)
    try:
        source_tables = {
            row[0]
            for row in source_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    finally:
        source_conn.close()

    assert "growth_events" not in source_tables


def test_api_events_route_rejects_invalid_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    metrics_path = tmp_path / "output" / "metrics.db"
    monkeypatch.setattr(app_module, "METRICS_DB_PATH", str(metrics_path))

    with app_module.app.test_client() as client:
        response = client.post(
            "/api/events",
            json={
                "event_name": "share_clicked",
                "location_name": "Rodman's Hollow",
            },
        )

    assert response.status_code == 400
    assert response.get_json() == {"error": "invalid event payload"}
    assert not metrics_path.exists()


def test_forecast_route_renders_predictions_and_location_detail(
    sample_db: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    briefing = sample_forecast_briefing()
    monkeypatch.setattr(app_module, "build_daily_forecast_briefing", lambda target_date=None: briefing)
    encoded_location = quote("Rodman's Hollow", safe="")

    with app_module.app.test_client() as client:
        response = client.get("/forecast")
        location_response = client.get(f"/location/{encoded_location}")

    assert response.status_code == 200
    assert location_response.status_code == 200

    text = response.get_data(as_text=True)
    assert "Forecast briefing" in text
    assert "Top zones for a first loop" in text
    assert text.count("Directional only.") == 1
    assert "Why confidence stays bounded" in text
    assert "Rodman&#39;s Hollow" in text
    assert "7.2/10" in text
    assert "Partly Cloudy" in text
    assert "9 mph" in text
    assert "% probability" not in text


def test_forecast_route_handles_empty_predictions(sample_db: Path, monkeypatch: pytest.MonkeyPatch):
    briefing = sample_forecast_briefing()
    briefing["zones"] = []
    monkeypatch.setattr(app_module, "build_daily_forecast_briefing", lambda target_date=None: briefing)

    with app_module.app.test_client() as client:
        response = client.get("/forecast")

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "Forecast briefing" in text
    assert "No zones available" in text


def test_forecast_helpers_read_generated_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    forecast_path = tmp_path / "forecast_artifact.json"
    artifact = {
        "version": 2,
        "generated_at": "2026-03-21T00:00:00Z",
        "source": {
            "total_records": 10,
            "latest_source_date": "2026-01-11",
            "training_rows": 10,
            "cluster_training_rows": 10,
            "actual_years": [2025, 2026],
        },
        "seasonality_by_month": {str(month): float(month) for month in range(1, 13)},
        "activity_index_by_day": {str(day): 0.0 for day in range(1, 367)},
        "cluster_profiles": {
            "Rodman's Hollow": {
                "label": "Rodman's Hollow",
                "lat": 41.155,
                "lon": -71.585,
                "tags": ["trail"],
                "support_count": 10,
                "dated_support_count": 6,
                "actual_years": [2025, 2026],
                "supporting_spots": [{"name": "Rodman's Hollow", "count": 10}],
                "best_months": ["July"],
                "feature_coverage": {"calendar_rows": 6, "historical_weather_rows": 0, "tide_rows": 0, "recency_rows": 6},
                "calendar_affinity": {},
            }
        },
        "seasonal_priors_by_day": {str(day): {} for day in range(1, 367)},
        "evaluation": {
            "targets": {"exact_location": {}, "cluster": {"kernel_seasonal": {"top3_accuracy": 0.14, "log_loss": 1.2}}},
            "selection": {"primary_model": "kernel_seasonal", "gating_reason": "Kernel remains primary.", "eligible_models": ["kernel_seasonal"]},
        },
        "feature_sources": {
            "calendar": {"available": True},
            "recency": {"available": True},
            "historical_weather": {"available": False},
            "live_weather": {"available": True},
            "tide": {"available": True},
        },
    }
    artifact["activity_index_by_day"]["182"] = 6.4
    artifact["seasonal_priors_by_day"]["182"] = {"Rodman's Hollow": 1.0}
    forecast_path.write_text(app_module.json.dumps(artifact), encoding="utf-8")

    monkeypatch.setattr(app_module, "FORECAST_ARTIFACT_PATH", str(forecast_path))
    monkeypatch.setattr(app_module, "DB_NAME", str(tmp_path / "missing.db"))
    monkeypatch.setattr(app_module, "get_today", lambda: datetime.date(2026, 7, 1))
    monkeypatch.setattr(app_module, "get_weather_context", lambda: None)
    monkeypatch.setattr(app_module, "get_tide_context", lambda: None)

    with app_module.app.test_request_context("/forecast"):
        briefing = app_module.build_daily_forecast_briefing()

    assert briefing["zones"][0]["label"] == "Rodman's Hollow"
    assert briefing["activity_score"] == 6.4
    assert app_module.get_seasonality_score() == 6.4


def test_forecast_route_handles_invalid_forecast_artifact(
    sample_db: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    forecast_path = tmp_path / "forecast_artifact.json"
    forecast_path.write_text("{not-json", encoding="utf-8")

    monkeypatch.setattr(app_module, "FORECAST_ARTIFACT_PATH", str(forecast_path))
    monkeypatch.setattr(app_module, "get_today", lambda: datetime.date(2026, 7, 1))
    monkeypatch.setattr(app_module, "get_weather_context", lambda: None)
    monkeypatch.setattr(app_module, "get_tide_context", lambda: None)

    with app_module.app.test_client() as client:
        response = client.get("/forecast")

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "Forecast briefing" in text
    assert "No zones available" in text


def test_get_weather_data_converts_noaa_response(monkeypatch: pytest.MonkeyPatch):
    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "properties": {
                    "temperature": {"value": 20},
                    "windSpeed": {"value": 4.0},
                    "textDescription": "Partly Cloudy",
                }
            }

    captured = {}

    def fake_get(url, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(app_module.requests, "get", fake_get)

    weather = app_module.get_weather_data()

    assert captured["url"].endswith("/stations/KBID/observations/latest")
    assert captured["headers"]["Accept"] == "application/geo+json"
    assert captured["timeout"] == 5
    assert weather["temp"] == 68
    assert weather["wind"] == 9
    assert weather["condition"] == "Partly Cloudy"
    assert weather["emoji"]
    assert weather["timestamp"]


def test_get_weather_data_uses_cache(monkeypatch: pytest.MonkeyPatch):
    calls = {"count": 0}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "properties": {
                    "temperature": {"value": 18},
                    "windSpeed": {"value": 2.0},
                    "textDescription": "Clear",
                }
            }

    def fake_get(url, headers, timeout):
        calls["count"] += 1
        return FakeResponse()

    monkeypatch.setattr(app_module.requests, "get", fake_get)

    first = app_module.get_weather_data()
    second = app_module.get_weather_data()

    assert calls["count"] == 1
    assert second == first
