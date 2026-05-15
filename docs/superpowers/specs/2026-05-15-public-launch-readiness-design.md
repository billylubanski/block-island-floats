# Public Launch Readiness Design

Date: 2026-05-15

## Goal

Prepare the Block Island Glass Float Tracker for public sharing after a small friend-testing round. The app already has the core surfaces in place: Explore, Field, Search, Today, Guide, location pages, PWA assets, and a validated archive. This pass should make those surfaces feel clear, trustworthy, and polished to a first-time visitor.

The launch promise is: this is an unofficial planning companion built from public reports. It helps people choose a stronger starting point, understand the archive, and move responsibly on-island. It does not replace the official Block Island Glass Float Project site for rules, registration, or original finder stories.

## Scope

This pass covers public-facing polish, not major product expansion.

In scope:

- Tighten content that explains what the app is, what it knows, and where official guidance still belongs.
- Make data and forecast freshness clearer, especially when the forecast model artifact is stale but live weather or tide still exist.
- Polish mobile readability and layout on the highest-traffic public screens.
- Improve share and PWA metadata so links and installed app surfaces read cleanly.
- Keep verification evidence simple and repeatable with existing tests, validation commands, and rendered browser checks.

Out of scope:

- New account systems, community submissions, moderation workflows, push notifications, or paid hosting changes.
- A full redesign of the visual system.
- A new live scan unless implementation discovers stale data that cannot be handled honestly with copy and freshness indicators.
- Reworking the core forecasting model.

## Current Baseline

The current repo is clean aside from a local `floats.db` modification after validation. Automated tests pass with `.venv/bin/pytest -q`: 99 passed, 12 skipped. The archive validates with `scripts/refresh_data.py validate` and `scripts/refresh_data.py validate-records`: 4358 canonical and DB rows, 0 invalid, 0 suspicious.

Rendered QA on Explore, Field, Search, Today, Guide, and a Rodman's Hollow location page showed no console errors at desktop or mobile widths. The mobile first screens are coherent and shareable. The main launch-readiness concerns are that the Today page can present stale model guidance, the public trust story can be more explicit, and the full location chronology table is wider than a phone viewport even though the page itself remains contained.

## Approach

Use a trust-first launch pass. The app works, so the priority is not adding more features. It is making first-time public visitors understand the product quickly and trust the boundaries.

Alternative approaches considered:

- Feature-first launch pass: add feedback prompts, beta onboarding, or richer sharing loops. This is useful later, but it expands scope before the public story is crisp.
- Field-first launch pass: deepen low-signal behavior and route planning. This matters for in-season use, but trust and freshness should come first before sharing a public URL.

## Public Surfaces

Explore should remain the primary entry point. It needs to quickly answer: what is this, where should I start, and why should I trust the recommendation. The page should make clear that recommendations are based on public find history plus current context, not secret hide locations.

Today should become more careful about confidence and freshness. If model guidance is stale, the language should avoid sounding same-day authoritative. Live weather and tide can remain useful, but the ranking should be framed as the latest model artifact until a fresh forecast is generated.

Field should stay focused on responsible action: shortlist, distance sorting, directions, weather, and hunt rules. The copy should prioritize safe, official-compliant behavior on the first screen.

Guide should be the trust anchor. It should explain the unofficial role, the data source, the limitations of public reports, and the official links. It should help a stranger decide whether the app is worth using without needing repo context.

Location pages should be share-ready. A shared location should explain archive strength, latest dated report, backup stops, and official report links without implying a guarantee. The full chronology should be readable or intentionally scrollable on mobile.

Search should stay utilitarian. It should help users find a place, finder, or float number and then route them to a fuller location guide.

## Components And Data Flow

The implementation should stay within the existing Flask/Jinja/CSS structure:

- `app.py` continues to build page metadata, forecast freshness, location share payloads, and official-link context.
- Templates own public copy and page-specific structure.
- `static/site.css` and `static/field-mode.css` own responsive layout polish.
- `static/manifest.json` and metadata in `templates/base.html` own install/share presentation.
- Existing generated artifacts and SQLite data remain the data source for this pass.

No new backend persistence is needed. If implementation adds small helper functions, they should support freshness, metadata, or copy clarity rather than creating a new feature layer.

## Error And Edge States

The app should be honest and calm when data is partial:

- Missing dates should read as archive limitations, not failures.
- Missing images should explain that the chronology is still useful.
- Stale forecast artifacts should visibly downgrade claims from "today's recommendation" to "latest model guidance" or similar.
- Weather or tide outages should leave the rest of the planning flow usable.
- Unknown or unmapped locations should avoid pretending to be precise.

## Testing And Verification

Verification should use existing commands first:

- `.venv/bin/pytest -q`
- `.venv/bin/python scripts/refresh_data.py validate`
- `.venv/bin/python scripts/refresh_data.py validate-records`

Rendered QA should cover:

- Explore, Field, Search, Today, Guide, and a representative location page.
- Desktop and mobile widths.
- Console errors.
- Horizontal overflow and mobile text fit.
- Key CTA visibility.
- Stale forecast messaging when the artifact is old.
- Location sharing and PWA metadata where practical.

## Acceptance Criteria

- A first-time visitor can tell within the first two screens that the app is an unofficial planning companion based on public reports.
- Forecast freshness is clear enough that stale model guidance does not read like a live guarantee.
- Mobile pages have no incoherent overflow, overlapping controls, or hidden critical CTAs.
- Shared location pages and metadata read naturally outside the app.
- Official links are present where users need rules, registration, and original report context.
- Existing automated tests and validation commands pass after changes.

## Implementation Notes

Keep edits scoped. Prefer copy, template, metadata, and CSS polish before adding new logic. If a data refresh becomes necessary, run it as a separate operational step and keep progress visible through the existing refresh status tooling.
