import sqlite3

def check_db():
    conn = sqlite3.connect('floats.db')
    c = conn.cursor()
    print("Checking for potential dates in location_raw...")
    
    # Check for numbers that look like years
    c.execute("SELECT id, location_raw FROM finds WHERE location_raw LIKE '%201%' OR location_raw LIKE '%202%' LIMIT 10")
    rows = c.fetchall()
    print(f"Rows with 201x/202x: {len(rows)}")
    for r in rows:
        print(f"ID: {r[0]}, Loc: {r[1]}")
        
    # Check for slashes
    c.execute("SELECT id, location_raw FROM finds WHERE location_raw LIKE '%/%' LIMIT 10")
    rows = c.fetchall()
    print(f"\nRows with slashes: {len(rows)}")
    for r in rows:
        print(f"ID: {r[0]}, Loc: {r[1]}")

    conn.close()

if __name__ == "__main__":
    check_db()
