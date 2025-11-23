import sqlite3
import re

conn = sqlite3.connect('floats.db')

# Check data quality for multiple years
years_to_check = [2020, 2021, 2022, 2023, 2024, 2025]

print("Year-by-Year Analysis of Float Numbering:\n" + "="*60)

for year in years_to_check:
    rows = conn.execute(
        'SELECT float_number FROM finds WHERE year = ? AND float_number IS NOT NULL', 
        (year,)
    ).fetchall()
    
    # Extract numeric float numbers
    nums = []
    for row in rows:
        match = re.search(r'(\d+)', str(row[0]))
        if match:
            nums.append(int(match.group(1)))
    
    if not nums:
        print(f"\n{year}: No float numbers found")
        continue
    
    nums_set = set(nums)
    max_num = max(nums)
    unique_found = len(nums_set)
    
    # Find missing numbers in sequence
    missing = [i for i in range(1, max_num + 1) if i not in nums_set]
    
    # Calculate unreported using current algorithm
    unreported = max_num - unique_found
    
    print(f"\n{year}:")
    print(f"  Max float #: {max_num}")
    print(f"  Unique floats found: {unique_found}")
    print(f"  Total records: {len(nums)}")
    print(f"  Missing in sequence: {len(missing)}")
    print(f"  Current 'unreported' calc: {unreported}")
    print(f"  First 10 missing: {missing[:10] if missing else 'None'}")
    
    # Check if numbering is mostly sequential
    if len(missing) == 0:
        print(f"  [OK] SEQUENTIAL - All numbers 1-{max_num} found!")
    elif len(missing) / max_num < 0.1:
        print(f"  [WARN] MOSTLY SEQUENTIAL - Only {len(missing)} gaps ({len(missing)/max_num*100:.1f}%)")
    else:
        print(f"  [ERROR] NOT SEQUENTIAL - {len(missing)} gaps ({len(missing)/max_num*100:.1f}%)")

# Write summary to file as well
with open('float_numbering_analysis.txt', 'w') as f:
    conn = sqlite3.connect('floats.db')
    for year in years_to_check:
        rows = conn.execute(
            'SELECT float_number FROM finds WHERE year = ? AND float_number IS NOT NULL', 
            (year,)
        ).fetchall()
        
        nums = []
        for row in rows:
            match = re.search(r'(\d+)', str(row[0]))
            if match:
                nums.append(int(match.group(1)))
        
        if nums:
            nums_set = set(nums)
            max_num = max(nums)
            unique_found = len(nums_set)
            missing = [i for i in range(1, max_num + 1) if i not in nums_set]
            
            f.write(f"{year}: Max={max_num}, Found={unique_found}, Missing={len(missing)} ({len(missing)/max_num*100:.1f}%)\n")

conn.close()
print("\nAnalysis saved to float_numbering_analysis.txt")
