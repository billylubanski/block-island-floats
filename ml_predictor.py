import sqlite3
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
import pickle
import os
from datetime import datetime

from analyzer import normalize_location

DB_NAME = 'floats.db'
MODEL_FILE = 'float_model.pkl'


def _finds_has_column(conn, column_name):
    info = conn.execute("PRAGMA table_info(finds)").fetchall()
    return any(col[1] == column_name for col in info)


def _model_file_for_mode(model_file, valid_only):
    if not valid_only:
        return model_file
    root, ext = os.path.splitext(model_file)
    return f"{root}_valid{ext}"


def get_data(db_name=DB_NAME, valid_only=False):
    """Fetch and prepare data from the database."""
    conn = sqlite3.connect(db_name)
    query = "SELECT date_found, location_raw FROM finds WHERE date_found IS NOT NULL AND date_found != ''"
    if valid_only and _finds_has_column(conn, "is_valid"):
        query += " AND COALESCE(is_valid, 1) = 1"
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # Normalize locations
    df['location_normalized'] = df['location_raw'].apply(normalize_location)
    # Filter out "Other/Unknown" if desired, or keep them. 
    # For prediction, maybe we want to exclude them? 
    # Let's keep them for now but maybe the user doesn't want to go to "Other/Unknown" page.
    # Actually, "Other/Unknown" might be a valid bucket, but the link /location/Other/Unknown might be weird.
    # Let's filter out 'Other/Unknown' for better predictions of actual places.
    df = df[df['location_normalized'] != 'Other/Unknown']
    
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
    df['dt'] = df['date_found'].apply(parse_date)
    df = df.dropna(subset=['dt'])
    
    # Cyclic features for day of year
    df['day_of_year'] = df['dt'].dt.dayofyear
    df['sin_day'] = np.sin(2 * np.pi * df['day_of_year'] / 365.0)
    df['cos_day'] = np.cos(2 * np.pi * df['day_of_year'] / 365.0)
    
    # Month
    df['month'] = df['dt'].dt.month
    
    return df

def train_model(db_name=DB_NAME, model_file=MODEL_FILE, valid_only=False):
    """Train the model and save it."""
    target_model_file = _model_file_for_mode(model_file, valid_only)
    print("Fetching data...")
    df = get_data(db_name=db_name, valid_only=valid_only)
    
    if len(df) < 10:
        print("Not enough data to train model.")
        return False

    print(f"Training on {len(df)} records...")
    df = prepare_features(df)
    
    # Target encoding
    le = LabelEncoder()
    df['target'] = le.fit_transform(df['location_normalized'])
    
    X = df[['sin_day', 'cos_day', 'month']]
    y = df['target']
    
    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    clf.fit(X, y)
    
    # Save model and encoder
    with open(target_model_file, 'wb') as f:
        pickle.dump({'model': clf, 'encoder': le}, f)
        
    print("Model trained and saved.")
    return True

def predict_today(valid_only=False):
    """Predict top 3 locations for today."""
    target_model_file = _model_file_for_mode(MODEL_FILE, valid_only)
    if not os.path.exists(target_model_file):
        print("Model not found. Training now...")
        if not train_model(valid_only=valid_only):
            return []
            
    with open(target_model_file, 'rb') as f:
        data = pickle.load(f)
        clf = data['model']
        le = data['encoder']
        
    today = datetime.now()
    day_of_year = today.timetuple().tm_yday
    sin_day = np.sin(2 * np.pi * day_of_year / 365.0)
    cos_day = np.cos(2 * np.pi * day_of_year / 365.0)
    month = today.month
    
    X_new = pd.DataFrame([[sin_day, cos_day, month]], columns=['sin_day', 'cos_day', 'month'])
    
    # Get probabilities
    probs = clf.predict_proba(X_new)[0]
    
    # Get top 3 indices
    top_3_idx = probs.argsort()[-3:][::-1]
    
    predictions = []
    for idx in top_3_idx:
        location = le.inverse_transform([idx])[0]
        probability = probs[idx]
        predictions.append({
            'location': location,
            'probability': round(probability * 100, 1)
        })
        
    return predictions

def get_seasonality_score(valid_only=False):
    """Get a simple seasonality score based on historical finds for this month."""
    conn = sqlite3.connect(DB_NAME)
    # Get total finds
    total_query = "SELECT count(*) FROM finds WHERE date_found IS NOT NULL"
    if valid_only and _finds_has_column(conn, "is_valid"):
        total_query += " AND COALESCE(is_valid, 1) = 1"
    total = conn.execute(total_query).fetchone()[0]
    
    # Get finds for current month
    current_month = datetime.now().month
    # This is a rough approximation since we store dates as strings. 
    # Ideally we'd use the parsed dates, but for speed we'll just query.
    # Actually, let's use the python parsing logic we already have in analyzer.py or just re-implement simple check
    
    # Let's just use the dataframe logic since we have it
    df = get_data(valid_only=valid_only)
    df = prepare_features(df)
    
    month_counts = df['month'].value_counts()
    this_month_count = month_counts.get(current_month, 0)
    
    if total == 0: return 0
    
    # Average finds per month (uniform distribution) would be Total / 12
    avg_per_month = total / 12
    
    # Score: Ratio of this month's finds to average
    score = (this_month_count / avg_per_month) * 5 # Scale to 0-10 roughly
    
    return min(round(score, 1), 10)

if __name__ == "__main__":
    train_model()
    print("\nPrediction for today:")
    print(predict_today())
