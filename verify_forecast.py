from app import app
import sys

def test_forecast_route():
    print("Testing /forecast route...")
    with app.test_client() as client:
        response = client.get('/forecast')
        if response.status_code == 200:
            print("✅ Route /forecast returned 200 OK")
            content = response.data.decode('utf-8')
            if "Float Forecast" in content:
                print("✅ Page title found")
            else:
                print("❌ Page title NOT found")
                
            if "Seasonality Score" in content:
                print("✅ Seasonality Score found")
            else:
                print("❌ Seasonality Score NOT found")
                
            if "Top Predicted Locations" in content:
                print("✅ Predictions section found")
                
                # Extract links and test them
                import re
                import html
                from urllib.parse import unquote
                
                links = re.findall(r'href="/location/([^"]+)"', content)
                print(f"Found {len(links)} location links to test.")
                for link in links:
                    # Decode HTML entities (browser behavior)
                    link_decoded = html.unescape(link)
                    # Decode URL (for printing)
                    loc_name = unquote(link_decoded)
                    
                    print(f"Testing link for: {loc_name} (URL: /location/{link_decoded})")
                    resp = client.get(f'/location/{link_decoded}')
                    if resp.status_code == 200:
                        print(f"  ✅ Link working for {loc_name}")
                    else:
                        print(f"  ❌ Link BROKEN for {loc_name} (Status: {resp.status_code})")
            else:
                print("❌ Predictions section NOT found")
        else:
            print(f"❌ Route /forecast returned {response.status_code}")
            print(response.data.decode('utf-8'))

if __name__ == "__main__":
    test_forecast_route()
