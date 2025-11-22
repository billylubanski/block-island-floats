import sqlite3

conn = sqlite3.connect('floats.db')
c = conn.cursor()

# Check schema
c.execute('PRAGMA table_info(finds)')
print('Database schema:')
for row in c.fetchall():
    print(f'  {row[1]} ({row[2]})')

# Check if we have URLs
c.execute("SELECT COUNT(*) FROM finds WHERE url IS NOT NULL AND url != ''")
url_count = c.fetchone()[0]
print(f'\nFinds with URLs: {url_count} out of {c.execute("SELECT COUNT(*) FROM finds").fetchone()[0]}')

# Sample finds with URLs
print('\nSample finds with URLs:')
c.execute('SELECT id, year, float_number, finder, location_raw, url FROM finds WHERE url IS NOT NULL AND url != "" LIMIT 5')
for row in c.fetchall():
    print(f'  ID {row[0]}: {row[1]} #{row[2]} - {row[3]} at {row[4]}')
    print(f'    URL: {row[5][:80]}...')

conn.close()
