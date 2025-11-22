import sqlite3
import json

DB_NAME = 'floats.db'
JSON_FILE = 'all_floats_final.json'

def main():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Add url column if it doesn't exist
    try:
        cursor.execute("ALTER TABLE finds ADD COLUMN url TEXT")
        print("Added 'url' column to finds table")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("'url' column already exists")
        else:
            raise
    
    # Load JSON data
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Updating {len(data)} records with URLs...")
    
    # Update each record with its URL
    updated = 0
    for record in data:
        record_id = record.get('id')
        url = record.get('url', '')
        
        if record_id and url:
            cursor.execute("UPDATE finds SET url = ? WHERE id = ?", (url, record_id))
            updated += 1
    
    conn.commit()
    conn.close()
    
    print(f"Successfully updated {updated} records with URLs")

if __name__ == "__main__":
    main()
