#!/usr/bin/env python3
"""
Migrate image URLs from JSON source data to database
"""
import sqlite3
import json
import os

# Load all JSON files
json_files = [
    'all_floats_final.json',
    'scraped_data/floats_2025.json',
    'scraped_data/floats_2024.json',
    'scraped_data/floats_2023.json',
    'scraped_data/floats_2022.json',
    'scraped_data/floats_2021.json',
    'scraped_data/floats_2020.json',
    'scraped_data/floats_2019.json',
    'scraped_data/floats_2018.json',
    'scraped_data/floats_2017.json',
    'scraped_data/floats_2016.json',
    'scraped_data/floats_2015.json',
    'scraped_data/floats_2014.json',
    'scraped_data/floats_2013.json',
    'scraped_data/floats_2012.json',
]

# Build image URL lookup by ID
image_lookup = {}

for json_file in json_files:
    if os.path.exists(json_file):
        print(f'Loading {json_file}...')
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for entry in data:
                float_id = entry.get('id')
                image_url = entry.get('image', '')
                if float_id and image_url:
                    image_lookup[float_id] = image_url

print(f'\n✅ Loaded {len(image_lookup)} image URLs from JSON files')

# Update database
conn = sqlite3.connect('floats.db')
cursor = conn.cursor()

# Get all finds with their IDs
cursor.execute('SELECT id, url FROM finds')
finds = cursor.fetchall()

updated = 0
for find_id, url in finds:
    # Extract original ID from URL
    # URL format: https://www.blockislandinfo.com/event/title/5719/
    if url:
        parts = url.rstrip('/').split('/')
        if len(parts) > 0:
            original_id = parts[-1]
            if original_id in image_lookup:
                image_url = image_lookup[original_id]
                cursor.execute('UPDATE finds SET image_url = ? WHERE id = ?', (image_url, find_id))
                updated += 1

conn.commit()
conn.close()

print(f'✅ Updated {updated} finds with image URLs')
print(f'   {len(finds) - updated} finds without images')
