"""
StatementSense — FastAPI Backend
Serves the RenewalSense, ScreentimeSense, CalendarSense, and SubscriptionSense
engines as REST APIs.
"""

import os
import sys
import logging
import traceback
from pathlib import Path
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("StatementSense")

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

# ── Subscription router: graceful import ──
# If the subscription engine fails to load (missing deps, import errors),
# the rest of the app must still start. Log the exact error for debugging.
_subscription_import_error = None
try:
    from .api.subscription import router as subscription_router
    logger.info("SubscriptionSense router loaded successfully")
except Exception as e:
    _subscription_import_error = traceback.format_exc()
    subscription_router = None
    logger.error(f"SubscriptionSense router FAILED to import:\n{_subscription_import_error}")

app = FastAPI(
    title="StatementSense API",
    description="Intelligent Subscription Management — RenewalSense, ScreentimeSense, CalendarSense, SubscriptionSense",
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

if subscription_router is not None:
    app.include_router(subscription_router)
    logger.info("SubscriptionSense router MOUNTED at /api/subscription")
else:
    logger.warning("SubscriptionSense router NOT mounted — see error above")


@app.get("/")
def root():
    features = ["RenewalSense", "ScreentimeSense", "CalendarSense"]
    if subscription_router is not None:
        features.append("SubscriptionSense")
    return {
        "app": "StatementSense",
        "version": "1.0.0",
        "features": features,
        "subscription_status": "ok" if subscription_router else "failed",
        "docs": "/docs"
    }


@app.get("/api/debug/subscription-status")
def subscription_debug():
    """Diagnostic endpoint to show why SubscriptionSense failed to load."""
    return {
        "loaded": subscription_router is not None,
        "error": _subscription_import_error,
        "python_path": sys.path,
        "cwd": os.getcwd(),
        "capstone_exists": os.path.isdir("Capstone"),
        "capstone_inner_exists": os.path.isdir("Capstone/Capstone"),
        "capstone_init": os.path.isfile("Capstone/__init__.py"),
        "capstone_inner_init": os.path.isfile("Capstone/Capstone/__init__.py"),
        "capstone_revised_exists": os.path.isdir("capstone_revised"),
        "detection_alg_exists": os.path.isfile("subscription_detection_alg.py"),
    }


# ── Cloud Run entry point ──
# When run directly (not via `uvicorn backend.app.main:app`), start the server
# bound to 0.0.0.0 on the PORT that Cloud Run provides.
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

