# Recovery Rate Update - Summary

## What Changed

Updated the "Finds by Year" table to show **recovery rates** instead of raw find comparisons.

### Before
- Showed: Year | Finds | Trend %
- Progress bar compared find counts to the highest year
- Misleading: 2020 showed as "best" just because more people reported finds

### After
- Shows: Year | Hidden | Found | Recovery Rate %
- Progress bar shows percentage of floats recovered (found/hidden × 100)
- Meaningful: Shows actual treasure hunting success rate per year

## Example Data

| Year | Hidden | Found | Recovery Rate |
|------|--------|-------|---------------|
| 2020 | 575    | 393   | 68.3%         |
| 2024 | 558   | 243   | 43.5%         |
| 2025 | 558    | 243   | 43.5%         |

Now hunters can see that 2020 had a better recovery rate (68%) than recent years (~44%), giving a more accurate picture of success rates.

## Technical Implementation

1. **analyzer.py**: Added `get_year_recovery_stats()` function
   - Calculates hidden floats (max float number per year)
   - Calculates found floats (unique float numbers reported)
   - Calculates recovery rate percentage

2. **app.py**: Updated to use new function
   - Removed redundant year calculation code
   - Passes recovery stats to template
   
3. **index.html**: Updated table display
   - Changed columns from "Finds" to "Hidden/Found"
   - Progress bar now shows recovery_rate instead of count comparison
   - Description updated to explain recovery rates

## Files Modified
- `analyzer.py` - Added get_year_recovery_stats() function
- `app.py` - Updated index() route to use new stats
- `templates/index.html` - Updated Finds by Year table

## Impact
✅ More accurate representation of year-over-year performance  
✅ Helps hunters understand which years had better recovery rates  
✅ Accounts for different numbers of floats hidden each year
