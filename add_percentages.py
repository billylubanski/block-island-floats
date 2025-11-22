#!/usr/bin/env python3
"""
Script to add percentage display next to trend bars in Finds by Year section
"""

# Read the file
with open('templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the trend bar section
old_code = '''                    <td>
                        <div
                            style="background: rgba(255,255,255,0.1); height: 10px; border-radius: 5px; width: 100%; display: flex; align-items: center;">
                            <div
                                style="background: linear-gradient(to right, var(--accent), #1A8672); height: 100%; border-radius: 5px; width: {{ (row['count'] / max_count * 100) if max_count > 0 else 0 }}%; transition: width 0.3s ease;">
                            </div>
                        </div>
                    </td>'''

new_code = '''                    <td>
                        <div style="display: flex; align-items: center; gap: 0.75rem;">
                            <div
                                style="background: rgba(255,255,255,0.1); height: 10px; border-radius: 5px; flex: 1; display: flex; align-items: center;">
                                <div
                                    style="background: linear-gradient(to right, var(--accent), #1A8672); height: 100%; border-radius: 5px; width: {{ (row['count'] / max_count * 100) if max_count > 0 else 0 }}%; transition: width 0.3s ease;">
                                </div>
                            </div>
                            <span style="color: var(--text-secondary); font-size: 0.875rem; min-width: 3rem; text-align: right;">
                                {{ (row['count'] / max_count * 100) | round(0) | int }}%
                            </span>
                        </div>
                    </td>'''

if old_code in content:
    content = content.replace(old_code, new_code)
    
    # Write back
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Successfully added percentage display to trend bars")
else:
    print("❌ Could not find the code to replace")
    print("This might mean the template structure has changed")
