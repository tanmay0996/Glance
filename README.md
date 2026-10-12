# FaceAttend AI

FaceAttend AI is a student attendance system that uses webcam-based face recognition to identify registered students and mark attendance automatically.

## Project Overview

This project is built to reduce manual attendance work in classrooms. Instead of writing names or checking attendance sheets, the system captures a live face from the webcam, compares it with stored student face data, and marks the student as present if the match is valid.

The main idea is simple:
- register student details and photo
- save the face data
- detect face from webcam
- compare it with registered faces
- mark attendance when the match is correct

## Main Logic / Workflow
<img width="600" alt="FaceAttend AI Workflow Infographic" src="https://github.com/user-attachments/assets/2dbf965c-6ff3-4b9d-b3ed-18d00a3ae3c2" />

## Technologies Used

| Technology | Purpose |
|---|---|
| **Python** | Main programming language used for the entire project |
| **Streamlit** | Creates the web application interface for student registration and attendance |
| **OpenCV** | Detects faces in uploaded images and webcam frames |
| **DeepFace** | Provides face recognition functionality and generates face embeddings |
| **FaceNet512** | Creates numerical face representations for comparing faces |
| **SQLite** | Stores student records and attendance information locally |
| **Pandas** | Handles and displays tabular data such as student and attendance records |
| **NumPy** | Performs numerical calculations and embedding comparison |
| **Pillow** | Processes uploaded student images |
| **streamlit-webrtc** | Connects the browser webcam to the application for live video streaming |

## How to Download the Project

```bash
git clone https://github.com/TeliMushera/FaceAttendAI.git
cd FaceAttendAI
```

## How to Run the Project

### 1. Create a virtual environment

```bash
python -m venv .venv
```

### 2. Activate the environment

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
FaceAttendAI/
├── app.py
├── requirements.txt
├── attendance.db
├── student_photos/
├── README.md
├── .gitignore
└── .python-version
```

## Important Notes

- Use a clear and front-facing photo for better recognition.
- Good lighting improves accuracy.
- Keep only one face in front of the camera for best results.
- This project stores data locally in SQLite for academic/demo use.

## Main Purpose

The main purpose of FaceAttend AI is to automate attendance using face recognition and make attendance marking faster, easier, and more accurate.
