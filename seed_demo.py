"""Fill Glance with demo students and attendance so the app isn't empty.

Usage:
    python seed_demo.py           # only seeds an empty database
    python seed_demo.py --reset   # deletes ALL students and attendance first

The demo photos are initials on a plain colour, not real faces, so the
Take attendance camera can't match them. Add a real student with a
front-facing photo to try live recognition.
"""
import argparse
import datetime as dt
import random
import sqlite3
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "attendance.db"
PHOTO_DIR = BASE_DIR / "student_photos"

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    student_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    department TEXT,
    email TEXT,
    photo_path TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT NOT NULL,
    attendance_date TEXT NOT NULL,
    attendance_time TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Present',
    UNIQUE(student_id, attendance_date),
    FOREIGN KEY(student_id) REFERENCES students(student_id)
);
"""

# (name, department code, department)
STUDENTS = [
    ("Aarav Sharma", "IS", "Information Science"),
    ("Ananya Rao", "IS", "Information Science"),
    ("Rohan Kulkarni", "IS", "Information Science"),
    ("Priya Nair", "IS", "Information Science"),
    ("Karthik Reddy", "IS", "Information Science"),
    ("Sneha Hegde", "IS", "Information Science"),
    ("Vikram Iyer", "CS", "Computer Science"),
    ("Meera Joshi", "CS", "Computer Science"),
    ("Aditya Menon", "CS", "Computer Science"),
    ("Divya Shetty", "CS", "Computer Science"),
    ("Siddharth Patil", "CS", "Computer Science"),
    ("Kavya Gowda", "CS", "Computer Science"),
    ("Rahul Deshpande", "EC", "Electronics"),
    ("Ishita Banerjee", "EC", "Electronics"),
    ("Nikhil Bhat", "EC", "Electronics"),
    ("Pooja Kamath", "EC", "Electronics"),
    ("Arjun Pillai", "EC", "Electronics"),
    ("Tanvi Acharya", "EC", "Electronics"),
]

# Neutral slates only: plum is reserved for the "present" stamp.
PHOTO_COLOURS = [
    (104, 116, 134), (122, 134, 150), (92, 106, 122), (134, 142, 152),
    (112, 124, 128), (128, 120, 112), (98, 112, 112), (140, 132, 124),
]

PRESENT_TODAY = 11
PRESENT_RATE = 0.8
CLASS_DAYS = 21


def font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow older than 10.1
        return ImageFont.load_default()


def make_photo(path, initials, colour):
    image = Image.new("RGB", (400, 400), colour)
    draw = ImageDraw.Draw(image)
    draw.text(
        (200, 200), initials,
        fill=(244, 246, 248), font=font(160), anchor="mm"
    )
    image.save(path, "JPEG", quality=88)


def recent_weekdays(today, count):
    days, day = [], today
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day -= dt.timedelta(days=1)
    return sorted(days)


def arrival_time():
    seconds = 8 * 3600 + 50 * 60 + random.randint(0, 35 * 60)
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def clear_existing(conn):
    for (photo_path,) in conn.execute("SELECT photo_path FROM students"):
        Path(photo_path).unlink(missing_ok=True)

    conn.execute("DELETE FROM attendance")
    conn.execute("DELETE FROM students")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--reset", action="store_true",
        help="delete every existing student, photo and attendance record first"
    )
    args = parser.parse_args()

    PHOTO_DIR.mkdir(exist_ok=True)
    random.seed(7)

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    existing = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]

    if existing and not args.reset:
        conn.close()
        raise SystemExit(
            f"{DB_PATH.name} already has {existing} students. "
            "Nothing changed. Run with --reset to replace them with demo data."
        )

    clear_existing(conn)

    today = dt.date.today()
    now = dt.datetime.now().replace(microsecond=0)
    counters = {}
    student_ids = []

    for index, (name, code, department) in enumerate(STUDENTS):
        counters[code] = counters.get(code, 0) + 1
        student_id = f"1DS23{code}{counters[code]:03d}"
        initials = "".join(part[0] for part in name.split()[:2]).upper()

        photo_path = PHOTO_DIR / f"{uuid.uuid4().hex}.jpg"
        make_photo(photo_path, initials, PHOTO_COLOURS[index % len(PHOTO_COLOURS)])

        created = now - dt.timedelta(days=random.randint(22, 40))
        email = name.lower().replace(" ", ".") + "@example.edu"

        conn.execute(
            "INSERT INTO students VALUES (?, ?, ?, ?, ?, ?)",
            (student_id, name, department, email, str(photo_path), str(created.date()))
        )
        student_ids.append(student_id)

    days = recent_weekdays(today, CLASS_DAYS)
    if today not in days:  # seeded on a weekend: still show a "today"
        days = days[1:] + [today]

    rows = 0
    for day in days:
        if day == today:
            present = set(random.sample(student_ids, PRESENT_TODAY))
        else:
            present = {sid for sid in student_ids if random.random() < PRESENT_RATE}

        for student_id in sorted(present):
            conn.execute(
                "INSERT INTO attendance "
                "(student_id, attendance_date, attendance_time, status) "
                "VALUES (?, ?, ?, 'Present')",
                (student_id, day.isoformat(), arrival_time())
            )
            rows += 1

    conn.commit()
    conn.close()

    print(f"Seeded {len(student_ids)} demo students and {rows} attendance records")
    print(f"over {len(days)} class days ({days[0]} to {days[-1]}); "
          f"{PRESENT_TODAY} of {len(student_ids)} present today.")


if __name__ == "__main__":
    main()
