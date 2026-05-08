"""
Statement Sense — Transaction Filter
Feature 7.1 · Filter layer between PDF/email parsers and subscription detection.

Strips bank-generated noise rows (fees, taxes, charges) that can never be
subscriptions, leaving only real merchant transactions for downstream processing.
"""

import re

# ─────────────────────────────────────────────
# Noise patterns  (case-insensitive substring match)
# ─────────────────────────────────────────────

_NOISE_PATTERNS = [
    r'service charge',
    r'gct[/\s]?govt\s+tax',   # "GCT/GOVT TAX" and variants
    r'\bgct\b',                # standalone GCT label rows
    r'govt\s+tax',
    r'pos\s+tx\s+fee',
    r'decline\s+tr[xn]+\s+fee',
    r'decline\s+tx\s+fee',
    r'stamp\s+duty',
    r'withholding\s+tax',
    r'record\s+keeping',
    r'abm\s+fee',
]

_NOISE_RE = re.compile(
    '|'.join(f'(?:{p})' for p in _NOISE_PATTERNS),
    re.IGNORECASE,
)


def is_noise_row(description: str) -> bool:
    """
    Return True if the description matches a known bank-generated noise pattern.
    These rows can never represent subscription or merchant transactions.
    """
    return bool(_NOISE_RE.search(description))


def filter_transactions(transactions: list[dict]) -> list[dict]:
    """
    Remove noise rows from a normalised transaction list produced by
    parse_ncb_pdf() or parse_scotiabank_pdf().

    Keeps: POS purchases, ABM withdrawals, transfers, subscription charges.
    Removes: service charges, GCT, POS/decline fees, stamp duty, etc.

    Returns a new list; the input is not modified.
    """
    return [t for t in transactions if not is_noise_row(t.get('description', ''))]
