# Software Requirements Specification (SRS)
**Standard:** IEEE Std 830 / ISO/IEC/IEEE 29148  
**Project:** Campus Venue & Event Resource Allocator  

## 1. Introduction
### 1.1 Purpose
This document specifies the functional and non-functional requirements for the Campus Venue & Event Resource Allocator, a multi-role workflow system designed to eliminate double-bookings, enforce venue capacity limits, and provide an immutable audit trail for student chapter events.

### 1.2 Scope
The system manages 4 primary campus venues (Main Auditorium, Seminar Hall A, CSE AI & Robotics Lab, Open Air Amphitheatre) across 3 distinct organizational actors: Student Coordinator, Faculty Advisor, and Facilities Admin.

## 2. Overall Description
### 2.1 User Classes and Characteristics
1. **Student Coordinator:** Initiates event booking requests, specifies expected attendance, and selects AV/compute equipment.
2. **Faculty Advisor:** Reviews pending requests for academic alignment and approves or rejects them with remarks.
3. **Facilities Admin:** Performs final resource allocation, monitors daily venue utilization percentages, and inspects conflict logs.

## 3. Specific Requirements

### 3.1 Functional Requirements (FR)
* **FR-01 (Role-Based Access Control):** The system shall restrict UI actions and API state transitions based on the active actor role (`student`, `faculty`, `admin`).
* **FR-02 (Capacity Boundary Enforcement):** The system shall reject any booking request where `expected_attendees > venue.capacity` or `expected_attendees < 1`.
* **FR-03 (Chronological Validation):** The system shall verify that `end_time > start_time` for all booking requests.
* **FR-04 (Temporal Conflict Detection):** The system shall block any booking creation or approval if another booking in the `APPROVED_FACULTY` or `CONFIRMED` state occupies the same venue on the same date where $Start_A < End_B \land End_A > Start_B$.
* **FR-05 (Finite State Machine Enforcement):**
  * `PENDING_FACULTY` $\rightarrow$ `APPROVED_FACULTY` | `REJECTED` (Authorized: `faculty` only).
  * `APPROVED_FACULTY` $\rightarrow$ `CONFIRMED` | `REJECTED` (Authorized: `admin` only).
* **FR-06 (Audit & Conflict Logging):** Every state mutation and blocked conflict attempt shall be recorded with a timestamp and actor identifier.

### 3.2 Non-Functional Requirements (NFR)
* **NFR-01 (Performance):** Conflict detection and state transition API calls shall execute in $< 50\text{ ms}$.
* **NFR-02 (Reliability & Graceful Degradation):** If the backend server is unreachable, the frontend client shall gracefully fall back to client-side validation without crashing.
* **NFR-03 (Testability):** All core boundary and state-machine rules shall be verified via an automated `pytest` unit test suite.

## 4. COCOMO Effort Estimation (Basic Organic Mode)
Assuming an estimated source size of $\text{KLOC} = 0.65$ (650 lines of Python + React/JSX code):
* **Effort Applied ($E$):** $E = a_b (\text{KLOC})^{b_b} = 2.4 \times (0.65)^{1.05} \approx 1.53 \text{ Person-Months}$
* **Development Time ($D$):** $D = c_b (E)^{d_b} = 2.5 \times (1.53)^{0.38} \approx 2.94 \text{ Months}$