import json
import sqlite3
from pathlib import Path

import pytest

from scripts.refresh_data import (
    AUDIT_PATH,
    CANONICAL_KEYS,
    MANIFEST_PATH,
    PoliteSession,
    SourceAccessDeniedError,
    SITEMAP_STATE_KEYS,
    build_manifest,
    build_cleanup_report,
    build_manual_review_queue,
    merge_duplicate_records,
    canonicalize_date,
    discover_year_filters,
    discover_year_filters_from_html,
    exclude_extreme_float_number_records,
    extract_record_id_from_url,
    extract_date_from_detail_html,
    is_access_denied_html,
    normalize_record,
    parse_listing_page,
    parse_detail_record_from_html,
    parse_detail_record_result_from_html,
    parse_robots_policy,
    parse_sitemap_xml,
    parse_title,
    rebuild_database,
    scrape_records,
    select_sitemap_fetch_ids,
    apply_sitemap_updates,
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


def sample_forecast_artifact(*, total_records: int = 2, latest_source_date: str = "2026-06-12") -> dict[str, object]:
    return {
        "version": 2,
        "generated_at": "2026-03-21T00:00:00Z",
        "source": {
            "total_records": total_records,
            "latest_source_date": latest_source_date,
            "training_rows": 2,
            "cluster_training_rows": 2,
            "actual_years": [2025, 2026],
        },
        "seasonality_by_month": {str(month): 0 for month in range(1, 13)},
        "activity_index_by_day": {str(day): 0 for day in range(1, 367)},
        "cluster_profiles": {
            "Rodman's Hollow": {
                "label": "Rodman's Hollow",
                "lat": 41.155,
                "lon": -71.585,
                "tags": ["trail"],
                "support_count": 2,
                "dated_support_count": 2,
                "actual_years": [2025, 2026],
                "primary_spot": "Rodman's Hollow",
                "supporting_spots": [{"name": "Rodman's Hollow", "count": 2}],
                "best_months": ["June"],
                "feature_coverage": {"calendar_rows": 2, "historical_weather_rows": 0, "tide_rows": 0, "recency_rows": 2},
                "calendar_affinity": {},
            }
        },
        "seasonal_priors_by_day": {str(day): {} for day in range(1, 367)},
        "evaluation": {
            "targets": {
                "exact_location": {},
                "cluster": {"kernel_seasonal": {"top1_accuracy": 0.1, "top3_accuracy": 0.2, "log_loss": 1.1, "calibration_gap": 0.05}},
            },
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


def sample_sitemap_state(records: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {
        record["id"]: {
            "url": record["url"],
            "sitemap_lastmod": "2026-03-24T02:45:48Z",
            "first_seen_at": "2026-03-24T02:45:48Z",
            "last_seen_at": "2026-03-24T02:45:48Z",
            "last_fetched_at": "2026-03-24T02:45:48Z",
            "fetch_status": "ok",
        }
        for record in records
    }


def test_discover_year_filters_from_html():
    filters = discover_year_filters_from_html(load_fixture("found_floats_page.html"))
    assert filters == {"2026": "31", "2025": "24"}


def test_discover_year_filters_from_script_payload():
    html = """
    <script>
    var yearFilters = [{"label":"2024","value":"23"},{"label":"2025","value":"24"}];
    </script>
    """
    filters = discover_year_filters_from_html(html)
    assert filters == {"2025": "24", "2024": "23"}


def test_is_access_denied_html_detects_edgesuite_block_page():
    html = """
    <html><body>
    <h1>Access Denied</h1>
    <p>You don't have permission to access "http://www.blockislandinfo.com/" on this server.</p>
    <p>Reference #18.deadbeef</p>
    <a href="https://errors.edgesuite.net/18.deadbeef">details</a>
    </body></html>
    """
    assert is_access_denied_html(html) is True


def test_discover_year_filters_rejects_access_denied_html():
    blocked_html = """
    <html><body>
    <h1>Access Denied</h1>
    <p>You don't have permission to access "http://www.blockislandinfo.com/" on this server.</p>
    <p>Reference #18.deadbeef</p>
    </body></html>
    """

    with pytest.raises(SourceAccessDeniedError):
        discover_year_filters(None, page_html=blocked_html)


def test_parse_listing_page_extracts_records_and_next_skip():
    records, next_skip = parse_listing_page(load_fixture("found_floats_page.html"), "2026")
    assert [record["id"] for record in records] == ["6001", "6000"]
    assert records[0]["url"].endswith("/event/321-alex-p/6001/")
    assert next_skip == 24


def test_scrape_records_refuses_cached_fallback_when_year_goes_empty(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("scripts.refresh_data.discover_year_filters", lambda session: {"2025": "24"})
    monkeypatch.setattr("scripts.refresh_data.scrape_year_records", lambda session, year, category_id: [])

    with pytest.raises(RuntimeError, match="refusing cached fallback"):
        scrape_records(object(), cached_by_year={"2025": sample_records()})


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("267 - B. Massoia", ("267", "B. Massoia")),
        ("245 Amy K.", ("245", "Amy K.")),
        ("305", ("305", "")),
        ("#253, Laura Pepper", ("253", "Laura Pepper")),
        ("#67-Denise Souza", ("67", "Denise Souza")),
        ("Number 355, Austin Powell", ("355", "Austin Powell")),
        ("Gabrielle #170", ("170", "Gabrielle")),
        ("207/Chris Abate", ("207", "Chris Abate")),
        ("Finder Only", ("", "Finder Only")),
    ],
)
def test_parse_title(title, expected):
    assert parse_title(title) == expected


def test_extract_date_rejects_placeholder_and_parses_valid_date():
    assert extract_date_from_detail_html(load_fixture("event_detail_jsonld.html")) == "2026-06-12"
    assert extract_date_from_detail_html(load_fixture("event_detail_placeholder.html")) == ""
    assert canonicalize_date("2026-01-01T00:00:00-04:00") == ""


def test_parse_sitemap_xml_extracts_event_urls_and_lastmod():
    entries = parse_sitemap_xml(load_fixture("sitemap.xml"))
    assert list(entries) == ["5741", "3633"]
    assert entries["5741"]["url"].endswith("/5741/")
    assert entries["5741"]["sitemap_lastmod"] == "2026-03-24T02:45:48Z"


def test_parse_detail_record_uses_embedded_category_year():
    record = parse_detail_record_from_html(
        load_fixture("event_detail_embedded_data.html"),
        "https://www.blockislandinfo.com/event/138-k-frost/5741/",
    )
    assert record == {
        "id": "5741",
        "year": "2025",
        "title": "138 K Frost",
        "url": "https://www.blockislandinfo.com/event/138-k-frost/5741/",
        "image": "https://cdn.example.com/5741.jpg",
        "location": "Behind stone wall near Ballards",
        "date_found": "2026-03-12",
    }


def test_parse_detail_record_normalizes_implausible_future_category_year():
    html = load_fixture("event_detail_embedded_data.html").replace('"catName":"2025"', '"catName":"2028"')
    result = parse_detail_record_result_from_html(
        html,
        "https://www.blockislandinfo.com/event/138-k-frost/5741/",
    )

    assert result["record"]["year"] == "2026"
    assert result["warning"] == "implausible_season_year"
    assert result["rejection_reason"] == ""


def test_parse_detail_record_rejects_non_float_event_without_year_category():
    html = """
    <html>
      <head>
        <title>The Glass Float Project | Block Island</title>
        <script>
          var data = {
            "recid": "7",
            "title": "The Glass Float Project",
            "location": "Block Island",
            "image": "https://cdn.example.com/project.jpg",
            "categories": []
          };
        </script>
        <script type="application/ld+json">
          {"@context":"https://schema.org","@type":"Event","name":"The Glass Float Project","startDate":"2026-03-24","location":{"name":"Block Island"}}
        </script>
      </head>
      <body></body>
    </html>
    """
    result = parse_detail_record_result_from_html(
        html,
        "https://www.blockislandinfo.com/event/the-glass-float-project/7/",
    )

    assert result == {
        "record": None,
        "rejection_reason": "non_float_event",
        "warning": "",
    }


def test_parse_detail_record_falls_back_to_description_for_location():
    html = """
    <html>
      <head>
        <script>
          var data = {
            "recid": "6009",
            "title": "153",
            "description": "<p>Side of the outdoor bar at Captain Nicks in the gravel (off season)</p>",
            "categories": [{"catName":"2025"}]
          };
          var dates = "2025-07-10";
        </script>
      </head>
      <body></body>
    </html>
    """

    record = parse_detail_record_from_html(
        html,
        "https://www.blockislandinfo.com/event/153/6009/",
    )

    assert record == {
        "id": "6009",
        "year": "2025",
        "title": "153",
        "url": "https://www.blockislandinfo.com/event/153/6009/",
        "image": "",
        "location": "Side of the outdoor bar at Captain Nicks in the gravel (off season)",
        "date_found": "2025-07-10",
    }


def test_parse_detail_record_decodes_html_entities_in_title_and_location():
    html = """
    <html>
      <head>
        <script>
          var data = {
            "recid": "5693",
            "title": "403&#8211; Charlotte Jacobson (10 y.o.)",
            "location": "Tom &amp; Huck's path",
            "image": "https://cdn.example.com/5693.jpg",
            "categories": [{"catName":"2025"}]
          };
          var dates = "2025-10-22";
        </script>
      </head>
      <body></body>
    </html>
    """

    record = parse_detail_record_from_html(
        html,
        "https://www.blockislandinfo.com/event/403%26%238211%3b-charlotte-jacobson-(10-y-o-)/5693/",
    )

    assert record == {
        "id": "5693",
        "year": "2025",
        "title": "403– Charlotte Jacobson (10 y.o.)",
        "url": "https://www.blockislandinfo.com/event/403%26%238211%3b-charlotte-jacobson-(10-y-o-)/5693/",
        "image": "https://cdn.example.com/5693.jpg",
        "location": "Tom & Huck's path",
        "date_found": "2025-10-22",
    }


def test_parse_robots_policy_reads_crawl_delay_and_disallow_rules():
    policy = parse_robots_policy("User-agent: *\nDisallow: /plugins/\nAllow: /\nCrawl-delay: 5\n")
    assert policy["crawl_delay_seconds"] == 5.0
    assert policy["parser"].can_fetch("*", "https://www.blockislandinfo.com/sitemap.xml") is True
    assert policy["parser"].can_fetch("*", "https://www.blockislandinfo.com/plugins/crm/count/") is False


def test_polite_session_retries_429_with_retry_after(monkeypatch: pytest.MonkeyPatch):
    class FakeResponse:
        def __init__(self, status_code: int, text: str = "", headers: dict[str, str] | None = None):
            self.status_code = status_code
            self.text = text
            self.headers = headers or {}

    class FakeSession:
        def __init__(self, responses: list[FakeResponse]):
            self.responses = responses
            self.calls = 0

        def get(self, url: str, timeout: int = 30) -> FakeResponse:
            response = self.responses[self.calls]
            self.calls += 1
            return response

    sleep_calls: list[float] = []
    monkeypatch.setattr("scripts.refresh_data.time.sleep", lambda seconds: sleep_calls.append(seconds))

    fetcher = PoliteSession(
        FakeSession(
            [
                FakeResponse(429, headers={"Retry-After": "7"}),
                FakeResponse(200, text="<html>ok</html>"),
            ]
        ),
        min_delay_seconds=0.0,
        max_retries=2,
    )

    response = fetcher.get("https://example.com/test", context="https://example.com/test")
    assert response.status_code == 200
    assert sleep_calls == [7.0]


def test_build_manifest_counts_records():
    manifest = build_manifest(sample_records())
    assert manifest["total_records"] == 2
    assert manifest["latest_source_date"] == "2026-06-12"
    assert manifest["records_by_year"] == {"2026": 1, "2025": 1}
    assert manifest["missing_dates"] == 1
    assert manifest["missing_images"] == 1


def test_build_manifest_includes_source_discovery():
    manifest = build_manifest(
        sample_records(),
        source_discovery={
            "refresh_scope": "full",
            "sitemap_urls_seen": 10,
            "detail_pages_fetched": 2,
            "reused_rows": 8,
            "new_ids": 1,
            "changed_ids": 1,
            "backfilled_ids": 1,
            "forced_refetch_ids": 6,
            "anomaly_counts": {"detail_404": 1},
        },
    )
    assert manifest["source_discovery"]["refresh_scope"] == "full"
    assert manifest["source_discovery"]["sitemap_urls_seen"] == 10
    assert manifest["source_discovery"]["forced_refetch_ids"] == 6
    assert manifest["source_discovery"]["anomaly_counts"] == {"detail_404": 1}


def test_build_cleanup_report_counts_placeholder_images_and_manual_review_rows():
    records = sample_records() + [
        {
            "id": "6002",
            "year": "2025",
            "title": "305",
            "url": "https://example.com/6002",
            "image": "https://assets.simpleviewinc.com/simpleview/image/upload/c_fill,h_250,q_75,w_300/v1/clients/blockislandri/default_image_2__test.jpg",
            "location": "",
            "date_found": "",
        }
    ]
    validation_report = {
        "summary": {"invalid_rows": 2, "suspicious_rows": 1},
        "flagged_records": [
            {
                "id": "6003",
                "year": 2025,
                "finder": "Kelly & Ross Colgan",
                "location_raw": "Rodman's Hollow",
                "url": "https://example.com/6003",
                "validation_errors": ["invalid_float_number"],
                "suspicious_flags": ["blank_float_with_hash_finder"],
            },
        ],
    }

    report = build_cleanup_report(records, validation_report=validation_report)

    assert report["totals"]["blank_images"] == 1
    assert report["totals"]["placeholder_images"] == 1
    assert "effective_missing_images" not in report["totals"]
    assert report["totals"]["blank_locations"] == 1
    assert report["validation"]["top_bucketed_unknown_locations"] == []
    assert report["validation"]["unresolved_title_rows"][0]["id"] == "6003"


def test_build_manual_review_queue_groups_duplicate_candidates():
    validation_report = {
        "flagged_records": [
            {
                "id": "10",
                "year": 2025,
                "float_number": "55",
                "finder": "Alice",
                "location_raw": "Clayhead Trail",
                "location_normalized": "Clay Head Trail",
                "date_found": "2025-06-01",
                "url": "https://example.com/10",
                "validation_errors": [],
                "suspicious_flags": [],
            },
            {
                "id": "11",
                "year": 2025,
                "float_number": "",
                "finder": "No Number",
                "location_raw": "Ocean View",
                "location_normalized": "Ocean View Pavilion",
                "date_found": "2025-06-02",
                "url": "https://example.com/11",
                "validation_errors": ["invalid_float_number"],
                "suspicious_flags": [],
            },
            {
                "id": "12",
                "year": 2025,
                "float_number": "77",
                "finder": "Bob",
                "location_raw": "Rodman's Hollow",
                "location_normalized": "Rodman's Hollow",
                "date_found": "",
                "url": "https://example.com/12",
                "validation_errors": [],
                "suspicious_flags": ["duplicate_float_year_location"],
            },
            {
                "id": "13",
                "year": 2025,
                "float_number": "77",
                "finder": "Casey",
                "location_raw": "Rodman's Hollow trail",
                "location_normalized": "Rodman's Hollow",
                "date_found": "",
                "url": "https://example.com/13",
                "validation_errors": [],
                "suspicious_flags": ["duplicate_float_year_location"],
            },
        ]
    }

    queue = build_manual_review_queue(validation_report)

    assert queue["counts"] == {
        "unresolved_titles": 1,
        "duplicate_groups": 1,
    }
    assert queue["duplicate_groups"][0]["records"][0]["id"] == "12"
    assert queue["duplicate_groups"][0]["records"][1]["id"] == "13"


def test_merge_duplicate_records_keeps_best_representative_and_merges_fields():
    records = [
        normalize_record(
            {
                "id": "1039",
                "year": "2020",
                "title": "332 L. Mcguire",
                "url": "https://example.com/1039",
                "image": "",
                "location": "Behind a rock on ClayHead Trail",
                "date_found": "",
            }
        ),
        normalize_record(
            {
                "id": "3931",
                "year": "2020",
                "title": "#332",
                "url": "https://example.com/3931",
                "image": "https://cdn.example.com/3931.jpg",
                "location": "ClayHead Trail",
                "date_found": "2024-07-08",
            }
        ),
    ]

    merged_records, merge_report = merge_duplicate_records(records)

    assert len(merged_records) == 1
    assert merged_records[0]["id"] == "3931"
    assert merged_records[0]["title"] == "332 L. Mcguire"
    assert merged_records[0]["date_found"] == "2024-07-08"
    assert merge_report == [
        {
            "year": "2020",
            "float_number": "332",
            "location_normalized": "Clay Head Trail",
            "kept_id": "3931",
            "merged_ids": ["1039", "3931"],
        }
    ]


def test_rebuild_database_applies_finder_override(tmp_path: Path):
    db_path = tmp_path / "floats.db"
    records = [
        {
            "id": "4155",
            "year": "2024",
            "title": "No number Abigail",
            "url": "https://example.com/4155",
            "image": "https://cdn.example.com/4155.jpg",
            "location": "Nathan Mott Trail",
            "date_found": "2024-09-24",
        }
    ]

    rebuild_database(
        records,
        db_path,
        record_overrides={"4155": {"finder_override": "Abigail"}},
    )

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT float_number, finder FROM finds WHERE id = 4155").fetchone()
    conn.close()

    assert row == ("", "Abigail")


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


def test_select_sitemap_fetch_ids_uses_new_changed_and_capped_backfill():
    existing_by_id = {
        "5": normalize_record(
            {
                "id": "5",
                "year": "2025",
                "title": "5 Finder",
                "url": "https://example.com/5",
                "image": "",
                "location": "Loc 5",
                "date_found": "",
            }
        ),
        "4": normalize_record(
            {
                "id": "4",
                "year": "2025",
                "title": "4 Finder",
                "url": "https://example.com/4",
                "image": "",
                "location": "Loc 4",
                "date_found": "",
            }
        ),
        "3": normalize_record(
            {
                "id": "3",
                "year": "2025",
                "title": "3 Finder",
                "url": "https://example.com/3",
                "image": "",
                "location": "Loc 3",
                "date_found": "",
            }
        ),
        "2": normalize_record(
            {
                "id": "2",
                "year": "2025",
                "title": "2 Finder",
                "url": "https://example.com/2",
                "image": "https://cdn.example.com/2.jpg",
                "location": "Loc 2",
                "date_found": "2025-06-02",
            }
        ),
        "1": normalize_record(
            {
                "id": "1",
                "year": "2025",
                "title": "1 Finder",
                "url": "https://example.com/1",
                "image": "https://cdn.example.com/1.jpg",
                "location": "Loc 1",
                "date_found": "2025-06-01",
            }
        ),
    }
    sitemap_entries = {
        "6": {"url": "https://example.com/6", "sitemap_lastmod": "2026-03-25T00:00:00Z"},
        "5": {"url": "https://example.com/5", "sitemap_lastmod": "2026-03-24T00:00:00Z"},
        "4": {"url": "https://example.com/4", "sitemap_lastmod": "2026-03-24T00:00:00Z"},
        "3": {"url": "https://example.com/3", "sitemap_lastmod": "2026-03-24T00:00:00Z"},
        "2": {"url": "https://example.com/2", "sitemap_lastmod": "2026-03-24T00:00:00Z"},
        "1": {"url": "https://example.com/1", "sitemap_lastmod": "2026-03-24T00:00:00Z"},
    }
    previous_state = {
        "5": {"url": "https://example.com/5", "sitemap_lastmod": "2026-03-24T00:00:00Z"},
        "4": {"url": "https://example.com/4", "sitemap_lastmod": "2026-03-24T00:00:00Z"},
        "3": {"url": "https://example.com/3", "sitemap_lastmod": "2026-03-24T00:00:00Z"},
        "2": {"url": "https://example.com/2", "sitemap_lastmod": "2026-03-20T00:00:00Z"},
        "1": {"url": "https://example.com/1", "sitemap_lastmod": "2026-03-24T00:00:00Z"},
    }

    scheduling = select_sitemap_fetch_ids(
        sitemap_entries,
        existing_by_id,
        previous_state,
        backfill_batch_size=2,
    )

    assert scheduling == {
        "fetch_ids": ["6", "2", "5", "4"],
        "new_ids": ["6"],
        "changed_ids": ["2"],
        "backfill_ids": ["5", "4"],
        "forced_refetch_ids": [],
    }


def test_select_sitemap_fetch_ids_treats_bootstrap_state_as_cached():
    existing_by_id = {
        "1": normalize_record(
            {
                "id": "1",
                "year": "2025",
                "title": "1 Finder",
                "url": "https://example.com/1",
                "image": "https://cdn.example.com/1.jpg",
                "location": "Loc 1",
                "date_found": "2025-06-01",
            }
        ),
    }
    sitemap_entries = {
        "1": {"url": "https://example.com/1", "sitemap_lastmod": "2026-03-24T00:00:00Z"},
    }
    previous_state = {
        "1": {
            "url": "https://example.com/1",
            "sitemap_lastmod": "",
            "first_seen_at": "2026-03-20T00:00:00Z",
            "last_seen_at": "2026-03-20T00:00:00Z",
            "last_fetched_at": "",
            "fetch_status": "bootstrap",
        }
    }

    scheduling = select_sitemap_fetch_ids(
        sitemap_entries,
        existing_by_id,
        previous_state,
        backfill_batch_size=2,
    )

    assert scheduling == {
        "fetch_ids": [],
        "new_ids": [],
        "changed_ids": [],
        "backfill_ids": [],
        "forced_refetch_ids": [],
    }


def test_select_sitemap_fetch_ids_rotates_backfill_to_oldest_unfetched_rows():
    existing_by_id = {
        record_id: normalize_record(
            {
                "id": record_id,
                "year": "2025",
                "title": f"{record_id} Finder",
                "url": f"https://example.com/{record_id}",
                "image": "",
                "location": "Loc",
                "date_found": "",
            }
        )
        for record_id in ("3", "2", "1")
    }
    sitemap_entries = {
        record_id: {"url": f"https://example.com/{record_id}", "sitemap_lastmod": "2026-03-24T00:00:00Z"}
        for record_id in ("3", "2", "1")
    }
    previous_state = {
        "3": {"url": "https://example.com/3", "sitemap_lastmod": "2026-03-24T00:00:00Z", "last_fetched_at": "2026-03-20T00:00:00Z"},
        "2": {"url": "https://example.com/2", "sitemap_lastmod": "2026-03-24T00:00:00Z", "last_fetched_at": ""},
        "1": {"url": "https://example.com/1", "sitemap_lastmod": "2026-03-24T00:00:00Z", "last_fetched_at": "2026-03-01T00:00:00Z"},
    }

    scheduling = select_sitemap_fetch_ids(
        sitemap_entries,
        existing_by_id,
        previous_state,
        backfill_batch_size=2,
    )

    assert scheduling["backfill_ids"] == ["2", "1"]
    assert scheduling["forced_refetch_ids"] == []


def test_select_sitemap_fetch_ids_full_refresh_fetches_all_records():
    existing_by_id = {
        "3": normalize_record(
            {
                "id": "3",
                "year": "2025",
                "title": "3 Finder",
                "url": "https://example.com/3",
                "image": "",
                "location": "Loc 3",
                "date_found": "",
            }
        ),
        "2": normalize_record(
            {
                "id": "2",
                "year": "2025",
                "title": "2 Finder",
                "url": "https://example.com/2",
                "image": "https://cdn.example.com/2.jpg",
                "location": "Loc 2",
                "date_found": "2025-06-02",
            }
        ),
        "1": normalize_record(
            {
                "id": "1",
                "year": "2025",
                "title": "1 Finder",
                "url": "https://example.com/1",
                "image": "https://cdn.example.com/1.jpg",
                "location": "Loc 1",
                "date_found": "2025-06-01",
            }
        ),
    }
    sitemap_entries = {
        "4": {"url": "https://example.com/4", "sitemap_lastmod": "2026-03-25T00:00:00Z"},
        "3": {"url": "https://example.com/3", "sitemap_lastmod": "2026-03-24T00:00:00Z"},
        "2": {"url": "https://example.com/2", "sitemap_lastmod": "2026-03-23T00:00:00Z"},
        "1": {"url": "https://example.com/1", "sitemap_lastmod": "2026-03-24T00:00:00Z"},
    }
    previous_state = {
        "3": {"url": "https://example.com/3", "sitemap_lastmod": "2026-03-24T00:00:00Z"},
        "2": {"url": "https://example.com/2", "sitemap_lastmod": "2026-03-20T00:00:00Z"},
        "1": {"url": "https://example.com/1", "sitemap_lastmod": "2026-03-24T00:00:00Z"},
    }

    scheduling = select_sitemap_fetch_ids(
        sitemap_entries,
        existing_by_id,
        previous_state,
        full_refresh=True,
    )

    assert scheduling == {
        "fetch_ids": ["4", "3", "2", "1"],
        "new_ids": ["4"],
        "changed_ids": ["2"],
        "backfill_ids": ["3"],
        "forced_refetch_ids": ["1"],
    }


def test_apply_sitemap_updates_keeps_existing_rows_on_404_and_tracks_missing_urls():
    existing_records = {
        "6000": normalize_record(sample_records()[1]),
    }
    sitemap_entries = {
        "6000": {
            "url": "https://www.blockislandinfo.com/event/120-kim-l/6000/",
            "sitemap_lastmod": "2026-03-24T00:00:00Z",
        },
        "5741": {
            "url": "https://www.blockislandinfo.com/event/138-k-frost/5741/",
            "sitemap_lastmod": "2026-03-24T02:45:48Z",
        },
    }

    def fake_fetch(url: str) -> dict[str, object]:
        if extract_record_id_from_url(url) == "6000":
            return {"status_code": 404, "body": ""}
        return {"status_code": 200, "body": load_fixture("event_detail_embedded_data.html")}

    records, sitemap_state, source_discovery = apply_sitemap_updates(
        existing_records,
        sitemap_entries,
        previous_state={},
        fetch_detail_page=fake_fetch,
        refreshed_at="2026-03-24T03:00:00Z",
        backfill_batch_size=1,
    )

    assert {record["id"] for record in records} == {"6000", "5741"}
    assert sitemap_state["6000"]["fetch_status"] == "http_404"
    assert sitemap_state["5741"]["fetch_status"] == "ok"
    assert source_discovery["detail_pages_fetched"] == 2
    assert source_discovery["new_ids"] == 1
    assert source_discovery["backfilled_ids"] == 1
    assert source_discovery["forced_refetch_ids"] == 0
    assert source_discovery["refresh_scope"] == "incremental"
    assert source_discovery["anomaly_counts"]["detail_404"] == 1


def test_apply_sitemap_updates_full_refresh_reports_forced_refetches():
    existing_records = {
        "6000": normalize_record(
            {
                "id": "6000",
                "year": "2025",
                "title": "120 Kim L.",
                "url": "https://www.blockislandinfo.com/event/120-kim-l/6000/",
                "image": "https://cdn.example.com/6000.jpg",
                "location": "Rodman's Hollow",
                "date_found": "2025-06-10",
            }
        ),
    }
    sitemap_entries = {
        "6000": {
            "url": "https://www.blockislandinfo.com/event/120-kim-l/6000/",
            "sitemap_lastmod": "2026-03-24T00:00:00Z",
        },
        "5741": {
            "url": "https://www.blockislandinfo.com/event/138-k-frost/5741/",
            "sitemap_lastmod": "2026-03-24T02:45:48Z",
        },
    }

    records, _, source_discovery = apply_sitemap_updates(
        existing_records,
        sitemap_entries,
        previous_state={
            "6000": {
                "url": "https://www.blockislandinfo.com/event/120-kim-l/6000/",
                "sitemap_lastmod": "2026-03-24T00:00:00Z",
                "last_fetched_at": "2026-03-20T00:00:00Z",
                "fetch_status": "ok",
            }
        },
        fetch_detail_page=lambda url: (
            {"status_code": 200, "body": ""}
            if extract_record_id_from_url(url) == "6000"
            else {"status_code": 200, "body": load_fixture("event_detail_embedded_data.html")}
        ),
        refreshed_at="2026-03-24T03:00:00Z",
        full_refresh=True,
    )

    assert {record["id"] for record in records} == {"6000", "5741"}
    assert source_discovery["detail_pages_fetched"] == 2
    assert source_discovery["reused_rows"] == 0
    assert source_discovery["new_ids"] == 1
    assert source_discovery["backfilled_ids"] == 0
    assert source_discovery["forced_refetch_ids"] == 1
    assert source_discovery["refresh_scope"] == "full"


def test_apply_sitemap_updates_marks_existing_rows_missing_from_sitemap():
    existing_records = {
        "6000": normalize_record(sample_records()[1]),
    }

    records, sitemap_state, source_discovery = apply_sitemap_updates(
        existing_records,
        sitemap_entries={},
        previous_state={},
        fetch_detail_page=lambda url: {"status_code": 200, "body": ""},
        refreshed_at="2026-03-24T03:00:00Z",
    )

    assert {record["id"] for record in records} == {"6000"}
    assert sitemap_state["6000"]["fetch_status"] == "missing_from_sitemap"
    assert source_discovery["anomaly_counts"]["missing_from_sitemap"] == 1


def test_apply_sitemap_updates_tracks_non_float_rejections():
    sitemap_entries = {
        "7": {
            "url": "https://www.blockislandinfo.com/event/the-glass-float-project/7/",
            "sitemap_lastmod": "2026-03-24T00:00:00Z",
        },
    }
    html = """
    <html>
      <head>
        <script>
          var data = {
            "recid": "7",
            "title": "The Glass Float Project",
            "location": "Block Island",
            "categories": []
          };
        </script>
      </head>
      <body></body>
    </html>
    """

    records, sitemap_state, source_discovery = apply_sitemap_updates(
        existing_by_id={},
        sitemap_entries=sitemap_entries,
        previous_state={},
        fetch_detail_page=lambda url: {"status_code": 200, "body": html},
        refreshed_at="2026-03-24T03:00:00Z",
    )

    assert records == []
    assert sitemap_state["7"]["fetch_status"] == "non_float_event"
    assert source_discovery["anomaly_counts"]["non_float_event"] == 1


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
    forecast_path = tmp_path / "forecast_artifact.json"
    evaluation_path = tmp_path / "forecast_evaluation.json"
    sitemap_state_path = tmp_path / "sitemap_state.json"
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
    artifact = sample_forecast_artifact()
    write_json(forecast_path, artifact)
    write_json(evaluation_path, artifact["evaluation"])
    write_json(sitemap_state_path, sample_sitemap_state(records))
    monkeypatch.setattr("scripts.refresh_data.SCRAPED_DATA_DIR", snapshot_dir)
    write_per_year_snapshots(records)

    errors = validate_outputs(
        records,
        db_path=db_path,
        manifest_path=manifest_path,
        forecast_path=forecast_path,
        evaluation_path=evaluation_path,
        sitemap_state_path=sitemap_state_path,
    )
    assert any("drift detected" in error.lower() for error in errors)


def test_validate_outputs_requires_forecast_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    records = sample_records()
    db_path = tmp_path / "floats.db"
    manifest_path = tmp_path / "refresh_manifest.json"
    sitemap_state_path = tmp_path / "sitemap_state.json"
    snapshot_dir = tmp_path / "scraped_data"

    rebuild_database(records, db_path)
    write_json(manifest_path, build_manifest(records))
    write_json(sitemap_state_path, sample_sitemap_state(records))
    monkeypatch.setattr("scripts.refresh_data.SCRAPED_DATA_DIR", snapshot_dir)
    write_per_year_snapshots(records)

    errors = validate_outputs(
        records,
        db_path=db_path,
        manifest_path=manifest_path,
        forecast_path=tmp_path / "missing.json",
        evaluation_path=tmp_path / "missing-eval.json",
        sitemap_state_path=sitemap_state_path,
    )
    assert any("forecast artifact is missing" in error.lower() for error in errors)


def test_validate_outputs_passes_with_forecast_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    records = sample_records()
    db_path = tmp_path / "floats.db"
    manifest_path = tmp_path / "refresh_manifest.json"
    forecast_path = tmp_path / "forecast_artifact.json"
    evaluation_path = tmp_path / "forecast_evaluation.json"
    sitemap_state_path = tmp_path / "sitemap_state.json"
    snapshot_dir = tmp_path / "scraped_data"
    sitemap_state = sample_sitemap_state(records)

    rebuild_database(records, db_path)
    write_json(manifest_path, build_manifest(records))
    artifact = sample_forecast_artifact()
    write_json(forecast_path, artifact)
    write_json(evaluation_path, artifact["evaluation"])
    write_json(sitemap_state_path, sitemap_state)
    monkeypatch.setattr("scripts.refresh_data.SCRAPED_DATA_DIR", snapshot_dir)
    write_per_year_snapshots(records)

    assert set(sitemap_state["6000"]) == set(SITEMAP_STATE_KEYS)
    assert validate_outputs(
        records,
        db_path=db_path,
        manifest_path=manifest_path,
        forecast_path=forecast_path,
        evaluation_path=evaluation_path,
        sitemap_state_path=sitemap_state_path,
    ) == []


def test_validate_outputs_requires_sitemap_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    records = sample_records()
    db_path = tmp_path / "floats.db"
    manifest_path = tmp_path / "refresh_manifest.json"
    forecast_path = tmp_path / "forecast_artifact.json"
    evaluation_path = tmp_path / "forecast_evaluation.json"
    snapshot_dir = tmp_path / "scraped_data"

    rebuild_database(records, db_path)
    write_json(manifest_path, build_manifest(records))
    artifact = sample_forecast_artifact()
    write_json(forecast_path, artifact)
    write_json(evaluation_path, artifact["evaluation"])
    monkeypatch.setattr("scripts.refresh_data.SCRAPED_DATA_DIR", snapshot_dir)
    write_per_year_snapshots(records)

    errors = validate_outputs(
        records,
        db_path=db_path,
        manifest_path=manifest_path,
        forecast_path=forecast_path,
        evaluation_path=evaluation_path,
        sitemap_state_path=tmp_path / "missing_sitemap_state.json",
    )
    assert any("sitemap state is missing" in error.lower() for error in errors)


def test_validate_outputs_rejects_sitemap_state_missing_required_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    records = sample_records()
    db_path = tmp_path / "floats.db"
    manifest_path = tmp_path / "refresh_manifest.json"
    forecast_path = tmp_path / "forecast_artifact.json"
    evaluation_path = tmp_path / "forecast_evaluation.json"
    sitemap_state_path = tmp_path / "sitemap_state.json"
    snapshot_dir = tmp_path / "scraped_data"

    rebuild_database(records, db_path)
    write_json(manifest_path, build_manifest(records))
    artifact = sample_forecast_artifact()
    write_json(forecast_path, artifact)
    write_json(evaluation_path, artifact["evaluation"])
    invalid_state = sample_sitemap_state(records)
    invalid_state["6000"] = {"url": "https://example.com/6000"}
    write_json(sitemap_state_path, invalid_state)
    monkeypatch.setattr("scripts.refresh_data.SCRAPED_DATA_DIR", snapshot_dir)
    write_per_year_snapshots(records)

    errors = validate_outputs(
        records,
        db_path=db_path,
        manifest_path=manifest_path,
        forecast_path=forecast_path,
        evaluation_path=evaluation_path,
        sitemap_state_path=sitemap_state_path,
    )
    assert any("missing keys" in error.lower() for error in errors)


def test_canonical_fixture_shape():
    for record in sample_records():
        assert tuple(record.keys()) == CANONICAL_KEYS
