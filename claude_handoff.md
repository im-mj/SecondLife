# Claude Handoff

## Current State

This project is a Flask app for matching patients to clinical trials using Synthea patient data, ClinicalTrials.gov / AACT trial data, and MIMIC-IV demo data for validation.

The current main entry points are:

- `app.py`: Flask server and API routes
- `pipeline.py`: data loading, feature engineering, model training, and matching
- `templates/index.html`: frontend UI
- `llm.md`: project reference / architecture notes

## What Was Added / Improved

The current `pipeline.py` is beyond the earlier basic condition-age-gender version. It now loads and uses:

- patient conditions
- patient demographics
- patient medications
- patient observations / labs
- trial conditions
- trial eligibilities
- trial studies
- trial facilities
- trial summaries
- trial interventions
- trial countries
- trial keywords

The feature set is currently 17 features, including:

- condition overlap and similarity
- age compatibility
- gender compatibility
- condition rarity
- trial specificity
- medication compatibility
- lab availability
- geo feasibility

The model cache on disk matches the current 17-feature schema.

## Current Review Findings

These are the main issues identified in the current codebase:

1. `patient_id` is not passed from `app.py` into `pipeline.match_patient()` for patient-mode searches.
   - This means the new patient-specific medication and lab features do not activate in the main UI flow.

2. The new real-data features are not reflected in the pseudo-label generation.
   - Training labels still only depend on age, gender, and condition overlap.
   - As a result, features like medication compatibility, lab availability, and geo feasibility have very low practical influence.

3. Hospital-aware matching is still not truly implemented.
   - Trial facility data is displayed, but ranking is not based on patient-to-hospital distance, preferred hospital, or same-hospital filtering.
   - `geo_feasibility` is currently a trial-country heuristic, not a patient-to-site match.

4. The frontend manual condition input is fragile.
   - It uses inline `onclick` interpolation for condition strings.
   - Real condition names containing apostrophes such as `alzheimer's disease` can break this flow.

5. The frontend does not expose the new backend signals clearly.
   - The UI still emphasizes only the old score breakdown and does not show enough of the new medication / geography reasoning.

## Recommended Next Changes

Priority order:

1. Fix `app.py` to pass `patient_id` into `pipeline.match_patient()` when mode is `patient`.
2. Replace inline JS string interpolation in `templates/index.html` with safe event binding / `data-*` attributes.
3. Rework pseudo-label logic so the training target explicitly uses the new real-data features or replace pseudo-labels with reviewed labels.
4. Add actual hospital-aware ranking:
   - facility name filtering
   - patient address / ZIP normalization
   - distance-to-site feature using facility latitude / longitude
5. Surface the new reasoning fields in the UI.

## Known Operational Notes

- The workspace is large: about 4.34 GB.
- Several files are over GitHub's normal 100 MB limit.
- Git LFS is required if the intent is to push the datasets and artifacts as-is.

Large files include:

- `Final Clinical Trails Data/trail_eligibilities.csv`
- `Final Clinical Trails Data/trail_detailed_descriptions.csv`
- `Final Clinical Trails Data/trail_brief_summaries.csv`
- `Final Clinical Trails Data/trail_facilities.csv`
- `Final Patients Synthea Data/patients_medications.csv`
- `Final Patients Synthea Data/patients_observations.csv`
- `model_cache.pkl`

## How To Resume

1. Ensure Python dependencies are available.
2. Start the app with:

```powershell
python app.py
```

3. Open `http://localhost:5000`
4. First fix to make:
   - wire `patient_id` through `/api/match`
5. Then continue with frontend hardening and hospital-aware ranking.

## Git Note

This handoff file was created because the original Claude session stopped mid-work due to rate limits. It is intended to give the next person enough context to continue without re-discovering the current architecture and known issues from scratch.
