"""
main.py — FastAPI routes only

This file is wiring. No business logic lives here.
Every route delegates immediately to a domain file:
  perfect_corp.py     → skin analysis
  rag_products.py     → product retrieval
  routine_generator.py→ triage + routine generation

If logic is accumulating here, it belongs in one of the three files above.
"""

import dataclasses
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from perfect_corp import (
    analyse,
    AnalysisTimeoutError,
    NoFaceDetectedError,
    PerfectCorpError,
)
from rag_products import retrieve_for_skin
from routine_generator import generate_routine, RoutineOutput

load_dotenv(Path(__file__).parent.parent / ".env.local")


# ── App setup ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Verify required env vars are present at startup — fail fast
    required = [
        "PERFECTCORP_API_KEY",
        "VOYAGE_API_KEY",
        "GROQ_API_KEY",
        "SUPABASE_URL",
        "SUPABASE_KEY",
    ]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        raise RuntimeError(f"Missing environment variables: {', '.join(missing)}")
    yield


app = FastAPI(title="Confidence API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten this before any production use
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Serialisation helper ──────────────────────────────────────────────────────

def _serialise(output: RoutineOutput) -> dict:
    """Convert RoutineOutput (dataclasses) to a plain dict for JSON response."""
    return dataclasses.asdict(output)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyse")
async def analyse_skin(
    image: UploadFile = File(...),
    ingredients_to_avoid: str = Form(default=""),
):
    """
    POST /analyse

    Accepts:
      image               — selfie image file (multipart/form-data)
      ingredients_to_avoid — comma-separated ingredient names (optional)

    Returns:
      RoutineOutput as JSON — see routine_generator.py for full schema

    Pipeline:
      1. Read image bytes
      2. Perfect Corp skin analysis (upload → task → poll → parse)
      3. RAG product retrieval (embed query → cosine search → top matches)
      4. Routine generation (triage → Groq prompt → structured JSON)
    """
    # Parse optional ingredients list
    avoid_list: list[str] = (
        [i.strip() for i in ingredients_to_avoid.split(",") if i.strip()]
        if ingredients_to_avoid
        else []
    )

    # Step 1 — read image
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail={
            "message": "No image received. Please upload a selfie.",
            "user_message": "We didn't receive an image. Try again with a clear selfie.",
        })

    # Step 2 — skin analysis
    timeout = int(os.environ.get("POLL_TIMEOUT_SECONDS", 30))
    try:
        skin_result = analyse(image_bytes, os.environ["PERFECTCORP_API_KEY"], timeout=timeout)
    except AnalysisTimeoutError:
        raise HTTPException(status_code=408, detail={
            "message": "Perfect Corp analysis timed out.",
            "user_message": (
                "We couldn't complete the analysis in time. "
                "Try again with a well-lit, front-facing photo. "
                "For persistent skin concerns, a dermatologist is always the most reliable option."
            ),
        })
    except NoFaceDetectedError:
        raise HTTPException(status_code=400, detail={
            "message": "No face detected in image.",
            "user_message": (
                "We couldn't read your skin clearly. "
                "Try a well-lit photo with your face centred. "
                "If you have skin concerns you'd like properly assessed, "
                "consider booking with a skin specialist."
            ),
        })
    except PerfectCorpError as e:
        raise HTTPException(status_code=502, detail={
            "message": f"Skin analysis failed: {e}",
            "user_message": f"Skin analysis error: {e}. Try again with a clear, well-lit photo.",
        })

    # Step 3 — product retrieval (graceful degradation — empty list if Supabase fails)
    products = retrieve_for_skin(skin_result, k=6, ingredients_to_avoid=avoid_list)

    # Step 4 — routine generation (triage + Groq)
    try:
        output = generate_routine(skin_result, products, avoid_list or None)
    except Exception as e:
        raise HTTPException(status_code=500, detail={
            "message": f"Routine generation failed: {e}",
            "user_message": (
                "Something went wrong generating your routine. "
                "Try again. For anything persistent or urgent, "
                "a dermatologist is always the right call."
            ),
        })

    return _serialise(output)