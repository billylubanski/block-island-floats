#!/usr/bin/env python3
"""
Script to safely add the unreported floats stat card to index.html
"""

# Read the file
with open('templates/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line with the closing </div> after the 3rd stat card (around line 70)
# We're looking for the stat-grid closing div
insert_position = None
for i, line in enumerate(lines):
    # Look for the line after "Most Popular Spot" stat card
    if 'Most Popular Spot' in line:
        # Find the next </div> after a few lines (closing the 3rd card)
        for j in range(i, min(i+10, len(lines))):
            if '</div>' in lines[j] and 'card stat-card' not in lines[j]:
                # Check if the next line is the stat-grid closing
                if j+1 < len(lines) and '</div>' in lines[j+1]:
                    insert_position = j + 1  # Insert before the stat-grid closing div
                    break
        break

if insert_position:
    # Lines to insert
    new_lines = [
        '    {% if unreported_stats and unreported_stats.unreported > 0 %}\n',
        '    <div class="card stat-card">\n',
        '        <div class="stat-value" style="color: var(--accent);">{{ unreported_stats.unreported }}</div>\n',
        '        <div class="stat-label">Still Out There! 🎯</div>\n',
        '    </div>\n',
        '    {% endif %}\n'
    ]
    
    # Insert the lines
    lines[insert_position:insert_position] = new_lines
    
    # Write back
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print(f"✅ Successfully added unreported floats stat card at line {insert_position}")
    print("Added lines:")
    for line in new_lines:
        print(f"  {line.rstrip()}")
else:
    print("❌ Could not find insertion point")
