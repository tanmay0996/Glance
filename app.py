import streamlit as st
import sqlite3
import pandas as pd
import altair as alt
from PIL import Image
from pathlib import Path
from datetime import date, datetime, timedelta
from html import escape
import base64
import io
import uuid
import cv2
import numpy as np
import av
import threading
from streamlit_webrtc import webrtc_streamer, WebRtcMode
from deepface import DeepFace

# --- Page Configuration ---

BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"

st.set_page_config(
    page_title="Glance",
    page_icon=str(ASSETS_DIR / "glance-mark.svg"),
    layout="wide"
)

# --- Folders and Database ---

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

# Overlay colours on the webcam feed (BGR).
STAMP_BGR = (143, 43, 110)
UNKNOWN_BGR = (24, 35, 180)


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


# Generate and cache embeddings for all registered students.
@st.cache_data(show_spinner="Reading registered faces…")
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
                    label_text = f"{name} | Stamped present"
                else:
                    label_text = f"{name} | Verifying..."

                color = STAMP_BGR

            else:
                label_text = "Not recognised"
                color = UNKNOWN_BGR

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


# --- Interface Helpers ---

STAMP_HEX = "#6E2B8F"
MUTED_HEX = "#687387"
LINE_HEX = "#D5DBE1"
INK_HEX = "#15191F"


# Load the stylesheet once per run.
def inject_styles():
    css = (BASE_DIR / "styles.css").read_text(encoding="utf-8")
    st.html(f"<style>{css}</style>")


# Build a small base64 thumbnail so photos can sit inside HTML rows.
@st.cache_data(show_spinner=False)
def photo_data_uri(photo_path, modified_time, size=160):
    path = Path(photo_path)

    if not path.exists():
        return None

    try:
        image = Image.open(path).convert("RGB")
        image.thumbnail((size, size))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"

    except Exception:
        return None


def photo_mtime(photo_path):
    path = Path(photo_path)
    return path.stat().st_mtime if path.exists() else 0


def initials(name):
    parts = [part for part in str(name).split() if part]
    return "".join(part[0] for part in parts[:2]).upper() or "?"


def avatar_html(student):
    uri = photo_data_uri(
        student["photo_path"],
        photo_mtime(student["photo_path"]),
        96
    )

    if uri:
        return f'<img class="g-avatar" src="{uri}" alt="">'

    return f'<span class="g-avatar">{escape(initials(student["name"]))}</span>'


# The date stamp: Glance's single mark for "present".
def stamp_html(day, time_text=None, large=False):
    when = datetime.strptime(day, "%Y-%m-%d").strftime("%d %b").upper()
    detail = f"{when} · {time_text[:5]}" if time_text else when
    size = " lg" if large else ""

    return (
        f'<span class="g-stamp{size}" role="img" '
        f'aria-label="Present, {escape(detail)}">'
        f'<span class="k">Present</span>'
        f'<span class="v">{escape(detail)}</span>'
        f'</span>'
    )


def page_heading(title, subtitle=None, show_date=True):
    today_text = date.today().strftime("%a %d %b %Y").upper()
    date_html = f'<span class="g-date">{today_text}</span>' if show_date else ""
    sub_html = f'<p class="g-sub">{escape(subtitle)}</p>' if subtitle else ""

    st.html(
        f'<div class="g-head"><h1>{escape(title)}</h1>{date_html}</div>'
        f'{sub_html}'
    )


def section_label(title, count=None):
    count_html = (
        f'<span class="g-count">{count}</span>'
        if count is not None else ""
    )

    st.html(
        f'<div class="g-section"><h3>{escape(title)}</h3>{count_html}</div>'
    )


def today_roster():
    """Return every student with today's attendance time (or None)."""

    students = get_students()
    attendance = get_attendance()
    today = str(date.today())

    today_rows = attendance[attendance["attendance_date"] == today][
        ["student_id", "attendance_time"]
    ]

    roster = students.merge(today_rows, on="student_id", how="left")
    return roster, today


def present_rows_html(present, today, fresh_ids=()):
    if present.empty:
        return (
            '<div class="g-list"><div class="g-empty">'
            'No one stamped yet today. Start '
            '<b>Take attendance</b> and stamps will appear here.'
            '</div></div>'
        )

    rows = []

    for _, student in present.iterrows():
        fresh = " fresh" if student["student_id"] in fresh_ids else ""
        rows.append(
            f'<div class="g-row{fresh}">'
            f'{avatar_html(student)}'
            f'<div class="g-who"><div class="g-name">{escape(student["name"])}</div>'
            f'<div class="g-id">{escape(student["student_id"])}</div></div>'
            f'{stamp_html(today, student["attendance_time"])}'
            f'</div>'
        )

    return f'<div class="g-list">{"".join(rows)}</div>'


def missing_rows_html(missing):
    if missing.empty:
        return (
            '<div class="g-list"><div class="g-empty">'
            '<b>Everyone is stamped present.</b>'
            '</div></div>'
        )

    rows = []

    for _, student in missing.iterrows():
        rows.append(
            f'<div class="g-row">'
            f'{avatar_html(student)}'
            f'<div class="g-who"><div class="g-name">{escape(student["name"])}</div>'
            f'<div class="g-id">{escape(student["student_id"])}</div></div>'
            f'<span class="g-wait">Not yet marked</span>'
            f'</div>'
        )

    return f'<div class="g-list">{"".join(rows)}</div>'


def chart_config(chart):
    return chart.configure(
        font="Schibsted Grotesk",
        background="transparent"
    ).configure_view(
        stroke=None
    ).configure_axis(
        labelColor=MUTED_HEX,
        titleColor=MUTED_HEX,
        labelFont="Courier Prime",
        labelFontSize=11,
        titleFontSize=12,
        titleFontWeight=500,
        gridColor="#E3E8ED",
        domainColor=LINE_HEX,
        tickColor=LINE_HEX
    )


def save_photo(uploaded_file):
    """Validate an uploaded photo and save it. Returns (path, error)."""

    image = Image.open(uploaded_file).convert("RGB")

    if image.width < 100 or image.height < 100:
        return None, (
            "This photo is too small. Use one at least "
            "100 × 100 pixels."
        )

    face, _ = prepare_face(
        cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    )

    if face is None:
        return None, (
            "No face found in this photo. Use a front-facing photo "
            "with the whole face visible and good light."
        )

    photo_path = PHOTO_DIR / f"{uuid.uuid4().hex}.jpg"
    image.save(photo_path, quality=95)

    return photo_path, None


# --- Pages ---

def page_today():
    roster, today = today_roster()

    page_heading("Today")

    if roster.empty:
        st.html(
            '<p class="g-sub">No students yet. Add your class once, '
            'then take attendance with the webcam each day.</p>'
        )
        st.page_link(
            PAGE_ADD,
            label="Add your first student",
            icon=":material/person_add:"
        )
        return

    present = roster[roster["attendance_time"].notna()].sort_values(
        "attendance_time", ascending=False
    )
    missing = roster[roster["attendance_time"].isna()]

    total = len(roster)
    count = len(present)
    cells = "".join(
        '<i class="on"></i>' if index < count else "<i></i>"
        for index in range(total)
    )

    roll_col, action_col = st.columns([3, 1], vertical_alignment="bottom")

    with roll_col:
        st.html(
            f'<div class="g-roll">'
            f'<p class="g-roll-text"><b>{count}</b> of {total} stamped present'
            f' <span>· {total - count} not yet marked</span></p>'
            f'<div class="g-tally" style="--n:{total}" '
            f'aria-hidden="true">{cells}</div>'
            f'</div>'
        )

    with action_col:
        if st.button(
            "Take attendance",
            icon=":material/photo_camera:",
            type="primary",
            width="stretch"
        ):
            st.switch_page(PAGE_LIVE)

    st.space("small")

    left, right = st.columns(2, gap="large")

    with left:
        section_label("Stamped present", count)
        st.html(present_rows_html(present, today))

    with right:
        section_label("Not yet marked", total - count)
        st.html(missing_rows_html(missing))

    st.space("medium")
    render_daily_chart(roster)


def render_daily_chart(roster):
    attendance = get_attendance()

    if attendance.empty:
        return

    daily = (
        attendance.groupby("attendance_date")
        .size()
        .reset_index(name="present")
        .sort_values("attendance_date")
        .tail(14)
    )
    daily["day"] = pd.to_datetime(daily["attendance_date"])
    daily["label"] = daily["day"].dt.strftime("%d %b")

    section_label("Last 14 class days", f"of {len(roster)} students")

    chart = alt.Chart(daily).mark_bar(
        color=STAMP_HEX,
        cornerRadiusTopLeft=3,
        cornerRadiusTopRight=3,
        size=22
    ).encode(
        x=alt.X(
            "label:N",
            sort=None,
            title=None,
            axis=alt.Axis(labelAngle=0)
        ),
        y=alt.Y(
            "present:Q",
            title="Present",
            scale=alt.Scale(domain=[0, max(len(roster), 1)]),
            axis=alt.Axis(tickCount=4)
        ),
        tooltip=[
            alt.Tooltip("day:T", title="Date", format="%a %d %b"),
            alt.Tooltip("present:Q", title="Stamped present")
        ]
    ).properties(height=220)

    st.altair_chart(chart_config(chart), theme=None, width="stretch")


def page_live():
    page_heading(
        "Take attendance",
        "Ask each student to look at the camera for a moment. "
        "After five matching frames they are stamped present."
    )

    students = get_students()

    student_records = tuple(
        (
            row["student_id"],
            row["name"],
            row["photo_path"],
            photo_mtime(row["photo_path"])
        )
        for _, row in students.iterrows()
    )

    camera_col, feed_col = st.columns([3, 2], gap="large")

    with camera_col:
        student_embeddings = build_student_embeddings(student_records)

        if not student_embeddings:
            with st.container(border=True):
                st.markdown("**No faces to match against yet.**")
                st.write(
                    "Add students with a clear, front-facing photo, "
                    "then come back here."
                )
                st.page_link(
                    PAGE_ADD,
                    label="Add student",
                    icon=":material/person_add:"
                )

        else:
            processor = FaceAttendanceProcessor(student_embeddings)

            webrtc_streamer(
                key="glance-live",
                mode=WebRtcMode.SENDRECV,
                video_frame_callback=processor.recv,
                media_stream_constraints={
                    "video": True,
                    "audio": False
                },
                async_processing=True
            )

            st.html(
                f'<div class="g-live-hint">'
                f'<span><i class="g-dot ok"></i>Recognised, verifying</span>'
                f'<span><i class="g-dot no"></i>Not recognised</span>'
                f'<span>{len(student_embeddings)} of {len(students)} faces ready</span>'
                f'</div>'
            )

            skipped = len(students) - len(student_embeddings)
            if skipped:
                st.caption(
                    f"{skipped} student photo(s) have no detectable face "
                    "and can't be matched. Replace them from Students."
                )

    with feed_col:
        live_feed()


@st.fragment(run_every="2s")
def live_feed():
    roster, today = today_roster()

    present = roster[roster["attendance_time"].notna()].sort_values(
        "attendance_time", ascending=False
    )

    current_ids = set(present["student_id"])
    seen = st.session_state.get("seen_present")
    fresh_ids = current_ids - seen if seen is not None else set()
    st.session_state["seen_present"] = current_ids

    section_label("Stamped today", f"{len(present)} of {len(roster)}")
    st.html(present_rows_html(present, today, fresh_ids))

    if not present.empty:
        st.download_button(
            "Download today's list",
            data=present[["student_id", "name", "attendance_time"]]
            .rename(columns={"attendance_time": "time"})
            .to_csv(index=False)
            .encode("utf-8"),
            file_name=f"glance_attendance_{today}.csv",
            mime="text/csv",
            icon=":material/download:",
            type="tertiary"
        )


def page_students():
    students = get_students()

    page_heading(
        "Students",
        f"{len(students)} registered" if not students.empty else None,
        show_date=False
    )

    if students.empty:
        st.html(
            '<p class="g-sub">No students yet. Each student needs an ID, '
            'a name and one clear photo.</p>'
        )
        st.page_link(
            PAGE_ADD,
            label="Add student",
            icon=":material/person_add:"
        )
        return

    search_col, dept_col, add_col = st.columns(
        [3, 2, 1], vertical_alignment="bottom"
    )

    with search_col:
        search = st.text_input(
            "Search",
            placeholder="Name or student ID",
            icon=":material/search:"
        ).strip().lower()

    departments = sorted(
        department for department in students["department"].dropna().unique()
        if department
    )

    with dept_col:
        department = st.selectbox(
            "Department",
            ["All departments"] + departments
        )

    with add_col:
        if st.button(
            "Add student",
            icon=":material/person_add:",
            width="stretch"
        ):
            st.switch_page(PAGE_ADD)

    filtered = students

    if search:
        filtered = filtered[
            filtered["name"].str.lower().str.contains(search, na=False, regex=False)
            | filtered["student_id"].str.lower().str.contains(search, na=False, regex=False)
        ]

    if department != "All departments":
        filtered = filtered[filtered["department"] == department]

    if filtered.empty:
        st.info(
            "No students match. Check the spelling or clear the filters.",
            icon=":material/search_off:"
        )
        return

    roster, today = today_roster()
    times = dict(zip(roster["student_id"], roster["attendance_time"]))

    columns = st.columns(3, gap="medium")

    for position, (_, student) in enumerate(filtered.iterrows()):
        with columns[position % 3]:
            student_card(student, today, times.get(student["student_id"]))


def student_card(student, today, time_today):
    student_id = student["student_id"]

    with st.container(border=True):
        uri = photo_data_uri(
            student["photo_path"],
            photo_mtime(student["photo_path"])
        )
        photo = (
            f'<img src="{uri}" alt="Photo of {escape(student["name"])}">'
            if uri else '<span class="g-photo-empty">No photo</span>'
        )
        status = (
            stamp_html(today, time_today)
            if isinstance(time_today, str)
            else '<span>Not yet marked today</span>'
        )

        st.html(
            f'<div class="g-card">{photo}<div class="g-who">'
            f'<div class="g-name">{escape(student["name"])}</div>'
            f'<div class="g-id">{escape(student_id)}</div>'
            f'<ul class="g-meta">'
            f'<li>{escape(student["department"] or "No department")}</li>'
            f'<li>{escape(student["email"] or "No email")}</li>'
            f'</ul>'
            f'<div class="g-today">{status}</div>'
            f'</div></div>'
        )

        edit_col, delete_col = st.columns(2)

        with edit_col:
            with st.popover(
                "Edit",
                icon=":material/edit:",
                width="stretch"
            ):
                edit_form(student)

        with delete_col:
            with st.popover(
                "Delete",
                icon=":material/delete:",
                width="stretch"
            ):
                st.markdown(
                    f"Delete **{student['name']}** and all of their "
                    "attendance records? This can't be undone."
                )

                if st.button(
                    "Delete student",
                    key=f"confirm_delete_{student_id}",
                    type="primary",
                    icon=":material/delete:"
                ):
                    if delete_student(student_id, student["photo_path"]):
                        refresh_face_embeddings()
                        st.toast(
                            f"Deleted {student['name']}",
                            icon=":material/delete:"
                        )
                        st.rerun()
                    else:
                        st.error("Couldn't delete this student. Try again.")


def edit_form(student):
    student_id = student["student_id"]

    with st.form(f"edit_form_{student_id}", border=False):
        edited_name = st.text_input("Full name", value=student["name"])
        edited_department = st.text_input(
            "Department", value=student["department"] or ""
        )
        edited_email = st.text_input(
            "Email", value=student["email"] or ""
        )
        edited_photo = st.file_uploader(
            "Replace photo (optional)",
            type=["jpg", "jpeg", "png"],
            key=f"edit_photo_{student_id}"
        )

        save_changes = st.form_submit_button(
            "Save changes",
            type="primary",
            icon=":material/check:"
        )

    if not save_changes:
        return

    if not edited_name.strip():
        st.error("Name can't be empty.")
        return

    old_photo_path = Path(student["photo_path"])
    new_photo_path = None

    try:
        if edited_photo is not None:
            new_photo_path, error = save_photo(edited_photo)

            if error:
                st.error(error)
                return

        success = update_student(
            student_id,
            edited_name.strip(),
            edited_department.strip(),
            edited_email.strip(),
            new_photo_path
        )

        if not success:
            if new_photo_path is not None:
                new_photo_path.unlink(missing_ok=True)
            st.error("Couldn't save these changes. Try again.")
            return

        if new_photo_path is not None:
            old_photo_path.unlink(missing_ok=True)
            refresh_face_embeddings()

        st.toast(
            f"Saved changes to {edited_name.strip()}",
            icon=":material/check:"
        )
        st.rerun()

    except Exception as error:
        if new_photo_path is not None:
            new_photo_path.unlink(missing_ok=True)
        st.error(f"Couldn't save these changes: {error}")


def page_add():
    page_heading(
        "Add student",
        "Register a student once. Their photo is what Glance matches "
        "against at the camera.",
        show_date=False
    )

    form_col, tips_col = st.columns([3, 2], gap="large")

    with form_col:
        with st.form("student_registration", clear_on_submit=True):
            id_col, name_col = st.columns(2)

            with id_col:
                student_id = st.text_input(
                    "Student ID / USN",
                    placeholder="1DS23IS001"
                ).strip()

            with name_col:
                name = st.text_input(
                    "Full name",
                    placeholder="As it should appear on records"
                ).strip()

            dept_col, email_col = st.columns(2)

            with dept_col:
                department = st.text_input(
                    "Department",
                    placeholder="Information Science"
                ).strip()

            with email_col:
                email = st.text_input(
                    "Email",
                    placeholder="student@college.edu"
                ).strip()

            uploaded_photo = st.file_uploader(
                "Photo",
                type=["jpg", "jpeg", "png"]
            )

            submitted = st.form_submit_button(
                "Add student",
                type="primary",
                icon=":material/person_add:",
                width="stretch"
            )

    with tips_col:
        with st.container(border=True):
            st.markdown("**A photo that matches well**")
            st.markdown(
                "- Face the camera, eyes open, nothing covering the face\n"
                "- Even light, no strong shadow or backlight\n"
                "- Only one person in the photo\n"
                "- JPG or PNG, at least 100 × 100 pixels"
            )
            st.caption(
                "Photos are stored only on this computer, "
                "in the student_photos folder."
            )

    if not submitted:
        return

    if not student_id or not name:
        st.error("Add a student ID and a name.")
        return

    if uploaded_photo is None:
        st.error("Add a photo of the student.")
        return

    try:
        photo_path, error = save_photo(uploaded_photo)

        if error:
            st.error(error)
            return

        if not add_student(student_id, name, department, email, photo_path):
            photo_path.unlink(missing_ok=True)
            st.error(
                f"{student_id} is already registered. "
                "Use a different ID, or edit that student from Students."
            )
            return

        st.toast(f"Added {name}", icon=":material/person_add:")
        st.success(
            f"Added {name} ({student_id}). They can be stamped present "
            "at the camera now.",
            icon=":material/check_circle:"
        )

    except Exception as error:
        st.error(f"Couldn't add this student: {error}")


def page_records():
    page_heading("Records", show_date=False)

    attendance = get_attendance()
    students = get_students()

    if attendance.empty:
        st.html(
            '<p class="g-sub">No attendance yet. Records appear here '
            'after the first class is taken with the camera.</p>'
        )
        st.page_link(
            PAGE_LIVE,
            label="Take attendance",
            icon=":material/photo_camera:"
        )
        return

    attendance["day"] = pd.to_datetime(attendance["attendance_date"]).dt.date
    first_day = attendance["day"].min()
    last_day = max(attendance["day"].max(), date.today())
    default_start = max(first_day, last_day - timedelta(days=13))

    range_col, search_col = st.columns([2, 3], vertical_alignment="bottom")

    with range_col:
        picked = st.date_input(
            "Dates",
            value=(default_start, last_day),
            min_value=first_day,
            max_value=last_day,
            format="DD/MM/YYYY"
        )

    with search_col:
        search = st.text_input(
            "Student",
            placeholder="Name or student ID",
            icon=":material/search:"
        ).strip().lower()

    if isinstance(picked, (tuple, list)) and len(picked) == 2:
        start_day, end_day = picked
    else:
        start_day = end_day = picked[0] if isinstance(picked, (tuple, list)) else picked

    in_range = attendance[
        (attendance["day"] >= start_day) & (attendance["day"] <= end_day)
    ]

    if search:
        students = students[
            students["name"].str.lower().str.contains(search, na=False, regex=False)
            | students["student_id"].str.lower().str.contains(search, na=False, regex=False)
        ]
        in_range = in_range[in_range["student_id"].isin(students["student_id"])]

    class_days = sorted(in_range["day"].unique())

    if not class_days or students.empty:
        st.info(
            "No records for these dates or students. Widen the date range "
            "or clear the search.",
            icon=":material/event_busy:"
        )
        return

    section_label(
        "Attendance slip",
        f"{len(class_days)} class day(s) · {len(students)} student(s)"
    )
    st.html(slip_grid_html(students, in_range, class_days))

    st.space("medium")

    log_col, download_col = st.columns([4, 1], vertical_alignment="bottom")

    with log_col:
        section_label("Log", f"{len(in_range)} stamp(s)")

    export = in_range[
        ["attendance_date", "attendance_time", "student_id", "name", "status"]
    ].rename(columns={
        "attendance_date": "date",
        "attendance_time": "time",
        "student_id": "student id"
    })

    with download_col:
        st.download_button(
            "Download CSV",
            data=export.to_csv(index=False).encode("utf-8"),
            file_name=f"glance_records_{start_day}_{end_day}.csv",
            mime="text/csv",
            icon=":material/download:",
            width="stretch"
        )

    st.dataframe(
        export,
        hide_index=True,
        width="stretch",
        column_config={
            "date": st.column_config.DateColumn("Date", format="ddd DD MMM YYYY"),
            "time": "Time",
            "student id": "Student ID",
            "name": "Name",
            "status": "Status"
        }
    )


def slip_grid_html(students, records, class_days):
    stamped = set(zip(records["student_id"], records["day"]))

    head_cells = "".join(
        f'<th scope="col"><b>{day.strftime("%d")}</b>'
        f'{day.strftime("%b").upper()}</th>'
        for day in class_days
    )

    body_rows = []

    for _, student in students.iterrows():
        marks = []
        present_count = 0

        for day in class_days:
            if (student["student_id"], day) in stamped:
                present_count += 1
                marks.append(
                    f'<td><span class="g-mark" title="Present '
                    f'{day.strftime("%d %b")}">P</span></td>'
                )
            else:
                marks.append(
                    f'<td><span class="g-miss" title="Not marked '
                    f'{day.strftime("%d %b")}"></span></td>'
                )

        rate = round(100 * present_count / len(class_days))

        body_rows.append(
            f'<tr><th scope="row">{escape(student["name"])}'
            f'<span class="g-id">{escape(student["student_id"])}</span></th>'
            f'{"".join(marks)}'
            f'<td class="rate">{rate}%</td></tr>'
        )

    return (
        f'<div class="g-slip-wrap"><table class="g-slip">'
        f'<thead><tr><th scope="col"></th>{head_cells}'
        f'<th scope="col"><b>RATE</b>&nbsp;</th></tr></thead>'
        f'<tbody>{"".join(body_rows)}</tbody></table></div>'
        f'<div class="g-legend">'
        f'<span><span class="g-mark">P</span>Stamped present</span>'
        f'<span><span class="g-miss"></span>Not marked</span>'
        f'</div>'
    )


# --- Navigation ---

PAGE_TODAY = st.Page(
    page_today, title="Today", icon=":material/today:",
    default=True
)
PAGE_LIVE = st.Page(
    page_live, title="Take attendance", icon=":material/photo_camera:",
    url_path="take-attendance"
)
PAGE_STUDENTS = st.Page(
    page_students, title="Students", icon=":material/badge:",
    url_path="students"
)
PAGE_ADD = st.Page(
    page_add, title="Add student", icon=":material/person_add:",
    url_path="add-student"
)
PAGE_RECORDS = st.Page(
    page_records, title="Records", icon=":material/history:",
    url_path="records"
)

inject_styles()

st.logo(
    str(ASSETS_DIR / "glance-wordmark.svg"),
    size="large"
)

navigation = st.navigation(
    [PAGE_TODAY, PAGE_LIVE, PAGE_STUDENTS, PAGE_ADD, PAGE_RECORDS],
    position="top"
)

navigation.run()
