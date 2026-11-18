# Family Meal Planner

A phone-first web app that plans a week of Kerala family meals around each person's diet and health needs, then turns the plan into a grocery list.

![Home screen](docs/home.png) ![Weekly menu](docs/menu.png)

## The problem

Planning a week of meals for a family is a daily chore, and harder when one person has diabetes, another has high cholesterol, and a third is vegetarian. This app was built for a real family, with an elderly primary user in mind: big buttons, one action per screen, and a layout that works on a phone.

## What it does

- **Family profiles** with diet and health conditions that become hard rules in the plan (for example, no sugary dishes for diabetes, limited fried fish for cholesterol).
- **Weekly menu** of full plates (breakfast, lunch, snack, dinner), built by Gemini AI and checked by a rule engine that enforces real food logic: sambar with idli, no rice at dinner, no fish with curd.
- **Edit by hand:** tap any dish to see the recipe, swap it, choose another, or remove it.
- **Grocery list** grouped by shop section, editable, and shareable as a checklist.
- **Snacks, own recipes, PDF export**, and installable on a phone's home screen.
- **Private by default:** the real family copy sits behind a strong PIN with lockout and idle timeout.

## Try it

**Live demo: https://family-meal-planner.azurewebsites.net**

No sign-up or install needed. Open the link, pick one of the four sample people (all invented), and tap **Plan the week**. The first load can take about 30 seconds while the server wakes up.

The demo is for visitors, so it works differently from the private family version: there is no PIN, your changes are wiped every night, and AI-built menus are limited each day (3 per visitor). After that, the app still builds menus with its own rule engine.

## How it was built

I directed Claude Code (Anthropic's AI coding assistant) to write the app, describing what the family needed and reviewing the results. I made the product decisions and tested with real use; I am not a traditional developer.

- **Python and FastAPI** backend, **SQLite** database, plain HTML/JavaScript with Tailwind for the interface
- **Google Gemini API** for the weekly plan, with a retry and a rule-based fallback when the AI fails
- **Microsoft Azure App Service** for hosting, with automatic deploys from GitHub
- Security: server-side PIN gate, brute-force lockout, signed expiring session cookies, secrets kept in environment variables

## Run it yourself

```
pip install -r requirements.txt
cp .env.example .env        # then add GEMINI_API_KEY and APP_PIN
python -m uvicorn app.main:app --port 8000
```

To run the public demo version instead, set `DEMO_MODE=1` (see `.env.example`).
