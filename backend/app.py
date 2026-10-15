import os
import re
import threading
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

app = Flask(__name__)
CORS(app)

# Guards check-then-write sequences so two concurrent requests cannot both
# pass the conflict check and double-book the same slot.
STATE_LOCK = threading.Lock()

VENUES = {
    "aud": {"id": "aud", "name": "Main Auditorium", "capacity": 400, "equipment": ["Dual Projectors", "Line-Array PA", "4 Wireless Mics"]},
    "sha": {"id": "sha", "name": "Seminar Hall A", "capacity": 120, "equipment": ["Smart Board", "2 Wireless Mics"]},
    "lab": {"id": "lab", "name": "CSE AI & Robotics Lab", "capacity": 60, "equipment": ["30 Workstations", "4K Display"]},
    "amp": {"id": "amp", "name": "Open Air Amphitheatre", "capacity": 250, "equipment": ["Portable PA", "Stage Lighting"]},
}

ROLES = {
    "student": "Student Coordinator",
    "faculty": "Faculty Advisor",
    "admin": "Facilities Admin",
}

ACTIVE_STATUSES = {"APPROVED_FACULTY", "CONFIRMED"}

# Finite State Machine transition rules
TRANSITIONS = {
    "PENDING_FACULTY": {"faculty": ["APPROVED_FACULTY", "REJECTED"]},
    "APPROVED_FACULTY": {"admin": ["CONFIRMED", "REJECTED"]},
}

# Role authentication credentials
CREDENTIALS = {
    "faculty": {
        "email": "faculty@campus.edu",
        "password": "faculty123",
        "name": "Dr. Faculty Advisor",
    },
    "admin": {
        "email": "admin@campus.edu",
        "password": "admin123",
        "name": "Facilities Admin",
    },
}

TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def to_min(time_str: str) -> int:
    """Convert a strict 24h 'HH:MM' string to minutes since midnight. Raises ValueError otherwise."""
    if not isinstance(time_str, str) or not TIME_RE.match(time_str):
        raise ValueError(f"Invalid time: {time_str!r}")
    h, m = map(int, time_str.split(":"))
    return h * 60 + m


def valid_date(date_str) -> bool:
    if not isinstance(date_str, str):
        return False
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def now_clock() -> str:
    return datetime.now().strftime("%I:%M %p").lstrip("0")


def initial_state():
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    bookings = [
        {"id": 101, "title": "AI Summit 2026", "club": "IEEE CS", "venueId": "aud", "date": today, "start": "10:00", "end": "13:00", "attendees": 320, "equip": ["Dual Projectors", "Line-Array PA"], "status": "CONFIRMED", "remark": "Cleared. Keep aisles open."},
        {"id": 102, "title": "Hackathon Kickoff", "club": "Coding Club", "venueId": "sha", "date": today, "start": "14:00", "end": "17:00", "attendees": 100, "equip": ["Smart Board"], "status": "APPROVED_FACULTY", "remark": "Fine by me."},
        {"id": 103, "title": "Line Follower Workshop", "club": "Robotics Society", "venueId": "lab", "date": tomorrow, "start": "11:00", "end": "13:00", "attendees": 45, "equip": ["30 Workstations"], "status": "PENDING_FACULTY", "remark": ""},
        {"id": 104, "title": "Open Mic Night", "club": "Cultural Club", "venueId": "amp", "date": today, "start": "18:00", "end": "20:00", "attendees": 240, "equip": ["Portable PA", "Stage Lighting"], "status": "REJECTED", "remark": "Clashes with the evening sports meet."},
        {"id": 105, "title": "Guest Lecture: LLM Systems", "club": "IEEE CS", "venueId": "aud", "date": tomorrow, "start": "09:00", "end": "11:00", "attendees": 280, "equip": ["Dual Projectors"], "status": "PENDING_FACULTY", "remark": ""},
    ]
    audit = [
        {"t": "9:05 AM", "msg": "Request #101 transitioned from APPROVED_FACULTY -> CONFIRMED by Facilities Admin"},
        {"t": "8:40 AM", "msg": "Request #101 transitioned from PENDING_FACULTY -> APPROVED_FACULTY by Faculty Advisor"},
        {"t": "8:10 AM", "msg": "Request #104 transitioned from PENDING_FACULTY -> REJECTED by Faculty Advisor"},
    ]
    return bookings, audit, []


BOOKINGS, AUDIT_LOG, CONFLICT_LOG = initial_state()


def find_conflicts(draft, bookings_list, ignore_id=None):
    conflicts = []
    d_start, d_end = to_min(draft["start"]), to_min(draft["end"])
    for b in bookings_list:
        if b["id"] == ignore_id:
            continue
        if b["venueId"] == draft["venueId"] and b["date"] == draft["date"] and b["status"] in ACTIVE_STATUSES:
            b_start, b_end = to_min(b["start"]), to_min(b["end"])
            if d_start < b_end and d_end > b_start:
                conflicts.append(b)
    return conflicts


def error(msg, code, **extra):
    return jsonify({"ok": False, "error": msg, **extra}), code


# ---------- Frontend (served from the same origin for one-command startup) ----------
@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


# ---------- REST API ----------
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True}), 200


@app.route("/api/state", methods=["GET"])
def get_state():
    with STATE_LOCK:
        return jsonify({
            "bookings": BOOKINGS,
            "audit": AUDIT_LOG,
            "conflictLog": CONFLICT_LOG,
        }), 200


@app.route("/api/bookings", methods=["POST"])
def create_booking():
    data = request.get_json(silent=True)
    required_fields = {"title", "club", "venueId", "date", "start", "end", "attendees"}
    if not isinstance(data, dict) or not required_fields.issubset(data.keys()):
        return error("Invalid or missing payload data.", 400)

    title = str(data.get("title") or "").strip()
    club = str(data.get("club") or "").strip()
    venue_id = data.get("venueId")
    if not title:
        return error("Event title is required.", 400)
    if not club:
        return error("Organizing club is required.", 400)
    if venue_id not in VENUES:
        return error("Selected venue does not exist.", 400)
    if not valid_date(data["date"]):
        return error("Invalid date format (expected YYYY-MM-DD).", 400)

    venue = VENUES[venue_id]
    try:
        start_min = to_min(data["start"])
        end_min = to_min(data["end"])
        if isinstance(data["attendees"], bool):
            raise ValueError
        attendees = int(data["attendees"])
    except (ValueError, TypeError):
        return error("Invalid time or attendee format.", 400)

    if end_min <= start_min:
        return error("Chronological check failed: end time must be strictly after start time.", 400)
    if attendees < 1:
        return error("Expected attendees must be at least 1.", 400)
    if attendees > venue["capacity"]:
        return error(f"Capacity exceeded: {attendees} attendees > {venue['name']} capacity of {venue['capacity']}.", 400)

    equip = data.get("equip") or []
    if not isinstance(equip, list) or any(e not in venue["equipment"] for e in equip):
        return error(f"Requested equipment is not available at {venue['name']}.", 400)

    with STATE_LOCK:
        conflicts = find_conflicts(data, BOOKINGS)
        if conflicts:
            c = conflicts[0]
            err_msg = f"Time conflict with #{c['id']} \"{c['title']}\" ({c['start']}-{c['end']}) at {venue['name']}."
            CONFLICT_LOG.insert(0, {
                "t": now_clock(),
                "msg": f"Blocked new request \"{title}\" ({venue['name']}, {data['date']} {data['start']}-{data['end']}): {err_msg}"
            })
            return error(err_msg, 409, conflictLog=CONFLICT_LOG)

        new_id = max((b["id"] for b in BOOKINGS), default=100) + 1
        new_booking = {
            "id": new_id,
            "title": title,
            "club": club,
            "venueId": venue_id,
            "date": data["date"],
            "start": data["start"],
            "end": data["end"],
            "attendees": attendees,
            "equip": list(dict.fromkeys(equip)),
            "status": "PENDING_FACULTY",
            "remark": "",
        }
        BOOKINGS.append(new_booking)
        AUDIT_LOG.insert(0, {
            "t": now_clock(),
            "msg": f"Request #{new_id} created as PENDING_FACULTY by Student Coordinator"
        })
        return jsonify({
            "ok": True,
            "id": new_id,
            "booking": new_booking,
            "bookings": BOOKINGS,
            "audit": AUDIT_LOG,
            "conflictLog": CONFLICT_LOG,
        }), 201


@app.route("/api/bookings/<int:booking_id>/status", methods=["PATCH"])
def transition_booking(booking_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    to_status = data.get("to")
    actor_role = data.get("role")
    remark = str(data.get("remark") or "").strip()

    with STATE_LOCK:
        booking = next((b for b in BOOKINGS if b["id"] == booking_id), None)
        if not booking:
            return error(f"Booking #{booking_id} not found.", 404)

        allowed_targets = TRANSITIONS.get(booking["status"], {}).get(actor_role, [])
        if to_status not in allowed_targets:
            return error(f"Transition {booking['status']} -> {to_status} is not allowed for role '{actor_role}'.", 403)

        if to_status in ACTIVE_STATUSES:
            conflicts = find_conflicts(booking, BOOKINGS, ignore_id=booking_id)
            if conflicts:
                c = conflicts[0]
                msg = f"Cannot move #{booking_id} to {to_status}: overlaps #{c['id']} \"{c['title']}\" ({c['start']}-{c['end']})."
                CONFLICT_LOG.insert(0, {"t": now_clock(), "msg": msg})
                return error(msg, 409, conflictLog=CONFLICT_LOG)

        old_status = booking["status"]
        booking["status"] = to_status
        if remark:
            booking["remark"] = remark

        actor_name = ROLES.get(actor_role, actor_role)
        remark_suffix = f' (remark: "{remark}")' if remark else ""
        AUDIT_LOG.insert(0, {
            "t": now_clock(),
            "msg": f"Request #{booking_id} transitioned from {old_status} -> {to_status} by {actor_name}{remark_suffix}"
        })

        return jsonify({
            "ok": True,
            "booking": booking,
            "bookings": BOOKINGS,
            "audit": AUDIT_LOG,
            "conflictLog": CONFLICT_LOG,
        }), 200


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json(silent=True) or {}
    role = data.get("role")
    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")

    if role not in CREDENTIALS:
        return error("Invalid role specified for authentication.", 400)

    user = CREDENTIALS[role]
    if email == user["email"].lower() and password == user["password"]:
        return jsonify({
            "ok": True,
            "role": role,
            "name": user["name"],
            "email": user["email"],
        }), 200

    return error("Invalid credentials. Please verify email and password.", 401)


@app.route("/api/bookings/<int:booking_id>", methods=["DELETE"])
def delete_booking(booking_id):
    data = request.get_json(silent=True) if request.is_json else {}
    actor_role = data.get("role") or request.args.get("role") or "student"

    with STATE_LOCK:
        booking = next((b for b in BOOKINGS if b["id"] == booking_id), None)
        if not booking:
            return error(f"Booking #{booking_id} not found.", 404)

        if actor_role == "student" and booking["status"] not in {"PENDING_FACULTY", "REJECTED"}:
            return error("Students can only withdraw pending or rejected requests.", 403)

        BOOKINGS.remove(booking)

        actor_name = ROLES.get(actor_role, actor_role)
        AUDIT_LOG.insert(0, {
            "t": now_clock(),
            "msg": f"Request #{booking_id} (\"{booking['title']}\") deleted by {actor_name}"
        })

        return jsonify({
            "ok": True,
            "deletedId": booking_id,
            "bookings": BOOKINGS,
            "audit": AUDIT_LOG,
            "conflictLog": CONFLICT_LOG,
        }), 200


@app.route("/api/reset", methods=["POST"])
def reset_state():
    global BOOKINGS, AUDIT_LOG, CONFLICT_LOG
    with STATE_LOCK:
        BOOKINGS, AUDIT_LOG, CONFLICT_LOG = initial_state()
        return jsonify({"ok": True, "bookings": BOOKINGS, "audit": AUDIT_LOG, "conflictLog": CONFLICT_LOG}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f" * Open the app at http://localhost:{port}/")
    app.run(host="127.0.0.1", port=port, debug=os.environ.get("FLASK_DEBUG", "1") == "1")