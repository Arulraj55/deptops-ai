"""
api.py — DeptOps AI FastAPI Backend
Exposes all agent operations as REST endpoints.
Streamlit frontend calls these endpoints instead of importing agents directly.
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import json

app = FastAPI(title="DeptOps AI API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth / DB Init ────────────────────────────────────────────────────────────

@app.post("/auth/init")
def init_db():
    from auth import _init_db
    _init_db()
    return {"ok": True}


@app.post("/auth/signin")
def signin(username: str = Form(...), password: str = Form(...)):
    from auth import _get_user, _verify
    row = _get_user(username.strip())
    if row and _verify(password, row[2]):
        return {"authenticated": True, "username": row[0], "full_name": row[1] or row[0]}
    raise HTTPException(status_code=401, detail="Invalid username or password.")


@app.post("/auth/signup")
def signup(
    username: str = Form(...),
    full_name: str = Form(...),
    password: str = Form(...),
):
    from auth import _get_user, _create_user
    if _get_user(username.strip()):
        raise HTTPException(status_code=409, detail="Username already taken.")
    _create_user(username.strip(), full_name.strip(), password)
    return {"authenticated": True, "username": username.strip(), "full_name": full_name.strip()}


# ── File Storage ──────────────────────────────────────────────────────────────

@app.post("/files/analytics/upload")
async def upload_analytics(username: str = Form(...), file: UploadFile = File(...)):
    import db_storage
    content = await file.read()
    db_storage.save_analytics_file(username, file.filename, content)
    return {"ok": True, "filename": file.filename}


@app.get("/files/analytics/list")
def list_analytics(username: str):
    import db_storage
    return db_storage.list_analytics_files(username)


@app.post("/files/knowledge/upload")
async def upload_knowledge(username: str = Form(...), file: UploadFile = File(...)):
    import db_storage
    content = await file.read()
    db_storage.save_knowledge_file(username, file.filename, content)
    return {"ok": True, "filename": file.filename}


@app.get("/files/knowledge/list")
def list_knowledge(username: str):
    import db_storage
    return db_storage.list_knowledge_files(username)


@app.get("/files/knowledge/chunk-count")
def chunk_count(username: str):
    import db_storage
    raw = db_storage.load_tfidf_index(username)
    if not raw:
        return {"count": 0}
    idx = json.loads(raw)
    return {"count": len(idx.get("chunks", []))}


# ── Knowledge Agent ───────────────────────────────────────────────────────────

@app.post("/knowledge/reindex")
def reindex(username: str = Form(...)):
    from agents.knowledge_agent import ingest_documents
    return ingest_documents(username)


class KnowledgeQuery(BaseModel):
    username: str
    query: str


@app.post("/knowledge/ask")
def ask_knowledge(body: KnowledgeQuery):
    from agents.knowledge_agent import ask_knowledge_agent
    result = ask_knowledge_agent(body.username, body.query)
    # Convert sets to lists for JSON serialization
    result["sources"] = list(result.get("sources", []))
    result["page_numbers"] = list(result.get("page_numbers", []))
    return result


class CriterionRequest(BaseModel):
    username: str
    criterion_number: int


@app.post("/knowledge/criterion-summary")
def criterion_summary(body: CriterionRequest):
    from agents.knowledge_agent import generate_criterion_summary
    summary = generate_criterion_summary(body.username, body.criterion_number)
    return {"summary": summary}


# ── Analytics Agent ───────────────────────────────────────────────────────────

class AnalyticsQuery(BaseModel):
    username: str
    query: str
    filename: Optional[str] = None


@app.post("/analytics/ask")
def ask_analytics(body: AnalyticsQuery):
    from agents.analytics_agent import ask_analytics_agent
    result = ask_analytics_agent(body.username, body.query, body.filename)
    # Remove non-serializable objects (dataframe, plotly figs)
    result.pop("dataframe", None)
    result.pop("charts", None)
    stats = result.get("stats", {})
    # Remove non-serializable nested objects
    if "col_types" in stats:
        stats["col_types"] = {k: list(v) if isinstance(v, (set, list)) else v
                              for k, v in stats["col_types"].items()}
    return result


class AnalyticsFullRequest(BaseModel):
    username: str
    filename: str


@app.post("/analytics/full")
def analytics_full(body: AnalyticsFullRequest):
    """Returns stats + chart specs (no plotly objects — frontend builds charts from data)."""
    from agents.analytics_agent import ask_analytics_agent
    import pandas as pd

    result = ask_analytics_agent(body.username, "Full dataset statistical summary and NAAC insights", body.filename)
    df: pd.DataFrame = result.get("dataframe")
    stats = result.get("stats", {})

    # Serialize stats safely
    def _safe(obj):
        if isinstance(obj, (set,)):
            return list(obj)
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        return obj

    safe_stats = json.loads(json.dumps(stats, default=str))

    # Build chart data (raw data for frontend to render with Plotly)
    chart_data = []
    if df is not None:
        col_info = stats.get("col_types", {})
        num_cols = col_info.get("numerical", [])
        cat_cols = col_info.get("categorical", [])
        year_cols = col_info.get("year", [])

        best_cat = next(
            (c for c in cat_cols if any(k in c.lower() for k in ("dept", "department", "branch", "course", "section"))),
            cat_cols[0] if cat_cols else None
        )

        if best_cat and num_cols:
            val_col = num_cols[0]
            grouped = df.groupby(best_cat, as_index=False)[val_col].mean().round(2)
            grouped = grouped.sort_values(by=val_col, ascending=False).head(15)
            chart_data.append({
                "type": "bar",
                "title": f"Average {val_col} by {best_cat}",
                "x": grouped[best_cat].tolist(),
                "y": grouped[val_col].tolist(),
                "x_label": best_cat,
                "y_label": val_col,
            })

        if best_cat:
            vc = df[best_cat].astype(str).value_counts().reset_index()
            vc.columns = [best_cat, "Count"]
            chart_data.append({
                "type": "pie",
                "title": f"Distribution by {best_cat}",
                "labels": vc[best_cat].tolist(),
                "values": vc["Count"].tolist(),
            })

        if year_cols and num_cols:
            y_col, v_col = year_cols[0], num_cols[0]
            trend = df.groupby(y_col, as_index=False)[v_col].mean()
            chart_data.append({
                "type": "line",
                "title": f"{v_col} Trend Across {y_col}",
                "x": [str(v) for v in trend[y_col].tolist()],
                "y": trend[v_col].round(2).tolist(),
                "x_label": y_col,
                "y_label": v_col,
            })

        for n_col in num_cols[:2]:
            chart_data.append({
                "type": "histogram",
                "title": f"Distribution of {n_col}",
                "values": df[n_col].dropna().tolist(),
                "x_label": n_col,
            })

        if len(num_cols) >= 2:
            chart_data.append({
                "type": "scatter",
                "title": f"{num_cols[0]} vs {num_cols[1]}",
                "x": df[num_cols[0]].tolist(),
                "y": df[num_cols[1]].tolist(),
                "x_label": num_cols[0],
                "y_label": num_cols[1],
            })

    return {
        "answer": result.get("answer", ""),
        "stats": safe_stats,
        "chart_data": chart_data,
        "file_used": result.get("file_used", body.filename),
        "preview": df.head(20).to_dict(orient="records") if df is not None else [],
        "total_rows": len(df) if df is not None else 0,
        "total_cols": len(df.columns) if df is not None else 0,
    }


class CompareRequest(BaseModel):
    username: str
    ds1: str
    ds2: str


@app.post("/analytics/compare")
def compare_datasets(body: CompareRequest):
    from agents.analytics_agent import compare_datasets
    result = compare_datasets(body.username, body.ds1, body.ds2)
    return {"result": result}


class ExcelReportRequest(BaseModel):
    username: str
    filename: str


@app.post("/analytics/excel-report")
def excel_report(body: ExcelReportRequest):
    from fastapi.responses import Response
    from agents.analytics_agent import ask_analytics_agent, generate_excel_summary
    result = ask_analytics_agent(body.username, "summary", body.filename)
    df = result.get("dataframe")
    stats = result.get("stats", {})
    if df is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    excel_bytes = generate_excel_summary(df, stats)
    return Response(content=excel_bytes, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.post("/analytics/pdf-report")
def pdf_report(body: ExcelReportRequest):
    from fastapi.responses import Response
    from agents.analytics_agent import ask_analytics_agent, generate_pdf_report
    result = ask_analytics_agent(body.username, "summary", body.filename)
    df = result.get("dataframe")
    stats = result.get("stats", {})
    if df is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    pdf_bytes = generate_pdf_report(body.username, body.filename, result.get("answer", ""), stats)
    return Response(content=pdf_bytes, media_type="application/pdf")


# ── Website Testing Agent ─────────────────────────────────────────────────────

class WebsiteAuditRequest(BaseModel):
    url: str
    username: str = "hod"


@app.post("/website/audit")
def website_audit(body: WebsiteAuditRequest):
    from agents.website_testing_agent import run_website_testing_agent
    result = run_website_testing_agent(body.url.strip(), username=body.username)
    # Remove non-serializable objects
    result.pop("all_pages", None)
    return result


@app.post("/website/pdf-report")
def website_pdf_report(body: WebsiteAuditRequest):
    from fastapi.responses import Response
    from agents.website_testing_agent import run_website_testing_agent, generate_website_pdf_report
    result = run_website_testing_agent(body.url.strip(), username=body.username)
    pdf_bytes = generate_website_pdf_report(
        body.url,
        result.get("summary", {}),
        result.get("ai_report", "")
    )
    return Response(content=pdf_bytes, media_type="application/pdf")
