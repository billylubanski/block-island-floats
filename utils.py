import os
import sqlite3
from datetime import datetime
import json

DB_NAME = 'floats.db'
REFRESH_MANIFEST = os.path.join('generated', 'refresh_manifest.json')

def load_refresh_manifest():
    if not os.path.exists(REFRESH_MANIFEST):
        return {}
    try:
        with open(REFRESH_MANIFEST, encoding='utf-8') as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}

def get_last_updated():
    """Get the last data refresh timestamp."""
    manifest = load_refresh_manifest()
    refreshed_at = manifest.get('refreshed_at')
    if refreshed_at:
        try:
            timestamp = datetime.fromisoformat(refreshed_at)
            return timestamp.strftime('%B %d, %Y at %I:%M %p %Z')
        except ValueError:
            pass

    if os.path.exists(DB_NAME):
        timestamp = os.path.getmtime(DB_NAME)
        return datetime.fromtimestamp(timestamp).strftime('%B %d, %Y at %I:%M %p')
    return "Unknown"

def get_data_stats():
    """Get statistics about the data"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    total_finds = cursor.execute('SELECT COUNT(*) FROM finds').fetchone()[0]
    dated_finds = cursor.execute('SELECT COUNT(*) FROM finds WHERE date_found IS NOT NULL AND date_found != ""').fetchone()[0]
    
    # Get date range of dated finds
    date_range = cursor.execute(
        'SELECT MIN(date_found), MAX(date_found) FROM finds WHERE date_found IS NOT NULL AND date_found != ""'
    ).fetchone()
    
    conn.close()
    
    return {
        'total_finds': total_finds,
        'dated_finds': dated_finds,
        'date_range': date_range
    }
