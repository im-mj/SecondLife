"""
Second Life — SQLite database layer
Handles patient accounts, hospital accounts, trial interests, and connections.
"""

import csv
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "secondlife.db"
PATIENT_DETAILS_PATH = BASE_DIR / "Final Patients Synthea Data" / "patients_details.csv"
PATIENT_CONDITIONS_PATH = BASE_DIR / "Final Patients Synthea Data" / "final_patients_conditions.csv"
PATIENT_MEDICATIONS_PATH = BASE_DIR / "Final Patients Synthea Data" / "patients_medications.csv"
DATASET_PATIENT_SEED_COUNT = 20

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
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(patient_id, hospital_id, trial_id)
);

CREATE TABLE IF NOT EXISTS connection_messages (
    id              TEXT PRIMARY KEY,
    connection_id   TEXT NOT NULL,
    sender_role     TEXT NOT NULL,
    sender_id       TEXT NOT NULL,
    body            TEXT NOT NULL,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    is_read         INTEGER DEFAULT 0
);
"""

# Run after schema to add constraint to pre-existing DBs that lack it
_POST_SCHEMA = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_conn_unique
    ON connections(patient_id, hospital_id, COALESCE(trial_id, ''));
CREATE INDEX IF NOT EXISTS idx_msgs_conn
    ON connection_messages(connection_id, created_at);
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
        try:
            c.executescript(_POST_SCHEMA)
        except Exception:
            pass  # index may already exist with different definition
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

        # Demo patient accounts
        patients = [
            ("john_doe",   "pass123", None, "John",   "Doe",    "1965-03-12", "M",
             "123 Main St Boston MA 02101 US",
             ["hypertension", "diabetes", "myocardial infarction"],
             ["metformin", "lisinopril"], 1),
            ("jane_smith", "pass123", None, "Jane",   "Smith",  "1978-07-22", "F",
             "456 Oak Ave Cambridge MA 02139 US",
             ["asthma", "atopic dermatitis", "seasonal allergic rhinitis"],
             ["albuterol", "fluticasone"], 1),
            ("bob_jones",  "pass123", None, "Robert", "Jones",  "1955-11-05", "M",
             "789 Pine Rd Cleveland OH 44106 US",
             ["coronary artery disease", "hypertension", "chronic pain"],
             ["atorvastatin", "aspirin"], 1),
            ("alice_brown","pass123", None, "Alice",  "Brown",  "1972-06-14", "F",
             "101 Elm St Baltimore MD 21201 US",
             ["non-small cell lung cancer", "stroke"],
             ["erlotinib"], 1),
            ("david_chen", "pass123", None, "David",  "Chen",   "1948-09-30", "M",
             "202 Oak Blvd Chicago IL 60601 US",
             ["diabetes", "osteoporosis", "coronary artery disease"],
             ["insulin", "alendronate"], 1),
        ]
        for uname, pwd, syn_id, fn, ln, dob, gend, addr, conds, meds, open_trials in patients:
            existing = c.execute(
                "SELECT id FROM patient_accounts WHERE username=?", (uname,)
            ).fetchone()
            if not existing:
                c.execute(
                    """INSERT INTO patient_accounts
                       (id,username,password_hash,synthea_id,first_name,last_name,
                        dob,gender,address,conditions,medications,open_to_trials,created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (str(uuid.uuid4()), uname, _hash(pwd), syn_id, fn, ln,
                     dob, gend, addr,
                     json.dumps(conds), json.dumps(meds), open_trials,
                     datetime.now().isoformat())
                )
            else:
                # Ensure existing demo patients are open_to_trials=1
                c.execute(
                    "UPDATE patient_accounts SET open_to_trials=1 WHERE username=?", (uname,)
                )
        _seed_dataset_patients(c, max_patients=DATASET_PATIENT_SEED_COUNT)
        c.commit()


def _seed_dataset_patients(c, max_patients: int = 20):
    """
    Seed a small set of real Synthea patients into the portal so the hospital
    dashboards are not limited to hand-made demo accounts.
    """
    if not (PATIENT_DETAILS_PATH.exists() and PATIENT_CONDITIONS_PATH.exists()
            and PATIENT_MEDICATIONS_PATH.exists()):
        return

    existing_dataset_count = c.execute(
        "SELECT COUNT(*) FROM patient_accounts WHERE synthea_id IS NOT NULL"
    ).fetchone()[0]
    if existing_dataset_count >= max_patients:
        return

    existing_synthea_ids = {
        row[0] for row in c.execute(
            "SELECT synthea_id FROM patient_accounts WHERE synthea_id IS NOT NULL"
        ).fetchall()
    }
    needed = max_patients - existing_dataset_count
    selected = {}

    with PATIENT_DETAILS_PATH.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if len(selected) >= needed:
                break
            sid = (row.get("Patient_ID") or "").strip()
            if not sid or sid in existing_synthea_ids:
                continue
            if (row.get("Death_Date") or "").strip():
                continue

            first_name = (row.get("First_Name") or "").strip() or "Patient"
            last_name = (row.get("Last_Name") or "").strip() or sid[:6]
            dob = _normalize_dataset_date(row.get("Birth_Date", ""))
            gender = (row.get("Gender") or "").strip()
            address = (row.get("Address") or "").strip()
            username = f"synthea_{sid[:8].lower()}"
            selected[sid] = {
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "dob": dob,
                "gender": gender,
                "address": address,
                "conditions": [],
                "medications": [],
            }

    if not selected:
        return

    with PATIENT_CONDITIONS_PATH.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            sid = (row.get("Patient_ID") or "").strip()
            if sid not in selected:
                continue
            cond = (row.get("Condition_Name") or "").strip().lower()
            if cond and cond not in selected[sid]["conditions"]:
                selected[sid]["conditions"].append(cond)
                if len(selected[sid]["conditions"]) >= 8:
                    continue

    with PATIENT_MEDICATIONS_PATH.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            sid = (row.get("Patient_ID") or "").strip()
            if sid not in selected:
                continue
            med = (row.get("Medication_Name") or "").strip()
            if med and med not in selected[sid]["medications"]:
                selected[sid]["medications"].append(med)
                if len(selected[sid]["medications"]) >= 6:
                    continue

    for sid, patient in selected.items():
        c.execute(
            """INSERT OR IGNORE INTO patient_accounts
               (id,username,password_hash,synthea_id,first_name,last_name,
                dob,gender,address,conditions,medications,open_to_trials,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                str(uuid.uuid4()),
                patient["username"],
                _hash("pass123"),
                sid,
                patient["first_name"],
                patient["last_name"],
                patient["dob"],
                patient["gender"],
                patient["address"],
                json.dumps(patient["conditions"]),
                json.dumps(patient["medications"]),
                1,
                datetime.now().isoformat(),
            ),
        )


def _normalize_dataset_date(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    try:
        return datetime.strptime(raw, "%d-%m-%Y").strftime("%Y-%m-%d")
    except ValueError:
        return raw


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


def update_hospital_profile(hid: str, **kwargs):
    allowed = {"hospital_name", "location", "research_conditions"}
    fields, vals = [], []
    for k, v in kwargs.items():
        if k in allowed:
            fields.append(f"{k}=?")
            vals.append(json.dumps(v) if isinstance(v, (list, dict)) else v)
    if not fields:
        return
    vals.append(hid)
    with _conn() as c:
        c.execute(f"UPDATE hospital_accounts SET {', '.join(fields)} WHERE id=?", vals)
        c.commit()


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

def connection_exists(patient_id: str, hospital_id: str, trial_id: str) -> bool:
    with _conn() as c:
        row = c.execute(
            """SELECT id FROM connections
               WHERE patient_id=? AND hospital_id=? AND COALESCE(trial_id,'')=COALESCE(?,'')""",
            (patient_id, hospital_id, trial_id)
        ).fetchone()
    return row is not None


def create_connection(patient_id, hospital_id, trial_id, trial_title,
                      initiated_by="patient", message="") -> dict | None:
    """Returns None if a connection for this (patient, hospital, trial) already exists."""
    if connection_exists(patient_id, hospital_id, trial_id):
        return None
    cid = str(uuid.uuid4())
    try:
        with _conn() as c:
            c.execute(
                """INSERT INTO connections
                   (id,patient_id,hospital_id,trial_id,trial_title,
                    initiated_by,status,message,created_at)
                   VALUES (?,?,?,?,?,?,  'pending',?,?)""",
                (cid, patient_id, hospital_id, trial_id, trial_title[:200] if trial_title else "",
                 initiated_by, message, datetime.now().isoformat())
            )
            c.commit()
    except sqlite3.IntegrityError:
        return None  # race condition — already inserted
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


def delete_connection(cid: str) -> bool:
    """Delete a connection and its message history."""
    with _conn() as c:
        c.execute("DELETE FROM connection_messages WHERE connection_id=?", (cid,))
        cur = c.execute("DELETE FROM connections WHERE id=?", (cid,))
        c.commit()
    return cur.rowcount > 0


def get_open_patients_for_hospital(hospital_id: str, condition_filter: str = "",
                                    include_connected: bool = False) -> list:
    """
    Returns patients who are open_to_trials=1, optionally filtered by condition.
    When include_connected=False (default), excludes patients already connected to this hospital.
    """
    with _conn() as c:
        if include_connected:
            rows = c.execute(
                """SELECT id, first_name, last_name, gender, dob, address, conditions
                   FROM patient_accounts WHERE open_to_trials=1"""
            ).fetchall()
        else:
            rows = c.execute(
                """SELECT id, first_name, last_name, gender, dob, address, conditions
                   FROM patient_accounts
                   WHERE open_to_trials=1
                     AND id NOT IN (
                         SELECT DISTINCT patient_id FROM connections
                         WHERE hospital_id=?
                     )""",
                (hospital_id,)
            ).fetchall()

    result = []
    cf = condition_filter.lower().strip()
    for r in rows:
        d = dict(r)
        try:
            d["conditions"] = json.loads(d["conditions"]) if isinstance(d["conditions"], str) else d["conditions"]
        except Exception:
            d["conditions"] = []
        if cf and not any(cf in cond.lower() for cond in d["conditions"]):
            continue
        result.append(d)
    return result


# ---------------------------------------------------------------------------
# Connection Messages
# ---------------------------------------------------------------------------

def get_connection_messages(connection_id: str) -> list:
    with _conn() as c:
        rows = c.execute(
            """SELECT * FROM connection_messages
               WHERE connection_id=? ORDER BY created_at ASC""",
            (connection_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def create_connection_message(connection_id: str, sender_role: str,
                               sender_id: str, body: str) -> dict:
    mid = str(uuid.uuid4())
    with _conn() as c:
        c.execute(
            """INSERT INTO connection_messages
               (id, connection_id, sender_role, sender_id, body, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (mid, connection_id, sender_role, sender_id,
             body[:2000], datetime.now().isoformat())
        )
        c.commit()
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM connection_messages WHERE id=?", (mid,)
        ).fetchone()
    return dict(row) if row else {}


def mark_messages_read(connection_id: str, reader_role: str):
    with _conn() as c:
        c.execute(
            """UPDATE connection_messages SET is_read=1
               WHERE connection_id=? AND sender_role != ?""",
            (connection_id, reader_role)
        )
        c.commit()


def unread_count(connection_id: str, reader_role: str) -> int:
    with _conn() as c:
        row = c.execute(
            """SELECT COUNT(*) AS cnt FROM connection_messages
               WHERE connection_id=? AND sender_role != ? AND is_read=0""",
            (connection_id, reader_role)
        ).fetchone()
    return row["cnt"] if row else 0


def get_hospital_inbox_threads(hospital_id: str) -> list:
    """All connection threads for a hospital, ordered by most recent activity."""
    with _conn() as c:
        rows = c.execute(
            """SELECT
                   c.id, c.patient_id, c.trial_title, c.status, c.created_at,
                   p.first_name, p.last_name,
                   (SELECT body FROM connection_messages
                    WHERE connection_id=c.id ORDER BY created_at DESC LIMIT 1) AS last_message,
                   (SELECT created_at FROM connection_messages
                    WHERE connection_id=c.id ORDER BY created_at DESC LIMIT 1) AS last_message_at,
                   (SELECT COUNT(*) FROM connection_messages
                    WHERE connection_id=c.id AND sender_role='patient' AND is_read=0) AS unread_count
               FROM connections c
               JOIN patient_accounts p ON c.patient_id=p.id
               WHERE c.hospital_id=?""",
            (hospital_id,)
        ).fetchall()
    threads = [dict(r) for r in rows]
    threads.sort(key=lambda t: t.get("last_message_at") or t["created_at"], reverse=True)
    return threads


def get_patient_inbox_threads(patient_id: str) -> list:
    """All connection threads for a patient, ordered by most recent activity."""
    with _conn() as c:
        rows = c.execute(
            """SELECT
                   c.id, c.hospital_id, c.trial_title, c.status, c.created_at,
                   h.hospital_name,
                   (SELECT body FROM connection_messages
                    WHERE connection_id=c.id ORDER BY created_at DESC LIMIT 1) AS last_message,
                   (SELECT created_at FROM connection_messages
                    WHERE connection_id=c.id ORDER BY created_at DESC LIMIT 1) AS last_message_at,
                   (SELECT COUNT(*) FROM connection_messages
                    WHERE connection_id=c.id AND sender_role='hospital' AND is_read=0) AS unread_count
               FROM connections c
               JOIN hospital_accounts h ON c.hospital_id=h.id
               WHERE c.patient_id=?""",
            (patient_id,)
        ).fetchall()
    threads = [dict(r) for r in rows]
    threads.sort(key=lambda t: t.get("last_message_at") or t["created_at"], reverse=True)
    return threads
