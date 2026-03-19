import sqlite3
import sys
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from analyzer import normalize_location


def main():
    conn = sqlite3.connect(REPO_ROOT / "floats.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM finds WHERE location_normalized = ?",
        ("Other/Unknown",),
    )
    count = cursor.fetchone()[0]
    print(f'Finds with location_normalized = "Other/Unknown": {count}')

    all_locations = cursor.execute("SELECT location_raw FROM finds").fetchall()
    normalized_locations = [normalize_location(row[0]) for row in all_locations]
    location_counts = Counter(normalized_locations)

    if "Other/Unknown" in location_counts:
        print(f'"Other/Unknown" has {location_counts["Other/Unknown"]} finds total')
    else:
        print('"Other/Unknown" not found in normalized locations')

    conn.close()


if __name__ == "__main__":
    main()
