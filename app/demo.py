"""Public demo mode (DEMO_MODE=1).

A recruiter-facing copy of the app that runs with its own empty database,
invented sample households, no PIN, and a hard daily cap on AI requests so
strangers cannot run up the Gemini bill. Nothing here ever touches the real
family app, which is a separate deployment with a separate database.

Counters live in SQLite (not in memory) because the app runs several worker
processes and each would otherwise keep its own count.
"""

import os
from datetime import date

from . import db

# Invented people. Not real; chosen to show different diets and health rules.
SAMPLE_MEMBERS = [
    {"name": "Asha (sample)", "diet": "non-veg", "health_conditions": "High cholesterol",
     "likes": "", "dislikes": "", "in_household": True},
    {"name": "Ravi (sample)", "diet": "non-veg", "health_conditions": "Diabetes",
     "likes": "", "dislikes": "", "in_household": True},
    {"name": "Meera (sample)", "diet": "veg", "health_conditions": "Lactose intolerance",
     "likes": "", "dislikes": "", "in_household": True},
    {"name": "Grandpa Joe (sample)", "diet": "eggetarian", "health_conditions": "High blood pressure",
     "likes": "", "dislikes": "", "in_household": False},
]

MAX_MEMBERS = 8
MAX_USER_RECIPES = 15


def enabled() -> bool:
    return os.environ.get("DEMO_MODE", "").strip().lower() in ("1", "true", "yes")


def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, "").strip())
    except ValueError:
        return default
    return value if value >= 0 else default


def global_limit() -> int:
    """AI plans allowed per day across ALL visitors. 0 turns the AI off."""
    return _int_env("DEMO_AI_DAILY_LIMIT", 40)


def per_visitor_limit() -> int:
    """AI plans allowed per day for one visitor (by IP address)."""
    return _int_env("DEMO_AI_PER_VISITOR", 3)


def _ensure_tables(conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS demo_usage ("
        " day TEXT NOT NULL, who TEXT NOT NULL, count INTEGER NOT NULL DEFAULT 0,"
        " PRIMARY KEY (day, who))"
    )


def try_use_ai(visitor: str) -> tuple[bool, str]:
    """Reserve one AI call. Returns (allowed, reason_if_not).

    The check and the increment happen in one write transaction so two
    simultaneous requests cannot both slip under the limit.
    """
    today = date.today().isoformat()
    conn = db.get_conn()
    try:
        _ensure_tables(conn)
        conn.execute("BEGIN IMMEDIATE")
        total = conn.execute(
            "SELECT COALESCE(SUM(count), 0) FROM demo_usage WHERE day=? AND who != '*'", (today,)
        ).fetchone()[0]
        mine = conn.execute(
            "SELECT COALESCE(count, 0) FROM demo_usage WHERE day=? AND who=?", (today, visitor)
        ).fetchone()
        mine = mine[0] if mine else 0
        if total >= global_limit():
            conn.execute("ROLLBACK")
            return False, "The demo has reached its daily limit of AI plans. Try again tomorrow."
        if mine >= per_visitor_limit():
            conn.execute("ROLLBACK")
            return False, (f"You have used your {per_visitor_limit()} AI plans for today. "
                           "Menus below still work, built by the app's rule engine.")
        conn.execute(
            "INSERT INTO demo_usage (day, who, count) VALUES (?, ?, 1) "
            "ON CONFLICT(day, who) DO UPDATE SET count = count + 1", (today, visitor)
        )
        conn.execute("COMMIT")
        return True, ""
    finally:
        conn.close()


def reset_if_new_day() -> None:
    """Wipe visitor changes once a day and restore the sample households.

    Check, wipe and re-seed share one write transaction, so two worker
    processes crossing midnight together cannot both seed the households.
    """
    today = date.today().isoformat()
    conn = db.get_conn()
    try:
        _ensure_tables(conn)
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT value FROM settings WHERE key='demo_last_reset'").fetchone()
        if row and row["value"] == today:
            conn.execute("ROLLBACK")
            return
        conn.execute("DELETE FROM menu")  # cascades to menu_item and grocery_list
        conn.execute("DELETE FROM favorite")
        conn.execute("DELETE FROM family_member")
        conn.execute("DELETE FROM recipe WHERE source='user'")
        conn.execute("DELETE FROM demo_usage WHERE day != ?", (today,))
        for m in SAMPLE_MEMBERS:
            conn.execute(
                "INSERT INTO family_member (name, diet, health_conditions, likes, dislikes, in_household)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (m["name"], m["diet"], m["health_conditions"], m["likes"], m["dislikes"],
                 1 if m["in_household"] else 0),
            )
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('demo_last_reset', ?)",
                     (today,))
        conn.execute("COMMIT")
    finally:
        conn.close()
