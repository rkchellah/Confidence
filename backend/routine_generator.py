"""
Routine generation domain — routine_generator.py

Responsibilities:
  1. check_severity() — Python triage BEFORE Groq is called
  2. generate_routine() — assemble prompt, call Groq, return structured JSON
  3. referral_response() — return safe referral card when triage fires

Safety design (enforced in code, not the prompt):
  - Concerns scoring ≥ 0.85 in REFERRAL_CONCERNS → referral card, Groq not called
  - Concerns scoring 0.4–0.85 → routine + soft nudge to see a dermatologist
  - Concerns scoring < 0.4 → full routine, no nudge

System prompt hard limits (injected on every call, not overrideable):
  - Never diagnose — use observation language only
  - Never recommend prescription products
  - Only reference ingredients from the RAG product context
  - Never claim the analysis is medically accurate
"""

import json
import os
from dataclasses import dataclass, field

from groq import Groq
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
    This runs BEFORE Groq is called — the decision is in Python, not the LLM.
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


def referral_response(
    skin_result: SkinAnalysisResult,
    severe_concerns: list[str],
    moderate_concerns: list[str],
) -> RoutineOutput:
    """
    Build a safe referral response when severe concerns are detected.
    Groq is never called when this is returned.
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
        morning_routine=[],
        evening_routine=[],
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
      "reason": "one sentence explaining why this suits the detected skin profile"
    }
  ],
  "evening_routine": [
    {
      "step": 1,
      "role": "cleanser",
      "product": "exact product name from context",
      "key_ingredients": ["ingredient1", "ingredient2"],
      "reason": "one sentence explaining why this suits the detected skin profile"
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
- reason fields: one sentence, plain language, reference the detected concern by name.

FEW-SHOT EXAMPLES:

EXAMPLE 1 — Dry skin, dark spots, enlarged pores:
{
  "morning_routine": [
    {"step": 1, "role": "cleanser", "product": "CeraVe Hydrating Cleanser", "key_ingredients": ["ceramides", "hyaluronic acid"], "reason": "Gentle non-stripping formula preserves the moisture barrier — critical for the detected dryness concern."},
    {"step": 2, "role": "serum", "product": "TruSkin Vitamin C Serum", "key_ingredients": ["vitamin C", "vitamin E", "ferulic acid"], "reason": "Directly targets the detected age spot concern — vitamin C brightens over 4-6 weeks."},
    {"step": 3, "role": "moisturiser", "product": "CeraVe Moisturising Cream", "key_ingredients": ["ceramides", "niacinamide"], "reason": "Repairs the moisture barrier; niacinamide also helps with the detected pore concern."},
    {"step": 4, "role": "SPF", "product": "La Roche-Posay Anthelios Melt-in Milk SPF 100", "key_ingredients": ["avobenzone", "homosalate"], "reason": "Essential to prevent dark spots from worsening with sun exposure."}
  ],
  "evening_routine": [
    {"step": 1, "role": "cleanser", "product": "CeraVe Hydrating Cleanser", "key_ingredients": ["ceramides", "hyaluronic acid"], "reason": "Removes the day without stripping — suits the detected dryness concern."},
    {"step": 2, "role": "treatment", "product": "The Ordinary Retinol 0.5% in Squalane", "key_ingredients": ["retinol", "squalane"], "reason": "Addresses the detected texture concern and supports skin renewal overnight."},
    {"step": 3, "role": "moisturiser", "product": "CeraVe Moisturising Cream", "key_ingredients": ["ceramides", "hyaluronic acid"], "reason": "Locks in moisture overnight — suits the detected dryness concern."}
  ],
  "avoid_ingredient": {
    "ingredient": "alcohol denat.",
    "reason": "Drying — would worsen the detected moisture concern."
  }
}

EXAMPLE 2 — Oily skin, acne (moderate, score 0.62), enlarged pores:
{
  "morning_routine": [
    {"step": 1, "role": "cleanser", "product": "La Roche-Posay Effaclar Purifying Foaming Gel", "key_ingredients": ["zinc", "niacinamide", "LHA"], "reason": "Controls the detected oiliness concern without over-drying."},
    {"step": 2, "role": "serum", "product": "The Ordinary Niacinamide 10% + Zinc 1%", "key_ingredients": ["niacinamide", "zinc PCA"], "reason": "Targets the detected pore and acne concerns — niacinamide reduces excess oil."},
    {"step": 3, "role": "moisturiser", "product": "Neutrogena Hydro Boost Water Gel", "key_ingredients": ["hyaluronic acid", "dimethicone"], "reason": "Lightweight hydration that won't block pores — suits the detected oiliness concern."},
    {"step": 4, "role": "SPF", "product": "EltaMD UV Clear Broad-Spectrum SPF 46", "key_ingredients": ["niacinamide", "zinc oxide"], "reason": "Non-comedogenic formula — safe to use alongside the detected acne concern."}
  ],
  "evening_routine": [
    {"step": 1, "role": "cleanser", "product": "CeraVe Foaming Facial Cleanser", "key_ingredients": ["niacinamide", "ceramides"], "reason": "Removes excess oil from the day without disrupting the skin barrier."},
    {"step": 2, "role": "treatment", "product": "Differin Adapalene Gel 0.1%", "key_ingredients": ["adapalene"], "reason": "OTC retinoid that addresses the detected acne and texture concerns over time."},
    {"step": 3, "role": "moisturiser", "product": "COSRX Oil-Free Ultra Moisturising Lotion", "key_ingredients": ["birch sap", "betaine"], "reason": "Lightweight, non-comedogenic — suits the detected oiliness concern."}
  ],
  "avoid_ingredient": {
    "ingredient": "coconut oil",
    "reason": "Highly comedogenic — would worsen the detected acne and pore concerns."
  }
}"""


# ── 3. Groq call ──────────────────────────────────────────────────────────────

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
        nudge_section = f"\nMODERATE CONCERNS requiring nudge: {concern_list}\nFor these concerns, add this note in the reason field: 'If this persists after 8 weeks of consistent use, consider speaking to a dermatologist.'\n"

    return f"""SKIN ANALYSIS RESULT:
Skin type: {skin_result.skin_type}
Overall score: {skin_result.skin_score:.2f}/1.0

Top concerns:
{concern_lines}
{avoid_section}{nudge_section}
PRODUCT CONTEXT (use only these products):
{product_context}

Generate the morning and evening routine JSON now."""


def _parse_groq_response(content: str) -> dict:
    """
    Parse Groq's response into a dict.
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
      1. Triage — if severe concerns found, return referral card (Groq not called)
      2. Build prompt with skin profile + RAG product context
      3. Call Groq, parse JSON
      4. Return RoutineOutput

    Retries once on JSON parse failure with a correction nudge.
    """
    # Step 1 — triage
    severe = check_severity(skin_result.concerns)
    moderate = get_moderate_concerns(skin_result.concerns)

    if severe:
        return referral_response(skin_result, severe, moderate)

    # Step 2 — build prompt
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    user_message = _build_user_message(skin_result, products, ingredients_to_avoid, moderate)

    # Step 3 — call Groq (retry once on parse failure)
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
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *messages,
            ],
            temperature=0.3,
            max_tokens=2000,
        )

        raw_content = response.choices[0].message.content

        try:
            parsed = _parse_groq_response(raw_content)
            break
        except (json.JSONDecodeError, KeyError):
            if attempt == 1:
                raise ValueError(f"Groq returned invalid JSON after retry: {raw_content}")

    # Step 4 — build RoutineOutput
    def _steps(raw_steps: list[dict]) -> list[RoutineStep]:
        return [
            RoutineStep(
                step=s.get("step", i + 1),
                role=s.get("role", ""),
                product=s.get("product", ""),
                key_ingredients=s.get("key_ingredients", []),
                reason=s.get("reason", ""),
            )
            for i, s in enumerate(raw_steps)
        ]

    avoid_raw = parsed.get("avoid_ingredient")
    avoid = (
        AvoidIngredient(
            ingredient=avoid_raw.get("ingredient", ""),
            reason=avoid_raw.get("reason", ""),
        )
        if avoid_raw
        else None
    )

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
        morning_routine=_steps(parsed.get("morning_routine", [])),
        evening_routine=_steps(parsed.get("evening_routine", [])),
        avoid_ingredient=avoid,
        referral_concerns=[],
        moderate_nudge_concerns=moderate,
    )