"""
Second Life — Flask Web Application
DSCI 5260 | Group 7

Two-portal system: Patient Portal + Hospital Portal
Run:  python app.py   →  http://localhost:5000
"""

import os
import sys
import uuid
import mimetypes
import secrets
import threading
from datetime import datetime
from pathlib import Path

from flask import (Flask, jsonify, redirect, render_template,
                   request, send_file, session, url_for)
from werkzeug.utils import secure_filename

sys.path.insert(0, str(Path(__file__).parent))
from pipeline import SecondLifePipeline
import database as db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["JSON_SORT_KEYS"] = False
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB upload limit
app.config["TEMPLATES_AUTO_RELOAD"] = True

_RUNNING_ON_HF_SPACE = bool(os.environ.get("SPACE_ID"))
if _RUNNING_ON_HF_SPACE:
    # Hugging Face renders Spaces under huggingface.co as an embedded app, so
    # the session cookie must be explicitly marked for cross-site use.
    app.config["SESSION_COOKIE_SAMESITE"] = "None"
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_PARTITIONED"] = True
    if not os.environ.get("SECRET_KEY"):
        print(
            "[app] WARNING: SECRET_KEY is not set. Sessions will reset when the Space restarts.",
            file=sys.stderr,
        )

UPLOAD_DIR = Path(__file__).parent / "uploads" / "patient_docs"
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".png", ".jpg", ".jpeg"}

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
    if conn is None:
        return jsonify({"error": "A connection with this hospital for this trial already exists"}), 409
    return jsonify({"success": True, "connection": conn})


def _hospital_name_tokens(name: str) -> frozenset:
    """Tokenise a hospital name for facility-name matching (same stopword set as pipeline)."""
    import re as _re
    _STOP = {"the","of","and","at","for","in","a","an","is","by",
             "hospital","medical","center","centre","clinic","university",
             "health","care","healthcare","system","institute","foundation",
             "research","general","regional","national","community",
             "services","department","division","college","school"}
    words = _re.findall(r"[a-z]+", str(name).lower())
    return frozenset(w for w in words if w not in _STOP and len(w) >= 3)


def _facility_match_score(h_tokens: frozenset, facility_token_list: list) -> float:
    """
    Return the best Jaccard score between hospital name tokens and any facility
    name tokens for a given trial.  Returns 0.0 if facility_token_list is empty.
    """
    if not h_tokens or not facility_token_list:
        return 0.0
    best = 0.0
    for fac_tokens in facility_token_list:
        if not fac_tokens:
            continue
        inter = len(h_tokens & fac_tokens)
        union = len(h_tokens | fac_tokens)
        score = inter / union if union else 0.0
        if score > best:
            best = score
    return best


@app.route("/api/patient/hospitals-for-trial", methods=["GET"])
def hospitals_for_trial():
    err = _patient_required()
    if err:
        return err
    trial_id = request.args.get("trial_id", "")
    if not trial_id:
        return jsonify({"hospitals": []})

    from pipeline import STATE_ABBREV
    import re as _re

    trial_fac_tokens = []
    trial_states     = set()
    trial_conds      = set()
    if _ready():
        trial_fac_tokens = pipeline.trial_facility_tokens.get(trial_id, [])
        trial_states     = pipeline.trial_us_states.get(trial_id, set())
        if trial_id in pipeline.trial_profiles:
            trial_conds = pipeline.trial_profiles[trial_id]["conditions"]

    all_hospitals = db.get_all_hospitals()
    result = []
    for h in all_hospitals:
        h_name = (h.get("hospital_name") or "").strip()
        h_loc  = (h.get("location") or "").strip()

        # Extract hospital state from "City, ST" location string
        m = _re.search(r",\s*([A-Z]{2})\s*$", h_loc)
        h_state_full = STATE_ABBREV.get(m.group(1), "") if m else ""

        # Tier 1: real facility-name match (Jaccard ≥ 0.25 is a generous but meaningful threshold)
        h_tokens     = _hospital_name_tokens(h_name)
        name_score   = _facility_match_score(h_tokens, trial_fac_tokens)
        if name_score >= 0.25:
            result.append({
                "id":            h["id"],
                "hospital_name": h_name,
                "location":      h_loc,
                "match_reason":  "verified site on this trial",
                "match_tier":    1,
            })
            continue

        # Tier 2: hospital is in the same US state as a trial facility
        if trial_states and h_state_full and h_state_full in trial_states:
            result.append({
                "id":            h["id"],
                "hospital_name": h_name,
                "location":      h_loc,
                "match_reason":  "in same state as a trial site",
                "match_tier":    2,
            })
            continue

        # Tier 3: research_conditions overlap with trial conditions
        rc_set = {r.lower() for r in (h.get("research_conditions") or [])}
        if rc_set & trial_conds:
            result.append({
                "id":            h["id"],
                "hospital_name": h_name,
                "location":      h_loc,
                "match_reason":  "researches related conditions",
                "match_tier":    3,
            })
            continue

        # Tier 4: no facility data exists at all — show all registered hospitals
        if not trial_fac_tokens and not trial_states:
            result.append({
                "id":            h["id"],
                "hospital_name": h_name,
                "location":      h_loc,
                "match_reason":  "",
                "match_tier":    4,
            })

    result.sort(key=lambda x: x["match_tier"])
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


@app.route("/api/hospital/profile", methods=["POST"])
def update_hospital_profile():
    err = _hospital_required()
    if err:
        return err
    data    = request.get_json(force=True) or {}
    allowed = {"hospital_name", "location", "research_conditions"}
    kwargs  = {k: v for k, v in data.items() if k in allowed}
    db.update_hospital_profile(session["hospital_id"], **kwargs)
    return jsonify(_pub_hospital(db.get_hospital_by_id(session["hospital_id"])))


@app.route("/api/hospital/trials", methods=["GET"])
def get_hospital_trials():
    err = _hospital_required()
    if err:
        return err
    if not _ready():
        return jsonify({"trials": [], "message": "System still loading"}), 202
    hospital = db.get_hospital_by_id(session["hospital_id"])
    if not hospital:
        return jsonify({"trials": []}), 404
    trials = pipeline.trials_for_hospital(
        hospital.get("hospital_name", ""),
        hospital.get("location", ""),
        hospital.get("research_conditions", []),
        top_k=20,
    )
    return jsonify({"trials": trials, "total": len(trials)})


@app.route("/api/hospital/patients", methods=["GET"])
def get_hospital_patients():
    err = _hospital_required()
    if err:
        return err
    condition         = request.args.get("condition", "").strip()
    include_connected = request.args.get("include_connected", "0") == "1"
    patients          = db.get_open_patients_for_hospital(
        session["hospital_id"], condition, include_connected=include_connected
    )
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
    if conn is None:
        return jsonify({"error": "A connection with this patient already exists"}), 409
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


@app.route("/api/patient/connections/<cid>", methods=["DELETE"])
def delete_patient_connection(cid):
    err = _patient_required()
    if err:
        return err
    conn = db.get_connection(cid)
    if not conn or conn["patient_id"] != session["patient_id"]:
        return jsonify({"error": "Not found"}), 404
    db.delete_connection(cid)
    return jsonify({"success": True})


@app.route("/api/hospital/connections/<cid>", methods=["DELETE"])
def delete_hospital_connection(cid):
    err = _hospital_required()
    if err:
        return err
    conn = db.get_connection(cid)
    if not conn or conn["hospital_id"] != session["hospital_id"]:
        return jsonify({"error": "Not found"}), 404
    db.delete_connection(cid)
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# Connection Messages
# ---------------------------------------------------------------------------

@app.route("/api/patient/connections/<cid>/messages", methods=["GET"])
def get_patient_connection_messages(cid):
    err = _patient_required()
    if err:
        return err
    conn = db.get_connection(cid)
    if not conn or conn["patient_id"] != session["patient_id"]:
        return jsonify({"error": "Not found"}), 404
    db.mark_messages_read(cid, "patient")
    return jsonify({"messages": db.get_connection_messages(cid)})


@app.route("/api/patient/connections/<cid>/messages", methods=["POST"])
def post_patient_connection_message(cid):
    err = _patient_required()
    if err:
        return err
    conn = db.get_connection(cid)
    if not conn or conn["patient_id"] != session["patient_id"]:
        return jsonify({"error": "Not found"}), 404
    body = (request.get_json(force=True) or {}).get("body", "").strip()
    if not body:
        return jsonify({"error": "Message body required"}), 400
    msg = db.create_connection_message(cid, "patient", session["patient_id"], body)
    return jsonify({"success": True, "message": msg})


@app.route("/api/hospital/connections/<cid>/messages", methods=["GET"])
def get_hospital_connection_messages(cid):
    err = _hospital_required()
    if err:
        return err
    conn = db.get_connection(cid)
    if not conn or conn["hospital_id"] != session["hospital_id"]:
        return jsonify({"error": "Not found"}), 404
    db.mark_messages_read(cid, "hospital")
    return jsonify({"messages": db.get_connection_messages(cid)})


@app.route("/api/hospital/connections/<cid>/messages", methods=["POST"])
def post_hospital_connection_message(cid):
    err = _hospital_required()
    if err:
        return err
    conn = db.get_connection(cid)
    if not conn or conn["hospital_id"] != session["hospital_id"]:
        return jsonify({"error": "Not found"}), 404
    body = (request.get_json(force=True) or {}).get("body", "").strip()
    if not body:
        return jsonify({"error": "Message body required"}), 400
    msg = db.create_connection_message(cid, "hospital", session["hospital_id"], body)
    return jsonify({"success": True, "message": msg})


# ---------------------------------------------------------------------------
# Patient Documents
# ---------------------------------------------------------------------------

@app.route("/api/patient/documents", methods=["GET"])
def get_patient_documents():
    err = _patient_required()
    if err:
        return err
    patient = db.get_patient_by_id(session["patient_id"])
    return jsonify({"documents": patient.get("documents", []) or []})


@app.route("/api/patient/documents", methods=["POST"])
def upload_patient_document():
    err = _patient_required()
    if err:
        return err
    if "file" not in request.files or not request.files["file"].filename:
        return jsonify({"error": "No file selected"}), 400
    f   = request.files["file"]
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"}), 400

    pid     = session["patient_id"]
    doc_dir = UPLOAD_DIR / pid
    doc_dir.mkdir(parents=True, exist_ok=True)

    doc_id    = str(uuid.uuid4())
    safe_name = secure_filename(f.filename)
    save_path = doc_dir / f"{doc_id}_{safe_name}"
    f.save(str(save_path))

    doc_meta = {
        "id":          doc_id,
        "filename":    safe_name,
        "path":        str(save_path.relative_to(Path(__file__).parent)),
        "uploaded_at": datetime.now().isoformat(),
        "mime_type":   mimetypes.guess_type(f.filename)[0] or "application/octet-stream",
        "size_bytes":  save_path.stat().st_size,
    }
    patient = db.get_patient_by_id(pid)
    docs    = list(patient.get("documents", []) or [])
    docs.append(doc_meta)
    db.update_patient_profile(pid, documents=docs)
    return jsonify({"success": True, "document": doc_meta})


@app.route("/api/patient/documents/<doc_id>", methods=["DELETE"])
def delete_patient_document(doc_id):
    err = _patient_required()
    if err:
        return err
    pid     = session["patient_id"]
    patient = db.get_patient_by_id(pid)
    docs    = list(patient.get("documents", []) or [])
    target  = next((d for d in docs if d["id"] == doc_id), None)
    if not target:
        return jsonify({"error": "Not found"}), 404
    try:
        fpath = Path(__file__).parent / target["path"]
        if fpath.exists():
            fpath.unlink()
    except Exception:
        pass
    db.update_patient_profile(pid, documents=[d for d in docs if d["id"] != doc_id])
    return jsonify({"success": True})


@app.route("/api/patient/documents/<doc_id>/download")
def download_patient_document(doc_id):
    err = _patient_required()
    if err:
        return err
    patient = db.get_patient_by_id(session["patient_id"])
    docs    = list(patient.get("documents", []) or [])
    target  = next((d for d in docs if d["id"] == doc_id), None)
    if not target:
        return jsonify({"error": "Not found"}), 404
    fpath = Path(__file__).parent / target["path"]
    if not fpath.exists():
        return jsonify({"error": "File not found on disk"}), 404
    return send_file(str(fpath), download_name=target["filename"], as_attachment=True)


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------

@app.route("/api/hospital/inbox")
def get_hospital_inbox():
    err = _hospital_required()
    if err:
        return err
    return jsonify({"threads": db.get_hospital_inbox_threads(session["hospital_id"])})


@app.route("/api/patient/inbox")
def get_patient_inbox():
    err = _patient_required()
    if err:
        return err
    return jsonify({"threads": db.get_patient_inbox_threads(session["patient_id"])})


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
    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print(" Second Life — Clinical Trial Matching")
    print(f" http://localhost:{port}")
    print("=" * 60)
    app.run(host="0.0.0.0", debug=False, port=port, use_reloader=False)
