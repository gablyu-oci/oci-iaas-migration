"""
CLI script to index all docs into the RAG vector store.

Usage:
    cd /home/ubuntu/oci-migration-tool/backend
    python3 -m app.skills.shared.index_docs

Run this whenever you add or update .md files in docs/core/ or docs/services/.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.config import settings
from app.skills.shared.rag import index_docs

DOCS_ROOT = Path(__file__).parent.parent.parent.parent / "docs"


async def main():
    print(f"Indexing docs from: {DOCS_ROOT}")
    print(f"Database: {settings.DATABASE_URL.split('@')[-1]}")
    result = await index_docs(DOCS_ROOT, settings.DATABASE_URL)
    print(f"Done: {result['indexed']} chunks indexed, {result['skipped']} unchanged")
    if result.get("error"):
        print(f"Error: {result['error']}")


if __name__ == "__main__":
    asyncio.run(main())
