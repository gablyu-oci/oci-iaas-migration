#!/usr/bin/env python3
"""Seed service_mappings and iam_mappings tables from JSON files."""

import asyncio
import json
import sys
from pathlib import Path

# Ensure the backend package is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from sqlalchemy import text
from app.db.base import engine, async_session
from app.db.models import ServiceMapping, IAMMapping, Base


async def seed():
    # Create tables if they do not exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    data_dir = Path(__file__).parent.parent / "backend" / "data" / "seeds"

    async with async_session() as db:
        # Seed service mappings
        with open(data_dir / "service_mappings.json") as f:
            mappings = json.load(f)
        for m in mappings:
            db.add(ServiceMapping(**m))

        # Seed IAM mappings
        with open(data_dir / "iam_mappings.json") as f:
            mappings = json.load(f)
        for m in mappings:
            db.add(IAMMapping(**m))

        await db.commit()

    print("Seeded service_mappings and iam_mappings tables.")


if __name__ == "__main__":
    asyncio.run(seed())
