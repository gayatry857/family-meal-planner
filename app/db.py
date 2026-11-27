"""SQLite setup and helpers for the meal planner."""

import json
import os
import sqlite3
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent

# Where the database lives. Locally this is a file next to the code; on Azure
# DB_PATH points at /home/data/meals.db, because only /home survives a restart
# or a redeploy. Everything else in the container is thrown away.
DB_PATH = Path(os.environ.get("DB_PATH") or (APP_DIR / "meals.db"))
SEED_PATH = APP_DIR / "seed" / "recipes.json"
METADATA_PATH = APP_DIR / "seed" / "app_metadata.json"

# Rule/glossary keys mirrored from app_metadata.json into the settings table.
METADATA_KEYS = (
    "english_to_manglish", "pantry_staples", "incompatible_pairs",
    "incompatible_dish_pairs", "required_pairings", "requires_in_meal",
    "avoid_dishes", "protein_curry_keywords", "plate_rules", "batter_dishes",
    "rules", "grocery",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS family_member (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    diet TEXT NOT NULL DEFAULT 'veg',
    health_conditions TEXT NOT NULL DEFAULT '',
    likes TEXT NOT NULL DEFAULT '',
    dislikes TEXT NOT NULL DEFAULT '',
    in_household INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS recipe (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    cuisine TEXT NOT NULL DEFAULT 'kerala',
    meal_type TEXT NOT NULL DEFAULT 'lunch',
    prep_minutes INTEGER NOT NULL DEFAULT 30,
    is_quick INTEGER NOT NULL DEFAULT 0,
    diet TEXT NOT NULL DEFAULT '["veg"]',
    component TEXT NOT NULL DEFAULT '',
    ingredients TEXT NOT NULL DEFAULT '[]',
    steps TEXT NOT NULL DEFAULT '[]',
    tags TEXT NOT NULL DEFAULT '[]',
    youtube TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'seed',
    store_bought INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    frequency TEXT NOT NULL DEFAULT '',
    serves_subset INTEGER NOT NULL DEFAULT 0,
    day_preference TEXT NOT NULL DEFAULT '',
    also_meal_types TEXT NOT NULL DEFAULT '[]',
    also_components TEXT NOT NULL DEFAULT '[]',
    snack_type TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ingredient_name TEXT NOT NULL,
    quantity REAL NOT NULL DEFAULT 0,
    unit TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'other',
    last_updated TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS menu (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start_date TEXT NOT NULL,
    selected_member_ids TEXT NOT NULL DEFAULT '[]',
    school_tiffins INTEGER NOT NULL DEFAULT 0,
    office_tiffins INTEGER NOT NULL DEFAULT 0,
    time_crunch INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS menu_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    menu_id INTEGER NOT NULL REFERENCES menu(id) ON DELETE CASCADE,
    day TEXT NOT NULL,
    meal_type TEXT NOT NULL,
    component TEXT NOT NULL DEFAULT '',
    recipe_id INTEGER REFERENCES recipe(id)
);

CREATE TABLE IF NOT EXISTS grocery_list (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    menu_id INTEGER NOT NULL REFERENCES menu(id) ON DELETE CASCADE,
    ingredient_name TEXT NOT NULL,
    quantity REAL NOT NULL DEFAULT 0,
    unit TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'other',
    source TEXT NOT NULL DEFAULT 'menu',
    have_already INTEGER NOT NULL DEFAULT 0,
    used_in TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS favorite (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER NOT NULL UNIQUE REFERENCES recipe(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def backup_bytes() -> bytes:
    """A consistent copy of the whole database, safe to take while running.

    sqlite3's online backup API copies page by page and starts over if a write
    lands mid-copy, so the result is always a valid database. Reading the file
    off disk directly could catch it half-written.
    """
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "backup.db"
        source = sqlite3.connect(DB_PATH)
        try:
            dest = sqlite3.connect(target)
            try:
                source.backup(dest)
            finally:
                dest.close()
        finally:
            source.close()
        return target.read_bytes()


_SMALL_WORDS = {"with", "and", "or", "of", "in", "a", "the", "for", "to"}


def title_case_dish(name: str) -> str:
    """Display casing for dish names: "green gram thoran" -> "Green Gram Thoran"."""
    out = []
    for i, w in enumerate(name.split(" ")):
        if not w or w == "/":
            out.append(w)
            continue
        prefix, core = ("(", w[1:]) if w.startswith("(") else ("", w)
        if i > 0 and core.lower() in _SMALL_WORDS:
            out.append(prefix + core.lower())
        else:
            out.append(prefix + core[:1].upper() + core[1:].lower())
    return " ".join(out)


def infer_component(name: str, meal_type: str, tags: list[str]) -> str:
    """Best-effort component for recipes that don't declare one (e.g. user-added)."""
    n = name.lower()
    if meal_type == "snack":
        return "snack"
    if "pachadi" in n:
        return "pachadi"
    if "salad" in n or "kachumber" in n:
        return "salad"
    if any(w in n for w in ("thoran", "stir-fry", "mezhukku", "avial")):
        return "veg_side"
    if ("fry" in n or "roast" in n or "grilled" in n) and any(
        w in n for w in ("fish", "chicken", "egg", "meat", "beef", "prawn")
    ):
        return "protein_fry"
    if n in ("rice", "plain rice") or "rice" == n.strip():
        return "rice_staple"
    if any(w in n for w in ("chapati", "paratha", "bread", "roti", "phulka")):
        return "bread_staple"
    if meal_type == "breakfast":
        return "breakfast_side" if "chutney" in n else "breakfast_main"
    return "curry"


def _normalize_diet(value) -> list[str]:
    """`diet` arrives as an array (["veg"]); tolerate legacy strings."""
    if isinstance(value, list):
        return [str(v).strip().lower() for v in value if str(v).strip()] or ["veg"]
    if isinstance(value, str) and value.strip():
        return [value.strip().lower()]
    return ["veg"]


def _normalize_steps(value) -> list[str]:
    """`steps` arrives as an array of sentences; tolerate legacy paragraphs."""
    if isinstance(value, list):
        return [str(s).strip() for s in value if str(s).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _upsert_seed_recipes(conn: sqlite3.Connection, recipes: list[dict]) -> None:
    """Insert or refresh seed recipes by name (the source data has no ids);
    seed rows that vanished from the file are removed. source='user' rows are
    never touched."""
    seen_names = []
    for r in recipes:
        name = title_case_dish(r["name"]) if r["name"].islower() else r["name"]
        seen_names.append(name)
        component = r.get("component") or infer_component(
            name, r.get("meal_type", "lunch"), r.get("tags", [])
        )
        values = (
            r.get("cuisine", "kerala"),
            r.get("meal_type", "lunch"),
            r.get("prep_minutes", 30),
            1 if r.get("is_quick") else 0,
            json.dumps(_normalize_diet(r.get("diet"))),
            component,
            json.dumps(r.get("ingredients", [])),
            json.dumps(_normalize_steps(r.get("steps"))),
            json.dumps(r.get("tags", [])),
            r.get("youtube", ""),
            1 if r.get("store_bought") else 0,
            r.get("note", ""),
            r.get("frequency", ""),
            1 if r.get("serves_subset") else 0,
            r.get("day_preference", ""),
            json.dumps(r.get("also_meal_types", [])),
            json.dumps(r.get("also_components", [])),
            r.get("snack_type", ""),
        )
        row = conn.execute(
            "SELECT id FROM recipe WHERE name=? COLLATE NOCASE AND source='seed'", (name,)
        ).fetchone()
        if row:
            conn.execute(
                """UPDATE recipe SET cuisine=?, meal_type=?, prep_minutes=?, is_quick=?,
                   diet=?, component=?, ingredients=?, steps=?, tags=?, youtube=?,
                   store_bought=?, note=?, frequency=?, serves_subset=?,
                   day_preference=?, also_meal_types=?, also_components=?,
                   snack_type=?, name=? WHERE id=?""",
                values + (name, row["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO recipe (cuisine, meal_type, prep_minutes, is_quick, diet,
                   component, ingredients, steps, tags, youtube, store_bought, note,
                   frequency, serves_subset, day_preference, also_meal_types,
                   also_components, snack_type, name, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'seed')""",
                values + (name,),
            )

    # Drop seed rows no longer present in the data file (e.g. Kachumber Salad).
    placeholders = ",".join("?" * len(seen_names))
    stale = conn.execute(
        f"SELECT id FROM recipe WHERE source='seed' AND name NOT IN ({placeholders} )",
        seen_names,
    ).fetchall()
    for row in stale:
        conn.execute("DELETE FROM menu_item WHERE recipe_id=?", (row["id"],))
        conn.execute("DELETE FROM favorite WHERE recipe_id=?", (row["id"],))
        conn.execute("DELETE FROM recipe WHERE id=?", (row["id"],))


def init_db() -> None:
    """Create tables, run migrations, and sync seed data."""
    # The folder may not exist yet on a fresh host.
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)

        # Migrations for databases created by earlier versions.
        menu_cols = {r["name"] for r in conn.execute("PRAGMA table_info(menu)").fetchall()}
        if "time_crunch" not in menu_cols:
            conn.execute("ALTER TABLE menu ADD COLUMN time_crunch INTEGER NOT NULL DEFAULT 0")
        recipe_cols = {r["name"] for r in conn.execute("PRAGMA table_info(recipe)").fetchall()}
        if "component" not in recipe_cols:
            conn.execute("ALTER TABLE recipe ADD COLUMN component TEXT NOT NULL DEFAULT ''")
        item_cols = {r["name"] for r in conn.execute("PRAGMA table_info(menu_item)").fetchall()}
        if "component" not in item_cols:
            conn.execute("ALTER TABLE menu_item ADD COLUMN component TEXT NOT NULL DEFAULT ''")
            # Old single-dish menus can't be shown as composed plates; start fresh.
            conn.execute("DELETE FROM menu")
        for col, ddl in (
            ("store_bought", "INTEGER NOT NULL DEFAULT 0"),
            ("note", "TEXT NOT NULL DEFAULT ''"),
            ("frequency", "TEXT NOT NULL DEFAULT ''"),
            ("serves_subset", "INTEGER NOT NULL DEFAULT 0"),
            ("day_preference", "TEXT NOT NULL DEFAULT ''"),
            ("also_meal_types", "TEXT NOT NULL DEFAULT '[]'"),
            ("also_components", "TEXT NOT NULL DEFAULT '[]'"),
            ("snack_type", "TEXT NOT NULL DEFAULT ''"),
        ):
            if col not in recipe_cols:
                conn.execute(f"ALTER TABLE recipe ADD COLUMN {col} {ddl}")
        grocery_cols = {r["name"] for r in conn.execute("PRAGMA table_info(grocery_list)").fetchall()}
        if "used_in" not in grocery_cols:
            conn.execute("ALTER TABLE grocery_list ADD COLUMN used_in TEXT NOT NULL DEFAULT '[]'")

        recipes = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        if isinstance(recipes, dict):  # legacy shape: {"recipes": [...], ...glossaries}
            for key in ("aliases", "english_to_manglish", "pantry_staples", "incompatible_pairs"):
                if key in recipes:
                    conn.execute(
                        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                        (key, json.dumps(recipes[key])),
                    )
            recipes = recipes["recipes"]

        # Rules and glossaries now live in their own metadata file.
        if METADATA_PATH.exists():
            meta = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
            for key in METADATA_KEYS:
                if key in meta:
                    conn.execute(
                        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                        (key, json.dumps(meta[key])),
                    )

        # The recipe set changed shape (diet arrays, new components); any menu
        # built from the previous set can no longer be rendered as plates.
        old_diet = conn.execute(
            "SELECT diet FROM recipe WHERE source='seed' LIMIT 1"
        ).fetchone()
        if old_diet and not old_diet["diet"].startswith("["):
            conn.execute("DELETE FROM menu")

        # Migrate legacy scalar diet/steps on any row (incl. user recipes) to JSON.
        for row in conn.execute("SELECT id, diet, steps FROM recipe").fetchall():
            updates = {}
            if not str(row["diet"]).startswith("["):
                updates["diet"] = json.dumps(_normalize_diet(row["diet"]))
            if not str(row["steps"]).startswith("["):
                updates["steps"] = json.dumps(_normalize_steps(row["steps"]))
            if updates:
                sets = ", ".join(f"{k}=?" for k in updates)
                conn.execute(f"UPDATE recipe SET {sets} WHERE id=?",
                             (*updates.values(), row["id"]))

        _upsert_seed_recipes(conn, recipes)

        # Backfill component on any remaining rows (user-added recipes).
        for row in conn.execute("SELECT id, name, meal_type, tags FROM recipe WHERE component=''").fetchall():
            conn.execute(
                "UPDATE recipe SET component=? WHERE id=?",
                (infer_component(row["name"], row["meal_type"], json.loads(row["tags"])), row["id"]),
            )
        conn.commit()
    finally:
        conn.close()


def get_setting(key: str):
    """Return a parsed JSON value from the settings table, or None."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else None
    finally:
        conn.close()


def recipe_count() -> int:
    conn = get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM recipe").fetchone()[0]
    finally:
        conn.close()


# ---------- family members ----------

def _member_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["in_household"] = bool(d["in_household"])
    return d


def list_members() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM family_member ORDER BY in_household DESC, id"
        ).fetchall()
        return [_member_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_members(ids: list[int]) -> list[dict]:
    if not ids:
        return []
    conn = get_conn()
    try:
        marks = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT * FROM family_member WHERE id IN ({marks})", ids
        ).fetchall()
        return [_member_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def create_member(m: dict) -> dict:
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO family_member (name, diet, health_conditions, likes, dislikes, in_household)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (m["name"], m["diet"], m["health_conditions"], m["likes"],
             m["dislikes"], 1 if m["in_household"] else 0),
        )
        conn.commit()
        return get_members([cur.lastrowid])[0]
    finally:
        conn.close()


def update_member(member_id: int, m: dict) -> dict | None:
    conn = get_conn()
    try:
        cur = conn.execute(
            """UPDATE family_member
               SET name=?, diet=?, health_conditions=?, likes=?, dislikes=?, in_household=?
               WHERE id=?""",
            (m["name"], m["diet"], m["health_conditions"], m["likes"],
             m["dislikes"], 1 if m["in_household"] else 0, member_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        return get_members([member_id])[0]
    finally:
        conn.close()


def delete_member(member_id: int) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute("DELETE FROM family_member WHERE id=?", (member_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------- recipes ----------

def _recipe_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for key in ("ingredients", "tags", "diet", "steps", "also_meal_types", "also_components"):
        d[key] = json.loads(d[key]) if isinstance(d.get(key), str) else (d.get(key) or [])
    d["is_quick"] = bool(d["is_quick"])
    d["store_bought"] = bool(d.get("store_bought"))
    d["serves_subset"] = bool(d.get("serves_subset"))
    return d


def list_recipes() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM recipe ORDER BY id").fetchall()
        return [_recipe_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_recipe(recipe_id: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM recipe WHERE id=?", (recipe_id,)).fetchone()
        return _recipe_row_to_dict(row) if row else None
    finally:
        conn.close()


def count_user_recipes() -> int:
    conn = get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM recipe WHERE source='user'").fetchone()[0]
    finally:
        conn.close()


def create_user_recipe(r: dict) -> dict:
    """Save an "Add my recipe" entry; usable in planning immediately."""
    name = title_case_dish(r["name"].strip())
    prep = r.get("prep_minutes") or 30
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO recipe (name, cuisine, meal_type, prep_minutes, is_quick, diet,
               component, ingredients, steps, tags, youtube, frequency, snack_type, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'user')""",
            (
                name,
                r.get("cuisine", "kerala"),
                r.get("meal_type", "lunch"),
                prep,
                1 if prep <= 20 else 0,
                json.dumps(_normalize_diet(r.get("diet"))),
                infer_component(name, r.get("meal_type", "lunch"), []),
                json.dumps(r.get("ingredients", [])),
                json.dumps(_normalize_steps(r.get("steps"))),
                json.dumps(["my-recipe"]),
                r.get("youtube", ""),
                r.get("frequency", ""),
                r.get("snack_type", ""),
            ),
        )
        conn.commit()
        recipe_id = cur.lastrowid
    finally:
        conn.close()
    return get_recipe(recipe_id)


def update_user_recipe(recipe_id: int, r: dict) -> dict | None:
    """Edit a dish she added herself. Seed recipes are left alone."""
    name = title_case_dish(r["name"].strip())
    prep = r.get("prep_minutes") or 30
    conn = get_conn()
    try:
        cur = conn.execute(
            """UPDATE recipe SET name=?, meal_type=?, prep_minutes=?, is_quick=?, diet=?,
               component=?, ingredients=?, steps=?, youtube=?, frequency=?, snack_type=?
               WHERE id=? AND source='user'""",
            (
                name,
                r.get("meal_type", "lunch"),
                prep,
                1 if prep <= 20 else 0,
                json.dumps(_normalize_diet(r.get("diet"))),
                infer_component(name, r.get("meal_type", "lunch"), []),
                json.dumps(r.get("ingredients", [])),
                json.dumps(_normalize_steps(r.get("steps"))),
                r.get("youtube", ""),
                r.get("frequency", ""),
                r.get("snack_type", ""),
                recipe_id,
            ),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
    finally:
        conn.close()
    return get_recipe(recipe_id)


def delete_user_recipe(recipe_id: int) -> bool:
    """Remove a dish she added, and take it off any menu it's on."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM recipe WHERE id=? AND source='user'", (recipe_id,)
        ).fetchone()
        if row is None:
            return False
        conn.execute("DELETE FROM menu_item WHERE recipe_id=?", (recipe_id,))
        conn.execute("DELETE FROM favorite WHERE recipe_id=?", (recipe_id,))
        conn.execute("DELETE FROM recipe WHERE id=?", (recipe_id,))
        conn.commit()
        return True
    finally:
        conn.close()


# ---------- menus ----------

def save_menu(week_start_date: str, member_ids: list[int], school_tiffins: int,
              office_tiffins: int, time_crunch: bool, items: list[dict]) -> int:
    """items: [{day, meal_type, recipe_id}] — replaces any existing menu for the same week."""
    conn = get_conn()
    try:
        old = conn.execute(
            "SELECT id FROM menu WHERE week_start_date=?", (week_start_date,)
        ).fetchall()
        for row in old:
            conn.execute("DELETE FROM menu WHERE id=?", (row["id"],))
        cur = conn.execute(
            """INSERT INTO menu (week_start_date, selected_member_ids, school_tiffins,
                                 office_tiffins, time_crunch)
               VALUES (?, ?, ?, ?, ?)""",
            (week_start_date, json.dumps(member_ids), school_tiffins, office_tiffins,
             1 if time_crunch else 0),
        )
        menu_id = cur.lastrowid
        for it in items:
            conn.execute(
                """INSERT INTO menu_item (menu_id, day, meal_type, component, recipe_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (menu_id, it["day"], it["meal_type"], it["component"], it["recipe_id"]),
            )
        conn.commit()
        return menu_id
    finally:
        conn.close()


def get_latest_menu() -> dict | None:
    conn = get_conn()
    try:
        menu = conn.execute("SELECT * FROM menu ORDER BY id DESC LIMIT 1").fetchone()
        if not menu:
            return None
        items = conn.execute(
            "SELECT * FROM menu_item WHERE menu_id=? ORDER BY id", (menu["id"],)
        ).fetchall()
        d = dict(menu)
        d["selected_member_ids"] = json.loads(d["selected_member_ids"])
        d["time_crunch"] = bool(d["time_crunch"])
        d["items"] = [dict(i) for i in items]
        return d
    finally:
        conn.close()


def get_menu_item(menu_id: int, item_id: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM menu_item WHERE id=? AND menu_id=?", (item_id, menu_id)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def set_menu_item_recipe(menu_id: int, item_id: int, recipe_id: int) -> bool:
    """Point one menu row at a different dish. Keyed on the row id, not the
    component, so a meal can hold two curries without them moving together."""
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE menu_item SET recipe_id=? WHERE id=? AND menu_id=?",
            (recipe_id, item_id, menu_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def add_menu_item(menu_id: int, day: str, meal_type: str, component: str,
                  recipe_id: int) -> dict:
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO menu_item (menu_id, day, meal_type, component, recipe_id)
               VALUES (?, ?, ?, ?, ?)""",
            (menu_id, day, meal_type, component, recipe_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM menu_item WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def delete_menu_item(menu_id: int, item_id: int) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM menu_item WHERE id=? AND menu_id=?", (item_id, menu_id)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------- grocery list ----------

def replace_grocery_list(menu_id: int, items: list[dict]) -> list[dict]:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM grocery_list WHERE menu_id=?", (menu_id,))
        for it in items:
            conn.execute(
                """INSERT INTO grocery_list
                   (menu_id, ingredient_name, quantity, unit, category, source,
                    have_already, used_in)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (menu_id, it["ingredient_name"], it["quantity"], it["unit"],
                 it["category"], it["source"], 1 if it.get("have_already") else 0,
                 json.dumps(it.get("used_in", []))),
            )
        conn.commit()
        return get_grocery_list(menu_id)
    finally:
        conn.close()


def get_grocery_list(menu_id: int) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM grocery_list WHERE menu_id=? ORDER BY category, ingredient_name",
            (menu_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["have_already"] = bool(d["have_already"])
            d["used_in"] = json.loads(d.get("used_in") or "[]")
            out.append(d)
        return out
    finally:
        conn.close()


def add_grocery_item(menu_id: int, item: dict) -> dict:
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO grocery_list
               (menu_id, ingredient_name, quantity, unit, category, source, have_already)
               VALUES (?, ?, ?, ?, ?, 'manual', 0)""",
            (menu_id, item["ingredient_name"], item.get("quantity", 1),
             item.get("unit", ""), item.get("category", "other")),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM grocery_list WHERE id=?", (cur.lastrowid,)).fetchone()
        d = dict(row)
        d["have_already"] = bool(d["have_already"])
        d["used_in"] = json.loads(d.get("used_in") or "[]")
        return d
    finally:
        conn.close()


def update_grocery_item(item_id: int, item: dict) -> dict | None:
    conn = get_conn()
    try:
        cur = conn.execute(
            """UPDATE grocery_list SET ingredient_name=?, quantity=?, unit=?, category=?
               WHERE id=?""",
            (item["ingredient_name"], item.get("quantity", 1), item.get("unit", ""),
             item.get("category", "other"), item_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM grocery_list WHERE id=?", (item_id,)).fetchone()
        d = dict(row)
        d["have_already"] = bool(d["have_already"])
        d["used_in"] = json.loads(d.get("used_in") or "[]")
        return d
    finally:
        conn.close()


def delete_grocery_item(item_id: int) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute("DELETE FROM grocery_list WHERE id=?", (item_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def toggle_grocery_item(item_id: int) -> bool | None:
    """Returns the new have_already state, or None if not found."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT have_already FROM grocery_list WHERE id=?", (item_id,)).fetchone()
        if row is None:
            return None
        new_state = 0 if row["have_already"] else 1
        conn.execute("UPDATE grocery_list SET have_already=? WHERE id=?", (new_state, item_id))
        conn.commit()
        return bool(new_state)
    finally:
        conn.close()


# ---------- favorites ----------

def list_favorite_ids() -> list[int]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT recipe_id FROM favorite").fetchall()
        return [r["recipe_id"] for r in rows]
    finally:
        conn.close()


def toggle_favorite(recipe_id: int) -> bool:
    """Returns True if the recipe is now a favorite."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM favorite WHERE recipe_id=?", (recipe_id,)
        ).fetchone()
        if row:
            conn.execute("DELETE FROM favorite WHERE recipe_id=?", (recipe_id,))
            conn.commit()
            return False
        conn.execute("INSERT INTO favorite (recipe_id) VALUES (?)", (recipe_id,))
        conn.commit()
        return True
    finally:
        conn.close()
