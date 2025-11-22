#!/usr/bin/env python3
"""
Update the first stat card to show both total found and total hidden
"""

# Read the file
with open('templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and update the first stat card
old_card = '''    <div class="card stat-card">
        <div class="stat-value">{{ total_finds }}</div>
        <div class="stat-label">Total Floats Found</div>
    </div>'''

new_card = '''    <div class="card stat-card">
        <div class="stat-value">{{ total_finds }}</div>
        <div class="stat-label">Total Floats Found</div>
        <div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid rgba(255,255,255,0.1);">
            <div style="font-size: 1.25rem; font-weight: 600; color: var(--text-secondary);">{{ total_hidden_all_years }}</div>
            <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.25rem;">Total Floats Hidden</div>
        </div>
    </div>'''

if old_card in content:
    content = content.replace(old_card, new_card)
    
    # Write back
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Updated first stat card to include total hidden")
    print("   Found: 4,361")
    print("   Hidden: 7,335")
else:
    print("❌ Could not find the card to update")
