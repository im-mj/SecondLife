# Claude Handoff

## Current App Shape

Multi-page Flask app. All files committed + local session changes applied.

Active runtime files:

- `app.py`: Flask routes and portal/API logic
- `pipeline.py`: data loading, feature engineering, model training, trial matching
- `database.py`: SQLite accounts, interests, connections
- `templates/landing.html`: login / registration
- `templates/patient.html`: patient portal
- `templates/hospital.html`: hospital portal

`templates/index.html` deleted.

## Status: All Fixes Complete

The following work is done and local (not yet committed to Git):

### From Previous Session (before rate limit)

1. Hospital suggestion tiered logic (Tier 1 facility-name Jaccard, Tier 2 same-state, Tier 3 condition overlap, Tier 4 fallback)
2. Duplicate connection prevention (schema UNIQUE + COALESCE index)
3. Hospital patient feed excludes already-connected patients
4. Demo patient seeded with `open_to_trials = 1`
5. Hospital profile editing tab (name, location, research conditions)
6. Patient-facing model disclaimer on trial results
7. Trial site info (lead site + location) surfaced in patient UI
8. Hospital registration collects `research_conditions`

### From Current Session

9. **Patient connect modal**: Tier 1 hospitals shown under "Verified Trial Sites" (green header); Tiers 2/3/4 shown under "Related Hospitals — not confirmed trial sites" (grey header). Two visually separated sections.
10. **hospital.html bug fix**: `btn-close-white` → `btn-close` on `bg-info` profile condition tags (white X was invisible on light-blue background).
11. **landing.html**: Enter key now submits login/register forms (all username + password inputs).
12. **patient.html**: System status banner auto-clears — polls `/api/status` every 5s until pipeline is ready, then stops.

## Decision Log

**Hospital matching mode: BROAD**
- Tier 1 = verified site (Jaccard name match ≥ 0.25)
- Tiers 2+3 = related hospitals (same state / condition overlap)
- Visual separation in modal so user sees which is which
- Reason: safer for demo — modal won't be empty; stronger matches still shown first

## Known Limitation (not a bug, by design)

Model trains on synthetic/rule-based labels. Disclaimer shown in UI. Real fix requires clinician-reviewed labels or historical screening decisions — out of scope for DSCI 5260.

## Demo Credentials

| Role | Username | Password |
|------|----------|----------|
| Patient | john_doe | pass123 |
| Hospital | mgh | mgh123 |

## Recommended Test Flow

See "What to Test" section returned at end of last Claude session.

## Git Note

Last GitHub push: `ff67a12` — all local work above is uncommitted.
