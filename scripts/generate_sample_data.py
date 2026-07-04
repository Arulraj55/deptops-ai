"""
Run this script once to generate sample academic datasets for testing.
Usage: python scripts/generate_sample_data.py
"""

import random
import pandas as pd
from pathlib import Path

random.seed(42)

OUTPUT_DIR = Path("data/analytics")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SUBJECTS = ["Mathematics", "Physics", "Chemistry", "English", "CS Fundamentals",
            "Data Structures", "DBMS", "Operating Systems"]

DEPARTMENTS = ["Computer Science", "Electronics", "Mechanical", "Civil"]

# ── 1. Student Results ────────────────────────────────────────────────────────
def generate_results():
    rows = []
    for i in range(1, 121):
        marks = {sub: random.randint(30, 100) for sub in SUBJECTS}
        total = sum(marks.values())
        avg = total / len(SUBJECTS)
        result = "PASS" if avg >= 40 and all(m >= 35 for m in marks.values()) else "FAIL"
        cgpa = round(avg / 10, 2)
        rows.append({
            "student_id": f"S{i:04d}",
            "name": f"Student_{i}",
            "department": random.choice(DEPARTMENTS),
            "semester": random.choice([3, 4, 5, 6]),
            **marks,
            "total_marks": total,
            "average_marks": round(avg, 2),
            "cgpa": cgpa,
            "result": result,
        })
    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / "student_results.csv", index=False)
    print(f"[✓] Generated student_results.csv ({len(df)} rows)")


# ── 2. Attendance Records ─────────────────────────────────────────────────────
def generate_attendance():
    rows = []
    for i in range(1, 121):
        att = random.uniform(50, 100)
        rows.append({
            "student_id": f"S{i:04d}",
            "name": f"Student_{i}",
            "department": random.choice(DEPARTMENTS),
            "attendance_percentage": round(att, 2),
            "classes_held": 90,
            "classes_attended": int(90 * att / 100),
            "eligible_exam": "YES" if att >= 75 else "NO",
        })
    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / "attendance.csv", index=False)
    print(f"[✓] Generated attendance.csv ({len(df)} rows)")


# ── 3. Placement Statistics ───────────────────────────────────────────────────
def generate_placement():
    companies = ["TCS", "Infosys", "Wipro", "Cognizant", "Accenture",
                 "HCL", "Tech Mahindra", "IBM", "Capgemini", None]
    rows = []
    for i in range(1, 121):
        cgpa = round(random.uniform(5.0, 10.0), 2)
        placed = cgpa >= 6.0 and random.random() > 0.3
        company = random.choice(companies[:9]) if placed else None
        package = round(random.uniform(3.5, 18.0), 2) if placed else None
        rows.append({
            "student_id": f"S{i:04d}",
            "name": f"Student_{i}",
            "department": random.choice(DEPARTMENTS),
            "cgpa": cgpa,
            "placed": "YES" if placed else "NO",
            "company": company,
            "package_lpa": package,
        })
    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / "placement_stats.csv", index=False)
    print(f"[✓] Generated placement_stats.csv ({len(df)} rows)")


# ── 4. Faculty Performance ────────────────────────────────────────────────────
def generate_faculty():
    rows = []
    for i in range(1, 21):
        rows.append({
            "faculty_id": f"F{i:03d}",
            "name": f"Prof_{i}",
            "department": random.choice(DEPARTMENTS),
            "subject": random.choice(SUBJECTS),
            "classes_taken": random.randint(60, 90),
            "avg_student_score": round(random.uniform(45, 85), 2),
            "student_feedback_score": round(random.uniform(3.0, 5.0), 2),
            "pass_percentage_class": round(random.uniform(55, 98), 2),
        })
    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / "faculty_performance.csv", index=False)
    print(f"[✓] Generated faculty_performance.csv ({len(df)} rows)")


if __name__ == "__main__":
    generate_results()
    generate_attendance()
    generate_placement()
    generate_faculty()
    print("\nAll sample datasets generated in:", OUTPUT_DIR.resolve())
