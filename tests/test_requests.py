import requests

url = "https://www.blockislandinfo.com/glass-float-project/found-floats/?categories=24&skip=0&bounds=false&view=grid&sort=date"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

try:
    response = requests.get(url, headers=headers)
    print(f"Status Code: {response.status_code}")
    if "Kelly" in response.text:
        print("Found 'Kelly'!")
    elif "Float #" in response.text:
        print("Found 'Float #'!")
    elif "data-recid" in response.text:
        print("Found 'data-recid'!")
    else:
        print("Data NOT found.")
        print("First 500 chars:", response.text[:500])
except Exception as e:
    print(f"Error: {e}")
