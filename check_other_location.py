import sqlite3

conn = sqlite3.connect('floats.db')
result = conn.execute('SELECT DISTINCT location_normalized FROM finds WHERE location_normalized LIKE "%Other%" OR location_normalized LIKE "%Unknown%"').fetchall()
print(result)
conn.close()
