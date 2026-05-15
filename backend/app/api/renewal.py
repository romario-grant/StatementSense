"""RenewalSense API endpoints."""

import logging

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel, Field

from ..engines.renewal_engine import (
    analyze_existing_data,
    analyze_statement,
    simulate_plan_options,
)

router = APIRouter(prefix="/api/renewal", tags=["RenewalSense"])
logger = logging.getLogger(__name__)


class RenewalFromExistingRequest(BaseModel):
    transactions: list[dict] = Field(default_factory=list)
    subscriptions: list[dict] = Field(default_factory=list)
    price_changes: list[dict] | None = None
    manual_salary: dict | None = None
    year: int | None = None
    month: int | None = None


class PlanSimulatorRequest(BaseModel):
    subscription: dict = Field(default_factory=dict)
    salary: dict = Field(default_factory=dict)
    expenses: list[dict] = Field(default_factory=list)
    transactions: list[dict] = Field(default_factory=list)
    year: int | None = None
    month: int | None = None
    exchange_rate: float | None = None
    exchange_rate_source: str | None = None
    country: str | None = "Jamaica"
    local_currency: str | None = "JMD"


@router.post("/upload")
async def upload_statement(file: UploadFile = File(...)):
    """Accept a bank-statement upload and return the full renewal-risk analysis, including parsed transactions, the detected salary pattern, subscription risk scores, a thirty-day pay-cycle map, and summary statistics."""
    if not file.filename.lower().endswith(('.pdf', '.csv')):
        raise HTTPException(status_code=400, detail="Only PDF and CSV files are supported.")

    file_bytes = await file.read()

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")

    result = analyze_statement(file_bytes)

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    return result


@router.post("/analyze-existing")
async def analyze_existing(request: RenewalFromExistingRequest):
    """Run the renewal-risk analysis directly against transactions and subscriptions that have already been parsed elsewhere in the application, without re-uploading a statement."""
    if not request.transactions:
        raise HTTPException(status_code=400, detail="No parsed transactions were provided.")

    result = analyze_existing_data(
        request.transactions,
        request.subscriptions,
        request.price_changes,
        request.manual_salary,
        request.year,
        request.month,
    )

    if "error" in result:
        if result.get("code"):
            raise HTTPException(status_code=422, detail=result)
        raise HTTPException(status_code=422, detail=result["error"])

    return result


@router.post("/plan-simulator")
async def plan_simulator(request: PlanSimulatorRequest):
    """Resolve verified plan alternatives for a subscription and simulate each one against the user's existing renewal day so callers can compare plan switches."""
    try:
        result = simulate_plan_options(
            request.subscription,
            request.salary,
            request.expenses,
            request.transactions,
            request.year,
            request.month,
            request.exchange_rate,
            request.country or "Jamaica",
            request.local_currency or "JMD",
            request.exchange_rate_source,
        )
    except Exception as exc:
        logger.exception("Plan simulator failed")
        raise HTTPException(status_code=500, detail=f"Plan comparison failed: {exc}") from exc

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result
