import sqlite3

conn = sqlite3.connect('floats.db')
c = conn.cursor()

# Get URLs from Rodman's Hollow
c.execute("SELECT image_url FROM finds WHERE location_normalized = ? AND image_url IS NOT NULL LIMIT 20", ("Rodman's Hollow",))

with open('sample_urls.txt', 'w', encoding='utf-8') as f:
    for i, row in enumerate(c.fetchall(), 1):
        url = row[0]
        f.write(f"{i}. {url}\n")

print("✅ Wrote URLs to sample_urls.txt")
conn.close()
