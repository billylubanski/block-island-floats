import os
import sqlite3
from datetime import datetime
from functools import lru_cache

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder

from analyzer import normalize_location

DB_NAME = "floats.db"
MAX_PREDICTIONS = 3
MIN_TRAINING_ROWS = 10


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
        "%B %d, %Y", "%b %d, %Y", "%B %Y", "%b %Y"
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

    # Cyclic features for day of year
    df["day_of_year"] = df["dt"].dt.dayofyear
    df["sin_day"] = np.sin(2 * np.pi * df["day_of_year"] / 365.0)
    df["cos_day"] = np.cos(2 * np.pi * df["day_of_year"] / 365.0)

    # Month
    df["month"] = df["dt"].dt.month

    return df


def _build_model_bundle(db_name):
    df = get_data(db_name=db_name)
    if len(df) < MIN_TRAINING_ROWS:
        return None

    df = prepare_features(df)
    if len(df) < MIN_TRAINING_ROWS:
        return None

    # Target encoding
    le = LabelEncoder()
    df["target"] = le.fit_transform(df["location_normalized"])

    X = df[["sin_day", "cos_day", "month"]]
    y = df["target"]

    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    clf.fit(X, y)

    return {"model": clf, "encoder": le}


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


def predict_today():
    """Predict top 3 locations for today."""
    data = get_model_bundle()
    if not data:
        return []

    clf = data["model"]
    le = data["encoder"]

    today = datetime.now()
    day_of_year = today.timetuple().tm_yday
    sin_day = np.sin(2 * np.pi * day_of_year / 365.0)
    cos_day = np.cos(2 * np.pi * day_of_year / 365.0)
    month = today.month

    X_new = pd.DataFrame([[sin_day, cos_day, month]], columns=["sin_day", "cos_day", "month"])

    # Get probabilities
    probs = clf.predict_proba(X_new)[0]

    # Get top 3 indices
    top_count = min(MAX_PREDICTIONS, len(probs))
    top_3_idx = probs.argsort()[-top_count:][::-1]

    predictions = []
    for idx in top_3_idx:
        location = le.inverse_transform([idx])[0]
        probability = probs[idx]
        predictions.append({
            "location": location,
            "probability": round(probability * 100, 1)
        })

    return predictions


def get_seasonality_score():
    """Get a simple seasonality score based on historical finds for this month."""
    df = get_data()
    df = prepare_features(df)
    total = len(df)

    if total == 0:
        return 0

    current_month = datetime.now().month

    month_counts = df["month"].value_counts()
    this_month_count = int(month_counts.get(current_month, 0))

    # Average finds per month (uniform distribution) would be Total / 12
    avg_per_month = total / 12

    # Score: Ratio of this month's finds to average
    score = (this_month_count / avg_per_month) * 5  # Scale to 0-10 roughly

    return min(round(score, 1), 10)


if __name__ == "__main__":
    if train_model():
        print("\nPrediction for today:")
        print(predict_today())
    else:
        print("Not enough data to train the forecast model.")
