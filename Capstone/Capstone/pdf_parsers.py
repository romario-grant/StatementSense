"""
Statement Sense — PDF Statement Parsers
NCB Jamaica + Scotiabank Jamaica
Outputs normalised transaction records for all downstream pipeline stages.
"""

import re
import pdfplumber
from datetime import datetime
from collections import defaultdict


# ─────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────

def clean_amount(raw: str) -> float | None:
    """Convert '−1,086.96' or '35,000.00' to signed float. Returns None on failure."""
    if not raw:
        return None
    raw = raw.replace(',', '').replace('J$', '').replace(' ', '')
    negative = raw.startswith('-')
    raw = raw.lstrip('-')
    try:
        val = float(raw)
        return -val if negative else val
    except ValueError:
        return None


def group_words_by_row(words: list, y_tolerance: int = 3) -> list[list[dict]]:
    """Group words into rows based on their vertical (top) position."""
    if not words:
        return []
    rows = []
    current_row = [words[0]]
    for word in words[1:]:
        if abs(word['top'] - current_row[0]['top']) <= y_tolerance:
            current_row.append(word)
        else:
            rows.append(sorted(current_row, key=lambda w: w['x0']))
            current_row = [word]
    rows.append(sorted(current_row, key=lambda w: w['x0']))
    return rows


def normalise_date(date_str: str, year: int) -> str | None:
    """
    Converts NCB 'DD/Mon' or Scotiabank 'DDMMM' to 'YYYY-MM-DD'.
    Year is inferred from the statement header.
    """
    date_str = date_str.strip()
    for fmt in ('%d/%b', '%d%b'):
        try:
            dt = datetime.strptime(date_str, fmt).replace(year=year)
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


# ─────────────────────────────────────────────
# NCB Parser
# ─────────────────────────────────────────────

# Column x-boundaries derived from positional probe
NCB_COL = {
    'date':   (0,    70),
    'desc':   (70,   385),
    'amount': (385,  510),
    'balance':(510,  620),
}

NCB_DATE_RE  = re.compile(r'^\d{2}/[A-Za-z]{3}$')
NCB_SKIP_RE  = re.compile(
    r'(BALANCE BROUGHT FORWARD|NO\. OF DEBITS|TOTAL AMOUNT|CONTINUED|END OF STATEMENT'
    r'|DATE\s+PARTICULARS|GCT REGISTRATION|NATIONAL COMMERCIAL|UNIVERSITY BRANCH'
    r'|FOLD HERE|YOU MAY RECONCILE|OVERDRAWN AND DEBIT)',
    re.IGNORECASE
)


def _ncb_words_in_col(row_words, col_key):
    lo, hi = NCB_COL[col_key]
    return [w for w in row_words if lo <= w['x0'] < hi]


def _ncb_statement_year(pdf) -> int:
    """Extract statement year from 'STATEMENT DATE: DD-MM-YYYY' in header."""
    first_page_text = pdf.pages[0].extract_text() or ''
    m = re.search(r'STATEMENT\s+DATE[:\s]+\d{2}-\d{2}-(\d{4})', first_page_text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Fallback: grab the last 4-digit year found
    years = re.findall(r'\b(20\d{2})\b', first_page_text)
    return int(years[-1]) if years else datetime.now().year


def parse_ncb_pdf(filepath: str) -> list[dict]:
    """
    Parse an NCB Jamaica PDF statement.
    Returns a list of normalised transaction dicts.
    """
    transactions = []

    with pdfplumber.open(filepath) as pdf:
        year = _ncb_statement_year(pdf)

        for page in pdf.pages:
            words = page.extract_words()
            rows  = group_words_by_row(words, y_tolerance=3)

            for row in rows:
                row_text = ' '.join(w['text'] for w in row)

                # Skip header/footer/summary rows
                if NCB_SKIP_RE.search(row_text):
                    continue

                date_words   = _ncb_words_in_col(row, 'date')
                amount_words = _ncb_words_in_col(row, 'amount')
                desc_words   = _ncb_words_in_col(row, 'desc')
                bal_words    = _ncb_words_in_col(row, 'balance')

                # Only process rows that start with a valid date token
                if not date_words:
                    continue
                date_token = date_words[0]['text']
                if not NCB_DATE_RE.match(date_token):
                    continue

                # Skip carry-over balance row (date only, no description or amount)
                if not amount_words and not desc_words:
                    continue

                date_iso = normalise_date(date_token, year)
                desc     = ' '.join(w['text'] for w in desc_words).strip()
                amount   = clean_amount(' '.join(w['text'] for w in amount_words)) if amount_words else None
                balance  = clean_amount(' '.join(w['text'] for w in bal_words)) if bal_words else None

                if amount is None:
                    continue

                transactions.append({
                    'bank':        'NCB',
                    'date':        date_iso,
                    'description': desc,
                    'amount':      amount,
                    'balance':     balance,
                    'currency':    'JMD',
                    'source_file': filepath,
                })

    return transactions


# ─────────────────────────────────────────────
# Scotiabank Parser
# ─────────────────────────────────────────────

# Column x-boundaries derived from positional probe
SCOTIA_COL = {
    'date':    (0,    100),
    'desc':    (100,  340),
    'credit':  (340,  420),
    'debit':   (420,  505),
    'balance': (505,  600),
}

SCOTIA_DATE_RE = re.compile(r'^\d{2}[A-Za-z]{3}$')  # e.g. 02FEB
SCOTIA_SKIP_RE = re.compile(
    r'(OPENING BALANCE|CLOSING BALANCE|Transaction\s+Date|CREDIT|DEBIT'
    r'|SERVICE CHARGE DETAILS|Transactional Fee|Monthly Fee|Total Charges'
    r'|CHEQUES OUTSTANDING|NUMBER OR PAYEE|Your SAVINGS|www\.scotiabank'
    r'|Trademark|Page \d+ of \d+)',
    re.IGNORECASE
)
# Pages that are service charge details or cheques — skip entirely
SCOTIA_SKIP_PAGES = {5, 6, 7}  # 1-indexed


def _scotia_words_in_col(row_words, col_key):
    lo, hi = SCOTIA_COL[col_key]
    return [w for w in row_words if lo <= w['x0'] < hi]


def _scotia_statement_year(pdf) -> int:
    """Extract year from 'Statement Period: DDMMMYY to DDMMMYY'."""
    first_text = pdf.pages[0].extract_text() or ''
    m = re.search(r'(\d{2})([A-Za-z]{3})(\d{2})\s+to', first_text)
    if m:
        yr = int(m.group(3))
        return 2000 + yr if yr < 100 else yr
    return datetime.now().year


def _parse_scotia_amount(credit_words, debit_words) -> float | None:
    """
    Scotia splits amount into CREDIT and DEBIT columns.
    Credit = positive, debit = negative. Strip 'J$' and '+'/'-'.
    """
    if credit_words:
        raw = ' '.join(w['text'] for w in credit_words)
        raw = raw.replace('J$', '').replace('+', '').replace(',', '').strip()
        try:
            return float(raw)
        except ValueError:
            pass
    if debit_words:
        raw = ' '.join(w['text'] for w in debit_words)
        raw = raw.replace('J$', '').replace('-', '').replace(',', '').strip()
        try:
            return -float(raw)
        except ValueError:
            pass
    return None


def parse_scotiabank_pdf(filepath: str) -> list[dict]:
    """
    Parse a Scotiabank Jamaica PDF statement.
    Scotia layouts have date/amount at one y-position and description
    text at a slightly offset y — both belong to the same transaction row.
    The detail line (merchant info) follows on the next physical line.
    Returns a list of normalised transaction dicts.
    """
    transactions = []

    with pdfplumber.open(filepath) as pdf:
        year = _scotia_statement_year(pdf)

        for page_num, page in enumerate(pdf.pages, start=1):
            if page_num in SCOTIA_SKIP_PAGES:
                continue

            # Use higher y_tolerance to merge description + date/amount
            # that Scotia splits across slightly different top values
            words = page.extract_words()
            rows  = group_words_by_row(words, y_tolerance=5)

            pending_desc = None  # merchant detail line carried forward

            for row in rows:
                row_text = ' '.join(w['text'] for w in row)

                if SCOTIA_SKIP_RE.search(row_text):
                    pending_desc = None
                    continue

                date_words   = _scotia_words_in_col(row, 'date')
                desc_words   = _scotia_words_in_col(row, 'desc')
                credit_words = _scotia_words_in_col(row, 'credit')
                debit_words  = _scotia_words_in_col(row, 'debit')
                bal_words    = _scotia_words_in_col(row, 'balance')

                date_token = date_words[0]['text'] if date_words else ''
                has_date   = bool(SCOTIA_DATE_RE.match(date_token))
                has_amount = bool(credit_words or debit_words)

                if has_date and has_amount:
                    # Full transaction row — description + amount on same grouped row
                    date_iso  = normalise_date(date_token, year)
                    desc_line = ' '.join(w['text'] for w in desc_words).strip()

                    # Append any pending detail line from previous row
                    if pending_desc:
                        desc_line = (pending_desc + ' ' + desc_line).strip()
                        pending_desc = None

                    amount  = _parse_scotia_amount(credit_words, debit_words)
                    balance = None
                    if bal_words:
                        raw = ' '.join(w['text'] for w in bal_words)
                        raw = raw.replace('J$', '').replace(',', '').strip()
                        try:
                            balance = float(raw)
                        except ValueError:
                            pass

                    if amount is not None:
                        transactions.append({
                            'bank':        'Scotiabank',
                            'date':        date_iso,
                            'description': desc_line.strip(),
                            'amount':      amount,
                            'balance':     balance,
                            'currency':    'JMD',
                            'source_file': filepath,
                        })

                elif not has_date and not has_amount and desc_words:
                    # Pure detail line — merchant info for the previous transaction
                    detail = ' '.join(w['text'] for w in desc_words).strip()
                    # Attach to last transaction if available
                    if transactions:
                        transactions[-1]['description'] += ' ' + detail
                    pending_desc = None

                else:
                    pending_desc = None

    return transactions


# ─────────────────────────────────────────────
# Unified entry point
# ─────────────────────────────────────────────

def parse_statement_pdf(filepath: str, bank: str) -> list[dict]:
    """
    Single entry point. bank: 'NCB' | 'Scotiabank'
    Returns list of normalised transaction dicts.
    """
    if bank == 'NCB':
        return parse_ncb_pdf(filepath)
    elif bank == 'Scotiabank':
        return parse_scotiabank_pdf(filepath)
    else:
        raise ValueError(f"Unknown bank: {bank}")


# ─────────────────────────────────────────────
# Smoke test
# ─────────────────────────────────────────────

if __name__ == '__main__':
    import sys

    NCB_PATH    = r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and Vocational Training\Downloads\ACCT2015\NcbStatement.pdf'
    SCOTIA_PATH = r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and Vocational Training\Downloads\ACCT2015\ScotiaStatement.pdf'

    print('=' * 60)
    print('NCB TRANSACTIONS')
    print('=' * 60)
    ncb_txns = parse_ncb_pdf(NCB_PATH)
    for t in ncb_txns:
        print(f"  {t['date']}  {t['description'][:45]:<45}  {t['amount']:>12,.2f}")
    print(f'\nTotal: {len(ncb_txns)} transactions')

    print()
    print('=' * 60)
    print('SCOTIABANK TRANSACTIONS')
    print('=' * 60)
    sc_txns = parse_scotiabank_pdf(SCOTIA_PATH)
    for t in sc_txns:
        print(f"  {t['date']}  {t['description'][:45]:<45}  {t['amount']:>12,.2f}")
    print(f'\nTotal: {len(sc_txns)} transactions')