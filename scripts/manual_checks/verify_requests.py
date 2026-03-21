import json

import requests


def main():
    url = "https://www.blockislandinfo.com/includes/rest_v2/plugins_events_events/find/"
    payload = {
        "filter": {
            "active": True,
            "$and": [
                {
                    "categories.catId": {
                        "$in": ["23", "24"],
                    }
                }
            ],
        },
        "options": {
            "limit": 24,
            "skip": 0,
            "count": True,
            "castDocs": False,
            "fields": {
                "title": 1,
                "date": 1,
                "location": 1,
                "media_raw": 1,
            },
            "sort": {"startDate": -1, "rank": 1, "custom.numeric_sort": 1},
        },
    }
    params = {"json": json.dumps(payload)}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        ),
        "Accept": "application/json",
        "Referer": "https://www.blockislandinfo.com/glass-float-project/found-floats/",
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text[:500]}")
    except Exception as exc:
        print(f"Error: {exc}")


if __name__ == "__main__":
    main()
