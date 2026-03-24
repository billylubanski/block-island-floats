from __future__ import annotations

import datetime as dt
from typing import Any

from forecast_model import (
    DB_NAME,
    attach_cluster_labels,
    build_activity_index_by_day,
    build_evaluation,
    build_feature_sources,
    build_forecast_artifact,
    build_seasonal_priors_by_day,
    build_seasonality_by_month,
    get_all_location_counts,
    get_data,
    prepare_features,
)


def clear_model_cache() -> None:
    return None


def train_model(db_name: str | None = None) -> None:
    _ = db_name
    return None


def get_model_bundle(db_name: str | None = None) -> None:
    _ = db_name
    return None


def predict_today(db_name: str | None = None) -> list[dict[str, Any]]:
    artifact = build_forecast_artifact(db_name=db_name)
    day_key = str(dt.date.today().timetuple().tm_yday)
    priors = artifact.get("seasonal_priors_by_day", {}).get(day_key, {})
    cluster_profiles = artifact.get("cluster_profiles", {})

    ranked = sorted(priors.items(), key=lambda item: (-float(item[1]), item[0]))[:3]
    predictions = []
    for label, score in ranked:
        profile = cluster_profiles.get(label, {})
        predictions.append(
            {
                "location": profile.get("primary_spot") or label,
                "zone": label,
                "score": round(float(score), 4),
            }
        )
    return predictions


def get_seasonality_score(db_name: str | None = None) -> float:
    artifact = build_forecast_artifact(db_name=db_name)
    return float(artifact.get("seasonality_by_month", {}).get(str(dt.date.today().month), 0.0))


__all__ = [
    "DB_NAME",
    "attach_cluster_labels",
    "build_activity_index_by_day",
    "build_evaluation",
    "build_feature_sources",
    "build_forecast_artifact",
    "build_seasonal_priors_by_day",
    "build_seasonality_by_month",
    "clear_model_cache",
    "get_all_location_counts",
    "get_data",
    "get_model_bundle",
    "get_seasonality_score",
    "predict_today",
    "prepare_features",
    "train_model",
]
