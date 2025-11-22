# Block Island Glass Float Tracker

A web application that analyzes historical data from the Block Island Glass Float Project to help treasure hunters find the best locations and times to search for hidden glass floats.

## Features

- **Interactive Heatmap**: Visualize concentration patterns of float discoveries across Block Island
- **Top Hunting Grounds**: Ranked list of the most productive locations
- **Best Times to Hunt**: Seasonal analysis showing peak finding months
- **Trend Analysis**: Historical charts showing finds over the years
- **Mobile Optimized**: Responsive design works great on phones and tablets

## Data

- **4,200+ floats** tracked from 2012-2025
- **200+ verified dates** for recent finds (2024-2025)
- **100+ mapped locations** with GPS coordinates

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
