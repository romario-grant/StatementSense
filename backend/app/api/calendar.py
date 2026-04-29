from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
import asyncio
import concurrent.futures

from ..engines.calendar_engine import analyze_calendar

router = APIRouter(prefix="/api/calendar", tags=["CalendarSense"])

class SubscriptionInput(BaseModel):
    name: str
    cost: float

class CalendarRequest(BaseModel):
    home_location: str
    subscriptions: List[SubscriptionInput]
    access_token: str | None = None

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
