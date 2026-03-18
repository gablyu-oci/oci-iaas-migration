"""
RAG (Retrieval-Augmented Generation) for migration tool docs.

Stack:
  - pgvector  : vector similarity search inside existing PostgreSQL
  - fastembed : ONNX-based embeddings, no PyTorch, ~130 MB model download on first use
                Model: BAAI/bge-small-en-v1.5  (384-dim, fast, good quality)

Workflow:
  index_docs(docs_root)   — chunk all .md files, embed, upsert into doc_chunks table
  retrieve(query, k)      — embed query, return top-k chunks as formatted string
  retrieve_for_policy(policy_json, services, k) — convenience wrapper for IAM translation

Drop a new .md file into docs/core/ or docs/services/ and re-run index_docs()
(or POST /api/rag/index) to have it picked up automatically.
"""

from __future__ import annotations

import re
import hashlib
import asyncpg
from pathlib import Path
from typing import Optional

# ── Embedding model (lazy-loaded) ─────────────────────────────────────────────
_embedder = None
EMBEDDING_DIM = 384
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


def _get_embedder():
    global _embedder
    if _embedder is None:
        from fastembed import TextEmbedding
        _embedder = TextEmbedding(model_name=EMBEDDING_MODEL)
    return _embedder


def embed(texts: list[str]) -> list[list[float]]:
    """Embed a list of strings, return list of float vectors."""
    model = _get_embedder()
    return [list(map(float, v)) for v in model.embed(texts)]


# ── DB helpers ─────────────────────────────────────────────────────────────────

async def _get_conn(db_url: str) -> asyncpg.Connection:
    """Convert SQLAlchemy async URL to asyncpg-compatible URL."""
    url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    return await asyncpg.connect(url)


async def ensure_table(db_url: str) -> None:
    """Create doc_chunks table and HNSW index if they don't exist."""
    conn = await _get_conn(db_url)
    try:
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS doc_chunks (
                id          SERIAL PRIMARY KEY,
                file_name   TEXT NOT NULL,
                doc_section TEXT NOT NULL,
                doc_type    TEXT NOT NULL,
                content     TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                embedding   vector({EMBEDDING_DIM}),
                UNIQUE (file_name, doc_section)
            );
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS doc_chunks_embedding_idx
            ON doc_chunks USING hnsw (embedding vector_cosine_ops);
        """)
    finally:
        await conn.close()


# ── Chunking ───────────────────────────────────────────────────────────────────

def chunk_markdown(text: str, file_name: str, max_chars: int = 1500) -> list[dict]:
    """
    Split a markdown file into chunks by ## headings.
    Chunks larger than max_chars are split further at paragraph boundaries.
    Returns list of {file_name, section, content} dicts.
    """
    # Split on ## or ### headings
    parts = re.split(r'\n(?=#{1,3} )', text.strip())
    chunks = []
    for part in parts:
        if not part.strip():
            continue
        # Extract heading as section label
        first_line = part.split('\n', 1)[0].strip()
        section = re.sub(r'^#+\s*', '', first_line)[:120] or "intro"

        if len(part) <= max_chars:
            chunks.append({"file_name": file_name, "section": section, "content": part.strip()})
        else:
            # Split long sections at blank lines
            paras = re.split(r'\n{2,}', part)
            buffer, buf_section = [], section
            for i, para in enumerate(paras):
                buffer.append(para)
                if sum(len(b) for b in buffer) >= max_chars or i == len(paras) - 1:
                    content = "\n\n".join(buffer).strip()
                    if content:
                        chunks.append({
                            "file_name": file_name,
                            "section": buf_section,
                            "content": content,
                        })
                    buffer = []
                    buf_section = f"{section} (cont.)"
    return chunks


# ── Indexing ───────────────────────────────────────────────────────────────────

async def index_docs(docs_root: Path, db_url: str) -> dict:
    """
    Scan docs_root for .md files (core/ and services/ subdirs), chunk them,
    embed each chunk, and upsert into doc_chunks.

    Returns {"indexed": N, "skipped": M} where skipped = unchanged chunks.
    """
    await ensure_table(db_url)

    md_files = list(docs_root.rglob("*.md"))
    if not md_files:
        return {"indexed": 0, "skipped": 0, "error": "no .md files found"}

    all_chunks: list[dict] = []
    for path in sorted(md_files):
        # doc_type = immediate subdirectory name (e.g. "core", "services", "tools")
        try:
            doc_type = path.relative_to(docs_root).parts[0]
        except (ValueError, IndexError):
            doc_type = "other"
        text = path.read_text(encoding="utf-8")
        for chunk in chunk_markdown(text, path.name):
            chunk["doc_type"] = doc_type
            chunk["content_hash"] = hashlib.sha256(chunk["content"].encode()).hexdigest()[:16]
            all_chunks.append(chunk)

    if not all_chunks:
        return {"indexed": 0, "skipped": 0}

    conn = await _get_conn(db_url)
    try:
        # Check which chunks already exist with same content hash (skip re-embedding)
        existing = await conn.fetch(
            "SELECT file_name, doc_section, content_hash FROM doc_chunks"
        )
        existing_map = {(r["file_name"], r["doc_section"]): r["content_hash"] for r in existing}

        to_embed = [
            c for c in all_chunks
            if existing_map.get((c["file_name"], c["section"])) != c["content_hash"]
        ]
        skipped = len(all_chunks) - len(to_embed)

        if not to_embed:
            return {"indexed": 0, "skipped": skipped}

        # Embed in one batch
        vectors = embed([c["content"] for c in to_embed])

        # Upsert
        await conn.executemany(
            """
            INSERT INTO doc_chunks (file_name, doc_section, doc_type, content, content_hash, embedding)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (file_name, doc_section) DO UPDATE
              SET content = EXCLUDED.content,
                  content_hash = EXCLUDED.content_hash,
                  doc_type = EXCLUDED.doc_type,
                  embedding = EXCLUDED.embedding
            """,
            [
                (c["file_name"], c["section"], c["doc_type"],
                 c["content"], c["content_hash"], str(vectors[i]))
                for i, c in enumerate(to_embed)
            ],
        )
        return {"indexed": len(to_embed), "skipped": skipped}
    finally:
        await conn.close()


# ── Retrieval ──────────────────────────────────────────────────────────────────

async def retrieve(query: str, db_url: str, k: int = 12,
                   doc_type: Optional[str] = None) -> list[dict]:
    """
    Embed query and return top-k most similar chunks.

    Args:
        query:    The search query (policy text, service name, question, etc.)
        db_url:   SQLAlchemy async database URL
        k:        Number of chunks to return
        doc_type: Optional filter — "core" or "services"

    Returns list of {file_name, section, doc_type, content, similarity} dicts.
    """
    vec = embed([query])[0]
    vec_str = str(vec)

    conn = await _get_conn(db_url)
    try:
        if doc_type:
            rows = await conn.fetch(
                """
                SELECT file_name, doc_section, doc_type, content,
                       1 - (embedding <=> $1::vector) AS similarity
                FROM doc_chunks
                WHERE doc_type = $2
                ORDER BY embedding <=> $1::vector
                LIMIT $3
                """,
                vec_str, doc_type, k,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT file_name, doc_section, doc_type, content,
                       1 - (embedding <=> $1::vector) AS similarity
                FROM doc_chunks
                ORDER BY embedding <=> $1::vector
                LIMIT $2
                """,
                vec_str, k,
            )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def retrieve_for_policy(
    policy_json: str,
    services: list[str],
    db_url: str,
    k: int = 15,
) -> str:
    """
    Retrieve the most relevant doc chunks for an IAM policy translation.

    Runs two queries in parallel:
      1. Semantic search on the full policy text (finds conceptually relevant chunks)
      2. Service-name boosted query ("OCI <service> permissions policy")

    Returns formatted string ready to inject into a prompt.
    """
    import asyncio

    # Build a concise query from policy + detected services
    svc_list = ", ".join(services) if services else "general IAM"
    policy_query = f"AWS IAM policy translation to OCI for services: {svc_list}\n{policy_json[:800]}"
    svc_query = f"OCI permissions policy {svc_list} resource types verbs"

    results1, results2 = await asyncio.gather(
        retrieve(policy_query, db_url, k=k),
        retrieve(svc_query, db_url, k=k // 2),
    )

    # Merge, deduplicate by (file_name, section), keep highest similarity
    seen: dict[tuple, dict] = {}
    for chunk in results1 + results2:
        key = (chunk["file_name"], chunk["doc_section"])
        if key not in seen or chunk["similarity"] > seen[key]["similarity"]:
            seen[key] = chunk

    # Sort by similarity descending, take top k
    top = sorted(seen.values(), key=lambda c: c["similarity"], reverse=True)[:k]

    if not top:
        return "[no relevant docs found in RAG store]"

    parts = []
    for c in top:
        parts.append(
            f"=== {c['file_name']} › {c['doc_section']} "
            f"(similarity: {c['similarity']:.2f}) ===\n{c['content']}"
        )
    return "\n\n".join(parts)


# ── Sync wrappers for use in sync orchestrators ────────────────────────────────

def retrieve_for_policy_sync(
    policy_json: str,
    services: list[str],
    db_url: str,
    k: int = 15,
) -> str:
    """Synchronous wrapper around retrieve_for_policy for use in non-async code."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, retrieve_for_policy(policy_json, services, db_url, k))
                return future.result(timeout=30)
        else:
            return loop.run_until_complete(retrieve_for_policy(policy_json, services, db_url, k))
    except Exception as e:
        return f"[RAG retrieval error: {e}]"
