#!/usr/bin/env python3
"""
Fix the divide by zero error by initializing to 1 instead of 0
"""

# Read the file
with open('templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix: Change max_count from 0 to 1 to prevent divide by zero
old_code = "{% set max_count = 0 %}"
new_code = "{% set max_count = 1 %}"

if old_code in content:
    content = content.replace(old_code, new_code)
    
    # Write back
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Fixed divide by zero error")
    print("   Changed max_count from 0 to 1")
    print("   Note: Jinja2 loop variables don't persist, so loop doesn't update it")
    print("   We need a better solution...")
else:
    print("❌ Could not find the code to replace")
