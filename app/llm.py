"""Model calls and prompt builders.

The prompts are provider-agnostic: only `_generate_json()` knows which backend
is in use. AI_PROVIDER=gemini (default) or ollama.
"""

import json
import logging
import os
import random

logger = logging.getLogger("mealplanner.llm")

# --- provider config (change the model here) ---------------------------------
AI_PROVIDER = os.environ.get("AI_PROVIDER", "gemini").strip().lower()

# Cheapest current Flash-Lite model (Google AI Studio, checked July 2026).
GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMINI_TEMPERATURE = 0.4

OLLAMA_MODEL = "llama3.1:8b"
# The 8B model on a CPU-only laptop does ~6 tok/s, so a full plan can take
# minutes; this timeout must clear that. Only used when AI_PROVIDER=ollama.
OLLAMA_TIMEOUT_S = 420

MODEL = GEMINI_MODEL if AI_PROVIDER == "gemini" else OLLAMA_MODEL

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MEALS = ["breakfast", "lunch", "snack", "dinner"]

# Slots per meal, in serving order. A meal is a composed plate of these components.
# Lunch has no "extra" slot on purpose - she adds a pachadi or rasam by hand
# when she wants one, the planner never volunteers it.
MEAL_SLOTS = {
    "breakfast": ["breakfast_main", "breakfast_side", "breakfast_protein"],
    "lunch": ["rice_staple", "curry", "veg_side", "protein_fry"],
    "snack": ["snack"],
    "dinner": ["bread_staple", "curry", "protein_fry", "salad", "accompaniment"],
}
# Slots that may be left empty.
OPTIONAL_SLOTS = {"breakfast_side", "protein_fry", "accompaniment"}
# Breakfast mains that are complete on their own (no side needed).
STANDALONE_MAINS = {"breakfast smoothie", "oats upma", "chapati rolls with healthy filling"}
GRILLED_CHICKEN = "grilled chicken"


# --- provider plumbing -------------------------------------------------------

_gemini_client = None


def _get_gemini_client():
    """Lazily build the Gemini client so a missing key is a clear error, not
    an import crash. The key only ever comes from the environment/.env."""
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Put your key in the .env file "
                "next to run.bat, as GEMINI_API_KEY=your-key-here."
            )
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def _generate_json_gemini(prompt: str, max_output_tokens: int, temperature: float) -> str:
    from google.genai import types
    resp = _get_gemini_client().models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        ),
    )
    return resp.text or ""


def _generate_json_ollama(prompt: str, max_output_tokens: int, temperature: float) -> str:
    import ollama
    resp = ollama.Client(timeout=OLLAMA_TIMEOUT_S).chat(
        model=OLLAMA_MODEL,
        messages=[{"role": "user", "content": prompt}],
        format="json",
        options={"temperature": temperature, "num_predict": max_output_tokens},
    )
    return resp["message"]["content"]


def _generate_json(prompt: str, max_output_tokens: int, temperature: float) -> str:
    """One model call returning raw JSON text. The only provider-aware code."""
    if AI_PROVIDER == "ollama":
        return _generate_json_ollama(prompt, max_output_tokens, temperature)
    return _generate_json_gemini(prompt, max_output_tokens, temperature)


def check_ai() -> dict:
    """Confirm the configured backend is usable, with a tiny real call."""
    if AI_PROVIDER == "ollama":
        try:
            import ollama
            result = ollama.list()
            models = [m.get("model") or m.get("name") or "" for m in result.get("models", [])]
            ready = any(name.startswith(OLLAMA_MODEL) for name in models)
            return {"provider": "ollama", "model": OLLAMA_MODEL, "reachable": True,
                    "model_ready": ready,
                    "detail": None if ready else f"Run: ollama pull {OLLAMA_MODEL}"}
        except Exception as exc:
            logger.exception("Ollama health check failed")
            return {"provider": "ollama", "model": OLLAMA_MODEL, "reachable": False,
                    "model_ready": False, "detail": f"Ollama not responding: {exc}"}

    if not os.environ.get("GEMINI_API_KEY", "").strip():
        return {"provider": "gemini", "model": GEMINI_MODEL, "reachable": False,
                "model_ready": False,
                "detail": "No API key yet. Paste your key into the .env file "
                          "after GEMINI_API_KEY= and restart the app."}
    try:
        raw = _generate_json_gemini('Reply with {"ok": true}', max_output_tokens=32,
                                    temperature=0)
        _parse_json(raw)
        return {"provider": "gemini", "model": GEMINI_MODEL, "reachable": True,
                "model_ready": True, "detail": None}
    except Exception as exc:
        logger.exception("Gemini health check failed")
        return {"provider": "gemini", "model": GEMINI_MODEL, "reachable": False,
                "model_ready": False, "detail": f"Gemini API error: {exc}"}


# ---------- eligibility filters (Python safety net, mirrored in the prompt) ----------

def _allowed_diets(members: list[dict]) -> set[str]:
    """Strictest diet among the selected members wins."""
    diets = {m["diet"] for m in members} or {"non-veg"}
    if "veg" in diets:
        return {"veg"}
    if "eggetarian" in diets:
        return {"veg", "eggetarian"}
    return {"veg", "eggetarian", "non-veg"}


def _recipe_diets(recipe: dict) -> set[str]:
    """`diet` is an array in the data (e.g. ["eggetarian", "non-veg"])."""
    value = recipe.get("diet")
    if isinstance(value, list):
        return {str(v).lower() for v in value}
    return {str(value).lower()} if value else {"veg"}


def _egg_only(recipe: dict) -> bool:
    """Non-veg recipe whose only animal ingredient is egg (fine for eggetarians)."""
    text = " ".join(recipe["ingredients"]).lower()
    has_egg = "egg" in text
    has_meat = any(w in text for w in ("chicken", "fish", "mutton", "beef", "prawn", "meat"))
    return has_egg and not has_meat


# Structured conditions (section B): label fragment -> hard rule for the prompt.
CONDITION_RULES = {
    "diabet": "smaller rice portions, more vegetables, no sugary items, prefer millets/whole grains",
    "cholest": "prefer grilled/steamed over fried, limit fish-fry frequency and oil, limit red meat",
    "blood pressure": "low salt, limit pickles, papad and processed food",
    "thyroid": "balanced meals, avoid excess goitrogenic vegetables",
    "heart": "low oil, low salt, prefer grilled or steamed, limit red meat and fried food",
    "acidity": "milder spice, limit very oily or very sour dishes",
    "gerd": "milder spice, limit very oily or very sour dishes",
    "lactose": "no dairy: no curd, yogurt, buttermilk, milk or paneer dishes",
    "gluten": "no wheat: no chapati, paratha, puri, bread or semolina; use rice or millet staples",
    "nut allergy": "absolutely no nuts, nut pastes or nut garnishes",
    "pcos": "lower refined carbs, more protein and fiber",
}

# Conditions that also hard-exclude recipes in Python (not just the prompt).
_DAIRY_WORDS = ("yogurt", "curd", "buttermilk", "milk", "paneer", "thair", "moru")
# "atta" deliberately absent: it substring-matches "matta" rice. "wheat" covers it.
_GLUTEN_WORDS = ("wheat", "chapati", "paratha", "puri", "bread", "rava", "semolina", "maida")
_NUT_TOKENS = {"nut", "nuts", "peanut", "peanuts", "cashew", "cashews",
               "almond", "almonds", "walnut", "walnuts", "pista", "pistachio"}


def _recipe_text(recipe: dict) -> str:
    return (recipe["name"] + " " + " ".join(recipe["ingredients"])).lower()


def condition_rules_text(members: list[dict]) -> str:
    """One line of mapped hard rules per condition present, for the prompt."""
    conditions = " ".join(m["health_conditions"].lower() for m in members)
    lines = []
    for fragment, rule in CONDITION_RULES.items():
        if fragment in conditions and rule not in lines:
            lines.append(rule)
    return "; ".join(lines)


def recipe_eligible(recipe: dict, members: list[dict], time_crunch: bool,
                    rules: "Rules | None" = None) -> bool:
    if time_crunch and recipe["prep_minutes"] > 20:
        return False
    if rules is not None and recipe["name"].lower() in rules.avoid_dishes:
        return False
    allowed = _allowed_diets(members)
    diets = _recipe_diets(recipe)
    if not (diets & allowed):
        if not ("eggetarian" in allowed and _egg_only(recipe)):
            return False
    text = _recipe_text(recipe)
    conditions = " ".join(m["health_conditions"].lower() for m in members)
    if "lactose" in conditions:
        dairy_text = text.replace("coconut milk", "")  # coconut milk is not dairy
        if any(w in dairy_text for w in _DAIRY_WORDS):
            return False
    if "gluten" in conditions and any(w in text for w in _GLUTEN_WORDS):
        return False
    if "nut allergy" in conditions:
        tokens = set(text.replace("(", " ").replace(")", " ").replace("/", " ").replace(",", " ").split())
        if tokens & _NUT_TOKENS:
            return False
    # Dislikes are canonical comma-separated phrases ("Bitter Gourd, Fish Curry").
    for m in members:
        for phrase in [p.strip().lower() for p in m["dislikes"].split(",") if len(p.strip()) > 2]:
            if phrase in text:
                return False
    return True


# ---------- meal-composition rules (from app_metadata.json) ----------

class Rules:
    """The rule config, in one place. Everything comes from app_metadata.json
    so the family can edit rules without touching code."""

    def __init__(self, settings: dict):
        # Ingredient-keyword conflicts, e.g. ["fish", "curd"].
        self.pairs: list[list[str]] = settings.get("incompatible_pairs") or []
        # Dish-name conflicts the keyword rule can't catch, e.g. Fish Curry + Fish Fry.
        self.dish_pairs: list[list[str]] = settings.get("incompatible_dish_pairs") or []
        # [{"dish": "Idli", "must_include_one_of": ["Sambar"]}] — a dish needs a
        # partner *added to its plate* (breakfast main -> its side).
        self.required_pairings: list[dict] = settings.get("required_pairings") or []
        # [{"dish": "Qubus", "must_include_one_of": [...]}] — a dish may only be
        # used at all when one of these is already in the meal.
        self.requires_in_meal: list[dict] = settings.get("requires_in_meal") or []
        # Dishes the family would rather not eat at all.
        self.avoid_dishes = {n.lower() for n in (settings.get("avoid_dishes") or [])}
        # A dish that defines its whole plate (grilled chicken -> qubus + hummus,
        # no curry; parathas -> plain curd, no curry).
        self.plate_rules: list[dict] = settings.get("plate_rules") or []
        # Breakfasts whose batter ferments overnight.
        self.batter_dishes = {n.lower() for n in (settings.get("batter_dishes") or [])}
        # A curry built on one of these IS the meal's protein - no fry needed.
        self.protein_curry_keywords: list[str] = settings.get("protein_curry_keywords") or []
        rules = settings.get("rules") or {}
        self.prefer_repetition: bool = bool(rules.get("prefer_repetition"))
        placement = rules.get("placement") or {}
        self.rice_only = {n.lower() for n in placement.get("rice_only", [])}
        self.dinner_only = {n.lower() for n in placement.get("dinner_only_not_lunch", [])}
        self.not_at_lunch = {n.lower() for n in placement.get("not_at_lunch", [])}
        self.chicken_only_days = placement.get("chicken_only_days") or []
        self.no_consecutive_days = {n.lower() for n in placement.get("no_consecutive_days", [])}
        self.grilled_accompaniments = placement.get("grilled_chicken_accompaniments", [])

    def partners_for(self, dish_name: str) -> list[str] | None:
        """Required partners for a dish, or None when it has no rule."""
        for rule in self.required_pairings:
            if rule.get("dish", "").lower() == dish_name.lower():
                return rule.get("must_include_one_of") or []
        return None

    def gatekeepers_for(self, dish_name: str) -> list[str] | None:
        """Dishes that must already be in the meal for this dish to be allowed."""
        for rule in self.requires_in_meal:
            if rule.get("dish", "").lower() == dish_name.lower():
                return rule.get("must_include_one_of") or []
        return None


def allowed_with(recipe: dict, meal_recipes: list[dict], rules: Rules) -> bool:
    """False when a dish needs a partner in the meal that isn't there
    (e.g. Qubus only ever accompanies grilled chicken or grilled fish)."""
    required = rules.gatekeepers_for(recipe["name"])
    if not required:
        return True
    present = {r["name"].lower() for r in meal_recipes if r["id"] != recipe["id"]}
    return any(w.lower() in present for w in required)


def plate_rule_for(meal_recipes: list[dict], rules: Rules) -> dict | None:
    """The plate rule triggered by a dish already on this plate, if any."""
    names = {r["name"].lower() for r in meal_recipes}
    for rule in rules.plate_rules:
        if rule.get("when_dish", "").lower() in names:
            return rule
    return None


def is_batter_dish(recipe: dict, rules: Rules) -> bool:
    return recipe["name"].lower() in rules.batter_dishes


def _matches_keyword(recipe: dict, keyword: str) -> bool:
    return keyword.lower() in _recipe_text(recipe)


def conflicts_with(recipe: dict, others: list[dict], rules: Rules) -> bool:
    """True if recipe cannot share a meal with any already-placed dish."""
    name = recipe["name"].lower()
    for other in others:
        other_name = other["name"].lower()
        # Dish-name level conflicts (Fish Curry + Fish Fry, Sambar + Avial).
        for a, b in rules.dish_pairs:
            if {name, other_name} == {a.lower(), b.lower()}:
                return True
        # Ingredient/keyword level conflicts (fish + curd, prawns + bitter gourd).
        for a, b in rules.pairs:
            if _matches_keyword(recipe, a) and _matches_keyword(other, b):
                return True
            if _matches_keyword(recipe, b) and _matches_keyword(other, a):
                return True
    return False


def satisfies_pairing(main: dict, partners: list[dict], rules: Rules) -> bool:
    """True if a dish's required-pairing rule is met by what's on the plate."""
    required = rules.partners_for(main["name"])
    if not required:
        return True
    for want in required:
        if want.lower() == "any curry":
            if any(p["component"] == "curry" for p in partners):
                return True
        elif any(p["name"].lower() == want.lower() for p in partners):
            return True
    return False


def pairing_options(main: dict, pool: list[dict], rules: Rules) -> list[dict]:
    """Recipes from pool that satisfy this dish's required pairing."""
    required = rules.partners_for(main["name"])
    if not required:
        return pool
    wants_any_curry = any(w.lower() == "any curry" for w in required)
    names = {w.lower() for w in required if w.lower() != "any curry"}
    return [r for r in pool
            if r["name"].lower() in names or (wants_any_curry and r["component"] == "curry")]


def is_protein_curry(recipe: dict, rules: Rules) -> bool:
    """A fish/chicken/egg curry counts as that meal's protein on its own."""
    if recipe["component"] != "curry":
        return False
    return any(k.lower() in _recipe_text(recipe) for k in rules.protein_curry_keywords)


def is_rice_only(name: str, rules: Rules) -> bool:
    """Whether a dish is one of the thin curries only ever poured over rice.

    Matched on the phrase rather than the exact name, so a dish she adds later
    as "Tomato Rasam" is still kept away from the bread meals.
    """
    return any(r == name or r in name for r in rules.rice_only)


def allowed_at(recipe: dict, meal: str, day: str, rules: Rules) -> bool:
    """Placement rules: where a dish may and may not appear."""
    name = recipe["name"].lower()
    # Lunch is the rice meal; dinner is bread and breakfast is neither.
    if is_rice_only(name, rules) and meal != "lunch":
        return False
    if name in rules.dinner_only and meal != "dinner":
        return False
    if name in rules.not_at_lunch and meal == "lunch":
        return False
    # Chicken is a weekend food in this house.
    if rules.chicken_only_days and "chicken" in _recipe_text(recipe):
        if day not in rules.chicken_only_days:
            return False
    if name == GRILLED_CHICKEN and not (meal == "dinner" and day in ("Friday", "Saturday")):
        return False
    return True


def _rules_prompt_lines(rules: Rules) -> str:
    lines = []
    for a, b in rules.dish_pairs:
        lines.append(f"- NEVER serve {a} and {b} in the same meal.")
    seen = set()
    for a, b in rules.pairs:
        if (a, b) not in seen:
            seen.add((a, b))
            lines.append(f"- NEVER serve a dish containing {a} with a dish containing {b}.")
    for rule in rules.required_pairings:
        wants = " or ".join(rule.get("must_include_one_of", []))
        lines.append(f"- {rule['dish']} must be served with {wants}.")
    for rule in rules.requires_in_meal:
        wants = " or ".join(rule.get("must_include_one_of", []))
        lines.append(f"- ONLY use {rule['dish']} in a meal that has {wants}. "
                     f"Never serve {rule['dish']} with Indian or Kerala dishes.")
    if rules.rice_only:
        lines.append(
            f"- These are poured over rice and belong at lunch only: "
            f"{', '.join(sorted(rules.rice_only))}. NEVER serve any of them at "
            f"dinner or with a bread (Chapati, Puri, Qubus, Wheat Bread, Pasta, "
            f"any paratha).")
    if rules.dinner_only:
        lines.append(f"- These are dinner dishes, never lunch: {', '.join(sorted(rules.dinner_only))}.")
    if rules.not_at_lunch:
        lines.append(f"- Never at lunch: {', '.join(sorted(rules.not_at_lunch))}.")
    if rules.chicken_only_days:
        lines.append(f"- Chicken dishes ONLY on {', '.join(rules.chicken_only_days)} - "
                     "never on a weekday.")
    if rules.no_consecutive_days:
        lines.append(f"- Never on two days in a row: {', '.join(sorted(rules.no_consecutive_days))}.")
    if rules.avoid_dishes:
        lines.append(f"- The family avoids these dishes, never use them: "
                     f"{', '.join(sorted(rules.avoid_dishes))}.")
    lines.append("- If the curry is a fish, chicken or egg curry, that IS the meal's protein: "
                 "leave the protein_fry slot out of that meal.")
    lines.append("- Grilled Chicken: ONLY Friday or Saturday dinner.")
    for rule in rules.plate_rules:
        parts = []
        if rule.get("bread_staple"):
            parts.append(f"the bread must be {rule['bread_staple']}")
        if rule.get("accompaniment_one_of"):
            parts.append("serve it with " + " or ".join(rule["accompaniment_one_of"]))
        if rule.get("no_curry"):
            parts.append("leave the curry slot out entirely - NO curry on that plate")
        if parts:
            lines.append(f"- When the meal has {rule['when_dish']}: " + "; ".join(parts) + ".")
    if rules.batter_dishes:
        names = ", ".join(sorted(d.title() for d in rules.batter_dishes))
        lines.append(f"- Batter breakfasts ({names}) ferment overnight. Serve the SAME one "
                     "on two days running (one batter, two mornings; the side may change). "
                     "NEVER put two different batter dishes on consecutive days.")
    if rules.prefer_repetition:
        lines.append("- This family REPEATS dishes through the week (batch cooking). "
                     "Do NOT force variety; the same curry may appear on several days, "
                     "and a lunch curry may be that day's dinner curry too.")
    return "\n".join(lines)


def fills_slot(recipe: dict, slot: str) -> bool:
    """A dish's own component, plus any extra slots it can stand in for
    (Chia Seeds Pudding is a breakfast protein but also works as a side)."""
    return recipe["component"] == slot or slot in (recipe.get("also_components") or [])


def slot_pool(slot: str, recipes: list[dict]) -> list[dict]:
    """Recipes that can fill a given slot."""
    if slot == "breakfast_side":
        # Breakfast partners include curries (Idli+Sambar, Puttu+Kadala Curry).
        return [r for r in recipes
                if fills_slot(r, "breakfast_side") or r["component"] == "curry"]
    return [r for r in recipes if fills_slot(r, slot)]


# ---------- prompt building ----------

def _profile_context(members: list[dict]) -> str:
    lines = []
    for m in members:
        parts = [f"- {m['name']}: diet={m['diet']}"]  # member diet is a plain string
        if m["health_conditions"]:
            parts.append(f"health conditions: {m['health_conditions']} (HARD CONSTRAINT)")
        if m["likes"]:
            parts.append(f"likes: {m['likes']}")
        if m["dislikes"]:
            parts.append(f"dislikes: {m['dislikes']}")
        lines.append("; ".join(parts))
    return "\n".join(lines) if lines else "- (no profiles selected)"


def _component_catalog(eligible: list[dict]) -> str:
    slots = ["rice_staple", "bread_staple", "curry", "veg_side", "pachadi",
             "protein_fry", "salad", "accompaniment", "breakfast_main", "breakfast_side"]
    lines = []
    for slot in slots:
        pool = [r for r in eligible if r["component"] == slot]
        if pool:
            names = " | ".join(
                f"{r['name']} ({r['prep_minutes']}m, {'/'.join(_recipe_diets(r))})" for r in pool
            )
            lines.append(f"{slot}: {names}")
    return "\n".join(lines)


def _grounding(aliases: dict, english_to_manglish: dict) -> str:
    return (
        "Manglish glossary (dish/ingredient terms):\n"
        + "\n".join(f"- {k} = {v}" for k, v in aliases.items())
        + "\n\nEnglish -> Manglish ingredient map:\n"
        + "\n".join(f"- {k} -> {v}" for k, v in english_to_manglish.items())
    )


def _match_in_pool(name, pool: list[dict]) -> dict | None:
    """Resolve a model-returned dish name within a slot's pool, forgivingly."""
    if not name or not isinstance(name, str):
        return None
    n = name.strip().lower()
    for r in pool:
        if r["name"].lower() == n:
            return r
    for r in pool:
        if n in r["name"].lower() or r["name"].lower() in n:
            return r
    return None


STRICT_SUFFIX = (
    "\n\nIMPORTANT: Your previous reply was not valid JSON. "
    "Return ONLY the JSON object - no explanations, no code fences, no extra text."
)


def _parse_json(raw: str) -> dict:
    """Parse model output defensively: strip code fences, extract the {...} block."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text.lstrip("`")
        text = text.removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


def _chat_json(prompt: str, num_predict: int, temperature: float) -> dict:
    """One model call, JSON in and JSON out. `num_predict` caps the output —
    on Ollama it also stops llama3.1's whitespace loops."""
    logger.info("%s call (%s): prompt %d chars, max tokens %d",
                AI_PROVIDER, MODEL, len(prompt), num_predict)
    raw = _generate_json(prompt, max_output_tokens=num_predict, temperature=temperature)
    logger.info("%s raw response (%d chars): %s", AI_PROVIDER, len(raw), raw[:1500])
    return _parse_json(raw)


def _chat_json_with_retry(prompt: str, num_predict: int, validate) -> tuple[dict | None, str | None]:
    """Two attempts: normal, then a stricter instruction at low temperature.
    Returns (parsed, error_message). Every failure is logged, never swallowed."""
    base_temp = GEMINI_TEMPERATURE if AI_PROVIDER == "gemini" else 0.6
    last_error: str | None = None
    for attempt in (1, 2):
        p = prompt if attempt == 1 else prompt + STRICT_SUFFIX
        try:
            candidate = _chat_json(p, num_predict, temperature=base_temp if attempt == 1 else 0.2)
            if validate(candidate):
                return candidate, None
            last_error = "The AI replied in an unexpected format."
            logger.warning("LLM attempt %d returned JSON with unexpected shape: %s",
                           attempt, str(candidate)[:300])
        except Exception as exc:
            last_error = str(exc)
            logger.exception("LLM attempt %d failed", attempt)
    return None, last_error


# ---------- weekly plan ----------

def plan_week(members: list[dict], recipes: list[dict], aliases: dict,
              english_to_manglish: dict, rules: Rules,
              cuisine_mix: str, time_crunch: bool,
              allow_ai: bool = True, skip_reason: str = "") -> dict:
    """Returns {"days": [{"day", "meals": {meal: {slot: recipe_id}}}], "source": "llm"|"fallback"}."""
    eligible = [r for r in recipes if recipe_eligible(r, members, time_crunch, rules)]
    if not eligible:
        eligible = recipes  # never leave the week empty

    pools = {slot: slot_pool(slot, eligible)
             for slots in MEAL_SLOTS.values() for slot in slots}
    non_veg_ok = any(pools["protein_fry"])
    # Tolerant match: conditions are free text ("Cholestrol", "high cholesterol", ...).
    has_cholesterol = any("cholest" in m["health_conditions"].lower() for m in members)

    conditions = "; ".join(
        f"{m['name']}: {m['health_conditions']}" for m in members if m["health_conditions"]
    ) or "none"
    mapped_rules = condition_rules_text(members)

    protein_rule = (
        "- protein_fry: Fish Fry is the staple on most lunch days."
        + (" But cholesterol is present: use Fish Fry at most 3 times in the whole week, keep oil low." if has_cholesterol else "")
        if non_veg_ok else
        "- This family is vegetarian: leave out every protein_fry slot."
    )

    prompt = f"""You are planning a 7-day menu for a Kerala family. Every meal is a composed plate made of components, not a single dish.

WHO IS EATING ({len(members)} people — scale servings to this number):
{_profile_context(members)}

MEAL TEMPLATES (fill each slot with one dish from the matching component list below):
- breakfast: breakfast_main + breakfast_side (a chutney, a banana, or a curry such as Sambar or Kadala Curry) + breakfast_protein (boiled eggs, omelette, chia seeds pudding or boiled lentils).
- lunch: rice_staple (always Plain Rice) + curry + veg_side + protein_fry. Nothing else - no pachadi or rasam unless the family adds one themselves.
- snack: one snack, eaten between lunch and dinner.
- dinner: bread_staple + curry + protein_fry + Mixed Salad. NEVER rice at dinner.

HARD RULES:
- Health conditions are hard constraints: {conditions}.
  {"Apply these dietary rules: " + mapped_rules + "." if mapped_rules else ""}
- Honor each person's likes and dislikes.
- Cuisine mix: {cuisine_mix}.
- {"TIME CRUNCH: every component must take 20 minutes or less." if time_crunch else "Normal cooking time is fine."}
{protein_rule}
{_rules_prompt_lines(rules)}
- Use ONLY dish names from the component lists below, spelled exactly.

AVAILABLE DISHES BY COMPONENT:
{_component_catalog(eligible)}

{_grounding(aliases, english_to_manglish)}

Return ONLY valid JSON, all 7 days Monday to Sunday, exactly this shape (omit optional slots you leave out):
{{"days": [{{"day": "Monday",
  "breakfast": {{"breakfast_main": "...", "breakfast_side": "...", "breakfast_protein": "..."}},
  "lunch": {{"rice_staple": "Plain Rice", "curry": "...", "veg_side": "...", "protein_fry": "..."}},
  "snack": {{"snack": "..."}},
  "dinner": {{"bread_staple": "...", "curry": "...", "protein_fry": "...", "salad": "Mixed Salad"}}}}]}}"""

    source = "llm"
    if allow_ai:
        parsed, ai_error = _chat_json_with_retry(
            prompt, num_predict=4096,
            validate=lambda c: isinstance(c.get("days"), list) and bool(c["days"]),
        )
    else:  # e.g. the public demo's daily AI limit was reached
        parsed, ai_error = None, skip_reason
    if parsed is None:
        logger.warning("plan_week: both AI attempts failed, using deterministic fallback")
        source = "fallback"
        parsed = {"days": [{"day": d} for d in DAYS]}

    by_day = {}
    for entry in parsed["days"]:
        if isinstance(entry, dict) and entry.get("day") in DAYS:
            by_day[entry["day"]] = entry

    grilled = _match_in_pool(GRILLED_CHICKEN, pools["protein_fry"])
    # Grilled chicken is a Friday-or-Saturday dinner only, and always comes with
    # Qubus + hummus/garlic paste. Honor whichever of those days the model chose;
    # default to Friday. Deciding up front lets the bread slot become Qubus.
    grilled_days: set[str] = set()
    if grilled:
        for day in ("Friday", "Saturday"):
            dinner = by_day.get(day, {}).get("dinner")
            if isinstance(dinner, dict) and _match_in_pool(
                str(dinner.get("protein_fry", "")), [grilled]
            ):
                grilled_days.add(day)
        if not grilled_days:
            grilled_days = {"Friday"}
        # Never two days running: Friday and Saturday are adjacent, so when the
        # model asks for both, keep one.
        if GRILLED_CHICKEN in rules.no_consecutive_days and len(grilled_days) > 1:
            grilled_days = {sorted(grilled_days, key=DAYS.index)[0]}

    days = []
    fish_fry_count = 0
    # One batter, two mornings: a fermented breakfast repeats the next day, and
    # two *different* batter dishes never fall on consecutive days.
    batter_run: dict | None = None  # {"recipe": dict, "days": int}
    # Dishes used yesterday that must not repeat today (Boiled Eggs, Grilled
    # Chicken). Fish Fry is deliberately absent, so it may run back to back.
    used_yesterday: set[str] = set()

    def is_fish_fry(r: dict) -> bool:
        return r["name"].lower() == "fish fry"

    for day in DAYS:
        entry = by_day.get(day, {})
        meals: dict[str, dict] = {}
        used_today: set[str] = set()
        for meal in MEALS:
            meal_entry = entry.get(meal) if isinstance(entry.get(meal), dict) else {}
            plate: dict[str, int] = {}
            plate_recipes: list[dict] = []
            grilled_meal = (grilled is not None and meal == "dinner" and day in grilled_days)
            if grilled_meal:
                plate_recipes.append(grilled)  # pre-placed so the rest fits around it
            main_dish: dict | None = None

            for slot in MEAL_SLOTS[meal]:
                pool = [r for r in pools[slot] if allowed_at(r, meal, day, rules)]
                # Grilled chicken only ever appears on its planned day, so it can
                # never be served without its Qubus and hummus/garlic paste.
                if not grilled_meal:
                    pool = [r for r in pool if r["name"].lower() != GRILLED_CHICKEN]
                # Dishes that mustn't land two days running.
                pool = [r for r in pool if not (r["name"].lower() in rules.no_consecutive_days
                                                and r["name"].lower() in used_yesterday)] or pool
                if not pool:
                    continue

                others = [r for r in plate_recipes if not (grilled_meal and slot == "protein_fry"
                                                           and r["id"] == grilled["id"])]

                def usable(r: dict) -> bool:
                    return (not conflicts_with(r, others, rules)
                            and allowed_with(r, plate_recipes, rules))

                # Drop dishes whose gatekeeper isn't on this plate (Qubus without
                # grilled chicken/fish). Grilled dishes are pre-placed, so this is
                # decided correctly even though bread is filled first.
                pool = [r for r in pool if allowed_with(r, plate_recipes, rules)]
                if not pool:
                    continue

                # Some dishes define their whole plate: a grilled plate is Qubus +
                # grilled meat + hummus/garlic paste + salad, and a paratha plate
                # is paratha + plain curd. Neither takes a curry.
                plate_rule = plate_rule_for(plate_recipes, rules)
                if slot == "curry" and plate_rule and plate_rule.get("no_curry"):
                    continue

                # The accompaniment slot exists only for plates that call for one
                # (grilled chicken, parathas). Checked before the model's answer is
                # read, so a stray "Garlic Paste" next to an Indian curry is dropped.
                if slot == "accompaniment" and not plate_rule:
                    continue

                # A fish/chicken/egg curry already is the protein for this meal.
                if slot == "protein_fry" and any(
                    is_protein_curry(r, rules) for r in plate_recipes
                ):
                    continue

                # Fermented batter lasts two days: day two must repeat day one's
                # dish, and a different batter dish can't follow it either.
                if slot == "breakfast_main" and batter_run is not None:
                    if batter_run["days"] == 1:
                        pool = [r for r in pool if r["id"] == batter_run["recipe"]["id"]] or pool
                    else:
                        pool = [r for r in pool if not is_batter_dish(r, rules)
                                or r["id"] == batter_run["recipe"]["id"]] or pool

                recipe = _match_in_pool(meal_entry.get(slot), pool)

                # Enforced choices, regardless of what the model said.
                if slot == "rice_staple":
                    recipe = _match_in_pool("plain rice", pool) or recipe
                if slot == "breakfast_main" and batter_run is not None and batter_run["days"] == 1:
                    recipe = batter_run["recipe"]  # second morning of the same batter
                if grilled_meal and slot == "protein_fry":
                    recipe = grilled
                if plate_rule:
                    if slot == "bread_staple" and plate_rule.get("bread_staple"):
                        recipe = _match_in_pool(plate_rule["bread_staple"], pool) or recipe
                    elif slot == "accompaniment" and plate_rule.get("accompaniment_one_of"):
                        recipe = (_first_match(plate_rule["accompaniment_one_of"], pool)
                                  or recipe)

                # A breakfast side must satisfy the main's required pairing.
                pairing_pool = pool
                if slot == "breakfast_side" and main_dish is not None:
                    required = rules.partners_for(main_dish["name"])
                    if required:
                        pairing_pool = pairing_options(main_dish, pool, rules) or pool
                        if recipe is None or not satisfies_pairing(main_dish, [recipe], rules):
                            recipe = None  # force a partner that satisfies the rule

                conflicted = recipe is not None and not usable(recipe)
                if conflicted and not (grilled_meal and slot == "protein_fry"):
                    recipe = None  # replace with a compatible alternative below

                if recipe is None:
                    if slot in OPTIONAL_SLOTS and source == "llm" and not conflicted:
                        # The model left it out - but a required pairing overrides that.
                        if not (slot == "breakfast_side" and main_dish is not None
                                and rules.partners_for(main_dish["name"])):
                            continue
                    if slot in OPTIONAL_SLOTS and source == "fallback" and not (
                        (slot == "protein_fry" and meal == "lunch")
                        or (slot == "breakfast_side" and main_dish is not None
                            and rules.partners_for(main_dish["name"]))
                    ):
                        continue  # fallback keeps optional slots simple
                    options = [r for r in pairing_pool if usable(r)] or [r for r in pool if usable(r)]
                    if not options:
                        if slot in OPTIONAL_SLOTS:
                            continue  # nothing compatible; drop the optional slot
                        options = pool  # required slot: accept the least-bad option
                    if slot == "bread_staple":
                        # Chapati is the everyday bread; others appear when chosen.
                        recipe = _match_in_pool("chapati", options) or random.choice(options)
                    elif slot == "protein_fry" and meal == "lunch":
                        recipe = _match_in_pool("fish fry", options) or random.choice(options)
                    elif slot == "salad":
                        recipe = _match_in_pool("mixed salad", options) or random.choice(options)
                    else:
                        recipe = random.choice(options)
                if recipe is None:
                    continue

                # NOTE: no variety rule here. rules.prefer_repetition is true for
                # this family (batch cooking), so repeats across days are wanted.

                # Cholesterol: cap fish fry across the week at 3.
                if has_cholesterol and is_fish_fry(recipe):
                    if fish_fry_count >= 3:
                        alternatives = [r for r in pool if not is_fish_fry(r) and usable(r)]
                        if slot in OPTIONAL_SLOTS or not alternatives:
                            continue
                        recipe = random.choice(alternatives)
                    else:
                        fish_fry_count += 1
                elif is_fish_fry(recipe):
                    fish_fry_count += 1

                plate[slot] = recipe["id"]
                plate_recipes.append(recipe)
                used_today.add(recipe["name"].lower())
                if slot == "breakfast_main":
                    main_dish = recipe

            # Safety net: if a gatekept dish ended up without its partner (the
            # partner slot was dropped later), replace it with something plain.
            for slot, recipe_id in list(plate.items()):
                placed = next((r for r in plate_recipes if r["id"] == recipe_id), None)
                if placed is None or allowed_with(placed, plate_recipes, rules):
                    continue
                alternatives = [
                    r for r in pools[slot]
                    if allowed_at(r, meal, day, rules) and r["id"] != recipe_id
                    and allowed_with(r, plate_recipes, rules)
                    and not conflicts_with(r, [x for x in plate_recipes if x["id"] != recipe_id], rules)
                ]
                plate_recipes = [r for r in plate_recipes if r["id"] != recipe_id]
                if alternatives:
                    replacement = (_match_in_pool("chapati", alternatives)
                                   or random.choice(alternatives))
                    plate[slot] = replacement["id"]
                    plate_recipes.append(replacement)
                else:
                    del plate[slot]

            # Track the fermented-batter run so tomorrow repeats it.
            if meal == "breakfast":
                served = next((r for r in plate_recipes
                               if r["component"] == "breakfast_main"), None)
                if served is not None and is_batter_dish(served, rules):
                    if batter_run and batter_run["recipe"]["id"] == served["id"]:
                        batter_run["days"] += 1
                    else:
                        batter_run = {"recipe": served, "days": 1}
                else:
                    batter_run = None
            meals[meal] = plate
        days.append({"day": day, "meals": meals})
        used_yesterday = used_today
    return {"days": days, "source": source, "ai_error": ai_error}


def _first_match(names: list[str], pool: list[dict]) -> dict | None:
    """First pool recipe matching any of these names ("Hummus or Garlic Paste")."""
    for entry in names:
        for part in str(entry).split(" or "):
            found = _match_in_pool(part.strip(), pool)
            if found:
                return found
    return None


def pick_swap(current_recipe_id: int | None, slot: str, members: list[dict],
              recipes: list[dict], time_crunch: bool, rules: Rules,
              meal_recipes: list[dict] | None = None,
              meal: str = "", day: str = "") -> dict | None:
    """Instant, no-LLM swap: another eligible recipe for this component slot that
    fits the rest of the meal (conflicts, placement and required pairings)."""
    eligible = [r for r in recipes if recipe_eligible(r, members, time_crunch, rules)]
    pool = [r for r in slot_pool(slot, eligible) if r["id"] != current_recipe_id]
    if meal and day:
        pool = [r for r in pool if allowed_at(r, meal, day, rules)] or pool
    others = meal_recipes or []
    # Never swap in a dish whose partner isn't on the plate (Qubus needs grilled).
    gated = [r for r in pool if allowed_with(r, others + [r], rules)]
    if gated:
        pool = gated
    if others:
        compatible = [r for r in pool if not conflicts_with(r, others, rules)]
        if compatible:
            pool = compatible
        # Swapping a breakfast side must keep the main's required pairing.
        if slot == "breakfast_side":
            main = next((r for r in others if r["component"] == "breakfast_main"), None)
            if main is not None:
                narrowed = pairing_options(main, pool, rules)
                if narrowed:
                    pool = narrowed
    return random.choice(pool) if pool else None


# ---------- healthy snacks (instant, no LLM) ----------


FREQUENCY_LABELS = {
    "weekly": "Every week",
    "monthly": "Once a month",
    "quarterly": "Once in 3 months",
}


def is_snack(recipe: dict) -> bool:
    return (recipe["component"] == "snack" or "snack" in recipe["tags"]
            or recipe["meal_type"] == "snack")


def suggest_snacks(members: list[dict], recipes: list[dict], rules: Rules,
                   kind: str = "") -> dict:
    """Every snack she can have, optionally just the healthy or unhealthy ones.

    Unclassified snacks count as healthy, since that's what the list held
    before the healthy/unhealthy split existed.
    """
    eligible = [r for r in recipes if is_snack(r) and not r.get("store_bought")
                and recipe_eligible(r, members, False, rules)]
    if kind in ("healthy", "unhealthy"):
        eligible = [r for r in eligible
                    if (r.get("snack_type") or "healthy") == kind]
    ranked = sorted(eligible, key=lambda r: (r["prep_minutes"], r["name"]))
    suggestions = []
    for r in ranked:
        bits = [FREQUENCY_LABELS.get(r.get("frequency", ""), "")]
        bits.append(f"{r['prep_minutes']} min" if r["prep_minutes"] else "no cooking")
        suggestions.append({
            "recipe": r,
            "why": " · ".join(b for b in bits if b),
            "missing": [],
        })
    return {"suggestions": suggestions, "source": "instant"}
