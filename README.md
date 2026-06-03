# Confidence

Selfie to personalised skincare routine — in under 60 seconds.

Built for the DevNetwork AI+ML Hackathon 2026 — Perfect Corp Challenge ($2,500).

---

## What it does

Upload a selfie. Confidence analyses your skin using Perfect Corp's AI skin analysis API,
retrieves the most relevant products from a vetted knowledge base, and asks deepseek-chat to write
a personalised morning and evening routine — with specific products, key ingredients, and
plain-language reasons why each one matches your skin.

**Important:** Confidence provides skincare suggestions, not medical advice.
If you have persistent or unusual skin concerns, see a qualified dermatologist.

---

## How it works

```
Selfie → Perfect Corp skin analysis → 14 concern scores + skin type
       → RAG query → Supabase pgvector → top matched products
       → deepseek-chat → personalised morning + evening routine
```

Three phases, one result.

---

## Stack

| Layer | Choice |
|---|---|
| Backend | FastAPI (Python) |
| Skin analysis | Perfect Corp skin-analysis API |
| Embeddings | Voyage AI `voyage-3-lite` (1024-dim) |
| Vector DB | Supabase pgvector |
| LLM | deepseek-chat |
| Frontend | Single HTML file |
| Deploy | Render |

---

## Local setup

**1. Clone and install dependencies**
```bash
git clone <repo-url>
cd confidence
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**2. Set up environment variables**
```bash
cp .env.example .env.local
# Fill in all values in .env.local — see comments in the file
```

**3. Seed the product knowledge base**
```bash
# Run once — embeds 100 products and indexes them to Supabase
python scripts/build_product_db.py
```

**4. Run the backend**
```bash
uvicorn backend.main:app --reload
```

**5. Open the frontend**
```
Open frontend/index.html in your browser
```

---

## API

### POST /analyse
Accepts a selfie image, returns a full skincare routine.

**Request:** `multipart/form-data` with field `image`

**Response:**
```json
{
  "skin_profile": {
    "skin_type": "dry",
    "skin_score": 68,
    "concerns": [{"name": "dark_spots", "score": 0.82}]
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
  "avoid_ingredient": {"ingredient": "alcohol denat.", "reason": "Drying"},
  "medical_flag": false,
  "medical_note": null
}
```

When `medical_flag` is `true`, the UI shows an amber caution banner recommending specialist advice.

### GET /health
Returns `{"status": "ok"}`. Used by Render for health checks.

---

## Environment variables

See `.env.example` for the full list with descriptions.

| Variable | Where to get it |
|---|---|
| `PERFECTCORP_API_KEY` | https://yce.makeupar.com/api-console/en/api-keys/ |
| `VOYAGE_API_KEY` | https://dash.voyageai.com |
| `DEEPSEEK_API_KEY` | https://platform.deepseek.com |
| `SUPABASE_URL` | Your Supabase project settings |
| `SUPABASE_KEY` | Your Supabase project settings (service role) |

---

## Project files

| File | Purpose |
|---|---|
| `PLANNING.md` | Full project plan — read before touching anything |
| `STACK.md` | Tech choices and dependency rules |
| `VERTICAL.md` | Structural rules for where code lives |

---