import requests
from bs4 import BeautifulSoup

url = "https://www.blockislandinfo.com/event/267-b-massoia/5719/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

try:
    response = requests.get(url, headers=headers)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find JSON-LD
        script = soup.find('script', type='application/ld+json')
        if script:
            import json
            data = json.loads(script.string)
            print("JSON-LD Found!")
            print(f"startDate: {data.get('startDate')}")
            print(f"name: {data.get('name')}")
        else:
            print("No JSON-LD script found.")
        
except Exception as e:
    print(f"Error: {e}")
