from flask import Flask, render_template, request, url_for
import requests
import datetime
import json
import sqlite3
import os
from collections import Counter, defaultdict
from functools import lru_cache
from analyzer import normalize_location, analyze_dates, analyze_unreported_floats, get_year_recovery_stats
from locations import LOCATIONS
from utils import get_last_updated

app = Flask(__name__)
DB_NAME = 'floats.db'
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
FIELD_ETIQUETTE_PATH = os.path.join(APP_ROOT, 'data', 'field_etiquette.json')
OFFICIAL_LINKS = {
    'project': 'https://www.blockislandinfo.com/glass-float-project/',
    'register': 'https://www.blockislandinfo.com/glass-float-project/register-floats/',
    'found': 'https://www.blockislandinfo.com/glass-float-project/found-floats/',
    'tips': 'https://www.blockislandinfo.com/glass-float-project/tips-and-etiquette/',
    'greenway': 'https://www.blockislandinfo.com/glass-float-project/greenway-trail-guide/',
    'archives': 'https://www.blockislandinfo.com/glass-float-project/found-float-archives/',
}
REPORT_FIND_URL = OFFICIAL_LINKS['register']
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
    'notes_heading': 'Field reminders',
    'notes': [
        'Most official hides are on beaches or marked Greenway trails, with a smaller number in other public places.',
        'Trail hides sit close to the edge of established paths. Do not cut a new route into the brush for a promising spot.',
        'Leave no trace and carry out any trash you notice while hunting.',
        'Check for ticks and poison ivy after longer walks.',
        'If you find a second float, leave it in place or re-hide it in an approved area so someone else can discover it.',
        'Register your float so the official archive can attach your find, photo, and story to the season record.',
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
    'resources_heading': 'Official resources',
    'resources': [
        {
            'label': 'Register floats',
            'href': OFFICIAL_LINKS['register'],
        },
        {
            'label': 'Greenway trail guide',
            'href': OFFICIAL_LINKS['greenway'],
        },
    ],
}


@app.context_processor
def inject_official_links():
    return {'official_links': OFFICIAL_LINKS}


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


def parse_selected_year(raw_year):
    """Return a sanitized year filter tuple of (selected_year, year_param)."""
    if raw_year in (None, "", "all"):
        return "all", None

    try:
        year = int(raw_year)
    except (TypeError, ValueError):
        return "all", None

    return str(year), year

def build_finds_where_clause(year_param=None):
    clauses = []
    params = []
    if year_param is not None:
        clauses.append('year = ?')
        params.append(year_param)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    return where, params


def build_cta(label, href, external=False):
    cta = {
        'label': label,
        'href': href,
    }
    if external:
        cta['external'] = True
    return cta


def build_page_meta(active_nav, mode, kicker, title, subtitle, primary_cta=None):
    page_meta = {
        'active_nav': active_nav,
        'mode': mode,
        'kicker': kicker,
        'title': title,
        'subtitle': subtitle,
    }
    if primary_cta:
        page_meta['primary_cta'] = primary_cta
    return page_meta


def get_db_mtime():
    try:
        return os.path.getmtime(DB_NAME)
    except OSError:
        return 0


@lru_cache(maxsize=16)
def _get_location_counts_cached(selected_year, db_mtime):
    year_param = None if selected_year == 'all' else int(selected_year)
    where_clause, where_params = build_finds_where_clause(year_param=year_param)

    conn = get_db_connection()
    all_locs = conn.execute(
        f'SELECT location_raw FROM finds {where_clause}',
        where_params,
    ).fetchall()
    conn.close()

    loc_counts = Counter(normalize_location(row['location_raw']) for row in all_locs)
    return tuple(loc_counts.items())


def get_location_counts(year_param=None):
    year_key = 'all' if year_param is None else str(year_param)
    return Counter(dict(_get_location_counts_cached(year_key, get_db_mtime())))


def build_mapped_spots(loc_counts):
    spots = []
    for loc, count in loc_counts.most_common():
        coords = LOCATIONS.get(loc)
        if not coords:
            continue

        spots.append({
            'name': loc,
            'count': count,
            'lat': coords['lat'],
            'lon': coords['lon'],
        })

    return spots


def build_map_clusters(spots):
    grouped = defaultdict(list)
    for spot in spots:
        grouped[(spot['lat'], spot['lon'])].append(spot)

    clusters = []
    for (lat, lon), group in grouped.items():
        ranked_group = sorted(group, key=lambda spot: (-spot['count'], spot['name']))
        total_count = sum(spot['count'] for spot in ranked_group)
        primary_spot = ranked_group[0]

        clusters.append({
            'lat': lat,
            'lon': lon,
            'count': total_count,
            'label': primary_spot['name'] if len(ranked_group) == 1 else f"{primary_spot['name']} area",
            'spot_count': len(ranked_group),
            'spots': [
                {
                    'name': spot['name'],
                    'count': spot['count'],
                }
                for spot in ranked_group[:5]
            ],
            'remaining_spot_count': max(len(ranked_group) - 5, 0),
        })

    return sorted(clusters, key=lambda cluster: (-cluster['count'], cluster['label']))


def build_dashboard_map_payload(spots):
    clusters = build_map_clusters(spots)
    max_count = max((cluster['count'] for cluster in clusters), default=1)

    return {
        'center': [41.17, -71.58],
        'clusters': clusters,
        'cluster_count': len(clusters),
        'spot_count': len(spots),
        'max_count': max_count,
        'top_cluster': clusters[0] if clusters else None,
    }

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
            wind_speed_mps = props.get('windSpeed', {}).get('value')
            text_desc = props.get('textDescription', 'Unknown')

            # NOAA reports wind speed in meters per second.
            temp_f = round((temp_c * 9/5) + 32) if temp_c is not None else None
            wind_mph = round(wind_speed_mps * 2.23694) if wind_speed_mps is not None else None
            
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

    # Get year filter from query parameter
    selected_year, year_param = parse_selected_year(request.args.get('year', 'all'))
    where_clause, where_params = build_finds_where_clause(year_param=year_param)
    # Get total finds (filtered)
    total_finds = conn.execute(
        f'SELECT count(*) FROM finds {where_clause}',
        where_params,
    ).fetchone()[0]
    
    # Get year recovery statistics (hidden, found, recovery rate for each year)
    year_recovery_stats = get_year_recovery_stats()
    
    # Calculate total floats hidden across all years
    total_hidden_all_years = sum(year['hidden'] for year in year_recovery_stats)
    total_found_all_years = sum(year['found'] for year in year_recovery_stats)
    
    # Get date analysis stats (filtered)
    date_stats = analyze_dates(year_param)
    best_months = date_stats['best_months']
    total_dates_analyzed = date_stats['total_dates_analyzed']
    
    # Get unreported float stats (only for specific years, not "all")
    # Float numbers are reused each year, so aggregation across years doesn't make sense
    if year_param is not None:
        unreported_stats = analyze_unreported_floats(year_param)
        still_out_there = unreported_stats['unreported']
    else:
        unreported_stats = None
        still_out_there = max(total_hidden_all_years - total_found_all_years, 0)
    
    loc_counts = get_location_counts(year_param=year_param)
    mapped_spots = build_mapped_spots(loc_counts)
    top_locs = mapped_spots[:20]
    dashboard_map = build_dashboard_map_payload(mapped_spots)
    
    conn.close()
    
    # Get last updated timestamp
    last_updated = get_last_updated()
    primary_location = top_locs[0] if top_locs else None
    best_month = best_months[0] if best_months else None
    best_recovery_year = max(
        year_recovery_stats,
        key=lambda row: row['recovery_rate'],
    ) if year_recovery_stats else None
    
    return render_template('index.html', 
                           total_finds=total_finds,
                           years=year_recovery_stats,
                           top_locs=top_locs,
                           dashboard_map=dashboard_map,
                           best_months=best_months,
                           total_dates_analyzed=total_dates_analyzed,
                           unreported_stats=unreported_stats,
                           still_out_there=still_out_there,
                           last_updated=last_updated,
                           selected_year=selected_year,
                           primary_location=primary_location,
                           best_month=best_month,
                           best_recovery_year=best_recovery_year,
                           page_meta=build_page_meta(
                               active_nav='dashboard',
                               mode='dashboard',
                               kicker='Block Island glass float tracker',
                               title='Read the island before you head out',
                               subtitle='Map-led recovery patterns, seasonal activity, and the spots that keep paying off.',
                               primary_cta=build_cta(
                                   label='Report a find',
                                   href=REPORT_FIND_URL,
                                   external=True,
                               ),
                           ))

@app.route('/search')
def search():
    query = request.args.get('q', '')
    conn = get_db_connection()
    if query:
        params = [f'%{query}%', f'%{query}%', f'%{query}%']
        conditions = ['(finder LIKE ? OR location_raw LIKE ? OR float_number LIKE ?)']
        results = conn.execute(
            (
                f"SELECT * FROM finds WHERE {' AND '.join(conditions)} "
                "ORDER BY year DESC, date_found DESC LIMIT 50"
            ),
            params,
        ).fetchall()
    else:
        results = []
    display_results = []
    for row in results:
        location_name = normalize_location(row['location_raw'])
        display_results.append({
            'year': row['year'],
            'float_number': row['float_number'],
            'finder': row['finder'] or 'Unknown finder',
            'location_name': location_name,
            'location_raw': row['location_raw'],
            'report_url': row['url'],
        })
    conn.close()
    return render_template(
        'search.html',
        results=display_results,
        query=query,
        result_count=len(display_results),
        page_meta=build_page_meta(
            active_nav='search',
            mode='utility',
            kicker='Search the archive',
            title='Trace finders, float numbers, and locations fast',
            subtitle='Pull signal out of the registry without losing the context behind each reported find.',
        ),
    )

@app.route('/about')
def about():
    return render_template(
        'about.html',
        page_meta=build_page_meta(
            active_nav='about',
            mode='story',
            kicker='Why this tool exists',
            title='Built for hunters who like evidence before mileage',
            subtitle='The tracker turns public reports into a practical read on where, when, and how to search respectfully.',
            primary_cta=build_cta(
                label='Report a found float',
                href=REPORT_FIND_URL,
                external=True,
            ),
        ),
    )

@app.route('/field')
def field_mode():
    """Mobile-optimized field mode for on-island hunting"""
    hunting_spots = build_mapped_spots(get_location_counts())
    
    # Get last updated
    last_updated = get_last_updated()
    
    # Get current weather
    weather = get_weather_data()
    
    return render_template('field.html',
                          hunting_spots=hunting_spots,
                          last_updated=last_updated,
                          weather=weather,
                          etiquette=FIELD_ETIQUETTE,
                          page_meta=build_page_meta(
                              active_nav='field',
                              mode='utility',
                              kicker='On-island guide',
                              title='Field mode',
                              subtitle='Get oriented fast, sort spots by distance, and move from the trailhead with less friction.',
                          ))

@app.route('/location/<path:location_name>')
def location_detail(location_name):
    """Detail page for a specific location showing all finds and photos"""
    conn = get_db_connection()

    # Get all finds and filter by normalizing location_raw
    # (location_normalized column is not populated in DB, normalization happens on the fly)
    finds_query = 'SELECT * FROM finds'
    finds_query += ' ORDER BY year DESC, date_found DESC'
    all_finds = conn.execute(
        finds_query
    ).fetchall()
    
    # Filter finds by normalizing the location_raw
    finds = [f for f in all_finds if normalize_location(f['location_raw']) == location_name]
    
    if not finds:
        conn.close()
        return "Location not found", 404

    has_image_url = 'image_url' in finds[0].keys()
    
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
        image_url = find['image_url'] if has_image_url else None
        if image_url:
            # Filter out generic Block Island logo/placeholder images
            is_placeholder = 'default_image' in image_url
            
            if not is_placeholder:
                images.append({
                    'url': image_url,
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
    years_tracked = len(years)
    latest_find = next((find for find in finds if find['date_found']), None)
    featured_images = images[:12]
    extra_images = images[12:]
    recent_finds = finds[:18]
    older_finds = finds[18:]
    
    conn.close()
    
    return render_template('location_detail.html',
                          location_name=location_name,
                          total_finds=total_finds,
                          finds=finds,
                          images=images,
                          featured_images=featured_images,
                          extra_images=extra_images,
                          coords=coords,
                          peak_year=peak_year,
                          top_finder=top_finder,
                          years=sorted(years.items(), reverse=True),
                          years_tracked=years_tracked,
                          latest_find=latest_find,
                          recent_finds=recent_finds,
                          older_finds=older_finds,
                          page_meta=build_page_meta(
                              active_nav='dashboard',
                              mode='utility',
                              kicker='Location detail',
                              title=location_name,
                              subtitle=(
                                  f'{total_finds} reported finds across {years_tracked} seasons.'
                                  if years_tracked
                                  else f'{total_finds} reported finds.'
                              ),
                              primary_cta=build_cta(
                                  label='Open in Maps',
                                  href=f'https://maps.google.com/?q={coords["lat"]},{coords["lon"]}',
                                  external=True,
                              ) if coords else None,
                          ))

from ml_predictor import predict_today, get_seasonality_score

@app.route('/forecast')
def forecast():
    """Show float forecast for today"""
    predictions = predict_today()
    seasonality = get_seasonality_score()
    
    # Get weather for context
    weather = get_weather_data()
    
    return render_template('forecast.html', 
                          predictions=predictions,
                          seasonality=seasonality,
                          weather=weather,
                          top_prediction=predictions[0] if predictions else None,
                          page_meta=build_page_meta(
                              active_nav='forecast',
                              mode='utility',
                              kicker='Daily briefing',
                              title='Float forecast',
                              subtitle='A compact read on seasonal strength, likely locations, and current field conditions.',
                              primary_cta=build_cta(
                                  label='Open field mode',
                                  href=url_for('field_mode'),
                              ),
                          ))

@app.route('/sw.js')
def service_worker():
    from flask import send_from_directory
    response = send_from_directory('static', 'sw.js')
    response.headers['Cache-Control'] = 'no-cache'
    return response

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', '').lower() in {'1', 'true', 'yes', 'on'}, port=5000)
