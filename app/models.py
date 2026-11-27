"""Pydantic schemas mirroring the SQLite data model."""

from pydantic import BaseModel


class FamilyMember(BaseModel):
    id: int | None = None
    name: str
    diet: str = "veg"  # veg | non-veg | eggetarian
    health_conditions: str = ""
    likes: str = ""
    dislikes: str = ""
    in_household: bool = False


class Recipe(BaseModel):
    id: int | None = None
    name: str
    cuisine: str = "kerala"
    meal_type: str = "lunch"  # breakfast | lunch | dinner | snack
    prep_minutes: int = 30
    is_quick: bool = False
    diet: str = "veg"
    component: str = ""  # rice_staple | bread_staple | curry | veg_side | pachadi | protein_fry | salad | breakfast_main | breakfast_side | snack
    ingredients: list[str] = []
    steps: str = ""
    tags: list[str] = []
    youtube: str = ""
    source: str = "seed"  # seed | user


class InventoryItem(BaseModel):
    id: int | None = None
    ingredient_name: str
    quantity: float = 0
    unit: str = ""
    category: str = "other"


class Menu(BaseModel):
    id: int | None = None
    week_start_date: str
    selected_member_ids: list[int] = []
    school_tiffins: int = 0
    office_tiffins: int = 0


class MenuItem(BaseModel):
    id: int | None = None
    menu_id: int
    day: str
    meal_type: str
    recipe_id: int | None = None


class FamilyMemberIn(BaseModel):
    """Create/update payload for a family member."""
    name: str
    diet: str = "veg"
    health_conditions: str = ""
    likes: str = ""
    dislikes: str = ""
    in_household: bool = False


class PlanRequest(BaseModel):
    member_ids: list[int]
    cuisine_mix: str = "Kerala / Indian"
    time_crunch: bool = False


class MenuItemIn(BaseModel):
    """Her own pick for an existing slot."""
    recipe_id: int


class MenuItemAddIn(BaseModel):
    """Add a dish to a day/meal. `component` defaults to the recipe's own."""
    recipe_id: int
    day: str
    meal_type: str
    component: str = ""


class RecipeIn(BaseModel):
    """Add-my-recipe form: name + main ingredients minimum, rest optional."""
    name: str
    ingredients: list[str]
    meal_type: str = "lunch"
    diet: str = "veg"
    prep_minutes: int | None = None
    steps: str = ""
    youtube: str = ""
    # Snacks only: how often she has it, and whether it's a healthy one.
    frequency: str = ""          # weekly | monthly | quarterly
    snack_type: str = ""         # healthy | unhealthy


class GroceryItemIn(BaseModel):
    """Add/edit payload for a grocery line."""
    ingredient_name: str
    quantity: float = 1
    unit: str = ""
    category: str = ""


class PdfRequest(BaseModel):
    title: str = "Weekly menu"
    recipient: str = ""
    include_grocery: bool = False


class GroceryItem(BaseModel):
    id: int | None = None
    menu_id: int
    ingredient_name: str
    quantity: float = 0
    unit: str = ""
    category: str = "other"
    source: str = "menu"  # menu | staple | tiffin_fruit
    have_already: bool = False
