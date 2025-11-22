#!/usr/bin/env python3
"""
Fix the max_count initialization bug in the template
"""

# Read the file
with open('templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix: Change initial max_count from years[0]['count'] to 0
old_code = "{% set max_count = years[0]['count'] if years else 1 %}"
new_code = "{% set max_count = 0 %}"

if old_code in content:
    content = content.replace(old_code, new_code)
    
    # Write back
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Fixed max_count initialization bug")
    print("   Changed from: years[0]['count'] (which was 284)")  
    print("   Changed to: 0 (will correctly calculate 416 as max)")
else:
    print("❌ Could not find the code to replace")
