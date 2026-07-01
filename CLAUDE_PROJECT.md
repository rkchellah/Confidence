# Confidence — Claude Code Context

Read the global CLAUDE.md first.
This file adds the project-specific context on top of those global rules.

---

## What This Project Is

Confidence is a single-page web app that turns a selfie into a personalised
skincare routine. It calls Perfect Corp's skin analysis API to detect 14 skin
concerns, runs RAG over a vector database of 100+ skincare products, and uses
a DeepSeek LLM to generate a structured morning and evening routine. Built for the
DevNetwork AI+ML Hackathon 2026 — Perfect Corp challenge ($2,500).

---

## Tech Stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.11+ |
| Backend | FastAPI on Render |
| Frontend | Single HTML file |
| Skin analysis | Perfect Corp skin-analysis API (async: upload → task → poll) |
| Embeddings | Voyage AI `voyage-3-lite` (1024-dim) — fallback: sentence-transformers |
| Vector DB | Supabase pgvector |
| LLM | DeepSeek (`deepseek-chat`) |
| Deployment | Render free tier |

---

## Project Structure

```
confidence/
  backend/
    perfect_corp.py      ← Perfect Corp API domain (upload, task, poll, parse)
    rag_products.py      ← retrieval domain (embed, build_query, retrieve)
    routine_generator.py ← routine domain (triage, DeepSeek prompt, JSON output)
    main.py              ← FastAPI wiring only — no business logic here
  frontend/
    index.html           ← entire frontend: upload, loading, results
  scripts/
    build_product_db.py  ← one-time seed script — embed + index to Supabase
    sample_products.json ← 100 skincare products structured data
  PLANNING.md
  STACK.md
  VERTICAL.md
  CLAUDE_PROJECT.md      ← this file
  CLAUDE.md
  CLAUDE_CODE_HANDOFF.md
  .env.example
  .env.local             ← never touch
  .gitignore
  README.md
  requirements.txt
```

**Vertical rule:** `main.py` is wiring only. All business logic lives in its
domain file. If logic accumulates in `main.py`, it belongs somewhere else.

---

## Data Model

```
Supabase — skincare_products table
  id          bigserial primary key
  name        text
  brand       text
  category    text        — moisturiser | serum | cleanser | SPF | treatment | eye cream | toner
  content     text        — embedding chunk (see PLANNING.md for format)
  metadata    jsonb       — {brand, category, skin_types[], concerns[], price_tier, ingredients[]}
  embedding   vector(1024) — Voyage AI voyage-3-lite

Index: ivfflat on embedding (vector_cosine_ops), lists=50
RPC: match_skincare_products(query_embedding vector(1024), match_count int)
  → returns id, name, content, metadata, similarity float

No user data stored. Skin results stay in the browser response only.
```

---

## Auth Model

```
No authentication. Public web app — no login, no sessions, no RLS needed.
All API keys are server-side only (FastAPI env vars).
Images are sent to Perfect Corp and not stored by Confidence.
```

---

## Safety Design (read before touching routine_generator.py)

Three-tier triage enforced in Python BEFORE DeepSeek is called:

```
Mild    (0 – 0.4):    full product recommendation
Moderate (0.4 – 0.85): recommendation + soft nudge to see a dermatologist
Severe  (0.85+):      referral card only — DeepSeek LLM never called for this concern
```

```python
REFERRAL_CONCERNS = {"acne", "redness", "spots", "texture"}
HIGH_SEVERITY_THRESHOLD = 0.85
```

The LLM system prompt hard limits:
- Never diagnose — say "the analysis detected" not "you have"
- Never recommend prescription products
- Only reference ingredients from RAG product context
- Never claim the analysis is medically accurate

Do not weaken these constraints. They are intentional product decisions.

---

## Environment Variables

```
PERFECTCORP_API_KEY=     # https://yce.makeupar.com/api-console/en/api-keys/
VOYAGE_API_KEY=          # https://dash.voyageai.com
DEEPSEEK_API_KEY=        # https://platform.deepseek.com
SUPABASE_URL=
SUPABASE_KEY=            # service role key — never in frontend
POLL_TIMEOUT_SECONDS=30
```

---

## Do Not Touch

```
.env.local              ← never read or write
supabase/migrations/    ← if they exist, never auto-generate or delete
```

---

## Current State

```
[!] Perfect Corp API key — BLOCKER, everything waits on this
[x] PLANNING.md, STACK.md, VERTICAL.md written
[x] requirements.txt, .env.example, .gitignore, README.md written
[x] Safety design locked in — three-tier triage documented in PLANNING.md
[~] backend/perfect_corp.py — written, # VERIFY items need confirming against API docs
[ ] backend/rag_products.py
[ ] backend/routine_generator.py
[ ] backend/main.py
[ ] frontend/index.html
[ ] scripts/build_product_db.py + sample_products.json
[ ] Supabase table + ivfflat index created
[ ] Deployed to Render
[ ] Demo video recorded
[ ] Hackathon submitted
```

---

## How Tasks Come In

Tasks arrive from the Claude Projects chat as a filled-in handoff block
(see CLAUDE_CODE_HANDOFF.md for the template).

The handoff tells me what was decided in chat, which files are relevant,
and what the specific task is.

If no handoff is provided and the task is ambiguous — ask before touching anything.