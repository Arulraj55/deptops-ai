"""
Analytics Agent for DeptOps AI
-------------------------------
Analyzes ANY academic dataset (Excel / CSV) for NAAC & Department Management.

Capabilities:
- Intelligent column classifier (numerical, categorical, percentage, date, year).
- Automatic chart generator (Bar, Line, Pie, Histogram, Box Plot, Scatter, Heatmap, Correlation, Trend, Comparison).
- Automatic selection of optimal chart based on dataset dimensions.
- Comprehensive statistical summary, anomaly detection, year comparisons, percentage improvements.
- Powered by an OpenRouter free-model panel for natural language Q&A and chart explanations.
- Export support: Excel Summary, PDF Report, PNG Chart rendering.
"""

import io
import re
import pandas as pd
import numpy as np
from pathlib import Path
import logging

from config import invoke_openrouter_free_models

logger = logging.getLogger("AnalyticsAgent")


# ── File loading & discovery ──────────────────────────────────────────────────

def _load_dataframe(username: str, filename: str) -> pd.DataFrame:
    from db_storage import load_analytics_file
    content = load_analytics_file(username, filename)
    if content is None:
        raise FileNotFoundError(f"File '{filename}' not found in database.")
    buf = io.BytesIO(content)
    ext = Path(filename).suffix.lower()
    df = pd.read_csv(buf) if ext == ".csv" else pd.read_excel(buf)
    # Normalize column names — strip whitespace to prevent KeyError mismatches
    df.columns = [str(c).strip() for c in df.columns]
    return df


# ── Column Type Detector ──────────────────────────────────────────────────────

def detect_column_types(df: pd.DataFrame) -> dict:
    """
    Automatically detects column categories:
    - numerical
    - categorical (excludes unique names/IDs)
    - percentage
    - date
    - year
    - id_cols (names, roll numbers, reg numbers)
    """
    col_info = {
        "numerical": [],
        "categorical": [],
        "percentage": [],
        "date": [],
        "year": [],
        "id_cols": [],
        "all_clean": [str(c).strip() for c in df.columns]
    }

    ID_KEYWORDS = {"name", "student_name", "student", "roll", "roll_no", "rollno", "reg", "reg_no", "regno", "register", "register_no", "id", "email", "sno", "s_no", "serial"}

    for orig_col in df.columns:
        clean = str(orig_col).strip()
        clean_lower = clean.lower().replace(" ", "_")
        series = df[orig_col].dropna()

        if series.empty:
            continue

        # Check if ID / Name column
        if any(k in clean_lower for k in ID_KEYWORDS) and not any(k in clean_lower for k in ("dept", "department", "branch", "grade", "status", "year", "session")):
            col_info["id_cols"].append(clean)
            continue

        # Check year column
        if any(k in clean_lower for k in ("year", "acad_year", "session", "batch")) or (
            pd.api.types.is_numeric_dtype(series) and series.min() >= 1990 and series.max() <= 2050
        ):
            col_info["year"].append(clean)
            col_info["categorical"].append(clean)
            continue

        # Check date column
        if pd.api.types.is_datetime64_any_dtype(series) or "date" in clean_lower:
            col_info["date"].append(clean)
            continue
        try:
            if series.dtype == "object":
                parsed = pd.to_datetime(series, errors="coerce", format="mixed")
                if parsed.notna().sum() / len(series) > 0.7:
                    col_info["date"].append(clean)
                    continue
        except Exception:
            pass

        # Check percentage column
        if "pct" in clean_lower or "%" in clean_lower or "percentage" in clean_lower or "rate" in clean_lower:
            col_info["percentage"].append(clean)
            col_info["numerical"].append(clean)
            continue

        # Check numeric vs categorical
        if pd.api.types.is_numeric_dtype(series):
            if series.min() >= 0 and series.max() <= 100 and ("att" in clean_lower or "pass" in clean_lower):
                col_info["percentage"].append(clean)
            col_info["numerical"].append(clean)
        else:
            # If high cardinality (unique values == row count), treat as ID col unless it's dept/branch
            if series.nunique() > len(series) * 0.8 and not any(k in clean_lower for k in ("dept", "department", "branch", "course")):
                col_info["id_cols"].append(clean)
            else:
                col_info["categorical"].append(clean)

    return col_info


# ── Deep Data & Statistical Analyzer ─────────────────────────────────────────

def analyze_dataset(df: pd.DataFrame, filename: str) -> dict:
    """
    Generates statistical summary, key insights, highest/lowest, averages,
    group-by aggregations, anomalies, and percentage improvements.
    """
    col_info = detect_column_types(df)
    stats: dict = {"col_types": col_info, "filename": filename, "total_rows": len(df), "total_cols": len(df.columns)}

    num_cols = col_info["numerical"]
    cat_cols = col_info["categorical"]
    year_cols = col_info["year"]

    # 1. Summary for numerical columns
    if num_cols:
        desc = df[num_cols].describe().round(2).to_dict()
        stats["numeric_summary"] = desc

        highest_lowest = {}
        for col in num_cols:
            highest_lowest[col] = {
                "max": round(float(df[col].max()), 2),
                "min": round(float(df[col].min()), 2),
                "mean": round(float(df[col].mean()), 2),
                "std": round(float(df[col].std()), 2) if len(df) > 1 else 0.0,
            }
        stats["highest_lowest"] = highest_lowest

        anomalies = {}
        for col in num_cols:
            s = df[col].dropna()
            if len(s) > 5:
                q1, q3 = s.quantile(0.25), s.quantile(0.75)
                iqr = q3 - q1
                outliers = s[(s < (q1 - 1.5 * iqr)) | (s > (q3 + 1.5 * iqr))]
                if not outliers.empty:
                    anomalies[col] = len(outliers)
        stats["anomalies"] = anomalies

    # 2. Group-by breakdown for categorical columns (e.g. Department, Branch, Section)
    group_by_summaries = {}
    for c_col in cat_cols:
        if df[c_col].nunique() <= 30:
            counts = df[c_col].astype(str).value_counts().to_dict()
            grp_data = {"record_counts": counts}
            if num_cols:
                try:
                    num_means = df.groupby(c_col)[num_cols].mean().round(2).to_dict()
                    grp_data["means"] = num_means
                except Exception:
                    pass
            group_by_summaries[c_col] = grp_data
    stats["group_by_summaries"] = group_by_summaries

    # 3. Year-over-Year comparison if year column exists
    if year_cols and num_cols:
        y_col = year_cols[0]
        y_grouped = df.groupby(y_col)[num_cols].mean().round(2)
        stats["year_comparison"] = y_grouped.to_dict()

        yoy_pct = {}
        sorted_years = sorted(y_grouped.index.tolist())
        if len(sorted_years) >= 2:
            prev, curr = sorted_years[-2], sorted_years[-1]
            for col in num_cols:
                v_prev = y_grouped.loc[prev, col]
                v_curr = y_grouped.loc[curr, col]
                if v_prev and v_prev != 0:
                    chg = round(((v_curr - v_prev) / abs(v_prev)) * 100, 2)
                    yoy_pct[col] = {"from_year": str(prev), "to_year": str(curr), "change_pct": chg}
        stats["year_improvements"] = yoy_pct

    # 4. Categorical distribution summaries
    cat_summary = {}
    for col in cat_cols[:4]:
        val_counts = df[col].astype(str).value_counts().head(10).to_dict()
        cat_summary[col] = val_counts
    stats["cat_summary"] = cat_summary

    return stats


# ── Automatic Visualizations Generator ───────────────────────────────────────

def generate_visualizations(df: pd.DataFrame, col_info: dict) -> list[dict]:
    """
    Selects and creates the best Plotly charts based on column types.
    Avoids charts on student names/IDs and focuses on Department, Branch, Grade, Performance.
    """
    import plotly.express as px
    import plotly.graph_objects as go

    charts = []
    num_cols = col_info["numerical"]
    cat_cols = col_info["categorical"]
    year_cols = col_info["year"]

    # Pick best group column (prioritize Department, Branch, Section, Grade)
    best_cat = None
    for c in cat_cols:
        c_lower = c.lower()
        if any(k in c_lower for k in ("dept", "department", "branch", "course", "section")):
            best_cat = c
            break
    if not best_cat and cat_cols:
        best_cat = cat_cols[0]

    # 1. Grouped Bar Chart of Averages by Category/Department
    if best_cat and num_cols:
        try:
            val_col = num_cols[0]
            grouped_df = df.groupby(best_cat, as_index=False)[val_col].mean().round(2)
            grouped_df = grouped_df.sort_values(by=val_col, ascending=False).head(15)
            fig_grp = px.bar(
                grouped_df, x=best_cat, y=val_col, color=val_col, text_auto=True,
                title=f"📊 Average {val_col} by {best_cat}",
                color_continuous_scale="Tealgrn"
            )
            fig_grp.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            charts.append({"title": f"Average {val_col} by {best_cat}", "type": "grouped_bar", "fig": fig_grp})
        except Exception as e:
            logger.warning(f"Grouped bar chart error: {e}")

    # 2. Categorical Distribution (Department / Branch / Grade Distribution)
    if best_cat:
        try:
            vc = df[best_cat].astype(str).value_counts().reset_index()
            vc.columns = [best_cat, "Count"]

            if len(vc) <= 7:
                fig_pie = px.pie(
                    vc, names=best_cat, values="Count", title=f"📊 Distribution by {best_cat}",
                    color_discrete_sequence=px.colors.qualitative.Set3
                )
                fig_pie.update_layout(paper_bgcolor="rgba(0,0,0,0)")
                charts.append({"title": f"{best_cat} Pie Distribution", "type": "pie", "fig": fig_pie})

            fig_bar = px.bar(
                vc.head(12), x=best_cat, y="Count", color="Count", text_auto=True,
                title=f"📊 Record Count by {best_cat}", color_continuous_scale="Viridis"
            )
            fig_bar.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            charts.append({"title": f"{best_cat} Count Bar Chart", "type": "bar", "fig": fig_bar})
        except Exception as e:
            logger.warning(f"Categorical chart error: {e}")

    # 3. Year Trend Chart
    if year_cols and num_cols:
        try:
            y_col = year_cols[0]
            v_col = num_cols[0]
            fig_trend = px.line(
                df.groupby(y_col, as_index=False)[v_col].mean(),
                x=y_col, y=v_col, markers=True,
                title=f"📈 {v_col} Trend Across {y_col}",
                color_discrete_sequence=["#0f9d8a"]
            )
            fig_trend.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            charts.append({"title": f"{v_col} Trend Chart", "type": "trend", "fig": fig_trend})
        except Exception as e:
            logger.warning(f"Trend chart error: {e}")

    # 4. Histogram / Box Plot for Numerical Metrics
    if num_cols:
        for n_col in num_cols[:2]:
            try:
                fig_hist = px.histogram(
                    df, x=n_col, nbins=20, title=f"📉 Distribution of {n_col} (Histogram & Box)",
                    color_discrete_sequence=["#2f7cb8"], marginal="box"
                )
                fig_hist.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                charts.append({"title": f"{n_col} Histogram", "type": "histogram", "fig": fig_hist})
            except Exception as e:
                logger.warning(f"Histogram error: {e}")

    # 5. Scatter Plot if 2+ Numerical columns exist
    if len(num_cols) >= 2:
        col_x, col_y = num_cols[0], num_cols[1]
        try:
            fig_scat = px.scatter(
                df, x=col_x, y=col_y, color=best_cat,
                title=f"📍 Comparison: {col_x} vs {col_y}",
                trendline="ols" if len(df) > 5 else None
            )
        except Exception:
            fig_scat = px.scatter(
                df, x=col_x, y=col_y, color=best_cat,
                title=f"📍 Comparison: {col_x} vs {col_y}"
            )
        fig_scat.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        charts.append({"title": f"{col_x} vs {col_y} Scatter Plot", "type": "scatter", "fig": fig_scat})

    # 6. Heatmap / Correlation Matrix
    num_df = df[num_cols].select_dtypes(include="number")
    if num_df.shape[1] > 1:
        try:
            corr = num_df.corr().round(2)
            fig_corr = px.imshow(
                corr, text_auto=True, title="🔗 Metric Correlation Matrix Heatmap",
                color_continuous_scale="RdBu_r", zmin=-1, zmax=1
            )
            fig_corr.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            charts.append({"title": "Correlation Heatmap", "type": "heatmap", "fig": fig_corr})
        except Exception as c_err:
            logger.warning(f"Correlation heatmap error: {c_err}")

    return charts


# ── OpenRouter Free-Model Natural Language Analysis ───────────────────────────

def ask_analytics_agent(username: str, query: str, filename: str | None = None) -> dict:
    """
    Main entry point for Analytics Agent query processing.
    """
    from db_storage import list_analytics_files

    files = list_analytics_files(username)
    if not files:
        return {
            "answer": "No analytics datasets found. Please upload an Excel (.xlsx) or CSV file from the upload card.",
            "stats": {},
            "charts": [],
            "error": "no_datasets"
        }

    target_file = filename or files[0]["filename"]
    try:
        df = _load_dataframe(username, target_file)
    except Exception as exc:
        return {"answer": f"Error loading dataset `{target_file}`: {exc}", "stats": {}, "charts": [], "error": str(exc)}

    stats = analyze_dataset(df, target_file)
    col_info = stats["col_types"]
    charts = generate_visualizations(df, col_info)

    # Build rich prompt with department & group-by summaries for exact AI responses
    context_str = (
        f"Dataset: {target_file}\n"
        f"Total Rows: {len(df)}, Total Columns: {len(df.columns)}\n"
        f"Columns List: {list(df.columns)}\n\n"
    )
    if "group_by_summaries" in stats and stats["group_by_summaries"]:
        context_str += "Departmental / Categorical Aggregations & Breakdown:\n"
        for c_name, g_info in stats["group_by_summaries"].items():
            context_str += f"=== Category: '{c_name}' ===\n"
            context_str += f"  - Counts: {g_info.get('record_counts')}\n"
            if "means" in g_info:
                context_str += f"  - Averages: {g_info.get('means')}\n"
        context_str += "\n"

    if "highest_lowest" in stats:
        context_str += "Overall Numeric Metrics (Min/Max/Mean/StdDev):\n"
        for col_name, vals in stats["highest_lowest"].items():
            context_str += f"  - {col_name}: Mean={vals['mean']}, Max={vals['max']}, Min={vals['min']}\n"
        context_str += "\n"

    data_preview = df.head(50).to_string(index=False)
    context_str += f"Full Data (First 50 Rows):\n{data_preview}"

    answer = ""
    try:
        prompt = (
            f"You are the senior NAAC Academic Analytics AI Agent for DeptOps AI.\n"
            f"Answer the user's specific question accurately and directly using ONLY the dataset context provided below.\n"
            f"If asked about a specific department (e.g. CSE, IT, ECE), search the Category Breakdown and Data table and give EXACT numbers (student count, pass rate, avg marks/CGPA).\n\n"
            f"--- DATASET CONTEXT ---\n{context_str}\n--- END DATASET ---\n\n"
            f"User Question: {query}\n\n"
            f"Formatting Guidelines:\n"
            f"1. Direct, clear answer with EXACT numbers and counts from the data. Use Markdown tables if multiple departments or metrics are compared.\n"
            f"2. Use bold (**text**) for key figures, metrics, and department names.\n"
            f"3. Structure with clean section headers (##) and bullet points.\n"
            f"4. Conclude with 2-3 specific NAAC accreditation insights based on the figures."
        )
        answer = invoke_openrouter_free_models(prompt, temperature=0.1)
    except Exception as exc:
        logger.error(f"OpenRouter free-model panel failed for Analytics Agent: {exc}")
        # Build a smart, question-aware fallback from actual stats
        answer = f"## 📊 Data Analysis for `{target_file}`\n\n"

        # Try to find query-specific data in group-by summaries
        q_lower = query.lower()
        found_specific = False
        if "group_by_summaries" in stats:
            for cat_name, g_info in stats["group_by_summaries"].items():
                counts = g_info.get("record_counts", {})
                means = g_info.get("means", {})
                # Check if user asked about a specific category value
                for cat_val, cnt in counts.items():
                    if cat_val.lower() in q_lower:
                        found_specific = True
                        answer += f"### {cat_name}: **{cat_val}**\n"
                        answer += f"- **Total Students/Records**: {cnt}\n"
                        if means:
                            for metric_name, metric_vals in means.items():
                                if isinstance(metric_vals, dict) and cat_val in metric_vals:
                                    answer += f"- **Average {metric_name}**: {metric_vals[cat_val]}\n"
                        answer += "\n"

        if not found_specific:
            # General summary
            if "group_by_summaries" in stats:
                for k, v in stats["group_by_summaries"].items():
                    answer += f"### {k} Breakdown\n\n"
                    answer += "| Category | Records |\n|---|---|\n"
                    for cat_val, cnt in v.get("record_counts", {}).items():
                        answer += f"| **{cat_val}** | {cnt} |\n"
                    answer += "\n"
            if "highest_lowest" in stats:
                answer += "### Key Numeric Metrics\n\n"
                answer += "| Metric | Mean | Max | Min |\n|---|---|---|---|\n"
                for col, vals in stats["highest_lowest"].items():
                    answer += f"| **{col}** | {vals['mean']} | {vals['max']} | {vals['min']} |\n"
                answer += "\n"

        answer += "\n> ⚠️ *AI analysis is temporarily unavailable. Showing statistical summary from your data.*"

    return {
        "answer": answer,
        "stats": stats,
        "charts": charts,
        "file_used": target_file,
        "dataframe": df
    }


def compare_datasets(username: str, ds1: str, ds2: str) -> str:
    """Compares two uploaded datasets and provides a detailed analytical diff report."""
    try:
        df1 = _load_dataframe(username, ds1)
        df2 = _load_dataframe(username, ds2)
    except Exception as exc:
        return f"Error loading datasets for comparison: {exc}"

    stats1 = analyze_dataset(df1, ds1)
    stats2 = analyze_dataset(df2, ds2)

    # Try LLM comparison
    prompt = (
        f"You are the senior NAAC Academic Analytics AI Agent for DeptOps AI.\n"
        f"Compare the following two academic datasets and generate a comprehensive comparative report.\n\n"
        f"=== Dataset 1: {ds1} ===\n"
        f"Rows: {len(df1)}, Columns: {list(df1.columns)}\n"
        f"Summary Metrics: {stats1.get('highest_lowest', {})}\n"
        f"Group Breakdowns: {stats1.get('group_by_summaries', {})}\n\n"
        f"=== Dataset 2: {ds2} ===\n"
        f"Rows: {len(df2)}, Columns: {list(df2.columns)}\n"
        f"Summary Metrics: {stats2.get('highest_lowest', {})}\n"
        f"Group Breakdowns: {stats2.get('group_by_summaries', {})}\n\n"
        f"Generate:\n"
        f"1. Executive Side-by-Side Summary Table comparing total records, columns, key averages.\n"
        f"2. Major Improvements & Key Changes between Dataset 1 and Dataset 2.\n"
        f"3. Department/Category level comparison highlights.\n"
        f"4. NAAC Peer Team Review recommendations based on the comparison."
    )

    try:
        return invoke_openrouter_free_models(prompt, temperature=0.1)
    except Exception as exc:
        logger.error(f"OpenRouter free-model comparison failed: {exc}")
        # Build statistical fallback comparison
        report = f"## ⚖️ Dataset Comparison: `{ds1}` vs `{ds2}`\n\n"
        report += "### Overview\n\n"
        report += "| Attribute | Dataset 1 | Dataset 2 |\n|---|---|---|\n"
        report += f"| **File** | {ds1} | {ds2} |\n"
        report += f"| **Total Records** | {len(df1)} | {len(df2)} |\n"
        report += f"| **Total Columns** | {len(df1.columns)} | {len(df2.columns)} |\n"
        report += f"| **Columns** | {', '.join(df1.columns[:5])} | {', '.join(df2.columns[:5])} |\n\n"

        # Compare numeric metrics
        hl1 = stats1.get("highest_lowest", {})
        hl2 = stats2.get("highest_lowest", {})
        common_metrics = set(hl1.keys()) & set(hl2.keys())
        if common_metrics:
            report += "### Numeric Metrics Comparison\n\n"
            report += "| Metric | DS1 Mean | DS2 Mean | DS1 Max | DS2 Max |\n|---|---|---|---|---|\n"
            for m in common_metrics:
                report += f"| **{m}** | {hl1[m]['mean']} | {hl2[m]['mean']} | {hl1[m]['max']} | {hl2[m]['max']} |\n"
            report += "\n"

        # Compare categorical distributions
        gs1 = stats1.get("group_by_summaries", {})
        gs2 = stats2.get("group_by_summaries", {})
        common_cats = set(gs1.keys()) & set(gs2.keys())
        for cat in common_cats:
            report += f"### {cat} Distribution Comparison\n\n"
            all_vals = set(gs1[cat].get("record_counts", {}).keys()) | set(gs2[cat].get("record_counts", {}).keys())
            report += f"| {cat} | DS1 Count | DS2 Count |\n|---|---|---|\n"
            for v in sorted(all_vals):
                c1 = gs1[cat].get("record_counts", {}).get(v, 0)
                c2 = gs2[cat].get("record_counts", {}).get(v, 0)
                report += f"| **{v}** | {c1} | {c2} |\n"
            report += "\n"

        report += "\n> ⚠️ *AI analysis is temporarily unavailable. Showing statistical comparison from your data.*"
        return report


# ── Report Exporters (PDF & Excel) ───────────────────────────────────────────

def generate_excel_summary(df: pd.DataFrame, stats: dict) -> bytes:
    """Generates an Excel summary report file as bytes."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.head(100).to_excel(writer, sheet_name="Data Preview", index=False)
        if "numeric_summary" in stats:
            pd.DataFrame(stats["numeric_summary"]).to_excel(writer, sheet_name="Statistical Summary")
        if "year_comparison" in stats:
            pd.DataFrame(stats["year_comparison"]).to_excel(writer, sheet_name="Year Comparisons")
    return output.getvalue()


def generate_pdf_report(username: str, filename: str, answer: str, stats: dict) -> bytes:
    """Generates a styled PDF report for NAAC documentation."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'TitleStyle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=18,
            leading=22, textColor=colors.HexColor('#0f9d8a'), spaceAfter=12
        )
        body_style = ParagraphStyle(
            'BodyStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=10, leading=14, spaceAfter=8
        )

        elements = [
            Paragraph(f"🎓 DeptOps AI — Analytics Report", title_style),
            Paragraph(f"<b>Dataset:</b> {filename} | <b>User:</b> {username}", body_style),
            Spacer(1, 12),
            Paragraph("<b>Executive Summary & OpenRouter AI Insights:</b>", styles['Heading2']),
            Spacer(1, 6),
            Paragraph(answer.replace("\n", "<br/>"), body_style),
            Spacer(1, 14),
        ]

        if "highest_lowest" in stats:
            elements.append(Paragraph("<b>Key Numerical Metrics:</b>", styles['Heading3']))
            table_data = [["Metric Column", "Mean", "Max", "Min", "Std Dev"]]
            for k, v in stats["highest_lowest"].items():
                table_data.append([k, str(v['mean']), str(v['max']), str(v['min']), str(v['std'])])

            t = Table(table_data, colWidths=[140, 70, 70, 70, 70])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f9d8a')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            elements.append(t)

        doc.build(elements)
        return buffer.getvalue()
    except Exception as exc:
        logger.error(f"Failed to generate PDF report: {exc}")
        return f"PDF generation error: {exc}".encode("utf-8")


def run_analytics_agent(username: str, query: str, file_path: str | None = None) -> dict:
    return ask_analytics_agent(username=username, query=query, filename=file_path)
