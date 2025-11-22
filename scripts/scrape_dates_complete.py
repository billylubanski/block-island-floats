import sqlite3
import requests
import re
import json
import time
import concurrent.futures
from datetime import datetime

DB_NAME = 'floats.db'
MAX_WORKERS = 10  # Be nice to the server
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def extract_date_from_url(url):
    if not url:
        return None
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            # Try JSON-LD first (most reliable)
            json_ld_match = re.search(r'<script type="application/ld\+json">(.*?)</script>', response.text, re.DOTALL)
            if json_ld_match:
                try:
                    data = json.loads(json_ld_match.group(1))
                    if 'startDate' in data:
                        date_str = data['startDate'].split('T')[0]  # Format: 2024-10-14
                        
                        # Reject placeholder dates (YYYY-01-01)
                        if date_str.endswith('-01-01'):
                            return None
                            
                        return date_str
                except:
                    pass
            
            # Fallback to text regex
            # "Date Found: October 14, 2024"
            match = re.search(r'Date Found:</strong>\s*(.*?)(?:<|&)', response.text)
            if match:
                date_str = match.group(1).strip()
                try:
                    dt = datetime.strptime(date_str, '%B %d, %Y')
                    return dt.strftime('%Y-%m-%d')
                except:
                    pass
                    
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return None

def process_row(row):
    record_id = row['id']
    url = row['url']
    
    if not url:
        return record_id, None
        
    date_found = extract_date_from_url(url)
    return record_id, date_found

def main():
    conn = get_db_connection()
    
    # Get all finds with missing dates
    # We check for NULL or empty string
    cursor = conn.execute("SELECT id, url FROM finds WHERE date_found IS NULL OR date_found = ''")
    rows = cursor.fetchall()
    conn.close()
    
    total_rows = len(rows)
    print(f"Found {total_rows} records with missing dates.")
    
    if total_rows == 0:
        return

    # Process in chunks to allow saving progress
    chunk_size = 50
    
    # Re-open connection for writing
    conn = get_db_connection()
    
    processed_count = 0
    updated_count = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Map all rows to futures
        # We'll do this in batches to not queue 4000 tasks at once if we want to be safer, 
        # but 4000 is manageable for ThreadPoolExecutor.
        # However, let's just iterate and submit.
        
        futures = {executor.submit(process_row, row): row for row in rows}
        
        for future in concurrent.futures.as_completed(futures):
            record_id, date_found = future.result()
            processed_count += 1
            
            if date_found:
                conn.execute("UPDATE finds SET date_found = ? WHERE id = ?", (date_found, record_id))
                updated_count += 1
                
            if processed_count % 10 == 0:
                print(f"Processed {processed_count}/{total_rows} | Updated: {updated_count}")
                
            if processed_count % chunk_size == 0:
                conn.commit()
                print("  -- Committed batch --")

    conn.commit()
    conn.close()
    print(f"Done! Updated {updated_count} records.")

if __name__ == "__main__":
    main()
