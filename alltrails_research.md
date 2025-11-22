# AllTrails Integration Research

## Summary

AllTrails integration is **possible but limited** for Block Island glass float hunting.

## Key Findings

### 1. **URL Structure**
AllTrails uses this format for trails:
```
https://www.alltrails.com/explore/map/[trail-name-and-id]
```

Example: `https://www.alltrails.com/explore/map/mohegan-bluffs-trail-123abc`

### 2. **Deep Linking**
- **App Scheme**: `alltrails://` exists but parameters are not publicly documented
- **No Official API**: AllTrails doesn't provide public deep link documentation
- **Web Links Work**: HTTPS links (`https://www.alltrails.com/trail/...`) will:
  - Open in AllTrails app if installed
  - Fallback to website if not installed

### 3. **Block Island Trails**
Major trails on Block Island include:
- **Clayhead Preserve** - 5 miles, oldest trail
- **Rodman's Hollow** - 3.65 miles, glacial basin
- **Hodge Family Wildlife Preserve** - 2 miles, easy
- **Fresh Pond Trail** - 1.5 miles
- **Turnip Farm/Elaine Loffredo Preserve** - 2 miles

### 4. **Challenge for Glass Float Hunting**
**Problem**: Glass float locations (Mohegan Bluffs, Andy's Way, etc.) are mostly **beaches and coastal areas**, not hiking trails.

**Mismatch**:
- AllTrails = Hiking/walking trails through preserves
- Glass Floats = Found on beaches, coastal paths, shorelines

**Better Alternatives**:
- Google Maps (shows beach access, coastal areas)
- Apple Maps (same coverage)
- Direct GPS coordinates

## Recommendation

**Don't prioritize AllTrails integration** because:

1. ❌ Most float spots aren't official trails
2. ❌ No public API for deep linking
3. ❌ Web links work but aren't better than Google/Apple Maps
4. ✅ Google Maps/Apple Maps already work perfectly
5. ✅ They show beaches, roads, and coastal access better

## If You Still Want AllTrails

### Option: Add Web Links for Trail-Based Locations

For locations that ARE on trails (like Clayhead, Rodman's Hollow):

```html
<a href="https://www.alltrails.com/trail/us/rhode-island/clayhead-bluff-trail">
  View Trail on AllTrails
</a>
```

This would:
- Open AllTrails app if installed
- Or open website if not
- Work on both iOS and Android

### Implementation Example

```python
# In locations.py, add AllTrails IDs for trail-based locations
LOCATIONS = {
    "Rodman's Hollow": {
        "lat": 41.1683,
        "lon": -71.5642,
        "alltrails": "https://www.alltrails.com/trail/us/rhode-island/rodmans-hollow"
    },
    "Clayhead": {
        "lat": 41.2167,
        "lon": -71.5500,
        "alltrails": "https://www.alltrails.com/trail/us/rhode-island/clayhead-bluff"
    }
}
```

Then in field.html:
```html
{% if spot.alltrails %}
<a href="{{ spot.alltrails }}" class="nav-btn">AllTrails</a>
{% endif %}
```

## Bottom Line

**Current implementation with Google/Apple Maps is optimal.** AllTrails would add complexity without significant benefit for most glass float locations, which are beaches rather than trail heads.
