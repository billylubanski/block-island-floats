from flask import Flask, render_template, request
import sqlite3
import re
from collections import Counter
from analyzer import normalize_location, analyze_dates, analyze_unreported_floats
from locations import LOCATIONS
from utils import get_last_updated

app = Flask(__name__)
DB_NAME = 'floats.db'

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    conn = get_db_connection()
    
    # Get year filter from query parameter
    selected_year = request.args.get('year', 'all')
    
    # Build WHERE clause for year filtering
    if selected_year != 'all':
        year_filter = f"WHERE year = {selected_year}"
        year_param = int(selected_year)
    else:
        year_filter = ""
        year_param = None
    
    # Get total finds (filtered)
    if year_param:
        total_finds = conn.execute('SELECT count(*) FROM finds WHERE year = ?', (year_param,)).fetchone()[0]
    else:
        total_finds = conn.execute('SELECT count(*) FROM finds').fetchone()[0]
    
    # Get finds by year (always show all years for context)
    years_data = conn.execute('SELECT year, count(*) as count FROM finds GROUP BY year ORDER BY year DESC').fetchall()
    
    # Calculate max year count for percentage calculations
    max_year_count = max([row['count'] for row in years_data], default=1) if years_data else 1
    
    # Calculate total floats hidden across all years
    total_hidden_all_years = 0
    for year_row in years_data:
        year = year_row['year']
        float_nums = []
        for row in conn.execute('SELECT float_number FROM finds WHERE year = ? AND float_number IS NOT NULL AND float_number != ""', (year,)):
            match = re.search(r'(\d+)', str(row['float_number']))
            if match:
                float_nums.append(int(match.group(1)))
        if float_nums:
            total_hidden_all_years += max(float_nums)
    
    # Get date analysis stats (filtered)
    date_stats = analyze_dates(year_param)
    best_months = date_stats['best_months']
    total_dates_analyzed = date_stats['total_dates_analyzed']
    
    # Get unreported float stats (only for specific years, not "all")
    # Float numbers are reused each year, so aggregation across years doesn't make sense
    if year_param:
        unreported_stats = analyze_unreported_floats(year_param)
    else:
        unreported_stats = None
    
    # Get top locations (filtered)
    if year_param:
        all_locs = conn.execute('SELECT location_raw FROM finds WHERE year = ?', (year_param,)).fetchall()
    else:
        all_locs = conn.execute('SELECT location_raw FROM finds').fetchall()
    
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
                           years=years_data,
                           max_year_count=max_year_count,
                           top_locs=top_locs,
                           map_markers=map_markers,
                           best_months=best_months,
                           total_dates_analyzed=total_dates_analyzed,
                           unreported_stats=unreported_stats,
                           last_updated=last_updated,
                           selected_year=selected_year)

@app.route('/search')
def search():
    query = request.args.get('q', '')
    conn = get_db_connection()
    if query:
        results = conn.execute('SELECT * FROM finds WHERE finder LIKE ? OR location_raw LIKE ? OR float_number LIKE ? LIMIT 50', 
                               (f'%{query}%', f'%{query}%', f'%{query}%')).fetchall()
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
    
    # Get all locations with coordinates and their find counts
    all_locs = conn.execute('SELECT location_raw FROM finds').fetchall()
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
    
    return render_template('field.html',
                          hunting_spots=hunting_spots,
                          last_updated=last_updated)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
