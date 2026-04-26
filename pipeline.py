"""
Second Life — Clinical Trial Matching Pipeline
DSCI 5260 | Group 7

Full pipeline using ALL available data files:
  Patient side  : conditions, demographics, medications, observations
  Trial side    : conditions, eligibilities, studies, facilities,
                  summaries, interventions, countries, keywords
  Validation    : MIMIC-IV (real patients, NDA access)

Features align with Second_Life_Final_Notebook_V2.ipynb plus
real-data replacements for previously simulated feasibility factors.
"""

import re
import math
import pickle
import warnings
from pathlib import Path
from datetime import datetime

# US state abbreviation → full name (patient addresses use abbreviations,
# facility data uses full names)
STATE_ABBREV = {
    "AL":"Alabama","AK":"Alaska","AZ":"Arizona","AR":"Arkansas","CA":"California",
    "CO":"Colorado","CT":"Connecticut","DE":"Delaware","FL":"Florida","GA":"Georgia",
    "HI":"Hawaii","ID":"Idaho","IL":"Illinois","IN":"Indiana","IA":"Iowa",
    "KS":"Kansas","KY":"Kentucky","LA":"Louisiana","ME":"Maine","MD":"Maryland",
    "MA":"Massachusetts","MI":"Michigan","MN":"Minnesota","MS":"Mississippi",
    "MO":"Missouri","MT":"Montana","NE":"Nebraska","NV":"Nevada","NH":"New Hampshire",
    "NJ":"New Jersey","NM":"New Mexico","NY":"New York","NC":"North Carolina",
    "ND":"North Dakota","OH":"Ohio","OK":"Oklahoma","OR":"Oregon","PA":"Pennsylvania",
    "RI":"Rhode Island","SC":"South Carolina","SD":"South Dakota","TN":"Tennessee",
    "TX":"Texas","UT":"Utah","VT":"Vermont","VA":"Virginia","WA":"Washington",
    "WV":"West Virginia","WI":"Wisconsin","WY":"Wyoming","DC":"District of Columbia",
}

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, average_precision_score, brier_score_loss,
    f1_score, precision_score, recall_score, roc_auc_score,
)
from sklearn.model_selection import GroupKFold, GroupShuffleSplit, cross_val_score
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent

# Patient data (Synthea)
PATIENT_CONDITIONS_PATH  = BASE_DIR / "Final Patients Synthea Data" / "final_patients_conditions.csv"
PATIENT_DETAILS_PATH     = BASE_DIR / "Final Patients Synthea Data" / "patients_details.csv"
PATIENT_MEDICATIONS_PATH = BASE_DIR / "Final Patients Synthea Data" / "patients_medications.csv"
PATIENT_OBSERVATIONS_PATH= BASE_DIR / "Final Patients Synthea Data" / "patients_observations.csv"

# Trial data (ClinicalTrials.gov / AACT)
TRIAL_CONDITIONS_PATH    = BASE_DIR / "Final Clinical Trails Data" / "trail_conditions.csv"
TRIAL_ELIGIBILITY_PATH   = BASE_DIR / "Final Clinical Trails Data" / "trail_eligibilities.csv"
TRIAL_STUDIES_PATH       = BASE_DIR / "Final Clinical Trails Data" / "trail_studies.csv"
TRIAL_FACILITIES_PATH    = BASE_DIR / "Final Clinical Trails Data" / "trail_facilities.csv"
TRIAL_SUMMARIES_PATH     = BASE_DIR / "Final Clinical Trails Data" / "trail_brief_summaries.csv"
TRIAL_INTERVENTIONS_PATH = BASE_DIR / "Final Clinical Trails Data" / "trail_interventions.csv"
TRIAL_COUNTRIES_PATH     = BASE_DIR / "Final Clinical Trails Data" / "trail_countries.csv"
TRIAL_KEYWORDS_PATH      = BASE_DIR / "Final Clinical Trails Data" / "trail_keywords.csv"

# MIMIC-IV (real patients, NDA)
MIMIC_PATIENTS_PATH  = BASE_DIR / "mimic-iv-clinical-database-demo-2.2" / "hosp" / "patients.csv.gz"
MIMIC_DIAGNOSES_PATH = BASE_DIR / "mimic-iv-clinical-database-demo-2.2" / "hosp" / "diagnoses_icd.csv.gz"
MIMIC_ICD_DICT_PATH  = BASE_DIR / "mimic-iv-clinical-database-demo-2.2" / "hosp" / "d_icd_diagnoses.csv.gz"

MODEL_CACHE = BASE_DIR / "model_cache.pkl"

# ---------------------------------------------------------------------------
# Feature columns — matches Second_Life_Final_Notebook_V2.ipynb feature set
# plus real-data replacements for the Beta-simulated feasibility factors
# ---------------------------------------------------------------------------
FEATURE_COLS = [
    # --- Condition matching (from notebook) ---
    "condition_overlap",          # raw count of shared conditions
    "jaccard_similarity",         # overlap / union
    "overlap_ratio_trial",        # overlap / len(trial_conditions)
    "overlap_ratio_patient",      # overlap / len(patient_conditions)
    "condition_rarity_score",     # mean(1/log2(n_trials_per_cond+2)) — rare conditions = higher score
    "trial_specificity",          # 1 / trial_condition_count — focused trials score higher
    # --- Patient profile ---
    "condition_burden",           # total patient conditions / 10 (normalised)
    "active_ratio",               # active (unresolved) conditions / total
    "resolved_ratio",             # resolved conditions / total  ← NEW
    # --- Age (soft continuous, no hard gate) ---
    "age_distance",               # normalised distance outside age range (0 if within)
    "age_centered",               # position within age range (−1 to +1)
    "age_compatibility",          # 1.0 in range, decays over 30-year gap
    # --- Gender (soft) ---
    "gender_compatibility",       # 1.0 match/all, 0.1 mismatch
    # --- Real feasibility factors (replace Beta simulation) ---
    "geo_feasibility",            # 1.0 same-state facility, 0.8 US other state, 0.4 international
    "med_compatibility",          # keyword overlap: patient meds ↔ trial drug interventions
    "lab_availability",           # patient observation/lab type coverage (0–1)
    # --- Data quality ---
    "data_completeness",          # fraction of key fields present
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_age(age_str):
    if pd.isna(age_str):
        return None
    s = str(age_str).lower().strip()
    if s in ("n/a", "na", "", "none"):
        return None
    nums = re.findall(r"(\d+)", s)
    if not nums:
        return None
    age = int(nums[0])
    if "month" in s:
        return age / 12.0
    if "week" in s:
        return age / 52.0
    if "day" in s:
        return age / 365.0
    return float(age)


def _drug_keyword(name: str) -> str:
    """Extract the primary drug name keyword from a medication/intervention string."""
    name = str(name).lower().strip()
    # Remove leading spaces and numeric prefixes like "24 HR "
    name = re.sub(r"^\d[\d\s]*hr\s+", "", name)
    # Remove dosage patterns
    name = re.sub(
        r"[\d./]+\s*(mg|ml|mcg|iu|units?|%|actuat|day|pack|tablet|injection"
        r"|oral|capsule|solution|cream|spray|patch|inhaler|mg/ml|mg/actuat)",
        " ", name
    )
    # Split on non-alpha
    words = [w for w in re.split(r"[\s,\-+/\[\]()]+", name)
             if len(w) >= 4 and not w.replace(".", "").replace("/", "").isdigit()]
    if not words:
        return ""
    # Skip generic prefixes
    skip = {"intra", "oral", "drug", "form", "with", "plus", "anti", "solution",
            "extended", "release", "pack", "spray", "cream", "patch"}
    for w in words:
        if w not in skip:
            return w
    return words[0]


def _name_tokens(name: str) -> frozenset:
    """Tokenise a hospital/facility name: drop stopwords and short words."""
    _STOP = {"the","of","and","at","for","in","a","an","is","by",
             "hospital","medical","center","centre","clinic","university",
             "health","care","healthcare","system","institute","foundation",
             "research","general","regional","national","community",
             "services","department","division","college","school"}
    words = re.findall(r"[a-z]+", str(name).lower())
    return frozenset(w for w in words if w not in _STOP and len(w) >= 3)


def _geo_score(patient_state_full: str, trial_states: set) -> float:
    """
    State-level geo feasibility score.
    patient_state_full: full state name e.g. 'Massachusetts'
    trial_states: set of full US state names where trial has facilities
    """
    if not trial_states:
        return 0.5   # no facility data — neutral
    if patient_state_full and patient_state_full in trial_states:
        return 1.0   # trial in same state
    if trial_states:             # trial has US facility but different state
        return 0.75
    return 0.35                  # international only (shouldn't reach here)


def _extract_state(address: str) -> str:
    """Extract full US state name from a patient address string."""
    if not address or address in ("nan", "None", ""):
        return ""
    m = re.search(r"\b([A-Z]{2})\s+\d{5}\b", str(address))
    if m:
        return STATE_ABBREV.get(m.group(1), "")
    return ""


def _compute_features(
    patient_conds: set, patient_age: float, patient_gender: str,
    trial_conds: set, trial_min_age: float, trial_max_age: float,
    trial_gender: str,
    total_patient_conds: int, active_patient_conds: int,
    trial_cond_count: int,
    # pre-computed per-entity lookups
    cond_rarity_map: dict,          # condition → rarity_score
    trial_us_states: set,           # set of US state full-names for this trial
    pat_med_kws: set,               # patient's medication keywords
    trial_drug_kws: set,            # trial's drug intervention keywords
    pat_lab_score: float,           # patient's lab/observation coverage (0–1)
    patient_state_full: str = "",   # patient's US state full name
) -> dict:
    """Compute all 17 soft continuous match features (no hard binary gates)."""

    overlap = len(patient_conds & trial_conds)
    union   = len(patient_conds | trial_conds)

    jaccard             = overlap / union if union > 0 else 0.0
    overlap_ratio_pat   = overlap / len(patient_conds)  if len(patient_conds) > 0  else 0.0
    overlap_ratio_trial = overlap / len(trial_conds)    if len(trial_conds) > 0    else 0.0

    # Condition rarity: rare condition match is stronger signal
    overlap_conds = patient_conds & trial_conds
    if overlap_conds:
        rarity_vals = [cond_rarity_map.get(c, 0.5) for c in overlap_conds]
        condition_rarity_score = float(np.mean(rarity_vals))
    else:
        condition_rarity_score = 0.0

    trial_specificity   = 1.0 / trial_cond_count if trial_cond_count > 0 else 0.0
    condition_burden    = min(total_patient_conds / 10.0, 1.0)
    active_ratio        = active_patient_conds / total_patient_conds if total_patient_conds > 0 else 0.0
    resolved            = max(0, total_patient_conds - active_patient_conds)
    resolved_ratio      = resolved / total_patient_conds if total_patient_conds > 0 else 0.0

    # Age features (continuous)
    age     = patient_age if patient_age and not np.isnan(patient_age) else 50.0
    min_a   = trial_min_age if trial_min_age else 0.0
    max_a   = trial_max_age if trial_max_age else 120.0

    if age < min_a:
        age_distance = (min_a - age) / 100.0
    elif age > max_a:
        age_distance = (age - max_a) / 100.0
    else:
        age_distance = 0.0

    mid    = (min_a + max_a) / 2.0
    half   = (max_a - min_a) / 2.0 if max_a > min_a else 1.0
    age_centered = max(-1.0, min(1.0, (age - mid) / half))

    if min_a <= age <= max_a:
        age_compat = 1.0
    else:
        dist = min(abs(age - min_a), abs(age - max_a))
        age_compat = max(0.0, 1.0 - dist / 30.0)

    # Gender (soft)
    pg = str(patient_gender).upper().strip()
    tg = str(trial_gender).upper().strip()
    if tg in ("ALL", ""):
        gender_compat = 1.0
    elif (pg in ("M", "MALE")   and tg in ("M", "MALE")) or \
         (pg in ("F", "FEMALE") and tg in ("F", "FEMALE")):
        gender_compat = 1.0
    else:
        gender_compat = 0.1

    # Geo feasibility: state-level (same state = 1.0, other US = 0.75, no data = 0.5)
    geo_feasibility = _geo_score(patient_state_full, trial_us_states)

    # Medication compatibility (real: keyword overlap)
    if pat_med_kws and trial_drug_kws:
        m_overlap = len(pat_med_kws & trial_drug_kws)
        m_union   = len(pat_med_kws | trial_drug_kws)
        # Presence of any shared keyword = compatible; jaccard for strength
        med_compat = 0.8 + 0.2 * (m_overlap / m_union) if m_overlap > 0 else 0.4
    else:
        med_compat = 0.5   # neutral when data is missing

    # Data completeness
    data_completeness = sum([
        not np.isnan(age),
        pg != "",
        total_patient_conds > 0,
        min_a is not None,
        tg != "",
    ]) / 5.0

    # Rule-based match score (reference only — NOT a feature, used for labelling)
    match_score = (
        0.35 * overlap_ratio_trial +
        0.25 * overlap_ratio_pat   +
        0.20 * age_compat          +
        0.20 * gender_compat
    ) * 100.0

    return {
        "condition_overlap":        float(overlap),
        "jaccard_similarity":       jaccard,
        "overlap_ratio_trial":      overlap_ratio_trial,
        "overlap_ratio_patient":    overlap_ratio_pat,
        "condition_rarity_score":   condition_rarity_score,
        "trial_specificity":        trial_specificity,
        "condition_burden":         condition_burden,
        "active_ratio":             active_ratio,
        "resolved_ratio":           resolved_ratio,
        "age_distance":             age_distance,
        "age_centered":             age_centered,
        "age_compatibility":        age_compat,
        "gender_compatibility":     gender_compat,
        "geo_feasibility":          geo_feasibility,
        "med_compatibility":        med_compat,
        "lab_availability":         float(pat_lab_score),
        "data_completeness":        data_completeness,
        "match_score":              match_score,
    }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class SecondLifePipeline:
    """
    Loads all data files, trains the eligibility model, and exposes
    match_patient() for the Flask app.
    """

    def __init__(self):
        self.model         = None
        self.scaler        = None
        self.model_metrics = {}

        # DataFrames
        self.patient_conditions_df = None
        self.patient_details_df    = None
        self.trial_studies_df      = None
        self.trial_elig_df         = None
        self.trial_summaries_df    = None
        self.trial_facilities_df   = None

        # Lookup structures built in load()
        self.trial_profiles    = {}   # trial_id → profile dict
        self.cond_to_trials    = {}   # condition → [trial_ids]
        self.overlapping_conds = set()
        self.patient_profiles  = {}   # patient_id → profile dict

        # New real-data lookups
        self.cond_rarity_map        = {}   # condition → rarity score
        self.trial_us_states        = {}   # trial_id → set of US state full names
        self.trial_facility_tokens  = {}   # trial_id → list of frozensets of facility name tokens
        self.trial_drug_keywords    = {}   # trial_id → set of drug keywords
        self.patient_med_keywords   = {}   # patient_id → set of med keywords
        self.patient_lab_score      = {}   # patient_id → lab coverage (0–1)
        self.patient_address_state  = {}   # patient_id → full US state name

        self.stats = {}

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(self):
        print("[pipeline] Loading patient conditions …")
        pc = pd.read_csv(PATIENT_CONDITIONS_PATH)
        pc["condition_lower"] = pc["Condition_Name"].str.lower().str.strip()
        self.patient_conditions_df = pc

        print("[pipeline] Loading patient demographics …")
        pd_df = pd.read_csv(PATIENT_DETAILS_PATH)
        pd_df["Birth_Date"] = pd.to_datetime(pd_df["Birth_Date"], format="%d-%m-%Y", errors="coerce")
        ref = datetime(2024, 1, 1)
        pd_df["Patient_Age"] = ((ref - pd_df["Birth_Date"]).dt.days / 365.25).round()
        pd_df["Gender"] = pd_df["Gender"].str.upper().str.strip()
        self.patient_details_df = pd_df

        if "Address" in pd_df.columns:
            addr_series = pd_df.set_index("Patient_ID")["Address"].dropna()
            state_series = addr_series.apply(lambda a: _extract_state(str(a)))
            self.patient_address_state = {pid: st for pid, st in state_series.items() if st}
            print(f"  Patients with state data: {len(self.patient_address_state):,}")

        print("[pipeline] Loading patient medications …")
        meds = pd.read_csv(PATIENT_MEDICATIONS_PATH,
                           usecols=["Patient_ID", "Medication_Name", "Medication_End_Date"])
        # Keep only active medications (no end date)
        active_meds = meds[meds["Medication_End_Date"].isna()].copy()
        active_meds["kw"] = active_meds["Medication_Name"].apply(_drug_keyword)
        active_meds = active_meds[active_meds["kw"] != ""]
        self.patient_med_keywords = (
            active_meds.groupby("Patient_ID")["kw"].apply(set).to_dict()
        )
        # Fall back: use all meds if no active ones
        all_meds_kw = meds.copy()
        all_meds_kw["kw"] = all_meds_kw["Medication_Name"].apply(_drug_keyword)
        all_meds_kw = all_meds_kw[all_meds_kw["kw"] != ""]
        all_med_map = all_meds_kw.groupby("Patient_ID")["kw"].apply(set).to_dict()
        for pid, kws in all_med_map.items():
            if pid not in self.patient_med_keywords:
                self.patient_med_keywords[pid] = kws
        print(f"  Patients with medication data: {len(self.patient_med_keywords):,}")

        print("[pipeline] Loading patient observations/labs …")
        obs = pd.read_csv(PATIENT_OBSERVATIONS_PATH,
                          usecols=["Patient_ID", "Observation_Name"])
        # Unique lab types per patient, normalised by 20 (typical max)
        lab_counts = obs.groupby("Patient_ID")["Observation_Name"].nunique()
        self.patient_lab_score = (lab_counts / 20.0).clip(0, 1).to_dict()
        print(f"  Patients with observation data: {len(self.patient_lab_score):,}")

        print("[pipeline] Loading trial conditions …")
        tc = pd.read_csv(TRIAL_CONDITIONS_PATH)
        tc["condition_lower"] = tc["Condition_Name_Lower"].str.lower().str.strip()

        print("[pipeline] Loading trial eligibilities …")
        elig = pd.read_csv(TRIAL_ELIGIBILITY_PATH)
        elig.columns = elig.columns.str.strip()
        if "Gender" in elig.columns:
            elig.rename(columns={"Gender": "Sex"}, inplace=True)
        elig["Min_Age"] = elig["Minimum_Age"].apply(_parse_age).fillna(0)
        elig["Max_Age"] = elig["Maximum_Age"].apply(_parse_age).fillna(120)
        elig["Sex"]     = elig["Sex"].fillna("ALL").str.upper().str.strip()
        self.trial_elig_df = elig

        print("[pipeline] Loading trial studies …")
        studies = pd.read_csv(TRIAL_STUDIES_PATH)
        self.trial_studies_df = studies
        print(f"  Total trials: {studies['Trial_ID'].nunique():,}")

        print("[pipeline] Loading trial facilities …")
        try:
            fac = pd.read_csv(TRIAL_FACILITIES_PATH, encoding="utf-8", on_bad_lines="skip")
            self.trial_facilities_df = fac
        except Exception:
            self.trial_facilities_df = pd.DataFrame(
                columns=["Trial_ID", "Facility_City", "Facility_State", "Facility_Country"])

        print("[pipeline] Loading trial summaries …")
        try:
            summaries = pd.read_csv(TRIAL_SUMMARIES_PATH, encoding="utf-8", on_bad_lines="skip")
            self.trial_summaries_df = summaries
        except Exception:
            self.trial_summaries_df = pd.DataFrame(columns=["Trial_ID", "Brief_Summary"])

        # ---- NEW: Trial interventions (for med_compatibility) ----
        print("[pipeline] Loading trial interventions (drug keywords) …")
        interv = pd.read_csv(TRIAL_INTERVENTIONS_PATH,
                             usecols=["Trial_ID", "Intervention_Type", "Intervention_Name"])
        drug_interv = interv[interv["Intervention_Type"] == "DRUG"].copy()
        drug_interv["kw"] = drug_interv["Intervention_Name"].apply(_drug_keyword)
        drug_interv = drug_interv[drug_interv["kw"] != ""]
        self.trial_drug_keywords = (
            drug_interv.groupby("Trial_ID")["kw"].apply(set).to_dict()
        )
        print(f"  Trials with drug intervention data: {len(self.trial_drug_keywords):,}")

        # ---- State-level geo + facility-name index ----
        print("[pipeline] Building trial US state index and facility-name index …")
        fac = self.trial_facilities_df
        if (fac is not None and not fac.empty
                and "Facility_Country" in fac.columns
                and "Facility_State" in fac.columns):
            fac_us = fac[fac["Facility_Country"].str.strip().str.lower()
                         .isin(["united states", "usa", "us"])].copy()
            fac_us["state_clean"] = fac_us["Facility_State"].str.strip()
            fac_us = fac_us[
                fac_us["state_clean"].notna() &
                (fac_us["state_clean"] != "") &
                (fac_us["state_clean"].str.lower() != "nan")
            ]
            self.trial_us_states = (
                fac_us.groupby("Trial_ID")["state_clean"].apply(set).to_dict()
            )
            # Facility-name token sets: trial_id → list of frozensets of significant words
            if "Facility_Name" in fac_us.columns:
                def _tok(name):
                    _STOP = {"the","of","and","at","for","in","a","an","is","by",
                             "hospital","medical","center","centre","clinic","university",
                             "health","care","healthcare","system","institute","foundation",
                             "research","general","regional","national","community",
                             "services","department","division","college","school"}
                    words = re.findall(r"[a-z]+", str(name).lower())
                    return frozenset(w for w in words if w not in _STOP and len(w) >= 3)
                fac_us["name_tokens"] = fac_us["Facility_Name"].apply(_tok)
                self.trial_facility_tokens = (
                    fac_us.groupby("Trial_ID")["name_tokens"].apply(list).to_dict()
                )
            else:
                self.trial_facility_tokens = {}
        else:
            self.trial_us_states = {}
            self.trial_facility_tokens = {}
        print(f"  Trials with US facility state data: {len(self.trial_us_states):,}")
        print(f"  Trials with facility name tokens:   {len(self.trial_facility_tokens):,}")

        # ---- NEW: Trial keywords (extend condition matching bridge) ----
        print("[pipeline] Loading trial keywords …")
        kw_df = pd.read_csv(TRIAL_KEYWORDS_PATH,
                            usecols=["Trial_ID", "Keyword_Name_Lower"])
        kw_df["kw_lower"] = kw_df["Keyword_Name_Lower"].str.lower().str.strip()
        self.trial_keyword_map = kw_df.groupby("Trial_ID")["kw_lower"].apply(set).to_dict()

        # Find overlapping conditions
        patient_cond_set = set(pc["condition_lower"].dropna().unique())
        trial_cond_set   = set(tc["condition_lower"].dropna().unique())
        self.overlapping_conds = patient_cond_set & trial_cond_set
        print(f"  Overlapping conditions (exact): {len(self.overlapping_conds)}")

        # ---- NEW: Condition rarity scores ----
        print("[pipeline] Computing condition rarity scores …")
        cond_trial_counts = tc[tc["condition_lower"].isin(self.overlapping_conds)] \
                              .groupby("condition_lower")["Trial_ID"].nunique().to_dict()
        for cond in self.overlapping_conds:
            n = cond_trial_counts.get(cond, 1)
            self.cond_rarity_map[cond] = 1.0 / math.log2(n + 2)
        # Normalise to 0–1
        max_r = max(self.cond_rarity_map.values()) if self.cond_rarity_map else 1.0
        self.cond_rarity_map = {c: v / max_r for c, v in self.cond_rarity_map.items()}

        # Build trial profiles
        print("[pipeline] Building trial profiles …")
        tc_filtered = tc[tc["condition_lower"].isin(self.overlapping_conds)]
        trial_cond_map = tc_filtered.groupby("Trial_ID")["condition_lower"].apply(set).to_dict()

        elig_idx   = elig.set_index("Trial_ID")
        studies_idx= studies.set_index("Trial_ID")

        active_statuses = {
            "RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION",
            "ACTIVE_NOT_RECRUITING", "UNKNOWN",
        }

        for trial_id, conds in trial_cond_map.items():
            e = elig_idx.loc[trial_id]   if trial_id in elig_idx.index   else None
            s = studies_idx.loc[trial_id] if trial_id in studies_idx.index else None

            # Handle cases where index lookup returns DataFrame (duplicate IDs)
            if isinstance(e, pd.DataFrame): e = e.iloc[0]
            if isinstance(s, pd.DataFrame): s = s.iloc[0]

            min_age  = float(e["Min_Age"])         if e is not None else 0.0
            max_age  = float(e["Max_Age"])         if e is not None else 120.0
            sex      = str(e["Sex"])               if e is not None else "ALL"
            criteria = str(e.get("Eligibility_Criteria", "")) if e is not None else ""

            status   = str(s["Overall_Status"])    if s is not None else "UNKNOWN"
            title    = str(s["Brief_Title"])       if s is not None else trial_id
            phase    = str(s["Phase"])             if s is not None else "N/A"
            start    = str(s.get("Start_Date", "")) if s is not None else ""
            enroll   = s.get("Enrollment", np.nan) if s is not None else np.nan

            self.trial_profiles[trial_id] = {
                "conditions":  conds,
                "min_age":     min_age,
                "max_age":     max_age,
                "sex":         sex,
                "status":      status,
                "is_active":   status in active_statuses,
                "title":       title[:200],
                "phase":       phase,
                "start_date":  start,
                "enrollment":  int(enroll) if pd.notna(enroll) else None,
                "criteria":    criteria[:500],
            }

        # Reverse index: condition → [trial_ids]
        for trial_id, prof in self.trial_profiles.items():
            for cond in prof["conditions"]:
                self.cond_to_trials.setdefault(cond, []).append(trial_id)

        # Extend cond_to_trials with keyword matches
        for trial_id, kws in self.trial_keyword_map.items():
            for kw in kws:
                if kw in self.overlapping_conds and trial_id in self.trial_profiles:
                    self.cond_to_trials.setdefault(kw, [])
                    if trial_id not in self.cond_to_trials[kw]:
                        self.cond_to_trials[kw].append(trial_id)

        print(f"  Trial profiles built: {len(self.trial_profiles):,}")

        # Build patient profiles
        print("[pipeline] Building patient profiles …")
        pat_filtered = pc[pc["condition_lower"].isin(self.overlapping_conds)]
        pat_agg = pat_filtered.groupby("Patient_ID").agg(
            patient_conds  = ("condition_lower", set),
            active_conds   = ("Condition_End_Date", lambda x: x.isna().sum()),
            total_conds    = ("condition_lower", "count"),
        ).reset_index()

        details_idx = pd_df.set_index("Patient_ID")[["Patient_Age", "Gender"]]
        pat_merged  = pat_agg.merge(details_idx, left_on="Patient_ID",
                                    right_index=True, how="inner")
        self.patient_profiles = pat_merged.set_index("Patient_ID").to_dict("index")
        print(f"  Patient profiles built: {len(self.patient_profiles):,}")

        self.stats = {
            "total_patients":                pd_df["Patient_ID"].nunique(),
            "total_trials":                  studies["Trial_ID"].nunique(),
            "recruiting_trials":             int((studies["Overall_Status"] == "RECRUITING").sum()),
            "overlapping_conditions":        len(self.overlapping_conds),
            "matched_trials":                len(self.trial_profiles),
            "patient_profiles_with_matches": len(self.patient_profiles),
            "patients_with_medication_data": len(self.patient_med_keywords),
            "patients_with_lab_data":        len(self.patient_lab_score),
            "trials_with_geo_data":          len(self.trial_us_states),
            "trials_with_drug_data":         len(self.trial_drug_keywords),
            "_conditions":                   sorted(self.overlapping_conds),
        }
        return self

    # ------------------------------------------------------------------
    # Train
    # ------------------------------------------------------------------

    def train(self, n_patients: int = 3000, n_trials_per_patient: int = 30,
              random_state: int = 42):
        if MODEL_CACHE.exists():
            print("[pipeline] Loading cached model …")
            with open(MODEL_CACHE, "rb") as f:
                cached = pickle.load(f)
            self.model          = cached["model"]
            self.scaler         = cached["scaler"]
            self.model_metrics  = cached["metrics"]
            self.overlapping_conds = cached.get("overlapping_conds", self.overlapping_conds)
            print(f"  Cached model loaded — AUC-ROC = {self.model_metrics.get('auroc', 'N/A'):.4f}")
            return self

        print(f"[pipeline] Generating training pairs (n_patients={n_patients}) …")
        rng = np.random.default_rng(random_state)

        all_pids = list(self.patient_profiles.keys())
        sampled_pids = rng.choice(all_pids, size=min(n_patients, len(all_pids)), replace=False)

        active_tids = [tid for tid, p in self.trial_profiles.items() if p["is_active"]]
        if not active_tids:
            active_tids = list(self.trial_profiles.keys())

        rows = []
        for pid in sampled_pids:
            prof       = self.patient_profiles[pid]
            pat_conds  = prof["patient_conds"]
            pat_age    = float(prof["Patient_Age"]) if pd.notna(prof["Patient_Age"]) else 50.0
            pat_gender = str(prof["Gender"])        if pd.notna(prof["Gender"])       else "M"
            total_c    = int(prof["total_conds"])
            active_c   = int(prof["active_conds"])

            pat_med_kws  = self.patient_med_keywords.get(pid, set())
            pat_lab      = self.patient_lab_score.get(pid, 0.3)
            pat_state    = self.patient_address_state.get(pid, "")

            # Positive candidates: share at least one condition
            candidate_tids = set()
            for c in pat_conds:
                candidate_tids.update(self.cond_to_trials.get(c, []))

            if not candidate_tids:
                continue

            # Negative candidates: random trials with no condition overlap
            neg_tids = set(rng.choice(active_tids,
                                       size=min(10, len(active_tids)),
                                       replace=False).tolist())

            candidate_list = list(candidate_tids)
            rng.shuffle(candidate_list)
            candidate_list = candidate_list[:n_trials_per_patient]
            candidate_list += [t for t in neg_tids if t not in candidate_tids]

            for tid in candidate_list:
                if tid not in self.trial_profiles:
                    continue
                tp = self.trial_profiles[tid]

                feats = _compute_features(
                    pat_conds, pat_age, pat_gender,
                    tp["conditions"], tp["min_age"], tp["max_age"], tp["sex"],
                    total_c, active_c, len(tp["conditions"]),
                    self.cond_rarity_map,
                    self.trial_us_states.get(tid, set()),
                    pat_med_kws,
                    self.trial_drug_keywords.get(tid, set()),
                    pat_lab,
                    patient_state_full=pat_state,
                )
                feats["Patient_ID"] = pid
                feats["Trial_ID"]   = tid
                rows.append(feats)

        df = pd.DataFrame(rows)
        print(f"  Training pairs generated: {len(df):,}")

        # Rule-based label — uses all 6 main signals, 15% noise for realism
        import hashlib
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
            h = int(hashlib.md5(
                    f"{row['Patient_ID']}_{row['Trial_ID']}".encode()
                ).hexdigest()[:8], 16)
            if (h % 1000) / 1000 < 0.15:
                base = 1 - base
            return base

        df["label"] = df.apply(_label, axis=1)

        X      = df[FEATURE_COLS].fillna(0)
        y      = df["label"].values
        groups = df["Patient_ID"].values

        gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=random_state)
        train_idx, test_idx = next(gss.split(X, y, groups))

        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        g_train         = groups[train_idx]

        print(f"  Train: {len(X_train):,} | Test: {len(X_test):,} | Positive rate: {y_train.mean()*100:.1f}%")

        scaler     = StandardScaler()
        X_train_sc = scaler.fit_transform(X_train)

        print("[pipeline] Training Random Forest (n_estimators=200, max_depth=12) …")
        rf = RandomForestClassifier(
            n_estimators=200, max_depth=12, min_samples_split=10,
            class_weight="balanced", random_state=random_state, n_jobs=-1,
        )
        rf.fit(X_train, y_train)

        # Calibrate probabilities
        cal = CalibratedClassifierCV(rf, cv=3, method="isotonic")
        cal.fit(X_train, y_train)

        y_pred = cal.predict(X_test)
        y_prob = cal.predict_proba(X_test)[:, 1]

        metrics = {
            "accuracy":      accuracy_score(y_test, y_pred),
            "precision":     precision_score(y_test, y_pred, zero_division=0),
            "recall":        recall_score(y_test, y_pred, zero_division=0),
            "f1":            f1_score(y_test, y_pred, zero_division=0),
            "auroc":         roc_auc_score(y_test, y_prob),
            "brier":         brier_score_loss(y_test, y_prob),
            "avg_precision": average_precision_score(y_test, y_prob),
            "train_size":    len(X_train),
            "test_size":     len(X_test),
            "positive_rate": float(y_train.mean()),
        }

        cv = GroupKFold(n_splits=5)
        cv_scores = cross_val_score(rf, X_train, y_train, cv=cv,
                                     groups=g_train, scoring="roc_auc")
        metrics["cv_auroc_mean"] = float(cv_scores.mean())
        metrics["cv_auroc_std"]  = float(cv_scores.std())
        metrics["feature_importance"] = dict(zip(FEATURE_COLS, rf.feature_importances_))

        print(f"  Accuracy : {metrics['accuracy']*100:.1f}%")
        print(f"  AUC-ROC  : {metrics['auroc']:.4f}")
        print(f"  CV AUC   : {metrics['cv_auroc_mean']:.4f} ± {metrics['cv_auroc_std']:.4f}")

        self.model         = cal
        self.scaler        = scaler
        self.model_metrics = metrics

        with open(MODEL_CACHE, "wb") as f:
            pickle.dump({
                "model":             cal,
                "scaler":            scaler,
                "metrics":           metrics,
                "overlapping_conds": self.overlapping_conds,
            }, f)
        print("[pipeline] Model saved to cache.")
        return self

    # ------------------------------------------------------------------
    # Match
    # ------------------------------------------------------------------

    def match_patient(self, conditions: list, age: float, gender: str,
                      top_k: int = 20, active_only: bool = True,
                      patient_id: str = None, address: str = "") -> list:
        if self.model is None:
            raise RuntimeError("Model not trained. Call .train() first.")

        input_conds   = {c.lower().strip() for c in conditions}
        matched_conds = input_conds & self.overlapping_conds
        if not matched_conds:
            return []

        # Candidate trials
        candidate_tids = set()
        for c in matched_conds:
            candidate_tids.update(self.cond_to_trials.get(c, []))
        if not candidate_tids:
            return []

        total_c  = len(input_conds)
        active_c = int(total_c * 0.7)
        gender   = str(gender).upper().strip()

        pat_med_kws = self.patient_med_keywords.get(patient_id, set()) if patient_id else set()
        pat_lab     = self.patient_lab_score.get(patient_id, 0.3)     if patient_id else 0.3

        # State-level geo: prefer provided address, fall back to Synthea lookup
        patient_state_full = _extract_state(address) if address else ""
        if not patient_state_full and patient_id:
            patient_state_full = self.patient_address_state.get(patient_id, "")

        rows = []
        for tid in candidate_tids:
            if tid not in self.trial_profiles:
                continue
            tp = self.trial_profiles[tid]
            if active_only and not tp["is_active"]:
                continue

            feats = _compute_features(
                matched_conds, age, gender,
                tp["conditions"], tp["min_age"], tp["max_age"], tp["sex"],
                total_c, active_c, len(tp["conditions"]),
                self.cond_rarity_map,
                self.trial_us_states.get(tid, set()),
                pat_med_kws,
                self.trial_drug_keywords.get(tid, set()),
                pat_lab,
                patient_state_full=patient_state_full,
            )
            feats["Trial_ID"] = tid
            rows.append(feats)

        if not rows:
            return []

        df = pd.DataFrame(rows)
        X  = df[FEATURE_COLS].fillna(0)

        probs = self.model.predict_proba(X)[:, 1]
        df["eligibility_probability"] = probs
        df["combined_score"] = 0.6 * probs + 0.4 * (df["match_score"] / 100.0)

        df_sorted = df.sort_values("combined_score", ascending=False).head(top_k)

        results = []
        for _, row in df_sorted.iterrows():
            tid  = row["Trial_ID"]
            tp   = self.trial_profiles[tid]
            overlap_conds = sorted(matched_conds & tp["conditions"])

            summary = ""
            if self.trial_summaries_df is not None and not self.trial_summaries_df.empty:
                s_rows = self.trial_summaries_df[self.trial_summaries_df["Trial_ID"] == tid]
                if not s_rows.empty:
                    col = "Brief_Summary" if "Brief_Summary" in s_rows.columns else s_rows.columns[-1]
                    summary = str(s_rows.iloc[0][col])[:400]

            location = ""
            facility_name = ""
            n_sites  = 0
            if self.trial_facilities_df is not None and not self.trial_facilities_df.empty:
                f_rows = self.trial_facilities_df[self.trial_facilities_df["Trial_ID"] == tid]
                if not f_rows.empty:
                    # Prefer US sites first, fall back to first row
                    us_rows = f_rows[f_rows.get("Facility_Country", pd.Series(dtype=str))
                                     .str.strip().str.lower()
                                     .isin(["united states", "usa", "us"])] \
                              if "Facility_Country" in f_rows.columns else pd.DataFrame()
                    r = us_rows.iloc[0] if not us_rows.empty else f_rows.iloc[0]
                    parts = [str(r.get(c, "")) for c in
                             ["Facility_City", "Facility_State", "Facility_Country"]
                             if str(r.get(c, "")).strip() not in ("", "nan")]
                    location = ", ".join(parts)
                    if "Facility_Name" in r.index:
                        fn = str(r.get("Facility_Name", "")).strip()
                        facility_name = fn if fn not in ("", "nan") else ""
                    n_sites  = len(f_rows)

            results.append({
                "trial_id":                tid,
                "title":                   tp["title"],
                "phase":                   tp["phase"],
                "status":                  tp["status"],
                "min_age":                 int(tp["min_age"]),
                "max_age":                 int(tp["max_age"]),
                "sex":                     tp["sex"],
                "enrollment":              tp["enrollment"],
                "start_date":              tp["start_date"],
                "eligibility_probability": round(float(row["eligibility_probability"]) * 100, 1),
                "match_score":             round(float(row["match_score"]), 1),
                "combined_score":          round(float(row["combined_score"]) * 100, 1),
                "jaccard_similarity":      round(float(row["jaccard_similarity"]), 3),
                "age_compatibility":       round(float(row["age_compatibility"]) * 100, 1),
                "gender_compatibility":    round(float(row["gender_compatibility"]) * 100, 1),
                "geo_feasibility":         round(float(row["geo_feasibility"]) * 100, 1),
                "med_compatibility":       round(float(row["med_compatibility"]) * 100, 1),
                "condition_rarity_score":  round(float(row["condition_rarity_score"]), 3),
                "overlap_conditions":      overlap_conds,
                "trial_conditions":        sorted(tp["conditions"]),
                "criteria":                tp["criteria"],
                "summary":                 summary,
                "location":                location,
                "facility_name":           facility_name,
                "n_sites":                 n_sites,
            })

        return results

    # ------------------------------------------------------------------
    # Hospital trial dashboard
    # ------------------------------------------------------------------

    def trials_for_hospital(self, hospital_name: str, location: str,
                             research_conditions: list, top_k: int = 20) -> list:
        """
        Return trials relevant to this hospital using 3-tier logic (reversed from
        hospitals-for-trial): Tier 1 = Jaccard name match, Tier 2 = same state,
        Tier 3 = research-condition overlap.
        """
        h_tokens = _name_tokens(hospital_name)

        m = re.search(r",\s*([A-Z]{2})\s*$", str(location).strip())
        h_state = STATE_ABBREV.get(m.group(1), "") if m else ""
        rc_set  = {r.lower().strip() for r in (research_conditions or []) if r}

        collected: list[tuple[str, int]] = []
        seen: set = set()

        # Tier 1: facility-name Jaccard ≥ 0.25
        for trial_id, fac_list in self.trial_facility_tokens.items():
            if trial_id not in self.trial_profiles:
                continue
            if not self.trial_profiles[trial_id].get("is_active", False):
                continue
            best = 0.0
            for ft in fac_list:
                if h_tokens and ft:
                    inter = len(h_tokens & ft)
                    union = len(h_tokens | ft)
                    s = inter / union if union else 0.0
                    if s > best:
                        best = s
            if best >= 0.25:
                collected.append((trial_id, 1))
                seen.add(trial_id)

        # Tier 2: same state — cap at 2×top_k additional to avoid runaway
        if h_state and len(collected) < top_k:
            t2_cap = top_k * 2
            t2_added = 0
            for trial_id, states in self.trial_us_states.items():
                if t2_added >= t2_cap:
                    break
                if trial_id in seen or trial_id not in self.trial_profiles:
                    continue
                if not self.trial_profiles[trial_id].get("is_active", False):
                    continue
                if h_state in states:
                    collected.append((trial_id, 2))
                    seen.add(trial_id)
                    t2_added += 1

        # Tier 3: research-condition overlap — fill up to top_k
        if rc_set and len(collected) < top_k:
            t3_cap = top_k * 2
            t3_added = 0
            for cond in rc_set:
                for trial_id in self.cond_to_trials.get(cond, []):
                    if t3_added >= t3_cap:
                        break
                    if trial_id in seen or trial_id not in self.trial_profiles:
                        continue
                    if not self.trial_profiles[trial_id].get("is_active", False):
                        continue
                    collected.append((trial_id, 3))
                    seen.add(trial_id)
                    t3_added += 1

        collected.sort(key=lambda x: x[1])
        collected = collected[:top_k]

        _REASON = {1: "verified trial site", 2: "trial in your state",
                   3: "matches your research conditions"}

        output = []
        for trial_id, tier in collected:
            tp = self.trial_profiles[trial_id]

            summary = ""
            if self.trial_summaries_df is not None and not self.trial_summaries_df.empty:
                s_rows = self.trial_summaries_df[self.trial_summaries_df["Trial_ID"] == trial_id]
                if not s_rows.empty:
                    col = "Brief_Summary" if "Brief_Summary" in s_rows.columns else s_rows.columns[-1]
                    summary = str(s_rows.iloc[0][col])[:300]

            location_str = facility_name = ""
            n_sites = 0
            if self.trial_facilities_df is not None and not self.trial_facilities_df.empty:
                f_rows = self.trial_facilities_df[self.trial_facilities_df["Trial_ID"] == trial_id]
                if not f_rows.empty:
                    n_sites = len(f_rows)
                    us_rows = f_rows[f_rows["Facility_Country"].str.strip().str.lower()
                                     .isin(["united states", "usa", "us"])] \
                              if "Facility_Country" in f_rows.columns else pd.DataFrame()
                    r = us_rows.iloc[0] if not us_rows.empty else f_rows.iloc[0]
                    parts = [str(r.get(c, "")) for c in
                             ["Facility_City", "Facility_State", "Facility_Country"]
                             if str(r.get(c, "")).strip() not in ("", "nan")]
                    location_str = ", ".join(parts)
                    if "Facility_Name" in r.index:
                        fn = str(r.get("Facility_Name", "")).strip()
                        facility_name = fn if fn not in ("", "nan") else ""

            output.append({
                "trial_id":     trial_id,
                "title":        tp["title"],
                "phase":        tp["phase"],
                "status":       tp["status"],
                "min_age":      int(tp["min_age"]),
                "max_age":      int(tp["max_age"]),
                "sex":          tp["sex"],
                "enrollment":   tp["enrollment"],
                "conditions":   sorted(tp["conditions"]),
                "summary":      summary,
                "location":     location_str,
                "facility_name": facility_name,
                "n_sites":      n_sites,
                "match_tier":   tier,
                "match_reason": _REASON[tier],
            })

        return output

    # ------------------------------------------------------------------
    # Patient lookup
    # ------------------------------------------------------------------

    def get_patient(self, patient_id: str):
        if patient_id not in self.patient_profiles:
            return None
        prof = self.patient_profiles[patient_id]
        det  = self.patient_details_df[self.patient_details_df["Patient_ID"] == patient_id]
        if det.empty:
            return None
        row = det.iloc[0]

        all_conds = sorted(
            self.patient_conditions_df[
                self.patient_conditions_df["Patient_ID"] == patient_id
            ]["Condition_Name"].dropna().unique().tolist()
        )

        return {
            "patient_id":            patient_id,
            "age":                   int(prof["Patient_Age"]) if pd.notna(prof["Patient_Age"]) else None,
            "gender":                str(prof["Gender"]),
            "first_name":            str(row.get("First_Name", "")),
            "last_name":             str(row.get("Last_Name", "")),
            "race":                  str(row.get("Race", "")),
            "ethnicity":             str(row.get("Ethnicity", "")),
            "address":               str(row.get("Address", "")),
            "conditions":            all_conds,
            "matching_conditions":   sorted(prof["patient_conds"]),
            "medications":           sorted(self.patient_med_keywords.get(patient_id, set())),
            "has_lab_data":          patient_id in self.patient_lab_score,
        }

    def search_patients(self, query: str, limit: int = 20) -> list:
        query_l = query.lower().strip()
        results = []
        for pid, prof in self.patient_profiles.items():
            if query_l in pid.lower():
                det = self.patient_details_df[self.patient_details_df["Patient_ID"] == pid]
                if not det.empty:
                    r = det.iloc[0]
                    results.append({
                        "patient_id":   pid,
                        "age":          int(prof["Patient_Age"]) if pd.notna(prof["Patient_Age"]) else None,
                        "gender":       str(prof["Gender"]),
                        "first_name":   str(r.get("First_Name", "")),
                        "last_name":    str(r.get("Last_Name", "")),
                        "n_conditions": len(prof["patient_conds"]),
                    })
                if len(results) >= limit:
                    break
        return results

    # ------------------------------------------------------------------
    # MIMIC Validation
    # ------------------------------------------------------------------

    def _map_icd_to_overlapping(self, icd_long_titles: list) -> list:
        matched = set()
        for title in icd_long_titles:
            t = title.lower().strip()
            if t in self.overlapping_conds:
                matched.add(t)
                continue
            for cond in self.overlapping_conds:
                if cond in t or t in cond:
                    matched.add(cond)
                    break
            t_words = set(t.split())
            for cond in self.overlapping_conds:
                c_words  = set(cond.split())
                shorter  = min(len(t_words), len(c_words))
                if shorter > 0 and len(t_words & c_words) / shorter >= 0.75:
                    matched.add(cond)
        return list(matched)

    def validate_mimic(self) -> list:
        print("[pipeline] Running MIMIC-IV validation …")
        patients  = pd.read_csv(MIMIC_PATIENTS_PATH)
        diagnoses = pd.read_csv(MIMIC_DIAGNOSES_PATH)
        icd_dict  = pd.read_csv(MIMIC_ICD_DICT_PATH)

        icd_map = icd_dict.set_index(["icd_code", "icd_version"])["long_title"].to_dict()
        diagnoses["condition_name"] = diagnoses.apply(
            lambda r: icd_map.get((r["icd_code"], r["icd_version"]),
                                   str(r["icd_code"])).lower(), axis=1
        )

        results = []
        for _, pat in patients.iterrows():
            sid    = int(pat["subject_id"])
            age    = float(pat["anchor_age"])
            gender = "M" if pat["gender"] == "M" else "F"

            raw_conds    = diagnoses[diagnoses["subject_id"] == sid]["condition_name"].dropna().unique().tolist()
            mapped_conds = self._map_icd_to_overlapping(raw_conds)
            all_conds    = list(set(raw_conds + mapped_conds))

            matches = self.match_patient(all_conds, age, gender, top_k=5)

            results.append({
                "subject_id":         sid,
                "age":                int(age),
                "gender":             gender,
                "n_conditions":       len(raw_conds),
                "conditions":         raw_conds[:5],
                "mapped_conditions":  mapped_conds[:5],
                "n_matches":          len(matches),
                "top_match":          matches[0] if matches else None,
            })
        return results

    # ------------------------------------------------------------------
    # Autocomplete
    # ------------------------------------------------------------------

    def condition_autocomplete(self, query: str, limit: int = 15) -> list:
        q = query.lower().strip()
        return sorted([c for c in self.overlapping_conds if q in c])[:limit]
