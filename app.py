from flask import Flask, render_template, request
import sqlite3
from collections import Counter
from analyzer import normalize_location, analyze_dates
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
    
    # Get total finds
    total_finds = conn.execute('SELECT count(*) FROM finds').fetchone()[0]
    
    # Get finds by year
    years_data = conn.execute('SELECT year, count(*) as count FROM finds GROUP BY year ORDER BY year DESC').fetchall()
    
    # Get date analysis stats
    date_stats = analyze_dates()
    best_months = date_stats['best_months']
    total_dates_analyzed = date_stats['total_dates_analyzed']
    
    # Get top locations
    # We need to fetch all and normalize in python because normalization is complex
    all_locs = conn.execute('SELECT location_raw FROM finds').fetchall()
    normalized_locs = [normalize_location(row['location_raw']) for row in all_locs]
    loc_counts = Counter(normalized_locs)
    
    # Attach coordinates
    top_locs = []
    map_markers = []
    
    # Get all locations that have coordinates, plus top 20 even if they don't (to show in list)
    for loc, count in loc_counts.most_common(100):
        coords = LOCATIONS.get(loc, None)
        
        # Data for table (Top 100)
        if coords or count > 5: 
            top_locs.append({
                'name': loc,
                'count': count,
                'lat': coords['lat'] if coords else None,
                'lon': coords['lon'] if coords else None
            })
            
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
                           years=years_data, 
                           top_locs=top_locs,
                           map_markers=map_markers,
                           best_months=best_months,
                           total_dates_analyzed=total_dates_analyzed,
                           last_updated=last_updated)

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

if __name__ == '__main__':
    app.run(debug=True, port=5000)
