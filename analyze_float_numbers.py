import sqlite3
import re
from collections import defaultdict

conn = sqlite3.connect('floats.db')
c = conn.cursor()

# Get all float numbers by year
c.execute("SELECT year, float_number, finder FROM finds WHERE float_number IS NOT NULL AND float_number != '' ORDER BY year, float_number")
rows = c.fetchall()

# Parse float numbers - they might be like "267", "#267", "267 - Name", etc.
float_numbers_by_year = defaultdict(set)

def extract_number(float_num_str):
    """Extract the numeric float number from various formats"""
    if not float_num_str:
        return None
    # Remove common prefixes and suffixes
    match = re.search(r'(\d+)', str(float_num_str))
    if match:
        return int(match.group(1))
    return None

for year, float_num, finder in rows:
    num = extract_number(float_num)
    if num:
        float_numbers_by_year[year].add(num)

# Analyze by year
print("Glass Float Number Analysis by Year")
print("=" * 60)
for year in sorted(float_numbers_by_year.keys()):
    numbers = sorted(float_numbers_by_year[year])
    if numbers:
        max_num = max(numbers)
        found_count = len(numbers)
        print(f"\n{year}:")
        print(f"  Highest float number: #{max_num}")
        print(f"  Unique floats found/reported: {found_count}")
        print(f"  Potential unreported: {max_num - found_count}")
        print(f"  Float numbers range: {min(numbers)} - {max_num}")
        
        # Show some gaps (missing numbers)
        all_expected = set(range(1, max_num + 1))
        missing = sorted(all_expected - set(numbers))
        if missing:
            if len(missing) <= 10:
                print(f"  Missing float numbers: {missing}")
            else:
                print(f"  Missing float numbers: {missing[:5]}...{missing[-5:]} (total: {len(missing)})")

# Overall summary
print("\n" + "=" * 60)
print("SUMMARY:")
print("=" * 60)
total_found = sum(len(nums) for nums in float_numbers_by_year.values())
print(f"Total unique float numbers tracked: {total_found}")

# Check 2025 in detail
if 2025 in float_numbers_by_year:
    nums_2025 = sorted(float_numbers_by_year[2025])
    max_2025 = max(nums_2025)
    print(f"\n2025 Details:")
    print(f"  If they hide floats #1-#{max_2025}, then:")
    print(f"  - Total hidden: {max_2025}")
    print(f"  - Found/Reported: {len(nums_2025)}")
    print(f"  - Still out there: {max_2025 - len(nums_2025)}")

conn.close()
