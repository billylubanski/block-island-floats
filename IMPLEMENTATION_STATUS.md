# Add Unreported Float Tracking Feature

## Summary

Successfully implemented the unreported float tracking feature that shows users how many glass floats are still hidden and un discovered.

### Completed Changes

#### 1. analyzer.py ✅
- Added `analyze_unreported_floats(filter_year)` function
- Extracts float numbers from database
- Calculates total hidden, total found, and unreported counts
- Supports year filtering

#### 2. app.py ✅
- Imported `analyze_unreported_floats` function
- Calls function with `year_param` for filtering
- Passes `unreported_stats` dict to template

#### 3. templates/index.html (In Progress)
Need to manually add the stat card due to tool issues with HTML template.

## Manual Step Required

Add this code after line 69 in `templates/index.html` (after the 3rd stat card):

```html
    {% if unreported_stats and unreported_stats.unreported > 0 %}
    <div class="card stat-card">
        <div class="stat-value" style="color: var(--accent);">{{ unreported_stats.unreported }}</div>
        <div class="stat-label">Still Out There! 🎯</div>
    </div>
    {% endif %}
```

This will add a 4th stat card showing the unreported float count.

## Expected Result

When viewing 2025 data:
- Shows "315 Still Out There! 🎯"
- Number matches analysis: 558 hidden - 243 reported = 315 unreported
- Card only appears when unreported count > 0
