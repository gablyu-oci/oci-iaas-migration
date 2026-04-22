# Llama Stack Model Catalog — Availability Report

Endpoint: `https://llama-stack.ai-apps-ord.oci-incubations.com/v1/chat/completions`
Probed: 2026-04-21 21:26 UTC  ·  **95 models listed · 64 working · 31 unavailable**

Each row is a real POST to `/v1/chat/completions` with a 200-token
budget and the prompt `Reply with exactly the single word: ready`. The client
auto-retries with `max_completion_tokens` if the server rejects `max_tokens`.

- **OK** — returned a non-empty assistant message.
- **FAIL** — non-2xx response, empty response, or infrastructural error. The
  error column shows the server's message, classified where useful.

## Summary by provider

| Provider | Working | Unavailable | Total |
|---|---:|---:|---:|
| OpenAI | 42 | 16 | 58 |
| Google | 3 | 0 | 3 |
| xAI | 14 | 2 | 16 |
| Meta | 5 | 1 | 6 |
| Cohere | 0 | 12 | 12 |

---

## OpenAI — 42/58 working

| Model ID | Status | Token field | Latency | Notes / error |
|---|:---:|:---:|---:|---|
| `openai.gpt-4.1` | ✅ OK | `max_completion_tokens` | 1.9s | — |
| `openai.gpt-4.1-2025-04-14` | ✅ OK | `max_completion_tokens` | 0.9s | — |
| `openai.gpt-4.1-mini` | ✅ OK | `max_completion_tokens` | 1.0s | — |
| `openai.gpt-4.1-mini-2025-04-14` | ✅ OK | `max_completion_tokens` | 0.7s | — |
| `openai.gpt-4.1-nano` | ✅ OK | `max_completion_tokens` | 1.0s | — |
| `openai.gpt-4.1-nano-2025-04-14` | ✅ OK | `max_completion_tokens` | 0.6s | — |
| `openai.gpt-4o` | ✅ OK | `max_completion_tokens` | 1.6s | — |
| `openai.gpt-4o-2024-08-06` | ✅ OK | `max_completion_tokens` | 0.8s | — |
| `openai.gpt-4o-2024-11-20` | ✅ OK | `max_completion_tokens` | 0.9s | — |
| `openai.gpt-4o-mini` | ✅ OK | `max_completion_tokens` | 0.8s | — |
| `openai.gpt-4o-mini-2024-07-18` | ✅ OK | `max_completion_tokens` | 0.9s | — |
| `openai.gpt-4o-mini-search-preview` | ✅ OK | `max_completion_tokens` | 1.2s | — |
| `openai.gpt-4o-mini-search-preview-2025-03-11` | ✅ OK | `max_completion_tokens` | 1.9s | — |
| `openai.gpt-4o-search-preview` | ✅ OK | `max_completion_tokens` | 2.4s | — |
| `openai.gpt-4o-search-preview-2025-03-11` | ✅ OK | `max_completion_tokens` | 2.4s | — |
| `openai.gpt-5` | ✅ OK | `max_completion_tokens` | 2.0s | — |
| `openai.gpt-5-2025-08-07` | ✅ OK | `max_completion_tokens` | 2.5s | — |
| `openai.gpt-5-codex` | ❌ FAIL | — | 0.7s | responses API only |
| `openai.gpt-5-mini` | ✅ OK | `max_completion_tokens` | 1.8s | — |
| `openai.gpt-5-mini-2025-08-07` | ✅ OK | `max_completion_tokens` | 1.5s | — |
| `openai.gpt-5-nano` | ✅ OK | `max_completion_tokens` | 2.4s | — |
| `openai.gpt-5-nano-2025-08-07` | ✅ OK | `max_completion_tokens` | 1.9s | — |
| `openai.gpt-5.1` | ✅ OK | `max_completion_tokens` | 1.7s | — |
| `openai.gpt-5.1-2025-11-13` | ✅ OK | `max_completion_tokens` | 2.9s | — |
| `openai.gpt-5.1-chat-latest` | ✅ OK | `max_completion_tokens` | 1.6s | — |
| `openai.gpt-5.1-codex` | ❌ FAIL | — | 0.7s | not a chat model |
| `openai.gpt-5.1-codex-max` | ❌ FAIL | — | 0.7s | not a chat model |
| `openai.gpt-5.1-codex-mini` | ❌ FAIL | — | 0.5s | responses API only |
| `openai.gpt-5.2` | ✅ OK | `max_completion_tokens` | 1.2s | — |
| `openai.gpt-5.2-2025-12-11` | ✅ OK | `max_completion_tokens` | 1.0s | — |
| `openai.gpt-5.2-chat-latest` | ✅ OK | `max_completion_tokens` | 1.2s | — |
| `openai.gpt-5.2-codex` | ❌ FAIL | — | 0.8s | not a chat model |
| `openai.gpt-5.2-pro` | ❌ FAIL | — | 0.5s | not a chat model |
| `openai.gpt-5.2-pro-2025-12-11` | ❌ FAIL | — | 0.5s | not a chat model |
| `openai.gpt-5.3-codex` | ❌ FAIL | — | 1.6s | not a chat model |
| `openai.gpt-5.4` | ✅ OK | `max_completion_tokens` | 1.3s | — |
| `openai.gpt-5.4-2026-03-05` | ✅ OK | `max_completion_tokens` | 1.1s | — |
| `openai.gpt-5.4-mini` | ✅ OK | `max_completion_tokens` | 1.8s | — |
| `openai.gpt-5.4-mini-2026-03-17` | ✅ OK | `max_completion_tokens` | 2.0s | — |
| `openai.gpt-5.4-nano` | ✅ OK | `max_completion_tokens` | 1.5s | — |
| `openai.gpt-5.4-nano-2026-03-17` | ✅ OK | `max_completion_tokens` | 1.6s | — |
| `openai.gpt-5.4-pro` | ❌ FAIL | — | 0.6s | not a chat model |
| `openai.gpt-5.4-pro-2026-03-05` | ❌ FAIL | — | 1.0s | not a chat model |
| `openai.gpt-audio` | ❌ FAIL | — | 1.2s | audio-only model |
| `openai.gpt-image-1` | ❌ FAIL | — | 1.0s | image/non-chat model |
| `openai.gpt-image-1.5` | ❌ FAIL | — | 1.0s | image/non-chat model |
| `openai.gpt-oss-120b` | ✅ OK | `max_completion_tokens` | 0.8s | — |
| `openai.gpt-oss-20b` | ✅ OK | `max_completion_tokens` | 0.6s | — |
| `openai.o1` | ❌ FAIL | `max_completion_tokens` | 3.3s | reasoning-model, 200-token probe budget exhausted |
| `openai.o1-2024-12-17` | ✅ OK | `max_completion_tokens` | 2.3s | — |
| `openai.o3` | ✅ OK | `max_completion_tokens` | 1.6s | — |
| `openai.o3-2025-04-16` | ✅ OK | `max_completion_tokens` | 1.4s | — |
| `openai.o3-mini` | ✅ OK | `max_completion_tokens` | 2.7s | — |
| `openai.o3-mini-2025-01-31` | ✅ OK | `max_completion_tokens` | 3.0s | — |
| `openai.o4-mini` | ✅ OK | `max_completion_tokens` | 1.8s | — |
| `openai.o4-mini-2025-04-16` | ✅ OK | `max_completion_tokens` | 1.8s | — |
| `openai.text-embedding-3-large` | ❌ FAIL | — | 0.2s | embedding model (HTTP 500 on chat endpoint) |
| `openai.text-embedding-3-small` | ❌ FAIL | — | 0.8s | embedding model (HTTP 500 on chat endpoint) |

## Google — 3/3 working

| Model ID | Status | Token field | Latency | Notes / error |
|---|:---:|:---:|---:|---|
| `google.gemini-2.5-flash` | ✅ OK | `max_completion_tokens` | 1.1s | — |
| `google.gemini-2.5-flash-lite` | ✅ OK | `max_completion_tokens` | 15.9s | — |
| `google.gemini-2.5-pro` | ✅ OK | `max_completion_tokens` | 2.9s | — |

## xAI — 14/16 working

| Model ID | Status | Token field | Latency | Notes / error |
|---|:---:|:---:|---:|---|
| `xai.grok-3` | ✅ OK | `max_completion_tokens` | 0.7s | — |
| `xai.grok-3-fast` | ✅ OK | `max_completion_tokens` | 1.0s | — |
| `xai.grok-3-mini` | ✅ OK | `max_completion_tokens` | 3.4s | — |
| `xai.grok-3-mini-fast` | ✅ OK | `max_completion_tokens` | 3.7s | — |
| `xai.grok-4` | ✅ OK | `max_completion_tokens` | 4.0s | — |
| `xai.grok-4-1-fast-non-reasoning` | ✅ OK | `max_completion_tokens` | 0.7s | — |
| `xai.grok-4-1-fast-reasoning` | ✅ OK | `max_completion_tokens` | 2.1s | — |
| `xai.grok-4-fast-non-reasoning` | ✅ OK | `max_completion_tokens` | 1.5s | — |
| `xai.grok-4-fast-reasoning` | ✅ OK | `max_completion_tokens` | 1.2s | — |
| `xai.grok-4.20-0309-non-reasoning` | ✅ OK | `max_completion_tokens` | 0.7s | — |
| `xai.grok-4.20-0309-reasoning` | ✅ OK | `max_completion_tokens` | 2.3s | — |
| `xai.grok-4.20-multi-agent` | ❌ FAIL | — | 0.5s | multi-agent only |
| `xai.grok-4.20-multi-agent-0309` | ❌ FAIL | — | 0.9s | multi-agent only |
| `xai.grok-4.20-non-reasoning` | ✅ OK | `max_completion_tokens` | 1.3s | — |
| `xai.grok-4.20-reasoning` | ✅ OK | `max_completion_tokens` | 2.2s | — |
| `xai.grok-code-fast-1` | ✅ OK | `max_completion_tokens` | 2.3s | — |

## Meta — 5/6 working

| Model ID | Status | Token field | Latency | Notes / error |
|---|:---:|:---:|---:|---|
| `meta.llama-3.1-405b-instruct` | ✅ OK | `max_completion_tokens` | 0.5s | — |
| `meta.llama-3.2-11b-vision-instruct` | ❌ FAIL | — | 0.4s | not configured on this gateway |
| `meta.llama-3.2-90b-vision-instruct` | ✅ OK | `max_completion_tokens` | 1.0s | — |
| `meta.llama-3.3-70b-instruct` | ✅ OK | `max_completion_tokens` | 0.6s | — |
| `meta.llama-4-maverick-17b-128e-instruct-fp8` | ✅ OK | `max_completion_tokens` | 0.5s | — |
| `meta.llama-4-scout-17b-16e-instruct` | ✅ OK | `max_completion_tokens` | 0.5s | — |

## Cohere — 0/12 working

| Model ID | Status | Token field | Latency | Notes / error |
|---|:---:|:---:|---:|---|
| `cohere.command-a-03-2025` | ❌ FAIL | — | 0.6s | Cohere chat (not OpenAI-compatible on this gateway) |
| `cohere.command-a-vision` | ❌ FAIL | — | 0.9s | Cohere chat (not OpenAI-compatible on this gateway) |
| `cohere.command-latest` | ❌ FAIL | — | 0.5s | Cohere chat (not OpenAI-compatible on this gateway) |
| `cohere.command-plus-latest` | ❌ FAIL | — | 0.6s | Cohere chat (not OpenAI-compatible on this gateway) |
| `cohere.command-r-08-2024` | ❌ FAIL | — | 0.4s | Cohere chat (not OpenAI-compatible on this gateway) |
| `cohere.command-r-plus-08-2024` | ❌ FAIL | — | 0.4s | Cohere chat (not OpenAI-compatible on this gateway) |
| `cohere.embed-english-light-v3.0` | ❌ FAIL | — | 0.2s | embedding model (HTTP 500 on chat endpoint) |
| `cohere.embed-english-v3.0` | ❌ FAIL | — | 0.4s | embedding model (HTTP 500 on chat endpoint) |
| `cohere.embed-multilingual-image-v3.0` | ❌ FAIL | — | 0.2s | embedding model (HTTP 500 on chat endpoint) |
| `cohere.embed-multilingual-light-v3.0` | ❌ FAIL | — | 0.4s | embedding model (HTTP 500 on chat endpoint) |
| `cohere.embed-multilingual-v3.0` | ❌ FAIL | — | 0.4s | transient HTTP 502 at probe time |
| `cohere.embed-v4.0` | ❌ FAIL | — | 0.3s | embedding model (HTTP 500 on chat endpoint) |

---

## Failure categories

| Category | Count | Why | Could we reach it? |
|---|---:|---|---|
| not a chat model | 8 | Model responds on `/v1/completions` or `/v1/responses`, not `/v1/chat/completions`. | Yes — route through a different Llama Stack endpoint. |
| embedding model (HTTP 500 on chat endpoint) | 7 | Embedding/rerank models throw on chat; they're here because `/v1/models` lists everything. | Yes via `/v1/embeddings` — different surface. |
| Cohere chat (not OpenAI-compatible on this gateway) | 6 | Cohere's own Chat API is exposed elsewhere; the OpenAI-compatibility layer doesn't proxy these. | Yes — call via Cohere's native endpoint (separate client). |
| multi-agent only | 2 | Grok multi-agent variants reject plain chat calls. | Yes — requires xAI's multi-agent request envelope. |
| image/non-chat model | 2 | Image generation / editing model. | Yes via `/v1/images/*` — different surface. |
| responses API only | 2 | Gated to the newer `/v1/responses` endpoint (agentic runs). | Yes, but requires switching our client to the Responses API. |
| audio-only model | 1 | Requires audio input or audio output modality. | Yes — must send audio content. |
| reasoning-model, 200-token probe budget exhausted | 1 | Reasoning model consumed all tokens on hidden reasoning. Production calls use 8192+, so this is a probe-budget artifact, not a model bug. | Yes — fine with a realistic token budget. |
| not configured on this gateway | 1 | Listed in `/v1/models` but the upstream provider returns 404. | No — contact the Llama Stack operator. |
| transient HTTP 502 at probe time | 1 | Upstream returned 502 during this probe run — likely transient. | Probably yes on retry; re-probe to confirm. |

---

## How to re-probe

```bash
python3 scripts/probe_llm_models.py
```

Writes this file in place. Reads endpoint + key from `LLM_BASE_URL` and
`LLM_API_KEY`, same as the backend.
