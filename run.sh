#!/bin/sh
# One-click launcher for the Family Meal Planner (Mac/Linux)

if [ ! -f .env ]; then
    echo "No .env file found. Copy .env.example to .env and paste your"
    echo "Gemini API key after GEMINI_API_KEY="
    exit 1
fi

echo "Starting the meal planner..."
(sleep 2; open http://localhost:8000 2>/dev/null || xdg-open http://localhost:8000 2>/dev/null) &
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
