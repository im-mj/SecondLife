# Second Life — LLM Context File

> **Purpose:** Authoritative reference for any AI assistant or developer working on this project.
> Covers every aspect: goals, data files used, code architecture, feature engineering, API, model details, and how to run the system.

---

## Project Overview

**Name:** Second Life
**Course:** DSCI 5260 — Business Analytics Capstone
**Team:** Group 7
- Manoj Guttikonda (11806491)
- Krishna Sri Sai (11806493)
- Soumika Kandari (11682517)
- Rohith Tummalapalli (11806174)
- Nikhitha Chada (11808001)

**Goal:** Match patients who have a specific medical condition to clinical trials that are actively researching that condition. Given a patient (by ID or by manual entry of conditions + age + gender), the system returns ranked clinical trials they are most likely eligible for, with a calibrated ML eligibility probability score.

---

## Running the System

```bash
cd "E:/DSCI 5260/Project/PT"
python app.py
```

Open **http://localhost:5000** in a browser.

- **First run:** ~90–120 seconds. All 9 data files load, model trains, cache is saved.
- **Subsequent runs:** ~15–20 seconds. Model loads from `model_cache.pkl`.
- **Force retrain:** Delete `model_cache.pkl` and restart.

---

## Directory Structure

```
E:/DSCI 5260/Project/PT/
│
├── app.py                              ← Flask web server (port 5000)
├── pipeline.py                         ← Core ML pipeline
├── model_cache.pkl                     ← Trained model cache (auto-created)
├── llm.md                              ← This file
│
├── templates/
│   └── index.html                      ← Single-page app (HTML/CSS/JS, no frameworks)
│
├── Final Patients Synthea Data/        ← Synthetic patient data
│   ├── final_patients_conditions.csv   ✅ USED — patient conditions
│   ├── patients_details.csv            ✅ USED — demographics, age, gender
│   ├── patients_medications.csv        ✅ USED — medication history → med_compatibility feature
│   ├── patients_observations.csv       ✅ USED — lab/vital signs → lab_availability feature
│   └── patients_conditions.csv         ⚠️  Raw unprocessed duplicate of final_patients_conditions.csv
│
├── Final Clinical Trails Data/         ← Clinical trial data (ClinicalTrials.gov / AACT)
│   ├── trail_conditions.csv            ✅ USED — condition ↔ trial mapping
│   ├── trail_eligibilities.csv         ✅ USED — age range, gender, criteria text
│   ├── trail_studies.csv               ✅ USED — title, status, phase, enrollment
│   ├── trail_facilities.csv            ✅ USED — location, city, state, country, coordinates
│   ├── trail_brief_summaries.csv       ✅ USED — summary text shown in UI
│   ├── trail_interventions.csv         ✅ USED — drug interventions → med_compatibility feature
│   ├── trail_countries.csv             ✅ USED — countries → geo_feasibility feature
│   ├── trail_keywords.csv              ✅ USED — extends condition index (keyword bridge)
│   ├── trail_detailed_descriptions.csv ➡️  Available, not loaded (too large, summaries sufficient)
│   ├── trail_outcomes.csv              ➡️  Available, future use (outcome-based matching)
│   ├── trail_sponsors.csv              ➡️  Available, future use (industry vs academic filter)
│   ├── trail_interventions_other_names.csv ➡️ Available, future use
│   ├── trail_central_contacts.csv      ➡️  Available, future use (contact info)
│   ├── trail_facility_contacts.csv     ➡️  Available, future use
│   ├── trail_overall_officials.csv     ➡️  Available, future use
│   ├── trail_responsible_parties.csv   ➡️  Available, future use
│   └── trail_result_contacts.csv       ➡️  Available, future use
│
├── mimic-iv-clinical-database-demo-2.2/  ← Real patients (NDA required)
│   ├── hosp/patients.csv.gz            ✅ USED — 100 real de-identified patients
│   ├── hosp/diagnoses_icd.csv.gz       ✅ USED — ICD-9/10 diagnosis codes
│   ├── hosp/d_icd_diagnoses.csv.gz     ✅ USED — ICD code → human-readable name dictionary
│   └── (other MIMIC tables)            ➡️  Available, not used in current validation
│
├── Code/                               ← Original exploratory notebooks
│   ├── Second_Life_Final_Notebook_V2.ipynb  ← The primary reference notebook
│   ├── main.py                              ← Earlier pipeline attempt (paths were wrong, superseded)
│   ├── Clincial.ipynb                       ← Fuzzy condition matching exploration
│   ├── Data_Cleaning_and_Understanding.ipynb
│   └── Data Understanding Phase.ipynb
│
├── Visualizations/
│   ├── Clinical Trials.twbx
│   ├── Patients.twbx
│   └── Combined.twbx
│
└── Assignment 1–5/                     ← Submitted coursework
    └── Assignment 5/ contains a notebook identical to Second_Life_Final_Notebook_V2.ipynb
```

---

## Data Sources & Schemas

### 1. `final_patients_conditions.csv` — Patient Conditions

| Column | Type | Notes |
|---|---|---|
| `Condition_Start_Date` | DD-MM-YYYY | Diagnosis date |
| `Condition_End_Date` | DD-MM-YYYY or NaN | NaN = still active |
| `Patient_ID` | UUID | Primary key |
| `Encounter_ID` | UUID | Clinical encounter |
| `Condition_Code` | int (SNOMED CT) | Standardised code |
| `Condition_Name` | string | Human-readable |

**967,454 rows · 228,566 unique patients · 117 unique conditions**

Top conditions: sinusitis (165K), acute viral pharyngitis (88K), acute bronchitis (71K), prediabetes (69K), hypertension (60K)

---

### 2. `patients_details.csv` — Patient Demographics

| Column | Notes |
|---|---|
| `Patient_ID` | UUID — primary key |
| `Birth_Date` | DD-MM-YYYY → converted to `Patient_Age` (as of 2024-01-01) |
| `Death_Date` | DD-MM-YYYY or NaN |
| `First_Name`, `Last_Name` | Synthetic |
| `Gender` | M / F — uppercased in pipeline |
| `Race`, `Ethnicity` | Demographics |
| `Address` | Full US address (Synthea is US-based) |

**266,003 rows**

---

### 3. `patients_medications.csv` — Patient Medication History ✅ NEW

| Column | Notes |
|---|---|
| `Patient_ID` | UUID |
| `Medication_Start_Date` | DD-MM-YYYY |
| `Medication_End_Date` | DD-MM-YYYY or NaN (NaN = currently active) |
| `Medication_Name` | Full name e.g. "Penicillin V Potassium 250 MG" |
| `Reason_Description` | Condition this was prescribed for |

**794,978 rows · 213,182 patients · 101 unique medication names**

**Pipeline usage:** Drug keyword extracted (`_drug_keyword()`), grouped by patient. Active medications (no end date) preferred; falls back to all medications. Creates `patient_med_keywords` dict used for `med_compatibility` feature.

Sample extractions: `"Penicillin V Potassium 250 MG"` → `"penicillin"`, `"Ibuprofen 200 MG"` → `"ibuprofen"`, `"Cisplatin 50 MG Injection"` → `"cisplatin"`

---

### 4. `patients_observations.csv` — Lab Values & Vitals ✅ NEW

| Column | Notes |
|---|---|
| `Patient_ID` | UUID |
| `Observation_Date` | DD-MM-YYYY |
| `Observation_Name` | e.g. "Body Height", "Hemoglobin A1c/Hemoglobin.total in Blood" |
| `Observation_Value` | Numeric or string |
| `Observation_Unit` | e.g. "cm", "mmHg", "kg/m2" |

**1,048,575 rows · 23,231 patients · 63 observation types**

Key observation types: Body Height, Body Weight, BMI, Systolic BP, Diastolic BP, HbA1c, Glucose, Creatinine, Total Cholesterol, HDL, LDL

**Pipeline usage:** Count of unique observation types per patient, normalised by 20. Creates `patient_lab_score` dict used for `lab_availability` feature.

---

### 5. `trail_conditions.csv` — Trial ↔ Condition Mapping

| Column | Notes |
|---|---|
| `Condition_Record_ID` | Numeric record ID |
| `Trial_ID` | NCT number |
| `Condition_Name` | Original name |
| `Condition_Name_Lower` | Pre-cleaned lowercase version |

**1,015,883 rows · 570,385 unique trials · 127,239 unique conditions**

---

### 6. `trail_eligibilities.csv` — Trial Eligibility Criteria

> ⚠️ **Known quirk:** The `Gender` column has a leading space in the raw file (` Gender`). The pipeline strips all column names with `.str.strip()` on load.

| Column | Notes |
|---|---|
| `Trial_ID` | NCT number |
| `Gender` (raw: ` Gender`) | ALL / MALE / FEMALE |
| `Minimum_Age` | e.g. "18 Years", "6 Months" — parsed to float years |
| `Maximum_Age` | e.g. "80 Years" — parsed to float years. Missing → 120 |
| `Eligibility_Criteria` | Full inclusion/exclusion criteria text |
| `Adult_Allowed`, `Child_Allowed`, `Older_Adult_Allowed` | t / f |

**570,417 rows**

---

### 7. `trail_studies.csv` — Trial Metadata

| Column | Notes |
|---|---|
| `Trial_ID` | NCT number — primary key |
| `Brief_Title` | Short title shown in UI |
| `Overall_Status` | RECRUITING / COMPLETED / UNKNOWN / etc. |
| `Phase` | PHASE1 / PHASE2 / PHASE3 / PHASE4 |
| `Study_Type` | INTERVENTIONAL / OBSERVATIONAL |
| `Enrollment` | Target patient count |
| `Start_Date` | Trial start date |

**571,379 rows**

Status distribution: COMPLETED (312K), UNKNOWN (88K), RECRUITING (65K), TERMINATED (33K), NOT_YET_RECRUITING (26K)

---

### 8. `trail_interventions.csv` — Trial Drug/Procedure Interventions ✅ NEW

| Column | Notes |
|---|---|
| `Trial_ID` | NCT number |
| `Intervention_Type` | DRUG / BEHAVIORAL / DEVICE / PROCEDURE / BIOLOGICAL / etc. |
| `Intervention_Name` | Drug or procedure name |
| `Intervention_Description` | Detailed protocol text |

**1,173,448 rows · DRUG type: 398,380 rows · 196,865 trials have drug data**

**Pipeline usage:** Only DRUG-type interventions are used. Drug keyword extracted (`_drug_keyword()`), grouped by Trial_ID. Creates `trial_drug_keywords` dict. Cross-referenced with `patient_med_keywords` to compute `med_compatibility` feature.

---

### 9. `trail_countries.csv` — Trial Geographic Reach ✅ NEW

| Column | Notes |
|---|---|
| `Trial_ID` | NCT number |
| `Country_Name` | Full country name |

**778,382 rows · 519,412 unique trials with country data**

Top countries: United States (194K), China (49K), France (42K), Canada (33K), Germany (29K)

**Pipeline usage:** Grouped by Trial_ID into set of countries. Geo feasibility scoring:
- US present: 1.0
- ≥5 countries (multi-national): 0.7
- 2–4 countries: 0.5
- Single non-US country: 0.35
- No data: 0.5 (neutral)

---

### 10. `trail_keywords.csv` — Trial Keywords ✅ NEW

| Column | Notes |
|---|---|
| `Trial_ID` | NCT number |
| `Keyword_Name_Lower` | Lowercased keyword |

**1,507,316 rows**

**Pipeline usage:** Keywords are checked against the 106 overlapping conditions. Matching keywords are added to the `cond_to_trials` reverse index, expanding the set of candidate trials found for a given condition query.

---

### 11. `trail_facilities.csv` — Trial Locations

| Column | Notes |
|---|---|
| `Trial_ID` | NCT number |
| `Facility_City`, `Facility_State`, `Facility_Country` | Location |
| `Facility_Latitude`, `Facility_Longitude` | GPS coordinates |

Used in UI to display trial location and site count. Not a model feature (future: distance-based geo scoring).

---

### 12. `trail_brief_summaries.csv` — Trial Summaries

Used in UI only to display a readable description under each trial card.

---

### 13. MIMIC-IV Demo — Real Patient Validation

| File | Rows | Usage |
|---|---|---|
| `hosp/patients.csv.gz` | 100 | age, gender per patient |
| `hosp/diagnoses_icd.csv.gz` | 4,506 | ICD-9/10 codes per admission |
| `hosp/d_icd_diagnoses.csv.gz` | 109,775 | ICD code → long_title lookup |

Real de-identified ICU patients. Access requires NDA signature. Used only for pipeline validation — not for training.

---

## The 106 Overlapping Conditions

The conditions shared between the Synthea patient vocabulary (117 conditions) and the clinical trial condition vocabulary (127,239 conditions). These are the **matching bridge** — only patients and trials sharing at least one of these conditions can be paired.

```
acute allergic reaction          acute bacterial sinusitis         acute bronchitis
acute patella tendon rupture     acute viral pharyngitis           alzheimer's disease
amputation of lower limb         amputation of upper limb          appendectomy
appendicitis                     appendix rupture                  asthma
atopic dermatitis                attempted suicide                 attention-deficit-disordered children
bleeding anal                    brain concussion                  cardiac arrest
childhood asthma                 chromosomal abnormality           chronic migraine without aura, intractable
chronic pain                     chronic sinusitis                 chronic spinal paralysis
closed fracture of hip           concussion with brief loss of consciousness
congenital uterine anomaly       contact dermatitis                coronary artery disease
cystitis                         diabetes                          diabetic blindness
diabetic retinal disease         diabetic retinopathy associated with type 2 diabetes mellitus
drug overdose                    early onset alzheimer disease     eclampsia, antepartum
end-stage renal disease          facial laceration                 fibromyalgia syndrome, primary
forearm fracture                 fracture of ankle                 fracture of clavicle
gout                             history of myocardial infarction  hypertension
impacted molar                   injury of anterior cruciate ligament
laceration of forearm            laceration of hand                localized primary osteoarthritis of hip
lupus erythematosus              macular edema due to type 2 diabetes mellitus
malignant neoplasm, overlapping lesion of breast
malignant tumor of colon         medial collateral ligament        microalbuminuria due to type 2 diabetes mellitus
miscarriage in first trimester   miscarriage in second trimester   myocardial infarction
non-small cell carcinoma of lung, tnm stage 4
non-small cell lung cancer       nonproliferative diabetic retinopathy
normal pregnancy                 obstructive chronic bronchitis    osteoarthritis of hip
osteoarthritis of knee           osteoporosis                      otitis media
perennial allergic rhinitis      perennial allergic rhinitis with seasonal variation
peripheral neuropathy with type 2 diabetes
persistent diarrhea              pneumonia                         polyp of colon
prediabetes                      preeclampsia                      pregnancy complication
primary malignant neoplasm of lung
proliferative diabetic retinopathy
pulmonary emphysema              pyelonephritis                    rectal polyp
recurrent urinary tract infection
rheumatoid arthritis             risk of fracture                  rotator cuff injury
seasonal allergic rhinitis       second-degree burn                secondary malignant neoplasm of bone
sinusitis                        small cell carcinoma of lung      small cell lung cancer
sprain of ankle                  streptococcal sore throat         stroke
suicide due to use of firearm    suspected lung cancer             tear of meniscus of knee
third-degree burn                traumatic brain damage            tubal pregnancy
urinary tract infection          whiplash injury                   wrist disarticulation
wrist sprain
```

---

## Feature Engineering — All 17 Features

Feature set aligns with `Second_Life_Final_Notebook_V2.ipynb` + real-data replacements for previously Beta-simulated feasibility factors.

All features are **soft and continuous — no hard binary gates**. This produces calibrated probabilities rather than hard pass/fail verdicts.

### Condition Matching Features

| Feature | Formula / Source | Range |
|---|---|---|
| `condition_overlap` | `len(patient_conds ∩ trial_conds)` | 0–N |
| `jaccard_similarity` | `overlap / (patient_conds ∪ trial_conds)` | 0–1 |
| `overlap_ratio_trial` | `overlap / len(trial_conds)` | 0–1 |
| `overlap_ratio_patient` | `overlap / len(patient_conds)` | 0–1 |
| `condition_rarity_score` | `mean(1/log2(n_trials_per_cond + 2))` over overlapping conditions. Rare conditions matching = stronger signal. Normalised to 0–1 | 0–1 |
| `trial_specificity` | `1 / trial_condition_count` — focused single-condition trials score higher | 0–1 |

### Patient Profile Features

| Feature | Formula | Range |
|---|---|---|
| `condition_burden` | `min(total_patient_conditions / 10, 1.0)` | 0–1 |
| `active_ratio` | `active_conditions / total_conditions` (active = no end date) | 0–1 |
| `resolved_ratio` | `resolved_conditions / total_conditions` | 0–1 |

### Age Features (continuous, no hard gate)

| Feature | Formula | Range |
|---|---|---|
| `age_distance` | `(distance_from_range) / 100` if outside range, else 0 | 0–1 |
| `age_centered` | Patient age position within trial's age range, centred at midpoint | −1 to 1 |
| `age_compatibility` | 1.0 within range; `max(0, 1 − distance/30)` outside range — decays over 30-year gap | 0–1 |

### Gender Feature

| Feature | Formula | Range |
|---|---|---|
| `gender_compatibility` | 1.0 if trial accepts ALL or matching gender; 0.1 if mismatch (not 0 — soft penalty) | 0.1 or 1.0 |

### Real Feasibility Features (replaces Beta simulation from notebook)

| Feature | Source | Formula | Range |
|---|---|---|---|
| `geo_feasibility` | `trail_countries.csv` | 1.0 US, 0.7 multi-national (≥5 countries), 0.5 (2–4 countries), 0.35 single non-US, 0.5 if no data | 0.35–1.0 |
| `med_compatibility` | `patients_medications.csv` + `trail_interventions.csv` | Keyword overlap: 0.8–1.0 if any patient med matches trial drug; 0.4 if no match; 0.5 if data missing | 0.4–1.0 |
| `lab_availability` | `patients_observations.csv` | `min(unique_lab_types / 20, 1.0)` per patient | 0–1 |

### Quality Feature

| Feature | Formula | Range |
|---|---|---|
| `data_completeness` | Fraction of 5 key fields present (age, gender, conditions, trial age range, trial gender) | 0–1 |

---

## Model Details

### Algorithm
Random Forest Classifier with isotonic calibration

```python
RandomForestClassifier(
    n_estimators=200,
    max_depth=12,
    min_samples_split=10,
    class_weight='balanced',
    random_state=42,
    n_jobs=-1
)
CalibratedClassifierCV(rf, cv=3, method='isotonic')
```

### Training Data
- **113,675 patient–trial pairs** (3,000 sampled patients × candidate trials per patient + negatives)
- **90,994 training / 22,681 test** — patient-level `GroupShuffleSplit(test_size=0.2)`, no leakage
- Positive rate: 57.5%
- Labels: rule-based (`age_compat > 0.7 AND gender_compat > 0.5 AND jaccard > 0.05`) with 15% noise

### Performance

| Metric | Value |
|---|---|
| Accuracy | 84.86% |
| Precision | 84.87% |
| Recall | 89.54% |
| F1 Score | 87.14% |
| **AUC-ROC** | **0.8430** |
| CV AUC-ROC (5-fold GroupKFold) | 0.8419 ± 0.0016 |
| Brier Score | 0.1285 |

### Feature Importance

| Rank | Feature | Importance |
|---|---|---|
| 1 | age_compatibility | 19.5% |
| 2 | age_distance | 15.4% |
| 3 | jaccard_similarity | 14.2% |
| 4 | overlap_ratio_trial | 11.9% |
| 5 | overlap_ratio_patient | 9.9% |
| 6 | condition_overlap | 9.3% |
| 7 | condition_rarity_score | 7.1% |
| 8 | age_centered | 6.2% |
| 9 | gender_compatibility | 4.6% |
| 10 | resolved_ratio | 0.4% |
| 11 | condition_burden | 0.4% |
| 12 | active_ratio | 0.4% |
| 13 | lab_availability | 0.3% |
| 14 | geo_feasibility | 0.2% |
| 15 | med_compatibility | 0.2% |
| 16 | trial_specificity | 0.1% |
| 17 | data_completeness | 0.0% |

**Notes on low-importance feasibility features:**
- `geo_feasibility` is constant per trial, not per patient–trial pair (patient location not in dataset), limiting discriminative power
- `med_compatibility` matches are sparse (only 23K of 228K patients have lab data; few medication names match trial drug keywords exactly)
- `lab_availability` varies per patient but not per trial — low pair-level discriminative value
- These features remain in the model as they add signal when data is available and do not harm overall performance

### Scoring Formula (used to rank final results)

```
combined_score = 0.6 × eligibility_probability + 0.4 × (match_score / 100)

match_score = (0.35 × overlap_ratio_trial
             + 0.25 × overlap_ratio_patient
             + 0.20 × age_compatibility
             + 0.20 × gender_compatibility) × 100
```

---

## MIMIC-IV Validation

**100 real de-identified ICU patients** from MIMIC-IV demo dataset.

**ICD → Condition mapping strategy (3-tier):**
1. Exact lowercase match against overlapping conditions
2. Substring containment in either direction
3. Word-level overlap ≥75% of shorter string's words

**Results: 90/100 patients matched (90% match rate)**

Sample matches:
- Patient 10003400 (age 72, F) → hypertension, osteoarthritis → *Olmesartan on Ambulatory Blood Pressure Change*
- Patient 10002428 (age 80, F) → hypertension, pneumonia, osteoporosis → *Integration of Guidelines for Comorbidities*

Low match rate for some patients is expected: MIMIC is a critical-care dataset (ICU patients with severe acute conditions like sepsis, respiratory failure). These severe conditions don't overlap with the 106 bridging conditions from Synthea's outpatient-focused dataset.

---

## Code Architecture

### `pipeline.py`

**Class `SecondLifePipeline`**

#### `.load()`
Loads all 9 data files (patient conditions, demographics, medications, observations; trial conditions, eligibilities, studies, interventions, countries, keywords, facilities, summaries). Pre-computes:
- `cond_rarity_map` — condition → rarity score (1/log2 of trial count, normalised)
- `trial_geo_score` — trial_id → geo_feasibility from countries data
- `trial_drug_keywords` — trial_id → set of drug keyword strings
- `patient_med_keywords` — patient_id → set of medication keyword strings
- `patient_lab_score` — patient_id → lab coverage ratio
- `trial_profiles` — full trial profile dict indexed by trial_id
- `cond_to_trials` — reverse index: condition → list of trial_ids (extended with keyword matches)
- `patient_profiles` — patient profile dict indexed by patient_id

#### `.train(n_patients=3000)`
Generates training pairs, applies rule-based labels with 15% noise, performs patient-level grouped split, trains calibrated Random Forest, saves to `model_cache.pkl`.

#### `.match_patient(conditions, age, gender, top_k=20, active_only=True, patient_id=None)`
Main matching function. Uses `patient_id` to look up real medication and lab data when available. Returns list of ranked trial dicts including all scores, conditions, location, criteria, and summary.

#### `.validate_mimic()`
Loads MIMIC data, maps ICD codes to condition vocabulary, runs matching pipeline on all 100 patients.

#### `_compute_features(...)`
Module-level function. Computes all 17 features for a single patient–trial pair. Takes pre-computed geo/med/lab values as parameters for performance.

#### `_drug_keyword(name)`
Extracts primary drug name from a full medication/intervention string (e.g. `"Penicillin V Potassium 250 MG"` → `"penicillin"`).

---

### `app.py` — Flask Web Server

Starts on **port 5000**. Pipeline loads in a background thread so the server responds immediately.

#### API Routes

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Renders `templates/index.html` |
| `GET` | `/api/status` | `{ready, stats, model_metrics}` — 202 while loading |
| `POST` | `/api/match` | Main matching endpoint |
| `GET` | `/api/patient/<id>` | Patient profile + conditions + medications |
| `GET` | `/api/patients/search?q=` | Search-as-you-type (min 4 chars) |
| `GET` | `/api/conditions/autocomplete?q=` | Condition autocomplete (min 2 chars) |
| `GET` | `/api/validate/mimic` | Run MIMIC-IV validation (~30s) |
| `GET` | `/api/stats` | Dataset + model stats |

#### `POST /api/match` — Request

```json
// Patient ID mode
{ "mode": "patient", "patient_id": "<uuid>", "top_k": 20, "active_only": true }

// Manual entry mode
{ "mode": "manual", "conditions": ["hypertension", "diabetes"],
  "age": 55, "gender": "M", "top_k": 20, "active_only": true }
```

#### `POST /api/match` — Response (per result)

```json
{
  "trial_id": "NCT02864212",
  "title": "...",
  "phase": "PHASE4",
  "status": "RECRUITING",
  "min_age": 18, "max_age": 75, "sex": "ALL",
  "eligibility_probability": 87.3,
  "match_score": 91.5,
  "combined_score": 91.4,
  "jaccard_similarity": 0.667,
  "age_compatibility": 100.0,
  "gender_compatibility": 100.0,
  "geo_feasibility": 100.0,
  "med_compatibility": 50.0,
  "condition_rarity_score": 0.134,
  "overlap_conditions": ["diabetes", "hypertension"],
  "trial_conditions": ["diabetes", "hypertension", "obesity"],
  "criteria": "Inclusion Criteria:\n...",
  "summary": "This study...",
  "location": "Boston, MA, United States",
  "n_sites": 12
}
```

---

### `templates/index.html` — Frontend

Pure HTML/CSS/JavaScript. No external dependencies or CDN. ~700 lines.

**Three tabs:**

**Tab 1 — Match Patients**
- Mode toggle: Patient ID search / Manual entry
- Patient ID: search-as-you-type dropdown, shows info panel with full conditions + medications
- Manual: tag-style condition input with autocomplete, age, gender
- Options: result count, active-only toggle
- Results: collapsible trial cards with score circle (green/amber/red), badges, score breakdown bars, condition tags (overlapping highlighted green), eligibility criteria accordion, ClinicalTrials.gov link

**Tab 2 — Model & Stats**
- Dataset stat cards (9 numbers from all loaded data files)
- Model metrics table with progress bar visualisation
- Feature importance bar chart
- All 106 overlapping conditions as tags

**Tab 3 — MIMIC Validation**
- On-demand validation button
- Summary stats (total patients, matched, match rate %)
- Per-patient table (ICD conditions → mapped conditions → top match + score)

---

## Relationship to Original Notebooks

### `Second_Life_Final_Notebook_V2.ipynb` (primary reference)

The original notebook uses these 11 features (after VIF-based reduction from 23):
`active_conditions, trial_condition_count, condition_overlap, jaccard_similarity, active_ratio, condition_rarity_score, data_completeness, age_compatibility, geo_feasibility, med_compatibility, lab_availability`

**Key difference:** The notebook simulates `age_compatibility`, `geo_feasibility`, `med_compatibility`, and `lab_availability` using **Beta distributions** because it doesn't join the real data files. The production `pipeline.py` replaces those Beta simulations with **real data** from:
- `trail_eligibilities.csv` → age_compatibility, age_distance, age_centered
- `trail_countries.csv` → geo_feasibility
- `patients_medications.csv` + `trail_interventions.csv` → med_compatibility
- `patients_observations.csv` → lab_availability

The production pipeline also adds `resolved_ratio`, `overlap_ratio_trial`, `overlap_ratio_patient`, `gender_compatibility`, `trial_specificity`, and `condition_burden` beyond the notebook's feature set.

### `main.py` in Code/ folder

An earlier pipeline attempt using the same conceptual approach as `pipeline.py` but with:
- Wrong data file paths (pointing to non-existent `Clinical Trails Cleaned/` directory)
- No medication, observation, interventions, or countries data
- Smaller sample size (500 patients × 100 trials)
- **Superseded by `pipeline.py`**

### `Assignment 5` notebook

Exact duplicate of `Second_Life_Final_Notebook_V2.ipynb` — no new techniques.

---

## Known Limitations & Future Work

| Item | Current | Future |
|---|---|---|
| Label quality | Rule-based with 15% noise | Real clinician annotations |
| Condition vocabulary | 106 exact-match conditions | Embedding-based fuzzy matching (BioBERT/MedBERT) |
| Eligibility criteria | Displayed as text | NLP parsing for lab values, comorbidity exclusions |
| Geographic matching | Country-level geo score | Distance from patient address to nearest trial site (GPS coordinates available in `trail_facilities.csv`) |
| Medication compatibility | Keyword match | Drug-drug interaction databases, contraindication checks |
| Lab values | Coverage ratio | Match specific lab thresholds in eligibility criteria |
| Temporal | Not modelled | Trial enrollment deadline, condition recency |
| Model explainability | Feature importance | SHAP values per prediction |
| UI | Search + results | User will provide instructions for further UI enhancements |

---

## Environment & Dependencies

**Python:** 3.14.2

```
pandas==3.0.2
numpy==2.4.4
scikit-learn==1.8.0
scipy==1.17.1
flask==3.1.3
matplotlib==3.10.9
seaborn==0.13.2
```

```bash
pip install pandas numpy scikit-learn scipy flask matplotlib seaborn
```

---

## Quick API Reference

```bash
# Status
curl http://localhost:5000/api/status

# Match by patient ID
curl -X POST http://localhost:5000/api/match \
  -H "Content-Type: application/json" \
  -d '{"mode":"patient","patient_id":"<uuid>","top_k":20}'

# Match by manual conditions
curl -X POST http://localhost:5000/api/match \
  -H "Content-Type: application/json" \
  -d '{"mode":"manual","conditions":["hypertension","diabetes"],"age":55,"gender":"M"}'

# Patient info
curl http://localhost:5000/api/patient/<uuid>

# Patient search (min 4 chars)
curl "http://localhost:5000/api/patients/search?q=660b"

# Condition autocomplete (min 2 chars)
curl "http://localhost:5000/api/conditions/autocomplete?q=hyper"

# MIMIC validation
curl http://localhost:5000/api/validate/mimic

# Stats + model metrics
curl http://localhost:5000/api/stats
```
