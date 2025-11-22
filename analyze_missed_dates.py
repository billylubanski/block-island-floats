import sqlite3
import re

def analyze_missed_dates():
    conn = sqlite3.connect('floats.db')
    cursor = conn.cursor()
    
    # Get all rows where date_found is NULL
    cursor.execute("SELECT location_raw FROM finds WHERE date_found IS NULL")
    rows = cursor.fetchall()
    conn.close()
    
    months = [
        "January", "February", "March", "April", "May", "June", 
        "July", "August", "September", "October", "November", "December"
    ]
    
    print(f"Scanning {len(rows)} entries for missed dates...")
    
    missed_examples = []
    
    for row in rows:
        text = row[0]
        # Check if any month name is in the text
        for month in months:
            if month in text:
                missed_examples.append(text)
                break
                
    print(f"Found {len(missed_examples)} entries containing month names that were not parsed.")
    print("\nSample of missed entries:")
    for ex in missed_examples[:20]:
        print(f"- {ex}")

if __name__ == "__main__":
    analyze_missed_dates()
