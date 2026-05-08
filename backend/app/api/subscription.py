"""SubscriptionSense API endpoints."""

from fastapi import APIRouter, UploadFile, File, HTTPException

from ..engines.subscription_engine import analyze_subscriptions

router = APIRouter(prefix="/api/subscription", tags=["SubscriptionSense"])


@router.post("/upload")
async def upload_statement(file: UploadFile = File(...)):
    """
    Upload a bank statement PDF and get a full subscription analysis.

    Returns:
    - Detected subscriptions with billing periods and confidence scores
    - Renewal predictions with next charge dates
    - Free trial detection alerts
    - Price change detection (CUSUM)
    - Currency normalization (JMD → USD)
    """
    # Validate file type
    if not file.filename.lower().endswith(('.pdf', '.csv')):
        raise HTTPException(status_code=400, detail="Only PDF and CSV files are supported.")

    # Read file bytes
    file_bytes = await file.read()

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")

    # Run analysis
    result = analyze_subscriptions(file_bytes)

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    return result
