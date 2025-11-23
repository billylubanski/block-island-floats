# Float Tracker - Development Roadmap
**Created:** November 23, 2025  
**Status:** Active Planning

---

## 🎯 Quick Reference

### Current State
- ✅ **Production Ready** - Deployed on Render with 4,361 floats
- ✅ **6 Major Pages** - Dashboard, Field Mode, Location Details, About, Search
- ✅ **PWA Enabled** - Installable on mobile devices
- ✅ **Mobile-First** - GPS integration and responsive design

### Immediate Opportunity
⚠️ **5-Minute Win:** Add "Still Out There! 🎯" stat card (instructions in IMPLEMENTATION_STATUS.md)

---

## 📋 Prioritized Roadmap

### Phase 1: Quick Wins (1-2 weeks)
🎯 **Goal:** Polish existing features and fill small gaps

| Priority | Feature | Complexity | Impact | Time |
|----------|---------|------------|--------|------|
| 🔥 High | Unreported Float Stat Card | Low | High | 5 min |
| 🔥 High | Automated Tests (pytest) | Medium | High | 3-4 hours |
| ⭐ Medium | CSV/JSON Export | Low | Medium | 1-2 hours |
| ⭐ Medium | Advanced Search Filters | Medium | Medium | 4-5 hours |

**Deliverables:**
- 4th stat card showing unreported floats
- pytest suite covering analyzer.py functions
- Export button on dashboard/search pages
- Multi-select year + location filters

---

### Phase 2: Mobile Enhancement (2-3 weeks)
🎯 **Goal:** Improve Field Mode for on-island use

| Priority | Feature | Complexity | Impact | Time |
|----------|---------|------------|--------|------|
| 🔥 High | Offline Mode (Service Worker) | Medium | High | 6-8 hours |
| 🔥 High | Weather Integration | Low | Medium | 2 hours |
| ⭐ Medium | Favorite Locations | Medium | Medium | 4 hours |
| ✨ Low | Install Tutorial (PWA) | Low | Low | 1 hour |

**Deliverables:**
- Service worker caching for offline access
- Current Block Island weather on Field Mode
- LocalStorage-based bookmark system
- First-time user walkthrough

---

### Phase 3: Community Features (3-4 weeks)
🎯 **Goal:** Enable user engagement and contributions

| Priority | Feature | Complexity | Impact | Time |
|----------|---------|------------|--------|------|
| 🔥 High | Photo Upload Feature | High | High | 10-12 hours |
| 🔥 High | Push Notifications | High | Medium | 8-10 hours |
| ⭐ Medium | Finder Profile Pages | Medium | Medium | 6-8 hours |
| ⭐ Medium | Social Sharing | Low | Low | 2-3 hours |

**Deliverables:**
- Photo submission form with cloud storage (Cloudinary/S3)
- Admin review queue for submissions
- Web Push API for new float alerts
- Finder leaderboards and achievements
- Open Graph meta tags for social previews

---

### Phase 4: Polish & Scale (Ongoing)
🎯 **Goal:** Long-term maintenance and nice-to-haves

| Priority | Feature | Complexity | Impact | Time |
|----------|---------|------------|--------|------|
| ✨ Low | Historical Photo Carousel | Low | Low | 2 hours |
| ✨ Low | Print-Friendly Layouts | Low | Low | 1 hour |
| ✨ Low | Multi-Language Support | High | Low | 15+ hours |
| ✨ Low | API Documentation | Medium | Medium | 4 hours |

**Deliverables:**
- Swiper.js carousel on About page
- CSS print stylesheets
- Flask-Babel i18n (Spanish, Portuguese)
- OpenAPI spec for developer access

---

## 🔍 Detailed Feature Specs

### 1. Unreported Float Stat Card
**Problem:** Users don't know how many floats are still hidden  
**Solution:** Add 4th stat card showing count when year is selected

**Implementation:**
```html
<!-- Add to templates/index.html after line 76 -->
{% if unreported_stats and unreported_stats.unreported > 0 %}
<div class="card stat-card">
    <div class="stat-value" style="color: var(--accent);">{{ unreported_stats.unreported }}</div>
    <div class="stat-label">Still Out There! 🎯</div>
</div>
{% endif %}
```

**Backend:** Already implemented in `analyzer.py` and `app.py`  
**Testing:** Filter to 2025, verify "315 Still Out There!" appears

---

### 2. Offline Mode (Service Worker)
**Problem:** Block Island has spotty cell coverage  
**Solution:** Cache critical assets for offline browsing

**Tech Stack:**
- Service worker registration in base.html
- Cache API for static files + database queries
- Background sync for deferred actions

**Cached Resources:**
- HTML templates (dashboard, field, about)
- CSS/JS files
- Map tiles (limited zoom levels)
- Location coordinates
- Last 30 days of float data

**Testing:**
1. Install PWA on mobile
2. Enable airplane mode
3. Verify Field Mode + Dashboard still load

---

### 3. Photo Upload Feature
**Problem:** Many floats have placeholder images  
**Solution:** Community-driven photo submissions

**User Flow:**
1. User clicks "Upload Photo" on location detail page
2. Selects file + enters float number/year
3. Preview before submit
4. Admin reviews in moderation queue
5. Approved photos replace placeholders

**Tech Requirements:**
- New route: `POST /upload_photo`
- File validation (JPEG/PNG, max 5MB)
- Cloud storage (Cloudinary recommended)
- Database: Add `photos` table with moderation status
- Admin interface: `/admin/photos` (password-protected)

**Security:**
- CSRF tokens
- File type validation
- Image size limits
- Rate limiting (5 uploads/day per IP)

---

### 4. Push Notifications
**Problem:** Hunters want immediate alerts for new floats  
**Solution:** Web Push API subscriptions

**User Flow:**
1. User clicks "Get Alerts" button
2. Browser prompts for notification permission
3. Backend subscribes user to push service
4. Daily scraper checks for new floats
5. New floats trigger push to all subscribers

**Tech Requirements:**
- Push service: OneSignal or Firebase Cloud Messaging
- Subscription table in database
- Cron job for daily scraper + push trigger
- Notification payload: "3 new floats hidden today!"

**Testing:**
1. Subscribe to notifications
2. Manually trigger test push
3. Verify notification appears on mobile

---

### 5. Advanced Search Filters
**Problem:** Power users want granular queries  
**Solution:** Multi-select filters for year, location, finder

**UI Design:**
- Dropdown multi-select for years
- Autocomplete for locations
- Text input for finder name
- Date range picker for "Found between..."
- AND/OR toggle for filter logic

**Backend:**
- Update `/search` to accept multiple parameters
- Build dynamic SQL WHERE clauses
- Add pagination (50 results per page)
- Cache common queries

---

### 6. Finder Profile Pages
**Problem:** No recognition for top contributors  
**Solution:** Dedicated pages with stats and achievements

**Route:** `/finder/<name>`

**Content:**
- Total finds (all-time + per year)
- Locations visited (map view)
- Rarest finds (low float numbers)
- Achievements: "First Finder of 2025", "Explorer (25+ locations)", etc.
- Timeline chart of discoveries

**Implementation:**
- New template: `finder_profile.html`
- SQL queries: Group by finder, aggregate stats
- Badge system: JSON file with achievement definitions

---

## 🧪 Testing Strategy

### Current State
⚠️ **No automated tests exist**

### Phase 1 Testing Setup
**Tool:** pytest + pytest-flask

**Coverage Areas:**
1. **Unit Tests** (`test_analyzer.py`)
   - `normalize_location()` - 20 edge cases
   - `analyze_dates()` - Date format parsing
   - `analyze_unreported_floats()` - Count calculations

2. **Integration Tests** (`test_routes.py`)
   - Dashboard loads with 200 status
   - Year filter query parameter works
   - Search returns results
   - Location detail 404 for invalid names

3. **End-to-End** (Manual for now)
   - PWA install flow (iOS + Android)
   - Geolocation button
   - Field Mode navigation links

**Run Command:**
```bash
pytest --cov=app --cov=analyzer --cov-report=html
```

**CI/CD:** Add GitHub Actions workflow to run on PR

---

## 📊 Success Metrics

### Technical Health
- **Test Coverage:** >80% for core modules
- **Page Load Time:** <2s on 4G
- **Mobile Score (Lighthouse):** >90
- **Accessibility (WCAG):** AA compliance

### User Engagement (Post-Community Features)
- **Photo Submissions:** 50+ in first month
- **PWA Installs:** 100+ in first quarter
- **Push Subscribers:** 25% of unique visitors
- **Search Usage:** 10% of sessions

---

## 🚧 Technical Debt

### Current Issues
1. **No Automated Tests** - Risky refactoring
2. **Unpopulated DB Column** - `location_normalized` unused
3. **Hard-Coded Limits** - Map markers (30), search results (50)
4. **No Pagination** - Search/location tables can be slow

### Refactoring Opportunities
1. **Modularize Routes** - Split `app.py` into blueprints
2. **API Layer** - Separate JSON endpoints for future mobile app
3. **Caching** - Flask-Caching for expensive queries
4. **Database Indexes** - Speed up year + location filters

---

## 💡 Innovation Ideas (Backlog)

### 1. AR Treasure Hunt Mode
Use device camera + GPS to show "hot/cold" proximity to known find locations

**Tech:** WebXR API, Three.js  
**Complexity:** Very High  
**Impact:** High (viral potential)

---

### 2. Predictive Model
Machine learning to predict where floats will wash up based on weather/tides

**Tech:** Python scikit-learn, NOAA API  
**Complexity:** Very High  
**Impact:** Medium (experimental)

---

### 3. Community Forum
Discussion board for hunters to share tips and coordinate searches

**Tech:** Discourse integration or custom Flask forum  
**Complexity:** High  
**Impact:** Medium

---

### 4. Email Digest
Weekly email with new finds, top hunters, upcoming events

**Tech:** SendGrid, Celery for scheduling  
**Complexity:** Medium  
**Impact:** Medium

---

## 🔄 Maintenance Schedule

### Daily
- Monitor Render logs for errors
- Check database size (backup if >100MB)

### Weekly
- Run scraper to fetch new floats
- Review any user-submitted photos (once feature live)

### Monthly
- Update dependencies (Flask, Leaflet.js)
- Review analytics (Google Analytics recommended)
- Database backup to external storage

### Quarterly
- Security audit of dependencies
- Performance testing (Lighthouse)
- User feedback survey

---

## 📞 Next Actions

### This Week
1. ✅ Complete feature audit (DONE)
2. ✅ Update documentation (DONE)
3. 🔨 Add unreported float stat card (5 min)
4. 🔨 Write pytest suite for analyzer.py (3 hours)

### Next Sprint (2 weeks)
5. 🔨 Implement offline service worker
6. 🔨 Add CSV export functionality
7. 🔨 Advanced search filters
8. 🔨 Weather widget on Field Mode

### Next Month
9. 🔨 Photo upload system (MVP)
10. 🔨 Finder profile pages
11. 🔨 Push notification infrastructure

---

## ✅ Sign-Off

**Current Assessment:** The Float Tracker is production-ready with a solid foundation for community features.

**Recommended Focus:** Prioritize offline mode and photo uploads to maximize field usability and user engagement.

**Risk Level:** Low - Core features are stable, new additions are modular and low-risk.

---

*Roadmap version: 1.0 | Last updated: November 23, 2025*
