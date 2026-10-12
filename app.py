import streamlit as st
import sqlite3
import pandas as pd
from PIL import Image
from pathlib import Path
from datetime import date
import uuid
import cv2
import numpy as np
import av
import time
import threading
from datetime import datetime
from streamlit_webrtc import webrtc_streamer, WebRtcMode
from deepface import DeepFace

# --- Page Configuration ---

st.set_page_config(
    page_title="FaceAttend AI",
    page_icon="🎓",
    layout="wide"
)

# --- Folders and Database ---

BASE_DIR = Path(__file__).parent
PHOTO_DIR = BASE_DIR / "student_photos"
PHOTO_DIR.mkdir(exist_ok=True)

DB_PATH = BASE_DIR / "attendance.db"


# Open a connection to the SQLite database.
def get_connection():
    return sqlite3.connect(DB_PATH)


# Create the student and attendance tables if they do not exist.
def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            department TEXT,
            email TEXT,
            photo_path TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            attendance_date TEXT NOT NULL,
            attendance_time TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Present',
            UNIQUE(student_id, attendance_date),
            FOREIGN KEY(student_id)
                REFERENCES students(student_id)
        )
    """)

    conn.commit()
    conn.close()


create_tables()


# --- Database Functions ---

# Fetch all registered students.
def get_students():
    conn = get_connection()

    df = pd.read_sql_query(
        "SELECT * FROM students ORDER BY name",
        conn
    )

    conn.close()
    return df


# Add a new student and save the student's photo path.
def add_student(student_id, name, department, email, photo_path):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO students
            (student_id, name, department, email,
             photo_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            student_id,
            name,
            department,
            email,
            str(photo_path),
            str(date.today())
        ))

        conn.commit()
        return True

    except sqlite3.IntegrityError:
        return False

    finally:
        conn.close()


# Update student details and optionally replace the photo.
def update_student(
    student_id,
    name,
    department,
    email,
    photo_path=None
):
    conn = get_connection()

    try:
        if photo_path is not None:
            conn.execute("""
                UPDATE students
                SET name = ?,
                    department = ?,
                    email = ?,
                    photo_path = ?
                WHERE student_id = ?
            """, (
                name,
                department,
                email,
                str(photo_path),
                student_id
            ))

        else:
            conn.execute("""
                UPDATE students
                SET name = ?,
                    department = ?,
                    email = ?
                WHERE student_id = ?
            """, (
                name,
                department,
                email,
                student_id
            ))

        conn.commit()
        return True

    except Exception:
        conn.rollback()
        return False

    finally:
        conn.close()


# Delete a student, their attendance records, and their photo.
def delete_student(student_id, photo_path):
    conn = get_connection()

    try:
        conn.execute(
            "DELETE FROM attendance WHERE student_id = ?",
            (student_id,)
        )

        conn.execute(
            "DELETE FROM students WHERE student_id = ?",
            (student_id,)
        )

        conn.commit()

        path = Path(photo_path)
        if path.exists():
            path.unlink()

        return True

    except Exception:
        conn.rollback()
        return False

    finally:
        conn.close()

# Fetch attendance records along with student details.
def get_attendance():
    conn = get_connection()

    df = pd.read_sql_query("""
        SELECT
            students.student_id,
            students.name,
            attendance.attendance_date,
            attendance.attendance_time,
            attendance.status
        FROM attendance
        JOIN students
        ON students.student_id = attendance.student_id
        ORDER BY attendance.attendance_date DESC,
                 attendance.attendance_time DESC
    """, conn)

    conn.close()
    return df


# --- Face Recognition with DeepFace ---

FACE_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades
    + "haarcascade_frontalface_default.xml"
)

# Facenet512 cosine-distance threshold.
# Lower distance means a closer match.
MATCH_THRESHOLD = 0.30

REQUIRED_MATCHES = 5


# Detect the largest face and prepare it for recognition.
def prepare_face(image):
    """Detect the largest face and return its color crop."""

    if image is None:
        return None, None

    if len(image.shape) == 2:
        gray = image
    else:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    faces = FACE_CASCADE.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(60, 60)
    )

    if len(faces) == 0:
        return None, None

    x, y, w, h = max(
        faces,
        key=lambda face: face[2] * face[3]
    )

    # Keep the color information for DeepFace.
    face = image[y:y + h, x:x + w]

    if len(face.shape) == 2:
        face = cv2.cvtColor(face, cv2.COLOR_GRAY2BGR)

    face = cv2.resize(face, (160, 160))

    return face, (x, y, w, h)


# Convert a face image into a numerical face embedding.
def get_face_embedding(face):
    """Convert a face image into a numerical representation."""

    result = DeepFace.represent(
        img_path=face,
        model_name="Facenet512",
        detector_backend="skip",
        enforce_detection=False
    )

    return np.array(result[0]["embedding"], dtype=np.float32)


# Compare two face embeddings using cosine distance.
def cosine_distance(embedding1, embedding2):
    """Calculate the distance between two face embeddings."""

    norm1 = np.linalg.norm(embedding1)
    norm2 = np.linalg.norm(embedding2)

    if norm1 == 0 or norm2 == 0:
        return 1.0

    similarity = np.dot(embedding1, embedding2) / (norm1 * norm2)

    return float(1.0 - similarity)


@st.cache_data(show_spinner="Loading registered face data...")

# Generate and cache embeddings for all registered students.
def build_student_embeddings(student_records):
    """
    Generate and cache one face embedding per registered student.

    The cache is refreshed when a student's photo file changes
    or a student is added.
    """

    embeddings = []

    for student_id, name, photo_path, modified_time in student_records:

        path = Path(photo_path)

        if not path.exists():
            continue

        image = cv2.imread(str(path))

        if image is None:
            continue

        face, _ = prepare_face(image)

        if face is None:
            continue

        try:
            embedding = get_face_embedding(face)

            embeddings.append({
                "student_id": student_id,
                "name": name,
                "embedding": embedding
            })

        except Exception as error:
            print(
                f"Could not process photo for {name}: {error}"
            )

    return embeddings


# Clear cached embeddings after a student photo changes.
def refresh_face_embeddings():
    build_student_embeddings.clear()


# Record attendance once per student per day.
def mark_attendance(student_id):
    """Save one attendance record per student per day."""

    now = datetime.now()

    conn = get_connection()

    try:
        conn.execute("""
            INSERT OR IGNORE INTO attendance
            (student_id, attendance_date, attendance_time, status)
            VALUES (?, ?, ?, 'Present')
        """, (
            student_id,
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M:%S")
        ))

        conn.commit()

    finally:
        conn.close()


# Process webcam frames, recognize faces, and mark attendance.
class FaceAttendanceProcessor:

    def __init__(self, student_embeddings):
        self.student_embeddings = student_embeddings

        self.match_counts = {}
        self.marked_this_session = set()
        self.lock = threading.Lock()

        self.frame_count = 0
        self.last_result = None

    # Process each incoming webcam frame.
    def recv(self, frame):

        image = frame.to_ndarray(format="bgr24")

        self.frame_count += 1

        # Run face recognition every 5 frames to reduce workload.
        if self.frame_count % 5 == 0:

            face, box = prepare_face(image)

            if face is None:
                self.last_result = None

            else:
                try:
                    live_embedding = get_face_embedding(face)

                    best_match = None
                    best_distance = float("inf")

                    for student in self.student_embeddings:

                        distance = cosine_distance(
                            live_embedding,
                            student["embedding"]
                        )

                        if distance < best_distance:
                            best_distance = distance
                            best_match = student

                    if (
                        best_match is not None
                        and best_distance < MATCH_THRESHOLD
                    ):
                        self.last_result = (
                            best_match,
                            best_distance,
                            box
                        )
                    else:
                        self.last_result = (
                            None,
                            best_distance,
                            box
                        )

                except Exception as error:
                    print("Face recognition error:", error)
                    self.last_result = None

        # Draw the most recent recognition result.
        if self.last_result is not None:

            student, distance, box = self.last_result

            x, y, w, h = box

            if student is not None:

                student_id = student["student_id"]
                name = student["name"]

                with self.lock:

                    self.match_counts[student_id] = (
                        self.match_counts.get(student_id, 0) + 1
                    )

                    count = self.match_counts[student_id]

                    if (
                        count >= REQUIRED_MATCHES
                        and student_id not in self.marked_this_session
                    ):
                        mark_attendance(student_id)
                        self.marked_this_session.add(student_id)

                if count >= REQUIRED_MATCHES:
                    label_text = f"{name} | Attendance marked"
                else:
                    label_text = f"{name} | Verifying..."

                color = (0, 255, 0)

            else:
                label_text = "Unknown face"
                color = (0, 0, 255)

            cv2.rectangle(
                image,
                (x, y),
                (x + w, y + h),
                color,
                2
            )

            cv2.putText(
                image,
                label_text,
                (x, max(y - 10, 25)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                color,
                2
            )

        return av.VideoFrame.from_ndarray(
            image,
            format="bgr24"
        )


# --- Website Header ---

st.title("🎓 FaceAttend AI")
st.caption("Face Recognition Based Student Attendance System")

st.divider()


# --- Sidebar Navigation ---

st.sidebar.title("Navigation")

page = st.sidebar.radio(
    "Choose a page",
    [
        "Dashboard",
        "Register Student",
        "Student Directory",
        "Live Attendance",
        "Attendance Records"
    ]
)


# --- Dashboard ---

if page == "Dashboard":

    students = get_students()
    attendance = get_attendance()

    today = str(date.today())

    today_attendance = attendance[
        attendance["attendance_date"] == today
    ]

    total_students = len(students)
    present_today = len(today_attendance)
    absent_today = total_students - present_today

    col1, col2, col3 = st.columns(3)

    col1.metric("Total Students", total_students)
    col2.metric("Present Today", present_today)
    col3.metric("Not Marked Present", absent_today)

    st.subheader("Today's Attendance")

    if today_attendance.empty:
        st.info("No attendance has been marked today.")
    else:
        st.dataframe(
            today_attendance,
            use_container_width=True,
            hide_index=True
        )

    st.subheader("Recent Students")

    if students.empty:
        st.info("No students registered yet.")
    else:
        st.dataframe(
            students[
                ["student_id", "name", "department", "email"]
            ].head(5),
            use_container_width=True,
            hide_index=True
        )


# --- Register Student ---

elif page == "Register Student":

    st.header("Register a New Student")

    st.write(
        "Enter the student's details and upload a recent, "
        "clear photograph."
    )

    with st.form("student_registration"):

        student_id = st.text_input(
            "Student ID / USN",
            placeholder="Example: 1DS23IS001"
        ).strip()

        name = st.text_input(
            "Full Name",
            placeholder="Enter student's name"
        ).strip()

        department = st.text_input(
            "Department",
            placeholder="Example: Information Science"
        ).strip()

        email = st.text_input(
            "Email Address",
            placeholder="student@example.com"
        ).strip()

        uploaded_photo = st.file_uploader(
            "Upload Student Photo",
            type=["jpg", "jpeg", "png"]
        )

        submitted = st.form_submit_button(
            "Register Student",
            use_container_width=True
        )

        if submitted:

            if not student_id or not name:
                st.error("Student ID and name are required.")

            elif uploaded_photo is None:
                st.error("Please upload a student photograph.")

            else:
                try:
                    image = Image.open(uploaded_photo).convert("RGB")

                    if image.width < 100 or image.height < 100:
                        st.error(
                            "Please upload a larger, clearer image."
                        )

                    else:
                        filename = f"{uuid.uuid4().hex}.jpg"
                        photo_path = PHOTO_DIR / filename

                        image.save(photo_path, quality=95)

                        success = add_student(
                            student_id,
                            name,
                            department,
                            email,
                            photo_path
                        )

                        if success:
                            st.success(
                                f"{name} registered successfully!"
                            )

                            st.image(
                                image,
                                caption=f"{name} — {student_id}",
                                width=250
                            )

                        else:
                            photo_path.unlink(missing_ok=True)

                            st.error(
                                "This Student ID is already registered."
                            )

                except Exception as error:
                    st.error(
                        f"Could not register student: {error}"
                    )


# --- Student Directory ---

    st.header("Student Directory")

    students = get_students()

    if students.empty:
        st.info("No students registered yet.")

    else:
        search = st.text_input(
            "Search by name or student ID"
        ).strip().lower()

        if search:
            filtered = students[
                students["name"].str.lower().str.contains(
                    search, na=False
                )
                |
                students["student_id"].str.lower().str.contains(
                    search, na=False
                )
            ]
        else:
            filtered = students

        st.write(f"Showing {len(filtered)} student(s)")

        for _, student in filtered.iterrows():

            with st.expander(
                f"{student['name']} — {student['student_id']}"
            ):

                col1, col2 = st.columns([1, 2])

                with col1:
                    photo_path = Path(student["photo_path"])

                    if photo_path.exists():
                        st.image(
                            str(photo_path),
                            width=180
                        )
                    else:
                        st.warning("Student photo not found.")

                with col2:
                    st.write(
                        f"**Department:** "
                        f"{student['department'] or 'Not provided'}"
                    )

                    st.write(
                        f"**Email:** "
                        f"{student['email'] or 'Not provided'}"
                    )

                    st.write(
                        f"**Registered:** {student['created_at']}"
                    )


elif page == "Student Directory":

    st.header("Student Directory")

    students = get_students()

    if students.empty:
        st.info("No students registered yet.")

    else:
        search = st.text_input(
            "Search by name or student ID"
        ).strip().lower()

        if search:
            filtered = students[
                students["name"].str.lower().str.contains(
                    search, na=False
                )
                |
                students["student_id"].str.lower().str.contains(
                    search, na=False
                )
            ]
        else:
            filtered = students

        st.write(f"Showing {len(filtered)} student(s)")

        for _, student in filtered.iterrows():

            with st.expander(
                f"{student['name']} — {student['student_id']}"
            ):

                col1, col2 = st.columns([1, 2])

                with col1:
                    photo_path = Path(student["photo_path"])

                    if photo_path.exists():
                        st.image(
                            str(photo_path),
                            width=180
                        )
                    else:
                        st.warning("Student photo not found.")

                with col2:
                    st.write(
                        f"**Department:** "
                        f"{student['department'] or 'Not provided'}"
                    )

                    st.write(
                        f"**Email:** "
                        f"{student['email'] or 'Not provided'}"
                    )

                    st.write(
                        f"**Registered:** {student['created_at']}"
                    )

                st.divider()

                edit_col, delete_col = st.columns(2)

                with edit_col:

                    if st.button(
                        "✏️ Edit Student",
                        key=f"edit_{student['student_id']}"
                    ):
                        st.session_state[
                            f"editing_{student['student_id']}"
                        ] = True

                with delete_col:

                    if st.button(
                        "🗑️ Delete Student",
                        key=f"delete_{student['student_id']}"
                    ):
                        st.session_state[
                            f"deleting_{student['student_id']}"
                        ] = True

                if st.session_state.get(
                    f"editing_{student['student_id']}",
                    False
                ):

                    st.subheader("Edit Student Details")

                    with st.form(
                        f"edit_form_{student['student_id']}"
                    ):

                        edited_name = st.text_input(
                            "Full Name",
                            value=student["name"]
                        )

                        edited_department = st.text_input(
                            "Department",
                            value=student["department"] or ""
                        )

                        edited_email = st.text_input(
                            "Email Address",
                            value=student["email"] or ""
                        )

                        edited_photo = st.file_uploader(
                            "Change Student Photo (optional)",
                            type=["jpg", "jpeg", "png"]
                        )

                        save_changes = st.form_submit_button(
                            "Save Changes"
                        )


                        if save_changes:

                            if not edited_name.strip():

                                st.error(
                                    "Student name cannot be empty."
                                )

                            else:

                                old_photo_path = Path(
                                    student["photo_path"]
                                )

                                new_photo_path = None

                                try:

                                    if edited_photo is not None:

                                        image = Image.open(
                                            edited_photo
                                        ).convert("RGB")

                                        if image.width < 100 or image.height < 100:

                                            st.error(
                                                "Please upload a larger, clearer image."
                                            )

                                        else:

                                            filename = (
                                                f"{uuid.uuid4().hex}.jpg"
                                            )

                                            new_photo_path = (
                                                PHOTO_DIR / filename
                                            )

                                            image.save(
                                                new_photo_path,
                                                quality=95
                                            )

                                    if (
                                        edited_photo is None
                                        or new_photo_path is not None
                                    ):

                                        success = update_student(
                                            student["student_id"],
                                            edited_name.strip(),
                                            edited_department.strip(),
                                            edited_email.strip(),
                                            new_photo_path
                                        )

                                        if success:

                                            if (
                                                new_photo_path is not None
                                                and old_photo_path.exists()
                                            ):
                                                old_photo_path.unlink()

                                            # Refresh cached face embeddings
                                            if new_photo_path is not None:
                                                refresh_face_embeddings()

                                            st.success(
                                                "Student details updated successfully."
                                            )

                                            st.session_state[
                                                f"editing_{student['student_id']}"
                                            ] = False

                                            st.rerun()

                                        else:

                                            if (
                                                new_photo_path is not None
                                                and new_photo_path.exists()
                                            ):
                                                new_photo_path.unlink()

                                            st.error(
                                                "Could not update student details."
                                            )

                                except Exception as error:

                                    if (
                                        new_photo_path is not None
                                        and new_photo_path.exists()
                                    ):
                                        new_photo_path.unlink()

                                    st.error(
                                        f"Could not update student: {error}"
                                    )

                if st.session_state.get(
                    f"deleting_{student['student_id']}",
                    False
                ):

                    st.warning(
                        f"Are you sure you want to delete "
                        f"{student['name']}?"
                    )

                    confirm_col, cancel_col = st.columns(2)

                    with confirm_col:

                        if st.button(
                            "Yes, Delete",
                            key=f"confirm_delete_{student['student_id']}"
                        ):

                            success = delete_student(
                                student["student_id"],
                                student["photo_path"]
                            )

                            if success:
                                st.success(
                                    "Student deleted successfully."
                                )

                                st.session_state[
                                    f"deleting_{student['student_id']}"
                                ] = False

                                st.rerun()

                            else:
                                st.error(
                                    "Could not delete student."
                                )

                    with cancel_col:

                        if st.button(
                            "Cancel",
                            key=f"cancel_delete_{student['student_id']}"
                        ):

                            st.session_state[
                                f"deleting_{student['student_id']}"
                            ] = False

                            st.rerun()

# --- Live Attendance ---

elif page == "Live Attendance":

    st.header("Live Face Recognition Attendance")

    st.write(
        "Start the webcam to identify registered students "
        "and mark attendance."
    )

    students = get_students()

    student_records = tuple(
        (
            row["student_id"],
            row["name"],
            row["photo_path"],
            Path(row["photo_path"]).stat().st_mtime
            if Path(row["photo_path"]).exists()
            else 0
        )
        for _, row in students.iterrows()
    )

    student_embeddings = build_student_embeddings(student_records)

    if not student_embeddings:
        st.warning(
            "No usable student face photos were found. "
            "Register students with clear, front-facing photos first."
        )

    else:
        st.info(
            f"{len(student_embeddings)} student face(s) loaded. "
            "Keep one face visible at a time for this prototype."
        )

        processor = FaceAttendanceProcessor(student_embeddings)

        webrtc_streamer(
            key="faceattend-live",
            mode=WebRtcMode.SENDRECV,
            video_frame_callback=processor.recv,
            media_stream_constraints={
                "video": True,
                "audio": False
            },
            async_processing=True
        )

    st.divider()

    st.subheader("Today's Attendance")

    attendance = get_attendance()

    today = str(date.today())

    today_attendance = attendance[
        attendance["attendance_date"] == today
    ]

    if today_attendance.empty:
        st.info("No attendance marked today yet.")
    else:
        st.dataframe(
            today_attendance,
            use_container_width=True,
            hide_index=True
        )

        csv_data = today_attendance.to_csv(
            index=False
        ).encode("utf-8")

        st.download_button(
            "Download Today's Attendance",
            data=csv_data,
            file_name=f"attendance_{today}.csv",
            mime="text/csv"
        )


# --- Attendance Records ---

elif page == "Attendance Records":

    st.header("Attendance Records")

    attendance = get_attendance()

    if attendance.empty:
        st.info(
            "No attendance records yet. "
            "Face recognition attendance will be added next."
        )

    else:
        st.dataframe(
            attendance,
            use_container_width=True,
            hide_index=True
        )

        csv_data = attendance.to_csv(index=False).encode("utf-8")

        st.download_button(
            "Download Attendance CSV",
            data=csv_data,
            file_name="attendance_records.csv",
            mime="text/csv"
        )