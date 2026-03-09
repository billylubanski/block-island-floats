from flask import Flask, render_template, request
import requests
import datetime
import json
import sqlite3
import os
from collections import Counter
from analyzer import normalize_location, analyze_dates, analyze_unreported_floats, get_year_recovery_stats
from locations import LOCATIONS
from utils import get_last_updated

app = Flask(__name__)
DB_NAME = 'floats.db'
TRUTHY_VALUES = {'1', 'true', 'yes', 'on'}
DEFAULT_VALID_ONLY = os.getenv('IGNORE_INVALID_ROWS', '').strip().lower() in TRUTHY_VALUES
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
FIELD_ETIQUETTE_PATH = os.path.join(APP_ROOT, 'data', 'field_etiquette.json')
DEFAULT_FIELD_ETIQUETTE = {
    'title': 'Field Etiquette',
    'intro': 'Official float-hunting guidance for use while you are out on the trail.',
    'rules_heading': 'Hunt respectfully',
    'rules': [
        'Stay on established trails.',
        'Search near trails or between the bluffs and the high tide line.',
        'Do not dismantle stone walls.',
        'Do not whack vegetation.',
        'Stay off dunes.',
        'Keep pets on a leash.',
        'Look up. Floats may be hidden in trees.',
        'One float per person per year.',
    ],
    'restricted_heading': 'Floats are NOT hidden on',
    'restricted_locations': [
        'Dunes or up bluffs',
        '"The Maze"',
        'School grounds',
        'Island cemeteries',
        'Private homes',
        'Flowerbeds',
        'The Statue of Rebecca',
    ],
}


def load_field_etiquette():
    try:
        with open(FIELD_ETIQUETTE_PATH, encoding='utf-8') as etiquette_file:
            return json.load(etiquette_file)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Warning: using fallback field etiquette content: {exc}")
        return DEFAULT_FIELD_ETIQUETTE.copy()


FIELD_ETIQUETTE = load_field_etiquette()

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def finds_supports_validation(conn):
    table_info = conn.execute("PRAGMA table_info(finds)").fetchall()
    return any(col[1] == 'is_valid' for col in table_info)


def valid_only_enabled():
    value = request.args.get('valid_only')
    if value is None:
        return DEFAULT_VALID_ONLY
    return value.strip().lower() in TRUTHY_VALUES


def build_finds_where_clause(year_param=None, valid_only=False, supports_validation=False):
    clauses = []
    params = []
    if year_param is not None:
        clauses.append('year = ?')
        params.append(year_param)
    if valid_only and supports_validation:
        clauses.append('COALESCE(is_valid, 1) = 1')
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    return where, params


@app.context_processor
def inject_filters():
    return {'valid_only': valid_only_enabled()}

# Simple in-memory cache for weather data
weather_cache = {
    'data': None,
    'timestamp': None
}

def get_weather_data():
    """
    Fetch current weather for Block Island (Station KBID) from NOAA API.
    Caches data for 15 minutes to avoid rate limiting.
    """
    global weather_cache
    
    # Check cache (15 minute expiration)
    now = datetime.datetime.now()
    if (weather_cache['data'] and weather_cache['timestamp'] and 
        (now - weather_cache['timestamp']).total_seconds() < 900):
        return weather_cache['data']
        
    try:
        # NOAA API requires a User-Agent
        headers = {
            'User-Agent': '(glassfloattracker.com, contact@glassfloattracker.com)',
            'Accept': 'application/geo+json'
        }
        
        # Station KBID is Block Island State Airport
        url = "https://api.weather.gov/stations/KBID/observations/latest"
        
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            props = data.get('properties', {})
            
            # Extract relevant data
            temp_c = props.get('temperature', {}).get('value')
            wind_speed_kmh = props.get('windSpeed', {}).get('value')
            text_desc = props.get('textDescription', 'Unknown')
            icon_url = props.get('icon', '')
            
            # Convert units
            temp_f = round((temp_c * 9/5) + 32) if temp_c is not None else None
            wind_mph = round(wind_speed_kmh * 0.621371) if wind_speed_kmh is not None else None
            
            # Map text description to emoji
            desc_lower = text_desc.lower()
            if 'sunny' in desc_lower or 'clear' in desc_lower:
                emoji = '☀️'
            elif 'partly cloudy' in desc_lower:
                emoji = '⛅'
            elif 'cloudy' in desc_lower or 'overcast' in desc_lower:
                emoji = '☁️'
            elif 'rain' in desc_lower or 'drizzle' in desc_lower or 'shower' in desc_lower:
                emoji = '☔'
            elif 'thunder' in desc_lower:
                emoji = '⛈️'
            elif 'snow' in desc_lower:
                emoji = '❄️'
            elif 'fog' in desc_lower or 'mist' in desc_lower:
                emoji = '🌫️'
            elif 'wind' in desc_lower:
                emoji = '💨'
            else:
                emoji = '🌡️' # Thermometer as default
                
            weather_data = {
                'temp': temp_f,
                'condition': text_desc,
                'wind': wind_mph,
                'emoji': emoji,
                'timestamp': now.strftime("%I:%M %p")
            }
            
            # Update cache
            weather_cache['data'] = weather_data
            weather_cache['timestamp'] = now
            
            return weather_data
            
    except Exception as e:
        print(f"Error fetching weather: {e}")
        
    return None

@app.route('/')
def index():
    conn = get_db_connection()

    valid_only = valid_only_enabled()
    supports_validation = finds_supports_validation(conn)

    # Get year filter from query parameter
    selected_year = request.args.get('year', 'all')
    year_param = None
    if selected_year != 'all':
        try:
            year_param = int(selected_year)
        except ValueError:
            selected_year = 'all'

    where_clause, where_params = build_finds_where_clause(
        year_param=year_param,
        valid_only=valid_only,
        supports_validation=supports_validation,
    )

    # Get total finds (filtered)
    total_finds = conn.execute(
        f'SELECT count(*) FROM finds {where_clause}',
        where_params,
    ).fetchone()[0]
    
    # Get year recovery statistics (hidden, found, recovery rate for each year)
    year_recovery_stats = get_year_recovery_stats(valid_only=valid_only)
    
    # Calculate total floats hidden across all years
    total_hidden_all_years = sum(year['hidden'] for year in year_recovery_stats)
    
    # Get date analysis stats (filtered)
    date_stats = analyze_dates(year_param, valid_only=valid_only)
    best_months = date_stats['best_months']
    total_dates_analyzed = date_stats['total_dates_analyzed']
    
    # Get unreported float stats (only for specific years, not "all")
    # Float numbers are reused each year, so aggregation across years doesn't make sense
    if year_param is not None:
        unreported_stats = analyze_unreported_floats(year_param, valid_only=valid_only)
    else:
        unreported_stats = None
    
    # Get top locations (filtered)
    all_locs = conn.execute(
        f'SELECT location_raw FROM finds {where_clause}',
        where_params,
    ).fetchall()
    
    normalized_locs = [normalize_location(row['location_raw']) for row in all_locs]
    loc_counts = Counter(normalized_locs)
    
    # Attach coordinates
    top_locs = []
    map_markers = []
    
    # Get all locations that have coordinates, plus top 20 even if they don't (to show in list)
    for loc, count in loc_counts.most_common(100):
        coords = LOCATIONS.get(loc, None)
        
        # Data for table (Top 20)
        if coords or count > 5: 
            top_locs.append({
                'name': loc,
                'count': count,
                'lat': coords['lat'] if coords else None,
                'lon': coords['lon'] if coords else None
            })
            if len(top_locs) >= 20:
                break
            
    # Data for map (Top 30 with coordinates)
    for loc, count in loc_counts.most_common():
        coords = LOCATIONS.get(loc, None)
        if coords:
            map_markers.append({
                'name': loc,
                'count': count,
                'lat': coords['lat'],
                'lon': coords['lon']
            })
            if len(map_markers) >= 30:
                break
    
    conn.close()
    
    # Get last updated timestamp
    last_updated = get_last_updated()
    
    return render_template('index.html', 
                           total_finds=total_finds,
                           total_hidden_all_years=total_hidden_all_years,
                           years=year_recovery_stats,
                           top_locs=top_locs,
                           map_markers=map_markers,
                           best_months=best_months,
                           total_dates_analyzed=total_dates_analyzed,
                           unreported_stats=unreported_stats,
                           last_updated=last_updated,
                           selected_year=selected_year)

@app.route('/search')
def search():
    valid_only = valid_only_enabled()
    query = request.args.get('q', '')
    conn = get_db_connection()
    supports_validation = finds_supports_validation(conn)
    if query:
        params = [f'%{query}%', f'%{query}%', f'%{query}%']
        conditions = ['(finder LIKE ? OR location_raw LIKE ? OR float_number LIKE ?)']
        if valid_only and supports_validation:
            conditions.append('COALESCE(is_valid, 1) = 1')
        results = conn.execute(
            f"SELECT * FROM finds WHERE {' AND '.join(conditions)} LIMIT 50",
            params,
        ).fetchall()
    else:
        results = []
    conn.close()
    return render_template('search.html', results=results, query=query)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/field')
def field_mode():
    """Mobile-optimized field mode for on-island hunting"""
    conn = get_db_connection()
    valid_only = valid_only_enabled()
    supports_validation = finds_supports_validation(conn)

    # Get all locations with coordinates and their find counts
    query = 'SELECT location_raw FROM finds'
    if valid_only and supports_validation:
        query += ' WHERE COALESCE(is_valid, 1) = 1'
    all_locs = conn.execute(query).fetchall()
    normalized_locs = [normalize_location(row['location_raw']) for row in all_locs]
    loc_counts = Counter(normalized_locs)
    
    # Build location list with coordinates
    hunting_spots = []
    for loc, count in loc_counts.most_common():
        coords = LOCATIONS.get(loc, None)
        if coords:  # Only include locations we can navigate to
            hunting_spots.append({
                'name': loc,
                'count': count,
                'lat': coords['lat'],
                'lon': coords['lon']
            })
    
    conn.close()
    
    # Get last updated
    last_updated = get_last_updated()
    
    # Get current weather
    weather = get_weather_data()
    
    return render_template('field.html',
                          hunting_spots=hunting_spots,
                          last_updated=last_updated,
                          weather=weather,
                          etiquette=FIELD_ETIQUETTE)

@app.route('/location/<path:location_name>')
def location_detail(location_name):
    """Detail page for a specific location showing all finds and photos"""
    conn = get_db_connection()
    valid_only = valid_only_enabled()
    supports_validation = finds_supports_validation(conn)

    # Get all finds and filter by normalizing location_raw
    # (location_normalized column is not populated in DB, normalization happens on the fly)
    finds_query = 'SELECT * FROM finds'
    if valid_only and supports_validation:
        finds_query += ' WHERE COALESCE(is_valid, 1) = 1'
    finds_query += ' ORDER BY year DESC, date_found DESC'
    all_finds = conn.execute(
        finds_query
    ).fetchall()
    
    # Filter finds by normalizing the location_raw
    finds = [f for f in all_finds if normalize_location(f['location_raw']) == location_name]
    
    if not finds:
        conn.close()
        return "Location not found", 404
    
    # Calculate stats
    total_finds = len(finds)
    years = {}
    finders = {}
    images = []
    
    for find in finds:
        # Year distribution
        year = find['year']
        years[year] = years.get(year, 0) + 1
        
        # Top finders
        finder = find['finder']
        if finder:
            finders[finder] = finders.get(finder, 0) + 1
        
        # Collect images
        if find['image_url']:
            # Filter out generic Block Island logo/placeholder images
            image_url = find['image_url']
            is_placeholder = 'default_image' in image_url
            
            if not is_placeholder:
                images.append({
                    'url': find['image_url'],
                    'finder': finder,
                    'year': year,
                    'float_number': find['float_number'],
                    'date': find['date_found']
                })
    
    # Get coordinates
    coords = LOCATIONS.get(location_name, None)
    
    # Top stats
    peak_year = max(years.items(), key=lambda x: x[1]) if years else (None, 0)
    top_finder = max(finders.items(), key=lambda x: x[1]) if finders else (None, 0)
    
    conn.close()
    
    return render_template('location_detail.html',
                          location_name=location_name,
                          total_finds=total_finds,
                          finds=finds,
                          images=images,
                          coords=coords,
                          peak_year=peak_year,
                          top_finder=top_finder,
                          years=sorted(years.items(), reverse=True))

from ml_predictor import predict_today, get_seasonality_score

@app.route('/forecast')
def forecast():
    """Show float forecast for today"""
    valid_only = valid_only_enabled()
    predictions = predict_today(valid_only=valid_only)
    seasonality = get_seasonality_score(valid_only=valid_only)
    
    # Get weather for context
    weather = get_weather_data()
    
    return render_template('forecast.html', 
                          predictions=predictions,
                          seasonality=seasonality,
                          weather=weather)

@app.route('/sw.js')
def service_worker():
    from flask import send_from_directory
    response = send_from_directory('static', 'sw.js')
    response.headers['Cache-Control'] = 'no-cache'
    return response

if __name__ == '__main__':
    app.run(debug=True, port=5000)
