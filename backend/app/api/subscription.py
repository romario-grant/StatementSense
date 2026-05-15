"""SubscriptionSense API endpoints."""

import asyncio
import logging

from fastapi import APIRouter, UploadFile, File, HTTPException

from backend.app.extraction.extract_transactions import extract_from_bytes

from ..engines.subscription_engine import (
    analyze_extracted_subscriptions,
    analyze_subscriptions,
)

router = APIRouter(prefix="/api/subscription", tags=["SubscriptionSense"])
logger = logging.getLogger(__name__)


@router.post("/upload")
async def upload_statement(file: UploadFile = File(...)):
    """Accept a single bank-statement upload and return the full subscription analysis, including detected recurring charges, renewal predictions, trial alerts, CUSUM-based price-change detection, and normalized currency values."""
    if not file.filename.lower().endswith(('.pdf', '.csv')):
        raise HTTPException(status_code=400, detail="Only PDF and CSV files are supported.")

    file_bytes = await file.read()

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")

    try:
        result = analyze_subscriptions(file_bytes)
    except Exception as exc:
        logger.exception("Subscription analysis failed for %s", file.filename)
        raise HTTPException(
            status_code=500,
            detail=f"Subscription analysis failed: {exc}",
        ) from exc

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    return result


@router.post("/upload-multiple")
async def upload_multiple_statements(files: list[UploadFile] = File(...)):
    """Accept up to three consecutive bank statements and analyze them as a single dataset. Extraction is run concurrently for each statement, so end-to-end latency is governed by the slowest statement rather than the sum of all statements."""
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one statement.")
    if len(files) > 3:
        raise HTTPException(status_code=400, detail="Upload a maximum of 3 statements.")

    file_payloads: list[tuple[str, bytes]] = []
    for file in files:
        filename = file.filename or "statement"
        if not filename.lower().endswith((".pdf", ".csv")):
            raise HTTPException(status_code=400, detail="Only PDF and CSV files are supported.")

        file_bytes = await file.read()
        if len(file_bytes) == 0:
            raise HTTPException(status_code=400, detail=f"{filename} is empty.")

        file_payloads.append((filename, file_bytes))

    async def extract_one(filename: str, file_bytes: bytes):
        try:
            transactions = await asyncio.to_thread(extract_from_bytes, file_bytes)
            for tx in transactions:
                tx["source_file"] = tx.get("source_file") or filename
            return {"filename": filename, "transactions": transactions, "error": None}
        except Exception as exc:
            logger.exception("Subscription extraction failed for %s", filename)
            return {"filename": filename, "transactions": [], "error": str(exc)}

    extracted = await asyncio.gather(
        *(extract_one(filename, file_bytes) for filename, file_bytes in file_payloads)
    )

    warnings = [
        f"{item['filename']} could not be parsed: {item['error']}"
        for item in extracted
        if item["error"]
    ]
    raw_transactions = [
        tx
        for item in extracted
        for tx in item["transactions"]
    ]

    if not raw_transactions:
        detail = "No transactions could be extracted from the uploaded statements."
        if warnings:
            detail = f"{detail} {' '.join(warnings)}"
        raise HTTPException(status_code=422, detail=detail)

    result = analyze_extracted_subscriptions(raw_transactions)
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    result["statements_processed"] = len(file_payloads)
    result["statements_succeeded"] = sum(1 for item in extracted if item["transactions"])
    result["warnings"] = warnings
    return result
