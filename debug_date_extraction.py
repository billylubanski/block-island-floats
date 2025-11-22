import requests
import re
import json

url = "https://www.blockislandinfo.com/event/4-a-ladd/790/"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

response = requests.get(url, headers=headers, timeout=10)
html = response.text

# Check for JSON-LD
json_ld_match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
if json_ld_match:
    print("=== JSON-LD Found ===")
    print(json_ld_match.group(1)[:500])
    try:
        data = json.loads(json_ld_match.group(1))
        print("\nParsed JSON-LD:")
        print(json.dumps(data, indent=2)[:500])
    except Exception as e:
        print(f"Error parsing JSON-LD: {e}")
else:
    print("No JSON-LD found")

# Look for date patterns in the HTML
print("\n=== Searching for date patterns ===")
date_patterns = [
    r'Date Found:</strong>\s*(.*?)(?:<|&)',
    r'date-found["\']>\s*(.*?)\s*<',
    r'startDate["\']:\s*["\']([^"\']+)',
]

for pattern in date_patterns:
    matches = re.findall(pattern, html, re.IGNORECASE)
    if matches:
        print(f"Pattern '{pattern}' found: {matches[:3]}")

# Save a snippet of the HTML for inspection
print("\n=== HTML snippet around 'date' ===")
date_context = re.search(r'.{200}date.{200}', html, re.IGNORECASE | re.DOTALL)
if date_context:
    print(date_context.group(0))
