"""
Analytics Agent for DeptOps AI
-------------------------------
Analyzes ANY academic dataset (Excel / CSV) for NAAC & Department Management.

Capabilities:
- Intelligent column classifier (numerical, categorical, percentage, date, year).
- Automatic chart generator (Bar, Line, Pie, Histogram, Box Plot, Scatter, Heatmap, Correlation, Trend, Comparison).
- Automatic selection of optimal chart based on dataset dimensions.
- Comprehensive statistical summary, anomaly detection, year comparisons, percentage improvements.
- Powered by Gemini 2.5 Flash for natural language Q&A and chart explanations.
- Export support: Excel Summary, PDF Report, PNG Chart rendering.
"""

import io
import re
import pandas as pd
import numpy as np
from pathlib import Path
import logging

from config import get_llm, invoke_llm_with_retry

logger = logging.getLogger("AnalyticsAgent")


# ── File loading & discovery ──────────────────────────────────────────────────

def _load_dataframe(username: str, filename: str) -> pd.DataFrame:
    from db_storage import load_analytics_file
    content = load_analytics_file(username, filename)
    if content is None:
        raise FileNotFoundError(f"File '{filename}' not found in database.")
    buf = io.BytesIO(content)
    ext = Path(filename).suffix.lower()
    return pd.read_csv(buf) if ext == ".csv" else pd.read_excel(buf)


# ── Column Type Detector ──────────────────────────────────────────────────────

def detect_column_types(df: pd.DataFrame) -> dict:
    """
    Automatically detects column categories:
    - numerical
    - categorical
    - percentage
    - date
    - year
    """
    col_info = {
        "numerical": [],
        "categorical": [],
        "percentage": [],
        "date": [],
        "year": [],
        "all_clean": [str(c).strip() for c in df.columns]
    }

    for orig_col in df.columns:
        clean = str(orig_col).strip()
        clean_lower = clean.lower().replace(" ", "_")
        series = df[orig_col].dropna()

        if series.empty:
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
            # Check if percentage values (0-100)
            if series.min() >= 0 and series.max() <= 100 and ("att" in clean_lower or "pass" in clean_lower):
                col_info["percentage"].append(clean)
            col_info["numerical"].append(clean)
        else:
            col_info["categorical"].append(clean)

    return col_info


# ── Deep Data & Statistical Analyzer ─────────────────────────────────────────

def analyze_dataset(df: pd.DataFrame, filename: str) -> dict:
    """
    Generates statistical summary, key insights, highest/lowest, averages,
    anomalies, and percentage improvements across any academic dataset.
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

        # Highest & Lowest identification
        highest_lowest = {}
        for col in num_cols:
            highest_lowest[col] = {
                "max": round(float(df[col].max()), 2),
                "min": round(float(df[col].min()), 2),
                "mean": round(float(df[col].mean()), 2),
                "std": round(float(df[col].std()), 2) if len(df) > 1 else 0.0,
            }
        stats["highest_lowest"] = highest_lowest

        # Anomaly detection (z-score > 2.5 or values outside 1.5 IQR)
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

    # 2. Year-over-Year comparison if year column exists
    if year_cols and num_cols:
        y_col = year_cols[0]
        y_grouped = df.groupby(y_col)[num_cols].mean().round(2)
        stats["year_comparison"] = y_grouped.to_dict()

        # Calculate YoY percentage improvement
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

    # 3. Categorical distribution summaries
    cat_summary = {}
    for col in cat_cols[:4]:
        val_counts = df[col].astype(str).value_counts().head(5).to_dict()
        cat_summary[col] = val_counts
    stats["cat_summary"] = cat_summary

    return stats


# ── Automatic Visualizations Generator ───────────────────────────────────────

def generate_visualizations(df: pd.DataFrame, col_info: dict) -> list[dict]:
    """
    Selects and creates the best Plotly charts based on column types.
    Returns list of dicts: {"title": str, "chart_type": str, "fig": plotly_figure}
    """
    import plotly.express as px
    import plotly.graph_objects as go

    charts = []
    num_cols = col_info["numerical"]
    cat_cols = col_info["categorical"]
    year_cols = col_info["year"]

    # 1. Bar Chart / Trend Line for Year comparison
    if year_cols and num_cols:
        y_col = year_cols[0]
        v_col = num_cols[0]
        fig_trend = px.line(
            df.groupby(y_col, as_index=False)[v_col].mean(),
            x=y_col, y=v_col, markers=True,
            title=f"📈 {v_col} Trend Across Years",
            color_discrete_sequence=["#0f9d8a"]
        )
        fig_trend.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        charts.append({"title": f"{v_col} Trend Chart", "type": "trend", "fig": fig_trend})

    # 2. Categorical Bar Chart / Pie Chart
    if cat_cols:
        c_col = cat_cols[0]
        vc = df[c_col].astype(str).value_counts().reset_index()
        vc.columns = [c_col, "Count"]

        if len(vc) <= 6:
            fig_pie = px.pie(
                vc, names=c_col, values="Count", title=f"📊 Distribution of {c_col}",
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            fig_pie.update_layout(paper_bgcolor="rgba(0,0,0,0)")
            charts.append({"title": f"{c_col} Pie Chart", "type": "pie", "fig": fig_pie})

        fig_bar = px.bar(
            vc.head(10), x=c_col, y="Count", color="Count", text_auto=True,
            title=f"📊 {c_col} Counts (Bar Chart)", color_continuous_scale="Viridis"
        )
        fig_bar.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        charts.append({"title": f"{c_col} Bar Chart", "type": "bar", "fig": fig_bar})

    # 3. Histogram / Box Plot for Numerical Columns
    if num_cols:
        for n_col in num_cols[:2]:
            fig_hist = px.histogram(
                df, x=n_col, nbins=20, title=f"📉 Distribution of {n_col} (Histogram)",
                color_discrete_sequence=["#2f7cb8"], marginal="box"
            )
            fig_hist.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            charts.append({"title": f"{n_col} Histogram & Box Plot", "type": "histogram", "fig": fig_hist})

    # 4. Scatter Plot if 2+ Numerical columns exist
    if len(num_cols) >= 2:
        col_x, col_y = num_cols[0], num_cols[1]
        try:
            fig_scat = px.scatter(
                df, x=col_x, y=col_y, color=cat_cols[0] if cat_cols else None,
                title=f"📍 Comparison: {col_x} vs {col_y} (Scatter Plot)",
                trendline="ols" if len(df) > 5 else None
            )
        except Exception as t_err:
            logger.warning(f"Scatter plot trendline generation fallback (statsmodels issue): {t_err}")
            fig_scat = px.scatter(
                df, x=col_x, y=col_y, color=cat_cols[0] if cat_cols else None,
                title=f"📍 Comparison: {col_x} vs {col_y} (Scatter Plot)"
            )
        fig_scat.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        charts.append({"title": f"{col_x} vs {col_y} Scatter Plot", "type": "scatter", "fig": fig_scat})

    # 5. Heatmap / Correlation Matrix if 3+ Numerical columns exist
    num_df = df[num_cols].select_dtypes(include="number")
    if num_df.shape[1] > 1:
        try:
            corr = num_df.corr().round(2)
            fig_corr = px.imshow(
                corr, text_auto=True, title="🔗 Correlation Matrix Heatmap",
                color_continuous_scale="RdBu_r", zmin=-1, zmax=1
            )
            fig_corr.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            charts.append({"title": "Correlation Matrix Heatmap", "type": "heatmap", "fig": fig_corr})
        except Exception as c_err:
            logger.warning(f"Correlation heatmap error: {c_err}")

    return charts


# ── Gemini 2.5 Flash Natural Language Analysis ────────────────────────────────

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

    # Build rich prompt for Gemini 2.5 Flash
    context_str = f"Dataset: {target_file}\nRows: {len(df)}, Columns: {list(df.columns)}\n\n"
    if "highest_lowest" in stats:
        context_str += f"Key Numeric Metrics (Min/Max/Mean/Std):\n{stats['highest_lowest']}\n\n"
    if "year_improvements" in stats:
        context_str += f"Year-over-Year Percentage Improvements:\n{stats['year_improvements']}\n\n"
    if "anomalies" in stats:
        context_str += f"Detected Anomalies/Outliers: {stats['anomalies']}\n\n"
    context_str += f"Sample Data (First 5 Rows):\n{df.head(5).to_string(index=False)}"

    answer = ""
    try:
        llm = get_llm(temperature=0.2)
        prompt = (
            f"You are the senior NAAC Accreditation & Academic Analytics AI Agent for DeptOps AI.\n"
            f"Analyze the following dataset context and answer the HOD's question accurately.\n\n"
            f"Data Context:\n{context_str}\n\n"
            f"User Question: {query}\n\n"
            f"Provide:\n"
            f"1. Direct, clear answer with exact numbers and percentage comparisons.\n"
            f"2. Key trends, anomalies, highest/lowest highlights.\n"
            f"3. Actionable departmental recommendations for NAAC accreditation review."
        )
        res = invoke_llm_with_retry(llm, prompt)
        answer = res.content if hasattr(res, "content") else str(res)
    except Exception as exc:
        logger.error(f"Gemini LLM call failed for Analytics Agent: {exc}")
        # Direct rule-based fallback answer
        answer = f"**Data Summary for `{target_file}`:**\n\n"
        if "highest_lowest" in stats:
            for k, v in stats["highest_lowest"].items():
                answer += f"- **{k}**: Avg = {v['mean']}, Max = {v['max']}, Min = {v['min']}\n"
        if "year_improvements" in stats:
            for k, v in stats["year_improvements"].items():
                answer += f"- **{k} Change ({v['from_year']} -> {v['to_year']})**: {v['change_pct']}%\n"

    return {
        "answer": answer,
        "stats": stats,
        "charts": charts,
        "file_used": target_file,
        "dataframe": df
    }


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
            Paragraph("<b>Executive Summary & Gemini AI Insights:</b>", styles['Heading2']),
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
