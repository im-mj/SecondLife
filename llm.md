# Second Life — Project Reference (LLM Context Document)
DSCI 5260 | Group 7 | Last updated: 2026-04-25 (post two-portal redesign + 5 bug fixes + verified live run)

## Architecture Overview

Flask web app (port 5000) with two authenticated portals:
- **Patient Portal** (/patient): Register/login, update medical profile, get AI trial matches, connect with hospitals
- **Hospital Portal** (/hospital): Login, browse opt-in patients, search by condition, manage connections

### Key Files
- `pipeline.py` — Core ML pipeline (data loading, feature engineering, model training, matching)
- `app.py` — Flask server: session auth, patient API, hospital API, pipeline API
- `database.py` — SQLite layer: 4 tables, auth, connections, trial interests
- `templates/landing.html` — Login/register landing page
- `templates/patient.html` — Patient SPA (profile, trials, connections)
- `templates/hospital.html` — Hospital SPA (patients, search, connections)
- `llm.md` — This file

## Running the System

```powershell
cd "E:\DSCI 5260\Project\PT"
python app.py
# open http://localhost:5000
```

On first run (no model_cache.pkl): loads all data files (~2-3 min), trains RF model, saves cache.
On subsequent runs: loads cached model immediately.

Delete `model_cache.pkl` to force retrain (required after pipeline feature changes).

## Demo Credentials

- **Patient:** john_doe / pass123 (hypertension + diabetes + MI, Boston MA)
- **Patient:** jane_smith / pass123 (asthma + eczema + allergic rhinitis, Cambridge MA)
- **Patient:** bob_jones / pass123 (CAD + hypertension + chronic pain, Cleveland OH)
- **Hospital:** mgh / mgh123 (Massachusetts General Hospital, Boston MA)
- **Hospital:** cleveland / clinic123 (Cleveland Clinic, Cleveland OH)
- **Hospital:** jhopkins / johns123 (Johns Hopkins Hospital, Baltimore MD)

---

## Data Sources

### Patient Side (Synthea synthetic data)
- `Final Patients Synthea Data/final_patients_conditions.csv` — ~967K rows, **265,893 patients**, 106 conditions overlapping with trials. Columns: Patient_ID, Condition_Name, Condition_End_Date
- `Final Patients Synthea Data/patients_details.csv` — Demographics. Columns: Patient_ID, First_Name, Last_Name, Birth_Date (DD-MM-YYYY), Gender, Race, Ethnicity, Address
- `Final Patients Synthea Data/patients_medications.csv` — **213,182 patients with med data**. Columns: Patient_ID, Medication_Name, Medication_End_Date
- `Final Patients Synthea Data/patients_observations.csv` — **23,231 patients with lab data**. Columns: Patient_ID, Observation_Name

### Trial Side (ClinicalTrials.gov / AACT)
- `Final Clinical Trails Data/trail_conditions.csv` — ~1M rows, **571,379 total trials**, **34,074 with matched condition profiles**. Columns: Trial_ID, Condition_Name_Lower
- `Final Clinical Trails Data/trail_eligibilities.csv` — Columns: Trial_ID, Gender (leading space — stripped), Minimum_Age, Maximum_Age, Eligibility_Criteria
- `Final Clinical Trails Data/trail_studies.csv` — **65,292 recruiting trials**. Columns: Trial_ID, Brief_Title, Overall_Status, Phase, Start_Date, Enrollment
- `Final Clinical Trails Data/trail_facilities.csv` — **189,274 trials with US state geo data**. Columns: Trial_ID, Facility_City, Facility_State (full names), Facility_Country
- `Final Clinical Trails Data/trail_brief_summaries.csv` — Columns: Trial_ID, Brief_Summary
- `Final Clinical Trails Data/trail_interventions.csv` — **196,865 trials with drug intervention data**. Columns: Trial_ID, Intervention_Type, Intervention_Name
- `Final Clinical Trails Data/trail_countries.csv` — Not used for geo scoring (superseded by facility-level state data)
- `Final Clinical Trails Data/trail_keywords.csv` — Columns: Trial_ID, Keyword_Name_Lower

### MIMIC-IV Demo (code-level validation only, not in UI)
- `mimic-iv-clinical-database-demo-2.2/hosp/patients.csv.gz`
- `mimic-iv-clinical-database-demo-2.2/hosp/diagnoses_icd.csv.gz`
- `mimic-iv-clinical-database-demo-2.2/hosp/d_icd_diagnoses.csv.gz`

---

## SQLite Database (secondlife.db)

### Tables
```sql
patient_accounts(id, username, password_hash, synthea_id, first_name, last_name,
                 dob, gender, address, conditions TEXT DEFAULT '[]',
                 medications TEXT DEFAULT '[]', documents TEXT DEFAULT '[]',
                 open_to_trials INTEGER DEFAULT 0, created_at)

hospital_accounts(id, username, password_hash, hospital_name, location,
                  research_conditions TEXT DEFAULT '[]', created_at)

patient_trial_interests(id, patient_id, trial_id, trial_title, match_score,
                        status DEFAULT 'interested', created_at,
                        UNIQUE(patient_id, trial_id))

connections(id, patient_id, hospital_id, trial_id, trial_title,
            initiated_by DEFAULT 'patient', status DEFAULT 'pending',
            message, created_at)
```

---

## Feature Engineering (17 features in FEATURE_COLS)

| Feature | Description |
|---------|-------------|
| condition_overlap | Raw count of shared conditions |
| jaccard_similarity | overlap / union |
| overlap_ratio_trial | overlap / len(trial_conditions) |
| overlap_ratio_patient | overlap / len(patient_conditions) |
| condition_rarity_score | mean(1/log2(n_trials_per_cond+2)), normalised 0-1 |
| trial_specificity | 1 / trial_condition_count |
| condition_burden | total_patient_conds / 10 |
| active_ratio | active_conds / total_conds |
| resolved_ratio | resolved_conds / total_conds |
| age_distance | normalised distance outside age range (0 if within) |
| age_centered | position within age range (-1 to +1) |
| age_compatibility | 1.0 in range, decays over 30-year gap |
| gender_compatibility | 1.0 match/all, 0.1 mismatch |
| **geo_feasibility** | **State-level: 1.0 same state, 0.75 other US state, 0.5 no data** |
| **med_compatibility** | **Keyword overlap: patient meds vs trial drug interventions** |
| **lab_availability** | **Patient observation/lab type coverage (0-1, normalised by 20)** |
| data_completeness | fraction of key fields present |

---

## Bug Fixes Applied

### Fix 1 — patient_id not passed to match_patient() (CRITICAL)
**Before:** `pipeline.match_patient(conditions, age, gender, top_k=20)`
**After:** `pipeline.match_patient(conditions, age, gender, top_k=20, patient_id=session["patient_id"], address=address)`

Without this fix, patient-specific medication keywords and lab scores defaulted to empty set / 0.3 for all users — the med_compatibility and lab_availability features were effectively constants.

### Fix 2 — Pseudo-label used only 3 features (HIGH)
**Before:** AND gate on age/gender/condition — geo/med/lab had near-zero training influence.
**After:** 6-feature weighted score:
```python
def _label(row):
    score = (
        0.30 * float(row["age_compatibility"]    > 0.6) +
        0.15 * float(row["gender_compatibility"] > 0.5) +
        0.25 * float(row["jaccard_similarity"]   > 0.05) +
        0.10 * float(row["geo_feasibility"]) +
        0.10 * float(row["med_compatibility"]) +
        0.10 * float(row["lab_availability"])
    )
    base = int(score >= 0.5)
    h = int(hashlib.md5(f"{row['Patient_ID']}_{row['Trial_ID']}".encode()).hexdigest()[:8], 16)
    if (h % 1000) / 1000 < 0.15:
        base = 1 - base   # 15% random noise for realism
    return base
```

### Fix 3 — geo_feasibility was country-level heuristic (MEDIUM)
**Before:** Float from `trail_countries.csv` (1.0 US, 0.7 multi-national, 0.35 non-US). No patient location concept.
**After:** State-level matching using `trail_facilities.csv` + patient address regex extraction:
```python
STATE_ABBREV = {"MA": "Massachusetts", "TX": "Texas", ...}  # 51 entries

def _geo_score(patient_state_full: str, trial_states: set) -> float:
    if not trial_states: return 0.5        # no US facility data — neutral
    if patient_state_full and patient_state_full in trial_states: return 1.0
    if trial_states: return 0.75           # other US state
    return 0.35

def _extract_state(address: str) -> str:
    m = re.search(r"\b([A-Z]{2})\s+\d{5}\b", str(address))
    if m: return STATE_ABBREV.get(m.group(1), "")
    return ""
```

### Fix 4 — NameError `trial_geo` in _compute_features return dict (BUG)
`"geo_feasibility": float(trial_geo)` → `"geo_feasibility": geo_feasibility`

### Fix 5 — XSS in condition tag onclick handlers (MEDIUM)
`addConditionTag('${c}')` broke for conditions containing apostrophes like "alzheimer's disease".
Fixed with DOM-based makeTag() using textContent + addEventListener. No inline onclick anywhere.

---

## Geo Feasibility Architecture

```
Patient address:  "123 Main St Boston MA 02101 US"
                           |  regex: \b([A-Z]{2})\s+\d{5}\b
                    "MA"  -->  STATE_ABBREV  -->  "Massachusetts"

Trial facilities: trail_facilities.csv  -->  filter Facility_Country="United States"
                  -->  group by Trial_ID  -->  set of Facility_State values
                  e.g. {"Massachusetts", "New York", "California"}

Score: patient_state in trial_states   -->  1.0 (same state)
       trial_states non-empty          -->  0.75 (other US state)
       trial_states empty              -->  0.5  (no facility data)
```

---

## Flask API Routes

### Auth (no login required)
- `POST /auth/patient/register` -> {success, patient} or {error}
- `POST /auth/patient/login` -> {success, patient} or {error}
- `POST /auth/hospital/register` -> {success, hospital} or {error}
- `POST /auth/hospital/login` -> {success, hospital} or {error}
- `POST /auth/logout` -> {success}

### Patient API (requires patient session)
- `GET  /api/patient/profile` -> patient dict (no password_hash)
- `POST /api/patient/profile` -> updated patient dict
- `GET  /api/patient/matches` -> {results: [...trials], total}
- `GET  /api/patient/interests` -> {interests: [...]}
- `POST /api/patient/interest` -> {success}
- `DELETE /api/patient/interest/<trial_id>` -> {success}
- `GET  /api/patient/connections` -> {connections: [...]}
- `POST /api/patient/connect` -> {success, connection}
- `GET  /api/patient/hospitals-for-trial?trial_id=NCT...` -> {hospitals: [...]}

### Hospital API (requires hospital session)
- `GET  /api/hospital/profile` -> hospital dict
- `GET  /api/hospital/patients?condition=...` -> {patients: [...]} (open_to_trials=1 only)
- `POST /api/hospital/connect` -> {success, connection}
- `GET  /api/hospital/connections` -> {connections: [...]}
- `PUT  /api/hospital/connections/<cid>/status` -> {success}

### Shared
- `GET /api/status` -> {ready, stats} or {ready: false, message}
- `GET /api/conditions/autocomplete?q=...` -> {results: [...]}

---

## Trial Match Result Fields

Each item in /api/patient/matches results:
- trial_id, title, phase, status, min_age, max_age, sex, enrollment, start_date
- eligibility_probability (0-100, calibrated RF probability x 100)
- match_score (0-100, rule-based: overlap_ratio weighted)
- combined_score (0-100, 0.6 x eligibility + 0.4 x match_score)
- age_compatibility, gender_compatibility, geo_feasibility, med_compatibility (all 0-100)
- condition_rarity_score (0-1)
- overlap_conditions (list of conditions shared with patient)
- trial_conditions (all trial conditions)
- criteria (eligibility criteria text, truncated to 500 chars)
- summary (brief summary, truncated to 400 chars)
- location, n_sites
- interest_status (null | 'interested' | 'withdrawn', from patient_trial_interests)

---

## Data Privacy Model

1. Hospitals see only patients with open_to_trials=1 (name, age, gender, conditions)
2. Full details accessible only after patient-initiated connection
3. Hospital cannot contact a patient unless patient is open to trials
4. Connection record: patient_id, hospital_id, trial_id, initiated_by, status, message
5. Hospital can also initiate connections with opt-in patients from the hospital portal

---

## XSS Prevention

All user-controlled strings use DOM API (never innerHTML):
```javascript
function escH(s) {       // text content in innerHTML contexts
  const d = document.createElement('div');
  d.appendChild(document.createTextNode(String(s||'')));
  return d.innerHTML;
}
function escA(s) {       // HTML attribute values
  return String(s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;')
                      .replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
```
Event listeners use addEventListener only. Tags and cards built via createElement + textContent.

---

## ML Model

- Random Forest (n_estimators=200, max_depth=12, class_weight="balanced")
- CalibratedClassifierCV (isotonic, cv=3) for probability calibration
- GroupShuffleSplit (patient-level, 80/20, no leakage) for train/test split
- GroupKFold (5-fold, patient-level) for cross-validation
- Training sample: 3000 patients x 30 trials each + random negatives
- Cache: `model_cache.pkl` (delete to force retrain)

### Actual Metrics (from verified live run, 2026-04-25)

| Metric | Value |
|--------|-------|
| Accuracy | 85.15% |
| AUC-ROC | 0.5976 |
| CV AUC (5-fold) | 0.5992 ± 0.0052 |
| F1 | 0.9168 |
| Precision | 0.8518 |
| Recall | 0.9925 |
| Brier score | 0.1263 |
| Avg precision | 0.8540 |
| Train size | 90,994 pairs |
| Test size | 22,681 pairs |
| Positive label rate | 82.1% |

> **Note on AUC:** The 82.1% positive rate in pseudo-labels (weighted 6-feature labelling threshold at 0.5) makes the classification task easy to solve trivially — high accuracy/recall but lower AUC. To improve AUC, the pseudo-label threshold should be raised (e.g. 0.6) or positive/negative sampling balanced more aggressively.

### Feature Importance (Random Forest, ranked)

| Rank | Feature | Importance |
|------|---------|-----------|
| 1 | age_distance | 0.2040 |
| 2 | age_compatibility | 0.1691 |
| 3 | gender_compatibility | 0.1288 |
| 4 | age_centered | 0.0791 |
| 5 | jaccard_similarity | 0.0751 |
| 6 | condition_rarity_score | 0.0621 |
| 7 | overlap_ratio_trial | 0.0519 |
| 8 | overlap_ratio_patient | 0.0512 |
| 9 | condition_overlap | 0.0396 |
| 10 | condition_burden | 0.0274 |
| 11 | resolved_ratio | 0.0263 |
| 12 | active_ratio | 0.0258 |
| 13 | lab_availability | 0.0208 |
| 14 | geo_feasibility | 0.0158 |
| 15 | med_compatibility | 0.0144 |
| 16 | trial_specificity | 0.0087 |
| 17 | data_completeness | 0.0000 |

---

## MIMIC-IV Validation (code-level only, not in UI)

- 100 demo patients, ~90% match rate after 3-tier ICD -> condition mapping
- Call: pipeline.validate_mimic() -> list of {subject_id, mapped_conditions, n_matches, top_match}
- 3-tier mapping: exact -> substring containment -> word-overlap >= 75%
- Not exposed via any Flask route

---

## Live Run Verification (2026-04-25)

End-to-end test results after full retrain with no model_cache.pkl:

| Test | Result |
|------|--------|
| Landing page GET / | 200 OK |
| Patient login john_doe/pass123 | OK — returns patient JSON |
| Hospital login mgh/mgh123 | OK — returns hospital JSON |
| Pipeline ready (api/status) | ready: true |
| /api/patient/matches for john_doe | 20 results, all score fields populated |
| Top match geo score for Greece trial | 50% (no US facility — correct) |
| Hospital browses open_to_trials patients | 1 patient visible after toggle |
| Hospital condition search ?condition=hypertension | 1 result |
| Hospital -> patient connect (POST) | OK, status=pending |
| Patient sees hospital connection (GET) | 1 connection, hospital_name present |
| /api/conditions/autocomplete?q=hyper | ["hypertension"] |

---

## Known Issues / Future Improvements

1. **High pseudo-label positive rate (82.1%)** — lowers AUC-ROC to ~0.60. Fix: raise label threshold from 0.5 to 0.6, or explicitly sample equal positive/negative pairs.

2. **data_completeness feature importance = 0** — this feature is nearly constant across training pairs (all synthetic patients have complete data). Consider removing it from FEATURE_COLS or enriching with real missing-data cases.

3. **Fuzzy condition matching not yet implemented** — only exact condition name overlaps are used (106 conditions). Substring / semantic fuzzy matching would expand coverage significantly.

4. **lab_availability coverage is low (23,231 / 265,893 patients = 8.7%)** — observations file is sparse for this dataset. Consider normalising the denominator to the subset that has any lab data.

5. **Hospital portal does not rank patients by match quality** — patients are listed in insertion order. Could be ranked by condition overlap with the hospital's research_conditions.

6. **No email/notification system** — connection requests are only visible inside the portal. A real deployment would send email alerts.
