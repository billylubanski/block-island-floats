import os
import sqlite3
from datetime import datetime, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder

from analyzer import normalize_location

DB_NAME = "floats.db"
MAX_PREDICTIONS = 3
MIN_TRAINING_ROWS = 10
REFERENCE_LEAP_YEAR = 2024


def _empty_training_frame():
    return pd.DataFrame(columns=["date_found", "location_raw", "location_normalized"])


def get_data(db_name=None):
    """Fetch and prepare data from the database."""
    if db_name is None:
        db_name = DB_NAME

    if not os.path.exists(db_name):
        return _empty_training_frame()

    try:
        with sqlite3.connect(db_name) as conn:
            query = "SELECT date_found, location_raw FROM finds WHERE date_found IS NOT NULL AND date_found != ''"
            df = pd.read_sql_query(query, conn)
    except sqlite3.Error:
        return _empty_training_frame()

    if df.empty:
        return _empty_training_frame()

    df = df.copy()
    df["location_normalized"] = df["location_raw"].apply(normalize_location)
    df = df[df["location_normalized"] != "Other/Unknown"].copy()
    return df


def parse_date(date_str):
    """Parse date string to datetime object."""
    formats = [
        "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y",
        "%B %d, %Y", "%b %d, %Y", "%B %Y", "%b %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def prepare_features(df):
    """Feature engineering."""
    if df.empty:
        return df.copy()

    df = df.copy()
    df["dt"] = df["date_found"].apply(parse_date)
    df = df.dropna(subset=["dt"]).copy()
    if df.empty:
        return df

    # Cyclic features for day of year.
    df["day_of_year"] = df["dt"].dt.dayofyear
    df["sin_day"] = np.sin(2 * np.pi * df["day_of_year"] / 365.0)
    df["cos_day"] = np.cos(2 * np.pi * df["day_of_year"] / 365.0)
    df["month"] = df["dt"].dt.month
    return df


def build_seasonality_by_month(df):
    scores = {str(month): 0 for month in range(1, 13)}
    total = len(df)
    if total == 0:
        return scores

    month_counts = df["month"].value_counts()
    avg_per_month = total / 12
    for month in range(1, 13):
        this_month_count = int(month_counts.get(month, 0))
        score = (this_month_count / avg_per_month) * 5
        scores[str(month)] = min(round(score, 1), 10)
    return scores


def _build_model_bundle_from_frame(df):
    if len(df) < MIN_TRAINING_ROWS:
        return None

    working = df.copy()
    encoder = LabelEncoder()
    working["target"] = encoder.fit_transform(working["location_normalized"])

    features = working[["sin_day", "cos_day", "month"]]
    targets = working["target"]

    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(features, targets)
    return {"model": model, "encoder": encoder}


def _build_model_bundle(db_name):
    return _build_model_bundle_from_frame(prepare_features(get_data(db_name=db_name)))


@lru_cache(maxsize=8)
def _get_cached_model_bundle(db_name, db_mtime_ns):
    return _build_model_bundle(db_name)


def clear_model_cache():
    _get_cached_model_bundle.cache_clear()


def train_model(db_name=None):
    """Train and return the in-memory model bundle."""
    resolved_db_name = db_name or DB_NAME
    return _build_model_bundle(resolved_db_name)


def get_model_bundle(db_name=None):
    resolved_db_name = db_name or DB_NAME
    if not os.path.exists(resolved_db_name):
        return None

    try:
        db_mtime_ns = os.stat(resolved_db_name).st_mtime_ns
    except OSError:
        return None

    return _get_cached_model_bundle(resolved_db_name, db_mtime_ns)


def _predict_for_day(model_bundle, day_of_year, month):
    if not model_bundle:
        return []

    model = model_bundle["model"]
    encoder = model_bundle["encoder"]

    sin_day = np.sin(2 * np.pi * day_of_year / 365.0)
    cos_day = np.cos(2 * np.pi * day_of_year / 365.0)
    feature_frame = pd.DataFrame([[sin_day, cos_day, month]], columns=["sin_day", "cos_day", "month"])
    probabilities = model.predict_proba(feature_frame)[0]

    top_count = min(MAX_PREDICTIONS, len(probabilities))
    top_indices = probabilities.argsort()[-top_count:][::-1]

    predictions = []
    for idx in top_indices:
        predictions.append(
            {
                "location": encoder.inverse_transform([idx])[0],
                "probability": round(float(probabilities[idx]) * 100, 1),
            }
        )
    return predictions


def _reference_month_for_day(day_of_year):
    reference_date = datetime(REFERENCE_LEAP_YEAR, 1, 1) + timedelta(days=day_of_year - 1)
    return reference_date.month


def build_predictions_by_day(model_bundle):
    predictions = {}
    for day_of_year in range(1, 367):
        predictions[str(day_of_year)] = _predict_for_day(
            model_bundle,
            day_of_year=day_of_year,
            month=_reference_month_for_day(day_of_year),
        )
    return predictions


def build_forecast_artifact(db_name=None, *, total_records=0, latest_source_date="", generated_at=None):
    resolved_db_name = db_name or DB_NAME
    prepared = prepare_features(get_data(db_name=resolved_db_name))
    model_bundle = _build_model_bundle_from_frame(prepared)

    return {
        "generated_at": generated_at or datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "source": {
            "total_records": total_records,
            "latest_source_date": latest_source_date,
            "training_rows": int(len(prepared)),
        },
        "seasonality_by_month": build_seasonality_by_month(prepared),
        "predictions_by_day": build_predictions_by_day(model_bundle),
    }


def predict_today():
    """Predict top 3 locations for today."""
    today = datetime.now()
    return _predict_for_day(get_model_bundle(), today.timetuple().tm_yday, today.month)


def get_seasonality_score():
    """Get a simple seasonality score based on historical finds for this month."""
    today = datetime.now()
    seasonality = build_seasonality_by_month(prepare_features(get_data()))
    return seasonality.get(str(today.month), 0)


if __name__ == "__main__":
    artifact = build_forecast_artifact()
    today = datetime.now()
    print("\nPrediction for today:")
    print(artifact["predictions_by_day"][str(today.timetuple().tm_yday)])
