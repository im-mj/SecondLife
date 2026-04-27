# Second Life — Project Reference (LLM Context Document)

## Project Deliverables

All deliverables in `E:\DSCI 5260\Project\PT\`:

| File | Description |
|------|-------------|
| `Second_Life_Presentation_Final.pptx` | Final presentation. 6 slides: Title, Business Understanding & Introduction, Literature Review, Data Understanding, Modeling & Evaluation, Recommendations & Next Steps. |
| `Architecture Diagrams/secondlife workflow architecture diagrams.html` | 7 Mermaid.js diagrams: System Architecture, DB Schema, ML Pipeline, Patient Journey, Hospital Journey, Tiered Matching, Feature Engineering. View in browser. |
| `Architecture Diagrams/secondlife high level architecture.png` | High-level architecture image. |
| `Architecture Diagrams/secondlife high level architecture.drawio` | Editable source for high-level architecture diagram. |
| `Architecture Diagrams/secondlife low level architecture.drawio` | Editable source for low-level architecture diagram. |

---

## Architecture Overview

Flask web app (port 5000) with two authenticated portals:
- **Patient Portal** (/patient): Register/login, update medical profile, get AI trial matches, connect with hospitals
- **Hospital Portal** (/hospital): Login, browse opt-in patients, search by condition, manage connections, edit profile

### Key Files
- `pipeline.py` — Core ML pipeline (data loading, feature engineering, model training, matching)
- `app.py` — Flask server: session auth, patient API, hospital API, pipeline API
- `database.py` — SQLite layer: 5 tables, auth, connections, trial interests, messages
- `templates/landing.html` — Login/register landing page
- `templates/patient.html` — Patient SPA (profile, trials, connections, inbox)
- `templates/hospital.html` — Hospital SPA (patients, search, my trials, inbox, connections, profile)
- `Architecture Diagrams/secondlife workflow architecture diagrams.html` — 7 Mermaid.js architecture diagrams
- `llm.md` — This file

## Running the System

### Local
```powershell
cd "E:\DSCI 5260\Project\PT"
python app.py
# open http://localhost:5000
```

On first run (no model_cache.pkl): loads all data files (~2-3 min), trains RF model, saves cache.
On subsequent runs: loads cached model immediately.

Delete `model_cache.pkl` to force retrain (required after pipeline feature changes).

### Public Deployment — Hugging Face Spaces
- **URL:** https://huggingface.co/spaces/MrNoOne07/second-life
- **Runtime:** Docker container, Flask on port 7860 (mapped to public HTTPS)
- **Stack:** Flask 3.1.3, SQLite, Bootstrap 5.3.2
- Zero installation — accessible from any browser
- Same codebase as local; Docker handles environment setup

## Demo Credentials

All hand-made patients have `open_to_trials=1` and password `pass123`.

| Username | Password | Name | Conditions | Location |
|----------|----------|------|-----------|----------|
| john_doe | pass123 | John Doe | hypertension, diabetes, MI | Boston, MA |
| jane_smith | pass123 | Jane Smith | asthma, atopic dermatitis, allergic rhinitis | Cambridge, MA |
| bob_jones | pass123 | Robert Jones | CAD, hypertension, chronic pain | Cleveland, OH |
| alice_brown | pass123 | Alice Brown | non-small cell lung cancer, stroke | Baltimore, MD |
| david_chen | pass123 | David Chen | diabetes, osteoporosis, CAD | Chicago, IL |

| Username | Password | Hospital | Location |
|----------|----------|---------|----------|
| mgh | mgh123 | Massachusetts General Hospital | Boston, MA |
| cleveland | clinic123 | Cleveland Clinic | Cleveland, OH |
| jhopkins | johns123 | Johns Hopkins Hospital | Baltimore, MD |

### Dataset-Backed Patients (Synthea)
20 real Synthea patients are auto-seeded on first run from `Final Patients Synthea Data/`. Username format: `synthea_<first 8 chars of Patient_ID>`, password `pass123`, all `open_to_trials=1`. Total DB patients: 25 (5 hand-made + 20 Synthea).

List all accounts: `SELECT username, first_name, last_name FROM patient_accounts ORDER BY username;`

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
- `Final Clinical Trails Data/trail_facilities.csv` — **189,274 trials with US state geo data**. Columns: Trial_ID, Facility_Name, Facility_City, Facility_State (full names), Facility_Country
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
            message, created_at,
            UNIQUE(patient_id, hospital_id, trial_id))
-- Post-schema index handles NULL trial_id:
-- CREATE UNIQUE INDEX idx_conn_unique ON connections(patient_id, hospital_id, COALESCE(trial_id, ''))

connection_messages(id, connection_id, sender_role TEXT,  -- 'patient' or 'hospital'
                    sender_id TEXT, body TEXT,
                    created_at, is_read INTEGER DEFAULT 0)
-- Index: idx_msgs_conn ON connection_messages(connection_id, created_at)
```

JSON fields (conditions, medications, documents, research_conditions) are stored as TEXT and parsed via `_row_to_dict()`.

### Key database.py Functions

| Function | Purpose |
|---------|---------|
| `get_open_patients_for_hospital(hid, condition_filter, include_connected)` | Returns open_to_trials=1 patients; when `include_connected=False` excludes already-connected patients |
| `get_connection_messages(connection_id)` | All messages for a connection, ASC order |
| `create_connection_message(connection_id, sender_role, sender_id, body)` | Insert message, returns dict |
| `mark_messages_read(connection_id, reader_role)` | Mark all messages from the other role as read |
| `unread_count(connection_id, reader_role)` | Count of unread messages from the other role |
| `get_hospital_inbox_threads(hospital_id)` | All threads with last_message, last_message_at, unread_count; sorted by activity |
| `get_patient_inbox_threads(patient_id)` | Same for patient side |
| `_seed_dataset_patients(c, max_patients=20)` | Seeds Synthea patients from CSV on first run |

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

## Flask API Routes

### Auth (no login required)
- `POST /auth/patient/register` → {success, patient} or {error}
- `POST /auth/patient/login` → {success, patient} or {error}
- `POST /auth/hospital/register` → {success, hospital} or {error}
- `POST /auth/hospital/login` → {success, hospital} or {error}
- `POST /auth/logout` → {success}

### Patient API (requires patient session)
- `GET  /api/patient/profile` → patient dict (no password_hash)
- `POST /api/patient/profile` → updated patient dict; allowed fields: first_name, last_name, dob, gender, address, conditions, medications, open_to_trials
- `GET  /api/patient/matches` → {results: [...trials], total}
- `GET  /api/patient/interests` → {interests: [...]}
- `POST /api/patient/interest` → {success}; body: {trial_id, trial_title, match_score}
- `DELETE /api/patient/interest/<trial_id>` → {success}
- `GET  /api/patient/connections` → {connections: [...]} joined with hospital_name
- `POST /api/patient/connect` → {success, connection} or 409 if duplicate; body: {hospital_id, trial_id, trial_title, message}
- `GET  /api/patient/hospitals-for-trial?trial_id=NCT...` → {hospitals: [...]} tiered matching (see below)
- `GET  /api/patient/connections/<cid>/messages` → {messages: [...]}; marks hospital messages read
- `POST /api/patient/connections/<cid>/messages` → {success, message}; body: {body}
- `GET  /api/patient/inbox` → {threads: [...]} each with last_message, last_message_at, unread_count, hospital_name
- `GET  /api/patient/documents` → {documents: [...]}
- `POST /api/patient/documents` → {success, document}; multipart/form-data file upload (max 10 MB, .pdf/.docx/.doc/.txt/.png/.jpg/.jpeg)
- `DELETE /api/patient/documents/<doc_id>` → {success}; removes file from disk and DB
- `GET  /api/patient/documents/<doc_id>/download` → file download (as_attachment)

### Hospital API (requires hospital session)
- `GET  /api/hospital/profile` → hospital dict (no password_hash)
- `POST /api/hospital/profile` → updated hospital dict; allowed fields: hospital_name, location, research_conditions
- `GET  /api/hospital/patients?condition=&include_connected=` → {patients: [...]} open_to_trials=1; `include_connected=true` to include already-connected patients (used by Search tab)
- `POST /api/hospital/connect` → {success, connection} or 409 if duplicate; body: {patient_id, trial_id, trial_title, message}
- `GET  /api/hospital/connections` → {connections: [...]} joined with patient fields
- `PUT  /api/hospital/connections/<cid>/status` → {success}; body: {status: pending|accepted|rejected|completed}
- `GET  /api/hospital/connections/<cid>/messages` → {messages: [...]}; marks patient messages read
- `POST /api/hospital/connections/<cid>/messages` → {success, message}; body: {body}
- `GET  /api/hospital/inbox` → {threads: [...]} each with last_message, last_message_at, unread_count, first_name, last_name
- `GET  /api/hospital/trials` → {trials: [...]} active trials matched to hospital profile (see below)

### Shared
- `GET /api/status` → {ready, stats} or {ready: false, message}
- `GET /api/conditions/autocomplete?q=...` → {results: [...]}

---

## Hospital Trial Dashboard (`/api/hospital/trials`)

`pipeline.trials_for_hospital(hospital_name, location, research_conditions, top_k=20)` — reverse of patient matching: given a hospital's profile, find active clinical trials it is most relevant to.

| Tier | Match condition | `match_reason` field |
|------|----------------|----------------------|
| 1 | Jaccard(hospital name tokens, trial facility name tokens) ≥ 0.25 | "name matched to trial site" |
| 2 | Hospital state matches a US trial facility state | "in same state as trial site" |
| 3 | Hospital `research_conditions` overlaps trial conditions | "researches related conditions" |

Active-only filter (`is_active` check) applied at every tier. Returns list of dicts:
`trial_id, title, phase, status, summary, location, facility_name, n_sites, match_tier, match_reason`

---

## Tiered Hospital Matching (`/api/patient/hospitals-for-trial`)

For each trial, hospitals in the DB are scored and returned in tier order (Tier 1 first):

| Tier | Match condition | `match_reason` field | UI label |
|------|----------------|----------------------|----------|
| 1 | Jaccard(hospital name tokens, any trial facility name tokens) ≥ 0.25 | "verified site on this trial" | Green — Verified Trial Sites |
| 2 | Hospital state (from "City, ST" location) matches a trial US facility state | "in same state as a trial site" | Grey — Related Hospitals |
| 3 | Hospital `research_conditions` overlaps trial conditions | "researches related conditions" | Grey — Related Hospitals |
| 4 | Fallback — trial has no facility/state data at all | "" | Grey — Related Hospitals |

The patient connect modal groups Tier 1 hospitals under a green "VERIFIED TRIAL SITES" header and Tiers 2-4 under a grey "RELATED HOSPITALS — not confirmed trial sites" header.

**Pipeline lookups used:**
- `pipeline.trial_facility_tokens[trial_id]` — list of frozensets of significant words from facility names
- `pipeline.trial_us_states[trial_id]` — set of US state full names (e.g. {"Massachusetts"})
- `pipeline.trial_profiles[trial_id]["conditions"]` — set of condition strings

**Stopword set for facility name tokenisation** (same in pipeline.py and app.py):
hospital, medical, center, centre, clinic, university, health, care, healthcare, system, institute, foundation, research, general, regional, national, community, services, department, division, college, school, the, of, and, at, for, in, a, an, is, by

---

## Trial Match Result Fields

Each item in `/api/patient/matches` results:
- trial_id, title, phase, status, min_age, max_age, sex, enrollment, start_date
- eligibility_probability (0-100, calibrated RF probability × 100)
- match_score (0-100, rule-based: overlap_ratio weighted)
- combined_score (0-100, 0.6 × eligibility + 0.4 × match_score)
- age_compatibility, gender_compatibility, geo_feasibility, med_compatibility (all 0-100)
- condition_rarity_score (0-1)
- overlap_conditions (list of conditions shared with patient)
- trial_conditions (all trial conditions)
- criteria (eligibility criteria text, truncated 500 chars)
- summary (brief summary, truncated 400 chars)
- **facility_name** (lead US facility name, or "" if not available)
- location (lead US facility city/state/country string)
- n_sites (total facility count for this trial)
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

All user-controlled strings use DOM API (never innerHTML for user data):
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
- Training sample: 3000 patients × 30 trials each + random negatives
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

- 100 demo patients, ~90% match rate after 3-tier ICD → condition mapping
- Call: `pipeline.validate_mimic()` → list of {subject_id, mapped_conditions, n_matches, top_match}
- 3-tier mapping: exact → substring containment → word-overlap ≥ 75%
- Not exposed via any Flask route

---

## All Bug Fixes by Session

### Session 3 Fixes (2026-04-25) — Two-portal foundation

#### Fix 1 — patient_id not passed to match_patient() (CRITICAL)
**Before:** `pipeline.match_patient(conditions, age, gender, top_k=20)`
**After:** `pipeline.match_patient(conditions, age, gender, top_k=20, patient_id=session["patient_id"], address=address)`

Without this, patient-specific medication keywords and lab scores defaulted to empty / 0.3 for all users — med_compatibility and lab_availability were effectively constants.

#### Fix 2 — Pseudo-label used only 3 features (HIGH)
**Before:** AND gate on age/gender/condition — geo/med/lab had near-zero training influence.
**After:** 6-feature weighted score with 15% random noise:
```python
score = (
    0.30 * float(row["age_compatibility"]    > 0.6) +
    0.15 * float(row["gender_compatibility"] > 0.5) +
    0.25 * float(row["jaccard_similarity"]   > 0.05) +
    0.10 * float(row["geo_feasibility"]) +
    0.10 * float(row["med_compatibility"]) +
    0.10 * float(row["lab_availability"])
)
base = int(score >= 0.5)
# 15% hash-deterministic noise for realism
```

#### Fix 3 — geo_feasibility was country-level heuristic (MEDIUM)
**Before:** Float from `trail_countries.csv` (1.0 US, 0.7 multi-national, 0.35 non-US). No patient location.
**After:** State-level matching using `trail_facilities.csv` + patient address regex:
```python
def _geo_score(patient_state_full, trial_states):
    if not trial_states: return 0.5       # no US facility data — neutral
    if patient_state_full in trial_states: return 1.0
    return 0.75                           # other US state
```

#### Fix 4 — NameError `trial_geo` in _compute_features return dict
`"geo_feasibility": float(trial_geo)` → `"geo_feasibility": geo_feasibility`

#### Fix 5 — XSS in condition tag onclick handlers (MEDIUM)
`addConditionTag('${c}')` broke for conditions with apostrophes (e.g. "alzheimer's disease").
Fixed with DOM-based `makeTag()` using textContent + addEventListener. No inline onclick anywhere.

#### Fix 6 — Duplicate connection prevention (was: no guard)
- `connections` table: added `UNIQUE(patient_id, hospital_id, trial_id)` schema constraint
- `init_db()`: runs `CREATE UNIQUE INDEX IF NOT EXISTS idx_conn_unique ON connections(patient_id, hospital_id, COALESCE(trial_id, ''))` to handle NULL trial_id and backfill existing DBs
- `create_connection()`: pre-checks `connection_exists()` before insert; returns `None` on duplicate
- `/api/patient/connect` and `/api/hospital/connect`: return 409 when `create_connection()` returns None

#### Fix 7 — Hospital patient feed showed already-contacted patients (was: no exclusion)
`get_open_patients_for_hospital()` now uses:
```sql
WHERE open_to_trials=1
  AND id NOT IN (SELECT DISTINCT patient_id FROM connections WHERE hospital_id=?)
```

#### Fix 8 — Demo seed: john_doe starts with open_to_trials=1
Hospital portal was empty on a fresh database. `_seed_demo_data()` now seeds john_doe with `open_to_trials=1`.

#### Fix 9 — Hospital registration silently ignored research_conditions
`templates/landing.html` hospital register form now collects comma-separated research conditions and sends them as a parsed lowercase array to the backend.

#### Fix 10 — Trial cards only showed site count, not facility name or location
`pipeline.py match_patient()` now extracts `facility_name` from `Facility_Name` column; prefers US facilities. Patient portal detail grid shows "Lead Site" and "Location" when available.

---

### Session 4 Fixes (2026-04-25) — Hospital matching overhaul + profile editing

#### Fix 11 — Hospital suggestion logic replaced (was: research_conditions overlap only)
Complete replacement of `/api/patient/hospitals-for-trial`:

**Before:** looped all hospitals, included any whose `research_conditions` overlapped trial conditions. No tier concept, no facility data used.

**After:** 4-tier system using two new pipeline lookups:
- `pipeline.trial_facility_tokens[trial_id]` — built from `Facility_Name` column in trail_facilities.csv, US rows only. Each facility name tokenised by stripping stopwords + words < 3 chars.
- `pipeline.trial_us_states[trial_id]` — set of full US state names for the trial

Helper functions in `app.py`:
```python
def _hospital_name_tokens(name: str) -> frozenset:
    # strips stopwords, keeps words ≥ 3 chars
    ...

def _facility_match_score(h_tokens: frozenset, facility_token_list: list) -> float:
    # best Jaccard score against any facility in the trial
    ...
```

Each hospital gets one tier assigned and a `match_reason` + `match_tier` in the response.
Result list sorted by `match_tier` ascending (best first).

#### Fix 12 — Hospital portal had no profile editing
`POST /api/hospital/profile` added (was GET-only). `database.py update_hospital_profile()` added. `templates/hospital.html` now has a **My Profile** tab with editable hospital name, location, and research condition tags. On save, the navbar hospital name updates live without a page reload.

#### Fix 13 — Model disclaimer missing from patient trial results
`templates/patient.html` trial results section now shows an alert above results:
> "Match percentages are predictions from a model trained on synthetic patient data and rule-based labels — not validated clinical eligibility determinations. Always consult a healthcare provider before enrolling in any trial."

---

### Session 5 Fixes (2026-04-25) — Modal UX + bug fixes

#### Fix 14 — Patient connect modal showed all hospitals in one flat list
**Before:** All hospitals (all tiers) in a single flat list, sorted by tier, with coloured badges as the only visual distinction.

**After:** Modal renders two visually separated sections:
- **"VERIFIED TRIAL SITES"** (green `sec-head`) — Tier 1 hospitals only
- **"RELATED HOSPITALS — not confirmed trial sites"** (grey `sec-head` with inline subtitle) — Tiers 2, 3, 4

Both sections only render if they have entries. Click delegation on the outer `#hospitalList` wrapper still works for both sections.

#### Fix 15 — Close button invisible on hospital profile condition tags
`hospital.html renderProfTags()`: `btn-close-white` (white X) on `bg-info text-dark` badge (light blue background) → `btn-close` (dark X). The X was invisible before.

#### Fix 16 — Login/register forms required mouse click, no Enter key support
`templates/landing.html`: Added `_onEnter(inputId, fn)` helper and wired Enter key on all login and register inputs (both patient and hospital portals). Works on username field too (not just password).

#### Fix 17 — System ready banner never auto-cleared on slow boot
`templates/patient.html`: `checkStatus()` was called once at DOMContentLoaded and never again. If the pipeline was still training when the user opened the page, the yellow banner persisted even after the pipeline finished.

**After:** `startStatusPoll()` starts a `setInterval` (5s) when the initial check finds `ready: false`. The interval clears itself once `ready: true` is received.
```javascript
checkStatus().then(() => { if (!sysReady) startStatusPoll(); });
```

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
| Hospital browses open_to_trials patients | 25 patients visible (5 demo + 20 Synthea) |
| Hospital condition search ?condition=hypertension | results including Synthea patients |
| Hospital → patient connect (POST) | OK, status=pending |
| Patient sees hospital connection (GET) | 1 connection, hospital_name present |
| /api/conditions/autocomplete?q=hyper | ["hypertension"] |
| Duplicate connect attempt | 409 error |
| Hospital profile save | navbar name updates live |
| Patient connect modal | Two sections render correctly |
| /api/hospital/trials for mgh | Active trials with match tiers |
| /api/hospital/inbox | Threads with unread counts |
| /api/patient/inbox | Threads with hospital names |
| Patient document upload | File saved, metadata in DB |
| Inbox Synthea seeding | 25 patients total confirmed |

---

### Session 6 Fixes (2026-04-25) — Messaging, inbox, trial dashboard, document upload, dataset seeding

#### Fix 18 — Hospital trial dashboard (My Trials tab)
**Before:** Hospital portal had no way to see which clinical trials were relevant to it.

**After:** New "My Trials" nav tab in `hospital.html`. Calls `GET /api/hospital/trials` → `pipeline.trials_for_hospital()`. Active-only filter at all 3 tiers. Cards show status badge, phase, match tier, facility name, summary excerpt, and a "View on ClinicalTrials.gov ↗" link.

Active-only filter: `if not self.trial_profiles[trial_id].get("is_active", False): continue` at each tier loop in `pipeline.py`.

#### Fix 19 — Messaging (chat in connections)
**Before:** Connections table had no messaging. Patients and hospitals could only see connection status.

**After:**
- New `connection_messages` table with `sender_role`, `sender_id`, `body`, `is_read`.
- `GET/POST /api/patient/connections/<cid>/messages` and `GET/POST /api/hospital/connections/<cid>/messages`.
- Both portals have a messages modal (`#msgModal`) opened by a Chat button in the Connections table.
- `mark_messages_read()` called on GET to auto-mark messages as read when the recipient opens the thread.

#### Fix 20 — Dedicated Inbox tab (both portals)
**Before:** Chat only accessible from the My Connections table row — no inbox overview.

**After:** New "Inbox" nav tab in both `hospital.html` and `patient.html`.
- Calls `GET /api/hospital/inbox` or `GET /api/patient/inbox`.
- Backed by `get_hospital_inbox_threads()` / `get_patient_inbox_threads()` — SQL subqueries aggregate last_message, last_message_at, unread_count per thread.
- Threads sorted by most recent activity (Python-side sort on `last_message_at or created_at`).
- Unread count badge on nav tab button updates when inbox loads.
- "Open" button reuses the existing `openMsgModal()` and messages modal.

#### Fix 21 — Document upload (patient portal)
**Before:** Patient profile had no file upload section.

**After:** "My Documents" card added to patient profile tab. 4 routes:
- `POST /api/patient/documents` — werkzeug `secure_filename`, 10 MB limit, allowed extensions: `.pdf/.docx/.doc/.txt/.png/.jpg/.jpeg`. Saves to `uploads/patient_docs/<patient_id>/`. Metadata stored as JSON array in `patient_accounts.documents`.
- `DELETE /api/patient/documents/<doc_id>` — removes file from disk and metadata from DB.
- `GET /api/patient/documents/<doc_id>/download` — serves file as attachment.
- `app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024` enforced Flask-side.

#### Fix 22 — Dataset-backed patient seeding
**Before:** Only hand-made demo patients in DB (john_doe only had open_to_trials=1 initially). Hospital search returned 0 results on fresh DB.

**After:** `_seed_dataset_patients(c, max_patients=20)` in `database.py` seeds 20 real Synthea patients from CSV files on first run. Skips deceased patients (Death_Date not empty). Reads up to 8 conditions + 6 medications per patient. Username: `synthea_<first8chars_of_Patient_ID>`, password `pass123`, `open_to_trials=1`.

All 5 hand-made demo patients also set to `open_to_trials=1`. Total: 25 patients in DB.

#### Fix 23 — Hospital search include_connected toggle
**Before:** Hospital Search tab also excluded already-connected patients, same as Available Patients tab — making it useless for re-searching.

**After:** Search tab adds `include_connected=true` query param. `GET /api/hospital/patients?include_connected=true` bypasses the exclusion subquery. Available Patients tab retains strict exclusion. Toggle checkbox in Search tab UI.

#### Fix 24 — Template auto-reload
**Before:** `app.run(debug=False, use_reloader=False)` — template edits required server restart to take effect.

**After:** `app.config["TEMPLATES_AUTO_RELOAD"] = True` added after other config lines. Templates now reload on every request without enabling full debug mode or the reloader.

---

## Known Issues / Future Improvements

1. **High pseudo-label positive rate (82.1%)** — lowers AUC-ROC to ~0.60. Fix: raise label threshold from 0.5 to 0.6, or explicitly sample equal positive/negative pairs.

2. **data_completeness feature importance = 0** — nearly constant across training pairs (all synthetic patients have complete data). Consider removing from FEATURE_COLS.

3. **Fuzzy condition matching not implemented** — only exact condition name overlaps used (106 conditions). Substring/semantic fuzzy matching would expand coverage significantly.

4. **lab_availability coverage is low (8.7%)** — observations file is sparse. Consider normalising denominator to the subset that has any lab data.

5. **Hospital portal does not rank patients by match quality** — listed in insertion order. Could rank by condition overlap with the hospital's research_conditions.

6. **No email/notification system** — connection requests visible only inside the portal.

7. **No automated tests** — syntax checking only (`python -m py_compile`). Key flows to cover: patient registration → profile update → match → connect; hospital registration → patient browse → connect → status update; duplicate connection rejection.

8. **Inbox badge not auto-refreshed** — unread count badge only updates when the user clicks the Inbox tab. No real-time push; would require polling or WebSockets.

9. **Document access control** — uploaded files are served from disk by doc_id only; no additional hospital-side access to patient documents (by design — privacy model). Hospital sees document count in patient profile only after connection.

10. **Synthea patients have Synthea-style names** (e.g. "Geovany567 Reichert456") — cosmetically odd but functionally correct. No fix needed for demo.
