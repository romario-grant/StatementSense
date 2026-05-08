"""
Statement Sense — Currency Normaliser  (Feature 7.4)
Reverse-converts JMD transaction amounts to USD so that international
subscription charges (Netflix, Spotify, Adobe …) are stable across months
even as the JMD/USD exchange rate drifts.

BOJ API status (verified 2026-04-03)
─────────────────────────────────────
The endpoint https://boj.org.jm/api/public/key-rates returns HTTP 404.
The Bank of Jamaica publishes daily FX rates on their website via WordPress
DataTables loaded by AJAX — there is no public JSON REST API as of early 2026.

Raw probe result:
    GET https://boj.org.jm/api/public/key-rates  →  HTTP 404 Not Found

`fetch_boj_rate` is written to handle this gracefully: any HTTP or parse
error returns None, and `get_rate_with_fallback` then applies a 7-day
look-back before settling on the hardcoded FALLBACK_RATE of 157.50 JMD/USD
(approximate weighted-average sell rate, early 2026).

This means fetch_boj_rate will always return None with the current BOJ
infrastructure.  When/if BOJ publishes a real API the parser is ready.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import date, timedelta

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

#: Approximate JMD-per-USD weighted-average sell rate, early 2026
FALLBACK_RATE: float = 157.50

#: How many days to walk backwards when the target date has no BOJ data
#: (covers weekends, public holidays, and API gaps)
LOOKBACK_DAYS: int = 7

#: Timeout for BOJ HTTP requests (seconds)
_HTTP_TIMEOUT: int = 8

#: BOJ public API endpoint (currently returns HTTP 404 — see module docstring)
_BOJ_API_URL: str = 'https://boj.org.jm/api/public/key-rates'

#: Module-level cache shared by fetch_boj_rate across the process lifetime
_BOJ_RATE_CACHE: dict[str, float | None] = {}


# ─────────────────────────────────────────────
# BOJ API fetch
# ─────────────────────────────────────────────

def fetch_boj_rate(date_str: str) -> float | None:
    """
    Attempt to fetch the USD/JMD weighted-average sell rate from the BOJ API
    for the given date (``YYYY-MM-DD``).

    Results are stored in the module-level ``_BOJ_RATE_CACHE`` dict keyed by
    ``date_str`` so repeated calls for the same date never hit the network.

    Returns
    -------
    float   — USD/JMD rate (JMD per 1 USD) if successfully retrieved
    None    — if the API is unavailable, returns 404, or the response cannot
              be parsed (the current situation as of early 2026)

    Expected JSON shapes (handled, for future-proofing):
    ┌──────────────────────────────────────────────────────────────────────┐
    │ Shape A — list of currency objects                                   │
    │  [{"currency":"USD","date":"…","weighted_avg_sell":157.20}, …]       │
    │                                                                      │
    │ Shape B — dict with nested rates                                     │
    │  {"date":"…","rates":[{"currency":"USD","sell":157.20}, …]}          │
    │                                                                      │
    │ Shape C — flat single-day dict                                       │
    │  {"currency":"USD","date":"…","rate":157.20}                         │
    └──────────────────────────────────────────────────────────────────────┘
    """
    if date_str in _BOJ_RATE_CACHE:
        return _BOJ_RATE_CACHE[date_str]

    rate: float | None = None
    try:
        url = f'{_BOJ_API_URL}?date={date_str}'
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'StatementSense/1.0', 'Accept': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            body = resp.read().decode('utf-8', errors='replace')

        data = json.loads(body)

        rate = _extract_usd_rate(data)

    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            TypeError, KeyError, ValueError):
        # API unavailable (404, timeout, malformed JSON …) — degrade silently
        rate = None

    _BOJ_RATE_CACHE[date_str] = rate
    return rate


def _extract_usd_rate(data: object) -> float | None:
    """
    Try several plausible JSON shapes to extract a JMD-per-USD rate.
    Returns the first numeric value found, or None.
    """
    candidate_keys = ('weighted_avg_sell', 'weighted_avg', 'sell', 'rate',
                      'weighted_average_sell', 'average_sell', 'avg_sell')

    # Shape A: list of dicts
    if isinstance(data, list):
        for entry in data:
            if not isinstance(entry, dict):
                continue
            ccy = str(entry.get('currency', entry.get('currency_code', ''))).upper()
            if ccy == 'USD':
                for k in candidate_keys:
                    if k in entry:
                        return float(entry[k])

    # Shape B: dict with 'rates' list
    if isinstance(data, dict):
        rates = data.get('rates', data.get('data', []))
        if isinstance(rates, list):
            result = _extract_usd_rate(rates)
            if result is not None:
                return result

        # Shape C: flat dict for a single currency
        ccy = str(data.get('currency', data.get('currency_code', ''))).upper()
        if ccy == 'USD':
            for k in candidate_keys:
                if k in data:
                    return float(data[k])

    return None


# ─────────────────────────────────────────────
# Rate resolution with fallback
# ─────────────────────────────────────────────

def get_rate_with_fallback(date_str: str,
                           cache: dict[str, float]) -> float:
    """
    Resolve the JMD/USD rate for ``date_str``, storing the result in ``cache``.

    Resolution order
    ----------------
    1. ``cache`` hit  — return immediately (avoids redundant API calls).
    2. ``fetch_boj_rate(date_str)``  — live BOJ data.
    3. Walk backwards up to ``LOOKBACK_DAYS`` days — covers weekends/holidays.
    4. ``FALLBACK_RATE`` (157.50)  — when all else fails.

    The resolved rate is stored in ``cache[date_str]`` regardless of which
    path produced it.

    Parameters
    ----------
    date_str : ISO date string, ``'YYYY-MM-DD'``
    cache    : caller-supplied dict; may be pre-populated or empty
    """
    if date_str in cache:
        return cache[date_str]

    # Try today's date first
    rate = fetch_boj_rate(date_str)
    if rate is not None:
        cache[date_str] = rate
        return rate

    # Walk back up to LOOKBACK_DAYS
    target = date.fromisoformat(date_str)
    for delta in range(1, LOOKBACK_DAYS + 1):
        candidate = (target - timedelta(days=delta)).isoformat()
        rate = fetch_boj_rate(candidate)
        if rate is not None:
            cache[date_str] = rate
            return rate

    # Hard fallback
    cache[date_str] = FALLBACK_RATE
    return FALLBACK_RATE


# ─────────────────────────────────────────────
# Amount conversion
# ─────────────────────────────────────────────

def normalise_amount(amount_jmd: float, rate: float) -> float:
    """
    Convert a JMD amount to USD.

    Parameters
    ----------
    amount_jmd : signed amount (negative = debit, positive = credit)
    rate       : JMD per 1 USD (e.g. 157.50)

    Returns
    -------
    float rounded to 4 decimal places; sign is preserved.
    """
    return round(amount_jmd / rate, 4)


# ─────────────────────────────────────────────
# Transaction-level normalisation
# ─────────────────────────────────────────────

def normalise_transactions(transactions: list[dict],
                           cache: dict[str, float] | None = None) -> list[dict]:
    """
    Add an ``amount_usd`` field to every transaction dict.

    Currency handling
    -----------------
    - ``currency == 'JMD'``  → convert using ``get_rate_with_fallback``.
    - ``currency == 'USD'``  → set ``amount_usd = amount`` directly.
    - Anything else          → treat as JMD (conservative default).

    Parameters
    ----------
    transactions : list of transaction dicts (each needs ``date``, ``amount``,
                   ``currency`` keys)
    cache        : optional rate cache dict; created internally if None.
                   Pass in a pre-populated dict to override rates (useful
                   for tests and smoke-test reproducibility).

    Returns a new list of dicts; ``transactions`` is not mutated.
    """
    if cache is None:
        cache = {}

    result = [dict(t) for t in transactions]

    for t in result:
        if t.get('currency', 'JMD').upper() == 'USD':
            t['amount_usd'] = round(float(t['amount']), 4)
        else:
            rate = get_rate_with_fallback(t['date'], cache)
            t['amount_usd'] = normalise_amount(float(t['amount']), rate)

    return result


# ─────────────────────────────────────────────
# Smoke test
# ─────────────────────────────────────────────

if __name__ == '__main__':
    from pdf_parsers import parse_ncb_pdf, parse_scotiabank_pdf
    from transaction_filter import filter_transactions
    from merchant_normaliser import cluster_merchants
    from trial_classifier import (build_synthetic_dataset, train_classifier,
                                   classify_all_merchants)

    NCB_PATH    = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
                   r'Vocational Training\Downloads\ACCT2015\NcbStatement.pdf')
    SCOTIA_PATH = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
                   r'Vocational Training\Downloads\ACCT2015\ScotiaStatement.pdf')

    X, y = build_synthetic_dataset()
    model = train_classifier(X, y)

    # Shared rate cache — populated as transactions are processed
    rate_cache: dict[str, float] = {}

    for bank, path, parser in [
        ('NCB',        NCB_PATH,    parse_ncb_pdf),
        ('Scotiabank', SCOTIA_PATH, parse_scotiabank_pdf),
    ]:
        raw       = parser(path)
        filtered  = filter_transactions(raw)
        clustered = cluster_merchants(filtered)
        scored    = classify_all_merchants(clustered, model)
        normed    = normalise_transactions(scored, cache=rate_cache)

        print(f'\n{"=" * 72}')
        print(f'  {bank}  ({len(normed)} transactions)')
        print(f'{"=" * 72}')
        print(f'  {"Date":<12} {"JMD Amount":>14}  {"USD Amount":>10}  '
              f'{"Rate":>8}  Merchant')
        print(f'  {"-"*12} {"-"*14}  {"-"*10}  {"-"*8}  {"-"*30}')
        for t in normed:
            rate_used = rate_cache.get(t['date'], FALLBACK_RATE)
            print(f'  {t["date"]:<12} {t["amount"]:>14,.2f}  '
                  f'{t["amount_usd"]:>10.4f}  {rate_used:>8.2f}  '
                  f'{t["merchant_id"][:35]}')

    print(f'\nRate cache ({len(rate_cache)} dates):')
    for d, r in sorted(rate_cache.items()):
        src = 'BOJ' if d in _BOJ_RATE_CACHE and _BOJ_RATE_CACHE[d] is not None \
              else 'FALLBACK'
        print(f'  {d}  {r:.2f}  [{src}]')
