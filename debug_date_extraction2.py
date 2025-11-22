import requests
import re
import json
from bs4 import BeautifulSoup

url = "https://www.blockislandinfo.com/event/4-a-ladd/790/"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

response = requests.get(url, headers=headers, timeout=10)
soup = BeautifulSoup(response.text, 'html.parser')

# Find JSON-LD script
json_ld_script = soup.find('script', type='application/ld+json')
if json_ld_script:
    print("=== JSON-LD Content ===")
    print(json_ld_script.string)
    print("\n=== Parsed ===")
    try:
        data = json.loads(json_ld_script.string)
        print(json.dumps(data, indent=2))
        if 'startDate' in data:
            print(f"\nstartDate found: {data['startDate']}")
        else:
            print("\nNo startDate in JSON-LD")
    except Exception as e:
        print(f"Error: {e}")
else:
    print("No JSON-LD script found")

# Also check for the date in the page text
print("\n=== Looking for date in visible text ===")
text = soup.get_text()
date_match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}', text)
if date_match:
    print(f"Found date in text: {date_match.group(0)}")
