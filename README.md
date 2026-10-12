# Glance

Attendance at a glance — students are recognised by webcam and stamped present.

## Project Overview

Glance replaces the paper attendance sheet. A student is registered once with their details and a photo. After that, the webcam captures a live face, compares it with the stored face data, and marks the student present when the match is valid.

The flow:
- register student details and a photo
- save the face data
- detect a face from the webcam
- compare it with registered faces
- mark attendance when the match is correct

## Main Logic / Workflow
<img width="600" alt="Glance workflow infographic" src="https://github.com/user-attachments/assets/2dbf965c-6ff3-4b9d-b3ed-18d00a3ae3c2" />

## Pages

| Page | What it does |
|---|---|
| **Today** | Who is present and who is still missing for today's date |
| **Take attendance** | Opens the webcam, recognises faces and marks matched students present |
| **Students** | Lists registered students and their details |
| **Add student** | Registers a new student with ID, name, department, email and photo |
| **Records** | Attendance history across past dates |

## Technologies Used

| Technology | Purpose |
|---|---|
| **Python** | Main programming language for the project |
| **Streamlit** | Web interface for registration, attendance and records |
| **OpenCV** | Detects faces in uploaded images and webcam frames |
| **DeepFace** | Face recognition and face embeddings |
| **FaceNet512** | Numerical face representations used to compare faces |
| **SQLite** | Stores student records and attendance locally |
| **Pandas** | Handles and displays student and attendance tables |
| **NumPy** | Numerical work and embedding comparison |
| **Pillow** | Processes uploaded student images |
| **streamlit-webrtc** | Connects the browser webcam to the app for live video |

## How to Download the Project

```bash
git clone https://github.com/tanmay0996/Glance.git
cd Glance
```

## How to Run the Project

### 1. Create a virtual environment

```bash
python -m venv .venv
```

### 2. Activate the environment

Linux / macOS:

```bash
source .venv/bin/activate
```

Windows:

```bash
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Start the app

```bash
python -m streamlit run app.py
```

Then open the local URL shown in the terminal, usually:

```text
http://localhost:8501
```

## Project Structure

```text
Glance/
├── .streamlit/
│   └── config.toml      # Streamlit theme and server settings
├── app.py               # The Streamlit app
├── styles.css           # Custom styles loaded by the app
├── requirements.txt
├── attendance.db        # Created on first run (gitignored)
├── student_photos/      # Registered photos (gitignored)
├── PRODUCT.md           # Product notes: users, purpose, scope
├── DESIGN.md            # Design notes: visual system and UI decisions
├── README.md
├── .gitignore
└── .python-version
```

## Important Notes

- Use a clear, front-facing photo when registering a student.
- Good lighting helps recognition.
- Keep one face in front of the camera at a time.
- All data is stored locally in SQLite; this project is meant for academic/demo use.
