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

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from perfect_corp import (
    analyse,
    AnalysisTimeoutError,
    NoFaceDetectedError,
    ImageTooLargeError,
    PerfectCorpError,
    MAX_FILE_SIZE_BYTES,
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
        "DEEPSEEK_API_KEY",
        "SUPABASE_URL",
        "SUPABASE_KEY",
    ]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        raise RuntimeError(f"Missing environment variables: {', '.join(missing)}")
    yield


app = FastAPI(title="Confidence API", version="1.0.0", lifespan=lifespan)

# ── Upload checks ─────────────────────────────────────────────────────────────

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}


def _sniff_content_type(data: bytes) -> str | None:
    """Real image type from magic bytes — the client-sent header is not trusted alone."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return None


def _fail(status: int, log_detail: str, user_message: str) -> HTTPException:
    """Log the detail server-side; the client only ever gets the fixed user_message."""
    print(f"[analyse] {status}: {log_detail}")
    return HTTPException(status_code=status, detail={"user_message": user_message})


WRONG_TYPE_MESSAGE = "Please upload a JPG or PNG photo."
TOO_LARGE_MESSAGE = (
    "Your photo is too large — please use an image under 10MB. "
    "Try compressing it or taking a new photo at a lower resolution."
)
NO_FACE_MESSAGE = (
    "We couldn't read your skin clearly. "
    "Try a well-lit photo with your face centred. "
    "If you have skin concerns you'd like properly assessed, "
    "consider booking with a skin specialist."
)
# Multipart overhead (boundaries, the ingredients field) on top of the image.
MAX_REQUEST_BYTES = MAX_FILE_SIZE_BYTES + 1024 * 1024


@app.middleware("http")
async def reject_oversized_uploads(request: Request, call_next):
    """Refuse a too-large /analyse body from its Content-Length, before it is parsed."""
    if request.method == "POST" and request.url.path == "/analyse":
        length = request.headers.get("content-length", "")
        if length.isdigit() and int(length) > MAX_REQUEST_BYTES:
            print(f"[analyse] 413: Content-Length {length} over limit")
            return JSONResponse(status_code=413, content={"detail": {"user_message": TOO_LARGE_MESSAGE}})
    return await call_next(request)


# Registered last so it is the outermost layer — the early 413 above still gets CORS headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://confidence-two.vercel.app",
        "http://localhost:3000",
        "http://127.0.0.1:5500",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


ANALYSIS_FAILED_MESSAGE = (
    "We couldn't analyse this photo right now. "
    "Try again with a clear, well-lit photo."
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
def analyse_skin(
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
      4. Routine generation (triage → DeepSeek prompt → structured JSON)
    """
    # Parse optional ingredients list
    avoid_list: list[str] = (
        [i.strip() for i in ingredients_to_avoid.split(",") if i.strip()]
        if ingredients_to_avoid
        else []
    )

    # Step 1 — check type, then read at most one byte past the limit
    declared_type = (image.content_type or "").lower()
    if declared_type not in ALLOWED_CONTENT_TYPES:
        raise _fail(415, f"rejected declared content type {declared_type!r}", WRONG_TYPE_MESSAGE)

    image_bytes = image.file.read(MAX_FILE_SIZE_BYTES + 1)
    if not image_bytes:
        raise _fail(400, "empty upload", "We didn't receive an image. Try again with a clear selfie.")
    if len(image_bytes) > MAX_FILE_SIZE_BYTES:
        raise _fail(413, "upload over 10MB limit", TOO_LARGE_MESSAGE)

    content_type = _sniff_content_type(image_bytes)
    if content_type is None:
        raise _fail(415, f"bytes are not JPEG/PNG (declared {declared_type!r})", WRONG_TYPE_MESSAGE)

    # Step 2 — skin analysis
    timeout = int(os.environ.get("POLL_TIMEOUT_SECONDS", 30))
    try:
        skin_result = analyse(
            image_bytes,
            os.environ["PERFECTCORP_API_KEY"],
            timeout=timeout,
            content_type=content_type,
        )
    except AnalysisTimeoutError as e:
        raise _fail(408, f"Perfect Corp timeout: {e}", (
            "We couldn't complete the analysis in time. "
            "Try again with a well-lit, front-facing photo. "
            "For persistent skin concerns, a dermatologist is always the most reliable option."
        ))
    except NoFaceDetectedError as e:
        raise _fail(400, f"no face / image unreadable: {e}", NO_FACE_MESSAGE)
    except ImageTooLargeError as e:
        raise _fail(413, f"Perfect Corp size limit: {e}", TOO_LARGE_MESSAGE)
    except PerfectCorpError as e:
        raise _fail(502, f"Perfect Corp error: {e}", ANALYSIS_FAILED_MESSAGE)
    except Exception as e:
        raise _fail(502, f"skin analysis failed unexpectedly: {type(e).__name__}: {e}", ANALYSIS_FAILED_MESSAGE)

    # Step 3 — product retrieval (graceful degradation — empty list if Supabase fails)
    products = retrieve_for_skin(skin_result, k=6, ingredients_to_avoid=avoid_list)

    # Step 4 — routine generation (triage + DeepSeek)
    try:
        output = generate_routine(skin_result, products, avoid_list or None)
    except Exception as e:
        raise _fail(500, f"routine generation failed: {type(e).__name__}: {e}", (
            "Something went wrong generating your routine. "
            "Try again. For anything persistent or urgent, "
            "a dermatologist is always the right call."
        ))

    return _serialise(output)