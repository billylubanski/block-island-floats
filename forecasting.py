from __future__ import annotations

import datetime as dt
import math
import sqlite3
from collections import Counter, defaultdict
from typing import Any

import requests

from analyzer import normalize_location
from locations import LOCATIONS

BLOCK_ISLAND_COORDS = (41.17, -71.58)
BLOCK_ISLAND_GRIDPOINT = "BOX/63,33"
BLOCK_ISLAND_POINT_URL = "https://api.weather.gov/points/41.17,-71.58"
DEFAULT_OBSERVATION_STATION = "KBID"
PRIMARY_TIDE_STATION = "8459338"
FALLBACK_TIDE_STATION = "8459681"
TIDE_DATAGETTER_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
NWS_USER_AGENT = "(glassfloattracker.com, contact@glassfloattracker.com)"
REFERENCE_NEW_MOON = dt.date(2000, 1, 6)
SYNODIC_MONTH = 29.53058867
DAY_KEYS = tuple(str(day) for day in range(1, 367))

WATERFRONT_KEYWORDS = {
    "beach",
    "bluff",
    "bluffs",
    "cove",
    "dock",
    "harbor",
    "harbour",
    "lighthouse",
    "marina",
    "ocean",
    "pond",
    "point",
    "salt",
    "shore",
}
TRAIL_KEYWORDS = {
    "farm",
    "forest",
    "greenway",
    "hollow",
    "hill",
    "labyrinth",
    "loop",
    "maze",
    "park",
    "preserve",
    "road",
    "trail",
}
TOWN_KEYWORDS = {
    "airport",
    "bagel",
    "hotel",
    "inn",
    "landing",
    "library",
    "market",
    "office",
    "school",
    "shop",
    "station",
    "street",
    "theater",
    "town",
}


def empty_forecast_artifact() -> dict[str, Any]:
    return {
        "version": 2,
        "generated_at": "",
        "source": {
            "total_records": 0,
            "latest_source_date": "",
            "training_rows": 0,
            "cluster_training_rows": 0,
            "actual_years": [],
        },
        "seasonality_by_month": {str(month): 0.0 for month in range(1, 13)},
        "activity_index_by_day": {day_key: 0.0 for day_key in DAY_KEYS},
        "cluster_profiles": {},
        "seasonal_priors_by_day": {day_key: {} for day_key in DAY_KEYS},
        "evaluation": {
            "targets": {
                "exact_location": {},
                "cluster": {},
            },
            "selection": {
                "primary_model": "kernel_seasonal",
                "gating_reason": "No evaluation data available.",
                "eligible_models": [],
            },
        },
        "feature_sources": {
            "calendar": {"available": True},
            "recency": {"available": True},
            "historical_weather": {"available": False, "provider": "NOAA NCEI CDO"},
            "live_weather": {
                "available": True,
                "provider": "NWS API",
                "gridpoint": BLOCK_ISLAND_GRIDPOINT,
                "preferred_observation_station": DEFAULT_OBSERVATION_STATION,
            },
            "tide": {
                "available": True,
                "provider": "NOAA CO-OPS",
                "primary_station": PRIMARY_TIDE_STATION,
                "fallback_station": FALLBACK_TIDE_STATION,
            },
        },
    }


def parse_date(date_str: str | None) -> dt.datetime | None:
    if not date_str:
        return None

    formats = (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%B %Y",
        "%b %Y",
    )
    for fmt in formats:
        try:
            return dt.datetime.strptime(str(date_str), fmt)
        except ValueError:
            continue
    return None


def cyclical_day_distance(day_a: int, day_b: int, period: int = 366) -> int:
    diff = abs(int(day_a) - int(day_b))
    return min(diff, period - diff)


def gaussian_kernel(distance: float, sigma: float = 21.0) -> float:
    if sigma <= 0:
        return 0.0
    return math.exp(-((distance**2) / (2 * (sigma**2))))


def build_cluster_definitions(location_counts: dict[str, int] | Counter[str]) -> list[dict[str, Any]]:
    grouped: dict[tuple[float, float], list[str]] = defaultdict(list)
    for name, coords in LOCATIONS.items():
        grouped[(coords["lat"], coords["lon"])].append(name)

    definitions: list[dict[str, Any]] = []
    for (lat, lon), names in grouped.items():
        ranked_names = sorted(names, key=lambda item: (-int(location_counts.get(item, 0)), item))
        label = ranked_names[0] if len(ranked_names) == 1 else f"{ranked_names[0]} area"
        support_count = int(sum(int(location_counts.get(name, 0)) for name in ranked_names))
        definitions.append(
            {
                "label": label,
                "lat": lat,
                "lon": lon,
                "spots": ranked_names,
                "support_count": support_count,
                "spot_count": len(ranked_names),
                "tags": derive_cluster_tags(ranked_names),
            }
        )
    return sorted(definitions, key=lambda cluster: (-cluster["support_count"], cluster["label"]))


def build_cluster_lookup(location_counts: dict[str, int] | Counter[str]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for definition in build_cluster_definitions(location_counts):
        for spot in definition["spots"]:
            lookup[spot] = definition["label"]
    return lookup


def derive_cluster_tags(spots: list[str]) -> list[str]:
    lowered = " ".join(spot.lower() for spot in spots)
    tags = []
    if any(keyword in lowered for keyword in WATERFRONT_KEYWORDS):
        tags.append("waterfront")
    if any(keyword in lowered for keyword in TRAIL_KEYWORDS):
        tags.append("trail")
    if any(keyword in lowered for keyword in TOWN_KEYWORDS):
        tags.append("town")
    if not tags:
        tags.append("mixed")
    return tags


def nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> dt.date:
    first = dt.date(year, month, 1)
    delta = (weekday - first.weekday()) % 7
    return first + dt.timedelta(days=delta + (n - 1) * 7)


def last_weekday_of_month(year: int, month: int, weekday: int) -> dt.date:
    if month == 12:
        end = dt.date(year + 1, 1, 1) - dt.timedelta(days=1)
    else:
        end = dt.date(year, month + 1, 1) - dt.timedelta(days=1)
    delta = (end.weekday() - weekday) % 7
    return end - dt.timedelta(days=delta)


def observed_holiday(day: dt.date) -> dt.date:
    if day.weekday() == 5:
        return day - dt.timedelta(days=1)
    if day.weekday() == 6:
        return day + dt.timedelta(days=1)
    return day


def us_federal_holidays(year: int) -> set[dt.date]:
    holidays = {
        observed_holiday(dt.date(year, 1, 1)),
        nth_weekday_of_month(year, 1, 0, 3),
        nth_weekday_of_month(year, 2, 0, 3),
        last_weekday_of_month(year, 5, 0),
        observed_holiday(dt.date(year, 6, 19)),
        observed_holiday(dt.date(year, 7, 4)),
        nth_weekday_of_month(year, 9, 0, 1),
        nth_weekday_of_month(year, 10, 0, 2),
        observed_holiday(dt.date(year, 11, 11)),
        nth_weekday_of_month(year, 11, 3, 4),
        observed_holiday(dt.date(year, 12, 25)),
    }
    return holidays


def is_us_federal_holiday(day: dt.date) -> bool:
    return day in us_federal_holidays(day.year)


def is_long_weekend(day: dt.date) -> bool:
    holiday_dates = us_federal_holidays(day.year) | us_federal_holidays(day.year - 1) | us_federal_holidays(day.year + 1)
    return any(abs((day - holiday).days) <= 1 for holiday in holiday_dates) and day.weekday() in {4, 5, 6, 0}


def moon_phase(day: dt.date) -> tuple[str, float]:
    days_since_reference = (day - REFERENCE_NEW_MOON).days
    phase_position = (days_since_reference % SYNODIC_MONTH) / SYNODIC_MONTH
    illumination = 0.5 * (1 - math.cos(2 * math.pi * phase_position))

    if phase_position < 0.0625 or phase_position >= 0.9375:
        phase = "new"
    elif phase_position < 0.1875:
        phase = "waxing_crescent"
    elif phase_position < 0.3125:
        phase = "first_quarter"
    elif phase_position < 0.4375:
        phase = "waxing_gibbous"
    elif phase_position < 0.5625:
        phase = "full"
    elif phase_position < 0.6875:
        phase = "waning_gibbous"
    elif phase_position < 0.8125:
        phase = "last_quarter"
    else:
        phase = "waning_crescent"

    return phase, round(illumination, 4)


def moon_illumination_bucket(value: float) -> str:
    if value < 0.25:
        return "dark"
    if value < 0.6:
        return "balanced"
    return "bright"


def build_calendar_features(day: dt.date) -> dict[str, Any]:
    phase, illumination = moon_phase(day)
    return {
        "day_of_year": day.timetuple().tm_yday,
        "month": day.month,
        "weekday": day.weekday(),
        "weekday_name": day.strftime("%A"),
        "is_weekend": day.weekday() >= 5,
        "is_holiday": is_us_federal_holiday(day),
        "is_long_weekend": is_long_weekend(day),
        "moon_phase": phase,
        "moon_illumination": illumination,
        "moon_illumination_bucket": moon_illumination_bucket(illumination),
    }


def _nws_headers() -> dict[str, str]:
    return {
        "User-Agent": NWS_USER_AGENT,
        "Accept": "application/geo+json",
    }


def parse_wind_speed_mph(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return round(float(value))

    text = str(value)
    digits = "".join(char if char.isdigit() or char in ".-" else " " for char in text)
    values = [float(chunk) for chunk in digits.split() if chunk]
    if not values:
        return None
    return round(sum(values) / len(values))


def weather_emoji(description: str) -> str:
    desc_lower = (description or "").lower()
    if "sunny" in desc_lower or "clear" in desc_lower:
        return "\u2600\ufe0f"
    if "partly cloudy" in desc_lower:
        return "\u26c5"
    if "cloudy" in desc_lower or "overcast" in desc_lower:
        return "\u2601\ufe0f"
    if "rain" in desc_lower or "drizzle" in desc_lower or "shower" in desc_lower:
        return "\u2614"
    if "thunder" in desc_lower or "storm" in desc_lower:
        return "\u26c8\ufe0f"
    if "snow" in desc_lower:
        return "\u2744\ufe0f"
    if "fog" in desc_lower or "mist" in desc_lower:
        return "\U0001f32b\ufe0f"
    if "wind" in desc_lower:
        return "\U0001f4a8"
    return "\U0001f321\ufe0f"


def resolve_observation_station_id(
    station_features: list[dict[str, Any]],
    preferred_station: str = DEFAULT_OBSERVATION_STATION,
) -> str | None:
    if not station_features:
        return preferred_station

    for feature in station_features:
        props = feature.get("properties", {})
        if props.get("stationIdentifier") == preferred_station:
            return preferred_station

    first = station_features[0].get("properties", {})
    return first.get("stationIdentifier") or preferred_station


def fetch_live_weather_context(
    *,
    now: dt.datetime | None = None,
    request_get=requests.get,
) -> dict[str, Any] | None:
    current_time = now or dt.datetime.now()

    try:
        points_response = request_get(BLOCK_ISLAND_POINT_URL, headers=_nws_headers(), timeout=8)
        if points_response.status_code != 200:
            return None
        points_payload = points_response.json().get("properties", {})

        stations_url = points_payload.get("observationStations")
        forecast_hourly_url = points_payload.get("forecastHourly")
        if not stations_url or not forecast_hourly_url:
            return None

        stations_response = request_get(stations_url, headers=_nws_headers(), timeout=8)
        station_features = stations_response.json().get("features", []) if stations_response.status_code == 200 else []
        station_id = resolve_observation_station_id(station_features)

        observation_payload = {}
        if station_id:
            obs_url = f"https://api.weather.gov/stations/{station_id}/observations/latest"
            obs_response = request_get(obs_url, headers=_nws_headers(), timeout=8)
            if obs_response.status_code == 200:
                observation_payload = obs_response.json().get("properties", {})

        forecast_response = request_get(forecast_hourly_url, headers=_nws_headers(), timeout=8)
        forecast_periods = []
        if forecast_response.status_code == 200:
            forecast_periods = forecast_response.json().get("properties", {}).get("periods", [])
        current_period = forecast_periods[0] if forecast_periods else {}

        temperature_c = observation_payload.get("temperature", {}).get("value")
        temperature_f = round((temperature_c * 9 / 5) + 32) if temperature_c is not None else current_period.get("temperature")

        wind_speed_mps = observation_payload.get("windSpeed", {}).get("value")
        wind_speed = round(wind_speed_mps * 2.23694) if wind_speed_mps is not None else parse_wind_speed_mph(current_period.get("windSpeed"))

        description = observation_payload.get("textDescription") or current_period.get("shortForecast") or "Unknown"
        precip_chance = current_period.get("probabilityOfPrecipitation", {}).get("value")
        forecast_text = current_period.get("detailedForecast") or current_period.get("shortForecast") or description
        wind_direction = current_period.get("windDirection") or observation_payload.get("windDirection", {}).get("value")
        updated = observation_payload.get("timestamp") or current_period.get("startTime")
        severe = any(keyword in forecast_text.lower() for keyword in ("thunder", "storm", "gale", "snow", "advisory", "warning"))

        return {
            "temp": temperature_f,
            "condition": description,
            "wind": wind_speed,
            "wind_direction": wind_direction,
            "precip_chance": precip_chance,
            "summary": forecast_text,
            "severe": severe,
            "emoji": weather_emoji(description),
            "timestamp": current_time.strftime("%I:%M %p"),
            "station_id": station_id or DEFAULT_OBSERVATION_STATION,
            "gridpoint": BLOCK_ISLAND_GRIDPOINT,
            "updated_at": updated or current_time.isoformat(),
        }
    except Exception:
        return None


def _fetch_tide_predictions_for_station(
    station_id: str,
    *,
    target_time: dt.datetime,
    request_get=requests.get,
) -> dict[str, Any] | None:
    begin = (target_time - dt.timedelta(hours=12)).strftime("%Y%m%d %H:%M")
    end = (target_time + dt.timedelta(hours=18)).strftime("%Y%m%d %H:%M")
    hourly_params = {
        "product": "predictions",
        "application": "BIFloat",
        "station": station_id,
        "begin_date": begin,
        "end_date": end,
        "datum": "MLLW",
        "time_zone": "lst_ldt",
        "units": "english",
        "interval": "h",
        "format": "json",
    }
    hilo_params = dict(hourly_params)
    hilo_params["interval"] = "hilo"

    hourly_response = request_get(TIDE_DATAGETTER_URL, params=hourly_params, timeout=8)
    if hourly_response.status_code != 200:
        return None
    hourly_predictions = hourly_response.json().get("predictions", [])
    if not hourly_predictions:
        return None

    hilo_response = request_get(TIDE_DATAGETTER_URL, params=hilo_params, timeout=8)
    hilo_predictions = hilo_response.json().get("predictions", []) if hilo_response.status_code == 200 else []

    timeline = []
    for item in hourly_predictions:
        try:
            ts = dt.datetime.strptime(item["t"], "%Y-%m-%d %H:%M")
            height = float(item["v"])
        except (KeyError, TypeError, ValueError):
            continue
        timeline.append((ts, height))
    if not timeline:
        return None

    closest_index = min(range(len(timeline)), key=lambda idx: abs((timeline[idx][0] - target_time).total_seconds()))
    current_height = timeline[closest_index][1]
    prev_height = timeline[max(closest_index - 1, 0)][1]
    next_height = timeline[min(closest_index + 1, len(timeline) - 1)][1]
    stage = "rising" if next_height >= prev_height else "falling"

    nearest_event = None
    for item in hilo_predictions:
        try:
            event_time = dt.datetime.strptime(item["t"], "%Y-%m-%d %H:%M")
            event_type = item.get("type", "")
            event_height = float(item["v"])
        except (KeyError, TypeError, ValueError):
            continue
        if nearest_event is None or abs((event_time - target_time).total_seconds()) < abs((nearest_event["time"] - target_time).total_seconds()):
            nearest_event = {
                "time": event_time,
                "type": "high" if str(event_type).upper().startswith("H") else "low",
                "height": event_height,
            }

    return {
        "station_id": station_id,
        "height_now": round(current_height, 2),
        "stage": stage,
        "daily_range": round(max(height for _, height in timeline) - min(height for _, height in timeline), 2),
        "nearest_event": {
            "type": nearest_event["type"],
            "height": nearest_event["height"],
            "hours_away": round((nearest_event["time"] - target_time).total_seconds() / 3600, 1),
            "time": nearest_event["time"].isoformat(),
        } if nearest_event else None,
        "updated_at": target_time.isoformat(),
    }


def fetch_live_tide_context(
    *,
    target_time: dt.datetime | None = None,
    request_get=requests.get,
) -> dict[str, Any] | None:
    current_time = target_time or dt.datetime.now()
    for station_id in (PRIMARY_TIDE_STATION, FALLBACK_TIDE_STATION):
        context = _fetch_tide_predictions_for_station(station_id, target_time=current_time, request_get=request_get)
        if context:
            context["primary_station"] = PRIMARY_TIDE_STATION
            context["fallback_station"] = FALLBACK_TIDE_STATION
            return context
    return None


def build_recent_activity_snapshot(
    db_name: str,
    *,
    target_date: dt.date,
    location_to_cluster: dict[str, str],
) -> dict[str, Any]:
    snapshot = {
        "counts_by_cluster": {},
        "windows": {
            "7": 0,
            "14": 0,
            "30": 0,
        },
    }
    if not db_name:
        return snapshot

    try:
        conn = sqlite3.connect(db_name)
        rows = conn.execute(
            "SELECT date_found, location_raw FROM finds WHERE date_found IS NOT NULL AND date_found != ''"
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return snapshot

    cluster_counts = Counter()
    for date_found, location_raw in rows:
        parsed = parse_date(date_found)
        if parsed is None:
            continue
        found_date = parsed.date()
        if found_date > target_date:
            continue
        delta = (target_date - found_date).days
        if delta <= 30:
            normalized_location = normalize_location(location_raw)
            cluster_label = location_to_cluster.get(normalized_location)
            if cluster_label:
                cluster_counts[cluster_label] += 1
            snapshot["windows"]["30"] += 1
        if delta <= 14:
            snapshot["windows"]["14"] += 1
        if delta <= 7:
            snapshot["windows"]["7"] += 1

    snapshot["counts_by_cluster"] = dict(cluster_counts)
    return snapshot


def _bounded_multiplier(base: float, minimum: float = 0.85, maximum: float = 1.25) -> float:
    return min(max(base, minimum), maximum)


def _calendar_multiplier(profile: dict[str, Any], calendar_context: dict[str, Any]) -> tuple[float, str | None]:
    affinities = profile.get("calendar_affinity", {})
    weekday_name = calendar_context["weekday_name"]
    weekday_ratio = float(affinities.get("weekday_ratios", {}).get(weekday_name, 1.0))
    weekend_ratio = float(affinities.get("weekend_ratio", 1.0))
    holiday_ratio = float(affinities.get("holiday_ratio", 1.0))
    long_weekend_ratio = float(affinities.get("long_weekend_ratio", 1.0))
    moon_ratio = float(affinities.get("moon_phase_ratios", {}).get(calendar_context["moon_phase"], 1.0))
    illum_ratio = float(
        affinities.get("moon_illumination_ratios", {}).get(calendar_context["moon_illumination_bucket"], 1.0)
    )

    multiplier = weekday_ratio * moon_ratio * illum_ratio
    reason = None
    if calendar_context["is_weekend"]:
        multiplier *= weekend_ratio
        if weekend_ratio >= 1.08:
            reason = "Usually stronger on weekends."
    if calendar_context["is_holiday"]:
        multiplier *= holiday_ratio
        if holiday_ratio >= 1.08:
            reason = "Holiday timing has helped here before."
    elif calendar_context["is_long_weekend"]:
        multiplier *= long_weekend_ratio
        if long_weekend_ratio >= 1.08:
            reason = "Long weekends have historically helped this zone."
    return _bounded_multiplier(multiplier), reason


def _recency_multiplier(
    cluster_label: str,
    recent_activity: dict[str, Any],
) -> tuple[float, str | None]:
    cluster_recent = int(recent_activity.get("counts_by_cluster", {}).get(cluster_label, 0))
    island_30 = int(recent_activity.get("windows", {}).get("30", 0))

    if cluster_recent <= 0 or island_30 <= 0:
        return 1.0, None

    boost = 1.0 + min(cluster_recent * 0.08, 0.24)
    reason = "Recent reports support this zone." if cluster_recent >= 1 else None
    return _bounded_multiplier(boost), reason


def _tide_multiplier(profile: dict[str, Any], tide_context: dict[str, Any] | None) -> tuple[float, str | None]:
    if not tide_context:
        return 1.0, None

    tags = set(profile.get("tags", []))
    stage = tide_context.get("stage")
    daily_range = float(tide_context.get("daily_range") or 0.0)

    multiplier = 1.0
    reason = None
    if "waterfront" in tags:
        if stage == "rising":
            multiplier += 0.08
            reason = "Favorable incoming tide for waterfront spots."
        if daily_range >= 2.5:
            multiplier += 0.04
    elif "trail" in tags and daily_range >= 2.5:
        multiplier -= 0.03

    return _bounded_multiplier(multiplier), reason


def _weather_multiplier(profile: dict[str, Any], weather_context: dict[str, Any] | None) -> tuple[float, str | None]:
    if not weather_context:
        return 1.0, None

    tags = set(profile.get("tags", []))
    wind = weather_context.get("wind") or 0
    precip_chance = weather_context.get("precip_chance") or 0
    severe = bool(weather_context.get("severe"))

    multiplier = 1.0
    reason = None

    if severe:
        multiplier -= 0.12
        reason = "Weather is a drag today."
    elif "waterfront" in tags and wind <= 12 and precip_chance < 50:
        multiplier += 0.05
        reason = "Current weather is workable for exposed shoreline spots."
    elif "trail" in tags and wind >= 18:
        multiplier += 0.04
        reason = "Stronger wind can make sheltered trail zones comparatively better."

    return _bounded_multiplier(multiplier), reason


def describe_activity_score(score: float) -> str:
    if score >= 7.5:
        return "Active"
    if score >= 4.5:
        return "Steady"
    return "Quiet"


def zone_signal_label(score: float, max_score: float) -> str:
    if max_score <= 0:
        return "Low signal"
    relative = score / max_score
    if relative >= 0.85:
        return "Best signal"
    if relative >= 0.6:
        return "Useful fallback"
    return "Thin support"


def _confidence_band(artifact: dict[str, Any], zones: list[dict[str, Any]], feature_count: int) -> str:
    evaluation = artifact.get("evaluation", {})
    cluster_metrics = evaluation.get("targets", {}).get("cluster", {})
    selection = evaluation.get("selection", {})
    primary_model = selection.get("primary_model", "kernel_seasonal")
    primary_metrics = cluster_metrics.get(primary_model, cluster_metrics.get("kernel_seasonal", {}))

    top3_accuracy = float(primary_metrics.get("top3_accuracy", 0.0))
    top_zone = zones[0] if zones else {}
    support_count = int(top_zone.get("dated_support_count", 0))
    actual_years = len(top_zone.get("actual_years", []))

    if top3_accuracy >= 0.2 and support_count >= 18 and actual_years >= 3 and feature_count >= 2:
        return "high"
    if top3_accuracy >= 0.1 and support_count >= 8 and actual_years >= 2:
        return "medium"
    return "low"


def _select_reason_tags(reason_texts: list[str], profile: dict[str, Any], target_date: dt.date) -> list[str]:
    tags = []
    best_months = profile.get("best_months", [])
    if best_months and target_date.strftime("%B") in best_months[:2]:
        tags.append(f"Strong {target_date.strftime('%B').lower()} history")

    for reason in reason_texts:
        if not reason:
            continue
        lowered = reason.lower()
        if "recent reports" in lowered:
            tags.append("Recent finds nearby")
        elif "tide" in lowered:
            tags.append("Favorable incoming tide")
        elif "weather is a drag" in lowered:
            tags.append("Weather is a drag today")
        elif "weekend" in lowered or "holiday" in lowered:
            tags.append("Calendar timing fits past hits")
        elif "shoreline" in lowered:
            tags.append("Weather favors shoreline scouting")

    if not tags:
        tags.append("Strong base seasonal signal")
    return tags[:3]


def _lead_change_summary(today_zones: list[dict[str, Any]], yesterday_zones: list[dict[str, Any]], today_activity: float, yesterday_activity: float) -> str:
    if today_zones and yesterday_zones and today_zones[0]["label"] != yesterday_zones[0]["label"]:
        return f"Lead zone rotated from {yesterday_zones[0]['label']} to {today_zones[0]['label']}."
    if today_activity - yesterday_activity >= 0.7:
        return "Island-wide activity strengthened from yesterday."
    if yesterday_activity - today_activity >= 0.7:
        return "Island-wide activity softened from yesterday."
    return "The daily read is steady versus yesterday."


def build_daily_forecast_briefing(
    artifact: dict[str, Any],
    *,
    target_date: dt.date | None = None,
    weather_context: dict[str, Any] | None = None,
    tide_context: dict[str, Any] | None = None,
    recent_activity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target = target_date or dt.date.today()
    calendar_context = build_calendar_features(target)
    recent = recent_activity or {"counts_by_cluster": {}, "windows": {"7": 0, "14": 0, "30": 0}}
    day_key = str(target.timetuple().tm_yday)
    yesterday = target - dt.timedelta(days=1)
    yesterday_key = str(yesterday.timetuple().tm_yday)

    priors_by_day = artifact.get("seasonal_priors_by_day", {})
    today_priors = priors_by_day.get(day_key, {}) if isinstance(priors_by_day, dict) else {}
    yesterday_priors = priors_by_day.get(yesterday_key, {}) if isinstance(priors_by_day, dict) else {}
    cluster_profiles = artifact.get("cluster_profiles", {}) if isinstance(artifact.get("cluster_profiles"), dict) else {}
    selection = artifact.get("evaluation", {}).get("selection", {})
    selected_model = selection.get("primary_model", "kernel_seasonal")

    zones: list[dict[str, Any]] = []
    for label, profile in cluster_profiles.items():
        base_score = float(today_priors.get(label, 0.0))
        if base_score <= 0:
            continue

        calendar_mult, calendar_reason = _calendar_multiplier(profile, calendar_context)
        recency_mult, recency_reason = _recency_multiplier(label, recent)
        tide_mult, tide_reason = _tide_multiplier(profile, tide_context)
        weather_mult, weather_reason = _weather_multiplier(profile, weather_context)

        if selected_model == "hybrid_zone":
            final_score = base_score * calendar_mult * recency_mult * tide_mult * weather_mult
        else:
            final_score = base_score

        reason_texts = [calendar_reason, recency_reason, tide_reason, weather_reason]
        zones.append(
            {
                "label": label,
                "score": final_score,
                "base_score": base_score,
                "lat": profile.get("lat"),
                "lon": profile.get("lon"),
                "support_count": profile.get("support_count", 0),
                "dated_support_count": profile.get("dated_support_count", 0),
                "actual_years": profile.get("actual_years", []),
                "supporting_spots": profile.get("supporting_spots", []),
                "primary_spot": profile.get("supporting_spots", [{}])[0].get("name") if profile.get("supporting_spots") else label,
                "tags": profile.get("tags", []),
                "reason_texts": [reason for reason in reason_texts if reason],
                "reason_tags": _select_reason_tags(reason_texts, profile, target),
            }
        )

    zones.sort(key=lambda zone: (-zone["score"], zone["label"]))
    zones = zones[:3]

    yesterday_ranked = []
    for label, score in yesterday_priors.items():
        if label in cluster_profiles:
            yesterday_ranked.append({"label": label, "score": float(score)})
    yesterday_ranked.sort(key=lambda zone: (-zone["score"], zone["label"]))

    max_zone_score = max((zone["score"] for zone in zones), default=0.0)
    for zone in zones:
        zone["signal_label"] = zone_signal_label(zone["score"], max_zone_score)

    activity_by_day = artifact.get("activity_index_by_day", {})
    today_activity = float(activity_by_day.get(day_key, 0.0)) if isinstance(activity_by_day, dict) else 0.0
    yesterday_activity = float(activity_by_day.get(yesterday_key, today_activity)) if isinstance(activity_by_day, dict) else today_activity

    live_feature_count = int(bool(weather_context)) + int(bool(tide_context))
    confidence_band = _confidence_band(artifact, zones, live_feature_count)

    disclaimer = (
        "This briefing is directional. The seasonal signal is stronger than the live context, and support is still thin in many zones."
        if confidence_band == "low"
        else "Use this as a starting order, then confirm the read against the map, trail access, and real conditions."
    )

    return {
        "date": target.isoformat(),
        "activity_score": round(today_activity, 1),
        "activity_label": describe_activity_score(today_activity),
        "confidence_band": confidence_band,
        "conditions": {
            "weather": weather_context,
            "tide": tide_context,
            "calendar": calendar_context,
        },
        "zones": zones,
        "lead_change_summary": _lead_change_summary(zones, yesterday_ranked[:3], today_activity, yesterday_activity),
        "disclaimer": disclaimer,
        "feature_freshness": {
            "artifact_generated_at": artifact.get("generated_at", ""),
            "weather_updated_at": (weather_context or {}).get("updated_at", ""),
            "tide_updated_at": (tide_context or {}).get("updated_at", ""),
            "historical_weather_available": bool(
                artifact.get("feature_sources", {}).get("historical_weather", {}).get("available")
            ),
            "live_weather_available": bool(weather_context),
            "live_tide_available": bool(tide_context),
        },
        "selected_model": selected_model,
    }


def build_spot_forecast_lookup(briefing: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for index, zone in enumerate(briefing.get("zones", []), start=1):
        for spot in zone.get("supporting_spots", []):
            lookup[spot.get("name", "")] = {
                "rank": index,
                "zone_label": zone.get("label", ""),
            }
    return lookup
