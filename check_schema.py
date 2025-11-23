import sqlite3

conn = sqlite3.connect('floats.db')
cursor = conn.cursor()
cursor.execute('PRAGMA table_info(finds)')
columns = cursor.fetchall()
print('Schema for finds table:')
for col in columns:
    print(f'  {col[1]} ({col[2]})')

# Also show a sample record with Other/Unknown after normalization  
from analyzer import normalize_location

cursor.execute('SELECT location_raw, location_normalized FROM finds LIMIT 5')
rows = cursor.fetchall()
print('\nSample records:')
for row in rows:
    normalized = normalize_location(row[0])
    print(f'  Raw: {row[0][:50]}... -> Normalized in func: {normalized} | DB: {row[1]}')

conn.close()
