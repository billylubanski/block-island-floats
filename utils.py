import os
import sqlite3
from datetime import datetime

DB_NAME = 'floats.db'

def get_last_updated():
    """Get the last modification time of the database"""
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
