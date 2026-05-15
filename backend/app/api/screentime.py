"""ScreentimeSense API endpoints. Expose the screentime engine through single-subscription and batch analysis endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
import asyncio
import concurrent.futures

from ..engines.screentime_engine import analyze_screentime, analyze_screentime_batch, detect_exam_season

router = APIRouter(prefix="/api/screentime", tags=["ScreentimeSense"])

class ScreentimeRequest(BaseModel):
    app_name: str
    cost: float
    months_subscribed: int
    billing_period: str | None = "monthly"
    weekly_hours: List[float]  # Hours of use for each of the last four weeks.
    user_wage: float
    style_multiplier: float = 0.10
    local_currency: str = "JMD"
    exchange_rate: float | None = None

class BatchScreentimeRequest(BaseModel):
    subscriptions: List[ScreentimeRequest]
    user_wage: float
    style_multiplier: float = 0.10
    is_student: bool = False
    local_currency: str = "JMD"
    exchange_rate: float | None = None

def _run_analysis(
    app_name,
    cost,
    months_subscribed,
    weekly_hours,
    user_wage,
    style_multiplier,
    local_currency,
    exchange_rate,
    billing_period,
):
    """Synchronous wrapper around ``analyze_screentime`` used by the thread-pool executor."""
    return analyze_screentime(
        app_name=app_name,
        cost=cost,
        months_subscribed=months_subscribed,
        weekly_hours=weekly_hours,
        user_wage=user_wage,
        style_multiplier=style_multiplier,
        local_currency=local_currency,
        exchange_rate=exchange_rate,
        billing_period=billing_period or "monthly",
    )

@router.post("/analyze")
async def analyze_app_usage(request: ScreentimeRequest):
    """Analyze screen-time engagement for a single subscription."""
    if len(request.weekly_hours) != 4:
        raise HTTPException(status_code=400, detail="Must provide exactly 4 weeks of data")
        
    try:
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = await loop.run_in_executor(
                pool,
                _run_analysis,
                request.app_name,
                request.cost,
                request.months_subscribed,
                request.weekly_hours,
                request.user_wage,
                request.style_multiplier,
                request.local_currency,
                request.exchange_rate,
                request.billing_period or "monthly",
            )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/analyze-batch")
async def analyze_batch(request: BatchScreentimeRequest):
    """Analyze screen-time engagement for multiple subscriptions concurrently. Gemini classification calls fan out in parallel so end-to-end latency is governed by the slowest request rather than the sum of all requests."""
    for sub in request.subscriptions:
        if len(sub.weekly_hours) != 4:
            raise HTTPException(
                status_code=400,
                detail=f"Subscription '{sub.app_name}' must have exactly 4 weeks of data"
            )
    
    try:
        subs_list = [
            {
                "app_name": s.app_name,
                "cost": s.cost,
                "months_subscribed": s.months_subscribed,
                "billing_period": s.billing_period or "monthly",
                "weekly_hours": s.weekly_hours
            }
            for s in request.subscriptions
        ]
        
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            results = await loop.run_in_executor(
                pool,
                analyze_screentime_batch,
                subs_list,
                request.user_wage,
                request.style_multiplier,
                request.local_currency,
                request.exchange_rate,
            )
            
        if "error" in results:
            raise HTTPException(status_code=500, detail=results["error"])
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    # Run the optional student exam-season advisory once the main analysis has succeeded.
    exam_alert = None
    if request.is_student:
        try:
            loop2 = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                exam_alert = await loop2.run_in_executor(
                    pool,
                    detect_exam_season,
                    results["results"]
                )
        except Exception as e:
            print(f"[ExamDetection] Error: {e}")
    
    return {
        "results": results["results"],
        "count": len(results["results"]),
        "exam_alert": exam_alert
    }
