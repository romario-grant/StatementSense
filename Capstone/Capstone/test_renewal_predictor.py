"""
Tests for renewal_predictor.py  (Feature 7.3 — renewal half)

Unit tests use hand-crafted transaction lists with known dates and intervals.
The integration test runs the full pipeline against both real PDFs and prints
a renewal dashboard sorted by days_until.
"""

import os
import pytest
from datetime import date, timedelta

from renewal_predictor import (
    ALERT_LEAD_DAYS,
    COLD_START_PRIOR_DAYS,
    HIGH_CONFIDENCE_MIN_INTERVALS,
    compute_intervals,
    predict_all_merchants,
    predict_next_charge,
)

NCB_PATH    = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
               r'Vocational Training\Downloads\ACCT2015\NcbStatement.pdf')
SCOTIA_PATH = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
               r'Vocational Training\Downloads\ACCT2015\ScotiaStatement.pdf')

REFERENCE_DATE = '2026-04-25'

#: Required keys in every predict_next_charge result
REQUIRED_KEYS = {
    'last_charge_date',
    'median_interval_days',
    'next_charge_date',
    'confidence_band_days',
    'confidence',
    'days_until',
    'alert_date',
    'is_cold_start',
}


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_txns(dates: list[str],
               amounts: list[float] | None = None,
               merchant_id: str = 'TEST') -> list[dict]:
    """Minimal transaction dicts for a single merchant."""
    if amounts is None:
        amounts = [-1000.0] * len(dates)
    return [
        {
            'date': d, 'amount': a, 'merchant_id': merchant_id,
            'description': 'TEST CHARGE', 'bank': 'NCB',
            'currency': 'JMD', 'balance': None, 'source_file': 'test.pdf',
        }
        for d, a in zip(dates, amounts)
    ]


# ─────────────────────────────────────────────
# compute_intervals
# ─────────────────────────────────────────────

class TestComputeIntervals:

    def test_correct_day_gaps(self):
        # Jan 1 → Jan 31 = 30 days; Jan 31 → Mar 2 = 30 days; Mar 2 → Apr 1 = 30 days
        txns = _make_txns(['2025-01-01', '2025-01-31', '2025-03-02', '2025-04-01'])
        assert compute_intervals(txns) == [30, 30, 30]

    def test_unsorted_input_produces_correct_gaps(self):
        # Supply dates out of order — function must sort first
        txns = _make_txns(['2025-02-01', '2025-01-01', '2025-03-03'])
        gaps = compute_intervals(txns)
        assert gaps == [31, 30]

    def test_single_charge_returns_empty_list(self):
        assert compute_intervals(_make_txns(['2025-01-01'])) == []

    def test_empty_list_returns_empty_list(self):
        assert compute_intervals([]) == []

    def test_two_charges_returns_one_gap(self):
        txns = _make_txns(['2025-01-01', '2025-02-01'])
        assert compute_intervals(txns) == [31]

    def test_irregular_gaps(self):
        txns = _make_txns(['2025-01-01', '2025-01-08', '2025-01-22'])
        assert compute_intervals(txns) == [7, 14]


# ─────────────────────────────────────────────
# predict_next_charge — key presence
# ─────────────────────────────────────────────

class TestPredictNextChargeKeys:

    def test_returns_all_required_keys_single_charge(self):
        result = predict_next_charge(_make_txns(['2025-01-01']),
                                     reference_date='2025-01-15')
        assert REQUIRED_KEYS.issubset(result.keys())

    def test_returns_all_required_keys_multiple_charges(self):
        txns = _make_txns(['2025-01-01', '2025-01-31',
                           '2025-03-02', '2025-04-01'])
        result = predict_next_charge(txns, reference_date='2025-04-10')
        assert REQUIRED_KEYS.issubset(result.keys())


# ─────────────────────────────────────────────
# predict_next_charge — cold start
# ─────────────────────────────────────────────

class TestColdStart:

    def test_cold_start_uses_30_day_prior(self):
        result = predict_next_charge(_make_txns(['2025-01-01']),
                                     reference_date='2025-01-15')
        assert result['median_interval_days'] == COLD_START_PRIOR_DAYS

    def test_cold_start_confidence_is_low(self):
        result = predict_next_charge(_make_txns(['2025-01-01']),
                                     reference_date='2025-01-15')
        assert result['confidence'] == 'low'

    def test_cold_start_flag_true(self):
        result = predict_next_charge(_make_txns(['2025-01-01']),
                                     reference_date='2025-01-15')
        assert result['is_cold_start'] is True

    def test_cold_start_next_charge_is_30_days_after_last(self):
        result = predict_next_charge(_make_txns(['2025-01-01']),
                                     reference_date='2025-01-15')
        expected = (date(2025, 1, 1) + timedelta(days=30)).isoformat()
        assert result['next_charge_date'] == expected


# ─────────────────────────────────────────────
# predict_next_charge — confidence tiers
# ─────────────────────────────────────────────

class TestConfidenceTiers:

    def test_one_interval_gives_medium_confidence(self):
        result = predict_next_charge(_make_txns(['2025-01-01', '2025-02-01']),
                                     reference_date='2025-02-15')
        assert result['confidence'] == 'medium'

    def test_two_intervals_gives_medium_confidence(self):
        result = predict_next_charge(
            _make_txns(['2025-01-01', '2025-02-01', '2025-03-03']),
            reference_date='2025-03-10',
        )
        assert result['confidence'] == 'medium'

    def test_three_intervals_gives_high_confidence(self):
        txns = _make_txns(['2025-01-01', '2025-01-31',
                           '2025-03-02', '2025-04-01'])
        result = predict_next_charge(txns, reference_date='2025-04-10')
        assert result['confidence'] == 'high'

    def test_non_cold_start_flag_false_for_multiple_charges(self):
        txns = _make_txns(['2025-01-01', '2025-01-31',
                           '2025-03-02', '2025-04-01'])
        result = predict_next_charge(txns, reference_date='2025-04-10')
        assert result['is_cold_start'] is False

    def test_high_confidence_min_intervals_constant_is_3(self):
        assert HIGH_CONFIDENCE_MIN_INTERVALS == 3


# ─────────────────────────────────────────────
# predict_next_charge — median interval
# ─────────────────────────────────────────────

class TestMedianInterval:

    def test_median_correct_for_uniform_intervals(self):
        # Intervals: 30, 30, 30
        txns = _make_txns(['2025-01-01', '2025-01-31',
                           '2025-03-02', '2025-04-01'])
        result = predict_next_charge(txns, reference_date='2025-04-10')
        assert result['median_interval_days'] == 30

    def test_median_correct_for_skewed_intervals(self):
        # Intervals: 7, 7, 60 → median = 7
        txns = _make_txns(['2025-01-01', '2025-01-08',
                           '2025-01-15', '2025-03-16'])
        result = predict_next_charge(txns, reference_date='2025-03-20')
        assert result['median_interval_days'] == 7

    def test_next_charge_date_correct(self):
        # last charge = 2025-04-01, median = 30 → next = 2025-05-01
        txns = _make_txns(['2025-01-01', '2025-01-31',
                           '2025-03-02', '2025-04-01'])
        result = predict_next_charge(txns, reference_date='2025-04-10')
        assert result['next_charge_date'] == '2025-05-01'

    def test_last_charge_date_correct(self):
        txns = _make_txns(['2025-01-01', '2025-02-01', '2025-03-03',
                           '2025-04-02'])
        result = predict_next_charge(txns, reference_date='2025-04-10')
        assert result['last_charge_date'] == '2025-04-02'


# ─────────────────────────────────────────────
# predict_next_charge — confidence band
# ─────────────────────────────────────────────

class TestConfidenceBand:

    def test_band_zero_for_medium_confidence(self):
        result = predict_next_charge(_make_txns(['2025-01-01', '2025-02-01']),
                                     reference_date='2025-02-15')
        assert result['confidence_band_days'] == 0

    def test_band_zero_for_exactly_3_intervals(self):
        # 4 transactions → 3 intervals → high confidence but < 4 intervals for IQR
        txns = _make_txns(['2025-01-01', '2025-01-31',
                           '2025-03-02', '2025-04-01'])
        result = predict_next_charge(txns, reference_date='2025-04-10')
        assert result['confidence'] == 'high'
        assert result['confidence_band_days'] == 0

    def test_band_correct_for_4_plus_intervals(self):
        # 6 transactions → 5 intervals: [20, 28, 30, 32, 40]
        # np.percentile([20,28,30,32,40], [25,75]) → [28, 32]  (exact integer indices)
        # IQR = 4  →  band = round(1.5 * 4) = 6
        txns = _make_txns([
            '2025-01-01',   # base
            '2025-01-21',   # +20
            '2025-02-18',   # +28  (10 remaining Jan + 18 Feb)
            '2025-03-20',   # +30  (10 remaining Feb + 20 Mar; Feb 2025 = 28 days)
            '2025-04-21',   # +32  (11 remaining Mar + 21 Apr)
            '2025-05-31',   # +40  (9 remaining Apr + 31 May)
        ])
        result = predict_next_charge(txns, reference_date='2025-06-05')
        assert result['confidence_band_days'] == 6

    def test_band_zero_for_cold_start(self):
        result = predict_next_charge(_make_txns(['2025-01-01']),
                                     reference_date='2025-01-15')
        assert result['confidence_band_days'] == 0


# ─────────────────────────────────────────────
# predict_next_charge — days_until and alert_date
# ─────────────────────────────────────────────

class TestDaysUntilAndAlert:

    def test_days_until_correct(self):
        # next_charge = 2025-05-01, reference = 2025-04-10
        txns = _make_txns(['2025-01-01', '2025-01-31',
                           '2025-03-02', '2025-04-01'])
        result = predict_next_charge(txns, reference_date='2025-04-10')
        expected = (date(2025, 5, 1) - date(2025, 4, 10)).days  # 21
        assert result['days_until'] == expected

    def test_days_until_negative_when_overdue(self):
        # last charge 2025-01-01 + 30 days = 2025-01-31; reference = 2025-03-01
        result = predict_next_charge(_make_txns(['2025-01-01']),
                                     reference_date='2025-03-01')
        assert result['days_until'] < 0

    def test_alert_date_is_3_days_before_next_charge(self):
        txns = _make_txns(['2025-01-01', '2025-01-31',
                           '2025-03-02', '2025-04-01'])
        result = predict_next_charge(txns, reference_date='2025-04-10')
        next_d  = date.fromisoformat(result['next_charge_date'])
        alert_d = date.fromisoformat(result['alert_date'])
        assert (next_d - alert_d).days == ALERT_LEAD_DAYS

    def test_alert_lead_days_constant_is_3(self):
        assert ALERT_LEAD_DAYS == 3


# ─────────────────────────────────────────────
# predict_all_merchants
# ─────────────────────────────────────────────

class TestPredictAllMerchants:

    _STAMP_KEYS = {
        'last_charge_date', 'next_charge_date', 'days_until', 'confidence',
        'confidence_band_days', 'alert_date', 'is_cold_start',
    }

    def _multi_merchant_txns(self) -> list[dict]:
        return (
            _make_txns(['2025-01-01', '2025-01-31',
                        '2025-03-02', '2025-04-01'], merchant_id='SUB_A')
            + _make_txns(['2025-02-15'], merchant_id='SUB_B')
        )

    def test_stamps_fields_on_every_row(self):
        txns   = self._multi_merchant_txns()
        result = predict_all_merchants(txns, reference_date=REFERENCE_DATE)
        for t in result:
            assert self._STAMP_KEYS.issubset(t.keys())

    def test_does_not_mutate_input(self):
        txns         = self._multi_merchant_txns()
        original_key = set(txns[0].keys())
        predict_all_merchants(txns, reference_date=REFERENCE_DATE)
        assert set(txns[0].keys()) == original_key

    def test_returns_new_list(self):
        txns = self._multi_merchant_txns()
        assert predict_all_merchants(txns, reference_date=REFERENCE_DATE) is not txns

    def test_same_merchant_id_gets_same_prediction(self):
        # All four SUB_A rows must share the same next_charge_date
        txns   = self._multi_merchant_txns()
        result = predict_all_merchants(txns, reference_date=REFERENCE_DATE)
        sub_a  = [t for t in result if t['merchant_id'] == 'SUB_A']
        assert len({t['next_charge_date'] for t in sub_a}) == 1

    def test_different_merchants_can_have_different_predictions(self):
        txns   = self._multi_merchant_txns()
        result = predict_all_merchants(txns, reference_date=REFERENCE_DATE)
        a_next = next(t['next_charge_date'] for t in result if t['merchant_id'] == 'SUB_A')
        b_next = next(t['next_charge_date'] for t in result if t['merchant_id'] == 'SUB_B')
        # SUB_A has 4 charges; SUB_B has 1 — predictions differ
        assert a_next != b_next

    def test_cold_start_merchant_gets_cold_start_flag(self):
        txns   = self._multi_merchant_txns()
        result = predict_all_merchants(txns, reference_date=REFERENCE_DATE)
        sub_b  = next(t for t in result if t['merchant_id'] == 'SUB_B')
        assert sub_b['is_cold_start'] is True

    def test_empty_input_returns_empty_list(self):
        assert predict_all_merchants([]) == []


# ─────────────────────────────────────────────
# Integration test — full pipeline
# ─────────────────────────────────────────────

@pytest.fixture(scope='module')
def full_pipeline_renewal():
    """Run the complete pipeline on both real PDFs and return predicted rows."""
    pytest.importorskip('pdfplumber')  # skip gracefully if library missing

    for path in (NCB_PATH, SCOTIA_PATH):
        if not os.path.exists(path):
            pytest.skip(f'PDF not found: {path}')

    from pdf_parsers import parse_ncb_pdf, parse_scotiabank_pdf
    from transaction_filter import filter_transactions
    from merchant_normaliser import cluster_merchants
    from trial_classifier import (build_synthetic_dataset, train_classifier,
                                   classify_all_merchants)
    from currency_normaliser import normalise_transactions

    X, y  = build_synthetic_dataset()
    model = train_classifier(X, y)

    results: dict[str, list[dict]] = {}
    for bank, path, parser in [
        ('NCB',        NCB_PATH,    parse_ncb_pdf),
        ('Scotiabank', SCOTIA_PATH, parse_scotiabank_pdf),
    ]:
        raw       = parser(path)
        filtered  = filter_transactions(raw)
        clustered = cluster_merchants(filtered)
        scored    = classify_all_merchants(clustered, model)
        normed    = normalise_transactions(scored)
        results[bank] = predict_all_merchants(normed, reference_date=REFERENCE_DATE)

    return results


class TestIntegrationNCB:

    def test_all_rows_have_renewal_fields(self, full_pipeline_renewal):
        for t in full_pipeline_renewal['NCB']:
            assert 'next_charge_date' in t
            assert 'days_until' in t
            assert 'confidence' in t

    def test_confidence_values_are_valid(self, full_pipeline_renewal):
        valid = {'low', 'medium', 'high'}
        for t in full_pipeline_renewal['NCB']:
            assert t['confidence'] in valid

    def test_alert_date_always_3_days_before_next_charge(self, full_pipeline_renewal):
        for t in full_pipeline_renewal['NCB']:
            next_d  = date.fromisoformat(t['next_charge_date'])
            alert_d = date.fromisoformat(t['alert_date'])
            assert (next_d - alert_d).days == ALERT_LEAD_DAYS


class TestIntegrationScotiabank:

    def test_all_rows_have_renewal_fields(self, full_pipeline_renewal):
        for t in full_pipeline_renewal['Scotiabank']:
            assert 'next_charge_date' in t
            assert 'days_until' in t

    def test_hi_lo_basix_high_confidence(self, full_pipeline_renewal):
        """HI-LO BASIX has 4 charges — should reach 'high' confidence."""
        rows = [t for t in full_pipeline_renewal['Scotiabank']
                if 'HI-LO' in t['merchant_id'].upper()
                or 'HILO' in t['merchant_id'].upper()]
        if not rows:
            pytest.skip('HI-LO BASIX not found in Scotiabank data')
        assert rows[0]['confidence'] == 'high'

    def test_jada_browne_high_confidence(self, full_pipeline_renewal):
        """JADA BROWNE has 7 charges — should reach 'high' confidence."""
        rows = [t for t in full_pipeline_renewal['Scotiabank']
                if 'JADA' in t['merchant_id'].upper()]
        if not rows:
            pytest.skip('JADA BROWNE not found in Scotiabank data')
        assert rows[0]['confidence'] == 'high'

    def test_print_renewal_dashboard(self, full_pipeline_renewal, capsys):
        """Print renewal predictions for both banks sorted by days_until."""
        all_rows: list[dict] = []
        for bank_rows in full_pipeline_renewal.values():
            seen: set[str] = set()
            for t in bank_rows:
                mid = t['merchant_id']
                if mid not in seen:
                    seen.add(mid)
                    all_rows.append(t)

        all_rows.sort(key=lambda t: t['days_until'])

        W_MID, W_DATE = 36, 12
        print(f'\n{"=" * 92}')
        print(f'  RENEWAL DASHBOARD  (reference: {REFERENCE_DATE})')
        print(f'{"=" * 92}')
        print(f'  {"Merchant":<{W_MID}}  {"Last Charge":<{W_DATE}}  '
              f'{"Next Charge":<{W_DATE}}  {"Days":>6}  {"Conf":<8}  {"±Band":>6}')
        print(f'  {"-"*W_MID}  {"-"*W_DATE}  {"-"*W_DATE}  {"-"*6}  {"-"*8}  {"-"*6}')
        for t in all_rows:
            band_str = f'±{t["confidence_band_days"]}d' if t['confidence_band_days'] else '—'
            overdue  = '  [OVERDUE]' if t['days_until'] < 0 else ''
            print(f'  {t["merchant_id"]:<{W_MID}}  {t["last_charge_date"]:<{W_DATE}}  '
                  f'{t["next_charge_date"]:<{W_DATE}}  {t["days_until"]:>6}  '
                  f'{t["confidence"]:<8}  {band_str:>6}{overdue}')
        print(f'{"=" * 92}')
        print(f'  {len(all_rows)} merchants  |  '
              f'{sum(1 for t in all_rows if t["confidence"] == "high")} high-conf  |  '
              f'{sum(1 for t in all_rows if t["is_cold_start"])} cold-start')

        assert 'RENEWAL DASHBOARD' in capsys.readouterr().out
