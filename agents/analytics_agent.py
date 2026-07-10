"""
Analytics Agent
---------------
Analyzes academic datasets (CSV/Excel) using Pandas.
Files are loaded from Neon PostgreSQL (via db_storage).

Strategy:
1. Load file, compute all stats
2. Build a full data summary (columns + sample + stats)
3. Send to LLM with a strict "answer ONLY what was asked" prompt
4. Fall back to direct stats-based answer if LLM fails/rate-limited
"""

import io
import re
import pandas as pd
from pathlib import Path
from config import get_llm


# ── File discovery ────────────────────────────────────────────────────────────

def _list_available_files(username: str) -> list[str]:
    try:
        from db_storage import list_analytics_files
        return [row["filename"] for row in list_analytics_files(username)]
    except Exception:
        return []


def _load_dataframe(username: str, filename: str) -> pd.DataFrame:
    from db_storage import load_analytics_file
    content = load_analytics_file(username, filename)
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
                "total_students": total,
                "pass_count": pass_c,
                "fail_count": fail_c,
                "pass_percentage": round(pass_c / total * 100, 2) if total else 0,
                "fail_percentage": round(fail_c / total * 100, 2) if total else 0,
            })
            break

    for ac in ("attendance", "attendance_percentage", "att_%", "attendance_%"):
        if ac in cols:
            stats["avg_attendance"] = round(float(df[ac].mean()), 2)
            stats["below_75_count"] = int((df[ac] < 75).sum())
            stats["below_75_pct"] = round(stats["below_75_count"] / len(df) * 100, 2) if len(df) else 0
            stats["eligible_exam_count"] = int((df[ac] >= 75).sum())
            break

    for gc in ("cgpa", "gpa", "aggregate"):
        if gc in cols:
            stats["avg_cgpa"] = round(float(df[gc].mean()), 2)
            stats["max_cgpa"] = round(float(df[gc].max()), 2)
            stats["min_cgpa"] = round(float(df[gc].min()), 2)
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
    
    academic_keywords = {"pass", "fail", "marks", "cgpa", "gpa", "attendance", "subject", "grade", "course"}
    is_academic = any(k in c for c in cols for k in academic_keywords)

    if num_cols:
        avgs = df[num_cols].mean().round(2).to_dict()
        subj = {k: v for k, v in avgs.items() if 0 <= v <= 100}
        if subj:
            if is_academic:
                stats["subject_averages"] = subj
            else:
                stats["generic_averages"] = subj

    for fc in ("pass_percentage_class", "avg_student_score", "student_feedback_score"):
        if fc in cols:
            stats[f"avg_{fc}"] = round(float(df[fc].mean()), 2)

    return stats


# ── Build a rich context string for the LLM ──────────────────────────────────

def _build_context(df: pd.DataFrame, stats: dict, filename: str) -> str:
    df_n = df.copy()
    df_n.columns = [str(c).strip().lower().replace(" ", "_") for c in df_n.columns]

    lines = [
        f"File: {filename}",
        f"Total records: {len(df_n)}",
        f"Columns ({len(df_n.columns)}): {', '.join(df_n.columns.tolist())}",
        "",
        "=== COMPUTED STATISTICS ===",
    ]

    if "total_students" in stats:
        lines.append(f"Total students: {stats['total_students']}")
    if "pass_count" in stats:
        lines.append(f"Pass: {stats['pass_count']} ({stats['pass_percentage']}%)")
        lines.append(f"Fail: {stats['fail_count']} ({stats['fail_percentage']}%)")
    if "avg_attendance" in stats:
        lines.append(f"Average attendance: {stats['avg_attendance']}%")
        lines.append(f"Students below 75% (ineligible): {stats['below_75_count']} ({stats['below_75_pct']}%)")
        lines.append(f"Students at/above 75% (eligible): {stats['eligible_exam_count']}")
    if "avg_cgpa" in stats:
        lines.append(f"Average CGPA: {stats['avg_cgpa']}")
        lines.append(f"Highest CGPA: {stats['max_cgpa']}")
        lines.append(f"Lowest CGPA: {stats['min_cgpa']}")
        lines.append(f"Placement eligible (CGPA >= 6.0): {stats['placement_eligible']} ({stats['placement_eligible_pct']}%)")
    if "placed_count" in stats:
        lines.append(f"Placed: {stats['placed_count']} ({stats['placement_rate_pct']}%)")
        lines.append(f"Not placed: {stats['not_placed_count']}")
    if "subject_averages" in stats:
        lines.append("Subject-wise averages:")
        for subj, avg in sorted(stats["subject_averages"].items(), key=lambda x: -x[1]):
            lines.append(f"  {subj.replace('_',' ').title()}: {avg}")
    if "generic_averages" in stats:
        lines.append("Numeric column averages:")
        for col, avg in sorted(stats["generic_averages"].items(), key=lambda x: -x[1]):
            lines.append(f"  {col.replace('_',' ').title()}: {avg}")

    # Sample data (first 5 rows, text form)
    lines.append("")
    lines.append("=== SAMPLE DATA (first 5 rows) ===")
    lines.append(df_n.head(5).to_string(index=False))

    return "\n".join(lines)


# ── Direct stats fallback (no LLM needed) ────────────────────────────────────

def _direct_answer(query: str, stats: dict, df: pd.DataFrame, filename: str) -> str:
    q = query.lower()
    df_n = df.copy()
    df_n.columns = [str(c).strip().lower().replace(" ", "_") for c in df_n.columns]
    lines = []

    if any(w in q for w in ("pass", "fail", "result", "passed", "failed")):
        if "pass_percentage" in stats:
            lines += [
                f"**Pass/Fail — {filename}**",
                f"- Total: **{stats['total_students']}**",
                f"- Passed: **{stats['pass_count']} ({stats['pass_percentage']}%)**",
                f"- Failed: **{stats['fail_count']} ({stats['fail_percentage']}%)**",
            ]
        else:
            lines.append(f"No pass/fail column found in {filename}.")

    elif any(w in q for w in ("attendance", "absent", "eligible", "ineligible", "below 75")):
        if "avg_attendance" in stats:
            lines += [
                f"**Attendance — {filename}**",
                f"- Average: **{stats['avg_attendance']}%**",
                f"- Below 75% (ineligible): **{stats['below_75_count']} ({stats['below_75_pct']}%)**",
                f"- Eligible (≥75%): **{stats['eligible_exam_count']}**",
            ]
        else:
            lines.append(f"No attendance column found in {filename}.")

    elif any(w in q for w in ("placement", "placed", "company", "job", "recruit", "package")):
        if "placed_count" in stats:
            lines += [
                f"**Placement — {filename}**",
                f"- Placed: **{stats['placed_count']} ({stats['placement_rate_pct']}%)**",
                f"- Not placed: **{stats['not_placed_count']}**",
            ]
        elif "placement_eligible" in stats:
            lines += [
                f"**Placement Eligibility — {filename}**",
                f"- CGPA ≥ 6.0: **{stats['placement_eligible']} ({stats['placement_eligible_pct']}%)**",
                f"- Avg CGPA: **{stats['avg_cgpa']}**",
            ]
        else:
            lines.append(f"No placement data found in {filename}.")

    elif any(w in q for w in ("cgpa", "gpa", "grade", "aggregate")):
        if "avg_cgpa" in stats:
            lines += [
                f"**CGPA — {filename}**",
                f"- Average: **{stats['avg_cgpa']}**",
                f"- Highest: **{stats['max_cgpa']}** | Lowest: **{stats['min_cgpa']}**",
                f"- Placement eligible (≥6.0): **{stats['placement_eligible']} ({stats['placement_eligible_pct']}%)**",
            ]
        else:
            lines.append(f"No CGPA column found in {filename}.")

    elif any(w in q for w in ("subject", "marks", "average", "performance", "weak", "strong", "score", "most", "high", "low")):
        if "subject_averages" in stats:
            sa = stats["subject_averages"]
            lines.append(f"**Subject-wise Average Marks — {filename}**")
            for subj, avg in sorted(sa.items(), key=lambda x: -x[1]):
                icon = "🟢" if avg >= 60 else ("🟡" if avg >= 40 else "🔴")
                lines.append(f"- {icon} {subj.replace('_', ' ').title()}: **{avg}**")
            best = max(sa, key=sa.get)
            worst = min(sa, key=sa.get)
            lines += [
                f"\n🏆 Best: **{best.replace('_',' ').title()}** ({sa[best]})",
                f"⚠️ Weakest: **{worst.replace('_',' ').title()}** ({sa[worst]})",
            ]
        elif "generic_averages" in stats:
            sa = stats["generic_averages"]
            lines.append(f"**Column Averages — {filename}**")
            for subj, avg in sorted(sa.items(), key=lambda x: -x[1]):
                lines.append(f"- {subj.replace('_', ' ').title()}: **{avg}**")
            best = max(sa, key=sa.get)
            worst = min(sa, key=sa.get)
            lines += [
                f"\n🏆 Highest: **{best.replace('_',' ').title()}** ({sa[best]})",
                f"⚠️ Lowest: **{worst.replace('_',' ').title()}** ({sa[worst]})",
            ]
        else:
            lines.append(f"No numeric columns found for averages in {filename}.")

    elif any(w in q for w in ("faculty", "teacher", "professor", "feedback")):
        if "avg_avg_student_score" in stats:
            lines += [
                f"**Faculty Performance — {filename}**",
                f"- Avg Student Score: **{stats['avg_avg_student_score']}**",
                f"- Avg Pass % (class): **{stats.get('avg_pass_percentage_class','N/A')}%**",
            ]
        else:
            lines.append(f"No faculty performance data found in {filename}.")

    else:
        # Generic overview — always useful
        lines.append(f"**Dataset: {filename}**")
        lines.append(f"- Rows: **{len(df_n)}** | Columns: **{len(df_n.columns)}**")
        lines.append(f"- Columns: {', '.join(df_n.columns.tolist()[:12])}")
        if stats:
            lines.append("\n**Available statistics:**")
            for key, val in stats.items():
                if not isinstance(val, dict):
                    lines.append(f"- {key.replace('_',' ').title()}: **{val}**")

    return "\n".join(lines)


# ── Main Entry Point ──────────────────────────────────────────────────────────

def run_analytics_agent(username: str, query: str, file_path: str | None = None) -> dict:
    available = _list_available_files(username)

    if not file_path:
        if not available:
            return {
                "answer": "No data files found. Please upload a CSV or Excel file from the sidebar.",
                "stats": {}, "file_used": None, "error": "no_files",
            }
        file_path = available[0]

    filename = Path(file_path).name

    try:
        df = _load_dataframe(username, filename)
    except Exception as exc:
        return {"answer": f"Could not load file: {exc}", "stats": {}, "file_used": filename, "error": str(exc)}

    stats = _compute_stats(df)
    context = _build_context(df, stats, filename)
    fallback = _direct_answer(query, stats, df, filename)

    answer = fallback
    try:
        from langchain_core.prompts import ChatPromptTemplate
        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a data analyst for a university Head of Department.\n"
             "You have been given a dataset with statistics and sample rows.\n\n"
             "STRICT RULES:\n"
             "1. Answer ONLY the specific question asked — nothing else.\n"
             "2. Use the exact numbers from the statistics provided.\n"
             "3. Format: bullet points, bold numbers.\n"
             "4. If the data doesn't contain what was asked, say so in one line.\n"
             "5. Do NOT mention AI, LLM, OpenRouter, or rate limits.\n"
             "6. Do NOT add extra information the user didn't ask for.\n"
             "7. Provide zero conversational filler. Give ONLY the direct answer."),
            ("human",
             "DATASET CONTEXT:\n{context}\n\n"
             "QUESTION: {query}\n\n"
             "Answer the question using only the data above:"),
        ])
        llm = get_llm(temperature=0.0)
        response = (prompt | llm).invoke({"context": context, "query": query})
        if response and response.content and len(response.content.strip()) > 20:
            answer = response.content
    except Exception:
        pass  # use fallback

    return {
        "answer": answer,
        "stats": stats,
        "file_used": filename,
        "file_name": filename,
        "error": None,
    }


def get_available_datasets(username: str) -> list[str]:
    return _list_available_files(username)


def compute_stats(df) -> dict:
    return _compute_stats(df)


def load_dataframe(username: str, filename: str):
    return _load_dataframe(username, filename)
