"""FastAPI app: serves the API and the static frontend."""

import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

# Load .env (the API key) before anything reads the environment.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, HTTPException, Request, Response  # noqa: E402
from fastapi.responses import HTMLResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from . import db, demo, grocery, llm, pdf  # noqa: E402
from .models import (  # noqa: E402
    FamilyMemberIn, GroceryItemIn, MenuItemAddIn, MenuItemIn, PdfRequest,
    PlanRequest, RecipeIn,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)
logger = logging.getLogger("mealplanner")


def _local_ip() -> str:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # no packets sent; just picks the outbound interface
        return s.getsockname()[0]
    except OSError:
        return socket.gethostbyname(socket.gethostname())
    finally:
        s.close()


def _is_hosted() -> bool:
    """True when running on Azure App Service, which sets WEBSITE_HOSTNAME."""
    return bool(os.environ.get("WEBSITE_HOSTNAME"))


async def _register_mdns():
    """Advertise http://mealplanner.local:8000 on the LAN. Best-effort.
    Must use the async zeroconf API: the sync one blocks the event loop it needs."""
    if _is_hosted():
        # Pointless in the cloud: there is no home network to advertise on.
        return None, None
    try:
        import socket
        from zeroconf import ServiceInfo
        from zeroconf.asyncio import AsyncZeroconf
        ip = _local_ip()
        info = ServiceInfo(
            type_="_http._tcp.local.",
            name="Family Meal Planner._http._tcp.local.",
            addresses=[socket.inet_aton(ip)],
            port=8000,
            server="mealplanner.local.",
        )
        azc = AsyncZeroconf()
        await azc.async_register_service(info)
        logger.info("mDNS: advertising http://mealplanner.local:8000 (%s)", ip)
        return azc, info
    except Exception:
        logger.exception("mDNS registration failed; the IP address still works")
        return None, None


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    if demo.enabled():
        demo.reset_if_new_day()
        logger.info("DEMO MODE: AI limited to %d/day (%d per visitor)",
                    demo.global_limit(), demo.per_visitor_limit())
    status = _ai_status()
    if status["reachable"]:
        logger.info("AI ready: %s (%s)", status["model"], status["provider"])
    else:
        logger.warning("AI NOT ready (%s): %s", status["provider"], status["detail"])
    logger.info("Database: %s", db.DB_PATH)
    azc, info = await _register_mdns()
    yield
    if azc is not None:
        try:
            await azc.async_unregister_service(info)
            await azc.async_close()
        except Exception:
            pass


app = FastAPI(title="Family Meal Planner", lifespan=lifespan)


def _rules() -> llm.Rules:
    """Meal-composition rules, read fresh from settings (editable in app_metadata.json)."""
    return llm.Rules({key: db.get_setting(key) for key in db.METADATA_KEYS})


_health_cache: dict = {"at": 0.0, "status": None}


def _ai_status() -> dict:
    """llm.check_ai() makes a real AI call, so the demo reuses the answer for an
    hour; otherwise refreshing /api/health would be an uncapped way to spend."""
    if not demo.enabled():
        return llm.check_ai()
    if _health_cache["status"] is None or time.time() - _health_cache["at"] > demo.HEALTH_CACHE_SECONDS:
        _health_cache.update(at=time.time(), status=llm.check_ai())
    return _health_cache["status"]


def _client_ip(request: Request) -> str:
    """Azure's proxy appends the real address LAST; earlier entries can be faked."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[-1].strip().rsplit(":", 1)[0]
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def demo_guard(request: Request, call_next):
    if demo.enabled():
        if request.method in ("POST", "PUT"):
            if len(await request.body()) > demo.MAX_BODY_BYTES:
                return Response("That is too much text for the demo.", status_code=413)
        demo.reset_if_new_day()
    return await call_next(request)


@app.get("/api/health")
def health():
    ai_status = _ai_status()
    return {
        "status": "ok" if ai_status["reachable"] else "degraded",
        "database": {
            "path": str(db.DB_PATH),
            "recipes": db.recipe_count(),
            "pantry_staples": len(db.get_setting("pantry_staples") or []),
        },
        "ai": ai_status,
    }


# ---------- family members ----------

@app.get("/api/members")
def get_members():
    return db.list_members()


@app.post("/api/members")
def create_member(member: FamilyMemberIn):
    if demo.enabled() and len(db.list_members()) >= demo.MAX_MEMBERS:
        raise HTTPException(429, "The demo is full; added people are cleared every night.")
    return db.create_member(member.model_dump())


@app.put("/api/members/{member_id}")
def update_member(member_id: int, member: FamilyMemberIn):
    updated = db.update_member(member_id, member.model_dump())
    if updated is None:
        raise HTTPException(404, "Member not found")
    return updated


@app.delete("/api/members/{member_id}")
def delete_member(member_id: int):
    if not db.delete_member(member_id):
        raise HTTPException(404, "Member not found")
    return {"deleted": True}


# Fixed condition list (section B) — single source of truth for the profile form.
HEALTH_CONDITIONS = [
    "Diabetes", "High cholesterol", "High blood pressure", "Thyroid",
    "Heart condition", "Acidity / GERD", "Lactose intolerance",
    "Gluten intolerance", "Nut allergy", "PCOS", "None",
]


def _canonical_ingredients() -> list[str]:
    """Deduplicated Title Case ingredient choices from recipes + the English map."""
    seen: dict[str, str] = {}
    def add(raw: str):
        for part in raw.replace(" or ", "/").split("/"):
            name = part.split("(")[0].strip().lower()
            if len(name) > 2:
                seen.setdefault(name, name.title())
    for r in db.list_recipes():
        for ing in r["ingredients"]:
            add(ing)
    for eng in (db.get_setting("english_to_manglish") or {}).keys():
        add(eng)
    return sorted(seen.values())


@app.get("/api/choices")
def get_choices():
    """Options for the profile form: conditions, dish names, ingredients."""
    return {
        "conditions": HEALTH_CONDITIONS,
        "dishes": sorted(r["name"] for r in db.list_recipes()),
        "ingredients": _canonical_ingredients(),
    }


# ---------- recipes & favorites ----------

@app.get("/api/recipes")
def get_recipes():
    favorites = set(db.list_favorite_ids())
    return [{**r, "favorite": r["id"] in favorites} for r in db.list_recipes()]


@app.get("/api/recipes/{recipe_id}")
def get_recipe(recipe_id: int):
    recipe = db.get_recipe(recipe_id)
    if recipe is None:
        raise HTTPException(404, "Recipe not found")
    recipe["favorite"] = recipe_id in db.list_favorite_ids()
    return recipe


@app.post("/api/recipes")
def create_recipe(r: RecipeIn):
    if demo.enabled() and db.count_user_recipes() >= demo.MAX_USER_RECIPES:
        raise HTTPException(429, "The demo is full of visitor recipes; they are cleared every night.")
    if not r.name.strip():
        raise HTTPException(400, "The recipe needs a name")
    ingredients = [i.strip() for i in r.ingredients if i.strip()]
    if not ingredients:
        raise HTTPException(400, "List at least one main ingredient")
    return db.create_user_recipe({**r.model_dump(), "ingredients": ingredients})


@app.put("/api/recipes/{recipe_id}")
def update_recipe(recipe_id: int, r: RecipeIn):
    existing = db.get_recipe(recipe_id)
    if existing is None:
        raise HTTPException(404, "Recipe not found")
    if existing["source"] != "user":
        raise HTTPException(403, "Only dishes you added yourself can be changed")
    ingredients = [i.strip() for i in r.ingredients if i.strip()]
    if not r.name.strip() or not ingredients:
        raise HTTPException(400, "A dish needs a name and at least one ingredient")
    return db.update_user_recipe(recipe_id, {**r.model_dump(), "ingredients": ingredients})


@app.delete("/api/recipes/{recipe_id}")
def delete_recipe(recipe_id: int):
    existing = db.get_recipe(recipe_id)
    if existing is None:
        raise HTTPException(404, "Recipe not found")
    if existing["source"] != "user":
        raise HTTPException(403, "Only dishes you added yourself can be removed")
    db.delete_user_recipe(recipe_id)
    return {"deleted": True}


@app.post("/api/favorites/{recipe_id}")
def toggle_favorite(recipe_id: int):
    if db.get_recipe(recipe_id) is None:
        raise HTTPException(404, "Recipe not found")
    return {"favorite": db.toggle_favorite(recipe_id)}


@app.get("/api/favorites")
def get_favorites():
    return db.list_favorite_ids()


# ---------- weekly menu ----------

def _menu_response(menu: dict) -> dict:
    recipes = {r["id"]: r for r in db.list_recipes()}
    favorites = set(db.list_favorite_ids())
    grid: dict[str, dict[str, list]] = {d: {m: [] for m in llm.MEALS} for d in llm.DAYS}
    for item in menu["items"]:
        r = recipes.get(item["recipe_id"])
        if r and item["day"] in grid and item["meal_type"] in grid[item["day"]]:
            grid[item["day"]][item["meal_type"]].append(
                {"item_id": item["id"], "component": item["component"],
                 "recipe": {**r, "favorite": r["id"] in favorites}}
            )
    # Serve components in template order.
    for day in grid:
        for meal in grid[day]:
            order = {slot: i for i, slot in enumerate(llm.MEAL_SLOTS[meal])}
            grid[day][meal].sort(key=lambda c: order.get(c["component"], 99))
    return {
        "menu_id": menu["id"],
        "week_start_date": menu["week_start_date"],
        "selected_member_ids": menu["selected_member_ids"],
        "school_tiffins": menu["school_tiffins"],
        "office_tiffins": menu["office_tiffins"],
        "time_crunch": menu["time_crunch"],
        "days": [{"day": d, "meals": grid[d]} for d in llm.DAYS],
    }


@app.post("/api/plan")
def plan_week(req: PlanRequest, request: Request):
    members = db.get_members(req.member_ids)
    if not members:
        raise HTTPException(400, "Select at least one family member")
    allow_ai, skip_reason = True, ""
    if demo.enabled():
        allow_ai, skip_reason = demo.try_use_ai(_client_ip(request))
    plan = llm.plan_week(
        members=members,
        recipes=db.list_recipes(),
        aliases=db.get_setting("aliases") or {},
        english_to_manglish=db.get_setting("english_to_manglish") or {},
        rules=_rules(),
        cuisine_mix=req.cuisine_mix,
        time_crunch=req.time_crunch,
        allow_ai=allow_ai, skip_reason=skip_reason,
    )
    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # this week's Monday
    items = [
        {"day": d["day"], "meal_type": meal, "component": slot, "recipe_id": rid}
        for d in plan["days"]
        for meal, plate in d["meals"].items()
        for slot, rid in plate.items()
    ]
    menu_id = db.save_menu(
        str(week_start), req.member_ids, 0, 0, req.time_crunch, items,
    )
    menu = db.get_latest_menu()
    resp = _menu_response(menu)
    resp["source"] = plan["source"]
    resp["ai_error"] = plan.get("ai_error")  # shown in the UI when the AI failed
    return resp


@app.get("/api/menu/latest")
def latest_menu():
    menu = db.get_latest_menu()
    if menu is None:
        return {"menu_id": None}
    return _menu_response(menu)


def _require_menu(menu_id: int) -> dict:
    menu = db.get_latest_menu()
    if menu is None or menu["id"] != menu_id:
        raise HTTPException(404, "Menu not found")
    return menu


@app.post("/api/menu/{menu_id}/items/{item_id}/swap")
def swap_meal_item(menu_id: int, item_id: int):
    """Let the app pick a different dish for this one slot."""
    menu = _require_menu(menu_id)
    item = db.get_menu_item(menu_id, item_id)
    if item is None:
        raise HTTPException(404, "Dish not found in this menu")
    recipes_by_id = {r["id"]: r for r in db.list_recipes()}
    meal_recipes = [
        recipes_by_id[i["recipe_id"]] for i in menu["items"]
        if i["day"] == item["day"] and i["meal_type"] == item["meal_type"]
        and i["id"] != item_id and i["recipe_id"] in recipes_by_id
    ]
    replacement = llm.pick_swap(
        item["recipe_id"], item["component"], db.get_members(menu["selected_member_ids"]),
        db.list_recipes(), time_crunch=menu["time_crunch"], rules=_rules(),
        meal_recipes=meal_recipes, meal=item["meal_type"], day=item["day"],
    )
    if replacement is None:
        raise HTTPException(409, "No alternative dish available")
    db.set_menu_item_recipe(menu_id, item_id, replacement["id"])
    replacement["favorite"] = replacement["id"] in db.list_favorite_ids()
    return {"item_id": item_id, "component": item["component"], "recipe": replacement}


@app.put("/api/menu/{menu_id}/items/{item_id}")
def choose_meal_item(menu_id: int, item_id: int, req: MenuItemIn):
    """Her own choice for this slot - deliberately not rule-filtered."""
    _require_menu(menu_id)
    if db.get_menu_item(menu_id, item_id) is None:
        raise HTTPException(404, "Dish not found in this menu")
    recipe = db.get_recipe(req.recipe_id)
    if recipe is None:
        raise HTTPException(404, "Recipe not found")
    db.set_menu_item_recipe(menu_id, item_id, req.recipe_id)
    recipe["favorite"] = recipe["id"] in db.list_favorite_ids()
    return {"item_id": item_id, "recipe": recipe}


@app.delete("/api/menu/{menu_id}/items/{item_id}")
def remove_meal_item(menu_id: int, item_id: int):
    _require_menu(menu_id)
    if not db.delete_menu_item(menu_id, item_id):
        raise HTTPException(404, "Dish not found in this menu")
    return {"deleted": True}


@app.post("/api/menu/{menu_id}/items")
def add_meal_item(menu_id: int, req: MenuItemAddIn):
    """Add a dish to any day/meal. A meal may hold several of the same
    component (a second curry, an extra side) - rows are keyed by id."""
    _require_menu(menu_id)
    if req.day not in llm.DAYS:
        raise HTTPException(400, "Unknown day")
    if req.meal_type not in llm.MEALS:
        raise HTTPException(400, "Unknown meal")
    recipe = db.get_recipe(req.recipe_id)
    if recipe is None:
        raise HTTPException(404, "Recipe not found")
    item = db.add_menu_item(menu_id, req.day, req.meal_type,
                            req.component or recipe["component"], req.recipe_id)
    recipe["favorite"] = recipe["id"] in db.list_favorite_ids()
    return {"item_id": item["id"], "day": req.day, "meal_type": req.meal_type,
            "component": item["component"], "recipe": recipe}


# ---------- healthy snacks (instant) ----------

def _household_members() -> list[dict]:
    members = db.list_members()
    return [m for m in members if m["in_household"]] or members


@app.get("/api/snacks")
def snacks(kind: str = ""):
    """kind: "healthy", "unhealthy", or empty for all."""
    result = llm.suggest_snacks(_household_members(), db.list_recipes(), _rules(), kind)
    favorites = set(db.list_favorite_ids())
    for s in result["suggestions"]:
        s["recipe"]["favorite"] = s["recipe"]["id"] in favorites
    return result


# ---------- grocery list ----------

@app.post("/api/menu/{menu_id}/grocery")
def generate_grocery(menu_id: int):
    menu = db.get_latest_menu()
    if menu is None or menu["id"] != menu_id:
        raise HTTPException(404, "Menu not found")
    items = grocery.build_grocery_list(
        menu=menu,
        recipes={r["id"]: r for r in db.list_recipes()},
        pantry_staples=db.get_setting("pantry_staples") or [],
    )
    return {"menu_id": menu_id, "people": len(menu["selected_member_ids"]),
            "items": db.replace_grocery_list(menu_id, items)}


@app.get("/api/menu/{menu_id}/grocery")
def get_grocery(menu_id: int):
    menu = db.get_latest_menu()
    if menu is None or menu["id"] != menu_id:
        raise HTTPException(404, "Menu not found")
    return {"menu_id": menu_id, "people": len(menu["selected_member_ids"]),
            "items": db.get_grocery_list(menu_id)}


@app.post("/api/menu/{menu_id}/pdf")
def export_pdf(menu_id: int, req: PdfRequest):
    menu = db.get_latest_menu()
    if menu is None or menu["id"] != menu_id:
        raise HTTPException(404, "Menu not found")
    grocery_items = db.get_grocery_list(menu_id) if req.include_grocery else None
    if req.include_grocery and not grocery_items:
        grocery_items = grocery.build_grocery_list(
            menu=menu,
            recipes={r["id"]: r for r in db.list_recipes()},
            pantry_staples=db.get_setting("pantry_staples") or [],
        )
        grocery_items = db.replace_grocery_list(menu_id, grocery_items)
    content = pdf.build_menu_pdf(
        _menu_response(menu), title=req.title, recipient=req.recipient,
        grocery_items=grocery_items,
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="weekly-menu.pdf"'},
    )


@app.post("/api/menu/{menu_id}/grocery/pdf")
def export_grocery_pdf(menu_id: int):
    menu = _require_menu(menu_id)
    items = db.get_grocery_list(menu_id)
    if not items:
        items = db.replace_grocery_list(menu_id, grocery.build_grocery_list(
            menu=menu,
            recipes={r["id"]: r for r in db.list_recipes()},
            pantry_staples=db.get_setting("pantry_staples") or [],
        ))
    content = pdf.build_grocery_pdf(
        items, people=len(menu["selected_member_ids"]),
        week_start_date=menu["week_start_date"],
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="grocery-list.pdf"'},
    )


@app.post("/api/grocery/{item_id}/toggle")
def toggle_grocery(item_id: int):
    state = db.toggle_grocery_item(item_id)
    if state is None:
        raise HTTPException(404, "Item not found")
    return {"have_already": state}


@app.post("/api/menu/{menu_id}/grocery/items")
def add_grocery(menu_id: int, item: GroceryItemIn):
    if not item.ingredient_name.strip():
        raise HTTPException(400, "The item needs a name")
    payload = item.model_dump()
    payload["ingredient_name"] = payload["ingredient_name"].strip()
    if not payload["category"]:
        payload["category"] = grocery.categorize(payload["ingredient_name"])
    return db.add_grocery_item(menu_id, payload)


@app.put("/api/grocery/{item_id}")
def update_grocery(item_id: int, item: GroceryItemIn):
    if not item.ingredient_name.strip():
        raise HTTPException(400, "The item needs a name")
    payload = item.model_dump()
    payload["ingredient_name"] = payload["ingredient_name"].strip()
    if not payload["category"]:
        payload["category"] = grocery.categorize(payload["ingredient_name"])
    updated = db.update_grocery_item(item_id, payload)
    if updated is None:
        raise HTTPException(404, "Item not found")
    return updated


@app.delete("/api/grocery/{item_id}")
def delete_grocery(item_id: int):
    if not db.delete_grocery_item(item_id):
        raise HTTPException(404, "Item not found")
    return {"deleted": True}


# ---------- Public demo ----------
# This app used to sit behind a shared PIN because it held one family's health
# details. It is now a portfolio demo seeded with invented people, so there is
# nothing to guard and no login.


@app.get("/api/ping")
def ping():
    """Uptime check for the host."""
    return {"status": "ok"}


class AppFiles(StaticFiles):
    """Serve the frontend, but make the browser revalidate the app itself.

    Without this, a phone keeps running the version it cached the first time
    and never picks up an update. Icons and the manifest may still be cached.
    """

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if path.endswith((".html", ".js", ".css")) or path in ("", "."):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


app.mount("/", AppFiles(directory=STATIC_DIR, html=True), name="static")
