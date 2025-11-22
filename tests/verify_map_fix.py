import requests

def verify_map_fix():
    try:
        response = requests.get('http://127.0.0.1:5000/')
        if response.status_code == 200:
            content = response.text
            
            # Check for map container
            if '<div id="map"' in content:
                print("✅ Map container found")
            else:
                print("❌ Map container NOT found")
                
            # Check for spinner
            if 'id="map-loading"' in content:
                print("✅ Spinner found")
            else:
                print("❌ Spinner NOT found")
                
            # Check for script
            if 'L.map(\'map\')' in content:
                print("✅ Map initialization script found")
            else:
                print("❌ Map initialization script NOT found")
                
            # Check for spinner hiding logic
            if 'document.getElementById(\'map-loading\').style.display = \'none\'' in content:
                print("✅ Spinner hiding logic found")
            else:
                print("❌ Spinner hiding logic NOT found")
                
        else:
            print(f"❌ Failed to fetch home page: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    verify_map_fix()
