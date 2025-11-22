import sqlite3

conn = sqlite3.connect('floats.db')
c = conn.cursor()
print("Checking for potential missed dates...")
# Look for /
rows = c.execute("SELECT location_raw FROM finds WHERE location_raw LIKE '%/%' LIMIT 50").fetchall()
print(f"Rows with '/': {len(rows)}")
for row in rows:
    print(f"  {row[0]}")

# Look for 201x
rows = c.execute("SELECT location_raw FROM finds WHERE location_raw LIKE '%201%' LIMIT 50").fetchall()
print(f"Rows with '201': {len(rows)}")
for row in rows:
    print(f"  {row[0]}")
    
# Look for month names
months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
for month in months:
    rows = c.execute(f"SELECT location_raw FROM finds WHERE location_raw LIKE '%{month}%' LIMIT 5").fetchall()
    if rows:
        print(f"Rows with '{month}':")
        for row in rows:
            print(f"  {row[0]}")

print("\nChecking for EXTRACTED dates (date_found column)...")
rows = c.execute("SELECT date_found FROM finds WHERE date_found IS NOT NULL LIMIT 20").fetchall()
for row in rows:
    print(row[0])

print("\nCount of entries with dates:")
count = c.execute("SELECT count(*) FROM finds WHERE date_found IS NOT NULL").fetchone()[0]
print(count)

conn.close()
