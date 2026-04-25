"""
Second Life — SQLite database layer
Handles patient accounts, hospital accounts, trial interests, and connections.
"""

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "secondlife.db"

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
_SCHEMA = """
CREATE TABLE IF NOT EXISTS patient_accounts (
    id              TEXT PRIMARY KEY,
    username        TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    synthea_id      TEXT,
    first_name      TEXT,
    last_name       TEXT,
    dob             TEXT,
    gender          TEXT,
    address         TEXT,
    conditions      TEXT DEFAULT '[]',
    medications     TEXT DEFAULT '[]',
    documents       TEXT DEFAULT '[]',
    open_to_trials  INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS hospital_accounts (
    id                  TEXT PRIMARY KEY,
    username            TEXT UNIQUE NOT NULL,
    password_hash       TEXT NOT NULL,
    hospital_name       TEXT NOT NULL,
    location            TEXT,
    research_conditions TEXT DEFAULT '[]',
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS patient_trial_interests (
    id          TEXT PRIMARY KEY,
    patient_id  TEXT NOT NULL,
    trial_id    TEXT NOT NULL,
    trial_title TEXT,
    match_score REAL,
    status      TEXT DEFAULT 'interested',
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(patient_id, trial_id)
);

CREATE TABLE IF NOT EXISTS connections (
    id              TEXT PRIMARY KEY,
    patient_id      TEXT NOT NULL,
    hospital_id     TEXT NOT NULL,
    trial_id        TEXT,
    trial_title     TEXT,
    initiated_by    TEXT DEFAULT 'patient',
    status          TEXT DEFAULT 'pending',
    message         TEXT,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _row_to_dict(row) -> dict:
    if row is None:
        return None
    d = dict(row)
    for k in ("conditions", "medications", "documents", "research_conditions"):
        if k in d and isinstance(d[k], str):
            try:
                d[k] = json.loads(d[k])
            except Exception:
                d[k] = []
    return d


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

def init_db():
    with _conn() as c:
        c.executescript(_SCHEMA)
    _seed_demo_data()


def _seed_demo_data():
    """Seed demo hospital and patient accounts if not already present."""
    with _conn() as c:
        # Demo hospitals
        hospitals = [
            ("mgh", "mgh123", "Massachusetts General Hospital", "Boston, MA",
             ["hypertension", "diabetes", "cardiac arrest", "stroke"]),
            ("cleveland", "clinic123", "Cleveland Clinic", "Cleveland, OH",
             ["coronary artery disease", "myocardial infarction", "heart failure"]),
            ("jhopkins", "johns123", "Johns Hopkins Hospital", "Baltimore, MD",
             ["cancer", "non-small cell lung cancer", "malignant tumor of colon"]),
        ]
        for uname, pwd, name, loc, conds in hospitals:
            existing = c.execute(
                "SELECT id FROM hospital_accounts WHERE username=?", (uname,)
            ).fetchone()
            if not existing:
                c.execute(
                    "INSERT INTO hospital_accounts VALUES (?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), uname, _hash(pwd), name, loc,
                     json.dumps(conds), datetime.now().isoformat())
                )

        # Demo patient accounts (pre-linked to Synthea IDs)
        # These are real UUIDs from the dataset with known interesting conditions
        patients = [
            ("john_doe",  "pass123", None, "John",   "Doe",   "1965-03-12", "M",
             "123 Main St Boston MA 02101 US",
             ["hypertension", "diabetes", "myocardial infarction"],
             ["metformin", "lisinopril"]),
            ("jane_smith","pass123", None, "Jane",   "Smith", "1978-07-22", "F",
             "456 Oak Ave Cambridge MA 02139 US",
             ["asthma", "atopic dermatitis", "seasonal allergic rhinitis"],
             ["albuterol", "fluticasone"]),
            ("bob_jones", "pass123", None, "Robert", "Jones", "1955-11-05", "M",
             "789 Pine Rd Cleveland OH 44106 US",
             ["coronary artery disease", "hypertension", "chronic pain"],
             ["atorvastatin", "aspirin"]),
        ]
        for uname, pwd, syn_id, fn, ln, dob, gend, addr, conds, meds in patients:
            existing = c.execute(
                "SELECT id FROM patient_accounts WHERE username=?", (uname,)
            ).fetchone()
            if not existing:
                c.execute(
                    """INSERT INTO patient_accounts
                       (id,username,password_hash,synthea_id,first_name,last_name,
                        dob,gender,address,conditions,medications,open_to_trials,created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,0,?)""",
                    (str(uuid.uuid4()), uname, _hash(pwd), syn_id, fn, ln,
                     dob, gend, addr,
                     json.dumps(conds), json.dumps(meds),
                     datetime.now().isoformat())
                )
        c.commit()


# ---------------------------------------------------------------------------
# Patient CRUD
# ---------------------------------------------------------------------------

def create_patient(username, password, first_name="", last_name="",
                   dob="", gender="", address="", synthea_id=None) -> dict | None:
    pid = str(uuid.uuid4())
    try:
        with _conn() as c:
            c.execute(
                """INSERT INTO patient_accounts
                   (id,username,password_hash,synthea_id,first_name,last_name,
                    dob,gender,address,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (pid, username, _hash(password), synthea_id,
                 first_name, last_name, dob, gender, address,
                 datetime.now().isoformat())
            )
            c.commit()
        return get_patient_by_id(pid)
    except sqlite3.IntegrityError:
        return None   # username taken


def get_patient_by_id(pid: str) -> dict | None:
    with _conn() as c:
        return _row_to_dict(c.execute(
            "SELECT * FROM patient_accounts WHERE id=?", (pid,)
        ).fetchone())


def get_patient_by_username(username: str) -> dict | None:
    with _conn() as c:
        return _row_to_dict(c.execute(
            "SELECT * FROM patient_accounts WHERE username=?", (username,)
        ).fetchone())


def authenticate_patient(username: str, password: str) -> dict | None:
    p = get_patient_by_username(username)
    if p and p["password_hash"] == _hash(password):
        return p
    return None


def update_patient_profile(pid: str, **kwargs):
    allowed = {"first_name", "last_name", "dob", "gender", "address",
               "conditions", "medications", "documents", "open_to_trials", "synthea_id"}
    fields, vals = [], []
    for k, v in kwargs.items():
        if k in allowed:
            fields.append(f"{k}=?")
            vals.append(json.dumps(v) if isinstance(v, (list, dict)) else v)
    if not fields:
        return
    vals.append(pid)
    with _conn() as c:
        c.execute(f"UPDATE patient_accounts SET {', '.join(fields)} WHERE id=?", vals)
        c.commit()


# ---------------------------------------------------------------------------
# Hospital CRUD
# ---------------------------------------------------------------------------

def create_hospital(username, password, hospital_name, location="",
                    research_conditions=None) -> dict | None:
    hid = str(uuid.uuid4())
    try:
        with _conn() as c:
            c.execute(
                """INSERT INTO hospital_accounts
                   (id,username,password_hash,hospital_name,location,research_conditions,created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (hid, username, _hash(password), hospital_name, location,
                 json.dumps(research_conditions or []),
                 datetime.now().isoformat())
            )
            c.commit()
        return get_hospital_by_id(hid)
    except sqlite3.IntegrityError:
        return None


def get_hospital_by_id(hid: str) -> dict | None:
    with _conn() as c:
        return _row_to_dict(c.execute(
            "SELECT * FROM hospital_accounts WHERE id=?", (hid,)
        ).fetchone())


def get_hospital_by_username(username: str) -> dict | None:
    with _conn() as c:
        return _row_to_dict(c.execute(
            "SELECT * FROM hospital_accounts WHERE username=?", (username,)
        ).fetchone())


def authenticate_hospital(username: str, password: str) -> dict | None:
    h = get_hospital_by_username(username)
    if h and h["password_hash"] == _hash(password):
        return h
    return None


def get_all_hospitals() -> list:
    with _conn() as c:
        rows = c.execute(
            "SELECT id, hospital_name, location, research_conditions FROM hospital_accounts"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Trial Interests
# ---------------------------------------------------------------------------

def save_trial_interest(patient_id, trial_id, trial_title, match_score):
    iid = str(uuid.uuid4())
    with _conn() as c:
        c.execute(
            """INSERT OR REPLACE INTO patient_trial_interests
               (id,patient_id,trial_id,trial_title,match_score,status,created_at)
               VALUES (?,?,?,?,?,'interested',?)""",
            (iid, patient_id, trial_id, trial_title[:200],
             match_score, datetime.now().isoformat())
        )
        c.commit()


def get_patient_interests(patient_id: str) -> list:
    with _conn() as c:
        rows = c.execute(
            """SELECT * FROM patient_trial_interests
               WHERE patient_id=? ORDER BY match_score DESC""",
            (patient_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def withdraw_interest(patient_id, trial_id):
    with _conn() as c:
        c.execute(
            """UPDATE patient_trial_interests SET status='withdrawn'
               WHERE patient_id=? AND trial_id=?""",
            (patient_id, trial_id)
        )
        c.commit()


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------

def create_connection(patient_id, hospital_id, trial_id, trial_title,
                      initiated_by="patient", message="") -> dict:
    cid = str(uuid.uuid4())
    with _conn() as c:
        c.execute(
            """INSERT INTO connections
               (id,patient_id,hospital_id,trial_id,trial_title,
                initiated_by,status,message,created_at)
               VALUES (?,?,?,?,?,?,  'pending',?,?)""",
            (cid, patient_id, hospital_id, trial_id, trial_title[:200],
             initiated_by, message, datetime.now().isoformat())
        )
        c.commit()
    return get_connection(cid)


def get_connection(cid: str) -> dict | None:
    with _conn() as c:
        return _row_to_dict(c.execute(
            "SELECT * FROM connections WHERE id=?", (cid,)
        ).fetchone())


def get_patient_connections(patient_id: str) -> list:
    with _conn() as c:
        rows = c.execute(
            """SELECT c.*, h.hospital_name, h.location as hospital_location
               FROM connections c
               JOIN hospital_accounts h ON c.hospital_id=h.id
               WHERE c.patient_id=? ORDER BY c.created_at DESC""",
            (patient_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_hospital_connections(hospital_id: str) -> list:
    with _conn() as c:
        rows = c.execute(
            """SELECT c.*,
                      p.first_name, p.last_name, p.gender, p.dob,
                      p.conditions, p.address
               FROM connections c
               JOIN patient_accounts p ON c.patient_id=p.id
               WHERE c.hospital_id=? ORDER BY c.created_at DESC""",
            (hospital_id,)
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        for k in ("conditions",):
            if isinstance(d.get(k), str):
                try:
                    d[k] = json.loads(d[k])
                except Exception:
                    d[k] = []
        result.append(d)
    return result


def update_connection_status(cid: str, status: str):
    with _conn() as c:
        c.execute("UPDATE connections SET status=? WHERE id=?", (status, cid))
        c.commit()


def get_open_patients_for_hospital(hospital_id: str, condition_filter: str = "") -> list:
    """
    Returns patients who are open_to_trials=1 and have the given condition.
    Excludes patients already connected to this hospital.
    """
    with _conn() as c:
        rows = c.execute(
            """SELECT id, first_name, last_name, gender, dob, address, conditions
               FROM patient_accounts
               WHERE open_to_trials=1""",
        ).fetchall()

    result = []
    cf = condition_filter.lower().strip()
    for r in rows:
        d = dict(r)
        try:
            d["conditions"] = json.loads(d["conditions"]) if isinstance(d["conditions"], str) else d["conditions"]
        except Exception:
            d["conditions"] = []

        if cf and not any(cf in c.lower() for c in d["conditions"]):
            continue
        result.append(d)
    return result
