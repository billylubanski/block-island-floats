import sqlite3

DB_NAME = 'floats.db'

def main():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Find all records with January 1st dates (likely placeholders)
    cursor.execute("SELECT COUNT(*) FROM finds WHERE date_found LIKE '%-01-01'")
    count = cursor.fetchone()[0]
    print(f"Found {count} records with January 1st dates (likely placeholders)")
    
    # Clear these dates
    cursor.execute("UPDATE finds SET date_found = '' WHERE date_found LIKE '%-01-01'")
    conn.commit()
    
    print(f"Cleared {cursor.rowcount} placeholder dates")
    
    # Show remaining valid dates
    cursor.execute("SELECT COUNT(*) FROM finds WHERE date_found IS NOT NULL AND date_found != ''")
    valid_count = cursor.fetchone()[0]
    print(f"Remaining valid dates: {valid_count}")
    
    conn.close()

if __name__ == "__main__":
    main()
