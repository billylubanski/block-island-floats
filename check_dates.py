import sqlite3

conn = sqlite3.connect('floats.db')
c = conn.cursor()

# Get total finds
c.execute('SELECT COUNT(*) FROM finds')
total = c.fetchone()[0]
print(f'Total finds in database: {total}')

# Get finds with dates
c.execute("SELECT COUNT(*) FROM finds WHERE date_found IS NOT NULL AND date_found != ''")
with_dates = c.fetchone()[0]
print(f'Finds WITH dates: {with_dates}')

# Get finds without dates
without_dates = total - with_dates
print(f'Finds WITHOUT dates: {without_dates}')

# Show by year
print('\nFinds with dates by year:')
c.execute("SELECT year, COUNT(*) FROM finds WHERE date_found IS NOT NULL AND date_found != '' GROUP BY year ORDER BY year")
for row in c.fetchall():
    print(f'  {row[0]}: {row[1]} dated finds')

# Show sample of finds without dates
print('\nSample of finds WITHOUT dates (first 20):')
c.execute("SELECT id, year, location_raw, date_found FROM finds WHERE date_found IS NULL OR date_found = '' LIMIT 20")
for row in c.fetchall():
    print(f'  ID {row[0]}: {row[1]} - {row[2]} - date_found: "{row[3]}"')

conn.close()
