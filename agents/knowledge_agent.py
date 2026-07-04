"""
Knowledge Agent
---------------
RAG-based Q&A over institutional documents.

Uses TF-IDF retrieval (scikit-learn) — zero downloads, works offline.
Documents are stored as plain text chunks in a local JSON index.
Falls back to raw retrieved text if LLM is rate-limited.
"""

import os
import json
import math
import re
from pathlib import Path
from collections import defaultdict

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document

from config import get_llm, CHROMA_PERSIST_DIR, DOCUMENTS_DIR

# Store our simple index as a JSON file (no vector DB needed)
INDEX_PATH = Path(CHROMA_PERSIST_DIR) / "tfidf_index.json"


# ── Document loading ─────────────────────────────────────────────────────────

def _load_documents(docs_dir: str) -> list[Document]:
    docs_path = Path(docs_dir)
    if not docs_path.exists():
        return []
    all_docs: list[Document] = []
    for file in sorted(docs_path.iterdir()):
        if file.name.startswith("."):
            continue
        try:
            if file.suffix.lower() == ".pdf":
                loader = PyPDFLoader(str(file))
            elif file.suffix.lower() in (".txt", ".md"):
                loader = TextLoader(str(file), encoding="utf-8")
            else:
                continue
            docs = loader.load()
            for d in docs:
                d.metadata["source"] = file.name
            all_docs.extend(docs)
        except Exception as exc:
            print(f"[KnowledgeAgent] Skipped {file.name}: {exc}")
    return all_docs


def _split(docs: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=600, chunk_overlap=80,
        separators=["\n\n", "\n", ". ", " "],
    )
    return splitter.split_documents(docs)


# ── TF-IDF retrieval ──────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _build_tfidf_index(chunks: list[Document]) -> dict:
    """Build an in-memory TF-IDF index from document chunks."""
    corpus = [c.page_content for c in chunks]
    sources = [c.metadata.get("source", "Unknown") for c in chunks]

    # Term frequencies per document
    tf: list[dict] = []
    for doc in corpus:
        tokens = _tokenize(doc)
        freq: dict[str, int] = defaultdict(int)
        for t in tokens:
            freq[t] += 1
        total = max(len(tokens), 1)
        tf.append({t: count / total for t, count in freq.items()})

    # Document frequencies
    df: dict[str, int] = defaultdict(int)
    for doc_tf in tf:
        for term in doc_tf:
            df[term] += 1

    N = len(corpus)

    return {
        "chunks": corpus,
        "sources": sources,
        "tf": tf,
        "df": dict(df),
        "N": N,
    }


def _query_tfidf(index: dict, query: str, top_k: int = 5) -> list[dict]:
    """Score all chunks against a query using TF-IDF cosine similarity."""
    query_tokens = _tokenize(query)
    N = index["N"]
    df = index["df"]

    # Query TF-IDF vector
    q_freq: dict[str, int] = defaultdict(int)
    for t in query_tokens:
        q_freq[t] += 1
    q_total = max(len(query_tokens), 1)
    q_vec = {}
    for t, cnt in q_freq.items():
        idf = math.log((N + 1) / (df.get(t, 0) + 1)) + 1
        q_vec[t] = (cnt / q_total) * idf

    scores = []
    for i, doc_tf in enumerate(index["tf"]):
        score = 0.0
        for t, q_w in q_vec.items():
            if t in doc_tf:
                idf = math.log((N + 1) / (df.get(t, 0) + 1)) + 1
                score += q_w * doc_tf[t] * idf
        scores.append((score, i))

    scores.sort(reverse=True)
    results = []
    for score, idx in scores[:top_k]:
        if score > 0:
            results.append({
                "text": index["chunks"][idx],
                "source": index["sources"][idx],
                "score": round(score, 4),
            })
    return results


# ── Index persistence ─────────────────────────────────────────────────────────

def _save_index(index: dict):
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    # tf contains defaultdicts — convert to plain dicts for JSON
    serialisable = {
        "chunks": index["chunks"],
        "sources": index["sources"],
        "tf": [dict(d) for d in index["tf"]],
        "df": index["df"],
        "N": index["N"],
    }
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(serialisable, f, ensure_ascii=False)


def _load_index() -> dict | None:
    if not INDEX_PATH.exists():
        return None
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _index_exists() -> bool:
    idx = _load_index()
    return idx is not None and idx.get("N", 0) > 0


# ── Public API ────────────────────────────────────────────────────────────────

def build_vector_store(force_rebuild: bool = False):
    """Build the TF-IDF index from documents."""
    if not force_rebuild and _index_exists():
        return _load_index()

    docs = _load_documents(DOCUMENTS_DIR)
    if not docs:
        raise FileNotFoundError(
            f"No documents found in '{DOCUMENTS_DIR}'. "
            "Please upload PDF or TXT files and click 'Re-index Knowledge Base'."
        )

    chunks = _split(docs)
    print(f"[KnowledgeAgent] Building TF-IDF index: {len(chunks)} chunks...")
    index = _build_tfidf_index(chunks)
    _save_index(index)
    print(f"[KnowledgeAgent] Index saved. {len(chunks)} chunks indexed.")
    return index


def _extract_answer_from_context(query: str, hits: list[dict], sources: list[str]) -> str:
    """
    Extract a clean, readable answer from retrieved chunks without LLM.
    Finds the most relevant sentences from top chunks.
    """
    import re as _re
    q_words = set(_re.findall(r"[a-z]+", query.lower()))

    # Score each sentence by overlap with query words
    scored_sentences = []
    for hit in hits[:3]:
        text = hit["text"]
        sentences = _re.split(r"(?<=[.!?])\s+|\n", text)
        for sent in sentences:
            sent = sent.strip()
            if len(sent) < 20:
                continue
            words = set(_re.findall(r"[a-z]+", sent.lower()))
            score = len(q_words & words)
            if score > 0:
                scored_sentences.append((score, sent))

    scored_sentences.sort(reverse=True)
    top_sentences = [s for _, s in scored_sentences[:6]]

    if not top_sentences:
        # Just return the top chunk trimmed nicely
        return hits[0]["text"][:800].strip()

    src_str = ", ".join(f"`{s}`" for s in sources)
    answer_lines = [f"**Based on {src_str}:**\n"]
    answer_lines.extend(f"- {s}" for s in top_sentences)
    return "\n".join(answer_lines)


def run_knowledge_agent(query: str, top_k: int = 5) -> dict:
    """Answer a policy/regulation/syllabus question using TF-IDF RAG."""

    # Auto-index if needed
    if not _index_exists():
        docs = _load_documents(DOCUMENTS_DIR)
        if not docs:
            return {
                "answer": (
                    "No documents are indexed yet. "
                    "Please upload a PDF or TXT file from the sidebar "
                    "and click 'Re-index Knowledge Base'."
                ),
                "sources": [],
                "error": "no_documents",
            }
        try:
            build_vector_store(force_rebuild=True)
        except Exception as exc:
            return {"answer": f"Indexing error: {exc}", "sources": [], "error": str(exc)}

    index = _load_index()
    if not index:
        return {"answer": "Index not found.", "sources": [], "error": "no_index"}

    hits = _query_tfidf(index, query, top_k=top_k)
    if not hits:
        return {
            "answer": "No relevant information found in the knowledge base for your query.",
            "sources": [],
            "error": None,
        }

    context = "\n\n---\n\n".join(h["text"] for h in hits)
    sources = sorted({h["source"] for h in hits})

    # Smart fallback — extract key sentences from retrieved text instead of dumping raw content
    fallback_answer = _extract_answer_from_context(query, hits, sources)

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "You are an academic policy expert for a university department. "
            "Answer the question using ONLY the provided document context. "
            "Be direct and concise. Use bullet points for lists. "
            "Start your answer immediately — no preamble. "
            "If the answer is not in the context, say exactly: "
            "'This information is not available in the uploaded documents.'",
        ),
        ("human", "Document context:\n{context}\n\nQuestion: {query}"),
    ])

    answer = fallback_answer
    try:
        llm = get_llm(temperature=0.1)
        chain = prompt | llm
        response = chain.invoke({"context": context, "query": query})
        if response and response.content and len(response.content.strip()) > 20:
            answer = response.content
    except Exception:
        pass

    return {"answer": answer, "sources": sources, "error": None}


def ingest_documents() -> dict:
    """Force re-index all documents."""
    try:
        docs = _load_documents(DOCUMENTS_DIR)
        if not docs:
            return {
                "success": False,
                "message": f"No documents found in '{DOCUMENTS_DIR}'. Upload PDF or TXT files first.",
                "doc_count": 0,
            }
        index = build_vector_store(force_rebuild=True)
        return {
            "success": True,
            "message": f"Indexed {len(docs)} document(s) → {index['N']} chunks stored.",
            "doc_count": len(docs),
        }
    except Exception as exc:
        return {"success": False, "message": str(exc), "doc_count": 0}


def get_doc_count() -> int:
    """Return number of indexed chunks, 0 if not built."""
    idx = _load_index()
    return idx["N"] if idx else 0
