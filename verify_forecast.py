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
            else:
                print("❌ Predictions section NOT found")
        else:
            print(f"❌ Route /forecast returned {response.status_code}")
            print(response.data.decode('utf-8'))

if __name__ == "__main__":
    test_forecast_route()
