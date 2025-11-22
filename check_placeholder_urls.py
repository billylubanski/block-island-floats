import sqlite3

conn = sqlite3.connect('floats.db')
c = conn.cursor()

# Get some image URLs to inspect
c.execute("SELECT image_url FROM finds WHERE image_url IS NOT NULL AND image_url != '' LIMIT 20")
print("Sample image URLs:")
for row in c.fetchall():
    url = row[0]
    print(f"\n{url}")
    if 'Block' in url or 'logo' in url or 'island' in url.lower():
        print("  ^ THIS LOOKS LIKE A PLACEHOLDER")

conn.close()
