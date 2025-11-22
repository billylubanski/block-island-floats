import sqlite3

conn = sqlite3.connect('floats.db')
c = conn.cursor()
c.execute('SELECT year, count(*) as count FROM finds GROUP BY year ORDER BY year DESC')
rows = c.fetchall()

print('Year data (DESC order):')
max_count = 0
for row in rows:
    print(f'  {row[0]}: {row[1]} finds')
    if row[1] > max_count:
        max_count = row[1]

print(f'\nMax count: {max_count}')
print(f'First row count (years[0]): {rows[0][1]}')
print(f'\nProblem: Template initializes max_count to years[0] which is {rows[0][1]}, not the actual max of {max_count}')

conn.close()
