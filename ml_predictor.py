import sqlite3
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
import pickle
import os
from datetime import datetime
import math

DB_NAME = 'floats.db'
MODEL_FILE = 'float_model.pkl'

def get_data():
    """Fetch and prepare data from the database."""
    conn = sqlite3.connect(DB_NAME)
    query = "SELECT date_found, location_normalized FROM finds WHERE date_found IS NOT NULL AND date_found != ''"
    df = pd.read_sql_query(query, conn)
    conn.close()
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

def train_model():
    """Train the model and save it."""
    print("Fetching data...")
    df = get_data()
    
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
    with open(MODEL_FILE, 'wb') as f:
        pickle.dump({'model': clf, 'encoder': le}, f)
        
    print("Model trained and saved.")
    return True

def predict_today():
    """Predict top 3 locations for today."""
    if not os.path.exists(MODEL_FILE):
        print("Model not found. Training now...")
        if not train_model():
            return []
            
    with open(MODEL_FILE, 'rb') as f:
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

def get_seasonality_score():
    """Get a simple seasonality score based on historical finds for this month."""
    conn = sqlite3.connect(DB_NAME)
    # Get total finds
    total = conn.execute("SELECT count(*) FROM finds WHERE date_found IS NOT NULL").fetchone()[0]
    
    # Get finds for current month
    current_month = datetime.now().month
    # This is a rough approximation since we store dates as strings. 
    # Ideally we'd use the parsed dates, but for speed we'll just query.
    # Actually, let's use the python parsing logic we already have in analyzer.py or just re-implement simple check
    
    # Let's just use the dataframe logic since we have it
    df = get_data()
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
