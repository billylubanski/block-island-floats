# Public Launch Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing Block Island Glass Float Tracker feel safe, clear, and polished enough to share publicly.

**Architecture:** Keep the current Flask/Jinja/CSS shape. Add small presentation helpers in `app.py` only where they make freshness, metadata, or archive limitations easier to render. Prefer copy, responsive layout, and metadata changes over new product features.

**Tech Stack:** Flask, Jinja templates, SQLite-backed local data, pytest, Playwright/browser rendered QA, static CSS, web app manifest.

---

## File Structure

- Modify `app.py`: add public trust/freshness labels and richer metadata payloads for Explore, Today, Field, Guide, and location pages.
- Modify `templates/index.html`: add calm public-readiness trust copy on the first screen and archive/freshness support text.
- Modify `templates/forecast.html`: make stale forecast guidance visibly advisory and keep live weather/tide useful without overselling rankings.
- Modify `templates/about.html`: strengthen the unofficial planning-companion explanation and data-source limitations.
- Modify `templates/field.html`: sharpen first-screen responsible-use language and official-rule handoff.
- Modify `templates/location_detail.html`: improve share-ready trust copy and mobile chronology rendering.
- Modify `static/site.css`: add reusable trust-note and mobile chronology styles.
- Modify `static/field-mode.css`: polish field first-screen layout if copy changes need spacing.
- Modify `static/manifest.json`: update app description/categories/shortcuts for public install surfaces.
- Modify `tests/test_api.py`: cover public trust copy, stale forecast messaging, metadata, and share payloads.
- Modify `tests/test_regressions.py`: cover mobile chronology class/structure and legacy schema safety if needed.

## Task 1: Public Trust Copy And Metadata

**Files:**
- Modify: `app.py`
- Modify: `templates/index.html`
- Modify: `templates/about.html`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing tests for launch trust copy**

Add assertions to `test_index_route_renders_dashboard_controls`:

```python
assert "Unofficial planning companion" in text
assert "Built from public finder reports" in text
assert "Use official links for rules and registration" in text
```

Add assertions to `test_about_route_renders_project_copy`:

```python
assert "This is not an official hiding map" in text
assert "Public reports can be incomplete" in text
assert "The official project site remains the source of truth" in text
```

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/pytest tests/test_api.py::test_index_route_renders_dashboard_controls tests/test_api.py::test_about_route_renders_project_copy -q`

Expected: fails because the new trust copy is absent.

- [ ] **Step 3: Implement minimal trust copy**

In `app.py`, update the Explore page meta subtitle/description to explicitly describe public reports and unofficial planning. In `templates/index.html`, add a compact trust rail near the first screen with:

```html
<div class="launch-trust-rail" aria-label="Public launch trust notes">
    <span class="pill pill--accent">Unofficial planning companion</span>
    <span>Built from public finder reports</span>
    <span>Use official links for rules and registration</span>
</div>
```

In `templates/about.html`, update the trust panel copy to include:

```html
<p>This is not an official hiding map. It is a planning companion built from public reports, so it can show patterns but not guarantee where a float is hidden.</p>
<p>Public reports can be incomplete: some posts do not include dates, images, or precise place text. The official project site remains the source of truth for rules, registration, and original finder stories.</p>
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/pytest tests/test_api.py::test_index_route_renders_dashboard_controls tests/test_api.py::test_about_route_renders_project_copy -q`

Expected: pass.

## Task 2: Forecast Freshness And Advisory Language

**Files:**
- Modify: `app.py`
- Modify: `templates/forecast.html`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing stale-state assertions**

Extend `test_forecast_route_downgrades_headline_when_artifact_is_stale` with:

```python
assert "Advisory, not a live guarantee" in text
assert "Live weather and tide are current context; the ranked area comes from the latest saved model." in text
assert "Refresh the model before treating this as a same-day call." in text
```

Extend `test_forecast_route_renders_predictions_and_location_detail` with:

```python
assert "Planning suggestion, not a guarantee" in text
```

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/pytest tests/test_api.py::test_forecast_route_downgrades_headline_when_artifact_is_stale tests/test_api.py::test_forecast_route_renders_predictions_and_location_detail -q`

Expected: fails because the new advisory copy is absent.

- [ ] **Step 3: Implement freshness copy**

In `build_forecast_freshness()` stale return object, add fields:

```python
'trust_badge': 'Advisory, not a live guarantee',
'trust_summary': 'Live weather and tide are current context; the ranked area comes from the latest saved model.',
'trust_action': 'Refresh the model before treating this as a same-day call.',
```

In the fresh return object, add:

```python
'trust_badge': 'Planning suggestion, not a guarantee',
'trust_summary': 'Use this as a starting order, then confirm access, rules, weather, and what you see on the ground.',
'trust_action': '',
```

In `templates/forecast.html`, render those values inside `.forecast-priority` after the summary:

```html
<div class="forecast-trust-note">
    <strong>{{ freshness.trust_badge }}</strong>
    <p>{{ freshness.trust_summary }}</p>
    {% if freshness.trust_action %}
    <p>{{ freshness.trust_action }}</p>
    {% endif %}
</div>
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/pytest tests/test_api.py::test_forecast_route_downgrades_headline_when_artifact_is_stale tests/test_api.py::test_forecast_route_renders_predictions_and_location_detail -q`

Expected: pass.

## Task 3: Location Share And Mobile Chronology Polish

**Files:**
- Modify: `app.py`
- Modify: `templates/location_detail.html`
- Modify: `static/site.css`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing tests for share copy and chronology structure**

Extend `test_location_detail_builds_share_payload_and_meta`:

```python
assert "Unofficial archive read" in text
assert "Public reports can be incomplete" in text
assert "Use this as a planning card, not a guarantee." in context["share_payload"]["share_text"]
assert context["page_meta"]["description"].endswith("Use this as a planning card, not a guarantee.")
```

Extend `test_location_detail_renders_recent_find_official_report_links`:

```python
assert 'class="mobile-chronology-list"' in text
assert 'class="chronology-card"' in text
assert 'class="table-shell table-shell--desktop"' in text
```

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/pytest tests/test_api.py::test_location_detail_builds_share_payload_and_meta tests/test_api.py::test_location_detail_renders_recent_find_official_report_links -q`

Expected: fails because the public trust note and mobile chronology cards are absent.

- [ ] **Step 3: Implement share trust copy**

In `location_detail()`, append this sentence to `share_parts`:

```python
share_parts.append('Use this as a planning card, not a guarantee.')
```

In `templates/location_detail.html`, add a small trust note below the hero lead:

```html
<div class="launch-trust-rail launch-trust-rail--compact">
    <span class="pill pill--accent">Unofficial archive read</span>
    <span>Public reports can be incomplete</span>
    <span>Confirm rules and registration on the official site</span>
</div>
```

- [ ] **Step 4: Implement mobile chronology cards**

Inside the full chronology details body, keep the existing table but add `table-shell--desktop`:

```html
<div class="table-shell table-shell--desktop">
```

After the table, add:

```html
<div class="mobile-chronology-list" aria-label="Full chronology">
    {% for find in finds %}
    <article class="chronology-card">
        <div class="find-card__meta">
            <span class="pill pill--accent">{{ find.year }}</span>
            <span class="pill">{{ find.date_found|format_public_date('Undated') if find.date_found else 'Undated' }}</span>
        </div>
        <strong>Float #{{ find.float_number if find.float_number else 'Unknown' }}</strong>
        <span>{{ find.finder if find.finder else 'Unknown finder' }}</span>
        <span>Reported place: {{ find.location_raw if find.location_raw else location_name }}</span>
    </article>
    {% endfor %}
</div>
```

In `static/site.css`, add:

```css
.mobile-chronology-list {
    display: none;
}

.chronology-card {
    display: grid;
    gap: 0.65rem;
    padding: 0.95rem;
    border-radius: 16px;
    border: 1px solid rgba(193, 214, 203, 0.08);
    background: rgba(255, 255, 255, 0.03);
}

.chronology-card strong {
    font-size: 1rem;
}

.chronology-card span {
    color: var(--text-2);
    line-height: 1.5;
}

@media (max-width: 720px) {
    .table-shell--desktop {
        display: none;
    }

    .mobile-chronology-list {
        display: grid;
        gap: 0.85rem;
    }
}
```

- [ ] **Step 5: Run tests to verify pass**

Run: `.venv/bin/pytest tests/test_api.py::test_location_detail_builds_share_payload_and_meta tests/test_api.py::test_location_detail_renders_recent_find_official_report_links -q`

Expected: pass.

## Task 4: Field And PWA Public Install Polish

**Files:**
- Modify: `templates/field.html`
- Modify: `static/manifest.json`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing tests for field trust and manifest**

Extend `test_field_route_renders_json_backed_official_guidance`:

```python
assert "Stay on official routes and respect sensitive areas." in text
assert "Use the official rules before you head out." in text
```

Add a new test:

```python
def test_manifest_presents_public_install_surface():
    with app_module.app.test_client() as client:
        response = client.get("/static/manifest.json")

    assert response.status_code == 200
    manifest = response.get_json()
    assert manifest["name"] == "Block Island Glass Float Planner"
    assert manifest["short_name"] == "BI Floats"
    assert "public reports" in manifest["description"]
    assert "shortcuts" in manifest
    assert manifest["shortcuts"][0]["url"] == "/field"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/pytest tests/test_api.py::test_field_route_renders_json_backed_official_guidance tests/test_api.py::test_manifest_presents_public_install_surface -q`

Expected: fails because the copy and manifest values are not yet updated.

- [ ] **Step 3: Implement field and manifest polish**

In `templates/field.html`, add a compact note in `.field-command__copy` after the lead:

```html
<p class="field-safety-note">Stay on official routes and respect sensitive areas. Use the official rules before you head out.</p>
```

In `static/manifest.json`, update:

```json
{
    "name": "Block Island Glass Float Planner",
    "short_name": "BI Floats",
    "description": "Plan a Block Island glass float hunt with public reports, field tools, official links, and archive context.",
    "categories": ["travel", "navigation", "lifestyle"],
    "shortcuts": [
        {
            "name": "Field view",
            "short_name": "Field",
            "description": "Sort mapped float locations and open directions.",
            "url": "/field",
            "icons": [{ "src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png" }]
        },
        {
            "name": "Today",
            "short_name": "Today",
            "description": "Open the latest planning guidance.",
            "url": "/forecast",
            "icons": [{ "src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png" }]
        }
    ]
}
```

Keep existing icon, theme, background, display, and start URL fields.

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/pytest tests/test_api.py::test_field_route_renders_json_backed_official_guidance tests/test_api.py::test_manifest_presents_public_install_surface -q`

Expected: pass.

## Task 5: Final Verification And Rendered QA

**Files:**
- No planned code changes unless verification reveals a defect.

- [ ] **Step 1: Run focused tests**

Run: `.venv/bin/pytest tests/test_api.py tests/test_regressions.py -q`

Expected: pass.

- [ ] **Step 2: Run full deterministic tests**

Run: `.venv/bin/pytest -q`

Expected: pass, with UI smoke tests skipped unless `RUN_UI_SMOKE=1`.

- [ ] **Step 3: Run data validation**

Run:

```bash
.venv/bin/python scripts/refresh_data.py validate
.venv/bin/python scripts/refresh_data.py validate-records
```

Expected: both pass with 4358 rows and 0 invalid or suspicious rows.

- [ ] **Step 4: Rendered browser QA**

Start the app on an unused port:

```bash
PORT=5001 .venv/bin/python app.py
```

Check these URLs at desktop and mobile widths:

- `/`
- `/field`
- `/search`
- `/forecast`
- `/about`
- `/location/Rodman%27s%20Hollow`

Expected:

- no console errors,
- no page-wide horizontal overflow,
- mobile first screens show the trust/safety/advisory copy,
- stale forecast state reads as advisory,
- location chronology uses mobile cards below 720px,
- manifest JSON includes public install description and shortcuts.

- [ ] **Step 5: Commit implementation**

Stage only intended files. Do not stage incidental `floats.db` churn unless the implementation intentionally refreshes/compacts data.

Run:

```bash
git add app.py templates/index.html templates/about.html templates/forecast.html templates/field.html templates/location_detail.html static/site.css static/manifest.json tests/test_api.py docs/superpowers/plans/2026-05-15-public-launch-readiness.md
git commit -m "Polish public launch readiness"
```
