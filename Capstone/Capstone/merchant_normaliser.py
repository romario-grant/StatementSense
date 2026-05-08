"""
Statement Sense — Merchant Normaliser  (TC-1)
Clusters merchant name variants into a single canonical identity using
character-level TF-IDF cosine similarity.

Pipeline position:
    pdf_parsers → transaction_filter → merchant_normaliser → subscription detector
"""

import re
from collections import defaultdict

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# ─────────────────────────────────────────────
# Cleaning helpers
# ─────────────────────────────────────────────

# Leading bank-generated prefixes — longest first to avoid partial matches
_PREFIXES = [
    'POS PURCHASE ',
    'POS ',
    'ABM WITHDRAWAL ',
    'ABM ',
    'ITB-CUSTOMER TRAN DR ',
    'THIRD PARTY TRANSFER ',
    'FUNDS TRANSFER FROM ',
]

# Secondary: "TRANSFER TO/FROM" that survives after the outer prefix is stripped
_TRANSFER_DIR_RE  = re.compile(r'^TRANSFER\s+(?:TO|FROM)\s+', re.IGNORECASE)

# Trailing comma-separated reference codes, e.g. ", SAJAJMKN, FT26033GG3NF"
_REF_CODE_RE      = re.compile(r',\s*[A-Z0-9]{5,}(?:,\s*[A-Z0-9]{5,})*\s*$')

# Trailing location suffix — handles KINGSTON, TDKINGSTON, LKINGSTON, DKINGSTON,
# HIKINGSTON, KGN, etc., optionally followed by a number and "JM"
_LOCATION_RE      = re.compile(
    r'\s+[A-Z]*(?:KINGSTON|KGN)\s*\d*\s*(?:JM)?\s*$',
    re.IGNORECASE,
)

# Trailing standalone " JM" / " JA" (country/island codes)
_JX_RE            = re.compile(r'\s+J[AM]\s*$', re.IGNORECASE)

# Trailing number runs: account numbers, phone refs, location codes
# Allows digits mixed with dashes (e.g. "650-2530000").
# Matches one-or-more `<whitespace><digit><digit-or-dash>*` groups at end.
_TRAILING_DIGS_RE = re.compile(r'(\s+\d[\d\-]*)+\s*$')

# Leading digit reference token — e.g. "218690/0241" before merchant name
_LEADING_DIGS_RE  = re.compile(r'^\d[\d/]*\s+')

# Trailing filler conjunction
_TRAILING_AND_RE  = re.compile(r'\s+AND\s*$', re.IGNORECASE)

# Trailing noise characters (asterisks, ampersands, hyphens, spaces)
_TRAILING_NOISE_RE = re.compile(r'[\s*&\-]+$')


def clean_merchant(description: str) -> str:
    """
    Strip bank-generated prefixes and location/reference noise from a
    transaction description, returning an uppercase canonical merchant token.

    Examples
    --------
    "POS HI-LO BASIX KINGSTON"            → "HI-LO BASIX"
    "POS PURCHASE HI-LO BASIX KINGSTON 7 JM" → "HI-LO BASIX"
    "ITB-CUSTOMER TRAN DR Transfer to JADA BROWNE 3641" → "JADA BROWNE"
    """
    s = description.upper().strip()

    # 1. Strip known bank-generated prefix
    for prefix in _PREFIXES:
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
            break

    # 2. Strip secondary "TRANSFER TO/FROM" direction word
    s = _TRANSFER_DIR_RE.sub('', s).strip()

    # 3. Strip trailing comma-separated reference codes
    s = _REF_CODE_RE.sub('', s).strip()

    # 4. Strip trailing digit/phone-number runs FIRST so that location codes
    #    that trail reference numbers (e.g. "KGN 7 JM 0436750 5434308460203450")
    #    are exposed at string-end before the location regex fires.
    s = _TRAILING_DIGS_RE.sub('', s).strip()

    # 5. Strip trailing location suffix (KINGSTON variants + number + JM)
    s = _LOCATION_RE.sub('', s).strip()

    # 6. Strip trailing standalone country code ( JM / JA )
    s = _JX_RE.sub('', s).strip()

    # 7. Strip leading digit reference token (ABM ref numbers)
    s = _LEADING_DIGS_RE.sub('', s).strip()

    # 8. Strip trailing filler conjunction "AND"
    s = _TRAILING_AND_RE.sub('', s).strip()

    # 9. Strip trailing noise characters
    s = _TRAILING_NOISE_RE.sub('', s).strip()

    # 10. Collapse internal whitespace
    s = re.sub(r'\s+', ' ', s).strip()

    return s


# ─────────────────────────────────────────────
# TF-IDF similarity
# ─────────────────────────────────────────────

def tfidf_similarity(a: str, b: str) -> float:
    """
    Compute cosine similarity between two merchant name strings using
    character-level n-gram TF-IDF (n=2,3). Returns a float in [0, 1].

    Returns 0.0 for empty inputs or strings that share no n-gram vocabulary.
    """
    if not a or not b:
        return 0.0
    # Need at least 2 characters to form a bigram
    if len(a) < 2 or len(b) < 2:
        return 1.0 if a == b else 0.0

    vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 3))
    try:
        matrix = vec.fit_transform([a, b])
        return float(cosine_similarity(matrix[0:1], matrix[1:2])[0, 0])
    except ValueError:
        return 0.0


# ─────────────────────────────────────────────
# Clustering
# ─────────────────────────────────────────────

def _union_find_clusters(names: list[str], sim_matrix: np.ndarray,
                         threshold: float) -> dict[str, list[str]]:
    """Group name indices whose pairwise similarity >= threshold via Union-Find."""
    n = len(names)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for i in range(n):
        for j in range(i + 1, n):
            if sim_matrix[i, j] >= threshold:
                union(i, j)

    clusters: dict[int, list[str]] = defaultdict(list)
    for i, name in enumerate(names):
        clusters[find(i)].append(name)
    return clusters


def cluster_merchants(transactions: list[dict],
                      threshold: float = 0.65) -> list[dict]:
    """
    Add a ``merchant_id`` field to each transaction dict.

    Transactions whose cleaned descriptions are similar enough (cosine
    similarity >= threshold on char 2-3-gram TF-IDF) share the same
    merchant_id. The canonical id is the most-frequent cleaned name in the
    cluster, giving stable, human-readable identifiers.

    Parameters
    ----------
    transactions : list of normalised transaction dicts from pdf_parsers /
                   bank_email_parsers. The input list is NOT mutated.
    threshold    : similarity cutoff; default 0.65 works well for Jamaican
                   bank statement truncations.

    Returns
    -------
    New list of dicts, each with an added ``merchant_id`` key.
    """
    if not transactions:
        return []

    result = [dict(t) for t in transactions]

    # Clean every description
    for t in result:
        t['_cleaned'] = clean_merchant(t.get('description', ''))

    # Unique non-empty cleaned names
    name_counts: dict[str, int] = defaultdict(int)
    for t in result:
        if t['_cleaned']:
            name_counts[t['_cleaned']] += 1

    names = list(name_counts.keys())

    # Assign placeholder for empty-string results (generic account transfers)
    for t in result:
        if not t['_cleaned']:
            t['merchant_id'] = '(TRANSFER)'

    if not names:
        for t in result:
            t.pop('_cleaned', None)
        return result

    # Build TF-IDF matrix over all unique cleaned names
    vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 3))
    tfidf_matrix = vec.fit_transform(names)
    sim_matrix = cosine_similarity(tfidf_matrix)

    # Cluster via Union-Find
    clusters = _union_find_clusters(names, sim_matrix, threshold)

    # Canonical name = most frequent member of each cluster
    name_to_id: dict[str, str] = {}
    for group in clusters.values():
        canonical = max(group, key=lambda n: name_counts[n])
        for n in group:
            name_to_id[n] = canonical

    # Stamp merchant_id onto every transaction
    for t in result:
        cleaned = t['_cleaned']
        if cleaned:
            t['merchant_id'] = name_to_id.get(cleaned, cleaned)
        t.pop('_cleaned', None)

    return result


# ─────────────────────────────────────────────
# Smoke test
# ─────────────────────────────────────────────

if __name__ == '__main__':
    from pdf_parsers import parse_ncb_pdf, parse_scotiabank_pdf
    from transaction_filter import filter_transactions

    NCB_PATH    = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
                   r'Vocational Training\Downloads\ACCT2015\NcbStatement.pdf')
    SCOTIA_PATH = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
                   r'Vocational Training\Downloads\ACCT2015\ScotiaStatement.pdf')

    for bank, path, parser in [
        ('NCB',        NCB_PATH,    parse_ncb_pdf),
        ('Scotiabank', SCOTIA_PATH, parse_scotiabank_pdf),
    ]:
        raw      = parser(path)
        filtered = filter_transactions(raw)
        clustered = cluster_merchants(filtered)

        print(f'\n{"=" * 65}')
        n_clusters = len({t["merchant_id"] for t in clustered})
        print(f'  {bank}  |  {len(raw)} raw -> {len(filtered)} filtered -> '
              f'{n_clusters} merchant clusters')
        print(f'{"=" * 65}')

        # Group by merchant_id for display
        by_merchant: dict[str, list] = defaultdict(list)
        for t in clustered:
            by_merchant[t['merchant_id']].append(t)

        for mid, txns in sorted(by_merchant.items()):
            total = sum(t['amount'] for t in txns)
            print(f'  {mid:<45}  {len(txns):2d} txn(s)  {total:>12,.2f}')
