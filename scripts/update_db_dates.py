import sqlite3
import re

DB_NAME = 'floats.db'

def extract_date(text):
    if not text:
        return None
        
    # Regex for MM/DD/YY or MM/DD/YYYY
    date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', text)
    if date_match:
        return date_match.group(1)
        
    # Improved Regex for Month DD, YYYY
    # Handles: "July 18, 2015", "July 18 2015", "Jan. 18, 2015", "July 18th, 2015"
    # Also handles attached text like "seatJuly"
    month_match = re.search(r'([A-Z][a-z]{2,9}\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})', text)
    if month_match:
        return month_match.group(1)

    # Regex for Month YYYY (e.g., June 2017)
    month_year_match = re.search(r'([A-Z][a-z]{2,9}\.?\s+\d{4})', text)
    if month_year_match:
        return month_year_match.group(1)
        
    # Regex for Year at start (e.g., "2018 BI Triathalon")
    year_start_match = re.search(r'^(\d{4})\s+', text)
    if year_start_match:
        return year_start_match.group(1)
        
    return None

def update_dates():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    c.execute("SELECT id, location_raw, finder, date_found FROM finds")
    rows = c.fetchall()
    
    updated_count = 0
    total_rows = len(rows)
    
    print(f"Scanning {total_rows} rows...")
    
    target_ids = [1600, 444, 496, 531, 553, 50]
    
    with open('debug_update.txt', 'w', encoding='utf-8') as f:
        for row in rows:
            id_ = row[0]
            loc = row[1]
            finder = row[2]
            current_date = row[3]
            
            new_date = extract_date(loc)
            if not new_date:
                new_date = extract_date(finder)
                
            if id_ in target_ids:
                f.write(f"ID: {id_}, Loc: {repr(loc)}, Date: {current_date} -> New: {new_date}\n")
                
            if new_date and new_date != current_date:
                c.execute("UPDATE finds SET date_found=? WHERE id=?", (new_date, id_))
                updated_count += 1
                if updated_count % 100 == 0:
                    print(f"Updated {updated_count} rows...")
                
    conn.commit()
    conn.close()
    print(f"Finished! Updated {updated_count} rows out of {total_rows}.")

if __name__ == "__main__":
    update_dates()
