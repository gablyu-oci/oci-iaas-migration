"""Runtime-configurable settings.

Two groups of settings are exposed to the UI, both persisted in the
``system_settings`` key/value table and pushed into ``app.config.settings``
at startup and on every PUT so the rest of the app sees changes without
a restart:

1. **Credentials** — LLM endpoint base URL and (optional) API key.
2. **Models** — writer and reviewer model IDs.

``AVAILABLE_MODELS`` is the authoritative list of models verified to work
against the configured endpoint. Re-probe it if the upstream catalog changes.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant
from app.config import settings
from app.db.base import get_db
from app.db.models import SystemSetting, Tenant

router = APIRouter(prefix="/api/settings", tags=["settings"])


# Verified live against the Oracle internal Llama Stack gateway
# (https://llama-stack.ai-apps-ord.oci-incubations.com/v1) on 2026-04-21.
# 63 of the catalog's 95 models responded OK to a substantive probe.
# Reasoning models require max_completion_tokens — the client detects that
# by model-name prefix (see app.gateway.llm_client._is_reasoning_model).
AVAILABLE_MODELS: list[dict] = [
    # OpenAI GPT-5.4 family (reasoning)
    {"id": "oci/openai.gpt-5.4",                "family": "openai",  "label": "GPT-5.4",                 "reasoning": True},
    {"id": "oci/openai.gpt-5.4-mini",           "family": "openai",  "label": "GPT-5.4 mini",            "reasoning": True},
    {"id": "oci/openai.gpt-5.4-nano",           "family": "openai",  "label": "GPT-5.4 nano",            "reasoning": True},
    {"id": "oci/openai.gpt-5.4-2026-03-05",     "family": "openai",  "label": "GPT-5.4 (2026-03-05)",    "reasoning": True},
    {"id": "oci/openai.gpt-5.4-mini-2026-03-17","family": "openai",  "label": "GPT-5.4 mini (2026-03-17)","reasoning": True},
    {"id": "oci/openai.gpt-5.4-nano-2026-03-17","family": "openai",  "label": "GPT-5.4 nano (2026-03-17)","reasoning": True},
    # OpenAI GPT-5.2 / 5.1
    {"id": "oci/openai.gpt-5.2",                "family": "openai",  "label": "GPT-5.2",                 "reasoning": True},
    {"id": "oci/openai.gpt-5.2-chat-latest",    "family": "openai",  "label": "GPT-5.2 chat-latest"},
    {"id": "oci/openai.gpt-5.2-2025-12-11",     "family": "openai",  "label": "GPT-5.2 (2025-12-11)",    "reasoning": True},
    {"id": "oci/openai.gpt-5.1",                "family": "openai",  "label": "GPT-5.1",                 "reasoning": True},
    {"id": "oci/openai.gpt-5.1-chat-latest",    "family": "openai",  "label": "GPT-5.1 chat-latest"},
    {"id": "oci/openai.gpt-5.1-2025-11-13",     "family": "openai",  "label": "GPT-5.1 (2025-11-13)",    "reasoning": True},
    # OpenAI GPT-5 (original family)
    {"id": "oci/openai.gpt-5",                  "family": "openai",  "label": "GPT-5",                   "reasoning": True},
    {"id": "oci/openai.gpt-5-mini",             "family": "openai",  "label": "GPT-5 mini",              "reasoning": True},
    {"id": "oci/openai.gpt-5-nano",             "family": "openai",  "label": "GPT-5 nano",              "reasoning": True},
    {"id": "oci/openai.gpt-5-2025-08-07",       "family": "openai",  "label": "GPT-5 (2025-08-07)",      "reasoning": True},
    {"id": "oci/openai.gpt-5-mini-2025-08-07",  "family": "openai",  "label": "GPT-5 mini (2025-08-07)", "reasoning": True},
    {"id": "oci/openai.gpt-5-nano-2025-08-07",  "family": "openai",  "label": "GPT-5 nano (2025-08-07)", "reasoning": True},
    # OpenAI o-series (reasoning)
    {"id": "oci/openai.o1",                     "family": "openai",  "label": "o1",                      "reasoning": True},
    {"id": "oci/openai.o1-2024-12-17",          "family": "openai",  "label": "o1 (2024-12-17)",         "reasoning": True},
    {"id": "oci/openai.o3",                     "family": "openai",  "label": "o3",                      "reasoning": True},
    {"id": "oci/openai.o3-2025-04-16",          "family": "openai",  "label": "o3 (2025-04-16)",         "reasoning": True},
    {"id": "oci/openai.o3-mini-2025-01-31",     "family": "openai",  "label": "o3-mini (2025-01-31)",    "reasoning": True},
    {"id": "oci/openai.o4-mini",                "family": "openai",  "label": "o4-mini",                 "reasoning": True},
    {"id": "oci/openai.o4-mini-2025-04-16",     "family": "openai",  "label": "o4-mini (2025-04-16)",    "reasoning": True},
    # OpenAI GPT-4.1 / 4o (chat)
    {"id": "oci/openai.gpt-4.1",                "family": "openai",  "label": "GPT-4.1"},
    {"id": "oci/openai.gpt-4.1-mini",           "family": "openai",  "label": "GPT-4.1 mini"},
    {"id": "oci/openai.gpt-4.1-nano",           "family": "openai",  "label": "GPT-4.1 nano"},
    {"id": "oci/openai.gpt-4.1-2025-04-14",     "family": "openai",  "label": "GPT-4.1 (2025-04-14)"},
    {"id": "oci/openai.gpt-4.1-mini-2025-04-14","family": "openai",  "label": "GPT-4.1 mini (2025-04-14)"},
    {"id": "oci/openai.gpt-4.1-nano-2025-04-14","family": "openai",  "label": "GPT-4.1 nano (2025-04-14)"},
    {"id": "oci/openai.gpt-4o",                 "family": "openai",  "label": "GPT-4o"},
    {"id": "oci/openai.gpt-4o-mini",            "family": "openai",  "label": "GPT-4o mini"},
    {"id": "oci/openai.gpt-4o-2024-08-06",      "family": "openai",  "label": "GPT-4o (2024-08-06)"},
    {"id": "oci/openai.gpt-4o-2024-11-20",      "family": "openai",  "label": "GPT-4o (2024-11-20)"},
    {"id": "oci/openai.gpt-4o-mini-2024-07-18", "family": "openai",  "label": "GPT-4o mini (2024-07-18)"},
    {"id": "oci/openai.gpt-4o-search-preview",  "family": "openai",  "label": "GPT-4o search-preview"},
    {"id": "oci/openai.gpt-4o-mini-search-preview","family": "openai","label": "GPT-4o mini search-preview"},
    # OpenAI open-weight
    {"id": "oci/openai.gpt-oss-120b",           "family": "openai",  "label": "GPT-OSS 120B"},
    {"id": "oci/openai.gpt-oss-20b",            "family": "openai",  "label": "GPT-OSS 20B"},
    # Google Gemini 2.5
    {"id": "oci/google.gemini-2.5-pro",         "family": "google",  "label": "Gemini 2.5 Pro"},
    {"id": "oci/google.gemini-2.5-flash",       "family": "google",  "label": "Gemini 2.5 Flash"},
    {"id": "oci/google.gemini-2.5-flash-lite",  "family": "google",  "label": "Gemini 2.5 Flash Lite"},
    # xAI Grok 4.20
    {"id": "oci/xai.grok-4.20-reasoning",       "family": "xai",     "label": "Grok 4.20 (reasoning)",   "reasoning": True},
    {"id": "oci/xai.grok-4.20-non-reasoning",   "family": "xai",     "label": "Grok 4.20 (non-reasoning)"},
    {"id": "oci/xai.grok-4.20-0309-reasoning",  "family": "xai",     "label": "Grok 4.20 0309 (reasoning)","reasoning": True},
    {"id": "oci/xai.grok-4.20-0309-non-reasoning","family": "xai",   "label": "Grok 4.20 0309 (non-reasoning)"},
    # xAI Grok 4
    {"id": "oci/xai.grok-4",                    "family": "xai",     "label": "Grok 4"},
    {"id": "oci/xai.grok-4-fast-reasoning",     "family": "xai",     "label": "Grok 4 fast (reasoning)", "reasoning": True},
    {"id": "oci/xai.grok-4-fast-non-reasoning", "family": "xai",     "label": "Grok 4 fast (non-reasoning)"},
    {"id": "oci/xai.grok-4-1-fast-reasoning",   "family": "xai",     "label": "Grok 4.1 fast (reasoning)","reasoning": True},
    {"id": "oci/xai.grok-4-1-fast-non-reasoning","family": "xai",    "label": "Grok 4.1 fast (non-reasoning)"},
    # xAI Grok 3
    {"id": "oci/xai.grok-3",                    "family": "xai",     "label": "Grok 3"},
    {"id": "oci/xai.grok-3-fast",               "family": "xai",     "label": "Grok 3 fast"},
    {"id": "oci/xai.grok-3-mini",               "family": "xai",     "label": "Grok 3 mini"},
    {"id": "oci/xai.grok-3-mini-fast",          "family": "xai",     "label": "Grok 3 mini fast"},
    # xAI Grok Code
    {"id": "oci/xai.grok-code-fast-1",          "family": "xai",     "label": "Grok Code Fast 1"},
    # Meta Llama
    {"id": "oci/meta.llama-3.1-405b-instruct",  "family": "meta",    "label": "Llama 3.1 405B"},
    {"id": "oci/meta.llama-3.3-70b-instruct",   "family": "meta",    "label": "Llama 3.3 70B"},
    {"id": "oci/meta.llama-4-scout-17b-16e-instruct",   "family": "meta", "label": "Llama 4 Scout 17B×16E"},
    {"id": "oci/meta.llama-4-maverick-17b-128e-instruct-fp8","family": "meta","label": "Llama 4 Maverick 17B×128E (fp8)"},
]
_AVAILABLE_IDS = {m["id"] for m in AVAILABLE_MODELS}

# Keys persisted in the system_settings table. Mirrored onto ``settings`` in
# memory at startup and after each PUT. Legacy OCI_GENAI_* keys are ignored
# if still present in the table (safe; just stale rows).
_PERSISTED_KEYS = (
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_WRITER_MODEL",
    "LLM_REVIEWER_MODEL",
)


def _mask_api_key(key: str) -> str:
    """Return a UI-safe rendering of an API key.

    We only ever hand the last 4 characters back to the frontend so the
    plaintext secret never leaves the backend after it's been saved.
    """
    if not key:
        return ""
    if len(key) <= 8:
        return "••••"
    return f"{key[:3]}••••{key[-4:]}"


def _utcnow_sentinel() -> datetime:
    return datetime.utcnow()


async def _persist(db: AsyncSession, key: str, value: str) -> None:
    stmt = pg_insert(SystemSetting).values(key=key, value=value)
    stmt = stmt.on_conflict_do_update(
        index_elements=["key"],
        set_={"value": value, "updated_at": _utcnow_sentinel()},
    )
    await db.execute(stmt)


async def _load_persisted_overrides(db: AsyncSession) -> None:
    """Copy persisted settings (if any) onto the in-memory ``settings`` object.

    Called on startup (from ``app.main.lifespan``) and on each settings GET
    so the UI always reflects reality.
    """
    rows = (await db.execute(select(SystemSetting))).scalars().all()
    by_key = {r.key: r.value for r in rows}
    for k in _PERSISTED_KEYS:
        if k in by_key and by_key[k]:
            setattr(settings, k, by_key[k])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class ModelSettings(BaseModel):
    writer_model: str
    reviewer_model: str


class ModelSettingsResponse(ModelSettings):
    available: list[dict]


@router.get("/models", response_model=ModelSettingsResponse)
async def get_model_settings(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    await _load_persisted_overrides(db)
    return ModelSettingsResponse(
        writer_model=settings.LLM_WRITER_MODEL,
        reviewer_model=settings.LLM_REVIEWER_MODEL,
        available=AVAILABLE_MODELS,
    )


@router.put("/models", response_model=ModelSettingsResponse)
async def update_model_settings(
    body: ModelSettings,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    for name, val in (("writer_model", body.writer_model),
                      ("reviewer_model", body.reviewer_model)):
        if val not in _AVAILABLE_IDS:
            raise HTTPException(
                status_code=400,
                detail=f"{name} {val!r} is not in the list of available models",
            )

    await _persist(db, "LLM_WRITER_MODEL", body.writer_model)
    await _persist(db, "LLM_REVIEWER_MODEL", body.reviewer_model)
    await db.commit()

    settings.LLM_WRITER_MODEL = body.writer_model
    settings.LLM_REVIEWER_MODEL = body.reviewer_model

    return ModelSettingsResponse(
        writer_model=settings.LLM_WRITER_MODEL,
        reviewer_model=settings.LLM_REVIEWER_MODEL,
        available=AVAILABLE_MODELS,
    )


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------
class CredentialsResponse(BaseModel):
    """What the frontend sees.

    ``api_key_masked`` is a cosmetic fingerprint — the full value never leaves
    the backend once saved. ``api_key_set`` tells the UI whether to render a
    "Replace key" affordance vs an empty input. ``api_key_required`` is true
    when the configured endpoint rejects anonymous calls; when false, an
    empty key is fine (e.g., the internal Llama Stack gateway).
    """
    base_url: str
    api_key_masked: str
    api_key_set: bool


class CredentialsUpdate(BaseModel):
    # api_key is optional — leave blank to keep the existing one.
    api_key: str | None = None
    base_url: str


class CredentialsTestRequest(BaseModel):
    """Partial-override body for the test endpoint.

    All fields are optional — any missing/blank field falls back to the
    currently saved credentials. Lets the UI probe either the live config
    (post with empty body) or a candidate edit (post with the dirty form
    values) without juggling two endpoints.
    """
    api_key: str | None = None
    base_url: str | None = None


class TestResult(BaseModel):
    ok: bool
    error: str | None = None
    model_tested: str | None = None
    latency_ms: int | None = None


@router.get("/credentials", response_model=CredentialsResponse)
async def get_credentials(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    await _load_persisted_overrides(db)
    return CredentialsResponse(
        base_url=settings.LLM_BASE_URL,
        api_key_masked=_mask_api_key(settings.LLM_API_KEY),
        api_key_set=bool(settings.LLM_API_KEY),
    )


@router.put("/credentials", response_model=CredentialsResponse)
async def update_credentials(
    body: CredentialsUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Update LLM endpoint + API key. Only replaces the API key if
    ``api_key`` is a non-empty string — leave blank to keep existing. The
    API key is optional altogether (anonymous endpoints are supported)."""
    if not body.base_url.strip():
        raise HTTPException(status_code=400, detail="base_url is required")

    await _persist(db, "LLM_BASE_URL", body.base_url.strip())
    settings.LLM_BASE_URL = body.base_url.strip()

    if body.api_key is not None:
        new_key = body.api_key.strip()
        # Allow explicit clearing by passing an empty string.
        await _persist(db, "LLM_API_KEY", new_key)
        settings.LLM_API_KEY = new_key

    await db.commit()

    return CredentialsResponse(
        base_url=settings.LLM_BASE_URL,
        api_key_masked=_mask_api_key(settings.LLM_API_KEY),
        api_key_set=bool(settings.LLM_API_KEY),
    )


@router.post("/credentials/test", response_model=TestResult)
async def test_credentials(
    body: CredentialsTestRequest | None = None,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Make a tiny chat completion against the candidate credentials.

    Any field present in ``body`` overrides the currently saved value;
    anything omitted (or blank) falls back to what's configured. Nothing
    is persisted — ``/credentials`` PUT is the only write path.
    """
    await _load_persisted_overrides(db)

    api_key = (body.api_key.strip() if body and body.api_key else "") or settings.LLM_API_KEY
    base_url = (body.base_url.strip() if body and body.base_url else "") or settings.LLM_BASE_URL
    model = settings.LLM_REVIEWER_MODEL or settings.LLM_WRITER_MODEL

    if not base_url:
        return TestResult(ok=False, error="No base_url configured.")

    import time
    from openai import OpenAI
    from app.gateway.llm_client import _is_reasoning_model
    try:
        probe = OpenAI(api_key=api_key or "anonymous", base_url=base_url)
        t0 = time.perf_counter()
        params = {"model": model, "messages": [{"role": "user", "content": "ping"}]}
        # Reasoning models reject max_tokens
        params["max_completion_tokens" if _is_reasoning_model(model) else "max_tokens"] = 200
        resp = probe.chat.completions.create(**params)
        dur_ms = int((time.perf_counter() - t0) * 1000)
        txt = (resp.choices[0].message.content or "").strip()
        if not txt and resp.choices[0].finish_reason != "stop":
            return TestResult(
                ok=False,
                error=f"Empty response (finish_reason={resp.choices[0].finish_reason})",
                model_tested=model,
                latency_ms=dur_ms,
            )
        return TestResult(ok=True, model_tested=model, latency_ms=dur_ms)
    except Exception as exc:  # noqa: BLE001 — surface to UI
        return TestResult(ok=False, error=str(exc)[:500])
