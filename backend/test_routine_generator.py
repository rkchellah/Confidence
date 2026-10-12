"""
Tests for the catalogue post-check in routine_generator.generate_routine().

No network calls and no API keys: the DeepSeek client is replaced with a fake,
and .env.local is never loaded.

Run from the repo root:
    python -m unittest backend/test_routine_generator.py -v
"""

import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))

# Keep the test away from real secrets: routine_generator loads .env.local on import.
import dotenv  # noqa: E402
dotenv.load_dotenv = lambda *args, **kwargs: False

# rag_products imports supabase at module level; only the RetrievedProduct type is needed.
if "supabase" not in sys.modules:
    try:
        import supabase  # noqa: F401
    except ImportError:
        stub = types.ModuleType("supabase")
        stub.create_client = lambda *args, **kwargs: None
        stub.Client = object
        sys.modules["supabase"] = stub

import routine_generator as rg  # noqa: E402
from perfect_corp import SkinAnalysisResult, SkinConcern  # noqa: E402
from rag_products import RetrievedProduct  # noqa: E402


def _product(brand: str, name: str, category: str) -> RetrievedProduct:
    return RetrievedProduct(
        name=name,
        brand=brand,
        category=category,
        content=f"{category} {name}",
        metadata={"ingredients": ["glycerin"]},
        similarity=0.9,
    )


PRODUCTS = [
    _product("CeraVe", "CeraVe Foaming Facial Cleanser", "cleanser"),
    _product("Neutrogena", "Neutrogena Hydro Boost Water Gel", "moisturiser"),
    _product("EltaMD", "EltaMD UV Clear Broad-Spectrum SPF 46", "SPF"),
    _product("The Ordinary", "The Ordinary Niacinamide 10% + Zinc 1%", "serum"),
]

# Mild profile so triage does not short-circuit to referral_response().
SKIN = SkinAnalysisResult(
    skin_type="oily",
    skin_score=0.7,
    concerns=[SkinConcern(name="pore", score=0.3)],
)


def _step(n: int, role: str, product: str) -> dict:
    return {"step": n, "role": role, "product": product, "key_ingredients": ["x"], "reason": "Do it."}


def _fake_client(payload: dict):
    content = json.dumps(payload)

    class _Completions:
        def create(self, **kwargs):
            message = types.SimpleNamespace(content=content)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

    class _Client:
        def __init__(self, *args, **kwargs):
            self.chat = types.SimpleNamespace(completions=_Completions())

    return _Client


def _run(payload, products, avoid=None, skin=SKIN):
    with mock.patch.object(rg, "OpenAI", _fake_client(payload)), \
         mock.patch("builtins.print") as printed:
        output = rg.generate_routine(skin, products, avoid)
    logs = " ".join(str(call.args[0]) for call in printed.call_args_list if call.args)
    return output, logs


class CataloguePostCheckTests(unittest.TestCase):
    def test_all_valid_response_is_unchanged(self):
        payload = {
            "morning_routine": [
                _step(1, "cleanser", "CeraVe Foaming Facial Cleanser"),
                _step(2, "serum", "The Ordinary Niacinamide 10% + Zinc 1%"),
                _step(3, "moisturiser", "Neutrogena Hydro Boost Water Gel"),
                _step(4, "SPF", "EltaMD UV Clear Broad-Spectrum SPF 46"),
            ],
            "evening_routine": [
                _step(1, "cleanser", "CeraVe Foaming Facial Cleanser"),
                _step(2, "moisturiser", "Neutrogena Hydro Boost Water Gel"),
            ],
            "avoid_ingredient": {"ingredient": "coconut oil", "reason": "Can clog pores."},
        }
        output, logs = _run(payload, PRODUCTS)

        self.assertEqual(
            [s.product for s in output.morning_routine],
            [s["product"] for s in payload["morning_routine"]],
        )
        self.assertEqual(
            [s.product for s in output.evening_routine],
            [s["product"] for s in payload["evening_routine"]],
        )
        self.assertNotIn("WARNING", logs)

    def test_invented_products_are_replaced_or_dropped(self):
        payload = {
            "morning_routine": [
                _step(1, "cleanser", "Made Up Miracle Wash"),
                _step(2, "serum", "Imaginary Glow Serum"),
                _step(3, "moisturiser", "Neutrogena Hydro Boost Water Gel"),
                _step(4, "SPF", "Fictional Sun Shield SPF 99"),
            ],
            "evening_routine": [
                _step(1, "cleanser", "CeraVe Foaming Facial Cleanser"),
                _step(2, "moisturiser", "Fake Night Cream"),
            ],
            "avoid_ingredient": None,
        }
        output, logs = _run(payload, PRODUCTS)

        allowed = {rg._product_label(p).lower() for p in PRODUCTS}
        for step in output.morning_routine + output.evening_routine:
            self.assertIn(step.product.lower(), allowed)

        morning = [(s.step, s.role, s.product) for s in output.morning_routine]
        self.assertEqual(morning, [
            (1, "cleanser", "CeraVe Foaming Facial Cleanser"),
            (2, "moisturiser", "Neutrogena Hydro Boost Water Gel"),
            (3, "SPF", "EltaMD UV Clear Broad-Spectrum SPF 46"),
        ])
        self.assertEqual(output.evening_routine[1].product, "Neutrogena Hydro Boost Water Gel")

        for invented in ("Made Up Miracle Wash", "Imaginary Glow Serum", "Fictional Sun Shield SPF 99", "Fake Night Cream"):
            self.assertIn(invented, logs)

    def test_empty_products_uses_named_baseline(self):
        payload = {
            "morning_routine": [_step(1, "cleanser", "Made Up Miracle Wash")],
            "evening_routine": [_step(1, "cleanser", "Made Up Miracle Wash")],
            "avoid_ingredient": None,
        }
        output, logs = _run(payload, [])

        self.assertEqual(
            [s.product for s in output.morning_routine],
            [
                "Cetaphil Gentle Skin Cleanser",
                "La Roche-Posay Toleriane Double Repair Moisturiser",
                "CeraVe Hydrating Mineral Sunscreen SPF 30",
            ],
        )
        self.assertNotIn("Made Up Miracle Wash", [s.product for s in output.evening_routine])
        self.assertIn("No retrieved products", logs)


def _ingredient_product(brand: str, name: str, category: str, ingredients: list[str]) -> RetrievedProduct:
    return RetrievedProduct(
        name=name,
        brand=brand,
        category=category,
        content=f"PRODUCT | {name} | category: {category} | key_ingredients: {', '.join(ingredients)}",
        metadata={"ingredients": ingredients},
        similarity=0.9,
    )


# Severe acne sends generate_routine() down the referral path (no model call).
SEVERE_SKIN = SkinAnalysisResult(
    skin_type="oily",
    skin_score=0.4,
    concerns=[SkinConcern(name="acne", score=0.95)],
)

# The named catalogue trio: Cetaphil cleanser and La Roche-Posay moisturiser both
# contain niacinamide; the CeraVe SPF contains zinc oxide.
EMPTY_PAYLOAD = {"morning_routine": [], "evening_routine": [], "avoid_ingredient": None}


def _products(steps) -> list[str]:
    return [s.product for s in steps]


def _assert_numbered(test: unittest.TestCase, steps) -> None:
    test.assertEqual([s.step for s in steps], list(range(1, len(steps) + 1)))


class AvoidListFallbackTests(unittest.TestCase):
    def test_severe_referral_baseline_respects_avoid_list(self):
        output, _ = _run(EMPTY_PAYLOAD, [], avoid=["niacinamide"], skin=SEVERE_SKIN)

        self.assertTrue(output.referral_concerns)
        # Cleanser and moisturiser have no safe option; only SPF is left.
        self.assertEqual(_products(output.morning_routine), ["CeraVe Hydrating Mineral Sunscreen SPF 30"])
        self.assertEqual(output.evening_routine, [])
        _assert_numbered(self, output.morning_routine)

    def test_severe_referral_prefers_safe_retrieved_product(self):
        products = [
            _ingredient_product("Brand A", "Brand A Scented Cleanser", "cleanser", ["fragrance"]),
            _ingredient_product("Brand B", "Brand B Plain Cleanser", "cleanser", ["glycerin"]),
        ]
        output, _ = _run(EMPTY_PAYLOAD, products, avoid=["Fragrance"], skin=SEVERE_SKIN)

        self.assertEqual(output.morning_routine[0].product, "Brand B Plain Cleanser")
        for step in output.morning_routine + output.evening_routine:
            self.assertNotIn("Scented", step.product)

    def test_enforce_catalogue_baseline_respects_avoid_list(self):
        products = [
            _ingredient_product("Brand A", "Brand A Scented Cleanser", "cleanser", ["fragrance"]),
            _ingredient_product("Brand C", "Brand C Gel Moisturiser", "moisturiser", ["glycerin"]),
        ]
        payload = {
            "morning_routine": [
                _step(1, "cleanser", "Made Up Miracle Wash"),
                _step(2, "moisturiser", "Brand C Gel Moisturiser"),
            ],
            "evening_routine": [
                # Retrieved, but it matches the avoid list, so it must not survive.
                _step(1, "cleanser", "Brand A Scented Cleanser"),
            ],
            "avoid_ingredient": None,
        }
        output, logs = _run(payload, products, avoid=["fragrance"])

        # Retrieved cleanser is avoided, so the catalogue Cetaphil is used instead.
        self.assertEqual(
            _products(output.morning_routine),
            ["Cetaphil Gentle Skin Cleanser", "Brand C Gel Moisturiser"],
        )
        self.assertEqual(_products(output.evening_routine), ["Cetaphil Gentle Skin Cleanser"])
        self.assertIn("Made Up Miracle Wash", logs)

    def test_enforce_catalogue_omits_role_with_no_safe_baseline(self):
        products = [
            _ingredient_product("Brand A", "Brand A Scented Cleanser", "cleanser", ["fragrance"]),
            _ingredient_product("Brand C", "Brand C Gel Moisturiser", "moisturiser", ["glycerin"]),
        ]
        payload = {
            "morning_routine": [
                _step(1, "cleanser", "Made Up Miracle Wash"),
                _step(2, "moisturiser", "Brand C Gel Moisturiser"),
            ],
            "evening_routine": [],
            "avoid_ingredient": None,
        }
        # "panthenol" rules out the Cetaphil catalogue cleanser too.
        output, _ = _run(payload, products, avoid=["fragrance", "panthenol"])

        self.assertEqual(_products(output.morning_routine), ["Brand C Gel Moisturiser"])
        _assert_numbered(self, output.morning_routine)

    def test_empty_products_baseline_respects_avoid_list(self):
        output, _ = _run(EMPTY_PAYLOAD, [], avoid=["zinc oxide"])

        self.assertEqual(
            _products(output.morning_routine),
            ["Cetaphil Gentle Skin Cleanser", "La Roche-Posay Toleriane Double Repair Moisturiser"],
        )
        self.assertEqual(len(output.evening_routine), 2)
        _assert_numbered(self, output.morning_routine)


class MalformedAvoidIngredientTests(unittest.TestCase):
    def _avoid(self, value):
        payload = {
            "morning_routine": [_step(1, "cleanser", "CeraVe Foaming Facial Cleanser")],
            "evening_routine": [],
            "avoid_ingredient": value,
        }
        output, _ = _run(payload, PRODUCTS)
        return output.avoid_ingredient

    def test_dict_is_accepted(self):
        avoid = self._avoid({"ingredient": "coconut oil", "reason": "Can clog pores."})
        self.assertEqual((avoid.ingredient, avoid.reason), ("coconut oil", "Can clog pores."))

    def test_string_is_accepted(self):
        avoid = self._avoid("alcohol denat.")
        self.assertEqual((avoid.ingredient, avoid.reason), ("alcohol denat.", ""))

    def test_malformed_values_do_not_raise(self):
        for value in (42, ["fragrance"], {"ingredient": None}, {"ingredient": 7, "reason": []}, "", None):
            with self.subTest(value=value):
                self.assertIsNone(self._avoid(value))

    def test_dict_with_non_string_reason_keeps_ingredient(self):
        avoid = self._avoid({"ingredient": "fragrance", "reason": {"nested": True}})
        self.assertEqual((avoid.ingredient, avoid.reason), ("fragrance", ""))

    def test_non_object_json_does_not_raise(self):
        output, _ = _run(["not", "an", "object"], PRODUCTS)
        self.assertIsNone(output.avoid_ingredient)
        self.assertTrue(output.morning_routine)


if __name__ == "__main__":
    unittest.main()
