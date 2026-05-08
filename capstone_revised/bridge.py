"""
Bridge Module — converts open-source extraction output into the dict format
expected by the downstream capstone modules (transaction_filter, merchant_normaliser,
subscription_scorer, trial_classifier, renewal_predictor).

Capstone expected format per transaction:
{
    "bank":        str,       # e.g. "NCB", "Scotiabank", "Unknown"
    "date":        str,       # "YYYY-MM-DD"
    "description": str,       # merchant / narration text
    "amount":      float,     # negative = debit, positive = credit
    "balance":     float|None,
    "currency":    str,       # "JMD", "USD", etc.
    "source_file": str        # original filename
}
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ── Amount parsing ─────────────────────────────────────────────────

def _parse_amount(value) -> Optional[float]:
    """Convert a cell value into a clean float, or None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if not s or s.lower() in ("", "nan", "none", "-", "--"):
        return None
    # Strip currency symbols and whitespace
    s = re.sub(r"[₹$J\s,]", "", s)
    # Handle parenthesised negatives: (500.00) → -500.00
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None


# ── Date normalisation ─────────────────────────────────────────────

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d/%m/%y",
    "%d-%m-%y",
    "%m/%d/%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%d%b%Y",
    "%d/%b/%Y",
    "%d/%b",        # DD/Mon (NCB style — year inferred)
    "%d%b",         # DDMon  (Scotiabank style — year inferred)
]

def _parse_date(value, fallback_year: int = None) -> Optional[str]:
    """Try multiple date formats, return YYYY-MM-DD or None."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None

    if fallback_year is None:
        fallback_year = datetime.now().year

    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
            # If format has no year component, inject fallback
            if "%Y" not in fmt and "%y" not in fmt:
                dt = dt.replace(year=fallback_year)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s  # Return raw string if no format matched


# ── Bank detection from PDF text ───────────────────────────────────

_BANK_PATTERNS = {
    "NCB":            r"national\s+commercial\s+bank|ncb\s+jamaica|\bncb\b",
    "Scotiabank":     r"scotiabank|scotia\s+bank|bank\s+of\s+nova\s+scotia",
    "JMMB":           r"jmmb|jamaica\s+money\s+market",
    "JN Bank":        r"jn\s+bank|jamaica\s+national",
    "CIBC":           r"cibc|first\s*caribbean",
    "HDFC":           r"hdfc\s+bank",
    "ICICI":          r"icici\s+bank",
    "SBI":            r"state\s+bank\s+of\s+india|\bsbi\b",
    "Axis":           r"axis\s+bank",
}

def detect_bank(text: str) -> str:
    """Scan statement text for known bank names."""
    lower = text[:3000].lower()  # Only scan the first few pages
    for bank_name, pattern in _BANK_PATTERNS.items():
        if re.search(pattern, lower, re.IGNORECASE):
            return bank_name
    return "Unknown"


# ── Currency detection ─────────────────────────────────────────────

def detect_currency(text: str) -> str:
    """Infer currency from statement text."""
    lower = text[:3000].lower()
    if re.search(r"\bj\$|jmd|jamaican\s+dollar", lower):
        return "JMD"
    if re.search(r"\bus\$|usd|united\s+states\s+dollar", lower):
        return "USD"
    if re.search(r"₹|inr|indian\s+rupee", lower):
        return "INR"
    if re.search(r"£|gbp|british\s+pound", lower):
        return "GBP"
    if re.search(r"€|eur", lower):
        return "EUR"
    if re.search(r"ca\$|cad|canadian", lower):
        return "CAD"
    # Default for Jamaican context
    return "JMD"


# ── Table DataFrame → Capstone dict list ───────────────────────────

def dataframe_to_capstone_format(
    df: pd.DataFrame,
    bank: str,
    currency: str,
    source_file: str,
) -> List[Dict[str, Any]]:
    """
    Convert a pandas DataFrame (from the open-source table extractor)
    into the list-of-dict format expected by capstone downstream modules.
    """
    transactions = []

    # Normalise column names to lowercase for matching
    col_map = {col: col.strip().lower() for col in df.columns}
    df_lower = df.rename(columns=col_map)

    # Find column roles
    date_col = _find_column(df_lower, ["date", "dt", "txn date", "value date", "transaction date"])
    desc_col = _find_column(df_lower, ["description", "narration", "particular", "particulars", "details", "remarks"])
    debit_col = _find_column(df_lower, ["debit", "withdrawal", "dr", "withdrawals", "debit amount"])
    credit_col = _find_column(df_lower, ["credit", "deposit", "cr", "deposits", "credit amount"])
    amount_col = _find_column(df_lower, ["amount", "transaction amount"])
    balance_col = _find_column(df_lower, ["balance", "closing balance", "running balance", "bal"])

    if not date_col and not desc_col:
        logger.warning("Could not identify date or description columns — skipping table")
        return []

    for _, row in df_lower.iterrows():
        # Parse date
        date_val = _parse_date(row.get(date_col)) if date_col else None
        if not date_val:
            continue  # Skip rows without a parseable date

        # Parse description
        desc = str(row.get(desc_col, "")).strip() if desc_col else ""
        if not desc:
            continue

        # Parse amounts
        debit = _parse_amount(row.get(debit_col)) if debit_col else None
        credit = _parse_amount(row.get(credit_col)) if credit_col else None
        single_amount = _parse_amount(row.get(amount_col)) if amount_col else None
        balance = _parse_amount(row.get(balance_col)) if balance_col else None

        # Determine net amount (negative = debit)
        if debit is not None and debit > 0:
            amount = -abs(debit)
        elif credit is not None and credit > 0:
            amount = abs(credit)
        elif single_amount is not None:
            amount = single_amount  # Already signed or context-dependent
        else:
            amount = 0.0

        transactions.append({
            "bank": bank,
            "date": date_val,
            "description": desc,
            "amount": amount,
            "balance": balance,
            "currency": currency,
            "source_file": source_file,
        })

    logger.info(f"Converted {len(transactions)} rows from table to capstone format")
    return transactions


def gemini_output_to_capstone_format(
    gemini_rows: List[Dict[str, Any]],
    bank: str,
    currency: str,
    source_file: str,
) -> List[Dict[str, Any]]:
    """
    Convert Gemini JSON output into capstone-format dicts.
    """
    transactions = []

    for row in gemini_rows:
        date_val = _parse_date(row.get("date"))
        desc = str(row.get("description", "")).strip()
        if not date_val or not desc:
            continue

        debit = _parse_amount(row.get("debit"))
        credit = _parse_amount(row.get("credit"))
        amount_raw = _parse_amount(row.get("amount"))
        balance = _parse_amount(row.get("balance"))

        # Use the currency from Gemini if provided
        row_currency = row.get("currency", currency) or currency

        if debit is not None and debit > 0:
            amount = -abs(debit)
        elif credit is not None and credit > 0:
            amount = abs(credit)
        elif amount_raw is not None:
            amount = amount_raw
        else:
            amount = 0.0

        transactions.append({
            "bank": bank,
            "date": date_val,
            "description": desc,
            "amount": amount,
            "balance": balance,
            "currency": row_currency,
            "source_file": source_file,
        })

    logger.info(f"Converted {len(transactions)} Gemini rows to capstone format")
    return transactions


# ── Helpers ────────────────────────────────────────────────────────

def _find_column(df: pd.DataFrame, keywords: List[str]) -> Optional[str]:
    """Find the first column whose name contains any of the keywords."""
    for col in df.columns:
        col_lower = str(col).lower().strip()
        for keyword in keywords:
            if keyword in col_lower:
                return col
    return None
