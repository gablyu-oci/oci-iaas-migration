"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.base import init_db
from app.api import auth, aws, skills, plans


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run DB migrations on startup."""
    await init_db()
    yield


app = FastAPI(title="OCI Migration Tool", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(aws.router)
app.include_router(skills.router)
app.include_router(plans.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
