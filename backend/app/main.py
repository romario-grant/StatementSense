"""
FastAPI application entry point for StatementSense. Wires the RenewalSense,
ScreentimeSense, CalendarSense, and SubscriptionSense engines onto a single
ASGI app and exposes them under the /api namespace.
"""

import os
import sys
import logging
import traceback
from pathlib import Path
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("StatementSense")

# Environment variables are loaded before any engine modules import so that
# credentials such as GEMINI_API_KEY are available at module-import time.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Engines resolve credential file paths relative to this root.
os.environ.setdefault("STATEMENTSENSE_ROOT", str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.renewal import router as renewal_router
from .api.screentime import router as screentime_router
from .api.calendar import router as calendar_router

# Subscription router import is isolated so that an import failure in the
# subscription engine does not prevent the other routers from being served.
# The traceback is preserved for inspection through the debug endpoint below.
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

# Permissive CORS covers local development as well as Cloud Run and Firebase
# App Hosting frontends.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    """Report whether the SubscriptionSense router loaded and, if not, the import traceback."""
    return {
        "loaded": subscription_router is not None,
        "error": _subscription_import_error,
        "python_path": sys.path,
        "cwd": os.getcwd(),
        "extraction_module_exists": os.path.isdir("backend/app/extraction"),
        "shared_helpers_exist": os.path.isdir("backend/app/shared"),
        "currency_normaliser_exists": os.path.isfile("backend/app/shared/currency_normaliser.py"),
        "trial_classifier_exists": os.path.isfile("backend/app/shared/trial_classifier.py"),
        "detection_alg_exists": os.path.isfile("subscription_detection_alg.py"),
    }


# Cloud Run entry point: bind to 0.0.0.0 on the PORT supplied by the platform
# when invoked as a script rather than through an external uvicorn command.
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
