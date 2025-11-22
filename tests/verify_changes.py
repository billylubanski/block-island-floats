import requests
import threading
import time
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app

def run_server():
    app.run(port=5001)

def test_routes():
    # Give the server a moment to start
    time.sleep(2)
    
    base_url = "http://localhost:5001"
    
    try:
        # Test Home Page
        print("Testing Home Page...")
        response = requests.get(f"{base_url}/")
        if response.status_code == 200:
            print("✅ Home Page OK")
            if "map-loading" in response.text:
                print("✅ Loading Spinner HTML found")
            else:
                print("❌ Loading Spinner HTML NOT found")
        else:
            print(f"❌ Home Page Failed: {response.status_code}")

        # Test About Page
        print("\nTesting About Page...")
        response = requests.get(f"{base_url}/about")
        if response.status_code == 200:
            print("✅ About Page OK")
            if "About the Project" in response.text:
                print("✅ About Content found")
            else:
                print("❌ About Content NOT found")
        else:
            print(f"❌ About Page Failed: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        # We can't easily kill the Flask server thread, but the script will exit
        pass

if __name__ == "__main__":
    # Start server in a separate thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    test_routes()
