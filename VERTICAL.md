---
name: vertical-codebase
description: Structural rules for every new project. Propose verticals, get approval, then write code.
project: Confidence
note: This project uses a backend/frontend/scripts layout justified by the hackathon
      timeline and single-page architecture. The domain-first naming principles still apply
      within each folder — no junk drawers, no files stranded from the domain they serve.
---

# Vertical Codebase Rules

Every project starts with structure, not code.
Group code by what it does, not what it technically is.

---

## How This Applies to Confidence

Confidence uses a backend/frontend/scripts split rather than a full vertical tree.
This is an approved deviation for the hackathon — one HTML page and a four-file
Python backend do not need a src/ tree with domain folders.

The vertical principles still apply inside the backend:

```
backend/
  perfect_corp.py      → everything to do with Perfect Corp API
  rag_products.py      → everything to do with retrieval and embeddings
  routine_generator.py → everything to do with Groq and routine output
  main.py              → FastAPI wiring only — thin, no business logic here
```

`main.py` is thin. It connects the parts. Business logic lives in the domain files.
If logic starts accumulating in main.py, it belongs in one of the other three files.

---

## The Core Rule

**Group by what code does, not what it technically is.**

```
✅ perfect_corp.py     — the Perfect Corp domain
✅ rag_products.py     — the retrieval domain
✅ routine_generator.py— the routine generation domain

❌ api_client.py       — describes what it technically is
❌ utils.py            — a junk drawer waiting to happen
❌ helpers.py          — means nothing
```

---

## What Goes in main.py

`main.py` is allowed to contain:
- FastAPI app initialisation
- Route definitions (thin — delegate immediately to domain files)
- Request/response models (Pydantic)
- Error handler registration

`main.py` is not allowed to contain:
- HTTP calls to Perfect Corp
- Embedding or retrieval logic
- Prompt assembly or Claude calls
- Any business logic at all

---

## Files Live With Their Domain

Every helper, type, and constant belongs to the domain file it serves.

```
✅ SkinAnalysisResult dataclass lives in perfect_corp.py
✅ embed() function lives in rag_products.py
✅ RoutineOutput type lives in routine_generator.py

❌ types.py at top level — stranded from the domain it serves
❌ utils.py holding embed() — no domain owner
```

---

## Naming Rules

Name things after what they do in the product, not after technical patterns.

```
✅ perfect_corp.py        — the domain
✅ routine_generator.py   — what it produces
✅ rag_products.py        — what it retrieves

❌ api_wrapper.py         — technical description
❌ llm_caller.py          — technical description
❌ vector_search.py       — technical description
```

---

## The Mental Model

A good file structure communicates what the app does before you open a single file.

If someone reads the backend/ folder and understands it's about:
- talking to Perfect Corp for skin analysis
- retrieving products from a vector database
- generating routines with Groq

You've done it right.

If they see utils.py, helpers.py, and api_client.py — they understand nothing
about the product. They just know you know what a function is.

---

## Full Confidence Structure (approved)

```
confidence/
  backend/
    perfect_corp.py      — Perfect Corp API: upload, task, poll, parse
    rag_products.py      — Voyage AI embed + Supabase pgvector retrieve
    routine_generator.py — Groq prompt, few-shot, structured JSON output
    main.py              — FastAPI routes only, delegates to above
  frontend/
    index.html           — entire frontend: upload, loading, results
  scripts/
    build_product_db.py  — one-time: seed Supabase with embedded products
    sample_products.json — 100 skincare products structured data
  PLANNING.md
  STACK.md
  VERTICAL.md
  .env.example
  .env.local
  .gitignore
  README.md
  requirements.txt
```
