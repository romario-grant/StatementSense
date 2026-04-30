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
)

router = APIRouter(prefix="/api/calendar", tags=["CalendarSense"])

class SubscriptionInput(BaseModel):
    name: str
    cost: float

class CalendarRequest(BaseModel):
    home_location: str
    subscriptions: List[SubscriptionInput]
    access_token: str | None = None

# ── Legacy monolithic endpoint (backward compatible) ──

@router.post("/analyze")
async def analyze_user_calendar(request: CalendarRequest):
    """
    Connect to Google Calendar via OAuth, grab future travel dates, 
    and compare against local subscriptions.
    """
    try:
        if not request.home_location:
            raise ValueError("Home location is required")
            
        subs_list = [{"name": s.name, "cost": s.cost} for s in request.subscriptions]
        
        # Run in thread pool because it's a synchronous blocking operation
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


# ══════════════════════════════════════════════════════════════════════════════
# Progressive Loading Endpoints — Phase 1, 2, 3
# ══════════════════════════════════════════════════════════════════════════════

class EventsRequest(BaseModel):
    access_token: str | None = None

@router.post("/events")
async def get_calendar_events(request: EventsRequest):
    """Phase 1: Fetch calendar events only (~2s). Called on page load."""
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
    """Phase 2: Classify subs + detect travel in parallel (~10s). Called on Analyze click."""
    try:
        if not request.home_location:
            raise ValueError("Home location is required")
        if not request.subscriptions:
            raise ValueError("At least one subscription is required")

        subs_list = [{"name": s.name, "cost": s.cost} for s in request.subscriptions]

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

@router.post("/savings")
async def get_savings(request: SavingsRequest):
    """Phase 3: Calculate savings + alternatives (~10s). Auto-called when local subs + travel exist."""
    try:
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = await loop.run_in_executor(
                pool, compute_savings,
                request.away_periods, request.processed_subscriptions
            )
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
