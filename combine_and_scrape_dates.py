import json
import glob
import requests
from bs4 import BeautifulSoup
import concurrent.futures
import time
import random
import os

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def fetch_date(item):
    url = item.get('url')
    if not url:
        return None
        
    try:
        # Random sleep to be nice
        time.sleep(random.uniform(0.1, 0.5))
        
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            script = soup.find('script', type='application/ld+json')
            if script:
                data = json.loads(script.string)
                return data.get('startDate')
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None
    return None

def main():
    files = glob.glob("scraped_data/floats_*.json")
    all_floats = []
    for f in files:
        with open(f, "r") as file:
            data = json.load(file)
            all_floats.extend(data)
            
    print(f"Loaded {len(all_floats)} floats.")
    
    # Remove duplicates just in case
    unique_floats = {f['id']: f for f in all_floats}.values()
    all_floats = list(unique_floats)
    print(f"Unique floats: {len(all_floats)}")
    
    # Fetch dates
    print("Fetching dates...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_float = {executor.submit(fetch_date, item): item for item in all_floats}
        
        completed = 0
        total = len(all_floats)
        
        for future in concurrent.futures.as_completed(future_to_float):
            item = future_to_float[future]
            try:
                date_found = future.result()
                if date_found:
                    item['date_found'] = date_found
                else:
                    # Fallback: use year from item
                    # But we want specific date if possible.
                    # If not found, maybe leave empty or set to Jan 1st?
                    # For now, leave as None or empty string
                    item['date_found'] = ""
            except Exception as e:
                print(f"Exception for {item['id']}: {e}")
                item['date_found'] = ""
            
            completed += 1
            if completed % 100 == 0:
                print(f"Progress: {completed}/{total}")
                
    # Save final
    with open("all_floats_final.json", "w") as f:
        json.dump(all_floats, f, indent=2)
        
    print("Done! Saved to all_floats_final.json")

if __name__ == "__main__":
    main()
