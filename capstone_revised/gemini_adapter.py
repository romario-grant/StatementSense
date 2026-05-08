"""
Gemini Adapter — lightweight LLM-based transaction extraction.

Uses the google.genai SDK (the current supported Gemini Python SDK)
as an alternative to the open-source project's Vertex AI integration.
This is called when pdfplumber/camelot table detection fails.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from google import genai
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ── Initialise Gemini ──────────────────────────────────────────────

_client = None

def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "No Gemini API key found. Set GOOGLE_API_KEY or GEMINI_API_KEY "
                "in your environment or .env file."
            )
        _client = genai.Client(api_key=api_key)
    return _client


# ── Extraction prompt ──────────────────────────────────────────────

_EXTRACTION_PROMPT = """You are an expert at extracting structured transaction data from bank statements.

Given the raw text from a bank statement PDF, extract EVERY transaction into a JSON array.
Each transaction must have these fields:
- "date": the transaction date in YYYY-MM-DD format (infer the year from context if only day/month is shown)
- "description": the merchant name or transaction description exactly as written
- "debit": the amount debited (withdrawn/spent) as a number, or null if this is a credit
- "credit": the amount credited (deposited/received) as a number, or null if this is a debit
- "balance": the running balance after this transaction as a number, or null if not shown
- "currency": the currency code (e.g. "JMD", "USD", "INR") — infer from the statement

Rules:
- Extract ALL transactions, not just a sample
- Amounts should be plain numbers without currency symbols or commas (e.g. 1500.00 not $1,500.00)
- If the statement shows a single "amount" column, determine debit vs credit from context (negative = debit, or marked DR/withdrawal)
- Skip rows that are headers, sub-totals, page footers, service charge breakdowns, or non-transaction text
- If you cannot determine a field, use null

Return ONLY a valid JSON array. No markdown, no explanation, just the array.

BANK STATEMENT TEXT:
{text}
"""


def extract_transactions_with_gemini(raw_text: str) -> Optional[List[Dict[str, Any]]]:
    """
    Send raw PDF text to Gemini and get back structured transactions.

    Parameters
    ----------
    raw_text : str
        The full text extracted from the bank statement PDF.

    Returns
    -------
    list[dict] or None
        A list of transaction dicts, or None if extraction failed.
    """
    if not raw_text or len(raw_text.strip()) < 50:
        logger.warning("Text too short for Gemini extraction")
        return None

    try:
        client = _get_client()

        # Truncate to ~30k chars to stay within token limits
        truncated = raw_text[:30000]

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=_EXTRACTION_PROMPT.format(text=truncated),
            config={
                "temperature": 0.1,
                "max_output_tokens": 16384,
                "thinking_config": {"thinking_budget": 0},
            },
        )

        if not response.text:
            logger.error("Empty response from Gemini")
            return None

        # Parse JSON from response — strip markdown fences if present
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]  # remove ```json line
            text = text.rsplit("```", 1)[0]  # remove closing ```

        try:
            transactions = json.loads(text)
        except json.JSONDecodeError:
            # Gemini may have been truncated — try to recover partial array
            # by closing any open brackets/braces
            recovered = _try_recover_partial_json(text)
            if recovered is not None:
                transactions = recovered
                logger.warning(f"Recovered {len(transactions)} transactions from truncated Gemini response")
            else:
                logger.error("Failed to parse Gemini JSON response (even after recovery attempt)")
                return None

        if not isinstance(transactions, list):
            logger.error(f"Gemini returned {type(transactions)}, expected list")
            return None

        logger.info(f"Gemini extracted {len(transactions)} transactions")
        return transactions

    except Exception as e:
        logger.error(f"Gemini extraction failed: {e}")
        return None


def _try_recover_partial_json(text: str):
    """Attempt to recover a partial JSON array from a truncated response."""
    text = text.strip()
    if not text.startswith("["):
        return None
    
    # Find the last complete object (ends with })
    last_brace = text.rfind("}")
    if last_brace == -1:
        return None
    
    # Truncate to last complete object and close the array
    truncated = text[:last_brace + 1].rstrip(",").rstrip() + "]"
    
    try:
        result = json.loads(truncated)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    
    return None
