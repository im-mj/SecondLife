"""
Second Life — Flask Web Application
DSCI 5260 | Group 7

Two-portal system: Patient Portal + Hospital Portal
Run:  python app.py   →  http://localhost:5000
"""

import os
import sys
import secrets
import threading
from datetime import datetime
from pathlib import Path

from flask import (Flask, jsonify, redirect, render_template,
                   request, session, url_for)

sys.path.insert(0, str(Path(__file__).parent))
from pipeline import SecondLifePipeline
import database as db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["JSON_SORT_KEYS"] = False

# ---------------------------------------------------------------------------
# Pipeline boot (background thread — server comes up immediately)
# ---------------------------------------------------------------------------
pipeline: SecondLifePipeline | None = None
_boot_error: str = ""
_boot_ready = threading.Event()


def _boot():
    global pipeline, _boot_error
    try:
        db.init_db()
        p = SecondLifePipeline()
        p.load()
        p.train()
        pipeline = p
        print("[app] Pipeline ready.")
    except Exception as e:
        import traceback
        _boot_error = traceback.format_exc()
        print(f"[app] BOOT ERROR:\n{_boot_error}", file=sys.stderr)
    finally:
        _boot_ready.set()


_t = threading.Thread(target=_boot, daemon=True)
_t.start()


def _ready():
    return pipeline is not None


# ---------------------------------------------------------------------------
# Auth guards (return (response, code) or None)
# ---------------------------------------------------------------------------

def _patient_required():
    if "patient_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    return None


def _hospital_required():
    if "hospital_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    return None


# ---------------------------------------------------------------------------
# Sanitisers (strip password hash before sending to client)
# ---------------------------------------------------------------------------

def _pub_patient(p: dict) -> dict:
    d = dict(p)
    d.pop("password_hash", None)
    return d


def _pub_hospital(h: dict) -> dict:
    d = dict(h)
    d.pop("password_hash", None)
    return d


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def landing():
    if "patient_id" in session:
        return redirect(url_for("patient_portal"))
    if "hospital_id" in session:
        return redirect(url_for("hospital_portal"))
    return render_template("landing.html")


@app.route("/patient")
def patient_portal():
    if "patient_id" not in session:
        return redirect(url_for("landing"))
    patient = db.get_patient_by_id(session["patient_id"])
    if not patient:
        session.clear()
        return redirect(url_for("landing"))
    return render_template("patient.html", patient=_pub_patient(patient))


@app.route("/hospital")
def hospital_portal():
    if "hospital_id" not in session:
        return redirect(url_for("landing"))
    hospital = db.get_hospital_by_id(session["hospital_id"])
    if not hospital:
        session.clear()
        return redirect(url_for("landing"))
    return render_template("hospital.html", hospital=_pub_hospital(hospital))


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.route("/auth/patient/register", methods=["POST"])
def patient_register():
    data = request.get_json(force=True) or {}
    username   = data.get("username",   "").strip()
    password   = data.get("password",   "").strip()
    first_name = data.get("first_name", "").strip()
    last_name  = data.get("last_name",  "").strip()
    dob        = data.get("dob",        "").strip()
    gender     = data.get("gender",     "").strip().upper()
    address    = data.get("address",    "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    patient = db.create_patient(username, password, first_name, last_name,
                                dob, gender, address)
    if patient is None:
        return jsonify({"error": "Username already taken"}), 409

    session["patient_id"] = patient["id"]
    session["role"] = "patient"
    return jsonify({"success": True, "patient": _pub_patient(patient)})


@app.route("/auth/patient/login", methods=["POST"])
def patient_login():
    data    = request.get_json(force=True) or {}
    patient = db.authenticate_patient(data.get("username", ""),
                                      data.get("password", ""))
    if patient is None:
        return jsonify({"error": "Invalid username or password"}), 401

    session["patient_id"] = patient["id"]
    session["role"] = "patient"
    return jsonify({"success": True, "patient": _pub_patient(patient)})


@app.route("/auth/hospital/register", methods=["POST"])
def hospital_register():
    data          = request.get_json(force=True) or {}
    username      = data.get("username",      "").strip()
    password      = data.get("password",      "").strip()
    hospital_name = data.get("hospital_name", "").strip()
    location      = data.get("location",      "").strip()
    research_conditions = data.get("research_conditions", [])

    if not username or not password or not hospital_name:
        return jsonify({"error": "Username, password and hospital name are required"}), 400

    hospital = db.create_hospital(username, password, hospital_name,
                                  location, research_conditions)
    if hospital is None:
        return jsonify({"error": "Username already taken"}), 409

    session["hospital_id"] = hospital["id"]
    session["role"] = "hospital"
    return jsonify({"success": True, "hospital": _pub_hospital(hospital)})


@app.route("/auth/hospital/login", methods=["POST"])
def hospital_login():
    data     = request.get_json(force=True) or {}
    hospital = db.authenticate_hospital(data.get("username", ""),
                                        data.get("password", ""))
    if hospital is None:
        return jsonify({"error": "Invalid username or password"}), 401

    session["hospital_id"] = hospital["id"]
    session["role"] = "hospital"
    return jsonify({"success": True, "hospital": _pub_hospital(hospital)})


@app.route("/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# Patient API
# ---------------------------------------------------------------------------

@app.route("/api/patient/profile", methods=["GET"])
def get_patient_profile():
    err = _patient_required()
    if err:
        return err
    patient = db.get_patient_by_id(session["patient_id"])
    if not patient:
        return jsonify({"error": "Not found"}), 404
    return jsonify(_pub_patient(patient))


@app.route("/api/patient/profile", methods=["POST"])
def update_patient_profile():
    err = _patient_required()
    if err:
        return err
    data    = request.get_json(force=True) or {}
    allowed = {"first_name", "last_name", "dob", "gender", "address",
               "conditions", "medications", "open_to_trials"}
    kwargs  = {k: v for k, v in data.items() if k in allowed}
    db.update_patient_profile(session["patient_id"], **kwargs)
    return jsonify(_pub_patient(db.get_patient_by_id(session["patient_id"])))


@app.route("/api/patient/matches", methods=["GET"])
def patient_matches():
    err = _patient_required()
    if err:
        return err
    if not _ready():
        return jsonify({"error": "System still loading. Please wait."}), 503

    patient    = db.get_patient_by_id(session["patient_id"])
    conditions = patient.get("conditions", [])
    address    = patient.get("address", "")

    # Calculate age from DOB
    age  = 50
    dob  = patient.get("dob", "")
    if dob:
        try:
            birth = datetime.strptime(dob, "%Y-%m-%d")
            age   = int((datetime.now() - birth).days / 365.25)
        except Exception:
            pass

    gender = patient.get("gender", "M") or "M"

    if not conditions:
        return jsonify({"results": [],
                        "message": "No conditions on your profile. "
                                   "Update your profile first."})

    matches = pipeline.match_patient(
        conditions, age, gender, top_k=20,
        patient_id=session["patient_id"], address=address,
    )

    # Annotate with saved interest status
    interests = {i["trial_id"]: i["status"]
                 for i in db.get_patient_interests(session["patient_id"])}
    for m in matches:
        m["interest_status"] = interests.get(m["trial_id"])

    return jsonify({"results": matches, "total": len(matches)})


@app.route("/api/patient/interests", methods=["GET"])
def get_patient_interests():
    err = _patient_required()
    if err:
        return err
    return jsonify({"interests": db.get_patient_interests(session["patient_id"])})


@app.route("/api/patient/interest", methods=["POST"])
def save_patient_interest():
    err = _patient_required()
    if err:
        return err
    data       = request.get_json(force=True) or {}
    trial_id   = data.get("trial_id", "")
    trial_title = data.get("trial_title", "")
    match_score = float(data.get("match_score", 0))
    if not trial_id:
        return jsonify({"error": "trial_id required"}), 400
    db.save_trial_interest(session["patient_id"], trial_id,
                           trial_title, match_score)
    return jsonify({"success": True})


@app.route("/api/patient/interest/<trial_id>", methods=["DELETE"])
def remove_patient_interest(trial_id):
    err = _patient_required()
    if err:
        return err
    db.withdraw_interest(session["patient_id"], trial_id)
    return jsonify({"success": True})


@app.route("/api/patient/connections", methods=["GET"])
def get_patient_connections():
    err = _patient_required()
    if err:
        return err
    return jsonify({"connections": db.get_patient_connections(session["patient_id"])})


@app.route("/api/patient/connect", methods=["POST"])
def patient_connect():
    err = _patient_required()
    if err:
        return err
    data        = request.get_json(force=True) or {}
    hospital_id = data.get("hospital_id", "")
    trial_id    = data.get("trial_id", "")
    trial_title = data.get("trial_title", "")
    message     = data.get("message", "")
    if not hospital_id:
        return jsonify({"error": "hospital_id required"}), 400
    conn = db.create_connection(
        session["patient_id"], hospital_id, trial_id, trial_title,
        initiated_by="patient", message=message,
    )
    return jsonify({"success": True, "connection": conn})


@app.route("/api/patient/hospitals-for-trial", methods=["GET"])
def hospitals_for_trial():
    err = _patient_required()
    if err:
        return err
    trial_id = request.args.get("trial_id", "")
    if not trial_id:
        return jsonify({"hospitals": []})

    # Get trial conditions from pipeline
    trial_conds = set()
    if _ready() and trial_id in pipeline.trial_profiles:
        trial_conds = pipeline.trial_profiles[trial_id]["conditions"]

    all_hospitals = db.get_all_hospitals()
    result = []
    for h in all_hospitals:
        rc_set = {r.lower() for r in (h.get("research_conditions") or [])}
        if not trial_conds or (rc_set & trial_conds):
            result.append({
                "id":            h["id"],
                "hospital_name": h["hospital_name"],
                "location":      h.get("location", ""),
            })
    return jsonify({"hospitals": result})


# ---------------------------------------------------------------------------
# Hospital API
# ---------------------------------------------------------------------------

@app.route("/api/hospital/profile", methods=["GET"])
def get_hospital_profile():
    err = _hospital_required()
    if err:
        return err
    hospital = db.get_hospital_by_id(session["hospital_id"])
    if not hospital:
        return jsonify({"error": "Not found"}), 404
    return jsonify(_pub_hospital(hospital))


@app.route("/api/hospital/patients", methods=["GET"])
def get_hospital_patients():
    err = _hospital_required()
    if err:
        return err
    condition = request.args.get("condition", "").strip()
    patients  = db.get_open_patients_for_hospital(session["hospital_id"], condition)
    return jsonify({"patients": patients})


@app.route("/api/hospital/connect", methods=["POST"])
def hospital_connect():
    err = _hospital_required()
    if err:
        return err
    data        = request.get_json(force=True) or {}
    patient_id  = data.get("patient_id", "")
    trial_id    = data.get("trial_id", "")
    trial_title = data.get("trial_title", "")
    message     = data.get("message", "")
    if not patient_id:
        return jsonify({"error": "patient_id required"}), 400
    conn = db.create_connection(
        patient_id, session["hospital_id"], trial_id, trial_title,
        initiated_by="hospital", message=message,
    )
    return jsonify({"success": True, "connection": conn})


@app.route("/api/hospital/connections", methods=["GET"])
def get_hospital_connections():
    err = _hospital_required()
    if err:
        return err
    return jsonify({"connections": db.get_hospital_connections(session["hospital_id"])})


@app.route("/api/hospital/connections/<cid>/status", methods=["PUT"])
def update_hospital_connection_status(cid):
    err = _hospital_required()
    if err:
        return err
    data   = request.get_json(force=True) or {}
    status = data.get("status", "")
    if status not in ("pending", "accepted", "rejected", "completed"):
        return jsonify({"error": "Invalid status"}), 400
    db.update_connection_status(cid, status)
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# Shared pipeline API
# ---------------------------------------------------------------------------

@app.route("/api/status")
def api_status():
    if _boot_error:
        return jsonify({"ready": False, "error": _boot_error}), 500
    if not _ready():
        return jsonify({"ready": False,
                        "message": "Loading data and training model…"}), 202
    return jsonify({"ready": True, "stats": pipeline.stats})


@app.route("/api/conditions/autocomplete")
def api_conditions_autocomplete():
    if not _ready():
        return jsonify({"results": []})
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"results": []})
    return jsonify({"results": pipeline.condition_autocomplete(q, limit=15)})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print(" Second Life — Clinical Trial Matching")
    print(" http://localhost:5000")
    print("=" * 60)
    app.run(debug=False, port=5000, use_reloader=False)
