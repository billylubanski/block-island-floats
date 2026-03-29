import sys
import threading
import time
from pathlib import Path

import requests


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from app import app


def run_server():
    app.run(port=5001)


def test_routes():
    time.sleep(2)
    base_url = "http://localhost:5001"

    try:
        print("Testing Home Page...")
        response = requests.get(f"{base_url}/")
        if response.status_code == 200:
            print("Home Page OK")
            if "map-loading" in response.text:
                print("Loading Spinner HTML found")
            else:
                print("Loading Spinner HTML NOT found")
        else:
            print(f"Home Page Failed: {response.status_code}")

        print("\nTesting About Page...")
        response = requests.get(f"{base_url}/about")
        if response.status_code == 200:
            print("About Page OK")
            if "Use public float reports to choose a stronger starting point" in response.text:
                print("About Content found")
            else:
                print("About Content NOT found")
        else:
            print(f"About Page Failed: {response.status_code}")
    except Exception as exc:
        print(f"Error: {exc}")


if __name__ == "__main__":
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    test_routes()
