"""
Conversion helpers that normalise heterogeneous extractor output into the
canonical StatementSense transaction shape of bank, date, description, signed
amount, balance, currency, and source file. Also exposes header-text helpers
for detecting the bank name and currency.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)



def _parse_amount(value) -> Optional[float]:
    """Coerce a raw cell value into a float, returning None for blanks or unparseable input."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if not s or s.lower() in ("", "nan", "none", "-", "--"):
        return None
    # Drop currency symbols (INR, USD, JMD J-prefix) and thousands separators.
    s = re.sub(r"[\u20b9$J\s,]", "", s)
    # Accounting notation: parenthesised values denote negatives.
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None



# Ordered from most specific to least; year-bearing formats are tried first so
# that ambiguous strings prefer an explicit year over the inferred fallback.
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
    "%d/%b",        # Day plus abbreviated month; year supplied by fallback.
    "%d%b",         # Same as above without a separator.
]

def _parse_date(value, fallback_year: int = None) -> Optional[str]:
    """Parse a date string against the configured format list and return ISO YYYY-MM-DD, or the raw string when every format fails."""
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
            # Year-less formats default to 1900; substitute the statement year.
            if "%Y" not in fmt and "%y" not in fmt:
                dt = dt.replace(year=fallback_year)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s



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
    """Identify the issuing bank by matching known name patterns against the statement header."""
    # The first 3000 characters reliably cover the statement header where the
    # bank identity appears; scanning further risks false positives from
    # transaction descriptions.
    lower = text[:3000].lower()
    for bank_name, pattern in _BANK_PATTERNS.items():
        if re.search(pattern, lower, re.IGNORECASE):
            return bank_name
    return "Unknown"



def detect_currency(text: str) -> str:
    """Infer the statement currency from header symbols and codes, defaulting to JMD."""
    # Same header window as detect_bank; currency markers cluster near the top.
    lower = text[:3000].lower()
    if re.search(r"\bj\$|jmd|jamaican\s+dollar", lower):
        return "JMD"
    if re.search(r"\bus\$|usd|united\s+states\s+dollar", lower):
        return "USD"
    if re.search(r"\u20b9|inr|indian\s+rupee", lower):
        return "INR"
    if re.search(r"\u00a3|gbp|british\s+pound", lower):
        return "GBP"
    if re.search(r"\u20ac|eur", lower):
        return "EUR"
    if re.search(r"ca\$|cad|canadian", lower):
        return "CAD"
    # JMD is the dominant currency in the supported corpus; use it when no
    # explicit indicator is found.
    return "JMD"



def dataframe_to_capstone_format(
    df: pd.DataFrame,
    bank: str,
    currency: str,
    source_file: str,
) -> List[Dict[str, Any]]:
    """Convert a transaction table extracted by pdfplumber or camelot into canonical transaction dictionaries."""
    transactions = []

    # Normalise column names to lower case so keyword matching is bank-agnostic.
    col_map = {col: col.strip().lower() for col in df.columns}
    df_lower = df.rename(columns=col_map)

    # Map common header variants to the semantic role each column plays.
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
        date_val = _parse_date(row.get(date_col)) if date_col else None
        if not date_val:
            # Rows without a date are typically subtotals or page headers.
            continue

        desc = str(row.get(desc_col, "")).strip() if desc_col else ""
        if not desc:
            continue

        debit = _parse_amount(row.get(debit_col)) if debit_col else None
        credit = _parse_amount(row.get(credit_col)) if credit_col else None
        single_amount = _parse_amount(row.get(amount_col)) if amount_col else None
        balance = _parse_amount(row.get(balance_col)) if balance_col else None

        # Canonical sign convention: debits are negative, credits positive.
        # A single amount column is assumed to already carry the correct sign.
        if debit is not None and debit > 0:
            amount = -abs(debit)
        elif credit is not None and credit > 0:
            amount = abs(credit)
        elif single_amount is not None:
            amount = single_amount
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
    """Convert the JSON rows returned by the Gemini extractor into canonical transaction dictionaries."""
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

        # Prefer a per-row currency from Gemini when present; otherwise apply
        # the document-level currency detected from the header.
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



def _find_column(df: pd.DataFrame, keywords: List[str]) -> Optional[str]:
    """Return the first column whose name contains any of the supplied keywords."""
    for col in df.columns:
        col_lower = str(col).lower().strip()
        for keyword in keywords:
            if keyword in col_lower:
                return col
    return None
