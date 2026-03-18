"""RAG management endpoints — index docs and search the vector store."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_tenant
from app.config import settings
from app.db.models import Tenant

router = APIRouter()

DOCS_ROOT = Path(__file__).parent.parent.parent / "docs"


class IndexResult(BaseModel):
    indexed: int
    skipped: int
    error: str | None = None


class SearchRequest(BaseModel):
    query: str
    k: int = 10
    doc_type: str | None = None  # "core", "services", or None for all


class SearchResult(BaseModel):
    file_name: str
    section: str
    doc_type: str
    content: str
    similarity: float


@router.post("/rag/index", response_model=IndexResult)
async def index_docs_endpoint(tenant: Tenant = Depends(get_current_tenant)):
    """
    Re-index all .md files in docs/core/ and docs/services/ into the vector store.
    Only chunks whose content changed are re-embedded (content-hash dedup).
    Run this after dropping new .md files into those directories.
    """
    try:
        from app.skills.shared.rag import index_docs
        result = await index_docs(DOCS_ROOT, settings.DATABASE_URL)
        return IndexResult(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rag/search", response_model=list[SearchResult])
async def search_docs(
    req: SearchRequest,
    tenant: Tenant = Depends(get_current_tenant),
):
    """Search the RAG vector store with a free-text query."""
    try:
        from app.skills.shared.rag import retrieve
        chunks = await retrieve(req.query, settings.DATABASE_URL, k=req.k, doc_type=req.doc_type)
        return [SearchResult(**c) for c in chunks]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rag/stats")
async def rag_stats(tenant: Tenant = Depends(get_current_tenant)):
    """Return chunk counts per file and doc_type."""
    import asyncpg
    url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    try:
        conn = await asyncpg.connect(url)
        rows = await conn.fetch("""
            SELECT doc_type, file_name, COUNT(*) as chunks
            FROM doc_chunks
            GROUP BY doc_type, file_name
            ORDER BY doc_type, file_name
        """)
        await conn.close()
        total = sum(r["chunks"] for r in rows)
        return {
            "total_chunks": total,
            "by_file": [dict(r) for r in rows],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
