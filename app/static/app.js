// Meal planner frontend. One screen at a time, large targets, minimal typing.

const screen = document.getElementById("screen");
const headerNote = document.getElementById("header-note");
document.getElementById("btn-home").addEventListener("click", () => showHome());

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const MEAL_LABELS = { breakfast: "Breakfast", lunch: "Lunch", snack: "Snack", dinner: "Dinner" };
const SLOT_LABELS = {
  breakfast_main: "Main", breakfast_side: "Side", breakfast_protein: "Protein",
  rice_staple: "Rice", bread_staple: "Bread", curry: "Curry", veg_side: "Veg side",
  pachadi: "Pachadi", protein_fry: "Protein", salad: "Salad", extra: "Extra",
  snack: "Snack", accompaniment: "With it",
};
const GROCERY_CATEGORIES = ["vegetables", "fruits", "dairy & eggs", "fish & meat",
  "grains & staples", "store-bought", "pantry staples", "other"];
const DIET_LABELS = { veg: "Vegetarian", "non-veg": "Non-veg", eggetarian: "Eggetarian" };

let planSelection = { member_ids: [], cuisine_mix: "Kerala / Indian", time_crunch: false };

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  if (res.status === 401) {
    // The session lapsed. Send her to the PIN screen rather than showing an
    // error she has no way to act on.
    location.href = "/login";
    throw new Error("Signed out");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

function esc(s) {
  const div = document.createElement("div");
  div.textContent = String(s ?? "");
  return div.innerHTML;
}

function icon(name, cls = "icon") {
  return `<i data-lucide="${name}" class="${cls}"></i>`;
}

function render(html) {
  screen.innerHTML = html;
  lucide.createIcons();
}

// "Family recipe" is a badge driven by the tag, never part of the dish name.
function familyBadge(recipe) {
  return (recipe.tags || []).includes("family-recipe")
    ? `<span class="text-sm bg-amber text-ink rounded-full px-2.5 py-0.5 align-middle whitespace-nowrap">Family recipe</span>`
    : "";
}

// `diet` is an array on recipes, a plain string on family members.
function dietLabel(recipe) {
  const diets = Array.isArray(recipe.diet) ? recipe.diet : [recipe.diet];
  return diets.map((d) => DIET_LABELS[d] || d).join(" / ");
}

// ---------- Home ----------

// Who is using the app right now, remembered between visits.
function currentUser() {
  try { return JSON.parse(localStorage.getItem("mealplanner.user") || "null"); }
  catch (_) { return null; }
}

function setCurrentUser(member) {
  if (member) localStorage.setItem("mealplanner.user", JSON.stringify(
    { id: member.id, name: member.name }));
  else localStorage.removeItem("mealplanner.user");
}

// Greeting changes with the clock and the person.
function greeting() {
  const h = new Date().getHours();
  const part = h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
  const who = currentUser();
  return who ? `${part}, ${who.name}` : part;
}

// First screen: who's using the app? Skipped once she's chosen.
async function showWhoAreYou({ force = false } = {}) {
  const members = await api("/api/members");
  if (!members.length) { showHome(); return; }
  if (!force && currentUser() && members.some((m) => m.id === currentUser().id)) {
    showHome();
    return;
  }
  headerNote.textContent = "";
  const chips = members.map((m) => `
    <button data-id="${m.id}" class="who-chip card w-full flex items-center gap-4 p-4 text-left">
      <span class="bg-mint text-accent rounded-2xl p-3">${icon("user", "icon w-6 h-6")}</span>
      <span class="flex-1 font-medium text-lg">${esc(m.name)}</span>
      ${icon("chevron-right", "icon text-sub")}
    </button>`).join("");
  render(`
    <h1 class="text-3xl font-medium pt-1">Who's cooking today?</h1>
    <p class="text-sub text-lg pb-1">Tap your name</p>
    <div class="space-y-3 pt-1">${chips}</div>`);
  document.querySelectorAll(".who-chip").forEach((el) =>
    el.addEventListener("click", () => {
      setCurrentUser(members.find((m) => m.id === Number(el.dataset.id)));
      showHome();
    }));
}

function showHome() {
  headerNote.textContent = "";
  const item = (id, ic, label, sub) => `
    <button id="${id}" class="card w-full flex items-center gap-4 p-4 text-left">
      <span class="bg-mint text-accent rounded-2xl p-3">${icon(ic, "icon w-6 h-6")}</span>
      <span class="flex-1">
        <span class="block font-medium text-lg">${label}</span>
        ${sub ? `<span class="block text-sub text-sm">${sub}</span>` : ""}
      </span>
      ${icon("chevron-right", "icon text-sub")}
    </button>`;
  render(`
    <h1 class="text-3xl font-medium pt-1">${greeting()}</h1>
    <p class="text-sub text-lg pb-1">What's cooking?</p>
    <div class="space-y-3 pt-2">
      ${item("go-menu", "calendar-days", "This week's menu", "See and change the plan")}
      ${item("go-plan", "sparkles", "Plan the week", "Make a fresh 7-day menu")}
      ${item("go-grocery", "shopping-basket", "Grocery list", "What to buy this week")}
      ${item("go-snacks", "apple", "Snacks", "Something between meals")}
      ${item("go-add-recipe", "book-plus", "Add my recipe", "Save a family dish")}
      ${item("go-family", "users", "Family", "Profiles and health notes")}
    </div>
    <p class="text-center pt-4 space-x-4">
      <a href="#" id="go-switch" class="text-sub underline text-sm">Not ${esc((currentUser() || {}).name || "you")}?</a>
      <a href="#" id="go-setup" class="text-sub underline text-sm">Setup check</a>
    </p>`);
  document.getElementById("go-switch").onclick = (e) => {
    e.preventDefault();
    showWhoAreYou({ force: true });
  };
  document.getElementById("go-menu").onclick = showMenu;
  document.getElementById("go-snacks").onclick = showSnacks;
  document.getElementById("go-plan").onclick = showPlanStep1;
  document.getElementById("go-grocery").onclick = showGrocery;
  document.getElementById("go-add-recipe").onclick = showAddRecipe;
  document.getElementById("go-family").onclick = showFamily;
  document.getElementById("go-setup").onclick = (e) => { e.preventDefault(); showSetup(); };
}

// ---------- Family profiles ----------

async function showFamily() {
  headerNote.textContent = "Family";
  const members = await api("/api/members");
  const cards = members.map((m) => `
    <button data-id="${m.id}" class="member-card card w-full text-left p-4">
      <p class="font-medium text-lg">${esc(m.name)}
        ${m.in_household ? '<span class="text-xs bg-accent-tint text-accent rounded-full px-2 py-0.5 ml-1 align-middle">lives at home</span>' : ""}</p>
      <p class="text-sub">${esc(DIET_LABELS[m.diet] || m.diet)}${m.health_conditions ? " · " + esc(m.health_conditions) : ""}</p>
    </button>`).join("");
  render(`
    <h1 class="text-2xl font-medium">Family</h1>
    <p class="text-sub">Tap a person to change their details</p>
    <div class="space-y-3">${cards || '<p class="card text-sub p-4">No one added yet.</p>'}</div>
    <button id="add-member" class="btn btn-primary">${icon("plus")} Add family member</button>`);
  document.querySelectorAll(".member-card").forEach((el) =>
    el.addEventListener("click", () => showMemberForm(members.find((m) => m.id == el.dataset.id))));
  document.getElementById("add-member").onclick = () => showMemberForm(null);
}

// Accept commas or one-per-line, since people type both.
function splitList(text) {
  return (text || "").split(/[,\n]/).map((s) => s.trim()).filter(Boolean);
}

// Searchable multi-select: selected chips + a filter input with tappable suggestions.
function chipPicker(rootId, choices, selected, placeholder) {
  const root = document.getElementById(rootId);
  const state = new Set(selected);
  const draw = () => {
    const chips = [...state].map((v) => `
      <button type="button" data-v="${esc(v)}" class="pick-chip flex items-center gap-1.5 bg-accent-tint text-accent rounded-full px-3 py-2 text-sm font-medium !min-h-0">
        ${esc(v)} ${icon("x", "w-3.5 h-3.5")}
      </button>`).join("");
    root.innerHTML = `
      <div class="flex flex-wrap gap-2 ${state.size ? "pb-2" : ""}">${chips}</div>
      <input class="input pick-input" placeholder="${placeholder}">
      <div class="pick-suggestions pt-1"></div>`;
    lucide.createIcons();
    root.querySelectorAll(".pick-chip").forEach((el) =>
      el.addEventListener("click", () => { state.delete(el.dataset.v); draw(); }));
    const input = root.querySelector(".pick-input");
    const sugg = root.querySelector(".pick-suggestions");
    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      if (!q) { sugg.innerHTML = ""; return; }
      const matches = choices.filter((c) => c.toLowerCase().includes(q) && !state.has(c)).slice(0, 6);
      const custom = matches.some((c) => c.toLowerCase() === q) ? "" : `
        <button type="button" class="pick-add w-full text-left text-sub px-3 py-2.5 !min-h-0">Add "${esc(input.value.trim())}"</button>`;
      sugg.innerHTML = `<div class="card divide-y divide-line/60">` + matches.map((c) => `
        <button type="button" data-v="${esc(c)}" class="pick-opt w-full text-left px-3 py-2.5 !min-h-0">${esc(c)}</button>`).join("") + custom + `</div>`;
      sugg.querySelectorAll(".pick-opt").forEach((el) =>
        el.addEventListener("click", () => { state.add(el.dataset.v); draw(); }));
      const add = sugg.querySelector(".pick-add");
      if (add) add.addEventListener("click", () => {
        const v = input.value.trim();
        if (v) state.add(v[0].toUpperCase() + v.slice(1));
        draw();
      });
    });
  };
  draw();
  return () => [...state];
}

async function showMemberForm(member) {
  headerNote.textContent = "Family";
  const choices = await api("/api/choices");
  const m = member || { name: "", diet: "veg", health_conditions: "", likes: "", dislikes: "", in_household: false };
  const knownConditions = choices.conditions.filter((c) => c !== "None");
  const existing = splitList(m.health_conditions);
  const selectedConds = new Set(existing.filter((c) => knownConditions.some((k) => k.toLowerCase() === c.toLowerCase()))
    .map((c) => knownConditions.find((k) => k.toLowerCase() === c.toLowerCase())));
  const otherText = existing.filter((c) => !knownConditions.some((k) => k.toLowerCase() === c.toLowerCase())).join(", ");
  const dietRadio = (value) => `
    <label class="flex-1">
      <input type="radio" name="diet" value="${value}" class="peer hidden" ${m.diet === value ? "checked" : ""}>
      <span class="flex items-center justify-center rounded-xl border border-line peer-checked:border-accent peer-checked:bg-accent-tint peer-checked:text-accent font-medium cursor-pointer px-2 py-3 h-full">${DIET_LABELS[value]}</span>
    </label>`;
  render(`
    <h1 class="text-2xl font-medium">${member ? "Edit " + esc(m.name) : "Add family member"}</h1>
    <div class="card p-4 space-y-5">
      <div>
        <label class="font-medium block pb-1.5">Name</label>
        <input id="f-name" value="${esc(m.name)}" class="input" placeholder="e.g. Priya">
      </div>
      <div>
        <label class="font-medium block pb-1.5">Food type</label>
        <div class="flex gap-2">${dietRadio("veg")}${dietRadio("non-veg")}${dietRadio("eggetarian")}</div>
      </div>
      <div>
        <label class="font-medium block pb-1.5">Health conditions</label>
        <div id="f-conds" class="grid grid-cols-2 gap-2"></div>
        <input id="f-cond-other" value="${esc(otherText)}" class="input mt-2" placeholder="Other (optional)">
      </div>
      <div>
        <label class="font-medium block pb-1.5">Likes</label>
        <div id="f-likes"></div>
      </div>
      <div>
        <label class="font-medium block pb-1.5">Dislikes</label>
        <div id="f-dislikes"></div>
      </div>
      <label class="flex items-center gap-3 font-medium">
        <input id="f-household" type="checkbox" class="w-5 h-5 accent-[#2f7a68]" ${m.in_household ? "checked" : ""}>
        Lives at home (picked automatically every week)
      </label>
    </div>
    <button id="save-member" class="btn btn-primary">${icon("check")} Save</button>
    ${member ? `<button id="delete-member" class="btn btn-danger">${icon("trash-2")} Remove ${esc(m.name)}</button>` : ""}
    <button id="cancel-member" class="btn btn-outline">Cancel</button>`);

  // Condition chips: fixed list, multi-select, "None" clears the rest.
  const condRoot = document.getElementById("f-conds");
  const drawConds = () => {
    condRoot.innerHTML = choices.conditions.map((c) => {
      const on = c === "None" ? selectedConds.size === 0 : selectedConds.has(c);
      return `<button type="button" data-c="${esc(c)}" class="cond-chip rounded-xl border px-2 py-2.5 text-sm font-medium
        ${on ? "border-accent bg-accent-tint text-accent" : "border-line bg-surface text-sub"}">${esc(c)}</button>`;
    }).join("");
    condRoot.querySelectorAll(".cond-chip").forEach((el) =>
      el.addEventListener("click", () => {
        const c = el.dataset.c;
        if (c === "None") selectedConds.clear();
        else if (selectedConds.has(c)) selectedConds.delete(c);
        else selectedConds.add(c);
        drawConds();
      }));
  };
  drawConds();

  const pickerChoices = [...choices.dishes, ...choices.ingredients];
  const getLikes = chipPicker("f-likes", pickerChoices, splitList(m.likes), "Search dishes or ingredients…");
  const getDislikes = chipPicker("f-dislikes", pickerChoices, splitList(m.dislikes), "Search dishes or ingredients…");

  document.getElementById("save-member").onclick = async () => {
    const other = document.getElementById("f-cond-other").value.trim();
    const conditions = [...selectedConds, ...(other ? [other] : [])].join(", ");
    const payload = {
      name: document.getElementById("f-name").value.trim(),
      diet: document.querySelector('input[name="diet"]:checked').value,
      health_conditions: conditions,
      likes: getLikes().join(", "),
      dislikes: getDislikes().join(", "),
      in_household: document.getElementById("f-household").checked,
    };
    if (!payload.name) { alert("Please type a name."); return; }
    if (member) await api(`/api/members/${member.id}`, { method: "PUT", body: JSON.stringify(payload) });
    else await api("/api/members", { method: "POST", body: JSON.stringify(payload) });
    showFamily();
  };
  if (member) document.getElementById("delete-member").onclick = async () => {
    if (confirm(`Remove ${m.name}?`)) { await api(`/api/members/${member.id}`, { method: "DELETE" }); showFamily(); }
  };
  document.getElementById("cancel-member").onclick = showFamily;
}

// ---------- Planning flow ----------

async function showPlanStep1() {
  headerNote.textContent = "Plan · step 1 of 2";
  const members = await api("/api/members");
  if (!members.length) {
    render(`
      <h1 class="text-2xl font-medium">Who's eating?</h1>
      <p class="card p-4 text-sub">First add your family members, then we can plan the week.</p>
      <button id="go-family" class="btn btn-primary">${icon("users")} Add family members</button>`);
    document.getElementById("go-family").onclick = showFamily;
    return;
  }
  const selected = new Set(members.filter((m) => m.in_household).map((m) => m.id));
  const chipClass = (on) =>
    `person-chip w-full rounded-xl border font-medium py-4 px-3 flex items-center justify-center gap-2 ${on ? "border-accent bg-accent-tint text-accent" : "border-line bg-surface text-sub"}`;
  const chips = members.map((m) => `
    <button data-id="${m.id}" class="${chipClass(selected.has(m.id))}">
      ${selected.has(m.id) ? icon("check") : ""}<span>${esc(m.name)}</span>
    </button>`).join("");
  render(`
    <h1 class="text-2xl font-medium">Who's eating this week?</h1>
    <p class="text-sub">Your household is already ticked. Tap to change</p>
    <div class="grid grid-cols-2 gap-3">${chips}</div>
    <button id="plan-next" class="btn btn-primary">Next ${icon("arrow-right")}</button>`);
  document.querySelectorAll(".person-chip").forEach((el) =>
    el.addEventListener("click", () => {
      const id = Number(el.dataset.id);
      if (selected.has(id)) selected.delete(id); else selected.add(id);
      const on = selected.has(id);
      el.className = chipClass(on);
      el.innerHTML = `${on ? icon("check") : ""}<span>${esc(members.find((m) => m.id === id).name)}</span>`;
      lucide.createIcons();
    }));
  document.getElementById("plan-next").onclick = () => {
    if (!selected.size) { alert("Pick at least one person."); return; }
    planSelection.member_ids = [...selected];
    showPlanStep2();
  };
}

function showPlanStep2() {
  headerNote.textContent = "Plan · step 2 of 2";
  render(`
    <h1 class="text-2xl font-medium">A few details</h1>
    <div class="card p-4 space-y-5">
      <div>
        <label class="font-medium block pb-1.5">Cuisine</label>
        <select id="p-cuisine" class="input">
          <option>Kerala / Indian</option>
          <option>Mostly Kerala</option>
          <option>Mix of Kerala, Indian and continental</option>
        </select>
      </div>
      <label class="flex items-center gap-3 font-medium">
        <input id="p-crunch" type="checkbox" class="w-5 h-5 accent-[#2f7a68]">
        Busy week — quick dishes only (under 20 min)
      </label>
    </div>
    <button id="make-menu" class="btn btn-primary">${icon("sparkles")} Make the menu</button>`);
  document.getElementById("make-menu").onclick = async () => {
    planSelection.cuisine_mix = document.getElementById("p-cuisine").value;
    planSelection.time_crunch = document.getElementById("p-crunch").checked;
    render(`
      <div class="card p-8 text-center space-y-4 mt-6">
        <span class="inline-block text-accent animate-spin">${icon("loader-circle", "w-8 h-8")}</span>
        <p class="font-medium text-lg">Making your week's menu</p>
        <p class="text-sub">SmartPlate is putting the week together. This takes a few seconds</p>
      </div>`);
    try {
      const menu = await api("/api/plan", { method: "POST", body: JSON.stringify(planSelection) });
      renderMenu(menu);
    } catch (err) {
      render(`
        <p class="card p-4">Something went wrong: ${esc(err.message)}</p>
        <button id="retry" class="btn btn-primary">Try again</button>`);
      document.getElementById("retry").onclick = showPlanStep2;
    }
  };
}

// ---------- Weekly menu (composed plates) ----------

async function showMenu() {
  headerNote.textContent = "This week";
  const menu = await api("/api/menu/latest");
  if (!menu.menu_id) {
    render(`
      <h1 class="text-2xl font-medium">This week's menu</h1>
      <p class="card p-4 text-sub">No menu yet. Let's plan the week.</p>
      <button id="go-plan" class="btn btn-primary">${icon("sparkles")} Plan the week</button>`);
    document.getElementById("go-plan").onclick = showPlanStep1;
    return;
  }
  renderMenu(menu);
}

function renderMenu(menu) {
  headerNote.textContent = "This week";
  const today = new Date().toLocaleDateString("en-US", { weekday: "long" });
  const dayCards = menu.days.map((d) => {
    const mealBlocks = Object.keys(MEAL_LABELS).map((meal) => {
      const components = d.meals[meal] || [];
      if (!components.length) return "";
      const rows = components.map((c) => `
        <button class="meal-row w-full flex items-center gap-3 text-left py-2.5 !min-h-0"
                data-item="${c.item_id}" data-day="${d.day}" data-meal="${meal}"
                data-slot="${c.component}" data-recipe="${c.recipe.id}">
          <span class="text-sub text-sm w-20 flex-none">${SLOT_LABELS[c.component] || c.component}</span>
          <span class="flex-1">${esc(c.recipe.name)} ${familyBadge(c.recipe)}</span>
          ${icon("chevron-right", "icon w-4 h-4 text-line")}
        </button>`).join("");
      return `
        <div class="pt-4">
          <p class="font-display text-accent text-sm font-medium pb-1">${MEAL_LABELS[meal]}</p>
          <div class="divide-y divide-line">${rows}</div>
        </div>`;
    }).join("");
    const isToday = d.day === today;
    return `
      <div class="card p-4 ${isToday ? "border-accent" : ""}">
        <div class="flex items-baseline justify-between border-b border-line pb-3">
          <p class="font-display font-medium text-lg">${d.day}</p>
          ${isToday ? '<span class="text-accent text-sm font-medium">Today</span>' : ""}
        </div>
        ${mealBlocks}
        <button class="add-dish w-full flex items-center gap-2 text-accent font-medium pt-4 !min-h-0"
                data-day="${d.day}">${icon("plus", "icon w-4 h-4")} Add a dish</button>
      </div>`;
  }).join("");
  render(`
    <h1 class="text-2xl font-medium">This week's menu</h1>
    <p class="text-sub">Tap a dish to change or remove it</p>
    ${menu.source === "fallback" ? `<p class="notice text-sm">The AI helper could not be reached, so this is a simple automatic plan.${menu.ai_error ? `<span class="block text-sub pt-1">${esc(menu.ai_error)}</span>` : ""}</p>` : ""}
    <div class="space-y-3">${dayCards}</div>
    <button id="go-grocery" class="btn btn-primary">${icon("shopping-basket")} Grocery list</button>
    <button id="export-pdf" class="btn btn-outline">${icon("file-down")} Export as PDF</button>
    <button id="replan" class="btn btn-second">${icon("sparkles")} Plan again</button>`);
  document.querySelectorAll(".meal-row").forEach((el) =>
    el.addEventListener("click", () => showDishActions(menu.menu_id, {
      itemId: Number(el.dataset.item), recipeId: Number(el.dataset.recipe),
      day: el.dataset.day, meal: el.dataset.meal, component: el.dataset.slot,
    })));
  document.querySelectorAll(".add-dish").forEach((el) =>
    el.addEventListener("click", () => showAddToMenu(menu.menu_id, el.dataset.day)));
  document.getElementById("go-grocery").onclick = showGrocery;
  document.getElementById("export-pdf").onclick = () => showPdfExport(menu);
  document.getElementById("replan").onclick = showPlanStep1;
}

// ---------- One dish in the menu: recipe / swap / choose / remove ----------

async function showDishActions(menuId, slot) {
  headerNote.textContent = "This week";
  const r = await api(`/api/recipes/${slot.recipeId}`);
  render(`
    <p class="text-sub">${slot.day} · ${MEAL_LABELS[slot.meal]} · ${SLOT_LABELS[slot.component] || slot.component}</p>
    <div class="card p-5">
      <h1 class="text-2xl font-medium">${esc(r.name)} ${familyBadge(r)}</h1>
      <p class="text-sub pt-1">${r.store_bought ? "Bought, not cooked" : r.prep_minutes + " min"}</p>
    </div>
    ${r.youtube
      ? `<a href="${esc(r.youtube)}" target="_blank" class="block"><span class="btn btn-outline">${icon("play")} Watch on YouTube</span></a>`
      : `<p class="text-sub text-center text-sm">No video for this one.</p>`}
    <button id="d-swap" class="btn btn-primary">${icon("refresh-cw")} Swap it for me</button>
    <button id="d-choose" class="btn btn-outline">${icon("list")} Choose a dish myself</button>
    <button id="d-delete" class="btn btn-danger">${icon("trash-2")} Remove from this meal</button>
    <button id="d-back" class="btn btn-outline">${icon("arrow-left")} Back to the menu</button>
    <p id="d-status" class="text-sub text-center"></p>`);
  const status = document.getElementById("d-status");
  document.getElementById("d-back").onclick = showMenu;
  document.getElementById("d-swap").onclick = async () => {
    status.textContent = "Finding another dish…";
    try {
      const res = await api(`/api/menu/${menuId}/items/${slot.itemId}/swap`, { method: "POST" });
      showDishActions(menuId, { ...slot, recipeId: res.recipe.id });
    } catch (err) {
      status.textContent = err.message;
    }
  };
  document.getElementById("d-choose").onclick = () => showDishPicker(menuId, slot);
  document.getElementById("d-delete").onclick = async () => {
    if (!confirm(`Remove ${r.name} from ${slot.day} ${MEAL_LABELS[slot.meal].toLowerCase()}?`)) return;
    await api(`/api/menu/${menuId}/items/${slot.itemId}`, { method: "DELETE" });
    showMenu();
  };
}

// Type-ahead over the recipe book: "pa" -> Pachadi, Parippu; "pac" -> Pachadi.
function dishSearchBox(rootId, recipes, onPick, { onAddNew } = {}) {
  const root = document.getElementById(rootId);
  const input = root.querySelector(".dish-input");
  const list = root.querySelector(".dish-results");
  let picked = null;
  // Rank: name starts with the query, then any word in the name starts with it
  // (so "pa" finds "Beetroot Pachadi"), then anywhere in the name, then
  // ingredients. Typing more narrows it: "pa" -> Parippu + Pachadi, "pac" -> Pachadi.
  const rank = (r, q) => {
    const name = r.name.toLowerCase();
    if (name.startsWith(q)) return 0;
    if (name.split(/[\s/(-]+/).some((w) => w.startsWith(q))) return 1;
    if (name.includes(q)) return 2;
    if (r.ingredients.some((i) => i.toLowerCase().split(/[\s/(-]+/).some((w) => w.startsWith(q)))) return 3;
    if (r.ingredients.some((i) => i.toLowerCase().includes(q))) return 4;
    return 99;
  };
  const draw = () => {
    const q = input.value.trim().toLowerCase();
    if (!q) { list.innerHTML = ""; return; }
    const matches = recipes
      .map((r) => [rank(r, q), r])
      .filter(([score]) => score < 99)
      .sort((a, b) => a[0] - b[0] || a[1].name.localeCompare(b[1].name))
      .slice(0, 8)
      .map(([, r]) => r);
    list.innerHTML = `<div class="card divide-y divide-line/60">` + matches.map((r) => `
      <button type="button" data-id="${r.id}" class="dish-opt w-full text-left px-3 py-3 !min-h-0">
        <span class="font-medium">${esc(r.name)}</span>
        <span class="text-sub text-sm block">${esc(SLOT_LABELS[r.component] || r.component)} · ${r.store_bought ? "bought" : r.prep_minutes + " min"}</span>
      </button>`).join("")
      + (onAddNew ? `<button type="button" class="dish-add w-full text-left px-3 py-3 text-accent font-medium !min-h-0">Add "${esc(input.value.trim())}" as a new dish</button>` : "")
      + `</div>`;
    list.querySelectorAll(".dish-opt").forEach((el) =>
      el.addEventListener("click", () => {
        picked = recipes.find((r) => r.id === Number(el.dataset.id));
        input.value = picked.name;
        list.innerHTML = "";
        onPick(picked);
      }));
    const addBtn = list.querySelector(".dish-add");
    if (addBtn) addBtn.addEventListener("click", () => onAddNew(input.value.trim()));
  };
  input.addEventListener("input", draw);
  return () => picked;
}

async function showDishPicker(menuId, slot) {
  headerNote.textContent = "This week";
  const all = await api("/api/recipes");
  // Same kind of dish first, but she can pick anything.
  const sameKind = all.filter((r) => r.component === slot.component);
  const rest = all.filter((r) => r.component !== slot.component);
  render(`
    <h1 class="text-2xl font-medium">Choose a dish</h1>
    <p class="text-sub">${slot.day} · ${MEAL_LABELS[slot.meal]} · ${SLOT_LABELS[slot.component] || slot.component}. Start typing to find it.</p>
    <div id="pick-box" class="space-y-2">
      <input class="input dish-input" placeholder="e.g. pac…" autocomplete="off">
      <div class="dish-results"></div>
    </div>
    <button id="pick-cancel" class="btn btn-outline">Cancel</button>
    <p id="pick-status" class="text-sub text-center"></p>`);
  dishSearchBox("pick-box", [...sameKind, ...rest], async (recipe) => {
    document.getElementById("pick-status").textContent = "Saving…";
    await api(`/api/menu/${menuId}/items/${slot.itemId}`, {
      method: "PUT", body: JSON.stringify({ recipe_id: recipe.id }),
    });
    showMenu();
  }, { onAddNew: (name) => showAddRecipe({
    prefillName: name,
    onSaved: async (recipe) => {
      await api(`/api/menu/${menuId}/items/${slot.itemId}`, {
        method: "PUT", body: JSON.stringify({ recipe_id: recipe.id }),
      });
      showMenu();
    },
    onCancel: () => showDishPicker(menuId, slot),
  }) });
  document.getElementById("pick-cancel").onclick = () => showDishActions(menuId, slot);
}

// ---------- Add a dish to any day/meal ----------

async function showAddToMenu(menuId, day) {
  headerNote.textContent = "This week";
  const all = await api("/api/recipes");
  const dayOptions = DAYS.map((d) => `<option ${d === day ? "selected" : ""}>${d}</option>`).join("");
  render(`
    <h1 class="text-2xl font-medium">Add a dish</h1>
    <p class="text-sub">Start typing and pick from the list</p>
    <div class="card p-4 space-y-5">
      <div id="add-box">
        <label class="font-medium block pb-1.5">Dish</label>
        <input class="input dish-input" placeholder="e.g. pac…" autocomplete="off">
        <div class="dish-results pt-1"></div>
      </div>
      <div>
        <label class="font-medium block pb-1.5">Day</label>
        <select id="add-day" class="input">${dayOptions}</select>
      </div>
      <div>
        <label class="font-medium block pb-1.5">Meal</label>
        <select id="add-meal" class="input">
          <option value="breakfast">Breakfast</option>
          <option value="lunch" selected>Lunch</option>
          <option value="snack">Snack</option>
          <option value="dinner">Dinner</option>
        </select>
      </div>
    </div>
    <button id="add-go" class="btn btn-primary">${icon("plus")} Add to the menu</button>
    <button id="add-cancel" class="btn btn-outline">Cancel</button>
    <p id="add-status" class="text-sub text-center"></p>`);
  const getPicked = dishSearchBox("add-box", all, () => {
    document.getElementById("add-status").textContent = "";
  }, { onAddNew: (name) => showAddRecipe({
    prefillName: name,
    onSaved: async (recipe) => {
      await api(`/api/menu/${menuId}/items`, {
        method: "POST",
        body: JSON.stringify({
          recipe_id: recipe.id,
          day: document.getElementById("add-day")?.value || day,
          meal_type: document.getElementById("add-meal")?.value || "lunch",
        }),
      });
      showMenu();
    },
    onCancel: () => showAddToMenu(menuId, day),
  }) });
  document.getElementById("add-cancel").onclick = showMenu;
  document.getElementById("add-go").onclick = async () => {
    const recipe = getPicked();
    const status = document.getElementById("add-status");
    if (!recipe) { status.textContent = "Pick a dish from the list first."; return; }
    status.textContent = "Adding…";
    await api(`/api/menu/${menuId}/items`, {
      method: "POST",
      body: JSON.stringify({
        recipe_id: recipe.id,
        day: document.getElementById("add-day").value,
        meal_type: document.getElementById("add-meal").value,
      }),
    });
    showMenu();
  };
}

// ---------- PDF export ----------

// Fetch a PDF from the server, then offer it to the phone's share sheet.
// Falls back to a download where Web Share isn't available (any plain http://
// origin, which is why this only fully works once the app is on HTTPS).
async function sharePdf(url, body, filename, title, statusEl) {
  if (statusEl) statusEl.textContent = "Making the PDF…";
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (!res.ok) throw new Error(`Request failed (${res.status})`);
    const blob = await res.blob();
    const file = new File([blob], filename, { type: "application/pdf" });
    if (navigator.canShare && navigator.canShare({ files: [file] })) {
      try {
        await navigator.share({ files: [file], title });
        if (statusEl) statusEl.textContent = "Shared.";
        return;
      } catch (_) { /* cancelled — fall through to download */ }
    }
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(objectUrl);
    if (statusEl) statusEl.textContent = "PDF downloaded — attach it in WhatsApp to share.";
  } catch (err) {
    if (statusEl) statusEl.textContent = "Something went wrong: " + err.message;
  }
}

function showPdfExport(menu) {
  headerNote.textContent = "Export";
  render(`
    <h1 class="text-2xl font-medium">Export as PDF</h1>
    <div class="card p-4 space-y-5">
      <div>
        <label class="font-medium block pb-1.5">Title</label>
        <input id="pdf-title" value="Weekly menu" class="input">
      </div>
      <div>
        <label class="font-medium block pb-1.5">For (optional)</label>
        <input id="pdf-recipient" class="input" placeholder="e.g. Grandma's kitchen">
      </div>
      <label class="flex items-center gap-3 font-medium">
        <input id="pdf-grocery" type="checkbox" class="w-5 h-5 accent-[#2f7a68]">
        Also include the grocery list
      </label>
    </div>
    <button id="pdf-go" class="btn btn-primary">${icon("share-2")} Make &amp; share PDF</button>
    <button id="pdf-back" class="btn btn-outline">${icon("arrow-left")} Back</button>
    <p id="pdf-status" class="text-sub text-center"></p>`);
  document.getElementById("pdf-back").onclick = () => renderMenu(menu);
  document.getElementById("pdf-go").onclick = () => sharePdf(
    `/api/menu/${menu.menu_id}/pdf`,
    {
      title: document.getElementById("pdf-title").value.trim() || "Weekly menu",
      recipient: document.getElementById("pdf-recipient").value.trim(),
      include_grocery: document.getElementById("pdf-grocery").checked,
    },
    "weekly-menu.pdf", "Weekly menu", document.getElementById("pdf-status"),
  );
}

// ---------- Recipe view ----------

async function showRecipe(recipeId, slot, backTo) {
  const r = await api(`/api/recipes/${recipeId}`);
  headerNote.textContent = "Recipe";
  const back = backTo || showMenu;
  const ingredients = r.ingredients.map((i) => `<li class="py-1.5 border-b border-line/50 last:border-0">${esc(i)}</li>`).join("");
  render(`
    <div class="card p-5 space-y-4">
      <div class="flex items-start justify-between gap-2">
        <h1 class="text-2xl font-medium">${esc(r.name)} ${familyBadge(r)}</h1>
        <button id="fav" class="!min-h-0 p-1 ${r.favorite ? "text-accent" : "text-line"}">${icon("heart", "w-7 h-7")}</button>
      </div>
      <p class="text-sub flex items-center gap-2">
        ${r.store_bought ? `${icon("shopping-bag", "icon w-4 h-4")} Bought, not cooked`
                         : `${icon("clock", "icon w-4 h-4")} ${r.prep_minutes} min`}
        · ${esc(dietLabel(r))}</p>
      ${r.note ? `<p class="note">${esc(r.note)}</p>` : ""}
      ${r.tags.length ? `<p class="text-sub text-sm">${esc(r.tags.join(" · "))}</p>` : ""}
      <div>
        <h2 class="font-medium pb-1">You need</h2>
        <ul>${ingredients}</ul>
      </div>
      ${r.steps.length ? `
      <div>
        <h2 class="font-medium pb-1">How to make it</h2>
        <ol class="space-y-2 leading-relaxed">
          ${r.steps.map((s, i) => `
            <li class="flex gap-3">
              <span class="bg-mint text-ink rounded-full w-7 h-7 flex-none flex items-center justify-center text-sm font-medium">${i + 1}</span>
              <span>${esc(s)}</span>
            </li>`).join("")}
        </ol>
      </div>` : ""}
    </div>
    ${r.youtube ? `<a href="${esc(r.youtube)}" target="_blank" class="block"><span class="btn btn-outline">${icon("play")} Watch on YouTube</span></a>` : ""}
    <button id="back" class="btn btn-outline">${icon("arrow-left")} Back</button>`);
  document.getElementById("fav").onclick = async (e) => {
    const res = await api(`/api/favorites/${r.id}`, { method: "POST" });
    e.currentTarget.className = `!min-h-0 p-1 ${res.favorite ? "text-accent" : "text-line"}`;
  };
  document.getElementById("back").onclick = () => back();
}

// ---------- Grocery list ----------

async function showGrocery() {
  headerNote.textContent = "Grocery";
  const menu = await api("/api/menu/latest");
  if (!menu.menu_id) {
    render(`
      <h1 class="text-2xl font-medium">Grocery list</h1>
      <p class="card p-4 text-sub">Plan the week first — the list is made from the menu.</p>
      <button id="go-plan" class="btn btn-primary">${icon("sparkles")} Plan the week</button>`);
    document.getElementById("go-plan").onclick = showPlanStep1;
    return;
  }
  let data = await api(`/api/menu/${menu.menu_id}/grocery`);
  if (!data.items.length) {
    data = await api(`/api/menu/${menu.menu_id}/grocery`, { method: "POST" });
  }
  renderGrocery(menu.menu_id, data);
}

function groceryQty(i) {
  if (i.source === "staple") return "for the week";
  if (i.unit === "dishes") return `${i.quantity} ${i.quantity === 1 ? "dish" : "dishes"}`;
  return `${i.quantity % 1 === 0 ? i.quantity : i.quantity.toFixed(1)} ${i.unit}`.trim();
}

function renderGrocery(menuId, data) {
  const categories = [...new Set(data.items.map((i) => i.category))];
  const groups = categories.map((c) => {
    const rows = data.items.filter((i) => i.category === c).map((i) => `
      <div class="g-row py-1">
        <div class="flex items-center gap-2">
          <button data-id="${i.id}" class="g-item flex-1 flex items-center gap-3 text-left py-2.5 !min-h-0">
            <span class="check w-7 h-7 rounded-lg border-2 flex-none flex items-center justify-center
              ${i.have_already ? "bg-accent border-accent text-white" : "border-line bg-surface"}">
              ${i.have_already ? icon("check", "w-4 h-4") : ""}</span>
            <span class="g-label flex-1 capitalize ${i.have_already ? "line-through text-sub" : ""}">${esc(i.ingredient_name)}</span>
          </button>
          ${(i.used_in || []).length
            ? `<button data-id="${i.id}" class="g-why text-sub text-sm flex items-center gap-1 !min-h-0 px-2 py-2.5">
                 ${groceryQty(i)} ${icon("chevron-down", "icon w-4 h-4")}</button>`
            : `<span class="text-sub text-sm px-2">${groceryQty(i)}</span>`}
          <button data-id="${i.id}" class="g-edit text-sub !min-h-0 p-2" aria-label="Edit ${esc(i.ingredient_name)}">
            ${icon("pencil", "icon w-4 h-4")}</button>
        </div>
        <div id="why-${i.id}" class="hidden pl-10 pb-2">
          <p class="text-sub text-sm">Needed for:</p>
          <ul class="text-sm">${(i.used_in || []).map((d) => `<li class="py-0.5">${esc(d)}</li>`).join("")}</ul>
        </div>
      </div>`).join("");
    return `
      <div class="card p-4">
        <p class="text-accent text-sm font-medium capitalize pb-1">${c}</p>
        <div class="divide-y divide-line/60">${rows}</div>
      </div>`;
  }).join("");
  render(`
    <h1 class="text-2xl font-medium">Grocery list</h1>
    <p class="text-sub">For ${data.people} ${data.people === 1 ? "person" : "people"} this week. Tick what you already have</p>
    <button id="g-pdf" class="btn btn-primary">${icon("share-2")} Share as PDF</button>
    <button id="g-add" class="btn btn-outline">${icon("plus")} Add an item</button>
    <p id="g-status" class="text-sub text-sm text-center"></p>
    <div class="space-y-3">${groups}</div>
    <button id="rebuild" class="btn btn-outline">${icon("refresh-cw")} Rebuild from menu</button>`);

  document.querySelectorAll(".g-item").forEach((el) =>
    el.addEventListener("click", async () => {
      const res = await api(`/api/grocery/${el.dataset.id}/toggle`, { method: "POST" });
      const box = el.querySelector(".check");
      const label = el.querySelector(".g-label");
      box.className = `check w-7 h-7 rounded-lg border-2 flex-none flex items-center justify-center ${res.have_already ? "bg-accent border-accent text-white" : "border-line bg-surface"}`;
      box.innerHTML = res.have_already ? icon("check", "w-4 h-4") : "";
      label.className = `g-label flex-1 capitalize ${res.have_already ? "line-through text-sub" : ""}`;
      const item = data.items.find((i) => String(i.id) === el.dataset.id);
      if (item) item.have_already = res.have_already;
      lucide.createIcons();
    }));
  document.querySelectorAll(".g-edit").forEach((el) =>
    el.addEventListener("click", () =>
      showGroceryForm(menuId, data.items.find((i) => String(i.id) === el.dataset.id))));
  document.querySelectorAll(".g-why").forEach((el) =>
    el.addEventListener("click", () => {
      const panel = document.getElementById(`why-${el.dataset.id}`);
      const open = panel.classList.toggle("hidden");
      el.querySelector("i, svg")?.style.setProperty("transform", open ? "" : "rotate(180deg)");
    }));
  document.getElementById("g-add").onclick = () => showGroceryForm(menuId, null);
  document.getElementById("g-pdf").onclick = () => sharePdf(
    `/api/menu/${menuId}/grocery/pdf`, {}, "grocery-list.pdf", "Grocery list",
    document.getElementById("g-status"),
  );
  document.getElementById("rebuild").onclick = async () => {
    if (!confirm("Rebuild the list from the menu? Items you added by hand will be lost.")) return;
    const data2 = await api(`/api/menu/${menuId}/grocery`, { method: "POST" });
    renderGrocery(menuId, data2);
  };
}

function showGroceryForm(menuId, item) {
  headerNote.textContent = "Grocery";
  const it = item || { ingredient_name: "", quantity: 1, unit: "", category: "" };
  const options = GROCERY_CATEGORIES.map(
    (c) => `<option ${c === it.category ? "selected" : ""}>${c}</option>`).join("");
  render(`
    <h1 class="text-2xl font-medium">${item ? "Edit item" : "Add an item"}</h1>
    <div class="card p-4 space-y-5">
      <div>
        <label class="font-medium block pb-1.5">Item</label>
        <input id="g-name" value="${esc(it.ingredient_name)}" class="input" placeholder="e.g. mangoes">
      </div>
      <div class="flex gap-3">
        <div class="flex-1">
          <label class="font-medium block pb-1.5">How many</label>
          <input id="g-qty" type="number" min="0" step="0.5" value="${it.quantity}" class="input">
        </div>
        <div class="flex-1">
          <label class="font-medium block pb-1.5">Unit</label>
          <input id="g-unit" value="${esc(it.unit)}" class="input" placeholder="kg / pieces">
        </div>
      </div>
      <div>
        <label class="font-medium block pb-1.5">Group</label>
        <select id="g-cat" class="input capitalize"><option value="">Choose for me</option>${options}</select>
      </div>
    </div>
    <button id="g-save" class="btn btn-primary">${icon("check")} Save</button>
    ${item ? `<button id="g-del" class="btn btn-danger">${icon("trash-2")} Remove from list</button>` : ""}
    <button id="g-cancel" class="btn btn-outline">Cancel</button>`);
  const back = async () => {
    const fresh = await api(`/api/menu/${menuId}/grocery`);
    renderGrocery(menuId, fresh);
  };
  document.getElementById("g-cancel").onclick = back;
  document.getElementById("g-save").onclick = async () => {
    const payload = {
      ingredient_name: document.getElementById("g-name").value.trim(),
      quantity: Number(document.getElementById("g-qty").value) || 1,
      unit: document.getElementById("g-unit").value.trim(),
      category: document.getElementById("g-cat").value,
    };
    if (!payload.ingredient_name) { alert("Please type the item name."); return; }
    if (item) await api(`/api/grocery/${item.id}`, { method: "PUT", body: JSON.stringify(payload) });
    else await api(`/api/menu/${menuId}/grocery/items`, { method: "POST", body: JSON.stringify(payload) });
    back();
  };
  if (item) document.getElementById("g-del").onclick = async () => {
    await api(`/api/grocery/${item.id}`, { method: "DELETE" });
    back();
  };
}

// ---------- Healthy snacks (instant) ----------

function suggestionCards(suggestions, backTo) {
  const html = suggestions.map((s) => `
    <button data-id="${s.recipe.id}" class="sugg-card card w-full text-left p-4">
      <p class="font-medium text-lg">${esc(s.recipe.name)}</p>
      <p class="text-sub text-sm">${esc(s.why)}</p>
    </button>`).join("");
  return {
    html,
    wire: () => document.querySelectorAll(".sugg-card").forEach((el) =>
      el.addEventListener("click", () => showRecipe(Number(el.dataset.id), null, backTo))),
  };
}

// Snacks: pick healthy or unhealthy first, then see the whole list of each.
function showSnacks() {
  headerNote.textContent = "Snacks";
  const choice = (id, ic, label, sub) => `
    <button id="${id}" class="card w-full flex items-center gap-4 p-4 text-left">
      <span class="bg-mint text-accent rounded-2xl p-3">${icon(ic, "icon w-6 h-6")}</span>
      <span class="flex-1">
        <span class="block font-medium text-lg">${label}</span>
        <span class="block text-sub text-sm">${sub}</span>
      </span>
      ${icon("chevron-right", "icon text-sub")}
    </button>`;
  render(`
    <h1 class="text-2xl font-medium">Snacks</h1>
    <p class="text-sub">What are you in the mood for?</p>
    <div class="space-y-3 pt-1">
      ${choice("s-healthy", "apple", "Healthy snacks", "The everyday good ones")}
      ${choice("s-unhealthy", "cookie", "Treats", "For when you fancy something")}
    </div>`);
  document.getElementById("s-healthy").onclick = () => showSnackList("healthy");
  document.getElementById("s-unhealthy").onclick = () => showSnackList("unhealthy");
}

async function showSnackList(kind) {
  headerNote.textContent = "Snacks";
  const res = await api(`/api/snacks?kind=${kind}`);
  const title = kind === "healthy" ? "Healthy snacks" : "Treats";
  const cards = res.suggestions.map((s) => `
    <div class="card p-4 flex items-center gap-3">
      <button data-id="${s.recipe.id}" class="snack-open flex-1 text-left !min-h-0">
        <p class="font-medium text-lg">${esc(s.recipe.name)} ${familyBadge(s.recipe)}</p>
        <p class="text-sub text-sm">${esc(s.why)}</p>
      </button>
      ${s.recipe.source === "user"
        ? `<button data-id="${s.recipe.id}" class="snack-edit text-sub !min-h-0 p-2"
             aria-label="Edit ${esc(s.recipe.name)}">${icon("pencil", "icon w-4 h-4")}</button>`
        : ""}
    </div>`).join("");
  render(`
    <h1 class="text-2xl font-medium">${title}</h1>
    <p class="text-sub">${res.suggestions.length} to choose from. Tap one to see it${
      kind === "healthy" ? "" : " — treats are fine now and then"}.</p>
    <div class="space-y-3">${cards || '<p class="card p-4 text-sub">Nothing here yet. Add your first one below.</p>'}</div>
    <button id="add-snack" class="btn btn-primary">${icon("plus")} Add a snack</button>
    <button id="snack-back" class="btn btn-outline">${icon("arrow-left")} Back</button>`);
  document.querySelectorAll(".snack-open").forEach((el) =>
    el.addEventListener("click", () =>
      showRecipe(Number(el.dataset.id), null, () => showSnackList(kind))));
  document.querySelectorAll(".snack-edit").forEach((el) =>
    el.addEventListener("click", () => showEditRecipe(Number(el.dataset.id), kind)));
  document.getElementById("snack-back").onclick = showSnacks;
  document.getElementById("add-snack").onclick = () => showAddRecipe({
    heading: "Add a snack",
    prefillMeal: "snack",
    prefillSnackType: kind,
    onSaved: () => showSnackList(kind),
    onCancel: () => showSnackList(kind),
  });
}

// Edit or delete a dish she added herself.
async function showEditRecipe(recipeId, snackKind) {
  const r = await api(`/api/recipes/${recipeId}`);
  showAddRecipe({
    heading: `Edit ${r.name}`,
    recipe: r,
    prefillName: r.name,
    prefillMeal: r.meal_type,
    prefillSnackType: r.snack_type || snackKind,
    onSaved: () => (snackKind ? showSnackList(snackKind) : showHome()),
    onCancel: () => (snackKind ? showSnackList(snackKind) : showHome()),
  });
}

// ---------- Add my recipe ----------

function showAddRecipe(opts = {}) {
  const existing = opts.recipe || {};
  const isEdit = Boolean(existing.id);
  headerNote.textContent = isEdit ? "Edit recipe" : "Add recipe";
  const meal = opts.prefillMeal || existing.meal_type || "lunch";
  const diet = Array.isArray(existing.diet) ? existing.diet[0] : existing.diet;
  const snackType = opts.prefillSnackType || existing.snack_type || "healthy";
  const freq = existing.frequency || "weekly";
  const mealOption = (value, label) =>
    `<option value="${value}" ${meal === value ? "selected" : ""}>${label}</option>`;
  const freqOption = (value, label) =>
    `<option value="${value}" ${freq === value ? "selected" : ""}>${label}</option>`;
  const snackTypeChip = (value, label) => `
    <label class="flex-1">
      <input type="radio" name="snack-type" value="${value}" class="peer hidden" ${snackType === value ? "checked" : ""}>
      <span class="flex items-center justify-center rounded-xl border border-line peer-checked:border-accent peer-checked:bg-accent-tint peer-checked:text-accent font-medium cursor-pointer px-2 py-3 h-full">${label}</span>
    </label>`;
  render(`
    <h1 class="text-2xl font-medium">${esc(opts.heading || "Add my recipe")}</h1>
    <p class="text-sub">Just the name and main ingredients are enough — the rest is optional.</p>
    <div class="card p-4 space-y-5">
      <div>
        <label class="font-medium block pb-1.5">Dish name</label>
        <input id="r-name" class="input" placeholder="e.g. Chena Astram" value="${esc(opts.prefillName || existing.name || "")}">
      </div>
      <div>
        <label class="font-medium block pb-1.5">Main ingredients</label>
        <textarea id="r-ing" rows="3" class="input" placeholder="e.g. yam, coconut, moru — commas or one per line">${esc((existing.ingredients || []).join("\n"))}</textarea>
      </div>
      <div class="flex gap-3">
        <div class="flex-1">
          <label class="font-medium block pb-1.5">Meal</label>
          <select id="r-meal" class="input">
            ${mealOption("lunch", "Lunch")}
            ${mealOption("breakfast", "Breakfast")}
            ${mealOption("dinner", "Dinner")}
            ${mealOption("snack", "Snack")}
          </select>
        </div>
        <div class="flex-1">
          <label class="font-medium block pb-1.5">Minutes</label>
          <input id="r-prep" type="number" min="0" step="5" class="input" placeholder="30" value="${existing.prep_minutes ?? ""}">
        </div>
      </div>
      <div>
        <label class="font-medium block pb-1.5">Food type</label>
        <select id="r-diet" class="input">
          <option value="veg" ${diet === "veg" ? "selected" : ""}>Vegetarian</option>
          <option value="non-veg" ${diet === "non-veg" ? "selected" : ""}>Non-veg</option>
        </select>
      </div>
      <div>
        <label class="font-medium block pb-1.5">How to make it (optional)</label>
        <textarea id="r-steps" rows="3" class="input" placeholder="Short steps in your own words">${esc((existing.steps || []).join("\n"))}</textarea>
      </div>
      <div>
        <label class="font-medium block pb-1.5">YouTube link (optional)</label>
        <input id="r-youtube" class="input" placeholder="https://..." value="${esc(existing.youtube || "")}">
      </div>
      <div id="r-snack-fields" class="${meal === "snack" ? "" : "hidden"} space-y-5">
        <div>
          <label class="font-medium block pb-1.5">Is it a healthy snack?</label>
          <div class="flex gap-2">${snackTypeChip("healthy", "Healthy")}${snackTypeChip("unhealthy", "A treat")}</div>
        </div>
        <div>
          <label class="font-medium block pb-1.5">How often do you have it?</label>
          <select id="r-frequency" class="input">
            ${freqOption("weekly", "Every week")}
            ${freqOption("monthly", "Once a month")}
            ${freqOption("quarterly", "Once in 3 months")}
          </select>
        </div>
      </div>
    </div>
    <button id="r-save" class="btn btn-primary">${icon("check")} Save</button>
    ${isEdit ? `<button id="r-delete" class="btn btn-danger">${icon("trash-2")} Remove this dish</button>` : ""}
    <button id="r-cancel" class="btn btn-outline">Cancel</button>`);

  // The snack questions only make sense for snacks.
  document.getElementById("r-meal").addEventListener("change", (e) =>
    document.getElementById("r-snack-fields").classList.toggle("hidden",
      e.target.value !== "snack"));

  document.getElementById("r-cancel").onclick = opts.onCancel || showHome;
  if (isEdit) document.getElementById("r-delete").onclick = async () => {
    if (!confirm(`Remove ${existing.name} completely?`)) return;
    await api(`/api/recipes/${existing.id}`, { method: "DELETE" });
    (opts.onSaved || showHome)();
  };
  document.getElementById("r-save").onclick = async () => {
    const name = document.getElementById("r-name").value.trim();
    const ingredients = splitList(document.getElementById("r-ing").value);
    if (!name) { alert("Please type the dish name."); return; }
    if (!ingredients.length) { alert("List at least one main ingredient."); return; }
    const mealValue = document.getElementById("r-meal").value;
    const payload = {
      name,
      ingredients,
      meal_type: mealValue,
      diet: document.getElementById("r-diet").value,
      prep_minutes: Number(document.getElementById("r-prep").value) || null,
      steps: document.getElementById("r-steps").value.trim(),
      youtube: document.getElementById("r-youtube").value.trim(),
      frequency: mealValue === "snack" ? document.getElementById("r-frequency").value : "",
      snack_type: mealValue === "snack"
        ? (document.querySelector('input[name="snack-type"]:checked')?.value || "healthy") : "",
    };
    try {
      const recipe = isEdit
        ? await api(`/api/recipes/${existing.id}`, { method: "PUT", body: JSON.stringify(payload) })
        : await api("/api/recipes", { method: "POST", body: JSON.stringify(payload) });
      if (opts.onSaved) opts.onSaved(recipe);
      else showRecipe(recipe.id, null, showHome);
    } catch (err) {
      alert("Could not save: " + err.message);
    }
  };
}

// ---------- Setup check ----------

async function showSetup() {
  headerNote.textContent = "Setup";
  const row = (label, ok, detail) => `
    <div class="flex items-start gap-3">
      <span class="${ok ? "text-accent" : "text-danger"}">${icon(ok ? "circle-check" : "circle-x", "w-6 h-6")}</span>
      <div>
        <p class="font-medium">${label}</p>
        ${detail ? `<p class="text-sub text-sm">${esc(detail)}</p>` : ""}
      </div>
    </div>`;
  render(`<p class="card p-6 text-sub">Checking…</p>`);
  try {
    const h = await api("/api/health");
    render(`
      <h1 class="text-2xl font-medium">Setup check</h1>
      <div class="card p-5 space-y-4">
        ${row("Server is running", true)}
        ${row("Recipe book loaded", h.database.recipes > 0, `${h.database.recipes} recipes ready`)}
        ${row("AI helper", h.ai.reachable && h.ai.model_ready, h.ai.detail || `${h.ai.model} is ready`)}
      </div>
      ${backupCard()}`);
  } catch (err) {
    render(`<div class="card p-5">${row("Server is running", false, "Could not reach the app.")}</div>`);
  }
}

// Everything lives on one server. This is the only way to get a copy of it off
// that server, so it is worth keeping easy to find.
function backupCard() {
  return `
    <div class="card p-5 space-y-3">
      <p class="font-medium">Keep a copy of everything</p>
      <p class="text-sub text-sm">Saves the recipes, the family profiles and the
        saved menus into one file. Keep it somewhere other than this app, then
        nothing is lost if the app ever goes away.</p>
      <a href="/api/backup" download class="btn btn-outline w-full">
        ${icon("download", "icon w-5 h-5")} Download a backup
      </a>
    </div>`;
}

// Coming back to the app after a while, the session may have lapsed. Check as
// soon as it is on screen, so she meets the PIN screen rather than a menu that
// fails the moment she taps it.
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "visible") return;
  fetch("/api/session", { cache: "no-store" })
    .then((res) => { if (res.status === 401) location.href = "/login"; })
    .catch(() => {});  // offline: leave the screen alone
});

showWhoAreYou();
