import datetime

from forecasting import (
    build_calendar_features,
    build_daily_forecast_briefing,
    build_spot_forecast_lookup,
    convert_wind_speed_to_mph,
    empty_forecast_artifact,
    normalize_wind_direction,
    resolve_observation_station_id,
)


def sample_artifact() -> dict[str, object]:
    artifact = empty_forecast_artifact()
    artifact["generated_at"] = "2026-07-01T08:00:00Z"
    artifact["source"] = {
        "total_records": 10,
        "latest_source_date": "2026-07-01",
        "training_rows": 10,
        "cluster_training_rows": 10,
        "actual_years": [2025, 2026],
    }
    artifact["activity_index_by_day"]["182"] = 6.3
    artifact["activity_index_by_day"]["181"] = 5.6
    artifact["cluster_profiles"] = {
        "Rodman's Hollow": {
            "label": "Rodman's Hollow",
            "lat": 41.155,
            "lon": -71.585,
            "tags": ["trail"],
            "support_count": 20,
            "dated_support_count": 12,
            "actual_years": [2025, 2026],
            "primary_spot": "Rodman's Hollow",
            "supporting_spots": [{"name": "Rodman's Hollow", "count": 20}],
            "best_months": ["July"],
            "feature_coverage": {"calendar_rows": 12, "historical_weather_rows": 0, "tide_rows": 0, "recency_rows": 12},
            "calendar_affinity": {
                "weekday_ratios": {"Wednesday": 1.0},
                "weekend_ratio": 1.0,
                "holiday_ratio": 1.0,
                "long_weekend_ratio": 1.0,
                "moon_phase_ratios": {"full": 1.0},
                "moon_illumination_ratios": {"bright": 1.0},
            },
        }
    }
    artifact["seasonal_priors_by_day"]["182"] = {"Rodman's Hollow": 1.0}
    artifact["seasonal_priors_by_day"]["181"] = {"Rodman's Hollow": 1.0}
    artifact["evaluation"] = {
        "targets": {
            "exact_location": {},
            "cluster": {"kernel_seasonal": {"top3_accuracy": 0.12, "log_loss": 1.0}},
        },
        "selection": {"primary_model": "kernel_seasonal", "gating_reason": "Kernel remains primary.", "eligible_models": ["kernel_seasonal"]},
    }
    return artifact


def test_build_calendar_features_marks_observed_holiday_long_weekend():
    features = build_calendar_features(datetime.date(2026, 7, 3))

    assert features["weekday_name"] == "Friday"
    assert features["is_holiday"] is True
    assert features["is_long_weekend"] is True


def test_resolve_observation_station_id_prefers_kbid():
    features = [
        {"properties": {"stationIdentifier": "KWST"}},
        {"properties": {"stationIdentifier": "KBID"}},
    ]

    assert resolve_observation_station_id(features) == "KBID"


def test_convert_wind_speed_to_mph_honors_kmh_units():
    assert convert_wind_speed_to_mph(38.88, "wmoUnit:km_h-1") == 24


def test_normalize_wind_direction_converts_degrees_to_compass():
    assert normalize_wind_direction(230) == "SW"


def test_build_daily_forecast_briefing_returns_low_confidence_without_live_context():
    briefing = build_daily_forecast_briefing(
        sample_artifact(),
        target_date=datetime.date(2026, 7, 1),
        weather_context=None,
        tide_context=None,
        recent_activity={"counts_by_cluster": {}, "windows": {"7": 0, "14": 0, "30": 0}},
    )

    assert briefing["activity_score"] == 6.3
    assert briefing["confidence_band"] == "medium"
    assert briefing["zones"][0]["label"] == "Rodman's Hollow"


def test_build_spot_forecast_lookup_maps_supporting_spots():
    briefing = {
        "zones": [
            {
                "label": "Rodman's Hollow",
                "supporting_spots": [
                    {"name": "Rodman's Hollow"},
                    {"name": "Meadow Hill Trail"},
                ],
            }
        ]
    }

    lookup = build_spot_forecast_lookup(briefing)

    assert lookup["Rodman's Hollow"]["rank"] == 1
    assert lookup["Meadow Hill Trail"]["zone_label"] == "Rodman's Hollow"
