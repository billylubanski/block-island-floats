import sys
import os
import requests
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.getcwd())

from app import get_weather_data

def test_weather_fetching():
    print("Testing weather fetching logic...")
    
    # Mock response data
    mock_response = {
        'properties': {
            'temperature': {'value': 20},  # 20°C = 68°F
            'windSpeed': {'value': 15},    # 15 km/h = ~9 mph
            'textDescription': 'Partly Cloudy',
            'icon': 'https://api.weather.gov/icons/land/day/few?size=medium'
        }
    }
    
    # Mock requests.get
    with patch('requests.get') as mock_get:
        mock_obj = MagicMock()
        mock_obj.status_code = 200
        mock_obj.json.return_value = mock_response
        mock_get.return_value = mock_obj
        
        # Call function
        weather = get_weather_data()
        
        # Verify results
        if weather:
            print("✅ Weather data fetched successfully")
            print(f"   Temp: {weather['temp']}°F (Expected: 68°F)")
            print(f"   Wind: {weather['wind']} mph (Expected: 9 mph)")
            print(f"   Condition: {weather['condition']}")
            print(f"   Emoji: {weather['emoji']}")
            
            if weather['temp'] == 68 and weather['wind'] == 9:
                print("✅ Data conversion correct")
            else:
                print("❌ Data conversion failed")
        else:
            print("❌ Failed to fetch weather data")

if __name__ == "__main__":
    test_weather_fetching()
