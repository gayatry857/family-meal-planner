"""Weekly-menu PDF export (fpdf2, pure Python). Styled to match the app:
soft pastel ground, high-contrast charcoal text, teal accent, hairline borders."""

from datetime import date, timedelta

from fpdf import FPDF
from fpdf.enums import TableBordersLayout

INK = (31, 42, 48)
SUB = (90, 107, 112)
ACCENT = (47, 122, 104)
LINE = (223, 233, 229)
PAPER = (243, 248, 246)

SLOT_LABELS = {
    "breakfast_main": "Main", "breakfast_side": "Side", "rice_staple": "Rice",
    "bread_staple": "Bread", "curry": "Curry", "veg_side": "Veg side",
    "pachadi": "Pachadi", "protein_fry": "Protein", "salad": "Salad",
    "extra": "Extra", "snack": "Snack", "accompaniment": "With it",
    "breakfast_protein": "Protein",
}
MEALS = ["breakfast", "lunch", "snack", "dinner"]
MEAL_TITLES = {"breakfast": "Breakfast", "lunch": "Lunch", "snack": "Snack",
               "dinner": "Dinner"}


def _latin(text: str) -> str:
    """Core PDF fonts are latin-1; degrade anything else gracefully."""
    return text.encode("latin-1", "replace").decode("latin-1")


def _week_range(week_start_date: str) -> str:
    try:
        start = date.fromisoformat(week_start_date)
    except ValueError:
        return week_start_date
    end = start + timedelta(days=6)
    if start.month == end.month:
        return f"{start.day} - {end.day} {end.strftime('%B %Y')}"
    return f"{start.strftime('%d %b')} - {end.strftime('%d %b %Y')}"


def _cell_text(components: list[dict]) -> str:
    lines = []
    for c in components:
        r = c["recipe"]
        name = r["name"]
        if "amma-recipe" in r.get("tags", []):
            name += " (Amma's recipe)"
        lines.append(f"{SLOT_LABELS.get(c['component'], c['component'])}: {name}")
    return "\n".join(lines) or "-"


def build_menu_pdf(menu: dict, title: str, recipient: str,
                   grocery_items: list[dict] | None = None) -> bytes:
    pdf = FPDF(orientation="P", format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.set_margins(12, 14, 12)
    pdf.add_page()

    # Header
    pdf.set_text_color(*INK)
    pdf.set_font("helvetica", "B", 18)
    pdf.cell(0, 9, _latin(title or "Weekly menu"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 11)
    pdf.set_text_color(*SUB)
    sub = _week_range(menu["week_start_date"])
    if recipient:
        sub = f"For {recipient}  ·  {sub}"
    pdf.cell(0, 6, _latin(sub), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Menu table: days as rows, meals as columns.
    pdf.set_draw_color(*LINE)
    pdf.set_line_width(0.2)
    # A4 minus 12mm margins each side = 186mm of usable width; these must sum
    # to that or fpdf reflows the cells and long day names wrap.
    with pdf.table(
        col_widths=(25, 45, 43, 28, 45),
        borders_layout=TableBordersLayout.HORIZONTAL_LINES,
        line_height=4.6,
        padding=1.6,
        text_align="LEFT",
        first_row_as_headings=True,
    ) as table:
        header = table.row()
        pdf.set_font("helvetica", "B", 9.5)
        pdf.set_text_color(*ACCENT)
        for h in [""] + [MEAL_TITLES[m] for m in MEALS]:
            header.cell(h)
        for d in menu["days"]:
            row = table.row()
            pdf.set_font("helvetica", "B", 9.5)
            pdf.set_text_color(*INK)
            row.cell(d["day"])
            pdf.set_font("helvetica", "", 8.5)
            for meal in MEALS:
                row.cell(_latin(_cell_text(d["meals"].get(meal, []))))

    # Optional grocery page.
    if grocery_items:
        pdf.add_page()
        _draw_grocery(pdf, grocery_items)

    return bytes(pdf.output())


def _item_quantity(item: dict) -> str:
    if item["source"] == "staple":
        return "for the week"
    if item["unit"] == "dishes":
        return f"{int(item['quantity'])} {'dish' if item['quantity'] == 1 else 'dishes'}"
    return f"{item['quantity']:g} {item['unit']}".strip()


def _draw_grocery(pdf: FPDF, items: list[dict], heading: str = "Grocery list") -> None:
    """The shopping list with tick boxes, grouped by aisle."""
    if heading:
        pdf.set_font("helvetica", "B", 15)
        pdf.set_text_color(*INK)
        pdf.cell(0, 8, _latin(heading), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
    categories: dict[str, list[dict]] = {}
    for item in items:
        categories.setdefault(item["category"], []).append(item)
    for category in sorted(categories):
        pdf.set_font("helvetica", "B", 10.5)
        pdf.set_text_color(*ACCENT)
        pdf.cell(0, 7, _latin(category.title()), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "", 10)
        pdf.set_text_color(*INK)
        for item in categories[category]:
            mark = "x" if item["have_already"] else " "
            pdf.cell(6, 5.5, f"[{mark}]")
            pdf.cell(110, 5.5, _latin(item["ingredient_name"].capitalize()))
            pdf.set_text_color(*SUB)
            pdf.cell(0, 5.5, _latin(_item_quantity(item)), new_x="LMARGIN", new_y="NEXT")
            # Which dishes need it, so the printed list explains itself too.
            dishes = item.get("used_in") or []
            if dishes:
                pdf.set_font("helvetica", "", 8)
                pdf.cell(6, 4.4, "")
                pdf.cell(0, 4.4, _latin(", ".join(dishes)), new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("helvetica", "", 10)
            pdf.set_text_color(*INK)
        pdf.ln(1.5)


def build_grocery_pdf(items: list[dict], people: int, week_start_date: str) -> bytes:
    """The grocery list on its own, for sharing to the phone or printing."""
    pdf = FPDF(orientation="P", format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.set_margins(12, 14, 12)
    pdf.add_page()

    pdf.set_text_color(*INK)
    pdf.set_font("helvetica", "B", 18)
    pdf.cell(0, 9, "Grocery list", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 11)
    pdf.set_text_color(*SUB)
    who = f"For {people} {'person' if people == 1 else 'people'}"
    pdf.cell(0, 6, _latin(f"{who}  ·  {_week_range(week_start_date)}"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    _draw_grocery(pdf, items, heading="")
    return bytes(pdf.output())
