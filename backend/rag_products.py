"""
RAG retrieval domain — rag_products.py

Three responsibilities:
  1. embed(text) → vector (Voyage AI primary, sentence-transformers fallback)
  2. build_query(skin_result) → natural language search string
  3. retrieve(query, k) → top matching products from Supabase pgvector

The embed() function is the only place the embedding provider is referenced.
Swap provider here — nothing else in the codebase changes.

If switching to the sentence-transformers fallback:
  - Uncomment the fallback block in embed()
  - Comment out the Voyage AI block
  - Update Supabase column: vector(1024) → vector(384)
  - Rebuild the product index with build_product_db.py

Voyage AI docs:  https://docs.voyageai.com
Supabase Python: https://supabase.com/docs/reference/python
"""

import os
from dataclasses import dataclass

import httpx
from supabase import create_client, Client
from dotenv import load_dotenv

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from perfect_corp import SkinAnalysisResult

load_dotenv(Path(__file__).parent.parent / ".env.local")

# ── Clients (initialised once at import time) ─────────────────────────────────

_supabase_client: Client | None = None


def _supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_KEY"]
        _supabase_client = create_client(url, key)
    return _supabase_client


# ── Return type ───────────────────────────────────────────────────────────────

@dataclass
class RetrievedProduct:
    name: str
    brand: str
    category: str
    content: str           # full embedding chunk — injected into Claude prompt
    metadata: dict         # {skin_types, concerns, ingredients, price_tier}
    similarity: float


# ── 1. embed() ────────────────────────────────────────────────────────────────

def embed(text: str, input_type: str = "query") -> list[float]:
    response = httpx.post(
        "https://api.voyageai.com/v1/embeddings",
        headers={
            "Authorization": f"Bearer {os.environ['VOYAGE_API_KEY']}",
            "Content-Type": "application/json",
        },
        json={"input": [text], "model": "voyage-4-lite", "input_type": input_type},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]


# ── 2. build_query() ─────────────────────────────────────────────────────────

def build_query(skin_result: SkinAnalysisResult) -> str:
    """
    Convert a SkinAnalysisResult into a natural language search string.

    Takes the top 3 concerns by score and builds a query the vector search
    can match against product embeddings.

    Example output:
      "moisturiser for dry skin with acne, enlarged pores, and redness"
    """
    skin_type = skin_result.skin_type

    # Top 3 concerns by score — these drive the retrieval
    top_concerns = skin_result.concerns[:3]

    if not top_concerns:
        return f"skincare routine products for {skin_type} skin"

    # Format concern names for readability
    concern_labels = [c.name.replace("_", " ") for c in top_concerns]

    if len(concern_labels) == 1:
        concerns_str = concern_labels[0]
    elif len(concern_labels) == 2:
        concerns_str = f"{concern_labels[0]} and {concern_labels[1]}"
    else:
        concerns_str = (
            f"{concern_labels[0]}, {concern_labels[1]}, and {concern_labels[2]}"
        )

    return f"skincare products for {skin_type} skin with {concerns_str}"


# ── 3. retrieve() ─────────────────────────────────────────────────────────────

def retrieve(
    query: str,
    k: int = 3,
    ingredients_to_avoid: list[str] | None = None,
) -> list[RetrievedProduct]:
    """
    Embed the query and run cosine similarity search against skincare_products
    in Supabase via the match_skincare_products RPC function.

    Returns up to k products sorted by similarity (highest first).

    If Supabase is unreachable, returns an empty list — the caller (main.py)
    handles this gracefully by asking DeepSeek to generate without product context.

    ingredients_to_avoid: optionally filter out products containing these.
    The filtering is post-retrieval and simple — we check the content string.
    """
    try:
        query_vector = embed(query, input_type="query")

        response = (
            _supabase()
            .rpc(
                "match_skincare_products",
                {
                    "query_embedding": query_vector,
                    "match_count": k * 2,  # fetch extra, filter down below
                },
            )
            .execute()
        )

        rows = response.data or []

        products: list[RetrievedProduct] = []
        for row in rows:
            content = row.get("content", "")

            # Filter out products containing ingredients to avoid
            if ingredients_to_avoid:
                content_lower = content.lower()
                if any(ing.lower() in content_lower for ing in ingredients_to_avoid):
                    continue

            metadata = row.get("metadata") or {}
            products.append(
                RetrievedProduct(
                    name=row.get("name", ""),
                    brand=row.get("brand", ""),
                    category=row.get("category", ""),
                    content=content,
                    metadata=metadata,
                    similarity=float(row.get("similarity", 0.0)),
                )
            )

            if len(products) >= k:
                break

        return products

    except Exception as e:
        # Graceful degradation — Supabase unreachable or RPC failed
        # Log the error but don't crash the request
        print(f"[rag_products] retrieve() failed: {e}")
        return []


# ── Convenience: retrieve per concern ─────────────────────────────────────────

def retrieve_for_skin(
    skin_result: SkinAnalysisResult,
    k: int = 3,
    ingredients_to_avoid: list[str] | None = None,
) -> list[RetrievedProduct]:
    """
    Build query from skin result and retrieve matching products.
    This is the function routine_generator.py calls directly.

    Usage:
        products = retrieve_for_skin(skin_result, ingredients_to_avoid=["alcohol denat."])
    """
    query = build_query(skin_result)
    return retrieve(query, k=k, ingredients_to_avoid=ingredients_to_avoid)