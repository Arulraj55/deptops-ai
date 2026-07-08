"""
Analytics Agent
---------------
Analyzes academic datasets (CSV/Excel) using Pandas.
Files are loaded from Neon PostgreSQL (via db_storage) so they persist
across Render restarts.
LLM enhances the answer when available — but the answer is ALWAYS good
without LLM too, using smart query-aware fallback logic.
"""

import io
import os
import re
import pandas as pd
from pathlib import Path
from config import get_llm


# ── File discovery ────────────────────────────────────────────────────────────

def _list_available_files() -> list[str]:
    """Return list of filenames stored in the database."""
    try:
        from db_storage import list_analytics_files
        return [row["filename"] for row in list_analytics_files()]
    except Exception:
        return []


def _load_dataframe(filename: str) -> pd.DataFrame:
    """Load a dataframe from the database by filename."""
    from db_storage import load_analytics_file
    content = load_analytics_file(filename)
    if content is None:
        raise FileNotFoundError(f"File '{filename}' not found in database.")
    buf = io.BytesIO(content)
    ext = Path(filename).suffix.lower()
    return pd.read_csv(buf) if ext == ".csv" else pd.read_excel(buf)


# ── Stats computation ─────────────────────────────────────────────────────────

def _compute_stats(df: pd.DataFrame) -> dict:
    stats = {}
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    cols = df.columns.tolist()

    for rc in ("result", "status", "pass_fail"):
        if rc in cols:
            counts = df[rc].astype(str).str.strip().str.upper().value_counts()
            total = len(df)
            pass_c = int(counts.get("PASS", counts.get("P", 0)))
            fail_c = int(counts.get("FAIL", counts.get("F", 0)))
            stats.update({
                "total_students": total, "pass_count": pass_c, "fail_count": fail_c,
                "pass_percentage": round(pass_c / total * 100, 2) if total else 0,
                "fail_percentage": round(fail_c / total * 100, 2) if total else 0,
            })
            break

    for ac in ("attendance", "attendance_percentage", "att_%", "attendance_%"):
        if ac in cols:
            stats["avg_attendance"] = round(float(df[ac].mean()), 2)
            stats["below_75_count"] = int((df[ac] < 75).sum())
            stats["below_75_pct"] = round(stats["below_75_count"] / len(df) * 100, 2)
            stats["eligible_exam_count"] = int((df[ac] >= 75).sum())
            break

    for gc in ("cgpa", "gpa", "aggregate"):
        if gc in cols:
            stats["avg_cgpa"] = round(float(df[gc].mean()), 2)
            stats["placement_eligible"] = int((df[gc] >= 6.0).sum())
            stats["placement_eligible_pct"] = round(stats["placement_eligible"] / len(df) * 100, 2)
            break

    for pc in ("placed", "placement_status"):
        if pc in cols:
            pc_c = df[pc].astype(str).str.strip().str.upper().value_counts()
            placed = int(pc_c.get("YES", pc_c.get("Y", 0)))
            not_placed = int(pc_c.get("NO", pc_c.get("N", 0)))
            total = stats.get("total_students", len(df))
            stats.update({
                "placed_count": placed,
                "not_placed_count": not_placed,
                "total_students": total,
                "placement_rate_pct": round(placed / total * 100, 2) if total else 0,
            })
            break

    skip = {"total_marks", "average_marks", "cgpa", "gpa", "aggregate", "attendance",
            "attendance_percentage", "att_%", "roll_no", "student_id", "id",
            "classes_held", "classes_attended", "semester"}
    num_cols = [c for c in df.select_dtypes(include="number").columns if c not in skip]
    if num_cols:
        avgs = df[num_cols].mean().round(2).to_dict()
        subj = {k: v for k, v in avgs.items() if 0 <= v <= 100}
        if subj:
            stats["subject_averages"] = subj

    for fc in ("pass_percentage_class", "avg_student_score", "student_feedback_score"):
        if fc in cols:
            stats[f"avg_{fc}"] = round(float(df[fc].mean()), 2)

    return stats


# ── Smart query-aware fallback answer ─────────────────────────────────────────

def _answer_from_stats(query: str, stats: dict, df: pd.DataFrame, file_name: str) -> str:
    q = query.lower()
    df_n = df.copy()
    df_n.columns = [str(c).strip().lower().replace(" ", "_") for c in df_n.columns]
    lines = []

    if any(w in q for w in ["pass", "fail", "result", "passed", "failed"]):
        if "pass_percentage" in stats:
            lines += [
                f"**Pass/Fail Analysis — {file_name}**",
                f"- Total Students: **{stats['total_students']}**",
                f"- Passed: **{stats['pass_count']} ({stats['pass_percentage']}%)**",
                f"- Failed: **{stats['fail_count']} ({stats['fail_percentage']}%)**",
            ]
            if stats["fail_percentage"] > 40:
                lines.append("- ⚠️ High failure rate — review subject-wise performance.")
        else:
            lines.append(f"No pass/fail column found in **{file_name}**.")

    elif any(w in q for w in ["attendance", "absent", "eligible", "below 75", "ineligible"]):
        if "avg_attendance" in stats:
            lines += [
                f"**Attendance Summary — {file_name}**",
                f"- Average Attendance: **{stats['avg_attendance']}%**",
                f"- Students below 75% (exam ineligible): **{stats['below_75_count']} ({stats['below_75_pct']}%)**",
                f"- Students eligible for exam (≥75%): **{stats['eligible_exam_count']}**",
            ]
        else:
            lines.append(f"No attendance column found in **{file_name}**.")

    elif any(w in q for w in ["placement", "placed", "company", "package", "job", "recruit"]):
        if "placed_count" in stats:
            lines += [
                f"**Placement Summary — {file_name}**",
                f"- Students Placed: **{stats['placed_count']} ({stats['placement_rate_pct']}%)**",
                f"- Not Placed: **{stats['not_placed_count']}**",
            ]
            if "placement_eligible" in stats:
                lines.append(f"- CGPA Eligible (≥6.0): **{stats['placement_eligible']} ({stats['placement_eligible_pct']}%)**")
            for cc in ("company", "companies", "employer"):
                if cc in df_n.columns:
                    top = df_n[df_n[cc].notna()][cc].value_counts().head(5)
                    if not top.empty:
                        lines.append("- Top Recruiters: " + ", ".join(f"**{c}** ({n})" for c, n in top.items()))
                    break
        elif "placement_eligible" in stats:
            lines += [
                f"**Placement Eligibility — {file_name}**",
                f"- CGPA Eligible (≥6.0): **{stats['placement_eligible']} ({stats['placement_eligible_pct']}%)**",
                f"- Average CGPA: **{stats['avg_cgpa']}**",
            ]
        else:
            lines.append(f"No placement data found in **{file_name}**.")

    elif any(w in q for w in ["cgpa", "gpa", "grade", "aggregate", "score"]):
        if "avg_cgpa" in stats:
            lines += [
                f"**CGPA Analysis — {file_name}**",
                f"- Average CGPA: **{stats['avg_cgpa']}**",
                f"- Placement Eligible (CGPA ≥ 6.0): **{stats['placement_eligible']} ({stats['placement_eligible_pct']}%)**",
            ]
            for gc in ("cgpa", "gpa", "aggregate"):
                if gc in df_n.columns:
                    lines += [
                        f"- Highest CGPA: **{df_n[gc].max():.2f}**",
                        f"- Lowest CGPA: **{df_n[gc].min():.2f}**",
                    ]
                    break
        else:
            lines.append(f"No CGPA/GPA column found in **{file_name}**.")

    elif any(w in q for w in ["subject", "marks", "average", "performance", "weak", "strong"]):
        if "subject_averages" in stats:
            sa = stats["subject_averages"]
            lines.append(f"**Subject-wise Average Marks — {file_name}**")
            for subj, avg in sorted(sa.items(), key=lambda x: -x[1]):
                bar = "🟢" if avg >= 60 else ("🟡" if avg >= 45 else "🔴")
                lines.append(f"- {bar} {subj.replace('_', ' ').title()}: **{avg}**")
            best = max(sa, key=sa.get)
            worst = min(sa, key=sa.get)
            lines += [
                f"\n🏆 Best subject: **{best.replace('_', ' ').title()}** ({sa[best]})",
                f"⚠️ Weakest subject: **{worst.replace('_', ' ').title()}** ({sa[worst]})",
            ]
        else:
            lines.append(f"No subject marks columns found in **{file_name}**.")

    elif any(w in q for w in ["faculty", "teacher", "professor", "feedback"]):
        if "avg_avg_student_score" in stats:
            lines += [
                f"**Faculty Performance — {file_name}**",
                f"- Average Student Score across faculty: **{stats['avg_avg_student_score']}**",
                f"- Average Pass % (class level): **{stats.get('avg_pass_percentage_class', 'N/A')}%**",
                f"- Average Student Feedback Score: **{stats.get('avg_avg_student_feedback_score', 'N/A')}/5**",
            ]
        else:
            lines.append(f"No faculty performance data found in **{file_name}**.")

    else:
        lines.append(f"**Dataset Overview — {file_name}**")
        lines.append(f"- Rows: **{len(df_n)}** | Columns: **{len(df_n.columns)}**")
        lines.append(f"- Columns: {', '.join(str(c) for c in df_n.columns.tolist()[:10])}")
        if stats:
            lines.append("\n**Available Statistics:**")
            if "total_students" in stats:
                lines.append(f"- Total Records: **{stats['total_students']}**")
            if "pass_percentage" in stats:
                lines.append(f"- Pass Rate: **{stats['pass_percentage']}%**")
            if "avg_attendance" in stats:
                lines.append(f"- Avg Attendance: **{stats['avg_attendance']}%**")
            if "avg_cgpa" in stats:
                lines.append(f"- Avg CGPA: **{stats['avg_cgpa']}**")
            if "placement_rate_pct" in stats:
                lines.append(f"- Placement Rate: **{stats['placement_rate_pct']}%**")
            if "subject_averages" in stats:
                lines.append(f"- Subjects tracked: **{len(stats['subject_averages'])}**")

    return "\n".join(lines)


def _build_summary_text(df: pd.DataFrame, stats: dict, file_name: str) -> str:
    lines = [
        f"Dataset: {file_name}",
        f"Shape: {df.shape[0]} rows × {df.shape[1]} columns",
        f"Columns: {', '.join(str(c) for c in df.columns.tolist())}",
        "", "Computed Statistics:",
    ]
    for key, value in stats.items():
        if isinstance(value, dict):
            lines.append(f"  {key}:")
            for k, v in value.items():
                lines.append(f"    {k}: {v}")
        else:
            lines.append(f"  {key}: {value}")
    return "\n".join(lines)


# ── Main Entry Point ──────────────────────────────────────────────────────────

def run_analytics_agent(query: str, file_path: str | None = None) -> dict:
    """
    file_path here is now a filename (not a full path) — it matches what's
    stored in the database.  If not provided, the first available file is used.
    """
    available = _list_available_files()

    if not file_path:
        if not available:
            return {
                "answer": "No data files found. Please upload a CSV or Excel file from the sidebar.",
                "stats": {}, "file_used": None, "error": "no_files",
            }
        file_path = available[0]

    # file_path may be a bare filename or a full path — normalise to filename only
    filename = Path(file_path).name

    try:
        df = _load_dataframe(filename)
    except Exception as exc:
        return {"answer": f"Could not load file: {exc}", "stats": {}, "file_used": filename, "error": str(exc)}

    stats = _compute_stats(df)
    direct_answer = _answer_from_stats(query, stats, df, filename)
    summary_text = _build_summary_text(df, stats, filename)

    answer = direct_answer
    try:
        from langchain_core.prompts import ChatPromptTemplate
        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are an academic data analyst for a university Head of Department. "
             "Answer the HOD's question using ONLY the dataset statistics provided. "
             "Be specific with numbers. Use bullet points. Be concise. "
             "Do NOT mention anything about LLM, rate limits, or AI."),
            ("human", "Dataset Statistics:\n{summary}\n\nQuestion: {query}"),
        ])
        llm = get_llm(temperature=0.1)
        response = (prompt | llm).invoke({"summary": summary_text, "query": query})
        if response and response.content and len(response.content.strip()) > 30:
            answer = response.content
    except Exception:
        pass

    return {
        "answer": answer,
        "stats": stats,
        "file_used": filename,
        "file_name": filename,
        "error": None,
    }


def get_available_datasets() -> list[str]:
    return _list_available_files()


def compute_stats(df) -> dict:
    return _compute_stats(df)


def load_dataframe(filename: str):
    return _load_dataframe(filename)
