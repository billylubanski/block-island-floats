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
    yield
    app_module.weather_cache["data"] = None
    app_module.weather_cache["timestamp"] = None


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


def test_index_route_renders_dashboard_controls(sample_db: Path, capture_templates):
    with app_module.app.test_client() as client:
        response = client.get("/?year=2025")

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert 'class="utility-rail"' in text
    assert 'id="map-loading"' in text
    assert "<div id=\"map\"" in text
    assert "L.map('map')" in text
    assert "spinner.style.display = 'none'" in text
    assert "Year focus" in text
    assert "Floats still unreported" in text
    assert "Read the island before you head out" in text

    _, context = capture_templates[-1]
    assert context["selected_year"] == "2025"
    assert context["still_out_there"] == 1
    assert context["total_finds"] == 2


def test_about_route_renders_project_copy():
    with app_module.app.test_client() as client:
        response = client.get("/about")

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "Built for hunters who like evidence before mileage" in text
    assert "What this app is tracking" in text
    assert "How the experience is organized" in text


def test_forecast_route_renders_predictions_and_location_detail(
    sample_db: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    predictions = [
        {"location": "Rodman's Hollow", "probability": 88.5},
        {"location": "Clay Head Trail", "probability": 52.0},
    ]
    weather = {
        "temp": 68,
        "condition": "Partly Cloudy",
        "wind": 9,
        "emoji": "WEATHER",
        "timestamp": "09:30 AM",
    }

    monkeypatch.setattr(app_module, "predict_today", lambda: predictions)
    monkeypatch.setattr(app_module, "get_seasonality_score", lambda: 7.5)
    monkeypatch.setattr(app_module, "get_weather_data", lambda: weather)
    encoded_location = quote("Rodman's Hollow", safe="")

    with app_module.app.test_client() as client:
        response = client.get("/forecast")
        location_response = client.get(f"/location/{encoded_location}")

    assert response.status_code == 200
    assert location_response.status_code == 200

    text = response.get_data(as_text=True)
    assert "Float forecast" in text
    assert "How alive the month looks" in text
    assert "Top predicted locations" in text
    assert "Rodman&#39;s Hollow" in text
    assert "88.5%" in text
    assert "Partly Cloudy" in text
    assert "9 mph" in text


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
