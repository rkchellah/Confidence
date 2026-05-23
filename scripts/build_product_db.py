"""
build_product_db.py — one-time seed script

Reads sample_products.json, builds an embedding chunk for each product,
embeds it with Voyage AI voyage-4-lite, and inserts into Supabase.

Run once before starting the backend:
    cd confidence/
    python scripts/build_product_db.py

If you need to reseed from scratch:
    1. Truncate the table in Supabase SQL editor: TRUNCATE skincare_products;
    2. Run this script again.
"""

import json
import os
import sys
import time
from pathlib import Path

import httpx
from supabase import create_client
from dotenv import load_dotenv

# Load secrets from .env.local in the project root
load_dotenv(Path(__file__).parent.parent / ".env.local")

MODEL           = "voyage-4-lite"


def build_content(product: dict) -> str:
    """
    Build the text chunk used for embedding.
    This exact format is what gets indexed — keep it consistent with
    any query strings you build in rag_products.py.
    """
    return (
        f"PRODUCT | {product['name']} | "
        f"brand: {product['brand']} | "
        f"category: {product['category']} | "
        f"skin_types: {', '.join(product['skin_types'])} | "
        f"concerns_addressed: {', '.join(product['concerns_addressed'])} | "
        f"key_ingredients: {', '.join(product['key_ingredients'])} | "
        f"avoid_for: {', '.join(product['avoid_for']) if product['avoid_for'] else 'none'} | "
        f"price_tier: {product['price_tier']}"
    )


def embed_one(text: str) -> list[float]:
    """Embed a single text with retry on 429."""
    while True:
        try:
            response = httpx.post(
                "https://api.voyageai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {os.environ['VOYAGE_API_KEY']}",
                    "Content-Type": "application/json",
                },
                json={"input": [text], "model": "voyage-4-lite", "input_type": "document"},
                timeout=30.0,
            )
            if response.status_code == 429:
                print("  Rate limited — waiting 60s...")
                time.sleep(60)
                continue
            response.raise_for_status()
            return response.json()["data"][0]["embedding"]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                print("  Rate limited — waiting 60s...")
                time.sleep(60)
                continue
            raise


def main() -> None:
    products_path = Path(__file__).parent / "sample_products.json"
    if not products_path.exists():
        print(f"Error: {products_path} not found")
        sys.exit(1)

    with open(products_path, "r", encoding="utf-8") as f:
        products = json.load(f)

    print(f"Loaded {len(products)} products")
    db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    inserted = 0
    errors = 0

    for i, product in enumerate(products, 1):
        content = build_content(product)
        try:
            embedding = embed_one(content)
            row = {
                "name":     product["name"],
                "brand":    product["brand"],
                "category": product["category"],
                "content":  content,
                "metadata": {
                    "brand":       product["brand"],
                    "category":    product["category"],
                    "skin_types":  product["skin_types"],
                    "concerns":    product["concerns_addressed"],
                    "ingredients": product["key_ingredients"],
                    "avoid_for":   product["avoid_for"],
                    "price_tier":  product["price_tier"],
                },
                "embedding": embedding,
            }
            db.table("skincare_products").insert(row).execute()
            inserted += 1
            print(f"  [{i}/100] ✓ {product['name']}")
            time.sleep(8)
        except Exception as e:
            print(f"  [{i}/100] ✗ {product['name']}: {e}")
            errors += 1

    print(f"\nDone. Inserted: {inserted} | Errors: {errors}")


if __name__ == "__main__":
    main()