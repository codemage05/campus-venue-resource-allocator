# Campus Venue & Event Resource Allocator 🏛️📅

An interactive, full-stack Software Engineering PBL project designed to manage campus event bookings, prevent temporal double-bookings, and enforce role-based approval workflows across student organizations, faculty advisors, and facilities administrators.

## 🎯 Software Engineering Highlights
* **Requirements Engineering (Unit 1):** Complete [IEEE 830 Software Requirements Specification (SRS)](./docs/srs_ieee830.md) with Functional, Non-Functional requirements, and COCOMO effort estimation.
* **System Modeling & UML (Unit 2):** Full [Mermaid UML Suite](./docs/uml_diagrams.md) including Use Case, State Machine, Sequence, and Class diagrams.
* **Architectural Design (Unit 3):** Decoupled Client-Server REST architecture with a Finite State Machine (FSM) workflow engine.
* **Verification & Testing (Unit 4):** Automated `pytest` test suite covering Equivalence Partitioning, Boundary Value Analysis (BVA), and RBAC state enforcement.

## 🚀 Quick Start

### 1. Set up the Backend & run the Automated Unit Tests
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Run the automated unit test suite (22 test cases)
pytest -v
```

### 2. Start the App
```bash
# From backend/ with the venv active
python app.py
```
Then open **http://localhost:5000/** — Flask serves the React frontend and the REST API from the same origin.

> You can also open `frontend/index.html` directly in a browser. It will talk to the Flask API at `http://localhost:5000/api`
> if it is running, and otherwise switch to **Local fallback mode** (shown by the badge in the header) using client-side validation.

## 🔐 Role Authentication & Demo Credentials
* **Student Coordinator:** Public guest access (no password required). Can draft requests and withdraw own pending/rejected requests.
* **Faculty Advisor:** `faculty@campus.edu` / `faculty123` (Approve/Reject requests, delete events).
* **Facilities Admin:** `admin@campus.edu` / `admin123` (Confirm final allocations, delete events, monitor utilization).
* *Viva Feature:* The login modal includes a **"1-Click Auto-Fill"** button for instant demonstration.

## 🔌 REST API
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Liveness check |
| `GET` | `/api/state` | All bookings, audit log and conflict log |
| `POST` | `/api/auth/login` | Role authentication (`200` with user details, or `401` unauthorized) |
| `POST` | `/api/bookings` | Create a booking (`201`, or `400` invalid / `409` time conflict) |
| `PATCH` | `/api/bookings/<id>/status` | Body `{to, role, remark}` (`200`, or `403` illegal transition / `404` / `409`) |
| `DELETE` | `/api/bookings/<id>` | Body or param `{role}`: Delete booking (`200`, `403` if unauthorized, `404`) |
| `POST` | `/api/reset` | Restore the seed data |

## 📁 Project Structure
```
campus-venue-resource-allocator/
├── backend/
│   ├── app.py              # Flask REST API, State Machine & Conflict Engine
│   ├── test_app.py         # Automated Unit & Boundary Testing Suite (Pytest)
│   └── requirements.txt    # Flask, flask-cors, pytest
├── frontend/
│   └── index.html          # React (CDN) single-page client wired to Flask
├── docs/
│   ├── srs_ieee830.md      # Formal IEEE 830 Software Requirements Specification
│   └── uml_diagrams.md     # Use Case, Class, Sequence & State Machine Diagrams
└── README.md
```

> [!NOTE]
> Data is held in memory, so restarting the server resets it to the seed bookings.