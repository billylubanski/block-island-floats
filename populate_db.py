import sqlite3
import json
import os

DB_NAME = 'floats.db'
JSON_FILE = 'all_floats_final.json'

def setup_database():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Create table with date_found
    c.execute('''
        CREATE TABLE IF NOT EXISTS finds (
            id TEXT PRIMARY KEY,
            year TEXT,
            float_number TEXT,
            finder TEXT,
            location_raw TEXT,
            location_normalized TEXT,
            date_found TEXT
        )
    ''')
    conn.commit()
    conn.close()

def populate():
    if not os.path.exists(JSON_FILE):
        print(f"{JSON_FILE} not found!")
        return

    with open(JSON_FILE, 'r') as f:
        data = json.load(f)
        
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    print(f"Inserting {len(data)} records...")
    
    for item in data:
        # Parse title for float number and finder
        # Title format: "267 - B. Massoia" or "245 Amy K."
        title = item.get('title', '')
        parts = title.split('-', 1)
        if len(parts) > 1:
            float_num = parts[0].strip()
            finder = parts[1].strip()
        else:
            # Try splitting by space if it looks like number
            parts_space = title.split(' ', 1)
            if parts_space[0].isdigit():
                float_num = parts_space[0]
                finder = parts_space[1] if len(parts_space) > 1 else ""
            else:
                float_num = ""
                finder = title
        
        c.execute('''
            INSERT OR REPLACE INTO finds (id, year, float_number, finder, location_raw, location_normalized, date_found)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            item['id'],
            item['year'],
            float_num,
            finder,
            item['location'],
            item['location'], # Normalized same as raw for now
            item.get('date_found', '')
        ))
        
    conn.commit()
    conn.close()
    print("Database populated successfully.")

if __name__ == "__main__":
    setup_database()
    populate()
