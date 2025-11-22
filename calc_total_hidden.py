import sqlite3
import re

conn = sqlite3.connect('floats.db')
c = conn.cursor()

# Get all years
c.execute('SELECT DISTINCT year FROM finds ORDER BY year')
years = [row[0] for row in c.fetchall()]

total_hidden = 0
print("Floats hidden per year:")
print("=" * 40)

for year in years:
    # Get all float numbers for this year
    c.execute('SELECT float_number FROM finds WHERE year = ? AND float_number IS NOT NULL AND float_number != ""', (year,))
    float_nums = []
    
    for row in c.fetchall():
        match = re.search(r'(\d+)', str(row[0]))
        if match:
            float_nums.append(int(match.group(1)))
    
    if float_nums:
        max_for_year = max(float_nums)
        total_hidden += max_for_year
        print(f"{year}: {max_for_year} floats hidden")
    else:
        print(f"{year}: 0 floats hidden (no data)")

print("=" * 40)
print(f"TOTAL HIDDEN ACROSS ALL YEARS: {total_hidden}")

# Compare to total found
c.execute('SELECT COUNT(*) FROM finds')
total_found = c.fetchone()[0]
print(f"Total floats found/reported: {total_found}")
print(f"Still out there overall: {total_hidden - total_found}")

conn.close()
