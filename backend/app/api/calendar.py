"""CalendarSense API endpoints. Exposes the calendar engine through a combined
analysis endpoint and a set of progressive-loading endpoints that the frontend
calls in sequence to stream results as they become available.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
import asyncio
import concurrent.futures

from ..engines.calendar_engine import (
    analyze_calendar,
    fetch_events,
    classify_and_detect,
    compute_savings,
    create_reminders,
)

router = APIRouter(prefix="/api/calendar", tags=["CalendarSense"])

class SubscriptionInput(BaseModel):
    name: str
    cost: float
    renewal_day: int | None = None  # Day of month (1-31) used for smart timing of pause/resume suggestions.

class CalendarRequest(BaseModel):
    home_location: str
    subscriptions: List[SubscriptionInput]
    access_token: str | None = None

# Aggregated analysis endpoint

@router.post("/analyze")
async def analyze_user_calendar(request: CalendarRequest):
    """Run the full calendar analysis pipeline in a single call and return travel periods matched against local subscriptions."""
    try:
        if not request.home_location:
            raise ValueError("Home location is required")

        subs_list = [{"name": s.name, "cost": s.cost, "renewal_day": s.renewal_day} for s in request.subscriptions]

        # The calendar engine performs synchronous network I/O, so it is dispatched
        # to a thread pool to keep the event loop responsive.
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = await loop.run_in_executor(
                pool,
                analyze_calendar,
                request.home_location,
                subs_list,
                request.access_token
            )

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Progressive loading endpoints
#
# The frontend calls these endpoints in stages so it can display partial
# results while later, heavier stages still run. Each stage is independent
# and accepts the output of the previous stage as input.

class EventsRequest(BaseModel):
    access_token: str | None = None

@router.post("/events")
async def get_calendar_events(request: EventsRequest):
    """Return the user's upcoming Google Calendar events for downstream classification."""
    try:
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = await loop.run_in_executor(
                pool, fetch_events, request.access_token
            )
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ClassifyRequest(BaseModel):
    events: list
    home_location: str
    subscriptions: List[SubscriptionInput]

@router.post("/classify")
async def classify_subscriptions(request: ClassifyRequest):
    """Classify each subscription as local or portable and detect away-from-home travel periods in the supplied events."""
    try:
        if not request.home_location:
            raise ValueError("Home location is required")
        if not request.subscriptions:
            raise ValueError("At least one subscription is required")

        subs_list = [
            {"name": s.name, "cost": s.cost, "renewal_day": s.renewal_day}
            for s in request.subscriptions
        ]

        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = await loop.run_in_executor(
                pool, classify_and_detect,
                request.events, request.home_location, subs_list
            )
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SavingsRequest(BaseModel):
    away_periods: list
    processed_subscriptions: list
    local_currency: str | None = "JMD"
    exchange_rate: float | None = None

@router.post("/savings")
async def get_savings(request: SavingsRequest):
    """Compute potential savings and Places API alternatives for local subscriptions that overlap with travel periods."""
    try:
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = await loop.run_in_executor(
                pool, compute_savings,
                request.away_periods,
                request.processed_subscriptions,
                request.local_currency or "JMD",
                request.exchange_rate,
            )
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class RemindersRequest(BaseModel):
    access_token: str
    recommendations: list  # Recommendations to create reminders for.

@router.post("/reminders")
async def add_calendar_reminders(request: RemindersRequest):
    """Create Google Calendar reminder events for the cancel, pause, and restart dates in the supplied recommendations."""
    try:
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = await loop.run_in_executor(
                pool, create_reminders,
                request.access_token, request.recommendations
            )
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
