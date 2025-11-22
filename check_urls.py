import sqlite3

conn = sqlite3.connect('floats.db')
c = conn.cursor()

# Get URLs from Rodman's Hollow
c.execute("SELECT image_url FROM finds WHERE location_normalized = ? AND image_url IS NOT NULL LIMIT 15", ("Rodman's Hollow",))

print("Image URLs from Rodman's Hollow:")
print("=" * 80)
for i, row in enumerate(c.fetchall(), 1):
    url = row[0]
    print(f"\n{i}. {url}")

conn.close()
