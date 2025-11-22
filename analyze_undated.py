import sqlite3

conn = sqlite3.connect('floats.db')
c = conn.cursor()

# Get schema
c.execute("PRAGMA table_info(finds)")
print("Database schema:")
for row in c.fetchall():
    print(f"  {row[1]} ({row[2]})")

# Check what data is available for undated finds
print("\nSample of undated finds with all fields:")
c.execute("""
    SELECT id, year, location_raw, date_found, finder, float_number 
    FROM finds 
    WHERE date_found IS NULL OR date_found = '' 
    LIMIT 10
""")
for row in c.fetchall():
    print(f"  ID {row[0]}: year={row[1]}, location={row[2]}, date={row[3]}, finder={row[4]}, float#{row[5]}")

# Check if any have partial date info in other fields
print("\nChecking year distribution for undated finds:")
c.execute("""
    SELECT year, COUNT(*) 
    FROM finds 
    WHERE date_found IS NULL OR date_found = '' 
    GROUP BY year 
    ORDER BY year
""")
for row in c.fetchall():
    print(f"  {row[0]}: {row[1]} finds")

conn.close()
