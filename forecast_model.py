from __future__ import annotations

import os
import sqlite3
from collections import Counter, defaultdict
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import log_loss
from sklearn.preprocessing import LabelEncoder

from analyzer import normalize_location
from forecasting import (
    build_calendar_features,
    build_cluster_definitions,
    build_cluster_lookup,
    empty_forecast_artifact,
    gaussian_kernel,
    moon_illumination_bucket,
    parse_date,
)

DB_NAME = "floats.db"
MIN_TRAINING_ROWS = 10
KERNEL_SIGMA = 21.0
SMOOTHING_ALPHA = 0.5


def _empty_training_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["year", "date_found", "location_raw", "location_normalized"])


def get_data(db_name: str | None = None) -> pd.DataFrame:
    resolved_db_name = db_name or DB_NAME
    if not os.path.exists(resolved_db_name):
        return _empty_training_frame()

    try:
        with sqlite3.connect(resolved_db_name) as conn:
            query = (
                "SELECT year, date_found, location_raw FROM finds "
                "WHERE date_found IS NOT NULL AND date_found != ''"
            )
            frame = pd.read_sql_query(query, conn)
    except sqlite3.Error:
        return _empty_training_frame()

    if frame.empty:
        return _empty_training_frame()

    frame = frame.copy()
    frame["location_normalized"] = frame["location_raw"].apply(normalize_location)
    frame = frame[frame["location_normalized"] != "Other/Unknown"].copy()
    return frame


def get_all_location_counts(db_name: str | None = None) -> Counter[str]:
    resolved_db_name = db_name or DB_NAME
    counts: Counter[str] = Counter()
    if not os.path.exists(resolved_db_name):
        return counts

    try:
        with sqlite3.connect(resolved_db_name) as conn:
            rows = conn.execute("SELECT location_raw FROM finds").fetchall()
    except sqlite3.Error:
        return counts

    for (location_raw,) in rows:
        normalized = normalize_location(location_raw)
        if normalized != "Other/Unknown":
            counts[normalized] += 1
    return counts


def prepare_features(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()

    prepared = frame.copy()
    prepared["dt"] = prepared["date_found"].apply(parse_date)
    prepared = prepared.dropna(subset=["dt"]).copy()
    if prepared.empty:
        return prepared

    prepared["actual_year"] = prepared["dt"].dt.year.astype(int)
    prepared["day_of_year"] = prepared["dt"].dt.dayofyear.astype(int)
    prepared["sin_day"] = np.sin(2 * np.pi * prepared["day_of_year"] / 365.0)
    prepared["cos_day"] = np.cos(2 * np.pi * prepared["day_of_year"] / 365.0)
    prepared["month"] = prepared["dt"].dt.month.astype(int)

    calendar_rows = prepared["dt"].dt.date.apply(build_calendar_features)
    calendar_frame = pd.DataFrame(list(calendar_rows), index=prepared.index)
    calendar_frame = calendar_frame.drop(columns=["day_of_year", "month"], errors="ignore")
    prepared = pd.concat([prepared, calendar_frame], axis=1)
    prepared["moon_illumination_bucket"] = prepared["moon_illumination"].apply(moon_illumination_bucket)
    return prepared


def build_seasonality_by_month(frame: pd.DataFrame) -> dict[str, float]:
    scores = {str(month): 0.0 for month in range(1, 13)}
    total = len(frame)
    if total == 0:
        return scores

    month_counts = frame["month"].value_counts()
    avg_per_month = total / 12
    for month in range(1, 13):
        count = int(month_counts.get(month, 0))
        score = (count / avg_per_month) * 5 if avg_per_month else 0
        scores[str(month)] = round(min(score, 10), 1)
    return scores


def attach_cluster_labels(
    frame: pd.DataFrame,
    *,
    location_counts: Counter[str],
) -> tuple[pd.DataFrame, dict[str, str], dict[str, dict[str, Any]]]:
    lookup = build_cluster_lookup(location_counts)
    definitions = {
        definition["label"]: definition
        for definition in build_cluster_definitions(location_counts)
    }
    if frame.empty:
        return frame.copy(), lookup, definitions

    mapped = frame[frame["location_normalized"].isin(lookup)].copy()
    mapped["cluster_label"] = mapped["location_normalized"].map(lookup)
    return mapped, lookup, definitions


def smoothed_ratio(match_count: int, total_count: int, global_rate: float, alpha: float = 2.0) -> float:
    if total_count <= 0 or global_rate <= 0:
        return 1.0
    smoothed = (match_count + (alpha * global_rate)) / (total_count + alpha)
    return round(smoothed / global_rate, 4)


def build_activity_index_by_day(frame: pd.DataFrame) -> dict[str, float]:
    if frame.empty:
        return {str(day): 0.0 for day in range(1, 367)}

    observation_days = frame["day_of_year"].astype(int).tolist()
    raw_scores: dict[str, float] = {}
    for day in range(1, 367):
        score = sum(gaussian_kernel(min(abs(observed - day), 366 - abs(observed - day)), sigma=KERNEL_SIGMA) for observed in observation_days)
        raw_scores[str(day)] = score

    average_score = sum(raw_scores.values()) / len(raw_scores) if raw_scores else 0.0
    if average_score <= 0:
        return {str(day): 0.0 for day in range(1, 367)}

    return {
        day_key: round(min((score / average_score) * 5, 10), 1)
        for day_key, score in raw_scores.items()
    }


def build_seasonal_priors_by_day(frame: pd.DataFrame, *, label_col: str) -> dict[str, dict[str, float]]:
    priors = {str(day): {} for day in range(1, 367)}
    if frame.empty or label_col not in frame.columns:
        return priors

    labels = sorted(frame[label_col].dropna().unique().tolist())
    label_days = {
        label: frame.loc[frame[label_col] == label, "day_of_year"].astype(int).tolist()
        for label in labels
    }
    for day in range(1, 367):
        scores = {}
        for label in labels:
            days = label_days.get(label, [])
            if not days:
                continue
            score = sum(
                gaussian_kernel(min(abs(observed - day), 366 - abs(observed - day)), sigma=KERNEL_SIGMA)
                for observed in days
            )
            if score > 0:
                scores[label] = score
        total = sum(scores.values())
        if total > 0:
            priors[str(day)] = {
                label: round(score / total, 6)
                for label, score in scores.items()
            }
    return priors


def build_calendar_affinity(frame: pd.DataFrame, *, label_col: str) -> dict[str, dict[str, Any]]:
    if frame.empty:
        return {}

    total_rows = len(frame)
    global_weekday = frame["weekday_name"].value_counts().to_dict()
    global_weekend_rate = float(frame["is_weekend"].mean()) if total_rows else 0.0
    global_holiday_rate = float(frame["is_holiday"].mean()) if total_rows else 0.0
    global_long_weekend_rate = float(frame["is_long_weekend"].mean()) if total_rows else 0.0
    global_moon_phase = frame["moon_phase"].value_counts().to_dict()
    global_moon_bucket = frame["moon_illumination_bucket"].value_counts().to_dict()

    affinities: dict[str, dict[str, Any]] = {}
    for label, group in frame.groupby(label_col):
        row_count = len(group)
        weekday_ratios = {
            weekday: smoothed_ratio(int(group["weekday_name"].eq(weekday).sum()), row_count, global_weekday.get(weekday, 0) / total_rows if total_rows else 0.0)
            for weekday in sorted(global_weekday)
        }
        moon_phase_ratios = {
            phase: smoothed_ratio(int(group["moon_phase"].eq(phase).sum()), row_count, global_moon_phase.get(phase, 0) / total_rows if total_rows else 0.0)
            for phase in sorted(global_moon_phase)
        }
        moon_bucket_ratios = {
            bucket: smoothed_ratio(int(group["moon_illumination_bucket"].eq(bucket).sum()), row_count, global_moon_bucket.get(bucket, 0) / total_rows if total_rows else 0.0)
            for bucket in sorted(global_moon_bucket)
        }
        affinities[label] = {
            "weekday_ratios": weekday_ratios,
            "weekend_ratio": smoothed_ratio(int(group["is_weekend"].sum()), row_count, global_weekend_rate),
            "holiday_ratio": smoothed_ratio(int(group["is_holiday"].sum()), row_count, global_holiday_rate),
            "long_weekend_ratio": smoothed_ratio(int(group["is_long_weekend"].sum()), row_count, global_long_weekend_rate),
            "moon_phase_ratios": moon_phase_ratios,
            "moon_illumination_ratios": moon_bucket_ratios,
        }
    return affinities


def build_cluster_profiles(
    mapped_frame: pd.DataFrame,
    *,
    cluster_definitions: dict[str, dict[str, Any]],
    location_counts: Counter[str],
) -> dict[str, dict[str, Any]]:
    calendar_affinity = build_calendar_affinity(mapped_frame, label_col="cluster_label")
    profiles: dict[str, dict[str, Any]] = {}

    for label, definition in cluster_definitions.items():
        group = mapped_frame.loc[mapped_frame["cluster_label"] == label].copy()
        month_counts = group["month"].value_counts().sort_values(ascending=False) if not group.empty else pd.Series(dtype=int)
        best_months = [
            pd.Timestamp(year=2025, month=int(month), day=1).strftime("%B")
            for month in month_counts.index[:3]
        ]
        supporting_spots = [
            {"name": spot, "count": int(location_counts.get(spot, 0))}
            for spot in definition["spots"][:5]
        ]

        profiles[label] = {
            "label": label,
            "lat": definition["lat"],
            "lon": definition["lon"],
            "tags": definition["tags"],
            "spot_count": definition["spot_count"],
            "support_count": int(definition["support_count"]),
            "dated_support_count": int(len(group)),
            "actual_years": sorted({int(year) for year in group["actual_year"].tolist()}) if not group.empty else [],
            "primary_spot": supporting_spots[0]["name"] if supporting_spots else label,
            "supporting_spots": supporting_spots,
            "best_months": best_months,
            "feature_coverage": {
                "calendar_rows": int(len(group)),
                "historical_weather_rows": 0,
                "tide_rows": 0,
                "recency_rows": int(len(group)),
            },
            "calendar_affinity": calendar_affinity.get(label, {}),
        }
    return profiles


def _normalize_distribution(raw_scores: dict[str, float], label_space: list[str]) -> dict[str, float]:
    if not label_space:
        return {}

    adjusted = {label: float(raw_scores.get(label, 0.0)) + SMOOTHING_ALPHA for label in label_space}
    total = sum(adjusted.values())
    if total <= 0:
        uniform = 1.0 / len(label_space)
        return {label: uniform for label in label_space}
    return {label: value / total for label, value in adjusted.items()}


def _distribution_global(train_frame: pd.DataFrame, *, label_col: str, label_space: list[str]) -> dict[str, float]:
    counts = train_frame[label_col].value_counts().to_dict()
    return _normalize_distribution(counts, label_space)


def _distribution_month(train_frame: pd.DataFrame, *, month: int, label_col: str, label_space: list[str]) -> dict[str, float]:
    month_frame = train_frame.loc[train_frame["month"] == month]
    if month_frame.empty:
        return _distribution_global(train_frame, label_col=label_col, label_space=label_space)
    counts = month_frame[label_col].value_counts().to_dict()
    return _normalize_distribution(counts, label_space)


def _distribution_kernel(
    train_frame: pd.DataFrame,
    *,
    target_day: int,
    label_col: str,
    label_space: list[str],
) -> dict[str, float]:
    scores = defaultdict(float)
    for observed_day, label in train_frame[["day_of_year", label_col]].itertuples(index=False):
        distance = min(abs(int(observed_day) - int(target_day)), 366 - abs(int(observed_day) - int(target_day)))
        scores[label] += gaussian_kernel(distance, sigma=KERNEL_SIGMA)
    return _normalize_distribution(dict(scores), label_space)


def _distribution_hybrid(
    train_frame: pd.DataFrame,
    *,
    target_row: pd.Series,
    label_col: str,
    label_space: list[str],
    calendar_affinity: dict[str, dict[str, Any]],
) -> dict[str, float]:
    base = _distribution_kernel(train_frame, target_day=int(target_row["day_of_year"]), label_col=label_col, label_space=label_space)
    scores = {}
    for label in label_space:
        profile = calendar_affinity.get(label, {})
        multiplier = 1.0
        weekday_ratios = profile.get("weekday_ratios", {})
        multiplier *= float(weekday_ratios.get(target_row["weekday_name"], 1.0))
        if bool(target_row["is_weekend"]):
            multiplier *= float(profile.get("weekend_ratio", 1.0))
        if bool(target_row["is_holiday"]):
            multiplier *= float(profile.get("holiday_ratio", 1.0))
        elif bool(target_row["is_long_weekend"]):
            multiplier *= float(profile.get("long_weekend_ratio", 1.0))
        multiplier *= float(profile.get("moon_phase_ratios", {}).get(target_row["moon_phase"], 1.0))
        multiplier *= float(profile.get("moon_illumination_ratios", {}).get(target_row["moon_illumination_bucket"], 1.0))
        scores[label] = base.get(label, 0.0) * min(max(multiplier, 0.7), 1.35)
    return _normalize_distribution(scores, label_space)


def _rf_distributions(
    train_frame: pd.DataFrame,
    test_frame: pd.DataFrame,
    *,
    label_col: str,
    label_space: list[str],
) -> list[dict[str, float]]:
    if train_frame.empty or len(train_frame[label_col].dropna().unique()) < 2:
        fallback = _distribution_global(train_frame, label_col=label_col, label_space=label_space)
        return [fallback for _ in range(len(test_frame))]

    encoder = LabelEncoder()
    encoded_targets = encoder.fit_transform(train_frame[label_col])
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    feature_cols = ["sin_day", "cos_day", "month"]
    model.fit(train_frame[feature_cols], encoded_targets)

    probabilities = model.predict_proba(test_frame[feature_cols])
    distributions = []
    for row_probs in probabilities:
        raw = {label: 0.0 for label in label_space}
        for encoded_label, probability in zip(model.classes_, row_probs):
            label = encoder.inverse_transform([encoded_label])[0]
            raw[label] = float(probability)
        distributions.append(_normalize_distribution(raw, label_space))
    return distributions


def _expected_calibration_error(prob_matrix: np.ndarray, true_indices: np.ndarray, bins: int = 10) -> float:
    if prob_matrix.size == 0 or true_indices.size == 0:
        return 0.0

    confidences = prob_matrix.max(axis=1)
    predictions = prob_matrix.argmax(axis=1)
    accuracies = predictions == true_indices
    edges = np.linspace(0.0, 1.0, bins + 1)
    ece = 0.0
    for lower, upper in zip(edges[:-1], edges[1:]):
        if upper == 1.0:
            mask = (confidences >= lower) & (confidences <= upper)
        else:
            mask = (confidences >= lower) & (confidences < upper)
        if not np.any(mask):
            continue
        ece += abs(float(accuracies[mask].mean()) - float(confidences[mask].mean())) * float(mask.mean())
    return round(ece, 6)


def _summarize_distributions(
    y_true: list[str],
    distributions: list[dict[str, float]],
    *,
    label_space: list[str],
) -> dict[str, Any]:
    if not y_true or not distributions:
        return {}

    label_index = {label: idx for idx, label in enumerate(label_space)}
    prob_matrix = np.array(
        [
            [max(float(distribution.get(label, 0.0)), 1e-9) for label in label_space]
            for distribution in distributions
        ]
    )
    prob_matrix = prob_matrix / prob_matrix.sum(axis=1, keepdims=True)
    true_indices = np.array([label_index[label] for label in y_true])
    predictions = prob_matrix.argmax(axis=1)

    top3_hits = 0
    for row_idx, probs in enumerate(prob_matrix):
        top_indices = probs.argsort()[-min(3, len(label_space)):][::-1]
        if true_indices[row_idx] in top_indices:
            top3_hits += 1

    return {
        "rows": int(len(y_true)),
        "classes": int(len(label_space)),
        "top1_accuracy": round(float((predictions == true_indices).mean()), 4),
        "top3_accuracy": round(float(top3_hits / len(y_true)), 4),
        "log_loss": round(float(log_loss(true_indices, prob_matrix, labels=list(range(len(label_space))))), 4),
        "calibration_gap": _expected_calibration_error(prob_matrix, true_indices),
    }


def evaluate_target(frame: pd.DataFrame, *, label_col: str, include_hybrid: bool) -> dict[str, dict[str, Any]]:
    if frame.empty or len(frame) < MIN_TRAINING_ROWS:
        return {}

    actual_years = sorted(frame["actual_year"].dropna().unique().tolist())
    if len(actual_years) < 2:
        return {}

    label_space = sorted(frame[label_col].dropna().unique().tolist())
    if len(label_space) < 2:
        return {}

    y_true: list[str] = []
    global_distributions: list[dict[str, float]] = []
    month_distributions: list[dict[str, float]] = []
    kernel_distributions: list[dict[str, float]] = []
    rf_distributions: list[dict[str, float]] = []
    hybrid_distributions: list[dict[str, float]] = []

    for holdout_year in actual_years:
        train_frame = frame.loc[frame["actual_year"] != holdout_year].copy()
        test_frame = frame.loc[frame["actual_year"] == holdout_year].copy()
        if train_frame.empty or test_frame.empty:
            continue

        global_dist = _distribution_global(train_frame, label_col=label_col, label_space=label_space)
        rf_fold = _rf_distributions(train_frame, test_frame, label_col=label_col, label_space=label_space)
        hybrid_affinity = build_calendar_affinity(train_frame, label_col=label_col) if include_hybrid else {}

        for offset, (_, row) in enumerate(test_frame.iterrows()):
            y_true.append(row[label_col])
            global_distributions.append(global_dist)
            month_distributions.append(
                _distribution_month(train_frame, month=int(row["month"]), label_col=label_col, label_space=label_space)
            )
            kernel_distributions.append(
                _distribution_kernel(
                    train_frame,
                    target_day=int(row["day_of_year"]),
                    label_col=label_col,
                    label_space=label_space,
                )
            )
            rf_distributions.append(rf_fold[offset])
            if include_hybrid:
                hybrid_distributions.append(
                    _distribution_hybrid(
                        train_frame,
                        target_row=row,
                        label_col=label_col,
                        label_space=label_space,
                        calendar_affinity=hybrid_affinity,
                    )
                )

    metrics = {
        "global_topk": _summarize_distributions(y_true, global_distributions, label_space=label_space),
        "month_frequency": _summarize_distributions(y_true, month_distributions, label_space=label_space),
        "kernel_seasonal": _summarize_distributions(y_true, kernel_distributions, label_space=label_space),
        "current_random_forest": _summarize_distributions(y_true, rf_distributions, label_space=label_space),
    }
    if include_hybrid:
        metrics["hybrid_zone"] = _summarize_distributions(y_true, hybrid_distributions, label_space=label_space)
    return metrics


def select_primary_model(cluster_metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    kernel_metrics = cluster_metrics.get("kernel_seasonal", {})
    hybrid_metrics = cluster_metrics.get("hybrid_zone", {})
    if not kernel_metrics:
        return {
            "primary_model": "kernel_seasonal",
            "gating_reason": "Cluster evaluation data is unavailable.",
            "eligible_models": [],
        }

    if hybrid_metrics:
        kernel_top3 = float(kernel_metrics.get("top3_accuracy", 0.0))
        hybrid_top3 = float(hybrid_metrics.get("top3_accuracy", 0.0))
        kernel_log_loss = float(kernel_metrics.get("log_loss", 999.0))
        hybrid_log_loss = float(hybrid_metrics.get("log_loss", 999.0))
        if kernel_top3 > 0 and hybrid_top3 >= (kernel_top3 * 1.10) and hybrid_log_loss < kernel_log_loss:
            return {
                "primary_model": "hybrid_zone",
                "gating_reason": (
                    f"Hybrid scorer cleared the gate with top-3 {hybrid_top3:.4f} vs kernel {kernel_top3:.4f} "
                    f"and lower log loss {hybrid_log_loss:.4f} vs {kernel_log_loss:.4f}."
                ),
                "eligible_models": ["kernel_seasonal", "hybrid_zone"],
            }

    return {
        "primary_model": "kernel_seasonal",
        "gating_reason": "Kernel seasonal baseline remains primary because the richer scorer did not clear the top-3 and log-loss gate.",
        "eligible_models": ["kernel_seasonal"] + (["hybrid_zone"] if hybrid_metrics else []),
    }


def build_evaluation(prepared_frame: pd.DataFrame, mapped_frame: pd.DataFrame) -> dict[str, Any]:
    exact_metrics = evaluate_target(prepared_frame, label_col="location_normalized", include_hybrid=False)
    cluster_metrics = evaluate_target(mapped_frame, label_col="cluster_label", include_hybrid=True)
    selection = select_primary_model(cluster_metrics)
    return {
        "targets": {
            "exact_location": exact_metrics,
            "cluster": cluster_metrics,
        },
        "selection": selection,
    }


def build_feature_sources(prepared_frame: pd.DataFrame) -> dict[str, Any]:
    actual_years = sorted({int(year) for year in prepared_frame["actual_year"].tolist()}) if not prepared_frame.empty else []
    return {
        "calendar": {
            "available": True,
            "features": [
                "day_of_year",
                "month",
                "weekday",
                "weekend",
                "holiday",
                "long_weekend",
                "moon_phase",
                "moon_illumination",
            ],
        },
        "recency": {
            "available": True,
            "windows": [7, 14, 30],
        },
        "historical_weather": {
            "available": bool(os.getenv("NOAA_CDO_TOKEN")),
            "provider": "NOAA NCEI CDO",
            "preferred_station": "KBID",
            "fallback_strategy": "Nearest NWS observation station",
            "coverage_years": actual_years,
        },
        "live_weather": {
            "available": True,
            "provider": "NWS API",
            "gridpoint": "BOX/63,33",
            "preferred_observation_station": "KBID",
        },
        "tide": {
            "available": True,
            "provider": "NOAA CO-OPS",
            "primary_station": "8459338",
            "fallback_station": "8459681",
        },
    }


def build_forecast_artifact(
    db_name: str | None = None,
    *,
    total_records: int = 0,
    latest_source_date: str = "",
    generated_at: str | None = None,
) -> dict[str, Any]:
    resolved_db_name = db_name or DB_NAME
    prepared = prepare_features(get_data(db_name=resolved_db_name))
    location_counts = get_all_location_counts(db_name=resolved_db_name)
    mapped, _, cluster_definitions = attach_cluster_labels(prepared, location_counts=location_counts)

    artifact = empty_forecast_artifact()
    artifact["generated_at"] = generated_at or pd.Timestamp.utcnow().replace(microsecond=0).isoformat() + "Z"
    artifact["source"] = {
        "total_records": int(total_records),
        "latest_source_date": latest_source_date,
        "training_rows": int(len(prepared)),
        "cluster_training_rows": int(len(mapped)),
        "actual_years": sorted({int(year) for year in prepared["actual_year"].tolist()}) if not prepared.empty else [],
    }
    artifact["seasonality_by_month"] = build_seasonality_by_month(prepared)
    artifact["activity_index_by_day"] = build_activity_index_by_day(prepared)
    artifact["cluster_profiles"] = build_cluster_profiles(
        mapped,
        cluster_definitions=cluster_definitions,
        location_counts=location_counts,
    )
    if len(mapped) >= MIN_TRAINING_ROWS:
        artifact["seasonal_priors_by_day"] = build_seasonal_priors_by_day(mapped, label_col="cluster_label")
        artifact["evaluation"] = build_evaluation(prepared, mapped)
    artifact["feature_sources"] = build_feature_sources(prepared)
    return artifact
