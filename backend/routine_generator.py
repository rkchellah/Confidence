"""
Routine generation domain — routine_generator.py

Responsibilities:
  1. check_severity() — Python triage BEFORE DeepSeek is called
  2. generate_routine() — assemble prompt, call DeepSeek, return structured JSON
  3. referral_response() — return safe referral card when triage fires

Safety design (enforced in code, not the prompt):
  - Concerns scoring ≥ 0.85 in REFERRAL_CONCERNS → referral card + supportive
    cleanser / moisturiser / SPF routine. DeepSeek is not called.
    Decision change 2026-09-05: routine cards were added back. The first
    version returned empty lists (referral only). Empty cards looked like a
    broken result. The baseline must not treat the severe finding.
  - Concerns scoring 0.4–0.85 → DeepSeek routine + soft nudge to see a dermatologist
  - Concerns scoring < 0.4 → full DeepSeek routine, no nudge

System prompt hard limits (injected on every call, not overrideable):
  - Never diagnose — use observation language only
  - Never recommend prescription products
  - Only reference ingredients from the RAG product context
  - Never claim the analysis is medically accurate
"""

import json
import os
from dataclasses import dataclass, field

from openai import OpenAI
from dotenv import load_dotenv

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from perfect_corp import SkinAnalysisResult, SkinConcern
from rag_products import RetrievedProduct

load_dotenv(Path(__file__).parent.parent / ".env.local")

# ── Safety thresholds ─────────────────────────────────────────────────────────

HIGH_SEVERITY_THRESHOLD = 0.85
MODERATE_THRESHOLD = 0.40

# Only these concerns trigger the severe referral pathway.
# OTC products are genuinely insufficient at high severity for these.
# Concerns like pores, dark_circles, oiliness at 0.85+ still get recommendations
# because the risk of harm from a cosmetic product is low.
REFERRAL_CONCERNS = {"acne", "redness", "spots", "age_spot", "texture"}

# ── Output types ──────────────────────────────────────────────────────────────

@dataclass
class RoutineStep:
    step: int
    role: str                      # cleanser | serum | moisturiser | SPF | treatment | eye cream
    product: str
    key_ingredients: list[str]
    reason: str


@dataclass
class AvoidIngredient:
    ingredient: str
    reason: str


@dataclass
class ReferralConcern:
    name: str
    score: float
    message: str


@dataclass
class RoutineOutput:
    skin_profile: dict
    morning_routine: list[RoutineStep]
    evening_routine: list[RoutineStep]
    avoid_ingredient: AvoidIngredient | None
    referral_concerns: list[ReferralConcern]
    moderate_nudge_concerns: list[str]


# ── 1. Triage ─────────────────────────────────────────────────────────────────

def check_severity(concerns: list[SkinConcern]) -> list[str]:
    """
    Return names of concerns that are too severe for OTC recommendations.
    This runs BEFORE DeepSeek is called — the decision is in Python, not the LLM.
    """
    return [
        c.name for c in concerns
        if c.score >= HIGH_SEVERITY_THRESHOLD
        and c.name in REFERRAL_CONCERNS
    ]


def get_moderate_concerns(concerns: list[SkinConcern]) -> list[str]:
    """Return names of concerns in the moderate range (0.4–0.85)."""
    return [
        c.name for c in concerns
        if MODERATE_THRESHOLD <= c.score < HIGH_SEVERITY_THRESHOLD
    ]


def _product_label(product: RetrievedProduct) -> str:
    brand = (product.brand or "").strip()
    name = (product.name or "").strip()
    if brand and brand.lower() not in name.lower():
        return f"{brand} {name}"
    return name or "A gentle option from the catalogue"


def _product_ingredients(product: RetrievedProduct) -> list[str]:
    raw = product.metadata.get("ingredients", [])
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw[:3]]


def _catalogue_product(name: str, brand: str, category: str, ingredients: list[str]) -> RetrievedProduct:
    return RetrievedProduct(
        name=name,
        brand=brand,
        category=category,
        content=f"{category} {name}",
        metadata={"ingredients": ingredients},
        similarity=0.0,
    )


# Same trio as frontend fallbackRoutine() when RAG returns nothing.
_CATALOGUE_CLEANSER = _catalogue_product(
    "Gentle Skin Cleanser",
    "Cetaphil",
    "cleanser",
    ["glycerin", "panthenol", "niacinamide"],
)
_CATALOGUE_MOISTURISER = _catalogue_product(
    "Toleriane Double Repair Moisturiser",
    "La Roche-Posay",
    "moisturiser",
    ["ceramides", "niacinamide"],
)
_CATALOGUE_SPF = _catalogue_product(
    "Hydrating Mineral Sunscreen SPF 30",
    "CeraVe",
    "SPF",
    ["zinc oxide", "titanium dioxide", "ceramides"],
)


def _pick_product(products: list[RetrievedProduct], *needles: str) -> RetrievedProduct | None:
    for product in products:
        blob = f"{product.category} {product.name} {product.content}".lower()
        if any(needle in blob for needle in needles):
            return product
    return None


def _supportive_routine(products: list[RetrievedProduct]) -> tuple[list[RoutineStep], list[RoutineStep]]:
    """
    Conservative cleanser / moisturiser / SPF steps from the catalogue.
    Used when severe triage fires — DeepSeek is still not called.
    If RAG returns no matching row, use the named catalogue trio.
    """
    cleanser = _pick_product(products, "cleanser", "cleansing", "wash") or _CATALOGUE_CLEANSER
    moisturiser = _pick_product(products, "moisturis", "moisturiz", "cream", "lotion") or _CATALOGUE_MOISTURISER
    spf = _pick_product(products, "spf", "sunscreen", "sun screen") or _CATALOGUE_SPF
    if not products:
        print("[routine_generator] RAG empty — using named catalogue baseline")

    def step(number: int, role: str, product: RetrievedProduct | None, reason: str) -> RoutineStep:
        if product is None:
            return RoutineStep(
                step=number,
                role=role,
                product=f"A gentle {role}",
                key_ingredients=[],
                reason=reason,
            )
        return RoutineStep(
            step=number,
            role=role,
            product=_product_label(product),
            key_ingredients=_product_ingredients(product),
            reason=reason,
        )

    morning = [
        step(1, "cleanser", cleanser, "Wash your face."),
        step(2, "moisturiser", moisturiser, "Apply this cream."),
        step(3, "SPF", spf, "Put this on last before you go out."),
    ]
    evening = [
        step(1, "cleanser", cleanser, "Wash your face."),
        step(2, "moisturiser", moisturiser, "Apply this cream before bed."),
    ]
    return morning, evening


def referral_response(
    skin_result: SkinAnalysisResult,
    severe_concerns: list[str],
    moderate_concerns: list[str],
    products: list[RetrievedProduct] | None = None,
) -> RoutineOutput:
    """
    Build a safe referral response when severe concerns are detected.
    DeepSeek is never called when this is returned.
    A supportive OTC baseline is still included so the user is not left without steps.
    """
    referrals = []
    for concern_name in severe_concerns:
        concern = next((c for c in skin_result.concerns if c.name == concern_name), None)
        score = concern.score if concern else HIGH_SEVERITY_THRESHOLD
        referrals.append(
            ReferralConcern(
                name=concern_name,
                score=score,
                message=(
                    f"The analysis detected a high level of {concern_name.replace('_', ' ')} "
                    f"({score:.2f}). At this severity, over-the-counter products are unlikely "
                    "to be sufficient. We recommend a consultation with a dermatologist before "
                    "starting any new skincare routine."
                ),
            )
        )

    morning, evening = _supportive_routine(products or [])

    return RoutineOutput(
        skin_profile={
            "skin_type": skin_result.skin_type,
            "skin_score": round(skin_result.skin_score, 2),
            "concerns": [
                {
                    "name": c.name,
                    "score": round(c.score, 2),
                    "tier": _tier(c.score),
                }
                for c in skin_result.concerns[:5]
            ],
        },
        morning_routine=morning,
        evening_routine=evening,
        avoid_ingredient=None,
        referral_concerns=referrals,
        moderate_nudge_concerns=moderate_concerns,
    )


def _tier(score: float) -> str:
    if score >= HIGH_SEVERITY_THRESHOLD:
        return "severe"
    if score >= MODERATE_THRESHOLD:
        return "moderate"
    return "mild"


# ── 2. System prompt ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a skincare routine assistant. You help people find over-the-counter skincare products suited to their skin type and computer-vision-detected concerns.

HARD LIMITS — never violate these:
1. Never diagnose. Say "the analysis detected elevated redness" not "you have rosacea". You are not a doctor.
2. Never recommend prescription products (tretinoin, antibiotics, steroid creams, oral medications). OTC products only.
3. Only reference ingredients and benefits from the PRODUCT CONTEXT provided. Never invent ingredients or efficacy claims. Never say "clinically proven" unless it appears verbatim in the product context.
4. Never suggest the analysis is medically accurate. It is a computer vision estimate, not a clinical assessment.
5. Scope: cleansers, serums, moisturisers, SPF, eye creams, toners, OTC treatments only.

YOUR OUTPUT FORMAT:
Return a single valid JSON object. No markdown. No explanation. No text before or after the JSON.

Schema:
{
  "morning_routine": [
    {
      "step": 1,
      "role": "cleanser",
      "product": "exact product name from context",
      "key_ingredients": ["ingredient1", "ingredient2"],
      "reason": "one short how-to, like Wash your face."
    }
  ],
  "evening_routine": [
    {
      "step": 1,
      "role": "cleanser",
      "product": "exact product name from context",
      "key_ingredients": ["ingredient1", "ingredient2"],
      "reason": "one short how-to, like Wash your face."
    }
  ],
  "avoid_ingredient": {
    "ingredient": "ingredient name",
    "reason": "plain language explanation based on detected concerns"
  }
}

RULES:
- morning_routine: 3-4 steps. Always include cleanser, moisturiser, SPF. Add a serum or treatment if relevant.
- evening_routine: 3-4 steps. Always include cleanser, moisturiser. Add treatment or eye cream if relevant. No SPF at night.
- Use only products from the PRODUCT CONTEXT below.
- avoid_ingredient: one ingredient to avoid based on the skin profile. Keep it simple and specific.
- reason fields: one short how-to in everyday English. Say what to do, not why the formula is clever. No "barrier", "actives", "detected concern", "severity", or diagnosis language. Examples: "Wash your face." "Apply this cream." "Put this on last before you go out."

FEW-SHOT EXAMPLES:

EXAMPLE 1 — Dry skin, dark spots, enlarged pores:
{
  "morning_routine": [
    {"step": 1, "role": "cleanser", "product": "CeraVe Hydrating Cleanser", "key_ingredients": ["ceramides", "hyaluronic acid"], "reason": "Wash your face."},
    {"step": 2, "role": "serum", "product": "TruSkin Vitamin C Serum", "key_ingredients": ["vitamin C", "vitamin E", "ferulic acid"], "reason": "Apply a few drops after washing."},
    {"step": 3, "role": "moisturiser", "product": "CeraVe Moisturising Cream", "key_ingredients": ["ceramides", "niacinamide"], "reason": "Apply this cream."},
    {"step": 4, "role": "SPF", "product": "La Roche-Posay Anthelios Melt-in Milk SPF 100", "key_ingredients": ["avobenzone", "homosalate"], "reason": "Put this on last before you go out."}
  ],
  "evening_routine": [
    {"step": 1, "role": "cleanser", "product": "CeraVe Hydrating Cleanser", "key_ingredients": ["ceramides", "hyaluronic acid"], "reason": "Wash your face."},
    {"step": 2, "role": "treatment", "product": "The Ordinary Retinol 0.5% in Squalane", "key_ingredients": ["retinol", "squalane"], "reason": "Apply a thin layer after washing."},
    {"step": 3, "role": "moisturiser", "product": "CeraVe Moisturising Cream", "key_ingredients": ["ceramides", "hyaluronic acid"], "reason": "Apply this cream before bed."}
  ],
  "avoid_ingredient": {
    "ingredient": "alcohol denat.",
    "reason": "Can leave skin feeling tight and dry."
  }
}

EXAMPLE 2 — Oily skin, acne (moderate, score 0.62), enlarged pores:
{
  "morning_routine": [
    {"step": 1, "role": "cleanser", "product": "La Roche-Posay Effaclar Purifying Foaming Gel", "key_ingredients": ["zinc", "niacinamide", "LHA"], "reason": "Wash your face."},
    {"step": 2, "role": "serum", "product": "The Ordinary Niacinamide 10% + Zinc 1%", "key_ingredients": ["niacinamide", "zinc PCA"], "reason": "Apply a few drops after washing."},
    {"step": 3, "role": "moisturiser", "product": "Neutrogena Hydro Boost Water Gel", "key_ingredients": ["hyaluronic acid", "dimethicone"], "reason": "Apply this cream."},
    {"step": 4, "role": "SPF", "product": "EltaMD UV Clear Broad-Spectrum SPF 46", "key_ingredients": ["niacinamide", "zinc oxide"], "reason": "Put this on last before you go out."}
  ],
  "evening_routine": [
    {"step": 1, "role": "cleanser", "product": "CeraVe Foaming Facial Cleanser", "key_ingredients": ["niacinamide", "ceramides"], "reason": "Wash your face."},
    {"step": 2, "role": "treatment", "product": "Differin Adapalene Gel 0.1%", "key_ingredients": ["adapalene"], "reason": "Apply a thin layer after washing."},
    {"step": 3, "role": "moisturiser", "product": "COSRX Oil-Free Ultra Moisturising Lotion", "key_ingredients": ["birch sap", "betaine"], "reason": "Apply this cream before bed."}
  ],
  "avoid_ingredient": {
    "ingredient": "coconut oil",
    "reason": "Can clog pores on oily or breakout-prone skin."
  }
}"""


# ── 3. DeepSeek call ─────────────────────────────────────────────────────────

def _build_user_message(
    skin_result: SkinAnalysisResult,
    products: list[RetrievedProduct],
    ingredients_to_avoid: list[str] | None,
    moderate_concerns: list[str],
) -> str:
    """Assemble the user message with skin profile + RAG product context."""

    concern_lines = "\n".join(
        f"  - {c.name.replace('_', ' ')}: {c.score:.2f} ({_tier(c.score)})"
        for c in skin_result.concerns[:6]
    )

    product_context = "\n\n".join(p.content for p in products) if products else "No specific products retrieved — recommend based on skin type and concerns generally."

    avoid_section = ""
    if ingredients_to_avoid:
        avoid_section = f"\nINGREDIENTS TO AVOID (user-specified): {', '.join(ingredients_to_avoid)}\n"

    nudge_section = ""
    if moderate_concerns:
        concern_list = ", ".join(c.replace("_", " ") for c in moderate_concerns)
        nudge_section = f"\nMODERATE CONCERNS for the 8-week watch list: {concern_list}\nDo not put clinician language in the reason fields. Keep reasons as short how-tos only.\n"

    return f"""SKIN ANALYSIS RESULT:
Skin type: {skin_result.skin_type}
Overall score: {skin_result.skin_score:.2f}/1.0

Top concerns:
{concern_lines}
{avoid_section}{nudge_section}
PRODUCT CONTEXT (use only these products):
{product_context}

Generate the morning and evening routine JSON now."""


def _parse_llm_response(content: str) -> dict:
    """
    Parse DeepSeek's response into a dict.
    Strips any accidental markdown fences if present.
    """
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])
    return json.loads(content)


def generate_routine(
    skin_result: SkinAnalysisResult,
    products: list[RetrievedProduct],
    ingredients_to_avoid: list[str] | None = None,
) -> RoutineOutput:
    """
    Full pipeline:
      1. Triage — if severe concerns found, return referral card (DeepSeek not called)
      2. Build prompt with skin profile + RAG product context
      3. Call DeepSeek, parse JSON
      4. Return RoutineOutput

    Retries once on JSON parse failure with a correction nudge.
    """
    # Step 1 — triage
    severe = check_severity(skin_result.concerns)
    moderate = get_moderate_concerns(skin_result.concerns)

    if severe:
        return referral_response(skin_result, severe, moderate, products)

    # Step 2 — build prompt
    client = OpenAI(
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
    )
    user_message = _build_user_message(skin_result, products, ingredients_to_avoid, moderate)

    # Step 3 — call DeepSeek (retry once on parse failure)
    raw_content = None
    for attempt in range(2):
        messages = [{"role": "user", "content": user_message}]

        if attempt == 1 and raw_content:
            messages.append({"role": "assistant", "content": raw_content})
            messages.append({
                "role": "user",
                "content": "Your response was not valid JSON. Return only the JSON object — no markdown, no explanation.",
            })

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *messages,
            ],
            temperature=0.3,
            max_tokens=2000,
        )

        raw_content = response.choices[0].message.content

        try:
            parsed = _parse_llm_response(raw_content)
            break
        except (json.JSONDecodeError, KeyError):
            if attempt == 1:
                raise ValueError(f"DeepSeek returned invalid JSON after retry: {raw_content}")

    # Step 4 — build RoutineOutput
    def _steps(raw_steps: object) -> list[RoutineStep]:
        if not isinstance(raw_steps, list):
            return []
        built: list[RoutineStep] = []
        for i, item in enumerate(raw_steps):
            if not isinstance(item, dict):
                continue
            ingredients = item.get("key_ingredients", [])
            if not isinstance(ingredients, list):
                ingredients = []
            raw_step = item.get("step", i + 1)
            try:
                number = int(raw_step)
            except (TypeError, ValueError):
                number = i + 1
            built.append(
                RoutineStep(
                    step=number,
                    role=str(item.get("role", "")),
                    product=str(item.get("product", "")),
                    key_ingredients=[str(part) for part in ingredients],
                    reason=str(item.get("reason", "")),
                )
            )
        return built

    avoid_raw = parsed.get("avoid_ingredient")
    avoid = (
        AvoidIngredient(
            ingredient=avoid_raw.get("ingredient", ""),
            reason=avoid_raw.get("reason", ""),
        )
        if avoid_raw
        else None
    )

    morning = _steps(parsed.get("morning_routine") or parsed.get("morning") or [])
    evening = _steps(parsed.get("evening_routine") or parsed.get("evening") or [])
    if not morning and not evening:
        morning, evening = _supportive_routine(products)

    return RoutineOutput(
        skin_profile={
            "skin_type": skin_result.skin_type,
            "skin_score": round(skin_result.skin_score, 2),
            "concerns": [
                {
                    "name": c.name,
                    "score": round(c.score, 2),
                    "tier": _tier(c.score),
                }
                for c in skin_result.concerns[:5]
            ],
        },
        morning_routine=morning,
        evening_routine=evening,
        avoid_ingredient=avoid,
        referral_concerns=[],
        moderate_nudge_concerns=moderate,
    )