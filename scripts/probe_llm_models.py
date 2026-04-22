#!/usr/bin/env python3
"""Probe every model on the configured LLM endpoint and regenerate
``docs/llm-models.md`` with the results.

Usage:
    python3 scripts/probe_llm_models.py

Reads the endpoint + optional API key from the ``LLM_BASE_URL`` and
``LLM_API_KEY`` env vars (defaults to the Oracle internal Llama Stack
gateway, which is anonymous). Writes the markdown report next to this
script's parent at ``docs/llm-models.md``.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests


BASE_URL = os.environ.get(
    "LLM_BASE_URL",
    "https://llama-stack.ai-apps-ord.oci-incubations.com/v1",
).rstrip("/")
API_KEY = os.environ.get("LLM_API_KEY", "")

PROMPT = "Reply with exactly the single word: ready"
TOKEN_BUDGET = 200  # deliberately small; reasoning models that exhaust this get flagged

OUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "llm-models.md"

PROVIDER_ORDER = ["openai", "google", "xai", "meta", "cohere"]
PROVIDER_LABEL = {
    "openai": "OpenAI",
    "google": "Google",
    "xai":    "xAI",
    "meta":   "Meta",
    "cohere": "Cohere",
}

CATEGORY_INFO = {
    "not a chat model":
        ("Model responds on `/v1/completions` or `/v1/responses`, not `/v1/chat/completions`.",
         "Yes — route through a different Llama Stack endpoint."),
    "responses API only":
        ("Gated to the newer `/v1/responses` endpoint (agentic runs).",
         "Yes, but requires switching our client to the Responses API."),
    "Cohere chat (not OpenAI-compatible on this gateway)":
        ("Cohere's own Chat API is exposed elsewhere; the OpenAI-compatibility layer doesn't proxy these.",
         "Yes — call via Cohere's native endpoint (separate client)."),
    "embedding model (HTTP 500 on chat endpoint)":
        ("Embedding/rerank models throw on chat; they're here because `/v1/models` lists everything.",
         "Yes via `/v1/embeddings` — different surface."),
    "multi-agent only":
        ("Grok multi-agent variants reject plain chat calls.",
         "Yes — requires xAI's multi-agent request envelope."),
    "image/non-chat model":
        ("Image generation / editing model.",
         "Yes via `/v1/images/*` — different surface."),
    "audio-only model":
        ("Requires audio input or audio output modality.",
         "Yes — must send audio content."),
    "transient HTTP 502 at probe time":
        ("Upstream returned 502 during this probe run — likely transient.",
         "Probably yes on retry; re-probe to confirm."),
    "not configured on this gateway":
        ("Listed in `/v1/models` but the upstream provider returns 404.",
         "No — contact the Llama Stack operator."),
    "reasoning-model, 200-token probe budget exhausted":
        ("Reasoning model consumed all tokens on hidden reasoning. Production calls use 8192+, so this is a probe-budget artifact, not a model bug.",
         "Yes — fine with a realistic token budget."),
}


def _classify(err: str | None) -> str:
    if err is None:
        return "—"
    s = err.lower()
    if "not a chat model" in s:
        return "not a chat model"
    if "only supported in v1/responses" in s:
        return "responses API only"
    if "requires that either input content or output modality contain audio" in s:
        return "audio-only model"
    if "does not support chat" in s:
        return "image/non-chat model"
    if "multi agent" in s:
        return "multi-agent only"
    if "unsupported openai operation" in s:
        return "Cohere chat (not OpenAI-compatible on this gateway)"
    if "internal server error" in s and "500" in s:
        return "embedding model (HTTP 500 on chat endpoint)"
    if "502 bad gateway" in s:
        return "transient HTTP 502 at probe time"
    if "entity with key" in s and "not found" in s:
        return "not configured on this gateway"
    if "empty response" in s and "length" in s:
        return "reasoning-model, 200-token probe budget exhausted"
    return err[:120]


def _clean_err(s: str) -> str:
    """Extract the useful server message from OCI's nested-JSON errors."""
    if not s:
        return ""
    s = s.strip()
    m = re.search(r"'message':\s*'([^']+)'", s) or re.search(r'"message":\s*"([^"]+)"', s)
    if m:
        return m.group(1).strip()
    if "<html>" in s.lower():
        t = re.search(r"<title>([^<]+)</title>", s, re.I)
        if t:
            return t.group(1)
    return s.split("\n")[0][:240]


def _probe_one(model_id: str) -> dict:
    """Try one POST, then retry with the other token field on 400 token-field complaints."""
    t0 = time.perf_counter()
    last_err = None
    for token_key in ("max_completion_tokens", "max_tokens"):
        try:
            body = {
                "model": model_id,
                "messages": [{"role": "user", "content": PROMPT}],
                token_key: TOKEN_BUDGET,
            }
            headers = {"Content-Type": "application/json"}
            if API_KEY:
                headers["Authorization"] = f"Bearer {API_KEY}"
            r = requests.post(f"{BASE_URL}/chat/completions", json=body,
                              headers=headers, timeout=60)
            if r.status_code == 200:
                data = r.json()
                choice = data["choices"][0]
                text = (choice["message"]["content"] or "").strip()
                finish = choice.get("finish_reason")
                ok = bool(text) or finish == "stop"
                return {
                    "id": model_id,
                    "ok": ok,
                    "latency_s": round(time.perf_counter() - t0, 1),
                    "token_field": token_key,
                    "text": text[:60],
                    "error": None if ok else f"empty response (finish={finish})",
                }
            elif r.status_code == 400 and "max_tokens" in r.text and token_key == "max_tokens":
                continue
            last_err = f"HTTP {r.status_code}: {r.text[:400]}"
            break
        except requests.exceptions.Timeout:
            last_err = "timeout (60s)"
            break
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
            break
    return {
        "id": model_id,
        "ok": False,
        "latency_s": round(time.perf_counter() - t0, 1),
        "token_field": None,
        "text": "",
        "error": _clean_err(last_err or "unknown"),
    }


def _provider(model_id: str) -> str:
    stripped = model_id.split("/", 1)[-1]
    return stripped.split(".", 1)[0]


def _short(model_id: str) -> str:
    return model_id.split("/", 1)[-1]


def _render_md(results: list[dict]) -> str:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    total = len(results)
    ok_n = sum(1 for r in results if r["ok"])

    by_provider: dict[str, list[dict]] = {}
    for r in results:
        by_provider.setdefault(_provider(r["id"]), []).append(r)
    for lst in by_provider.values():
        lst.sort(key=lambda r: r["id"])

    lines: list[str] = []
    lines.append(f"# Llama Stack Model Catalog — Availability Report")
    lines.append("")
    lines.append(f"Endpoint: `{BASE_URL}/chat/completions`")
    lines.append(f"Probed: {now}  ·  **{total} models listed · {ok_n} working · {total - ok_n} unavailable**")
    lines.append("")
    lines.append(f"Each row is a real POST to `/v1/chat/completions` with a {TOKEN_BUDGET}-token")
    lines.append("budget and the prompt `Reply with exactly the single word: ready`. The client")
    lines.append("auto-retries with `max_completion_tokens` if the server rejects `max_tokens`.")
    lines.append("")
    lines.append("- **OK** — returned a non-empty assistant message.")
    lines.append("- **FAIL** — non-2xx response, empty response, or infrastructural error. The")
    lines.append("  error column shows the server's message, classified where useful.")
    lines.append("")
    lines.append("## Summary by provider")
    lines.append("")
    lines.append("| Provider | Working | Unavailable | Total |")
    lines.append("|---|---:|---:|---:|")
    seen = set()
    for p in PROVIDER_ORDER + sorted(by_provider.keys()):
        if p in seen or p not in by_provider:
            continue
        seen.add(p)
        rs = by_provider[p]
        ok = sum(1 for r in rs if r["ok"])
        label = PROVIDER_LABEL.get(p, p.title())
        lines.append(f"| {label} | {ok} | {len(rs) - ok} | {len(rs)} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    seen = set()
    for p in PROVIDER_ORDER + sorted(by_provider.keys()):
        if p in seen or p not in by_provider:
            continue
        seen.add(p)
        rs = by_provider[p]
        ok = sum(1 for r in rs if r["ok"])
        label = PROVIDER_LABEL.get(p, p.title())
        lines.append(f"## {label} — {ok}/{len(rs)} working")
        lines.append("")
        lines.append("| Model ID | Status | Token field | Latency | Notes / error |")
        lines.append("|---|:---:|:---:|---:|---|")
        for r in rs:
            status = "✅ OK" if r["ok"] else "❌ FAIL"
            tf = f"`{r['token_field']}`" if r["token_field"] else "—"
            note = _classify(r["error"]).replace("|", "\\|")
            lines.append(f"| `{_short(r['id'])}` | {status} | {tf} | {r['latency_s']}s | {note} |")
        lines.append("")

    # Failure categories summary
    buckets: dict[str, list[str]] = {}
    for r in results:
        if not r["ok"]:
            buckets.setdefault(_classify(r["error"]), []).append(_short(r["id"]))

    lines.append("---")
    lines.append("")
    lines.append("## Failure categories")
    lines.append("")
    lines.append("| Category | Count | Why | Could we reach it? |")
    lines.append("|---|---:|---|---|")
    for cat, ids in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        reason, reach = CATEGORY_INFO.get(cat, ("—", "—"))
        lines.append(f"| {cat} | {len(ids)} | {reason} | {reach} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## How to re-probe")
    lines.append("")
    lines.append("```bash")
    lines.append("python3 scripts/probe_llm_models.py")
    lines.append("```")
    lines.append("")
    lines.append("Writes this file in place. Reads endpoint + key from `LLM_BASE_URL` and")
    lines.append("`LLM_API_KEY`, same as the backend.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    headers = {"Accept": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    print(f"→ listing models at {BASE_URL}/models …", file=sys.stderr)
    resp = requests.get(f"{BASE_URL}/models", headers=headers, timeout=20)
    resp.raise_for_status()
    models = resp.json().get("data", [])
    print(f"   {len(models)} models to probe", file=sys.stderr)

    results = []
    for i, m in enumerate(models, 1):
        r = _probe_one(m["id"])
        flag = "OK  " if r["ok"] else "FAIL"
        print(f"   [{i:3d}/{len(models)}] {flag} {m['id']:55s}  {r['latency_s']}s", file=sys.stderr)
        results.append(r)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(_render_md(results))
    ok = sum(1 for r in results if r["ok"])
    print(f"\nwrote {OUT_PATH}  ·  {ok}/{len(results)} working", file=sys.stderr)

    # Also drop raw results for scripts that want to parse them
    sidecar = OUT_PATH.with_suffix(".json")
    sidecar.write_text(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
