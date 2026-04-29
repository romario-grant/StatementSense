"""
StatementSense — FastAPI Backend
Serves the RenewalSense, ScreentimeSense, and CalendarSense engines as REST APIs.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root (StatementSense/) — this must happen BEFORE
# any engine imports so that GEMINI_API_KEY is available globally.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/app/main.py → StatementSense/
load_dotenv(PROJECT_ROOT / ".env")

# Store project root in env so engines can find credential files
os.environ.setdefault("STATEMENTSENSE_ROOT", str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.renewal import router as renewal_router
from .api.screentime import router as screentime_router
from .api.calendar import router as calendar_router

app = FastAPI(
    title="StatementSense API",
    description="Intelligent Subscription Management — RenewalSense, ScreentimeSense, CalendarSense",
    version="1.0.0"
)

# Allow frontend to connect — local dev + Cloud Run / Firebase App Hosting
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://statementsense-84a99.web.app",
        "https://statementsense-84a99.firebaseapp.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(renewal_router)
app.include_router(screentime_router)
app.include_router(calendar_router)


@app.get("/")
def root():
    return {
        "app": "StatementSense",
        "version": "1.0.0",
        "features": ["RenewalSense", "ScreentimeSense", "CalendarSense"],
        "docs": "/docs"
    }


# ── Cloud Run entry point ──
# When run directly (not via `uvicorn backend.app.main:app`), start the server
# bound to 0.0.0.0 on the PORT that Cloud Run provides.
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

