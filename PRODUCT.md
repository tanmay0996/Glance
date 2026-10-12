# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Faculty or class coordinators who register students once and then take attendance at the start of a class from a laptop with a webcam *(inferred from the app's workflow; the user declined an interview)*. Secondary audience: evaluators reviewing the project as an academic submission *(inferred)*.

## Product Purpose
Glance replaces roll-call: a student looks at the webcam, is recognised against their registered photo, and is marked present once per day. Success is a class taken with no paper sheet and no name-calling, and a clean, exportable record afterwards.

## Positioning
Attendance by being seen, not by signing: a short, verified look at the camera (several consecutive matches, not one frame) is the whole act of checking in.

## Operating Context
- Single-operator tool running locally (`streamlit run app.py`) at `localhost:8501`; webcam access through the browser.
- Workflow: register student (ID, name, department, email, photo) → Live attendance (webcam) → review today / history → download CSV.
- Usually one face in frame at a time; lighting and a front-facing photo affect accuracy.

## Capabilities and Constraints
- Pure Python / Streamlit frontend — a hard constraint from the user. No separate JS framework.
- Recognition: OpenCV Haar cascade + DeepFace Facenet512 embeddings, cosine distance < 0.30, 5 matches to confirm.
- Storage: local SQLite (`attendance.db`) and `student_photos/`. One attendance row per student per day.
- Pages: Overview/dashboard, Register, Students (search, edit, delete), Live attendance, Records (history + CSV).

## Brand Commitments
- Name: **Glance** (user-confirmed). Previous working name "FaceAttend AI" is retired.

## Evidence on Hand
- No logo, imagery, testimonials, institution branding, or usage metrics exist. Do not invent institutions, accuracy figures, or user counts.

## Product Principles
1. The check-in moment is the product: the live screen must make "recognised → verifying → marked" unmistakable.
2. Every record is traceable to a person and a time; never hide who is missing.
3. Local and private by default — student photos never leave the machine.
4. One operator, few clicks: registering and taking attendance should need no manual.
