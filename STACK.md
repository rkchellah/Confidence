---
file: STACK.md
project: Confidence
read when: suggesting a library, using a framework API, installing a package, any version-specific question
---

# Stack Rules — Confidence

---

## This Project's Stack

This project deviates from the default STACK.md in three places.
Every deviation is documented below with a reason.

| Layer | Choice | Reason |
|-------|--------|--------|
| Language | Python 3.11+ | Backend is ML/API pipeline — Python is the right tool |
| Backend | FastAPI on Google Cloud Run | Hackathon timeline — no framework overhead, container-based free deploy |
| Frontend | Single HTML file | No component tree needed — one page, fast to build, easy to demo |
| Skin analysis | Perfect Corp skin-analysis API | Required by challenge brief |
| Embeddings | Voyage AI `voyage-3-lite` (1024-dim) | Free for new users, Anthropic-recommended for RAG. Fallback: Transformers.js |
| Vector DB | Supabase pgvector | Free tier, same infra pattern already established |
| LLM | DeepSeek (`deepseek-chat`) | Strong structured JSON output, OpenAI-compatible API |
| Deployment | Google Cloud Run | Container-based, scale-to-zero, simple Docker deploy for FastAPI |

---

## Deviations From Default STACK.md

### 1. FastAPI + HTML instead of Next.js + Vercel
**Reason:** Hackathon deadline is May 27–28. A single-page app with one POST endpoint
does not need a full React framework. FastAPI serves the API. One HTML file handles
the UI. Build time saved goes into product quality.

### 2. Voyage AI instead of OpenAI for embeddings
**Reason:** No budget for OpenAI API. GCP credits are policy-restricted to rkchellah.org.
Voyage AI has a free tier for new users and is Anthropic's recommended embedding partner for RAG.
Fallback is Transformers.js (zero cost, zero API key, runs in Python) — swap one function if needed.

### 3. No TypeScript — Python throughout
**Reason:** The entire stack is Python. FastAPI has full type hint support via Pydantic.
All type safety enforced through Python type hints and dataclasses.

---

## Official Documentation Sources

| Technology | Official Docs |
|-----------|---------------|
| FastAPI | https://fastapi.tiangolo.com |
| Python | https://docs.python.org/3 |
| Supabase Python SDK | https://supabase.com/docs/reference/python |
| Voyage AI | https://docs.voyageai.com |
| OpenAI Python SDK (DeepSeek) | https://api-docs.deepseek.com |
| Perfect Corp API | https://yce.perfectcorp.com/document/index.html |
| httpx | https://www.python-httpx.org |
| Google Cloud Run | https://cloud.google.com/run/docs |

When in doubt about any method, behavior, or version — verify at the official source before using it.

---

## No Hallucination Rule

This is absolute. Never invent:
- Package names that may not exist
- Method signatures not verified against docs
- API behaviors not confirmed
- SDK versions without checking

If uncertain, say so and give the verification link.

---

## Dependency Rules

Every dependency is a liability. Before adding a package:

1. Can this be done with a Python built-in?
2. Is this package actively maintained?
3. Is it the official or most widely trusted solution?

**Packages confirmed for this project:**

```
fastapi          — web framework
uvicorn          — ASGI server for FastAPI
httpx            — async HTTP client (Perfect Corp API calls)
supabase         — Supabase Python SDK
python-dotenv    — load .env.local
pydantic         — request/response validation (comes with FastAPI)
openai           — OpenAI SDK (DeepSeek API, OpenAI-compatible)
voyageai         — Voyage AI embeddings (verify package name at https://docs.voyageai.com)
```

**Transformers.js fallback (Python equivalent):**
```
sentence-transformers   — if Voyage AI is unavailable; model: all-MiniLM-L6-v2 (384-dim)
                          Note: if switching to this, update vector column to vector(384)
```

---

## Environment Variables

All secrets live in `.env.local`. Never in code. Never committed.

| Variable | Description |
|----------|-------------|
| `PERFECTCORP_API_KEY` | Perfect Corp API key — get from https://yce.makeupar.com/api-console/en/api-keys/ |
| `VOYAGE_API_KEY` | Voyage AI — get from https://dash.voyageai.com |
| `DEEPSEEK_API_KEY` | DeepSeek API key |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase service role key — never exposed to frontend |
| `POLL_TIMEOUT_SECONDS` | Perfect Corp poll timeout — default 30 |

`.env.local` is always in `.gitignore`. Always.
`.env.example` lists every variable name with a description but no real values. Committed to repo.
