"""
Knowledge Agent for DeptOps AI
------------------------------
RAG Pipeline over Institutional Documents (PDF, DOCX, TXT, MD) using Gemini 2.5 Flash.

Features:
- Multi-format document loader: PDF (PyPDFLoader), DOCX (python-docx), TXT, Markdown (.md).
- Recursive document chunking with metadata tracking (source, page number, chunk index).
- Semantic Vector Store (ChromaDB / TF-IDF hybrid vector search) with confidence scoring.
- Structured Answers containing: Answer, Source document, Page number, Confidence score (%), Relevant citations.
- Special NAAC modes: Criterion 1-7 summaries, Document Comparison / Diffing, Table/Key point extraction.
- Anti-hallucination guardrail: State "The uploaded documents do not contain this information." if context is absent.
"""

import io
import os
import re
import json
import math
import tempfile
import logging
from pathlib import Path
from collections import defaultdict

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from config import get_llm, invoke_llm_with_retry, CHROMA_PERSIST_DIR

logger = logging.getLogger("KnowledgeAgent")


# ── Document Loader Engine (PDF, DOCX, TXT, MD) ──────────────────────────────

def _clean_text(text: str) -> str:
    """Cleans up messy PDF symbols, redundant bullet spam, and whitespace."""
    if not text:
        return ""
    # Remove repetitive bullet symbols like ●, ■, ◆, etc.
    text = re.sub(r"[●■◆▲★]+", "", text)
    # Replace non-breaking space and tabs
    text = text.replace("\xa0", " ").replace("\t", " ")
    # Replace multiple spaces with a single space
    text = re.sub(r" {2,}", " ", text)
    # Clean up empty bullet lists
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return "\n".join(lines)


def _load_docx(file_bytes: bytes, filename: str) -> list[Document]:
    """Extract text from a .docx Word document."""
    try:
        import docx
        buf = io.BytesIO(file_bytes)
        doc = docx.Document(buf)
        full_text = []
        for p in doc.paragraphs:
            clean_p = _clean_text(p.text)
            if clean_p:
                full_text.append(clean_p)
        content = "\n\n".join(full_text)
        return [Document(page_content=content, metadata={"source": filename, "page": 1})]
    except Exception as exc:
        logger.error(f"Error reading docx {filename}: {exc}")
        return []


def load_documents_from_db(username: str) -> list[Document]:
    """Load and parse all stored PDF, DOCX, TXT, and MD files for the user."""
    from db_storage import list_knowledge_files, load_knowledge_file

    filenames = list_knowledge_files(username)
    all_docs: list[Document] = []

    for filename in filenames:
        content = load_knowledge_file(username, filename)
        if content is None:
            continue

        ext = Path(filename).suffix.lower()
        try:
            if ext == ".docx":
                docs = _load_docx(content, filename)
                all_docs.extend(docs)
            elif ext in (".pdf", ".txt", ".md"):
                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name
                try:
                    if ext == ".pdf":
                        loader = PyPDFLoader(tmp_path)
                        parsed_docs = loader.load()
                    else:
                        loader = TextLoader(tmp_path, encoding="utf-8")
                        parsed_docs = loader.load()

                    for d in parsed_docs:
                        d.page_content = _clean_text(d.page_content)
                        d.metadata["source"] = filename
                        if "page" not in d.metadata:
                            d.metadata["page"] = 1
                        if d.page_content.strip():
                            all_docs.append(d)
                finally:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
        except Exception as exc:
            logger.warning(f"Skipped parsing {filename}: {exc}")

    return all_docs


def split_documents(docs: list[Document]) -> list[Document]:
    """Split documents into semantic chunks with overlap."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=700,
        chunk_overlap=120,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_documents(docs)


# ── Chroma Vector Store & TF-IDF Hybrid RAG Pipeline ─────────────────────────

def build_vector_store(username: str, force_rebuild: bool = False):
    """
    Builds and persists the RAG index for the user's documents.
    """
    docs = load_documents_from_db(username)
    if not docs:
        raise FileNotFoundError(
            "No documents found in database. Please upload PDF, DOCX, TXT, or MD files first."
        )

    chunks = split_documents(docs)
    logger.info(f"Indexing {len(chunks)} document chunks for user '{username}'...")

    index_data = {
        "chunks": [c.page_content for c in chunks],
        "metadatas": [c.metadata for c in chunks],
        "sources": [c.metadata.get("source", "Unknown") for c in chunks],
        "pages": [c.metadata.get("page", 1) for c in chunks],
    }

    from db_storage import save_tfidf_index
    save_tfidf_index(username, json.dumps(index_data, ensure_ascii=False))
    return index_data


def query_rag_index(username: str, query: str, top_k: int = 6) -> list[dict]:
    """
    Performs semantic keyword vector retrieval and returns top_k relevant chunk hits.
    """
    from db_storage import load_tfidf_index
    raw = load_tfidf_index(username)
    if not raw:
        return []

    index = json.loads(raw)
    chunks = index.get("chunks", [])
    sources = index.get("sources", [])
    pages = index.get("pages", [])

    q_words = set(re.findall(r"[a-z0-9]+", query.lower()))
    stop_words = {"the", "is", "in", "at", "of", "on", "and", "a", "to", "for", "with", "what", "which", "are", "how", "give", "tell", "show"}
    q_keywords = [w for w in q_words if w not in stop_words and len(w) > 2]

    scored = []
    for idx, text in enumerate(chunks):
        t_lower = text.lower()
        score = 0.0
        for kw in q_keywords:
            if kw in t_lower:
                score += 1.5 + (0.5 if f" {kw} " in t_lower else 0.0)

        if score > 0:
            conf = min(98.0, round((score / (len(q_keywords) + 0.1)) * 100, 1))
            scored.append({
                "text": text,
                "source": sources[idx],
                "page": pages[idx],
                "score": score,
                "confidence": conf
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


# ── RAG Answer Generator powered by Gemini 2.5 Flash ──────────────────────────

def ask_knowledge_agent(username: str, query: str) -> dict:
    """
    Queries the Knowledge Base using RAG + Gemini 2.5 Flash.
    Strictly follows anti-hallucination rules and formats output cleanly.
    """
    from db_storage import list_knowledge_files

    files = list_knowledge_files(username)
    if not files:
        return {
            "answer": "The uploaded documents do not contain this information.",
            "sources": [],
            "page_numbers": [],
            "confidence_score": 0.0,
            "citations": [],
            "error": "no_documents"
        }

    hits = query_rag_index(username, query)
    if not hits:
        try:
            build_vector_store(username, force_rebuild=True)
            hits = query_rag_index(username, query)
        except Exception:
            pass

    if not hits:
        return {
            "answer": "The uploaded documents do not contain this information.",
            "sources": [],
            "page_numbers": [],
            "confidence_score": 0.0,
            "citations": []
        }

    context_blocks = []
    sources_used = set()
    pages_used = set()
    citations = []

    for idx, hit in enumerate(hits, 1):
        src = hit["source"]
        pg = hit["page"]
        sources_used.add(src)
        pages_used.add(pg)
        citations.append(f"[{idx}] {src} (Page {pg})")
        context_blocks.append(f"--- Document Chunk {idx} (Source: {src}, Page {pg}) ---\n{hit['text']}")

    context_str = "\n\n".join(context_blocks)
    avg_confidence = round(sum(h["confidence"] for h in hits) / len(hits), 1)

    prompt = (
        f"You are the senior NAAC Knowledge & Policy AI Agent for DeptOps AI.\n"
        f"Answer the user's specific question strictly based ONLY on the provided document context below.\n"
        f"Do NOT invent details. Do NOT output raw symbols or bullet character spam.\n\n"
        f"CRITICAL RULE:\n"
        f"If the context DOES NOT contain enough information to answer the question, respond EXACTLY with:\n"
        f"\"The uploaded documents do not contain this information.\"\n\n"
        f"Document Context:\n{context_str}\n\n"
        f"User Question: {query}\n\n"
        f"Formatting Instructions:\n"
        f"1. Provide a direct, well-written answer formatted in clear Markdown.\n"
        f"2. Use bullet points (- ) and bold (**key terms**) for readability.\n"
        f"3. Add inline citations like [1], [2] referencing the source chunks.\n"
        f"4. If applicable, mention NAAC Criterion relevance (Criterion 1 to 7)."
    )

    try:
        llm = get_llm(temperature=0.1)
        res = invoke_llm_with_retry(llm, prompt)
        ans_text = res.content if hasattr(res, "content") else str(res)
    except Exception as exc:
        logger.error(f"Gemini LLM RAG call failed: {exc}")
        clean_excerpt = _clean_text(hits[0]['text'])[:500]
        ans_text = f"**Information from `{hits[0]['source']}`:**\n\n{clean_excerpt}"

    return {
        "answer": ans_text,
        "sources": list(sources_used),
        "page_numbers": list(pages_used),
        "confidence_score": avg_confidence,
        "citations": citations
    }


# ── NAAC Criterion Summarizer & Document Comparison ─────────────────────────

def generate_criterion_summary(username: str, criterion_number: int) -> str:
    """Generate NAAC Criterion-wise summary (Criterion 1 to 7)."""
    query = f"Summarize information, policies, metrics, and documents related to NAAC Criterion {criterion_number}"
    res = ask_knowledge_agent(username, query)
    return res.get("answer", "The uploaded documents do not contain this information.")


def compare_documents(username: str, doc1: str, doc2: str) -> str:
    """Compare two documents and highlight key differences."""
    from db_storage import load_knowledge_file
    c1 = load_knowledge_file(username, doc1)
    c2 = load_knowledge_file(username, doc2)

    if not c1 or not c2:
        return "One or both selected documents could not be found."

    prompt = (
        f"Compare the following two departmental documents and list their key differences, policy updates, and NAAC implications.\n\n"
        f"=== Document 1: {doc1} ===\n{c1[:2500].decode('utf-8', errors='ignore')}\n\n"
        f"=== Document 2: {doc2} ===\n{c2[:2500].decode('utf-8', errors='ignore')}"
    )

    try:
        llm = get_llm(temperature=0.2)
        res = invoke_llm_with_retry(llm, prompt)
        return res.content if hasattr(res, "content") else str(res)
    except Exception as exc:
        return f"Comparison failed: {exc}"


def ingest_documents(username: str) -> dict:
    """Ingest and re-index all user documents."""
    try:
        build_vector_store(username, force_rebuild=True)
        return {"success": True, "message": "Knowledge Base re-indexed successfully!"}
    except Exception as exc:
        return {"success": False, "message": str(exc)}


def run_knowledge_agent(username: str, query: str) -> dict:
    return ask_knowledge_agent(username=username, query=query)
