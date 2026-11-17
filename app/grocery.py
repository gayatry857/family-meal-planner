"""Grocery list generation — plain Python, no LLM (per the brief)."""

# A small weekly fruit basket, scaled to the people eating. Individual lines so
# she can add, edit or remove them (app_metadata.json: grocery.fruits).
DEFAULT_FRUITS = ["banana", "apple", "orange", "papaya", "grapes"]
FRUIT_PER_PERSON_PER_WEEK = 5

# Never worth a line on a shopping list.
SKIP_INGREDIENTS = {"water", "hot water", "salted water", "salt", "oil", "cooking oil"}

# The family always has spices, masalas and condiments in the house
# (app_metadata.json: grocery.exclude_from_list).
SPICE_WORDS = (
    # "chili"/"chilli" in any form: green chili is a pantry staple (added
    # separately) and dried/red chili is a condiment the family always has.
    "turmeric", "mustard", "chili", "chilli", "masala", "garam",
    "pepper", "cumin", "coriander powder", "fenugreek", "asafoetida", "hing",
    "cardamom", "cinnamon", "clove", "bay leaf", "star anise", "fennel",
    "spice", "powder", "salt", "sugar", "vinegar", "soy sauce", "ketchup",
    "oil", "ghee", "tamarind", "kudampuli", "kokum", "baking soda", "yeast",
    "curry powder", "rasam powder", "sambar powder", "chaat", "pickle", "papad",
)

# Checked in order — the first match wins, so the most specific groups come
# first. "grains & staples" must beat "vegetables" or "black chickpeas" lands
# under vegetables (it contains "peas") and "kidney beans" under beans.
CATEGORY_KEYWORDS = {
    "grains & staples": [
        "rice", "atta", "wheat", "flour", "rava", "semolina", "oats", "bread",
        "batter", "dal", "parippu", "moong", "chickpea", "kadala", "channa",
        "kidney bean", "rajma", "cowpea", "payar", "lentil", "puttu podi",
        "chapati", "gram", "toor", "urad", "pasta", "noodle", "vermicelli",
        "poha", "millet", "quinoa", "pav", "maida", "sooji", "besan",
    ],
    "nuts & dry fruits": ["cashew", "almond", "badam", "walnut", "pista",
                          "raisin", "dates", "eenthapazham", "chia seeds"],
    "vegetables": [
        "okra", "vendakka", "beetroot", "carrot", "beans", "cabbage", "pumpkin",
        "mathanga", "drumstick", "muringakka", "tomato", "cucumber", "potato",
        "mushroom", "gourd", "kumbalanga", "pavakka", "padavalanga", "yam", "chena",
        "raw banana", "pacha kaya", "plantain", "mango", "manga", "greens", "methi",
        "cheera", "spinach", "capsicum", "peas", "lemon", "mint", "vegetable",
        "coriander",  # fresh leaves; "coriander powder" is filtered as a spice
        "lettuce", "leaves", "brinjal", "cauliflower", "ash gourd", "snake gourd",
        # Checked before "fruits", so these beat the bare "banana" match.
        "banana flower", "vazhakumbu", "raw banana",
    ],
    "fruits": ["banana", "fruit", "apple", "orange", "papaya", "grapes", "pomegranate", "dates"],
    "dairy & eggs": ["yogurt", "curd", "thairu", "buttermilk", "moru", "milk", "paneer", "butter", "egg", "cheese"],
    "fish & meat": ["fish", "meen", "chicken", "kozhi", "prawn", "chemmeen", "mutton", "beef", "meat", "sausage"],
    "store-bought": ["qubus", "hummus", "garlic paste", "pita", "khubz"],
}


def categorize(name: str) -> str:
    n = name.lower()
    for category, words in CATEGORY_KEYWORDS.items():
        if any(w in n for w in words):
            return category
    return "other"


def is_spice(name: str) -> bool:
    """Spices/masalas/condiments are excluded from the list entirely."""
    n = name.lower()
    return any(w in n for w in SPICE_WORDS)


def _matches_staple(ingredient: str, staples: list[str]) -> bool:
    n = ingredient.lower()
    return any(s.lower() in n for s in staples)


def _note_dish(index: dict[str, list[str]], key: str, dish: str) -> None:
    """Record that `dish` needs this ingredient, without repeating a dish that
    appears on several days."""
    dishes = index.setdefault(key, [])
    if dish not in dishes:
        dishes.append(dish)


def build_grocery_list(menu: dict, recipes: dict[int, dict],
                       pantry_staples: list[str]) -> list[dict]:
    """Menu ingredients + weekly pantry staples + individual fruit + store-bought
    items for planned dishes. Spices and condiments are left out entirely.

    Every line starts unticked; she ticks off what she already has or has bought.
    """
    display: dict[str, str] = {}
    store_bought: dict[str, str] = {}
    # ingredient -> the dishes on the menu that need it, so she can check why
    # something is on the list before crossing it off.
    used_in: dict[str, list[str]] = {}
    sb_used_in: dict[str, list[str]] = {}

    for item in menu["items"]:
        recipe = recipes.get(item["recipe_id"])
        if not recipe:
            continue
        # Store-bought dishes are bought as-is, not cooked from ingredients.
        if recipe.get("store_bought"):
            key = recipe["name"].lower()
            store_bought.setdefault(key, recipe["name"])
            _note_dish(sb_used_in, key, f'{recipe["name"]} ({item["day"]} {item["meal_type"]})')
            continue
        for ing in recipe["ingredients"]:
            key = ing.lower().strip().split(" (")[0].strip()
            if not key or key in SKIP_INGREDIENTS or is_spice(key):
                continue
            if _matches_staple(key, pantry_staples):
                continue  # covered by the staples section below
            display.setdefault(key, ing.strip().split(" (")[0].strip() or ing.strip())
            _note_dish(used_in, key, recipe["name"])

    out = []
    for key in sorted(display):
        name = display[key]
        out.append({
            "ingredient_name": name,
            "quantity": len(used_in[key]),
            "unit": "dishes",
            "category": categorize(name),
            "source": "menu",
            "have_already": False,
            "used_in": used_in[key],
        })

    # Store-bought items, one line each, only when their dish is on the menu.
    # They sit in their natural aisle (Banana under fruit, Qubus under
    # store-bought) rather than all being lumped together. Skip any that a
    # recipe already put on the list, so "Banana" never appears twice.
    listed = {o["ingredient_name"].lower() for o in out}
    for key, name in sorted(store_bought.items()):
        if key in listed:
            continue
        listed.add(key)
        out.append({
            "used_in": sb_used_in.get(key, []),
            "ingredient_name": name,
            "quantity": 1,
            "unit": "pack",
            "category": categorize(name),
            "source": "store_bought",
            "have_already": False,
        })

    # Weekly pantry staples — always on the list; she unticks what she still has.
    for staple in pantry_staples:
        out.append({
            "ingredient_name": staple,
            "quantity": 1,
            "unit": "week",
            "category": "pantry staples",
            "source": "staple",
            "have_already": False,
        })

    # Fruit as individual, editable lines (never one lumped "fruits" row).
    people = max(1, len(menu["selected_member_ids"]))
    per_fruit = max(2, round(people * FRUIT_PER_PERSON_PER_WEEK / len(DEFAULT_FRUITS)))
    for fruit in DEFAULT_FRUITS:
        if fruit in {o["ingredient_name"].lower() for o in out}:
            continue
        out.append({
            "ingredient_name": fruit,
            "quantity": per_fruit,
            "unit": "pieces",
            "category": "fruits",
            "source": "fruit",
            "have_already": False,
        })
    return out
