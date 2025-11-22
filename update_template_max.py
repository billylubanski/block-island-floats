#!/usr/bin/env python3
"""
Update template to use max_year_count from Python instead of calculating in Jinja
"""

# Read the file
with open('templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove the Jinja max calculation logic and use the Python-calculated value
old_section = '''                {% set max_count = 1 %}
                {% for row in years %}
                {% if row['count'] > max_count %}
                {% set max_count = row['count'] %}
                {% endif %}
                {% endfor %}

                {% for row in years %}'''

new_section = '''                {% for row in years %}'''

if old_section in content:
    content = content.replace(old_section, new_section)
    
    # Also replace all instances of max_count with max_year_count
    content = content.replace('max_count', 'max_year_count')
    
    # Write back
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Updated template to use max_year_count from Python")
    print("   Removed Jinja loop logic")
    print("   Replaced max_count with max_year_count throughout")
else:
    print("❌ Could not find the code to replace")
