# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## What This Project Is

Confidence - selfie to personalised skincare routine in under 60 seconds.
Hackathon project for DevNetwork AI+ML Hackathon 2026 (Perfect Corp Challenge, $2,500).
Deadline: May 27–28 2026.

---

## Commands

**Install dependencies (Python 3.11+):**
```bash
python -m venv venv
venv\Scripts\activate       # Windows
pip install -r requirements.txt
```

**Run the backend:**
```bash
uvicorn backend.main:app --reload
```
Backend starts at `http://localhost:8000`. Check `GET /health` first.

**Seed the product knowledge base (one-time):**
```bash
python scripts/build_product_db.py
```
Embeds 100 products from `scripts/sample_products.json` and indexes them to Supabase.
Re-running is safe but will duplicate rows - only run once per Supabase project.

**Open the frontend:**
Open `frontend/index.html` directly in a browser. No build step - single HTML file.

**Hit the API manually:**
```bash
curl -X POST http://localhost:8000/analyse \
  -F "image=@your_selfie.jpg" \
  -F "ingredients_to_avoid=alcohol denat., fragrance"
```

---

## Architecture

### The Pipeline

Every request through `POST /analyse` runs four steps in sequence:

```
image bytes
  → perfect_corp.py     upload → task → poll → parse → SkinAnalysisResult
  → rag_products.py     embed query → cosine search → RetrievedProduct[]
  → routine_generator.py triage → (maybe) DeepSeek prompt → RoutineOutput
  → main.py             serialise → JSON response
```

`main.py` is wiring only. No business logic lives there. If logic accumulates in `main.py`, it belongs in one of the three domain files.

### Backend Domain Files

| File | Owns |
|---|---|
| `backend/perfect_corp.py` | Perfect Corp API: upload → task → poll → parse. Defines `SkinAnalysisResult`, all custom exceptions (`AnalysisTimeoutError`, `NoFaceDetectedError`, `PerfectCorpError`). |
| `backend/rag_products.py` | Voyage AI embedding (`embed()`), query building (`build_query()`), Supabase pgvector retrieval (`retrieve_for_skin()`). Defines `RetrievedProduct`. |
| `backend/routine_generator.py` | Three-tier triage check in Python (before DeepSeek is called), DeepSeek prompt assembly, structured JSON output. Defines `RoutineOutput`. |
| `backend/main.py` | FastAPI routes, CORS, startup env-var validation, `_serialise()`. |

### Perfect Corp API - Async Pattern

The API is not synchronous. Every call follows this exact sequence:

```python
file_id = upload_image(image_bytes)
task_id = run_analysis(file_id)
raw     = poll_until_complete(task_id, timeout=30)  # polls every 2s
result  = parse_result(raw)                          # → SkinAnalysisResult
```

Do not deviate from this. Polling too fast risks rate limiting; 2s is the correct interval.

### Three-Tier Triage - The Most Important Architectural Decision

Safety enforcement is in Python code, not in the LLM prompt. This runs in `routine_generator.py` before any DeepSeek call:

| Tier | Score | What happens |
|---|---|---|
| Mild | 0–0.4 | Full product recommendation |
| Moderate | 0.4–0.85 | Recommendation + soft nudge to see a derm if it persists |
| Severe | 0.85+ | Referral card **and** a supportive morning/evening routine. DeepSeek is **not called**. |

Severe triage only fires for `REFERRAL_CONCERNS = {"acne", "redness", "spots", "age_spot", "texture"}`. Cosmetic concerns like pores and dark circles at high severity still get a normal DeepSeek routine.

**Decision change (2026-09-05):** The first version of severe triage was referral-only — empty `morning_routine` / `evening_routine`, no OTC steps. That left the results page blank after a high redness/acne/spot/texture score. The decision now is to put the routine cards back. DeepSeek is still skipped. `referral_response()` attaches a cleanser / moisturiser / SPF baseline from RAG (`_supportive_routine()`). Those steps are daily care only — they must not treat the severe finding. Until Cloud Run is redeployed, `frontend/index.html` `fallbackRoutine()` fills the same catalogue steps when the API still returns empty arrays.

### Embedding Abstraction

`embed()` in `rag_products.py` is the only place the embedding provider is referenced. Primary: Voyage AI `voyage-3-lite` (1024-dim). Fallback: `sentence-transformers` `all-MiniLM-L6-v2` (384-dim - requires updating the Supabase `vector(1024)` column and rebuilding the index).

### Supabase Schema

```
skincare_products
  id          bigserial primary key
  name        text
  brand       text
  category    text
  content     text         - embedding chunk
  metadata    jsonb        - {brand, category, skin_types[], concerns[], price_tier, ingredients[]}
  embedding   vector(1024)

RPC: match_skincare_products(query_embedding vector(1024), match_count int)
     → id, name, content, metadata, similarity float
```

### Graceful Degradation

If Supabase is unreachable, `retrieve()` returns `[]` and logs the error. The pipeline continues - DeepSeek generates a routine without specific product matches. This is intentional and documented.

### Error Handling Contract

`main.py` surfaces all failures with two keys: `message` (internal log) and `user_message` (shown to user). User-facing messages always suggest seeing a specialist where clinically appropriate.

---

## Environment Variables

All secrets in `.env.local` (never committed). Copy from `.env.example`.

| Variable | Purpose |
|---|---|
| `PERFECTCORP_API_KEY` | Perfect Corp skin analysis |
| `VOYAGE_API_KEY` | Voyage AI embeddings |
| `DEEPSEEK_API_KEY` | DeepSeek LLM (`deepseek-chat`) |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase service role key (never in frontend) |
| `POLL_TIMEOUT_SECONDS` | Perfect Corp poll timeout - default 30 |

These must be set on **Cloud Run** (`sightline-2026` / `confidence-api`). `.env.local` is dockerignored and is not uploaded by `gcloud run deploy --source .`. Missing any of the five keys at startup raises in `main.py` `lifespan` and Cloud Run reports a false “not listening on 8080”.

Full host map, pause/resume, failed revision `00004`, and key add on `00006-2d9`: see `DEPLOY.md`.

**Live as of 2026-09-05:** revision `confidence-api-00007-p94` on `sightline-2026` has the key and the supportive-routine Python. Severe results still show `A gentle cleanser` when RAG returns no matching row — check Supabase rows / Cloud Run retrieve logs. Do not deploy to `confidence-497418`.

---

## Engineering Standards

### Non-Negotiables

- **Never run git commands.** Tell Chella what to commit and why. He runs the commands.
- **Never write to or read `.env` files.**
- **No Python `Any` without justification.** Use type hints and dataclasses throughout (Pydantic for API models).
- **Never guess about an API, method, or version.** If uncertain, say so and give the official docs URL.
- **Never scaffold without a proposal first.** Propose structure, wait for approval, then build.
- **One step at a time.** Verify each step works before moving to the next.

### Code Structure

`main.py` is thin - it connects parts. Domain files own their logic. No new `utils.py`, `helpers.py`, or `api_client.py` files. Any new functionality belongs to an existing domain file or a new domain-named file proposed first.

### Git - Chella Commits

When a task is complete, state: what changed, which files were modified, the suggested commit message. Never suggest running the commit.

```
feat(backend): …
fix(rag): …
refactor(perfect-corp): …
```

### Official Docs

| Technology | URL |
|---|---|
| FastAPI | https://fastapi.tiangolo.com |
| Python | https://docs.python.org/3 |
| Supabase Python SDK | https://supabase.com/docs/reference/python |
| Voyage AI | https://docs.voyageai.com |
| OpenAI Python SDK (DeepSeek) | https://api-docs.deepseek.com |
| Perfect Corp API | https://yce.perfectcorp.com/document/index.html |
| httpx | https://www.python-httpx.org |
| Google Cloud Run | https://cloud.google.com/run/docs |

### If a Request Breaks a Rule

Flag it before doing anything. Name the rule, explain the conflict, ask Chella to confirm. Don't silently adapt and comply.
