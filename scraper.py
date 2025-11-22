import requests
from bs4 import BeautifulSoup
import sqlite3
import re

# Database setup
DB_NAME = 'floats.db'

def setup_database():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Drop table to ensure schema update and fresh data
    c.execute('DROP TABLE IF EXISTS finds')
    c.execute('''
        CREATE TABLE finds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER,
            float_number TEXT,
            finder TEXT,
            location_raw TEXT,
            location_normalized TEXT,
            date_found TEXT
        )
    ''')
    conn.commit()
    conn.close()

def clean_text(text):
    if not text:
        return ""
    return text.strip()

def extract_date(text):
    # Patterns to look for:
    # MM/DD/YY or MM/DD/YYYY
    # Month DD, YYYY
    
    # Regex for MM/DD/YY or MM/DD/YYYY
    date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', text)
    if date_match:
        return date_match.group(1)
        
    # Regex for Month DD, YYYY (e.g., October 12, 2023)
    month_match = re.search(r'([A-Z][a-z]+ \d{1,2}, \d{4})', text)
    if month_match:
        return month_match.group(1)

    # Regex for Month YYYY (e.g., June 2017)
    month_year_match = re.search(r'([A-Z][a-z]+ \d{4})', text)
    if month_year_match:
        return month_year_match.group(1)
        
    return None

def parse_archive_line(line, year):
    # Typical format: "560 - C. Rydingsward - Rock wall Lewis Dickens Farm"
    # Sometimes: "#561 - K. Nelson - Beacon hill road stonewall."
    
    line = line.strip()
    if line.startswith('#'):
        line = line[1:]
    
    # Normalize hyphens
    line = line.replace('–', '-').replace('—', '-')
        
    parts = line.split(' - ', 2)
    if len(parts) < 3:
        # Try splitting by just hyphen if spaces are missing
        parts = line.split('-', 2)
        
    if len(parts) >= 3:
        float_num = clean_text(parts[0])
        finder = clean_text(parts[1])
        location = clean_text(parts[2])
        
        # Extract date from location or finder if present
        date_found = extract_date(location)
        if not date_found:
            date_found = extract_date(finder)
            
        return {
            'year': year,
            'float_number': float_num,
            'finder': finder,
            'location_raw': location,
            'date_found': date_found
        }
    return None

def scrape_archives():
    url = "https://www.blockislandinfo.com/glass-float-project/found-float-archives/"
    print(f"Scraping {url}...")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        # DEBUG: Write full HTML
        with open('debug_scraper_html.html', 'w', encoding='utf-8') as f:
            f.write(response.text)
            
        soup = BeautifulSoup(response.content, 'html.parser')
        
        finds = []
        text = soup.get_text(separator='\n')
        lines = text.split('\n')
        
        # DEBUG: Write to file
        with open('debug_scraper_output.txt', 'w', encoding='utf-8') as f:
            for i, line in enumerate(lines):
                f.write(f"{i}: {repr(line)}\n")
        
        current_year = None
        year_pattern = re.compile(r'^\s*(20\d{2})\s*$')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Check if line is a year
            year_match = year_pattern.match(line)
            if year_match:
                current_year = int(year_match.group(1))
                continue
            
            if current_year:
                # Relaxed regex to catch lines starting with digits, let parser handle the rest
                if re.match(r'^#?\d+', line):
                    find = parse_archive_line(line, current_year)
                    if find:
                        finds.append(find)
                        
        return finds

    except Exception as e:
        print(f"Error scraping archives: {e}")
        return []

def scrape_current_year():
    url = "https://www.blockislandinfo.com/glass-float-project/found-floats/"
    print(f"Scraping {url}...")
    current_year = 2025 
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        finds = []
        text = soup.get_text(separator='\n')
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if re.match(r'^#?\d+', line):
                find = parse_archive_line(line, current_year)
                if find:
                    finds.append(find)
        
        return finds
    except Exception as e:
        print(f"Error scraping current: {e}")
        return []

def save_finds(finds):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    count = 0
    for f in finds:
        # Check if exists to avoid duplicates (simple check)
        c.execute('SELECT id FROM finds WHERE year=? AND float_number=? AND finder=?', 
                  (f['year'], f['float_number'], f['finder']))
        if not c.fetchone():
            c.execute('''
                INSERT INTO finds (year, float_number, finder, location_raw, date_found)
                VALUES (?, ?, ?, ?, ?)
            ''', (f['year'], f['float_number'], f['finder'], f['location_raw'], f['date_found']))
            count += 1
    conn.commit()
    conn.close()
    print(f"Saved {count} new finds.")

if __name__ == "__main__":
    setup_database()
    
    # Scrape Archives
    archive_finds = scrape_archives()
    print(f"Found {len(archive_finds)} archive entries.")
    save_finds(archive_finds)
    
    # Scrape Current
    current_finds = scrape_current_year()
    print(f"Found {len(current_finds)} current entries.")
    save_finds(current_finds)
