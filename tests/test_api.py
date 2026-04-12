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


def test_index_route_renders_dashboard_controls(
    sample_db: Path,
    capture_templates,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(app_module, "build_daily_forecast_briefing", lambda target_date=None: sample_forecast_briefing())

    with app_module.app.test_client() as client:
        response = client.get("/?year=2025")

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert 'class="dashboard-filter-panel__summary"' in text
    assert 'id="map-loading"' in text
    assert "<div id=\"map\"" in text
    assert 'id="dashboard-map-data"' in text
    assert '/static/dashboard-map.js' in text
    assert "Compare hotspots" in text
    assert "Hide menus" in text
    assert "Hide controls" in text
    assert "Show hotspots" in text
    assert "Reset map" in text
    assert 'aria-label="Open menu"' in text
    assert ">Open menu<" in text
    assert "Season focus" in text
    assert "Floats still unreported" in text
    assert "Start here now" in text
    assert "Begin at Rodman&#39;s Hollow" in text
    assert "See why it leads" in text
    assert "Plan your Block Island glass float hunt with real find history" in text
    assert 'name="description"' in text

    _, context = capture_templates[-1]
    assert context["selected_year"] == "2025"
    assert context["still_out_there"] == 1
    assert context["total_finds"] == 2
    assert context["dashboard_map"]["cluster_count"] >= 1
    assert context["lead_zone"]["label"] == "Rodman's Hollow"


def test_about_route_renders_project_copy():
    with app_module.app.test_client() as client:
        response = client.get("/about")

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "Use public float reports to choose a stronger starting point" in text
    assert "Use this for planning, not as an official hiding map" in text
    assert "A few rules shape the whole season" in text
    assert "Useful pages before and after the hunt" in text
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
    assert "Find the best spots near you" in text
    assert "Hunt rules" in text
    assert "Register your float so the official archive can attach your find" in text
    assert "Greenway trail guide" in text
    assert "Best bet right now" in text
    assert "Closest worthwhile stops" in text
    assert "Open every mapped location" in text
    assert 'role="status"' in text
    assert 'aria-live="polite"' in text
    assert 'href="#main-content"' in text
    assert 'id="main-content"' in text
    assert 'data-apple-maps-link hidden' in text
    assert app_module.OFFICIAL_LINKS["register"] in text
    assert f'href="{app_module.OFFICIAL_LINKS["project"]}"' not in text


def test_field_route_renders_focused_share_handoff(
    sample_db: Path,
    monkeypatch: pytest.MonkeyPatch,
    capture_templates,
):
    monkeypatch.setattr(app_module, "get_weather_data", lambda: None)
    monkeypatch.setattr(app_module, "build_daily_forecast_briefing", lambda target_date=None: sample_forecast_briefing())
    encoded_location = quote("Rodman's Hollow", safe="")

    with app_module.app.test_client() as client:
        response = client.get(f"/field?focus={encoded_location}")

    assert response.status_code == 200

    _, context = capture_templates[-1]
    assert context["focused_route"]["name"] == "Rodman's Hollow"
    assert context["focused_route"]["backup_stops"][0]["name"] == "Clay Head Trail"
    assert context["focused_route"]["summary"].startswith("Shared from a location page.")
    assert context["priority_tiers"]["best_bet"]["priority_label"] == "Shared route start"
    assert context["priority_tiers"]["best_bet"]["support_summary"] == "Keep Clay Head Trail ready as the next stop if the first pass comes up quiet."


def test_field_route_renders_fallback_guidance_payload(sample_db: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(app_module, "get_weather_data", lambda: None)
    monkeypatch.setattr(app_module, "build_daily_forecast_briefing", lambda target_date=None: sample_forecast_briefing())
    monkeypatch.setattr(app_module, "FIELD_ETIQUETTE", copy.deepcopy(app_module.DEFAULT_FIELD_ETIQUETTE))

    with app_module.app.test_client() as client:
        response = client.get("/field")

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "Hunt rules" in text
    assert "Leave no trace" in text
    assert "Register floats" in text
    assert "Full directory" in text


def test_field_route_limits_initial_directory_batch_for_large_sets(
    sample_db: Path,
    monkeypatch: pytest.MonkeyPatch,
    capture_templates,
):
    monkeypatch.setattr(app_module, "get_weather_data", lambda: None)
    monkeypatch.setattr(app_module, "build_daily_forecast_briefing", lambda target_date=None: sample_forecast_briefing())
    large_counts = {
        name: index + 1
        for index, name in enumerate(list(app_module.LOCATIONS.keys())[:15])
    }
    monkeypatch.setattr(app_module, "get_location_counts", lambda year_param=None: app_module.Counter(large_counts))

    with app_module.app.test_client() as client:
        response = client.get("/field")

    assert response.status_code == 200
    _, context = capture_templates[-1]
    assert context["directory_state"]["initial_visible_count"] == app_module.FIELD_DIRECTORY_BATCH_SIZE
    assert context["directory_state"]["remaining_count"] == 3

    text = response.get_data(as_text=True)
    assert "Showing 12 of 15 mapped locations." in text
    assert "Show 3 more locations" in text


def test_field_priority_tiers_keep_support_card_destinations_attached_to_each_spot():
    hunting_spots = [
        {
            "name": "Enchanted Forest",
            "count": 12,
            "lat": 41.1701,
            "lon": -71.5701,
            "location_href": "/location/Enchanted%20Forest",
        },
        {
            "name": "Nathan Mott Park",
            "count": 9,
            "lat": 41.1802,
            "lon": -71.5802,
            "location_href": "/location/Nathan%20Mott%20Park",
        },
        {
            "name": "Martin's Lane/Trail",
            "count": 7,
            "lat": 41.1903,
            "lon": -71.5903,
            "location_href": "/location/Martin%27s%20Lane%2FTrail",
        },
        {
            "name": "Cooneymus Beach",
            "count": 5,
            "lat": 41.1604,
            "lon": -71.5604,
            "location_href": "/location/Cooneymus%20Beach",
        },
    ]
    briefing = {
        "zones": [
            {
                "label": "Enchanted Forest",
                "location_href": "/location/Enchanted%20Forest",
                "signal_label": "Best signal",
                "primary_spot": "Enchanted Forest",
                "supporting_spots": [
                    {"name": "Enchanted Forest"},
                    {"name": "Nathan Mott Park"},
                    {"name": "Martin's Lane/Trail"},
                ],
                "reason_texts": ["Recent reports support this zone."],
                "reason_tags": ["Recent finds nearby"],
            }
        ]
    }

    with app_module.app.test_request_context("/field"):
        priority_tiers = app_module.build_field_priority_tiers(hunting_spots, briefing)

    worthwhile = {spot["name"]: spot for spot in priority_tiers["closest_worthwhile"]}

    assert worthwhile["Nathan Mott Park"]["location_href"] == "/location/Nathan%20Mott%20Park"
    assert worthwhile["Nathan Mott Park"]["lat"] == pytest.approx(41.1802)
    assert worthwhile["Nathan Mott Park"]["lon"] == pytest.approx(-71.5802)
    assert worthwhile["Nathan Mott Park"]["priority_reason"].startswith("Recent finds nearby also points toward Nathan Mott Park")

    assert worthwhile["Martin's Lane/Trail"]["location_href"] == "/location/Martin%27s%20Lane%2FTrail"
    assert worthwhile["Martin's Lane/Trail"]["lat"] == pytest.approx(41.1903)
    assert worthwhile["Martin's Lane/Trail"]["lon"] == pytest.approx(-71.5903)
    assert worthwhile["Martin's Lane/Trail"]["priority_reason"].startswith("Recent finds nearby also points toward Martin's Lane/Trail")
    assert worthwhile["Nathan Mott Park"]["location_href"] != briefing["zones"][0]["location_href"]
    assert worthwhile["Martin's Lane/Trail"]["location_href"] != briefing["zones"][0]["location_href"]

    assert app_module.build_field_reason_text("Cooneymus Beach", 5) == (
        "5 archived reports keep Cooneymus Beach on the shortlist even without forecast support."
    )


def test_search_route_includes_official_report_links(sample_db: Path):
    with app_module.app.test_client() as client:
        response = client.get("/search?q=Tester")

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert text.count("Showing up to 50 matching posts from public finder reports.") == 1
    assert "Open a location guide to see the full archive for that place beyond the search cap." in text
    assert text.count("Open location guide") == 2
    assert text.count("Open official report") == 3
    assert "Show 2 matching reports" in text
    assert "Latest dated post: <strong>Jul 10, 2025</strong>." in text
    assert "Register Floats" in text
    assert "https://example.com/find/2025-1" in text


def test_search_route_groups_normalized_location_matches(sample_db: Path, capture_templates):
    with app_module.app.test_client() as client:
        response = client.get("/search?q=Rodman's Hollow")

    assert response.status_code == 200
    _, context = capture_templates[-1]
    assert context["result_count"] == 2
    assert context["grouped_result_count"] == 1
    assert context["ungrouped_results"] == []
    assert context["grouped_results"][0]["location_name"] == "Rodman's Hollow"
    assert context["grouped_results"][0]["report_count"] == 2

    text = response.get_data(as_text=True)
    assert text.count("Open location guide") == 1
    assert text.count("Open official report") == 2
    assert "Show 2 matching reports" in text
    assert "The location guide opens the full archive for Rodman&#39;s Hollow" in text
    assert "reported this float on Jul 10, 2025." in text


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
    assert "Open location guide" in text
    assert "Open official report" not in text


def test_location_detail_renders_recent_find_official_report_links(sample_db: Path):
    encoded_location = quote("Rodman's Hollow", safe="")

    with app_module.app.test_client() as client:
        response = client.get(f"/location/{encoded_location}")

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "Open official report" in text
    assert 'class="gallery-item"' in text
    assert 'data-lightbox-index="' in text
    assert 'onclick="openLightbox' not in text
    assert 'role="dialog"' in text
    assert 'aria-modal="true"' in text
    assert app_module.OFFICIAL_LINKS["register"] in text
    assert "Newest posts first. This page keeps the full archive for Rodman&#39;s Hollow" in text
    assert "Latest recorded report: Jul 10, 2025." in text
    assert "Jul 10, 2025" in text
    assert "Latest recorded report: 2025-07-10." not in text
    assert "<td>2025-07-10</td>" not in text


def test_location_detail_builds_share_payload_and_meta(sample_db: Path, capture_templates):
    encoded_location = quote("Rodman's Hollow", safe="")

    with app_module.app.test_client() as client:
        response = client.get(f"/location/{encoded_location}")

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "Share this spot" in text
    assert "Copy outing card" in text
    assert "Mini route" in text
    assert "Google Maps" in text
    assert 'data-apple-maps-link hidden' in text
    assert 'property="og:description"' in text
    assert 'property="og:image:alt" content="Archive photo from Rodman&#39;s Hollow"' in text
    assert 'property="og:image" content="https://cdn.example.com/2025-1.jpg"' in text
    assert 'property="og:url"' in text
    assert 'rel="canonical" href="http://localhost/location/Rodman&#39;s%20Hollow"' in text

    _, context = capture_templates[-1]
    assert context["share_payload"] == {
        "title": "Rodman's Hollow outing card",
        "share_url": "http://localhost/location/Rodman's%20Hollow?ref=share",
        "share_text": (
            "Rodman's Hollow outing card: steady archive signal with 2 reported finds across 2 seasons. "
            "Latest dated report: Jul 10, 2025. Backup stop: Clay Head Trail."
        ),
        "copy_text": (
            "Rodman's Hollow outing card: steady archive signal with 2 reported finds across 2 seasons. "
            "Latest dated report: Jul 10, 2025. Backup stop: Clay Head Trail.\n"
            "http://localhost/location/Rodman's%20Hollow?ref=share\n"
            "Focused field view: http://localhost/field?focus=Rodman's+Hollow"
        ),
        "location_name": "Rodman's Hollow",
    }
    assert context["shared_ref"] is False
    assert context["page_meta"]["description"] == (
        "Rodman's Hollow outing card: steady archive signal with 2 reported finds across 2 seasons. "
        "Latest dated report: Jul 10, 2025. Backup stop: Clay Head Trail."
    )
    assert context["page_meta"]["image"] == "https://cdn.example.com/2025-1.jpg"
    assert context["page_meta"]["meta_title"] == "Rodman's Hollow outing card"
    assert context["page_meta"]["image_alt"] == "Archive photo from Rodman's Hollow"
    assert context["page_meta"]["url"] == "http://localhost/location/Rodman's%20Hollow"
    assert context["outing_card"]["badge_label"] == "Steady archive signal"
    assert context["outing_card"]["backup_stops"][0]["name"] == "Clay Head Trail"
    assert context["outing_card"]["field_href"] == "/field?focus=Rodman's+Hollow"
    assert context["outing_card"]["google_maps_href"] == "https://maps.google.com/?q=41.155,-71.585"
    assert context["outing_card"]["apple_maps_href"] == "maps://?ll=41.155,-71.585&q=Rodman%27s+Hollow"
    assert context["outing_card"]["backup_stops"][0]["google_maps_href"] == "https://maps.google.com/?q=41.2187,-71.5587"
    assert context["outing_card"]["backup_stops"][0]["apple_maps_href"] == "maps://?ll=41.2187,-71.5587&q=Clay+Head+Trail"


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
    assert "Where to start today" in text
    assert "Start with Rodman&#39;s Hollow" in text
    assert "Open location guide" in text
    assert "Where to go next if you want a backup" in text
    assert text.count("Use this as a starting suggestion, then confirm with access and conditions on the ground.") == 1
    assert "Why this stays a starting suggestion" in text
    assert "Rodman&#39;s Hollow" in text
    assert "7.2/10" in text
    assert "Partly Cloudy" in text
    assert "9 mph" in text
    assert "Wednesday, Jul 1, 2026" in text
    assert "Forecast updated: Jul 1, 2026 at 4:00 AM EDT" in text
    assert "Live weather updated: Jul 1, 2026 at 5:30 AM EDT" in text
    assert "Live tide updated: Jul 1, 2026 at 5:15 AM EDT" in text
    assert "Seasonal support is doing most of the work here." in text
    assert "9 dated reports across 2 seasons keep this area on the board." in text
    assert "2026-07-01T09:30:00Z" not in text
    assert "2026-07-01" not in text
    assert "Primary spine" not in text
    assert "% probability" not in text


def test_format_local_timestamp_handles_naive_and_aware_values():
    assert app_module.format_local_timestamp("2026-07-01T09:30:00Z") == "Jul 1, 2026 at 5:30 AM EDT"
    assert app_module.format_local_timestamp("2026-03-29T21:18:22.824388") == "Mar 29, 2026 at 9:18 PM EDT"
    assert app_module.format_local_timestamp("", missing="Unknown") == "Unknown"


def test_format_public_date_handles_dates_and_datetimes():
    assert app_module.format_public_date("2026-07-01") == "Jul 1, 2026"
    assert app_module.format_public_date("2026-07-01T09:30:00Z") == "Jul 1, 2026"
    assert app_module.format_public_date("", missing="Undated") == "Undated"


def test_forecast_route_handles_empty_predictions(sample_db: Path, monkeypatch: pytest.MonkeyPatch):
    briefing = sample_forecast_briefing()
    briefing["zones"] = []
    monkeypatch.setattr(app_module, "build_daily_forecast_briefing", lambda target_date=None: briefing)

    with app_module.app.test_client() as client:
        response = client.get("/forecast")

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "Where to start today" in text
    assert "No recommendation available" in text


def test_forecast_route_downgrades_headline_when_artifact_is_stale(
    sample_db: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    briefing = sample_forecast_briefing()
    briefing["feature_freshness"]["artifact_generated_at"] = "2026-03-24T21:37:00-04:00"
    monkeypatch.setattr(app_module, "build_daily_forecast_briefing", lambda target_date=None: briefing)
    monkeypatch.setattr(
        app_module,
        "get_current_time",
        lambda: datetime.datetime(2026, 4, 12, 12, 0, tzinfo=app_module.DISPLAY_TIMEZONE),
    )

    with app_module.app.test_client() as client:
        response = client.get("/forecast")

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "Latest model guidance for today" in text
    assert "Latest model points to Rodman&#39;s Hollow" in text
    assert "Starting suggestion from the latest forecast artifact" in text
    assert "Model artifact age: 2 weeks" in text
    assert "Treat the ranked area as advisory because the model artifact is older than the live weather and tide." in text
    assert "the ranking model was generated on Mar 24, 2026 at 9:37 PM EDT and is about 2 weeks old." in text
    assert "History + live conditions" not in text


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
    assert "Where to start today" in text
    assert "No recommendation available" in text


def test_get_weather_data_converts_noaa_response(monkeypatch: pytest.MonkeyPatch):
    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "properties": {
                    "temperature": {"value": 20},
                    "windSpeed": {"unitCode": "wmoUnit:km_h-1", "value": 38.88},
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
    assert weather["wind"] == 24
    assert weather["condition"] == "Partly Cloudy"
    assert weather["emoji"]
    assert weather["timestamp"]


def test_get_weather_context_falls_back_when_live_context_has_no_display_values(monkeypatch: pytest.MonkeyPatch):
    fallback_weather = {
        "temp": 68,
        "condition": "Partly Cloudy",
        "wind": 9,
        "emoji": "WEATHER",
        "timestamp": "09:30 AM",
    }

    monkeypatch.setattr(
        app_module,
        "fetch_live_weather_context",
        lambda **kwargs: {
            "temp": None,
            "condition": "Unknown",
            "wind": None,
            "summary": "",
            "updated_at": "2026-07-01T09:30:00Z",
        },
    )
    monkeypatch.setattr(app_module, "get_weather_data", lambda: fallback_weather)

    weather = app_module.get_weather_context()

    assert weather == fallback_weather


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
