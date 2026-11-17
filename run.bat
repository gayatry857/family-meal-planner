@echo off
REM One-click launcher for the Family Meal Planner (Windows)

if not exist ".env" (
    echo No .env file found. Copy .env.example to .env and paste your
    echo Gemini API key after GEMINI_API_KEY=
    pause
    exit /b 1
)

echo Starting the meal planner...
start "" http://localhost:8000
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
