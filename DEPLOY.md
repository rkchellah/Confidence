# Confidence — what changed, why, and how it is hosted

Record of 2026-09-05. Written so the next deploy does not repeat the same mix-up.

---

## Purpose we kept

Confidence turns a selfie into a morning and evening routine in under a minute.

- See the skin (Perfect Corp). Not a diagnosis.
- Find real products (Supabase pgvector). Not invented names.
- Write steps a person can follow (wash, cream, SPF).
- Stop the LLM when a score says OTC is not enough.

That purpose did not change. The work below was to keep the result page honest when a high score fired, and to get the live API and database talking again.

---

## Three hosts (do not collapse these)

| Piece | Host | Project / URL | Job |
|---|---|---|---|
| Product catalogue | **Supabase** | `cogujrijzatooedxghre.supabase.co` | `skincare_products` + `match_skincare_products` |
| API | **Cloud Run** | GCP project **`sightline-2026`** (number `59597652459`), service **`confidence-api`** | FastAPI: analyse → retrieve → triage → routine |
| Website | **Vercel** | `https://confidence-two.vercel.app` | Static `frontend/index.html` |

GCP project **`confidence-497418`** (number `769278956638`, org `rkchellah-org`) is a **different** Google project. Its Cloud Run list is empty. Do not deploy there.

Unpausing Supabase does not update the API. Deploying Cloud Run does not replace Supabase.

---

## Product decision — routine cards back (2026-09-05)

**First rule:** severe score (≥ 0.85 on acne, redness, spots, age_spot, texture) → referral card only. Empty `morning_routine` / `evening_routine`. DeepSeek not called.

**Why that existed:** safety in Python, not in the prompt. OTC actives must not treat a finding that belongs with a clinician.

**What went wrong in the product:** the results page looked broken. Skin type and markers showed. Morning and Evening said nothing was returned.

**Decision:** keep DeepSeek off. Put the routine cards back as daily care only (cleanser, moisturiser, SPF). Do not treat the severe finding.

| Layer | Change | Why |
|---|---|---|
| `backend/routine_generator.py` | `_supportive_routine()` picks cleanser / moisturiser / SPF from RAG products. `referral_response()` attaches them. | API can return steps without calling DeepSeek. |
| DeepSeek prompt | `reason` fields are how-tos (“Wash your face.”) | Cards were reading like generated marketing copy. |
| `frontend/index.html` | `fallbackRoutine()` fills the same catalogue trio if both arrays are empty. `everydayReason()` always shows how-to copy. | Live Cloud Run still returned `[]` until a new **source** revision. Page must not go blank. |

Documented in `CLAUDE.md`, `CLAUDE_PROJECT.md`, `README.md`, `PLANNING.md`.

---

## Ops sequence — 2026-09-05

### 1. Supabase paused

Free-tier project slept. `retrieve()` returned `[]` (designed degradation). Analyse still ran. Mild/moderate routines lost grounded product names. Severe path had no RAG list to pick from.

### 2. Resume blocked

Dashboard: `chella.supamoto@gmail.com` already had **2 active free projects**. A paused project cannot resume until one active project is paused, deleted, or upgraded.

**What we did:** pause a *different* unused free project (not Confidence). Pause means off for up to 1 year; then backup download only. After that, Confidence restored.

**Why not Neon:** Confidence talks to Supabase (`SUPABASE_URL`, `SUPABASE_KEY`, RPC). Neon Auth is unused (no login). Neon would have been a full migrate.

### 3. Results after restore still showed the same three products

Cetaphil Gentle Skin Cleanser, La Roche-Posay Toleriane Double Repair, CeraVe Hydrating Mineral SPF 30.

**Why:** that trio is hardcoded in `fallbackRoutine()` when redness ≥ 0.85. Cloud Run was still the **old image**: severe → empty arrays. The page filled the cards. Scores (80/100, referrals) were live Perfect Corp. The routine was not live RAG.

### 4. First Cloud Run source deploy failed

```text
gcloud run deploy confidence-api --source . --region us-central1 --allow-unauthenticated
```

Build succeeded. Revision `confidence-api-00004-qwq` died. Cloud Run said the container did not listen on `PORT=8080`.

**That message was misleading.** Uvicorn did bind to 8080. Then `main.py` `lifespan` required five env vars and raised:

`RuntimeError: Missing environment variables: DEEPSEEK_API_KEY`

The process exited. The probe then reported “not listening.”

`.env.local` is in `.dockerignore` on purpose. `--source .` ships code, not laptop secrets. The other four keys were already on the service. DeepSeek was not.

The **environment tag** warning on `gcloud config set project` is unrelated.

Traffic stayed on the previous healthy revision. `/health` → `{"status":"ok"}` the whole time. `/` → `{"detail":"Not Found"}` is normal (no root route).

### 5. Adding the key on PowerShell

`--update-env-vars DEEPSEEK_API_KEY=...` broke in PowerShell. gcloud treats `,` and `=` in the value as list syntax.

**What worked:** a local flags file (deleted after), not reading `.env` in chat:

```powershell
# reads .env.local on the laptop only, then:
gcloud run services update confidence-api --region=us-central1 --flags-file=deepseek-flags.yaml
```

**Result (done):** revision **`confidence-api-00006-2d9`** serving 100% at  
`https://confidence-api-59597652459.us-central1.run.app`

**What this revision is:** the **previous working image** plus `DEEPSEEK_API_KEY`.  
`gcloud run services update` does **not** upload `routine_generator.py`. It only changes service config and rolls a new revision of the last good container.

---

## What is live right now vs what is still local

| Item | Live API (`00007-p94`) | Notes |
|---|---|---|
| `DEEPSEEK_API_KEY` on Cloud Run | Yes (added on `00006-2d9`) | Startup check passes |
| Supportive routine Python | **Yes** — source deploy `00007-p94` | DeepSeek still skipped on severe |
| Named catalogue products on severe | **Not yet** | Cards say `A gentle cleanser` when RAG returns nothing |
| Frontend fallback | Only if both arrays are empty | API now sends steps, so fallback does not run |
| Supabase catalogue | Restored | If Table Editor has rows, do not re-seed |

`00007-p94` is the current serving revision (2026-09-05, `--source .` after the key was set).

Frontend is separate. Push `index.html` to Vercel for copy/fallback. That does not update Cloud Run.

---

## How to deploy next time (short)

1. Confirm project **`sightline-2026`**, service **`confidence-api`**, region **`us-central1`**.
2. Keys already on the service: `PERFECTCORP_API_KEY`, `VOYAGE_API_KEY`, `DEEPSEEK_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`. Do not `--set-env-vars` or `--clear-env-vars` (that wipes them).
3. `gcloud run deploy confidence-api --source . --region us-central1 --allow-unauthenticated`
4. `/health` → `{"status":"ok"}`
5. One real analyse. Inspect the JSON, not only the cards.

Console (key only, no terminal): service → **Edit & deploy new revision** → **Variables & secrets** → add one variable → Deploy.

---

## Files touched for the product change

| File | What | Why |
|---|---|---|
| `backend/routine_generator.py` | Supportive routine + everyday `reason` examples in the prompt | Severe no longer returns empty lists; DeepSeek still skipped |
| `frontend/index.html` | `fallbackRoutine()`, `everydayReason()` | Cover old API; how-to copy |
| `CLAUDE.md`, `CLAUDE_PROJECT.md`, `README.md`, `PLANNING.md` | Decision written down | Agents and judges do not treat empty routines as the current rule |
| `DEPLOY.md` | This file | Ops path: hosts, pause, failed revision, key, remaining source deploy |
