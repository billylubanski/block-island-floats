from flask import Flask, render_template, request, url_for
import requests
import datetime
import sqlite3
import os
import math
from collections import Counter
from urllib.parse import urlencode
from analyzer import normalize_location, analyze_dates, analyze_unreported_floats, get_year_recovery_stats
from locations import LOCATIONS
from utils import get_last_updated

app = Flask(__name__)
DB_NAME = 'floats.db'
TRUTHY_VALUES = {'1', 'true', 'yes', 'on'}
DEFAULT_VALID_ONLY = os.getenv('IGNORE_INVALID_ROWS', '').strip().lower() in TRUTHY_VALUES
SEARCH_PAGE_SIZE_OPTIONS = (25, 50, 100, 250)
DEFAULT_SEARCH_PAGE_SIZE = 25
SEARCH_SORT_OPTIONS = (
    ('newest', 'Newest first'),
    ('oldest', 'Oldest first'),
    ('float_asc', 'Float number ascending'),
    ('float_desc', 'Float number descending'),
    ('location_asc', 'Location A-Z'),
)
DEFAULT_SEARCH_SORT = 'newest'
SEARCH_FILTER_ANY = 'any'
SEARCH_DEDUPE_DEFAULT = 'dedupe'
SEARCH_DEDUPE_RAW = 'raw'
FLOAT_NUMBER_SQL = "REPLACE(TRIM(COALESCE(float_number, '')), '#', '')"
FLOAT_NUMBER_IS_NUMERIC_SQL = f"{FLOAT_NUMBER_SQL} != '' AND {FLOAT_NUMBER_SQL} NOT GLOB '*[^0-9]*'"
HAS_IMAGE_SQL = "(image_url IS NOT NULL AND TRIM(image_url) != '' AND LOWER(image_url) NOT LIKE '%default_image%')"
HAS_DATE_SQL = "(date_found IS NOT NULL AND TRIM(date_found) != '')"

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


def normalize_text(value):
    if value is None:
        return ''
    return ' '.join(str(value).strip().split())


def normalize_text_lower(value):
    return normalize_text(value).lower()


def normalize_float_number(value):
    cleaned = normalize_text(value).lstrip('#').strip()
    if not cleaned:
        return ''
    if cleaned.isdigit():
        return str(int(cleaned))
    return cleaned


def float_number_to_int(value):
    normalized = normalize_float_number(value)
    if normalized.isdigit():
        return int(normalized)
    return None


def row_has_image(row):
    image_url = normalize_text(row.get('image_url', ''))
    return bool(image_url) and 'default_image' not in image_url.lower()


def parse_optional_int(value):
    if value is None:
        return None
    text = normalize_text(value)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def parse_positive_int(value, default, minimum=1, maximum=None):
    parsed = parse_optional_int(value)
    if parsed is None:
        return default
    if parsed < minimum:
        return default
    if maximum is not None and parsed > maximum:
        return default
    return parsed


def parse_page_size(value):
    parsed = parse_optional_int(value)
    if parsed in SEARCH_PAGE_SIZE_OPTIONS:
        return parsed
    return DEFAULT_SEARCH_PAGE_SIZE


def get_search_location_variants(conn, valid_only=False, supports_validation=False):
    where_clause, where_params = build_finds_where_clause(
        valid_only=valid_only,
        supports_validation=supports_validation,
    )
    rows = conn.execute(
        f'SELECT DISTINCT COALESCE(location_raw, "") AS location_raw FROM finds {where_clause}',
        where_params,
    ).fetchall()
    location_variants = {}
    for row in rows:
        raw_location = row['location_raw'] if row['location_raw'] is not None else ''
        normalized_location = normalize_location(raw_location)
        location_variants.setdefault(normalized_location, set()).add(raw_location)
    location_options = sorted(location_variants.keys(), key=lambda loc: loc.lower())
    return location_variants, location_options


def build_search_conditions(
    filters,
    location_variants,
    valid_only=False,
    supports_validation=False,
):
    conditions = []
    params = []

    if valid_only and supports_validation:
        conditions.append('COALESCE(is_valid, 1) = 1')

    if filters['q']:
        like_query = f"%{filters['q']}%"
        conditions.append('(finder LIKE ? OR location_raw LIKE ? OR float_number LIKE ?)')
        params.extend([like_query, like_query, like_query])

    if filters['year'] is not None:
        conditions.append('year = ?')
        params.append(filters['year'])

    if filters['location']:
        matching_variants = location_variants.get(filters['location'])
        if not matching_variants:
            conditions.append('1 = 0')
        else:
            variant_clauses = []
            non_blank_variants = sorted(v for v in matching_variants if v)
            includes_blank = '' in matching_variants
            if non_blank_variants:
                placeholders = ', '.join(['?'] * len(non_blank_variants))
                variant_clauses.append(f'location_raw IN ({placeholders})')
                params.extend(non_blank_variants)
            if includes_blank:
                variant_clauses.append('(location_raw IS NULL OR TRIM(location_raw) = "")')
            conditions.append(f"({' OR '.join(variant_clauses)})")

    if filters['float_exact']:
        conditions.append(f'{FLOAT_NUMBER_SQL} = ?')
        params.append(filters['float_exact'])

    if filters['float_min'] is not None or filters['float_max'] is not None:
        conditions.append(FLOAT_NUMBER_IS_NUMERIC_SQL)
        if filters['float_min'] is not None:
            conditions.append(f'CAST({FLOAT_NUMBER_SQL} AS INTEGER) >= ?')
            params.append(filters['float_min'])
        if filters['float_max'] is not None:
            conditions.append(f'CAST({FLOAT_NUMBER_SQL} AS INTEGER) <= ?')
            params.append(filters['float_max'])

    if filters['finder']:
        conditions.append('finder LIKE ?')
        params.append(f"%{filters['finder']}%")

    if filters['has_image'] == 'yes':
        conditions.append(HAS_IMAGE_SQL)
    elif filters['has_image'] == 'no':
        conditions.append(f'NOT {HAS_IMAGE_SQL}')

    if filters['has_date'] == 'yes':
        conditions.append(HAS_DATE_SQL)
    elif filters['has_date'] == 'no':
        conditions.append(f'NOT {HAS_DATE_SQL}')

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ''
    return where_clause, params


def enrich_search_row(row):
    enriched = dict(row)
    enriched['location_normalized'] = normalize_location(enriched.get('location_raw', ''))
    enriched['float_number_clean'] = normalize_float_number(enriched.get('float_number', ''))
    enriched['float_number_int'] = float_number_to_int(enriched.get('float_number', ''))
    enriched['finder_clean'] = normalize_text_lower(enriched.get('finder', ''))
    enriched['date_clean'] = normalize_text(enriched.get('date_found', ''))
    enriched['has_image'] = row_has_image(enriched)
    enriched['has_date'] = bool(enriched['date_clean'])
    return enriched


def dedupe_key_for_row(row):
    key = (
        normalize_text_lower(row.get('location_normalized', '')),
        row.get('year'),
        normalize_float_number(row.get('float_number', '')),
        row.get('finder_clean', ''),
        normalize_text_lower(row.get('date_clean', '')),
    )
    signal_count = sum(
        1
        for value in (key[2], key[3], key[4])
        if value
    )
    # Avoid collapsing many low-information rows into one record.
    if signal_count < 2:
        return key + (row.get('id'),)
    return key


def dedupe_preferred_score(row):
    return (
        1 if row.get('has_date') else 0,
        1 if row.get('has_image') else 0,
        1 if normalize_float_number(row.get('float_number', '')) else 0,
        1 if row.get('finder_clean') else 0,
        row.get('year') or 0,
        row.get('id') or 0,
    )


def dedupe_rows(rows):
    chosen = {}
    for row in rows:
        key = dedupe_key_for_row(row)
        existing = chosen.get(key)
        if existing is None or dedupe_preferred_score(row) > dedupe_preferred_score(existing):
            chosen[key] = row
    return list(chosen.values())


def sort_search_rows(rows, sort_key):
    if sort_key == 'oldest':
        return sorted(
            rows,
            key=lambda row: (
                row.get('year') or 0,
                row.get('date_clean', ''),
                row.get('id') or 0,
            ),
        )
    if sort_key == 'float_asc':
        return sorted(
            rows,
            key=lambda row: (
                row.get('float_number_int') is None,
                row.get('float_number_int') or 0,
                -(row.get('year') or 0),
                row.get('id') or 0,
            ),
        )
    if sort_key == 'float_desc':
        return sorted(
            rows,
            key=lambda row: (
                row.get('float_number_int') is None,
                -(row.get('float_number_int') or 0),
                -(row.get('year') or 0),
                -(row.get('id') or 0),
            ),
        )
    if sort_key == 'location_asc':
        return sorted(
            rows,
            key=lambda row: (
                normalize_text_lower(row.get('location_normalized', '')),
                -(row.get('year') or 0),
                row.get('id') or 0,
            ),
        )
    return sorted(
        rows,
        key=lambda row: (
            row.get('year') or 0,
            row.get('date_clean', ''),
            row.get('id') or 0,
        ),
        reverse=True,
    )


def build_search_url(params, **overrides):
    merged = dict(params)
    for key, value in overrides.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = str(value)
    query = urlencode(merged)
    base = url_for('search')
    if not query:
        return base
    return f'{base}?{query}'


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
    conn = get_db_connection()
    supports_validation = finds_supports_validation(conn)
    location_variants, location_options = get_search_location_variants(
        conn,
        valid_only=valid_only,
        supports_validation=supports_validation,
    )

    year_filter = parse_optional_int(request.args.get('year', ''))

    location_filter = normalize_text(request.args.get('location', ''))
    if location_filter and location_filter not in location_variants:
        location_filter = ''

    float_exact_filter = normalize_float_number(request.args.get('float_exact', ''))
    float_min = parse_optional_int(request.args.get('float_min'))
    float_max = parse_optional_int(request.args.get('float_max'))
    if float_min is not None and float_max is not None and float_min > float_max:
        float_min, float_max = float_max, float_min

    has_image = request.args.get('has_image', SEARCH_FILTER_ANY).strip().lower()
    if has_image not in {SEARCH_FILTER_ANY, 'yes', 'no'}:
        has_image = SEARCH_FILTER_ANY

    has_date = request.args.get('has_date', SEARCH_FILTER_ANY).strip().lower()
    if has_date not in {SEARCH_FILTER_ANY, 'yes', 'no'}:
        has_date = SEARCH_FILTER_ANY

    sort_key = request.args.get('sort', DEFAULT_SEARCH_SORT).strip()
    allowed_sorts = {option[0] for option in SEARCH_SORT_OPTIONS}
    if sort_key not in allowed_sorts:
        sort_key = DEFAULT_SEARCH_SORT

    dedupe_mode = request.args.get('dedupe', SEARCH_DEDUPE_DEFAULT).strip().lower()
    if dedupe_mode != SEARCH_DEDUPE_RAW:
        dedupe_mode = SEARCH_DEDUPE_DEFAULT

    page_size = parse_page_size(request.args.get('page_size'))
    page = parse_positive_int(request.args.get('page'), 1, minimum=1)

    filters = {
        'q': normalize_text(request.args.get('q', '')),
        'year': year_filter,
        'location': location_filter,
        'float_exact': float_exact_filter,
        'float_min': float_min,
        'float_max': float_max,
        'finder': normalize_text(request.args.get('finder', '')),
        'has_image': has_image,
        'has_date': has_date,
    }

    where_clause, params = build_search_conditions(
        filters,
        location_variants=location_variants,
        valid_only=valid_only,
        supports_validation=supports_validation,
    )
    results = conn.execute(
        f"SELECT * FROM finds {where_clause}",
        params,
    ).fetchall()
    conn.close()

    enriched_rows = [enrich_search_row(row) for row in results]
    raw_count = len(enriched_rows)
    processed_rows = enriched_rows
    if dedupe_mode == SEARCH_DEDUPE_DEFAULT:
        processed_rows = dedupe_rows(enriched_rows)
    duplicate_count = max(0, raw_count - len(processed_rows))

    sorted_rows = sort_search_rows(processed_rows, sort_key)
    total_results = len(sorted_rows)
    total_pages = max(1, math.ceil(total_results / page_size)) if total_results else 1
    page = min(page, total_pages)

    offset = (page - 1) * page_size
    paged_results = sorted_rows[offset:offset + page_size]
    showing_from = offset + 1 if total_results else 0
    showing_to = min(offset + page_size, total_results) if total_results else 0

    conn = get_db_connection()
    where_base, base_params = build_finds_where_clause(
        valid_only=valid_only,
        supports_validation=supports_validation,
    )
    year_rows = conn.execute(
        f'SELECT DISTINCT year FROM finds {where_base} ORDER BY year DESC',
        base_params,
    ).fetchall()
    conn.close()
    year_options = [row['year'] for row in year_rows if row['year'] is not None]

    query_params = {}
    if valid_only:
        query_params['valid_only'] = '1'
    if filters['q']:
        query_params['q'] = filters['q']
    if filters['year'] is not None:
        query_params['year'] = str(filters['year'])
    if filters['location']:
        query_params['location'] = filters['location']
    if filters['float_exact']:
        query_params['float_exact'] = filters['float_exact']
    if filters['float_min'] is not None:
        query_params['float_min'] = str(filters['float_min'])
    if filters['float_max'] is not None:
        query_params['float_max'] = str(filters['float_max'])
    if filters['finder']:
        query_params['finder'] = filters['finder']
    if filters['has_image'] != SEARCH_FILTER_ANY:
        query_params['has_image'] = filters['has_image']
    if filters['has_date'] != SEARCH_FILTER_ANY:
        query_params['has_date'] = filters['has_date']
    if sort_key != DEFAULT_SEARCH_SORT:
        query_params['sort'] = sort_key
    if page_size != DEFAULT_SEARCH_PAGE_SIZE:
        query_params['page_size'] = str(page_size)
    if dedupe_mode == SEARCH_DEDUPE_RAW:
        query_params['dedupe'] = SEARCH_DEDUPE_RAW

    page_links = []
    if total_pages <= 7:
        page_numbers = list(range(1, total_pages + 1))
    else:
        page_numbers = sorted({
            1,
            2,
            total_pages - 1,
            total_pages,
            page - 1,
            page,
            page + 1,
        })
    for page_number in page_numbers:
        if 1 <= page_number <= total_pages:
            page_links.append({
                'number': page_number,
                'url': build_search_url(query_params, page=page_number),
                'active': page_number == page,
            })

    prev_url = build_search_url(query_params, page=page - 1) if page > 1 else None
    next_url = build_search_url(query_params, page=page + 1) if page < total_pages else None
    valid_toggle_url = build_search_url(
        query_params,
        valid_only='1' if not valid_only else None,
        page=1,
    )
    dedupe_toggle_url = build_search_url(
        query_params,
        dedupe=SEARCH_DEDUPE_RAW if dedupe_mode == SEARCH_DEDUPE_DEFAULT else None,
        page=1,
    )

    return render_template(
        'search.html',
        results=paged_results,
        filters=filters,
        page=page,
        page_size=page_size,
        page_size_options=SEARCH_PAGE_SIZE_OPTIONS,
        total_results=total_results,
        total_pages=total_pages,
        showing_from=showing_from,
        showing_to=showing_to,
        raw_count=raw_count,
        duplicate_count=duplicate_count,
        dedupe_mode=dedupe_mode,
        sort_key=sort_key,
        sort_options=SEARCH_SORT_OPTIONS,
        year_options=year_options,
        location_options=location_options,
        prev_url=prev_url,
        next_url=next_url,
        page_links=page_links,
        valid_toggle_url=valid_toggle_url,
        dedupe_toggle_url=dedupe_toggle_url,
    )

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
                          weather=weather)

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


@app.route('/float/<int:year>/<path:float_number>')
def float_detail(year, float_number):
    """Detail page for a specific float number within one year."""
    valid_only = valid_only_enabled()
    normalized_float = normalize_float_number(float_number)
    if not normalized_float:
        return "Float not found", 404

    conn = get_db_connection()
    supports_validation = finds_supports_validation(conn)
    conditions = ['year = ?', f'{FLOAT_NUMBER_SQL} = ?']
    params = [year, normalized_float]
    if valid_only and supports_validation:
        conditions.append('COALESCE(is_valid, 1) = 1')

    finds = conn.execute(
        f"SELECT * FROM finds WHERE {' AND '.join(conditions)} ORDER BY date_found DESC, id DESC",
        params,
    ).fetchall()
    conn.close()

    if not finds:
        return "Float not found", 404

    find_rows = []
    location_counts = Counter()
    for row in finds:
        find = dict(row)
        location_name = normalize_location(find.get('location_raw', ''))
        find['location_normalized'] = location_name
        find['has_image'] = row_has_image(find)
        find_rows.append(find)
        location_counts[location_name] += 1

    return render_template(
        'float_detail.html',
        year=year,
        float_number=normalized_float,
        finds=find_rows,
        total_finds=len(find_rows),
        top_locations=location_counts.most_common(5),
    )

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
