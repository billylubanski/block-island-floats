# Block Island Glass Float Tracker

A comprehensive web application that analyzes historical data from the Block Island Glass Float Project to help treasure hunters find the best locations and times to search for hidden glass floats on Block Island, Rhode Island.

## Features

### 🗺️ Dashboard
- **Interactive Heatmap**: Leaflet.js-powered visualization showing concentration patterns across the island
- **Year Filtering**: Filter all data by specific years or view all-time statistics
- **Top Hunting Grounds**: Ranked, clickable locations leading to detailed pages
- **Best Times to Hunt**: Monthly analysis based on historical find dates
- **Trend Charts**: Year-over-year discoveries with percentage bars
- **Stat Cards**: Total finds, years tracked, most popular spots, and total floats hidden

### 🎯 Field Mode (Mobile-First)
- **GPS Integration**: Auto-locates your position and calculates distances to hunting spots
- **Navigation Links**: One-tap directions to hunting grounds via Google Maps/Apple Maps
- **Sorted by Distance**: Nearest locations appear first when GPS is active
- **Compact Design**: Optimized for use while on-island

### 📍 Location Detail Pages
- **Photo Galleries**: Browse all floats found at each location (placeholders filtered out)
- **Statistics**: Total finds, peak year, top finder, year distribution
- **Find History**: Complete table of discoveries with dates and finders

### 🔍 Search & More
- **Full-Text Search**: Query across finders, locations, and float numbers
- **About Page**: Project background, data sources, and credits
- **PWA Support**: Install on your phone's home screen for app-like experience

## Data

- **4,361 floats** tracked from 2012-2025
- **100+ mapped locations** with GPS coordinates
- **200+ verified dates** for seasonal analysis
- **Continuous updates** from Block Island Glass Float Project website

## Tech Stack

- **Backend**: Flask (Python)
- **Frontend**: Vanilla JS, Leaflet.js for maps
- **Database**: SQLite
- **Scraping**: Playwright + Requests
- **Hosting**: Render (free tier)

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py

# Visit http://localhost:5000
```

## Data Sources

All data is scraped from the official [Block Island Glass Float Project](https://www.blockislandinfo.com/glass-float-project/) website.

## License

MIT

## Acknowledgments

- Block Island Tourism for maintaining the Glass Float Project
- All the float finders who report their discoveries!
