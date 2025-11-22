#!/usr/bin/env python3
"""
Add Field Mode link to navigation
"""

# Read the file
with open('templates/base.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the nav section
old_nav = '''            <nav>
                <a href="/">Dashboard</a>
                <a href="/search">Search</a>
                <a href="/about">About</a>
            </nav>'''

new_nav = '''            <nav>
                <a href="/">Dashboard</a>
                <a href="/field">🎯 Field Mode</a>
                <a href="/search">Search</a>
                <a href="/about">About</a>
            </nav>'''

if old_nav in content:
    content = content.replace(old_nav, new_nav)
    
    # Write back
    with open('templates/base.html', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Added Field Mode link to navigation")
else:
    print("❌ Could not find nav section to update")
