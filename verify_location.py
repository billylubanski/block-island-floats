import sqlite3

conn = sqlite3.connect('floats.db')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM finds WHERE location_normalized = ?', ('Other/Unknown',))
count = cursor.fetchone()[0]
print(f'Finds with location_normalized = "Other/Unknown": {count}')

# Also check if this location appears in the top locations
from analyzer import normalize_location
from collections import Counter

all_locs = cursor.execute('SELECT location_raw FROM finds').fetchall()
normalized_locs = [normalize_location(row[0]) for row in all_locs]
loc_counts = Counter(normalized_locs)

if 'Other/Unknown' in loc_counts:
    print(f'"Other/Unknown" has {loc_counts["Other/Unknown"]} finds total')
else:
    print('"Other/Unknown" not found in normalized locations')

conn.close()
