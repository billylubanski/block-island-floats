#!/usr/bin/env python3
"""
Make location names clickable in the Top Hunting Grounds table
"""

# Read the file
with open('templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace location name with link
old_line = '                    <td style="font-weight: 600; color: var(--text-primary);">{{ loc.name }}</td>'
new_line = '''                    <td style="font-weight: 600; color: var(--text-primary);">
                        <a href="/location/{{ loc.name }}" style="color: var(--accent); text-decoration: none;">
                            {{ loc.name }}
                        </a>
                    </td>'''

if old_line in content:
    content = content.replace(old_line, new_line)
    
    # Write back
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Made location names clickable in dashboard")
else:
    print("❌ Could not find location name to update")
