import requests

def verify_year_filter():
    try:
        response = requests.get('http://127.0.0.1:5000/')
        if response.status_code == 200:
            content = response.text
            
            # Check for control bar
            if 'class="control-bar"' in content:
                print("✅ Control bar found")
            else:
                print("❌ Control bar NOT found")
                # Print a chunk of the content to see what's there
                start_index = content.find('{% block content %}')
                if start_index == -1:
                    start_index = content.find('<main') 
                if start_index == -1:
                    start_index = 0
                print(f"Content snippet:\n{content[start_index:start_index+500]}...")
                
            # Check for year filter form
            if 'Filter by Year:' in content:
                print("✅ Year filter label found")
            else:
                print("❌ Year filter label NOT found")
                
            # Check for summary text
            if 'Showing <strong>' in content:
                print("✅ Summary text found")
            else:
                print("❌ Summary text NOT found")
                
            # Check for map (regression test)
            if '<div id="map"' in content:
                print("✅ Map container found")
            else:
                print("❌ Map container NOT found")
                
        else:
            print(f"❌ Failed to fetch home page: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    verify_year_filter()
