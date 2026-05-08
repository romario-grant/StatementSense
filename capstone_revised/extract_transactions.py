"""
Transaction Extractor — main entry point for capstone_revised.

Orchestrates the full extraction pipeline:
  1. Open-source table extraction (pdfplumber + camelot)
  2. Gemini LLM fallback (if tables not found)
  3. Bridge conversion to capstone format

Usage:
    from capstone_revised.extract_transactions import extract_from_pdf

    transactions = extract_from_pdf("path/to/statement.pdf")
    # Returns: [{bank, date, description, amount, balance, currency, source_file}, ...]
"""

import io
import logging
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

# ── Logging setup ──────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ── Import open-source modules (unchanged) ─────────────────────────

from .app.extract_text import extract_text_from_pdf
from .app.extract_tables import extract_tables_from_pdf

# ── Import bridge & Gemini adapter ─────────────────────────────────

from .bridge import (
    dataframe_to_capstone_format,
    gemini_output_to_capstone_format,
    detect_bank,
    detect_currency,
)
from .gemini_adapter import extract_transactions_with_gemini


# ── Main extraction function ──────────────────────────────────────

def extract_from_pdf(filepath: str) -> List[Dict[str, Any]]:
    """
    Extract transactions from any bank statement PDF.

    This function does NOT require you to specify the bank name,
    statement format, or column positions. It works with any bank.

    Pipeline:
        1. Try pdfplumber + camelot table detection (no AI needed)
        2. If no tables found → fall back to Gemini LLM extraction
        3. Convert to capstone-compatible format

    Parameters
    ----------
    filepath : str
        Path to the bank statement PDF.

    Returns
    -------
    list[dict]
        List of transactions in capstone format:
        [{bank, date, description, amount, balance, currency, source_file}, ...]
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"PDF not found: {filepath}")

    source_file = filepath.name
    logger.info(f"═══ Extracting transactions from: {source_file} ═══")

    # ── Step 1: Extract raw text (always needed for bank/currency detection) ──

    logger.info("[1/4] Extracting raw text from PDF...")
    raw_text = extract_text_from_pdf(str(filepath))

    if not raw_text or len(raw_text.strip()) < 20:
        logger.error("Could not extract any text from PDF. Is it a scanned image?")
        return []

    # ── Step 2: Detect bank and currency from text ──

    logger.info("[2/4] Detecting bank and currency...")
    bank = detect_bank(raw_text)
    currency = detect_currency(raw_text)
    logger.info(f"  Bank: {bank} | Currency: {currency}")

    # ── Step 3: Try table extraction (pdfplumber + camelot) ──

    logger.info("[3/4] Attempting automatic table extraction...")
    all_transactions: List[Dict[str, Any]] = []

    try:
        tables = extract_tables_from_pdf(str(filepath))
        if tables:
            logger.info(f"  Found {len(tables)} table(s) via pdfplumber/camelot")
            for i, df in enumerate(tables):
                logger.info(f"  Table {i+1}: {len(df)} rows, columns: {list(df.columns)}")
                converted = dataframe_to_capstone_format(
                    df=df,
                    bank=bank,
                    currency=currency,
                    source_file=source_file,
                )
                all_transactions.extend(converted)
    except Exception as e:
        logger.warning(f"  Table extraction failed: {e}")

    # ── Step 4: Gemini fallback if table extraction found nothing ──

    if not all_transactions:
        logger.info("[4/4] No tables found — falling back to Gemini LLM extraction...")
        try:
            gemini_rows = extract_transactions_with_gemini(raw_text)
            if gemini_rows:
                all_transactions = gemini_output_to_capstone_format(
                    gemini_rows=gemini_rows,
                    bank=bank,
                    currency=currency,
                    source_file=source_file,
                )
        except Exception as e:
            logger.error(f"  Gemini extraction also failed: {e}")
    else:
        logger.info("[4/4] Skipping Gemini — table extraction succeeded")

    # ── Summary ──

    logger.info(f"═══ Result: {len(all_transactions)} transactions from {source_file} ═══")

    if all_transactions:
        # Log a preview
        for t in all_transactions[:3]:
            logger.info(f"  {t['date']} | {t['description'][:40]:<40} | {t['amount']:>12.2f} {t['currency']}")
        if len(all_transactions) > 3:
            logger.info(f"  ... and {len(all_transactions) - 3} more")

    return all_transactions


def extract_from_bytes(file_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Extract transactions from PDF bytes (for file upload endpoints).

    Writes the bytes to a temp file and delegates to extract_from_pdf().

    Parameters
    ----------
    file_bytes : bytes
        Raw PDF file content.

    Returns
    -------
    list[dict]
        List of transactions in capstone format.
    """
    if not file_bytes:
        logger.error("Empty file bytes provided")
        return []

    # Write bytes to a temporary PDF file
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        return extract_from_pdf(tmp_path)
    finally:
        # Clean up temp file
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass

