---
file: PLANNING.md
project: Confidence — selfie to personalised skincare routine
hackathon: DevNetwork AI+ML Hackathon 2026
deadline: May 27–28, 2026
challenge: Perfect Corp — Building the Next Generation of AI-Driven Consumer Experiences ($2,500)
---

# Confidence — Project Plan

---

## Step 1 — Problem, Users, Constraints

**Problem:**
Buying skincare is guesswork. Shelves have hundreds of products, descriptions are vague,
and what works for one skin type fails on another. People either buy the wrong products
or pay for expensive consultations. Confidence turns a selfie into a personalised morning
and evening routine — specific products, grounded in real ingredient science, explained
in plain language.

**Users:**
- Consumer uploading a selfie — wants a clear, actionable skincare routine in under 60 seconds
- Hackathon judges — want to see: Perfect Corp API used meaningfully, RAG as the intelligence
  layer, a working demo with real output

**Hard constraints:**
- Must use at least 1 Perfect Corp API (required by challenge brief)
- Perfect Corp API is async: upload file → run task → poll until complete (not a direct response)
- API key at: https://yce.makeupar.com/api-console/en/api-keys/
- Must demonstrate "clear consumer or retail value" and "creative use of Perfect Corp APIs"
- Must include a demo video (1–3 minutes) showing the experience end-to-end
- Must participate in an exit interview if chosen as winner
- Deadline: May 27–28 2026
- No OpenAI — Voyage AI for embeddings (free tier), Transformers.js as fallback
- No GCP outside rkchellah.org policy restriction

---

## Step 2 — Proposal

### What it is

A web app. User uploads a selfie on a clean single-page interface.
The app calls Perfect Corp's skin analysis API, which returns scores for 14 skin concerns
(spots, wrinkles, texture, redness, oiliness, moisture, eye bags, acne, firmness,
radiance, dark circles, pores, droopy eyelids) plus skin type and an overall skin score.

Those scores are converted into a natural-language RAG query
("moisturiser for dry skin with dark spots and enlarged pores").
The query hits a vector database of 100+ indexed skincare products.
The top 3 most relevant products per concern are retrieved.

The Groq LLM receives the skin analysis + retrieved products and generates:
- A skin profile card (skin type, top 3 concerns, skin score)
- A morning routine (3–4 steps with specific products and why they match)
- An evening routine (3–4 steps with specific products and why they match)
- One ingredient to avoid based on detected sensitivities

Output rendered as a results page the user can screenshot and act on.

### Folder structure

```
confidence/
  backend/
    perfect_corp.py      — API client: upload → task → poll → parse
    rag_products.py      — embed query + retrieve top products from Supabase
    routine_generator.py — Claude prompt, few-shot examples, structured JSON output
    main.py              — FastAPI: POST /analyse, GET /health
  frontend/
    index.html           — selfie upload UI + results display (single HTML file)
  scripts/
    build_product_db.py  — one-time: embed and index product catalogue to Supabase
    sample_products.json — 100 skincare products as structured data
  PLANNING.md
  STACK.md
  VERTICAL.md
  .env.example
  .env.local             — never committed
  .gitignore
  README.md
  requirements.txt
```

### Tech stack

See STACK.md for full details and deviation rationale.

| Layer | Choice |
|---|---|
| Skin analysis | Perfect Corp skin-analysis API |
| Embeddings | Voyage AI `voyage-3-lite` (1024-dim) — fallback: Transformers.js |
| Embed abstraction | Single `embed()` function in `rag_products.py` — swap provider in one place |
| Vector DB | Supabase pgvector |
| LLM | Groq (`llama-3.3-70b-versatile`) |
| Backend | FastAPI on Render |
| Frontend | Single HTML file |

### Data model

```
Supabase — skincare_products table
  id          bigserial primary key
  name        text
  brand       text
  category    text       — moisturiser | serum | cleanser | SPF | treatment | eye cream | toner
  content     text       — full chunk used for embedding (see format below)
  metadata    jsonb      — {brand, category, skin_types[], concerns[], price_tier, ingredients[]}
  embedding   vector(1024)   ← Voyage AI voyage-3-lite output dimension

Index: ivfflat on embedding (vector_cosine_ops), lists=50
RPC: match_skincare_products(query_embedding vector(1024), match_count int)
  → returns id, name, content, metadata, similarity float
```

**Product chunk format for embedding:**
```
PRODUCT | {name} | brand: {brand} | category: {category} |
skin_types: {types} | concerns_addressed: {concerns} |
key_ingredients: {ingredients} | avoid_for: {avoid} |
price_tier: {budget|mid|premium}
```

### Auth model

```
No auth — public web app for the hackathon demo
All API keys: server-side only (FastAPI env vars, never in frontend HTML)
Images: sent to Perfect Corp API, not stored by Confidence
Skin results: not written to database — stays in the browser response only
```

### Feature list — v1 (hackathon submission only)

- [ ] Selfie upload — drag-and-drop or click, shows preview
- [ ] Optional "ingredients to avoid" field — filtered from RAG + injected into system prompt
- [ ] Loading state — animated steps (Analysing skin → Searching products → Generating routine)
- [ ] Skin profile card — skin type, top 3 concerns with scores, skin score /100
- [ ] Three-tier triage system — enforced in Python before Groq is called (see Safety Design)
        Mild (0–0.4): full recommendation
        Moderate (0.4–0.85): recommendation + soft nudge to see derm if it persists
        Severe (0.85+): referral card only — Groq not called for this concern
- [ ] Morning routine — 3–4 steps: product name, key ingredients, why it matches
- [ ] Evening routine — 3–4 steps: product name, key ingredients, why it matches
- [ ] Ingredient to avoid — one callout with plain-language reason
- [ ] Always-present disclaimer footer — not medical advice, visible on every result
- [ ] "See a professional" nudge on any concern card scoring above 0.6
- [ ] Graceful error states — every failure mode suggests a specialist where appropriate
- [ ] Results are printable / screenshottable

**Not in v1:**
- User accounts or saved routines
- Virtual try-on
- Product purchase links or affiliate integration
- Mobile app
- Routine conflict checker (deferred — the "products I already own" feature)

---

## Step 3 — Done Looks Like

**What the user sees:**

Upload screen:
```
[drag selfie here or click to upload]
[ingredients to avoid? (optional)]
[Analyse my skin →]
```

Loading steps (sequential, animated):
```
✓ Uploading photo
✓ Analysing skin concerns
✓ Searching product database
✓ Generating your routine
```

**Three possible result states depending on triage:**

State 1 — Mild concerns (all scores below 0.4):
```
Skin type: Dry · Skin score: 74/100
Top concerns: Dryness (0.31) · Pores (0.28) · Dark circles (0.22)

Morning routine → [full 4-step routine]
Evening routine → [full 4-step routine]
Ingredient to avoid: alcohol denat. — drying

─────────────────────────────────────────────────────
Confidence provides general skincare suggestions based on a
computer vision analysis. This is not medical advice.
For persistent skin concerns, consult a dermatologist.
─────────────────────────────────────────────────────
```

State 2 — Moderate concerns (any score 0.4–0.85):
```
Skin type: Combination · Skin score: 58/100
Top concerns: Acne (0.71) · Redness (0.63) · Oiliness (0.44)

⚠ Acne (0.71) — If this concern persists after 8 weeks of consistent
  use, consider speaking to a dermatologist.    [Find a specialist →]

Morning routine → [full routine with acne-suited products]
Evening routine → [full routine]
─────────────────────────────────────────────────────
Not medical advice. Consult a dermatologist for persistent concerns.
─────────────────────────────────────────────────────
```

State 3 — Severe concern (any score 0.85+):
```
Skin type: Oily · Skin score: 41/100

⛔ The analysis detected a high level of acne (0.91).
   At this severity, OTC products are unlikely to be sufficient.
   We recommend a consultation with a dermatologist before
   starting any new skincare routine.

   [Find a dermatologist near you →]

   We've included a general routine for your other concerns below,
   but please speak to a specialist about your acne first.

Morning routine → [routine for non-severe concerns only]
Evening routine → [routine for non-severe concerns only]
─────────────────────────────────────────────────────
Not medical advice. Consult a dermatologist for persistent concerns.
─────────────────────────────────────────────────────
```

**What POST /analyse returns:**

Normal response (no severe concerns):
```json
{
  "skin_profile": {
    "skin_type": "dry",
    "skin_score": 68,
    "concerns": [
      {"name": "dark_spots", "score": 0.62, "tier": "moderate"},
      {"name": "moisture", "score": 0.38, "tier": "mild"},
      {"name": "pores", "score": 0.29, "tier": "mild"}
    ]
  },
  "morning_routine": [
    {
      "step": 1,
      "role": "cleanser",
      "product": "CeraVe Hydrating Cleanser",
      "key_ingredients": ["ceramides", "hyaluronic acid"],
      "reason": "Gentle, non-stripping formula suited to dry skin"
    }
  ],
  "evening_routine": [],
  "avoid_ingredient": {
    "ingredient": "alcohol denat.",
    "reason": "Drying — worsens your moisture concern"
  },
  "referral_concerns": [],
  "moderate_nudge_concerns": ["dark_spots"]
}
```

Severe response (one or more concerns at 0.85+):
```json
{
  "skin_profile": {
    "skin_type": "oily",
    "skin_score": 41,
    "concerns": [
      {"name": "acne", "score": 0.91, "tier": "severe"},
      {"name": "redness", "score": 0.54, "tier": "moderate"}
    ]
  },
  "referral_concerns": [
    {
      "name": "acne",
      "score": 0.91,
      "message": "At this severity, OTC products are unlikely to be sufficient. We recommend a dermatologist consultation before starting any new routine."
    }
  ],
  "morning_routine": [],
  "evening_routine": [],
  "avoid_ingredient": null,
  "moderate_nudge_concerns": ["redness"]
}
```

**When something goes wrong:**

| Failure | HTTP | Message shown to user |
|---|---|---|
| Poll exceeds 30s | 408 | "We couldn't complete the analysis in time. Try again with a well-lit, front-facing photo. For persistent skin concerns, a dermatologist is always the most reliable option." |
| No face detected | 400 | "We couldn't read your skin clearly. Try a well-lit photo with your face centred. If you have skin concerns you'd like properly assessed, consider booking with a skin specialist." |
| Supabase unreachable | 200 | Silent degradation — triage check still runs, Claude generates routine without specific product matches |
| Groq error (after 1 retry) | 500 | "Something went wrong generating your routine. Try again. For anything persistent or urgent, a dermatologist is always the right call." |

---

## Step 4 — Implementation Order

```
[!] 0. Perfect Corp API key — BLOCKER. Get this first.
        https://yce.makeupar.com/api-console/en/api-keys/
        Confirm skin-analysis endpoint is on your tier
        Verify: curl the upload endpoint returns a file_id

[ ] 1. Project setup
        Create folder structure
        requirements.txt, .env.example, .gitignore, README.md
        Verify: FastAPI runs locally with GET /health returning 200

[ ] 2. backend/perfect_corp.py — WRITTEN, needs # VERIFY items confirmed
        upload_image(image_bytes) → file_id
        run_analysis(file_id) → task_id
        poll_until_complete(task_id, timeout=30) → raw result dict
        parse_result(raw) → SkinAnalysisResult
        Verify: upload real selfie, get back 14 concern scores

[ ] 3. Product knowledge base
        Write scripts/sample_products.json — 100 products across 8 categories
        Run scripts/build_product_db.py — embed with Voyage AI + index to Supabase
        Supabase table: skincare_products, vector(1024), ivfflat index
        Verify: retrieve("moisturiser dry skin dark spots") returns relevant products

[ ] 4. backend/rag_products.py
        embed(text) → vector — Voyage AI primary, Transformers.js fallback in same function
        build_query(skin_profile) → natural language string
        retrieve(query, k=3) → list of product dicts
        Verify: dry skin + dark spots → returns vitamin C serums + ceramide moisturisers

[ ] 5. backend/routine_generator.py
        Severity check in Python BEFORE Groq is called — not inside the prompt
          HIGH_SEVERITY_THRESHOLD = 0.85
          REFERRAL_CONCERNS = {"acne", "redness", "spots", "texture"}
          If any concern hits threshold → return referral card, skip Claude for that concern
        System prompt hard limits (no diagnoses, no prescription products,
          only reference ingredients from RAG context, no efficacy claims)
        Few-shot: 2 example routines in system prompt (dry skin, oily skin)
        Moderate nudge: concerns 0.4–0.85 get "see a derm if persists after 8 weeks"
        Input: skin_profile + retrieved_products + ingredients_to_avoid (optional)
        Output: structured JSON (full schema in Step 3)
        Verify: severe acne (0.91) → returns referral card, no routine
        Verify: moderate concern (0.71) → returns routine + nudge
        Verify: mild concern (0.28) → returns routine only

[ ] 6. backend/main.py
        POST /analyse — multipart image upload → full pipeline → return JSON
        GET /health
        Verify: curl POST /analyse with a selfie returns full routine JSON

[ ] 7. frontend/index.html
        Upload area, loading steps, results cards
        Responsive, clean, printable
        Verify: full flow in browser — upload → loading → results

[ ] 8. Deploy to Render
        Push to GitHub, connect Render free tier
        Set env vars from .env.example
        Verify: public URL returns routine for a real selfie

[ ] 9. Demo video (1–3 minutes)
        Upload → loading → skin profile → morning routine → evening routine
        Upload to YouTube or Vimeo

[ ] 10. Submission
        App link, demo video, short write-up
        Contact: valerie_torres@perfectcorp.com
        Deadline: May 27–28 2026
```

---

## Project Bootstrap Status

```
[!] Perfect Corp API key — get this FIRST
[x] Problem understood
[x] Vertical structure proposed and approved
[x] Data model defined
[x] Auth approach decided — no auth
[x] Safety design locked in — three-tier triage in Python, system prompt guardrails,
      no-diagnosis language, allergy field, always-present disclaimer
[x] Environment variables listed
[~] backend/perfect_corp.py — written, # VERIFY items pending API key
[x] .gitignore in place
[x] requirements.txt written
[x] .env.example written
[x] README.md written
[ ] Local dev running
[ ] Product knowledge base built
[ ] First feature verified end to end
```

---

## Safety Design — Three-Tier Triage

This is the most important architectural decision in the project.
Safety boundaries are enforced in Python code, not in the LLM prompt.
Prompts can be worked around. A threshold check in Python cannot.

---

### The triage rule

Every concern from Perfect Corp gets a tier assigned in Python
before Claude is called. The tier determines what the UI shows
and whether Claude is called at all for that concern.

| Tier | Score range | What happens |
|---|---|---|
| Mild | 0 – 0.4 | Full product recommendation. Groq generates steps normally. |
| Moderate | 0.4 – 0.85 | Recommendation + soft nudge: "If this persists after 8 weeks, see a dermatologist." |
| Severe | 0.85+ | Referral card only. Groq is not called for this concern. No OTC recommendation. |

---

### Referral concerns

Not every concern triggers the severe pathway — only the ones where
OTC products are genuinely insufficient at high severity:

```python
REFERRAL_CONCERNS = {"acne", "redness", "spots", "texture"}
HIGH_SEVERITY_THRESHOLD = 0.85
```

Concerns like `pores`, `dark_circles`, `oiliness` at 0.85+ still get
recommendations because the risk of harm from a cosmetic product is low.
The triage only fires on concerns where confident OTC advice could delay
real treatment.

---

### The severity check in code

This runs in `routine_generator.py` before any Groq call:

```python
def check_severity(concerns: list[dict]) -> list[str]:
    return [
        c["name"] for c in concerns
        if c["score"] >= HIGH_SEVERITY_THRESHOLD
        and c["name"] in REFERRAL_CONCERNS
    ]

severe = check_severity(skin_profile["concerns"])
if severe:
    return referral_response(severe)   # Groq never called

return call_groq(skin_profile, retrieved_products)
```

---

### System prompt hard limits

The Groq LLM receives these constraints on every call. They are not softened
or overrideable by user input:

```
HARD LIMITS — never violate these:
1. Never diagnose. Say "the analysis detected elevated redness"
   not "you have rosacea". You are not a doctor.
2. Never recommend prescription products (tretinoin, antibiotics,
   steroid creams, oral medications).
3. Only reference ingredients and benefits from the PRODUCT CONTEXT
   provided. Never invent ingredients or efficacy claims.
   Never say "clinically proven" unless it appears verbatim in the context.
4. Never suggest the analysis is medically accurate. It is a
   computer vision estimate — not a clinical assessment.
5. Scope is OTC products only: cleansers, serums, moisturisers,
   SPF, eye creams, toners. Nothing else.
```

---

### What Confidence never does

These are enforced in code, not just in the prompt:

- Diagnoses any skin condition by name
- Recommends prescription treatments
- Makes efficacy claims not in the product knowledge base
- Provides product advice for concerns scoring above 0.85 in REFERRAL_CONCERNS
- Claims the skin analysis is medically accurate

---

### Why this matters for the judges

If asked "what about medical accuracy?" in the exit interview, the answer is:

> Confidence has a three-tier triage system enforced in Python. Mild concerns
> get OTC recommendations. Moderate concerns get recommendations plus a prompt
> to see a specialist if it persists. Severe concerns in safety-sensitive
> categories get a dermatologist referral and no product recommendation at all.
> The boundary is in code — outside the LLM's control entirely.

That is a more responsible design than most consumer beauty apps on the market.

---

```
# Perfect Corp
PERFECTCORP_API_KEY=     # https://yce.makeupar.com/api-console/en/api-keys/

# Voyage AI (embeddings — primary)
VOYAGE_API_KEY=          # https://dash.voyageai.com

# Groq
GROQ_API_KEY=

# Supabase
SUPABASE_URL=
SUPABASE_KEY=            # service role key — never in frontend

# Config
POLL_TIMEOUT_SECONDS=30
```

---

## Critical: Perfect Corp API Pattern

The API is async. It does not return results immediately.
Every call follows this exact pattern — do not deviate:

```python
file_id = upload_image(image_bytes)        # Step 1: upload
task_id = run_analysis(file_id)            # Step 2: start task
raw     = poll_until_complete(task_id)     # Step 3: poll every 2s until done
result  = parse_result(raw)               # Step 4: parse into clean types
```

Polling too fast risks rate limiting. 2-second interval is the correct default.

---

## Embedding Abstraction — Critical Pattern

The embed function lives in `rag_products.py` and is the only place
the embedding provider is referenced. Swapping Voyage AI for Transformers.js
means changing one block in one file. Nothing else in the codebase changes.

```python
def embed(text: str) -> list[float]:
    # PRIMARY: Voyage AI (voyage-3-lite, 1024-dim)
    # FALLBACK: uncomment Transformers.js block below if Voyage AI unavailable
    ...
```

If switching to Transformers.js fallback:
- Model: all-MiniLM-L6-v2
- Output dimension: 384
- Update Supabase column: vector(1024) → vector(384)
- Update ivfflat index accordingly
