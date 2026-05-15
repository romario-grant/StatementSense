"""
Currency normalization helpers for subscription and renewal analysis.
The engine keeps statement amounts in the original currency and adds USD
equivalents when needed for cross-currency comparisons. Live USD/JMD lookup is
best-effort; callers always receive a deterministic fallback rate when the
provider is unavailable.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

# Constants

#: Approximate JMD-per-USD weighted-average sell rate, early 2026
FALLBACK_RATE: float = 157.50

#: Timeout for exchange-rate HTTP requests (seconds)
_HTTP_TIMEOUT: int = 8

#: No-key exchange-rate endpoint. Returns latest rates relative to USD.
_LIVE_RATE_URL: str = 'https://open.er-api.com/v6/latest/USD'

#: Module-level cache shared by live-rate lookups across the process lifetime
_LIVE_RATE_CACHE: dict[str, float | None] = {}


# Live exchange-rate fetch

def fetch_live_usd_jmd_rate() -> float | None:
    """Fetch the most recent USD-to-JMD exchange rate from the public exchange-rate provider. Successful results are cached for the lifetime of the process. ``None`` is returned when the provider is unreachable, signalling to callers that ``FALLBACK_RATE`` should be used."""
    cache_key = 'USD_JMD_LATEST'
    if cache_key in _LIVE_RATE_CACHE:
        return _LIVE_RATE_CACHE[cache_key]

    rate: float | None = None
    try:
        req = urllib.request.Request(
            _LIVE_RATE_URL,
            headers={'User-Agent': 'StatementSense/1.0', 'Accept': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            body = resp.read().decode('utf-8', errors='replace')

        data = json.loads(body)

        rates = data.get('rates', {}) if isinstance(data, dict) else {}
        if isinstance(rates, dict) and rates.get('JMD'):
            rate = float(rates['JMD'])

    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            TypeError, KeyError, ValueError):
        # Degrade silently when the provider is unreachable, returns a non-2xx response, or returns malformed JSON.
        rate = None

    _LIVE_RATE_CACHE[cache_key] = rate
    return rate


def _extract_usd_rate(data: object) -> float | None:
    """Extract a JMD-per-USD rate from a JSON response that may use one of several known shapes. The first numeric value located is returned; ``None`` is returned when no recognised shape contains a USD rate."""
    candidate_keys = ('weighted_avg_sell', 'weighted_avg', 'sell', 'rate',
                      'weighted_average_sell', 'average_sell', 'avg_sell')

    # Response is a list of currency records.
    if isinstance(data, list):
        for entry in data:
            if not isinstance(entry, dict):
                continue
            ccy = str(entry.get('currency', entry.get('currency_code', ''))).upper()
            if ccy == 'USD':
                for k in candidate_keys:
                    if k in entry:
                        return float(entry[k])

    # Response wraps a list of rates under a top-level key.
    if isinstance(data, dict):
        rates = data.get('rates', data.get('data', []))
        if isinstance(rates, list):
            result = _extract_usd_rate(rates)
            if result is not None:
                return result

        # Response is a flat dictionary describing a single currency.
        ccy = str(data.get('currency', data.get('currency_code', ''))).upper()
        if ccy == 'USD':
            for k in candidate_keys:
                if k in data:
                    return float(data[k])

    return None


# Rate resolution with fallback

def get_rate_with_fallback(date_str: str,
                           cache: dict[str, float]) -> float:
    """Resolve the JMD-per-USD rate for ``date_str`` and store it in ``cache``. Resolution checks the cache first, then the live provider, and finally returns ``FALLBACK_RATE`` so the caller always receives a deterministic numeric value."""
    if date_str in cache:
        return cache[date_str]

    # The live provider returns only the latest rate, so the supplied date acts purely as a caller-side cache key.
    rate = fetch_live_usd_jmd_rate()
    if rate is not None:
        cache[date_str] = rate
        return rate

    cache[date_str] = FALLBACK_RATE
    return FALLBACK_RATE


# Amount conversion

def normalise_amount(amount_jmd: float, rate: float) -> float:
    """Convert a signed JMD amount to USD using ``rate`` (JMD per one USD). The result is rounded to four decimal places and the sign of ``amount_jmd`` is preserved."""
    return round(amount_jmd / rate, 4)


# Transaction-level normalisation

def normalise_transactions(transactions: list[dict],
                           cache: dict[str, float] | None = None) -> list[dict]:
    """Annotate every transaction with an ``amount_usd`` field. JMD amounts are converted using ``get_rate_with_fallback``; USD amounts are copied directly. Any other currency code is treated as JMD as a conservative default. The input list is not mutated; a new annotated list is returned. A caller-supplied ``cache`` may be used to override or share resolved rates across calls."""
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

