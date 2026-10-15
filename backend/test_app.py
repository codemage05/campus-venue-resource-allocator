import pytest
from app import app, reset_state


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        client.post("/api/reset")
        yield client


def test_valid_booking_creation(client):
    """Equivalence Partitioning: Valid booking inside boundaries succeeds (201)."""
    res = client.post("/api/bookings", json={
        "title": "DevSecOps Workshop",
        "club": "IEEE CS",
        "venueId": "lab",
        "date": "2026-12-01",
        "start": "14:00",
        "end": "16:00",
        "attendees": 50,
        "equip": ["30 Workstations"]
    })
    assert res.status_code == 201
    data = res.get_json()
    assert data["ok"] is True
    assert data["booking"]["status"] == "PENDING_FACULTY"


def test_capacity_boundary_value_analysis(client):
    """Boundary Value Analysis (BVA): CSE Lab max capacity is 60. 60 passes, 61 fails."""
    # Exact boundary (60) -> PASS
    res_ok = client.post("/api/bookings", json={
        "title": "Boundary 60 Test", "club": "Coding Club", "venueId": "lab",
        "date": "2026-12-02", "start": "10:00", "end": "12:00", "attendees": 60
    })
    assert res_ok.status_code == 201

    # Above boundary (61) -> FAIL (400 Bad Request)
    res_fail = client.post("/api/bookings", json={
        "title": "Boundary 61 Test", "club": "Coding Club", "venueId": "lab",
        "date": "2026-12-03", "start": "10:00", "end": "12:00", "attendees": 61
    })
    assert res_fail.status_code == 400
    assert "Capacity exceeded" in res_fail.get_json()["error"]


def test_chronological_time_boundary(client):
    """Boundary check: End time equal to or before Start time is rejected (400)."""
    res = client.post("/api/bookings", json={
        "title": "Invalid Time Event", "club": "IEEE CS", "venueId": "sha",
        "date": "2026-12-05", "start": "15:00", "end": "14:00", "attendees": 40
    })
    assert res.status_code == 400
    assert "Chronological check failed" in res.get_json()["error"]


def test_temporal_conflict_detection(client):
    """Conflict check: Overlapping an active booking on the same venue & date fails (409)."""
    state = client.get("/api/state").get_json()
    confirmed = next(b for b in state["bookings"] if b["id"] == 101)

    res = client.post("/api/bookings", json={
        "title": "Overlapping Event",
        "club": "Robotics Society",
        "venueId": confirmed["venueId"],
        "date": confirmed["date"],
        "start": "11:00",
        "end": "12:00",
        "attendees": 100
    })
    assert res.status_code == 409
    assert "Time conflict" in res.get_json()["error"]


def test_rbac_and_state_machine_enforcement(client):
    """State Machine check: Student cannot approve; Admin cannot skip Faculty approval."""
    # 1. Student tries to approve Pending request #103 -> 403 Forbidden
    res_student = client.patch("/api/bookings/103/status", json={
        "to": "APPROVED_FACULTY", "role": "student"
    })
    assert res_student.status_code == 403

    # 2. Admin tries to directly confirm Pending request #103 -> 403 Forbidden
    res_admin_early = client.patch("/api/bookings/103/status", json={
        "to": "CONFIRMED", "role": "admin"
    })
    assert res_admin_early.status_code == 403

    # 3. Faculty approves #103 -> 200 OK
    res_faculty = client.patch("/api/bookings/103/status", json={
        "to": "APPROVED_FACULTY", "role": "faculty", "remark": "Approved for robotics lab"
    })
    assert res_faculty.status_code == 200
    assert res_faculty.get_json()["booking"]["status"] == "APPROVED_FACULTY"

    # 4. Admin confirms #103 -> 200 OK
    res_admin_ok = client.patch("/api/bookings/103/status", json={
        "to": "CONFIRMED", "role": "admin", "remark": "Keys allocated"
    })
    assert res_admin_ok.status_code == 200
    assert res_admin_ok.get_json()["booking"]["status"] == "CONFIRMED"


def test_competing_pending_requests_race_condition(client):
    """If two pending requests overlap, approving the first blocks approving the second (409)."""
    payload = {
        "title": "Competing Slot A", "club": "IEEE CS", "venueId": "sha",
        "date": "2026-12-10", "start": "10:00", "end": "12:00", "attendees": 80
    }
    id_a = client.post("/api/bookings", json=payload).get_json()["id"]
    id_b = client.post("/api/bookings", json={**payload, "title": "Competing Slot B"}).get_json()["id"]

    # Approve first request -> 200 OK
    res_a = client.patch(f"/api/bookings/{id_a}/status", json={"to": "APPROVED_FACULTY", "role": "faculty"})
    assert res_a.status_code == 200

    # Approve second overlapping request -> 409 Conflict
    res_b = client.patch(f"/api/bookings/{id_b}/status", json={"to": "APPROVED_FACULTY", "role": "faculty"})
    assert res_b.status_code == 409


VALID = {"title": "Valid", "club": "IEEE CS", "venueId": "sha", "date": "2026-12-20",
         "start": "10:00", "end": "11:00", "attendees": 10}


@pytest.mark.parametrize("override, fragment", [
    ({"start": "25:00"}, "Invalid time"),          # out-of-range hour
    ({"end": "10"}, "Invalid time"),               # malformed time
    ({"start": None}, "Invalid time"),             # null time (previously crashed with 500)
    ({"date": "2026-13-45"}, "Invalid date"),      # impossible date
    ({"attendees": "abc"}, "Invalid time or attendee"),
    ({"attendees": 0}, "at least 1"),              # lower boundary
    ({"title": "   "}, "title is required"),
    ({"venueId": "xyz"}, "venue does not exist"),
    ({"equip": ["Stage Lighting"]}, "equipment is not available"),  # not at Seminar Hall A
])
def test_invalid_payloads_rejected_with_400(client, override, fragment):
    """Equivalence Partitioning on invalid input classes: every one returns 400, never 500."""
    res = client.post("/api/bookings", json={**VALID, **override})
    assert res.status_code == 400
    assert fragment in res.get_json()["error"]


def test_non_object_json_body_rejected(client):
    """A JSON array body must be rejected cleanly (previously crashed with 500)."""
    assert client.post("/api/bookings", json=[1, 2, 3]).status_code == 400
    assert client.patch("/api/bookings/103/status", json=[1]).status_code == 403


def test_back_to_back_slots_do_not_conflict(client):
    """BVA on time overlap: a booking ending at 13:00 does not clash with one starting at 13:00."""
    state = client.get("/api/state").get_json()
    confirmed = next(b for b in state["bookings"] if b["id"] == 101)  # 10:00-13:00
    res = client.post("/api/bookings", json={**VALID, "venueId": "aud", "date": confirmed["date"],
                                             "start": "13:00", "end": "14:00"})
    assert res.status_code == 201


def test_unknown_booking_and_null_remark(client):
    assert client.patch("/api/bookings/9999/status", json={"to": "REJECTED", "role": "faculty"}).status_code == 404
    res = client.patch("/api/bookings/103/status", json={"to": "REJECTED", "role": "faculty", "remark": None})
    assert res.status_code == 200
    assert res.get_json()["booking"]["remark"] == ""  # not the string "None"


def test_terminal_states_are_final(client):
    """CONFIRMED and REJECTED have no outgoing transitions for any role."""
    for role in ("student", "faculty", "admin"):
        assert client.patch("/api/bookings/101/status", json={"to": "REJECTED", "role": role}).status_code == 403
        assert client.patch("/api/bookings/104/status", json={"to": "CONFIRMED", "role": role}).status_code == 403


def test_frontend_served_at_root(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"Venue" in res.data


def test_role_authentication_login(client):
    """Role Authentication check: Valid credentials return 200, invalid password returns 401."""
    # 1. Valid Faculty Login -> 200 OK
    res_faculty = client.post("/api/auth/login", json={
        "role": "faculty",
        "email": "faculty@campus.edu",
        "password": "faculty123"
    })
    assert res_faculty.status_code == 200
    assert res_faculty.get_json()["ok"] is True
    assert res_faculty.get_json()["name"] == "Dr. Faculty Advisor"

    # 2. Valid Admin Login -> 200 OK
    res_admin = client.post("/api/auth/login", json={
        "role": "admin",
        "email": "admin@campus.edu",
        "password": "admin123"
    })
    assert res_admin.status_code == 200
    assert res_admin.get_json()["ok"] is True

    # 3. Invalid Password -> 401 Unauthorized
    res_bad_pw = client.post("/api/auth/login", json={
        "role": "faculty",
        "email": "faculty@campus.edu",
        "password": "wrongpassword"
    })
    assert res_bad_pw.status_code == 401
    assert res_bad_pw.get_json()["ok"] is False

    # 4. Unknown Role -> 400 Bad Request
    res_bad_role = client.post("/api/auth/login", json={
        "role": "hacker",
        "email": "hacker@campus.edu",
        "password": "123"
    })
    assert res_bad_role.status_code == 400


def test_delete_booking_and_slot_release(client):
    """Deletion check: Student cannot delete CONFIRMED (403), Admin can (200), slot is freed for new booking (201)."""
    state = client.get("/api/state").get_json()
    confirmed = next(b for b in state["bookings"] if b["id"] == 101)  # Main Auditorium, 10:00-13:00

    # 1. Student attempts to delete confirmed booking #101 -> 403 Forbidden
    res_student_del = client.delete("/api/bookings/101", json={"role": "student"})
    assert res_student_del.status_code == 403
    assert "Students can only withdraw" in res_student_del.get_json()["error"]

    # 2. A conflicting booking attempt still fails (409)
    res_conflict = client.post("/api/bookings", json={
        "title": "Conflicting Slot Attempt",
        "club": "Coding Club",
        "venueId": confirmed["venueId"],
        "date": confirmed["date"],
        "start": "11:00",
        "end": "12:00",
        "attendees": 50,
        "equip": []
    })
    assert res_conflict.status_code == 409

    # 3. Admin deletes confirmed booking #101 -> 200 OK
    res_admin_del = client.delete("/api/bookings/101", json={"role": "admin"})
    assert res_admin_del.status_code == 200
    assert res_admin_del.get_json()["ok"] is True

    # Verify #101 is no longer in bookings
    state_after = client.get("/api/state").get_json()
    assert not any(b["id"] == 101 for b in state_after["bookings"])

    # 4. The same booking attempt on the freed slot now succeeds (201 Created)
    res_success = client.post("/api/bookings", json={
        "title": "Conflicting Slot Attempt Now Freed",
        "club": "Coding Club",
        "venueId": confirmed["venueId"],
        "date": confirmed["date"],
        "start": "11:00",
        "end": "12:00",
        "attendees": 50,
        "equip": []
    })
    assert res_success.status_code == 201
    assert res_success.get_json()["ok"] is True