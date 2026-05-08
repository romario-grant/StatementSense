"""
Tests for currency_normaliser.py  (Feature 7.4)

All tests that involve fetch_boj_rate mock the function so no network
access is required.  The fallback path (157.50) is the primary path
tested throughout.
"""

import pytest
from unittest.mock import patch, MagicMock
import urllib.error

import currency_normaliser as cn
from currency_normaliser import (
    FALLBACK_RATE,
    LOOKBACK_DAYS,
    fetch_boj_rate,
    get_rate_with_fallback,
    normalise_amount,
    normalise_transactions,
    _BOJ_RATE_CACHE,
    _extract_usd_rate,
)
from pdf_parsers import parse_ncb_pdf, parse_scotiabank_pdf
from transaction_filter import filter_transactions
from merchant_normaliser import cluster_merchants
from trial_classifier import (build_synthetic_dataset, train_classifier,
                               classify_all_merchants)

NCB_PATH    = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
               r'Vocational Training\Downloads\ACCT2015\NcbStatement.pdf')
SCOTIA_PATH = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
               r'Vocational Training\Downloads\ACCT2015\ScotiaStatement.pdf')

# Fixed rate used throughout tests — mirrors the hardcoded fallback
FIXED_RATE = FALLBACK_RATE  # 157.50


# ─────────────────────────────────────────────
# normalise_amount — unit tests
# ─────────────────────────────────────────────

class TestNormaliseAmount:

    def test_basic_conversion(self):
        # J$1575.00 / 157.50 = $10.0000 USD
        assert normalise_amount(1575.00, 157.50) == pytest.approx(10.0, abs=1e-4)

    def test_preserves_negative_sign_for_debits(self):
        result = normalise_amount(-1575.00, 157.50)
        assert result == pytest.approx(-10.0, abs=1e-4)

    def test_preserves_positive_sign_for_credits(self):
        result = normalise_amount(35000.00, 157.50)
        assert result > 0

    def test_zero_amount(self):
        assert normalise_amount(0.0, 157.50) == pytest.approx(0.0)

    def test_rounded_to_4_decimal_places(self):
        result = normalise_amount(100.0, 157.50)
        # 100 / 157.50 = 0.634920634… → rounds to 0.6349
        assert result == pytest.approx(0.6349, abs=1e-4)
        # Confirm it's actually 4dp
        assert result == round(100.0 / 157.50, 4)

    def test_large_jmd_amount(self):
        # J$50,000 at 157.50 ≈ USD 317.46
        result = normalise_amount(50000.0, 157.50)
        assert result == pytest.approx(317.4603, abs=1e-3)

    def test_different_rates_give_different_results(self):
        r1 = normalise_amount(-1500.0, 155.00)
        r2 = normalise_amount(-1500.0, 160.00)
        assert r1 != r2


# ─────────────────────────────────────────────
# _extract_usd_rate — unit tests (shape coverage)
# ─────────────────────────────────────────────

class TestExtractUSDRate:

    def test_shape_a_list_of_dicts(self):
        data = [
            {'currency': 'EUR', 'sell': 170.0},
            {'currency': 'USD', 'sell': 157.20, 'weighted_avg_sell': 157.35},
        ]
        assert _extract_usd_rate(data) == pytest.approx(157.35)

    def test_shape_a_falls_back_to_sell_key(self):
        data = [{'currency': 'USD', 'sell': 157.20}]
        assert _extract_usd_rate(data) == pytest.approx(157.20)

    def test_shape_b_nested_rates(self):
        data = {'date': '2026-01-13', 'rates': [{'currency': 'USD', 'sell': 158.00}]}
        assert _extract_usd_rate(data) == pytest.approx(158.00)

    def test_shape_c_flat_dict(self):
        data = {'currency': 'USD', 'date': '2026-01-13', 'rate': 157.50}
        assert _extract_usd_rate(data) == pytest.approx(157.50)

    def test_no_usd_entry_returns_none(self):
        data = [{'currency': 'GBP', 'sell': 200.0}]
        assert _extract_usd_rate(data) is None

    def test_empty_list_returns_none(self):
        assert _extract_usd_rate([]) is None

    def test_unrecognised_shape_returns_none(self):
        assert _extract_usd_rate('not a dict or list') is None


# ─────────────────────────────────────────────
# fetch_boj_rate — mock-based tests
# ─────────────────────────────────────────────

class TestFetchBojRate:

    def setup_method(self):
        """Clear module-level cache before each test."""
        _BOJ_RATE_CACHE.clear()

    def test_returns_none_on_http_404(self):
        with patch('urllib.request.urlopen',
                   side_effect=urllib.error.HTTPError(
                       None, 404, 'Not Found', {}, None)):
            result = fetch_boj_rate('2026-01-13')
        assert result is None

    def test_returns_none_on_network_error(self):
        with patch('urllib.request.urlopen',
                   side_effect=urllib.error.URLError('Connection refused')):
            result = fetch_boj_rate('2026-01-13')
        assert result is None

    def test_returns_none_on_bad_json(self):
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b'<html>not json</html>'
        with patch('urllib.request.urlopen', return_value=mock_resp):
            result = fetch_boj_rate('2026-01-13')
        assert result is None

    def test_returns_rate_on_valid_shape_a_response(self):
        payload = b'[{"currency":"USD","weighted_avg_sell":157.35}]'
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = payload
        with patch('urllib.request.urlopen', return_value=mock_resp):
            result = fetch_boj_rate('2026-01-13')
        assert result == pytest.approx(157.35)

    def test_caches_result_after_first_call(self):
        with patch('urllib.request.urlopen',
                   side_effect=urllib.error.HTTPError(
                       None, 404, 'Not Found', {}, None)):
            fetch_boj_rate('2026-01-20')

        assert '2026-01-20' in _BOJ_RATE_CACHE
        # Second call should not hit network — patch would raise if called
        with patch('urllib.request.urlopen',
                   side_effect=AssertionError('Should not hit network twice')):
            result = fetch_boj_rate('2026-01-20')
        assert result is None  # cached None

    def test_cache_hit_returns_stored_value(self):
        _BOJ_RATE_CACHE['2026-02-01'] = 159.00
        with patch('urllib.request.urlopen',
                   side_effect=AssertionError('Should not hit network')):
            result = fetch_boj_rate('2026-02-01')
        assert result == pytest.approx(159.00)


# ─────────────────────────────────────────────
# get_rate_with_fallback — mock-based tests
# ─────────────────────────────────────────────

class TestGetRateWithFallback:

    def setup_method(self):
        _BOJ_RATE_CACHE.clear()

    def _patch_fetch(self, return_value):
        return patch.object(cn, 'fetch_boj_rate', return_value=return_value)

    def test_returns_fallback_when_api_unavailable(self):
        cache: dict = {}
        with self._patch_fetch(None):
            rate = get_rate_with_fallback('2026-01-13', cache)
        assert rate == pytest.approx(FALLBACK_RATE)

    def test_stores_fallback_in_cache(self):
        cache: dict = {}
        with self._patch_fetch(None):
            get_rate_with_fallback('2026-01-13', cache)
        assert '2026-01-13' in cache
        assert cache['2026-01-13'] == pytest.approx(FALLBACK_RATE)

    def test_uses_cached_value_without_calling_api(self):
        cache = {'2026-01-13': 159.00}
        with patch.object(cn, 'fetch_boj_rate',
                          side_effect=AssertionError('Should not call API')):
            rate = get_rate_with_fallback('2026-01-13', cache)
        assert rate == pytest.approx(159.00)

    def test_returns_live_rate_when_api_available(self):
        cache: dict = {}
        with self._patch_fetch(158.75):
            rate = get_rate_with_fallback('2026-01-13', cache)
        assert rate == pytest.approx(158.75)

    def test_walkback_finds_previous_day_rate(self):
        """
        Target date returns None, but one day earlier returns a rate.
        The resolved rate should be that earlier rate.
        """
        cache: dict = {}
        call_log: list[str] = []

        def selective_fetch(d: str) -> float | None:
            call_log.append(d)
            if d == '2026-01-12':   # one day before target
                return 158.00
            return None

        with patch.object(cn, 'fetch_boj_rate', side_effect=selective_fetch):
            rate = get_rate_with_fallback('2026-01-13', cache)

        assert rate == pytest.approx(158.00)
        assert '2026-01-13' in call_log   # tried target date
        assert '2026-01-12' in call_log   # tried one day back

    def test_walkback_limited_to_lookback_days(self):
        """Fallback kicks in after LOOKBACK_DAYS attempts."""
        cache: dict = {}
        call_count = 0

        def always_none(d: str) -> None:
            nonlocal call_count
            call_count += 1
            return None

        with patch.object(cn, 'fetch_boj_rate', side_effect=always_none):
            rate = get_rate_with_fallback('2026-01-13', cache)

        # Should have tried target + LOOKBACK_DAYS prior dates
        assert call_count == 1 + LOOKBACK_DAYS
        assert rate == pytest.approx(FALLBACK_RATE)


# ─────────────────────────────────────────────
# normalise_transactions — unit tests
# ─────────────────────────────────────────────

def _make_txn(date_str: str, amount: float, currency: str = 'JMD',
              merchant: str = 'TEST') -> dict:
    return {
        'bank': 'TEST', 'date': date_str, 'description': 'TEST',
        'amount': amount, 'balance': None,
        'currency': currency, 'source_file': 'test.pdf',
        'merchant_id': merchant,
    }


class TestNormaliseTransactions:

    def _fixed_cache(self, dates: list[str]) -> dict[str, float]:
        return {d: FIXED_RATE for d in dates}

    def test_adds_amount_usd_to_every_row(self):
        txns = [_make_txn('2026-01-13', -1500.0),
                _make_txn('2026-01-20', -3000.0)]
        cache = self._fixed_cache(['2026-01-13', '2026-01-20'])
        result = normalise_transactions(txns, cache=cache)
        assert all('amount_usd' in t for t in result)

    def test_correct_usd_amount_for_jmd(self):
        txns = [_make_txn('2026-01-13', -1575.00)]
        cache = {'2026-01-13': 157.50}
        result = normalise_transactions(txns, cache=cache)
        assert result[0]['amount_usd'] == pytest.approx(-10.0, abs=1e-4)

    def test_skips_conversion_for_usd_transactions(self):
        txns = [_make_txn('2026-01-13', -15.99, currency='USD')]
        result = normalise_transactions(txns, cache={})
        assert result[0]['amount_usd'] == pytest.approx(-15.99, abs=1e-4)

    def test_negative_amounts_stay_negative(self):
        txns = [_make_txn('2026-01-13', -3500.0)]
        cache = {'2026-01-13': FIXED_RATE}
        result = normalise_transactions(txns, cache=cache)
        assert result[0]['amount_usd'] < 0

    def test_positive_amounts_stay_positive(self):
        txns = [_make_txn('2026-01-13', 35000.0)]
        cache = {'2026-01-13': FIXED_RATE}
        result = normalise_transactions(txns, cache=cache)
        assert result[0]['amount_usd'] > 0

    def test_input_not_mutated(self):
        txns = [_make_txn('2026-01-13', -1500.0)]
        original = [dict(t) for t in txns]
        cache = {'2026-01-13': FIXED_RATE}
        normalise_transactions(txns, cache=cache)
        assert txns == original

    def test_returns_new_list(self):
        txns = [_make_txn('2026-01-13', -1500.0)]
        cache = {'2026-01-13': FIXED_RATE}
        result = normalise_transactions(txns, cache=cache)
        assert result is not txns

    def test_same_date_uses_same_rate(self):
        """Two transactions on the same date must have amounts in the same ratio."""
        txns = [_make_txn('2026-01-13', -1500.0),
                _make_txn('2026-01-13', -3000.0)]
        cache = {'2026-01-13': FIXED_RATE}
        result = normalise_transactions(txns, cache=cache)
        ratio = result[1]['amount_usd'] / result[0]['amount_usd']
        assert ratio == pytest.approx(2.0, abs=1e-6)

    def test_creates_cache_if_none_provided(self):
        """Should not raise when no cache is passed; uses fallback."""
        txns = [_make_txn('2026-01-13', -1500.0)]
        with patch.object(cn, 'fetch_boj_rate', return_value=None):
            result = normalise_transactions(txns)   # no cache kwarg
        assert 'amount_usd' in result[0]

    def test_empty_input(self):
        assert normalise_transactions([]) == []

    def test_cache_populated_for_new_dates(self):
        """Passing an empty cache should have it populated after the call."""
        txns = [_make_txn('2026-01-13', -1500.0),
                _make_txn('2026-01-20', -2000.0)]
        cache: dict = {}
        with patch.object(cn, 'fetch_boj_rate', return_value=None):
            normalise_transactions(txns, cache=cache)
        assert '2026-01-13' in cache
        assert '2026-01-20' in cache
        assert cache['2026-01-13'] == FALLBACK_RATE

    def test_pre_populated_cache_overrides_api(self):
        """A pre-populated cache value should be used directly."""
        txns = [_make_txn('2026-01-13', -1575.0)]
        cache = {'2026-01-13': 157.50}
        with patch.object(cn, 'fetch_boj_rate',
                          side_effect=AssertionError('Should not call API')):
            result = normalise_transactions(txns, cache=cache)
        assert result[0]['amount_usd'] == pytest.approx(-10.0, abs=1e-4)


# ─────────────────────────────────────────────
# Integration tests — full pipeline
# ─────────────────────────────────────────────

@pytest.fixture(scope='module')
def full_pipeline():
    X, y = build_synthetic_dataset()
    model = train_classifier(X, y)
    results = {}
    cache: dict = {}

    for bank, path, parser in [
        ('NCB',        NCB_PATH,    parse_ncb_pdf),
        ('Scotiabank', SCOTIA_PATH, parse_scotiabank_pdf),
    ]:
        raw       = parser(path)
        filtered  = filter_transactions(raw)
        clustered = cluster_merchants(filtered)
        scored    = classify_all_merchants(clustered, model)
        # Use fallback rate for all dates (no network)
        with patch.object(cn, 'fetch_boj_rate', return_value=None):
            normed = normalise_transactions(scored, cache=cache)
        results[bank] = normed

    return results, cache


class TestNCBIntegration:

    def test_all_rows_have_amount_usd(self, full_pipeline):
        rows, _ = full_pipeline
        assert all('amount_usd' in t for t in rows['NCB'])

    def test_usd_amounts_have_correct_sign(self, full_pipeline):
        rows, _ = full_pipeline
        for t in rows['NCB']:
            assert (t['amount_usd'] >= 0) == (t['amount'] >= 0)

    def test_usd_amounts_smaller_magnitude_than_jmd(self, full_pipeline):
        """JMD/USD > 1 so |USD| must be less than |JMD|."""
        rows, _ = full_pipeline
        for t in rows['NCB']:
            assert abs(t['amount_usd']) < abs(t['amount'])

    def test_print_ncb_usd_amounts(self, full_pipeline, capsys):
        rows, cache = full_pipeline
        print('\n--- NCB  JMD → USD (fallback rate) ---')
        for t in rows['NCB']:
            rate = cache.get(t['date'], FALLBACK_RATE)
            print(f"  {t['date']}  {t['amount']:>12,.2f} JMD  "
                  f"{t['amount_usd']:>10.4f} USD  @{rate:.2f}  "
                  f"{t['merchant_id'][:30]}")
        assert 'NCB  JMD' in capsys.readouterr().out


class TestScotiabankIntegration:

    def test_all_rows_have_amount_usd(self, full_pipeline):
        rows, _ = full_pipeline
        assert all('amount_usd' in t for t in rows['Scotiabank'])

    def test_usd_amounts_have_correct_sign(self, full_pipeline):
        rows, _ = full_pipeline
        for t in rows['Scotiabank']:
            assert (t['amount_usd'] >= 0) == (t['amount'] >= 0)

    def test_usd_amounts_smaller_magnitude_than_jmd(self, full_pipeline):
        rows, _ = full_pipeline
        for t in rows['Scotiabank']:
            assert abs(t['amount_usd']) < abs(t['amount'])

    def test_shared_rate_cache_across_banks(self, full_pipeline):
        """Both banks processed with the same cache — dates from both should appear."""
        _, cache = full_pipeline
        # NCB dates (January 2026) and Scotia dates (February 2026) should both be in cache
        ncb_dates = {t['date'] for t in full_pipeline[0]['NCB']}
        sc_dates  = {t['date'] for t in full_pipeline[0]['Scotiabank']}
        for d in ncb_dates | sc_dates:
            assert d in cache, f'{d} missing from shared rate cache'

    def test_print_scotiabank_usd_amounts(self, full_pipeline, capsys):
        rows, cache = full_pipeline
        print('\n--- Scotiabank  JMD → USD (fallback rate) ---')
        for t in rows['Scotiabank']:
            rate = cache.get(t['date'], FALLBACK_RATE)
            print(f"  {t['date']}  {t['amount']:>12,.2f} JMD  "
                  f"{t['amount_usd']:>10.4f} USD  @{rate:.2f}  "
                  f"{t['merchant_id'][:30]}")
        assert 'Scotiabank  JMD' in capsys.readouterr().out
