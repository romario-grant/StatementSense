"""
Statement extraction entry points for uploaded PDF files.

The pipeline extracts raw text, detects bank and currency metadata, converts
structured tables when available, and uses Gemini only when table extraction
does not produce transactions.
"""

import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from .app.extract_text import extract_text_from_pdf
from .app.extract_tables import extract_tables_from_pdf

from .bridge import (
    dataframe_to_capstone_format,
    gemini_output_to_capstone_format,
    detect_bank,
    detect_currency,
)
from .gemini_adapter import extract_transactions_with_gemini

def extract_from_pdf(filepath: str) -> List[Dict[str, Any]]:
    """Extract transactions from any supported bank-statement PDF and return them in canonical StatementSense form. The pipeline first attempts structured table extraction via pdfplumber and camelot, falls back to Gemini-based extraction when no tables are detected, and finally maps every row into the standard ``{bank, date, description, amount, balance, currency, source_file}`` shape."""
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"PDF not found: {filepath}")

    source_file = filepath.name
    logger.info(f"Extracting transactions from {source_file}")

    logger.info("[1/4] Extracting raw text from PDF...")
    raw_text = extract_text_from_pdf(str(filepath))

    if not raw_text or len(raw_text.strip()) < 20:
        logger.error("Could not extract any text from PDF. Is it a scanned image?")
        return []

    logger.info("[2/4] Detecting bank and currency...")
    bank = detect_bank(raw_text)
    currency = detect_currency(raw_text)
    logger.info(f"  Bank: {bank} | Currency: {currency}")

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

    if not all_transactions:
        logger.info("[4/4] No tables found; using Gemini extraction...")
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
        logger.info("[4/4] Skipping Gemini; table extraction succeeded")

    logger.info(f"Extracted {len(all_transactions)} transactions from {source_file}")

    if all_transactions:
        # Preview a few normalized rows for extraction diagnostics.
        for t in all_transactions[:3]:
            logger.info(f"  {t['date']} | {t['description'][:40]:<40} | {t['amount']:>12.2f} {t['currency']}")
        if len(all_transactions) > 3:
            logger.info(f"  ... and {len(all_transactions) - 3} more")

    return all_transactions

def extract_from_bytes(file_bytes: bytes) -> List[Dict[str, Any]]:
    """Extract transactions from raw PDF bytes, used by HTTP upload endpoints. The bytes are written to a short-lived temporary file so the path-based extractors can read them, and the file is removed once extraction completes."""
    if not file_bytes:
        logger.error("Empty file bytes provided")
        return []

    # pdfplumber and camelot operate on filesystem paths, so uploads are staged briefly.
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        return extract_from_pdf(tmp_path)
    finally:
        # Remove the staged file even when extraction fails.
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass
