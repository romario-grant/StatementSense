"""RenewalSense API endpoints."""

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel, Field

from ..engines.renewal_engine import analyze_existing_data, analyze_statement

router = APIRouter(prefix="/api/renewal", tags=["RenewalSense"])


class RenewalFromExistingRequest(BaseModel):
    transactions: list[dict] = Field(default_factory=list)
    subscriptions: list[dict] = Field(default_factory=list)
    price_changes: list[dict] | None = None


@router.post("/upload")
async def upload_statement(file: UploadFile = File(...)):
    """
    Upload a bank statement PDF and get a full renewal risk analysis.
    
    Returns:
    - Parsed transactions with categories
    - Detected salary pattern
    - Subscription risk scores
    - 30-day paycycle map
    - Summary statistics
    """
    # Validate file type
    if not file.filename.lower().endswith(('.pdf', '.csv')):
        raise HTTPException(status_code=400, detail="Only PDF and CSV files are supported.")
    
    # Read file bytes
    file_bytes = await file.read()
    
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")
    
    # Run analysis
    result = analyze_statement(file_bytes)
    
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    
    return result


@router.post("/analyze-existing")
async def analyze_existing(request: RenewalFromExistingRequest):
    """
    Run RenewalSense from SubscriptionSense's saved parsed transactions and
    detected subscriptions. No statement upload or bank parsing happens here.
    """
    if not request.transactions:
        raise HTTPException(status_code=400, detail="No parsed transactions were provided.")

    result = analyze_existing_data(
        request.transactions,
        request.subscriptions,
        request.price_changes,
    )

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    return result
