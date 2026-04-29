"""RenewalSense API endpoints."""

from fastapi import APIRouter, UploadFile, File, HTTPException

from ..engines.renewal_engine import analyze_statement

router = APIRouter(prefix="/api/renewal", tags=["RenewalSense"])


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
