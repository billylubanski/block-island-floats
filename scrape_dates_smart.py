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
        time.sleep(random.uniform(0.1, 0.3))
        response = requests.get(url, headers=HEADERS, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            script = soup.find('script', type='application/ld+json')
            if script:
                data = json.loads(script.string)
                return data.get('startDate')
    except Exception:
        return None
    return None

def main():
    files = glob.glob("scraped_data/floats_*.json")
    all_floats = []
    for f in files:
        with open(f, "r") as file:
            data = json.load(file)
            all_floats.extend(data)
            
    # Sort by year desc (just in case)
    all_floats.sort(key=lambda x: x.get('year', '0'), reverse=True)
    
    print(f"Total floats: {len(all_floats)}")
    
    # Take top 200 for dates
    target_floats = all_floats[:200]
    remaining_floats = all_floats[200:]
    
    print(f"Fetching dates for top {len(target_floats)} floats...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_item = {executor.submit(fetch_date, item): item for item in target_floats}
        
        completed = 0
        for future in concurrent.futures.as_completed(future_to_item):
            item = future_to_item[future]
            date = future.result()
            if date:
                item['date_found'] = date
            else:
                item['date_found'] = ""
            completed += 1
            if completed % 20 == 0:
                print(f"  {completed}/{len(target_floats)}")
                
    # Combine
    final_list = target_floats + remaining_floats
    
    with open("all_floats_final.json", "w") as f:
        json.dump(final_list, f, indent=2)
        
    print("Saved all_floats_final.json")

if __name__ == "__main__":
    main()
