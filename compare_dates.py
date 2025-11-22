import requests
from bs4 import BeautifulSoup
import re

# Test a few different years
test_urls = [
    ("https://www.blockislandinfo.com/event/4-a-ladd/790/", "2020"),  # Old record
    ("https://www.blockislandinfo.com/event/267-b-massoia/5719/", "2025"),  # Recent record
]

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

for url, expected_year in test_urls:
    print(f"\n{'='*60}")
    print(f"Testing: {url} (Year: {expected_year})")
    print('='*60)
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Get all text
        text = soup.get_text()
        
        # Look for "Date Found" label
        if 'Date Found' in text:
            # Extract context around "Date Found"
            idx = text.find('Date Found')
            context = text[idx:idx+100]
            print(f"Context around 'Date Found': {context}")
        else:
            print("'Date Found' not found in visible text")
            
        # Look for any date patterns
        date_patterns = [
            r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}',
            r'\d{1,2}/\d{1,2}/\d{4}',
            r'\d{4}-\d{2}-\d{2}'
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, text)
            if matches:
                print(f"Pattern '{pattern[:30]}...' found: {matches[:5]}")
                
    except Exception as e:
        print(f"Error: {e}")
