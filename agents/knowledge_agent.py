"""
Knowledge Agent
---------------
RAG-based Q&A over institutional documents.

Uses TF-IDF retrieval (scikit-learn) — zero downloads, works offline.
Documents and the TF-IDF index are stored in Neon PostgreSQL so they
persist across Render restarts.
"""

import io
import json
import math
import re
from collections import defaultdict
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document

from config import get_llm


# ── Document loading from DB ──────────────────────────────────────────────────

def _load_documents_from_db(username: str) -> list[Document]:
    """Load all knowledge documents stored in the database."""
    import tempfile, os
    from db_storage import list_knowledge_files, load_knowledge_file

    filenames = list_knowledge_files(username)
    all_docs: list[Document] = []

    for filename in filenames:
        content = load_knowledge_file(username, filename)
        if content is None:
            continue
        ext = Path(filename).suffix.lower()
        try:
            # Write to a temp file so LangChain loaders can read it
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                if ext == ".pdf":
                    loader = PyPDFLoader(tmp_path)
                elif ext in (".txt", ".md"):
                    loader = TextLoader(tmp_path, encoding="utf-8")
                else:
                    continue
                docs = loader.load()
                for d in docs:
                    d.metadata["source"] = filename
                all_docs.extend(docs)
            finally:
                os.unlink(tmp_path)
        except Exception as exc:
            print(f"[KnowledgeAgent] Skipped {filename}: {exc}")

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
    corpus = [c.page_content for c in chunks]
    sources = [c.metadata.get("source", "Unknown") for c in chunks]

    tf: list[dict] = []
    for doc in corpus:
        tokens = _tokenize(doc)
        freq: dict[str, int] = defaultdict(int)
        for t in tokens:
            freq[t] += 1
        total = max(len(tokens), 1)
        tf.append({t: count / total for t, count in freq.items()})

    df_counts: dict[str, int] = defaultdict(int)
    for doc_tf in tf:
        for term in doc_tf:
            df_counts[term] += 1

    N = len(corpus)
    return {
        "chunks": corpus,
        "sources": sources,
        "tf": tf,
        "df": dict(df_counts),
        "N": N,
    }


def _query_tfidf(index: dict, query: str, top_k: int = 5) -> list[dict]:
    query_tokens = _tokenize(query)
    N = index["N"]
    df = index["df"]

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


# ── Index persistence (Neon DB) ───────────────────────────────────────────────

def _save_index(username: str, index: dict) -> None:
    from db_storage import save_tfidf_index
    serialisable = {
        "chunks": index["chunks"],
        "sources": index["sources"],
        "tf": [dict(d) for d in index["tf"]],
        "df": index["df"],
        "N": index["N"],
    }
    save_tfidf_index(username, json.dumps(serialisable, ensure_ascii=False))


def _load_index(username: str) -> dict | None:
    from db_storage import load_tfidf_index
    raw = load_tfidf_index(username)
    if raw is None:
        return None
    return json.loads(raw)


def _index_exists(username: str) -> bool:
    idx = _load_index(username)
    return idx is not None and idx.get("N", 0) > 0


# ── Public API ────────────────────────────────────────────────────────────────

def build_vector_store(username: str, force_rebuild: bool = False):
    """Build the TF-IDF index from documents stored in the database."""
    if not force_rebuild and _index_exists(username):
        return _load_index(username)

    docs = _load_documents_from_db(username)
    if not docs:
        raise FileNotFoundError(
            "No documents found in the database. "
            "Please upload PDF or TXT files and click 'Re-index Knowledge Base'."
        )

    chunks = _split(docs)
    print(f"[KnowledgeAgent] Building TF-IDF index: {len(chunks)} chunks...")
    index = _build_tfidf_index(chunks)
    _save_index(username, index)
    print(f"[KnowledgeAgent] Index saved to DB. {len(chunks)} chunks indexed.")
    return index


def _extract_answer_from_context(query: str, hits: list[dict], sources: list[str]) -> str:
    import re as _re
    q_words = set(_re.findall(r"[a-z]+", query.lower()))

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
        return hits[0]["text"][:800].strip()

    src_str = ", ".join(f"`{s}`" for s in sources)
    answer_lines = [f"**Based on {src_str}:**\n"]
    answer_lines.extend(f"- {s}" for s in top_sentences)
    return "\n".join(answer_lines)


def run_knowledge_agent(username: str, query: str, top_k: int = 8) -> dict:
    """Answer a policy/regulation/syllabus question using TF-IDF RAG."""
    from db_storage import list_knowledge_files

    if not _index_exists(username):
        filenames = list_knowledge_files(username)
        if not filenames:
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
            build_vector_store(username, force_rebuild=True)
        except Exception as exc:
            return {"answer": f"Indexing error: {exc}", "sources": [], "error": str(exc)}

    index = _load_index(username)
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
    fallback_answer = _extract_answer_from_context(query, hits, sources)

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "You are an academic policy expert for a university department.\n"
            "Answer the EXACT question asked using ONLY the document context provided.\n"
            "Rules:\n"
            "1. Answer directly — no preamble, no 'Based on the document...' intro.\n"
            "2. Use bullet points for multi-part answers.\n"
            "3. Include specific numbers, percentages, or rules mentioned in the text.\n"
            "4. If the answer is truly not in the context, say: "
            "'This specific information is not in the uploaded documents.'\n"
            "5. Never make up information not in the context.\n"
            "6. Do not include any extra context, unsolicited advice, or conversational filler. Only answer exactly what is asked.",
        ),
        ("human", "Question: {query}\n\nDocument context:\n{context}\n\nAnswer:"),
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


def ingest_documents(username: str) -> dict:
    """Force re-index all documents from the database."""
    from db_storage import list_knowledge_files
    try:
        filenames = list_knowledge_files(username)
        if not filenames:
            return {
                "success": False,
                "message": "No documents found in the database. Upload PDF or TXT files first.",
                "doc_count": 0,
            }
        index = build_vector_store(username, force_rebuild=True)
        return {
            "success": True,
            "message": f"Indexed {len(filenames)} document(s) → {index['N']} chunks stored.",
            "doc_count": len(filenames),
        }
    except Exception as exc:
        return {"success": False, "message": str(exc), "doc_count": 0}


def get_doc_count(username: str) -> int:
    """Return number of indexed chunks, 0 if not built."""
    idx = _load_index(username)
    return idx["N"] if idx else 0
