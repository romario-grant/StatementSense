"""
Tests for subscription_scorer.py  (Feature 7.2 — core model)

Unit tests use hand-crafted transaction lists with controlled amounts and intervals.
Integration tests run the full pipeline against both real PDFs and the synthetic dataset.
"""

import os
import pytest
from datetime import date, timedelta

from subscription_scorer import (
    BILLING_CYCLES,
    CONFIRMED_THRESHOLD,
    POSSIBLE_THRESHOLD,
    WEIGHTS,
    compute_consistency,
    compute_periodicity,
    compute_stability,
    score_all_merchants,
    score_merchant,
)

NCB_PATH    = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
               r'Vocational Training\Downloads\ACCT2015\NcbStatement.pdf')
SCOTIA_PATH = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
               r'Vocational Training\Downloads\ACCT2015\ScotiaStatement.pdf')
SYNTH_PATH  = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
               r'Vocational Training\Documents\Capstone'
               r'\StatementSense_Synthetic_5000_Group21 (1).xlsx')


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_txns(dates: list[str],
               amounts: list[float] | None = None,
               merchant_id: str = 'TEST') -> list[dict]:
    if amounts is None:
        amounts = [-1000.0] * len(dates)
    return [
        {
            'date': d, 'amount': a, 'merchant_id': merchant_id,
            'description': 'TEST', 'bank': 'NCB',
            'currency': 'JMD', 'balance': None, 'source_file': 'test.pdf',
        }
        for d, a in zip(dates, amounts)
    ]


def _dates_with_gaps(start: str, gaps: list[int]) -> list[str]:
    """Generate date strings from a start date and a list of day gaps."""
    d = date.fromisoformat(start)
    result = [d.isoformat()]
    for g in gaps:
        d += timedelta(days=g)
        result.append(d.isoformat())
    return result


# ─────────────────────────────────────────────
# compute_stability
# ─────────────────────────────────────────────

class TestComputeStability:

    def test_uniform_amounts_returns_1(self):
        assert compute_stability([1000.0, 1000.0, 1000.0]) == pytest.approx(1.0)

    def test_single_amount_returns_1(self):
        assert compute_stability([500.0]) == pytest.approx(1.0)

    def test_empty_list_returns_1(self):
        # Single-or-fewer: spec says return 1.0 for single charge
        assert compute_stability([]) == pytest.approx(1.0)

    def test_zero_mean_returns_0(self):
        assert compute_stability([0.0, 0.0, 0.0]) == pytest.approx(0.0)

    def test_high_variance_returns_low_stability(self):
        # [100, 5000] → large CV → stability close to 0
        result = compute_stability([100.0, 5000.0])
        assert result < 0.2

    def test_never_below_zero(self):
        # Extreme variance; max(0, 1-CV) must not go negative
        result = compute_stability([1.0, 100000.0])
        assert result >= 0.0

    def test_stability_decreases_with_variance(self):
        low_var  = compute_stability([900.0, 1000.0, 1100.0])
        high_var = compute_stability([100.0, 1000.0, 5000.0])
        assert low_var > high_var

    def test_nearly_uniform_is_close_to_1(self):
        result = compute_stability([999.0, 1000.0, 1001.0])
        assert result > 0.99


# ─────────────────────────────────────────────
# compute_periodicity
# ─────────────────────────────────────────────

class TestComputePeriodicity:

    def test_exact_30_day_returns_1(self):
        assert compute_periodicity([30, 30, 30]) == pytest.approx(1.0)

    def test_28_day_within_tolerance_of_30(self):
        # |28 - 30| = 2 ≤ 3 → should match
        assert compute_periodicity([28, 28, 28]) == pytest.approx(1.0)

    def test_33_day_within_tolerance_of_30(self):
        assert compute_periodicity([33, 33, 33]) == pytest.approx(1.0)

    def test_exact_7_day_returns_1(self):
        assert compute_periodicity([7, 7, 7, 7]) == pytest.approx(1.0)

    def test_exact_14_day_returns_1(self):
        assert compute_periodicity([14, 14]) == pytest.approx(1.0)

    def test_exact_365_day_returns_1(self):
        assert compute_periodicity([365]) == pytest.approx(1.0)

    def test_irregular_20_day_returns_0(self):
        # 20 days: |20-7|=13, |20-14|=6, |20-30|=10 — none ≤ 3
        assert compute_periodicity([20, 20, 20]) == pytest.approx(0.0)

    def test_empty_intervals_returns_0(self):
        assert compute_periodicity([]) == pytest.approx(0.0)

    def test_median_used_not_mean(self):
        # Intervals: [30, 30, 120] → median = 30 → 1.0 even though mean ≈ 60
        assert compute_periodicity([30, 30, 120]) == pytest.approx(1.0)

    def test_custom_tolerance(self):
        # |10 - 7| = 3, tolerance_days=2 → no match
        assert compute_periodicity([10], tolerance_days=2) == pytest.approx(0.0)
        # same but tolerance_days=3 → match
        assert compute_periodicity([10], tolerance_days=3) == pytest.approx(1.0)


# ─────────────────────────────────────────────
# compute_consistency
# ─────────────────────────────────────────────

class TestComputeConsistency:

    def test_exact_one_per_month(self):
        assert compute_consistency(9, 9) == pytest.approx(1.0)

    def test_partial_history(self):
        # 6 charges in 9 months → 6/9 ≈ 0.6667
        assert compute_consistency(6, 9) == pytest.approx(6 / 9, abs=1e-4)

    def test_capped_at_1(self):
        # 12 charges in 9 months → min(1, 12/9) = 1.0
        assert compute_consistency(12, 9) == pytest.approx(1.0)

    def test_zero_months_returns_0(self):
        assert compute_consistency(5, 0) == pytest.approx(0.0)

    def test_single_charge_single_month(self):
        assert compute_consistency(1, 1) == pytest.approx(1.0)

    def test_single_charge_nine_months(self):
        assert compute_consistency(1, 9) == pytest.approx(1 / 9, abs=1e-4)


# ─────────────────────────────────────────────
# score_merchant
# ─────────────────────────────────────────────

SCORE_KEYS = {
    'stability', 'periodicity', 'consistency',
    'subscription_score', 'subscription_flag', 'possible_flag',
    'n_charges', 'median_interval_days',
}


class TestScoreMerchant:

    def test_returns_all_required_keys(self):
        txns   = _make_txns(['2025-01-01', '2025-01-31'])
        result = score_merchant(txns, n_months=1)
        assert SCORE_KEYS.issubset(result.keys())

    def test_clear_subscription_scores_high(self):
        # 4 uniform monthly charges → stability=1, periodicity=1, consistency=1
        dates  = _dates_with_gaps('2025-01-01', [30, 30, 30])
        txns   = _make_txns(dates, amounts=[-1499.0] * 4)
        result = score_merchant(txns, n_months=4)
        assert result['subscription_score'] >= CONFIRMED_THRESHOLD

    def test_irregular_one_off_scores_below_possible(self):
        # Single charge over 9 months → S ≈ 0.378 < 0.40
        txns   = _make_txns(['2025-01-15'])
        result = score_merchant(txns, n_months=9)
        assert result['subscription_score'] < POSSIBLE_THRESHOLD

    def test_subscription_flag_true_at_threshold(self):
        dates  = _dates_with_gaps('2025-01-01', [30, 30, 30])
        txns   = _make_txns(dates, amounts=[-1499.0] * 4)
        result = score_merchant(txns, n_months=4)
        assert result['subscription_flag'] is True

    def test_subscription_flag_false_below_threshold(self):
        txns   = _make_txns(['2025-01-15'])
        result = score_merchant(txns, n_months=9)
        assert result['subscription_flag'] is False

    def test_possible_flag_true_in_middle_range(self):
        # 2 same-amount charges, 20-day interval (no cycle match), n_months=9
        # S = 0.35*1.0 + 0.40*0.0 + 0.25*(2/9) ≈ 0.406 → possible
        dates  = _dates_with_gaps('2025-01-01', [20])
        txns   = _make_txns(dates, amounts=[-1000.0, -1000.0])
        result = score_merchant(txns, n_months=9)
        assert result['possible_flag'] is True
        assert not result['subscription_flag']

    def test_possible_flag_false_when_confirmed(self):
        dates  = _dates_with_gaps('2025-01-01', [30, 30, 30])
        txns   = _make_txns(dates, amounts=[-1499.0] * 4)
        result = score_merchant(txns, n_months=4)
        assert result['possible_flag'] is False
        assert result['subscription_flag'] is True

    def test_n_charges_correct(self):
        txns   = _make_txns(['2025-01-01', '2025-02-01', '2025-03-03'])
        result = score_merchant(txns, n_months=3)
        assert result['n_charges'] == 3

    def test_median_interval_correct(self):
        dates  = _dates_with_gaps('2025-01-01', [30, 30, 30])
        txns   = _make_txns(dates)
        result = score_merchant(txns, n_months=4)
        assert result['median_interval_days'] == 30

    def test_median_interval_zero_for_single_charge(self):
        txns   = _make_txns(['2025-01-01'])
        result = score_merchant(txns, n_months=1)
        assert result['median_interval_days'] == 0

    def test_score_in_0_to_1(self):
        txns   = _make_txns(['2025-01-01', '2025-02-01'])
        result = score_merchant(txns, n_months=2)
        assert 0.0 <= result['subscription_score'] <= 1.0

    def test_weights_sum_to_1(self):
        assert sum(WEIGHTS.values()) == pytest.approx(1.0)


# ─────────────────────────────────────────────
# score_all_merchants
# ─────────────────────────────────────────────

_STAMP_KEYS = {'subscription_score', 'subscription_flag',
               'possible_flag', 'stability', 'periodicity', 'consistency'}


class TestScoreAllMerchants:

    def _two_merchant_txns(self) -> list[dict]:
        """A confirmed subscriber (SUB_A) and a one-off (IRREGULAR)."""
        dates_a = _dates_with_gaps('2025-01-01', [30, 30, 30])
        return (
            _make_txns(dates_a, amounts=[-1499.0] * 4, merchant_id='SUB_A')
            + _make_txns(['2025-02-15'], merchant_id='IRREGULAR')
        )

    def test_stamps_fields_on_every_row(self):
        txns   = self._two_merchant_txns()
        result = score_all_merchants(txns, n_months=4)
        for t in result:
            assert _STAMP_KEYS.issubset(t.keys())

    def test_does_not_mutate_input(self):
        txns         = self._two_merchant_txns()
        original_key = set(txns[0].keys())
        score_all_merchants(txns, n_months=4)
        assert set(txns[0].keys()) == original_key

    def test_returns_new_list(self):
        txns = self._two_merchant_txns()
        assert score_all_merchants(txns, n_months=4) is not txns

    def test_same_merchant_id_gets_same_score(self):
        txns   = self._two_merchant_txns()
        result = score_all_merchants(txns, n_months=4)
        sub_a  = [t for t in result if t['merchant_id'] == 'SUB_A']
        assert len({t['subscription_score'] for t in sub_a}) == 1

    def test_confirmed_subscription_flagged(self):
        txns   = self._two_merchant_txns()
        result = score_all_merchants(txns, n_months=4)
        sub_a  = next(t for t in result if t['merchant_id'] == 'SUB_A')
        assert sub_a['subscription_flag'] is True

    def test_irregular_not_confirmed(self):
        txns   = self._two_merchant_txns()
        result = score_all_merchants(txns, n_months=9)
        irreg  = next(t for t in result if t['merchant_id'] == 'IRREGULAR')
        assert irreg['subscription_flag'] is False

    def test_empty_input_returns_empty(self):
        assert score_all_merchants([]) == []


# ─────────────────────────────────────────────
# Integration tests — real PDFs
# ─────────────────────────────────────────────

@pytest.fixture(scope='module')
def full_pipeline_scored():
    for path in (NCB_PATH, SCOTIA_PATH):
        if not os.path.exists(path):
            pytest.skip(f'PDF not found: {path}')

    from pdf_parsers import parse_ncb_pdf, parse_scotiabank_pdf
    from transaction_filter import filter_transactions
    from merchant_normaliser import cluster_merchants
    from trial_classifier import (build_synthetic_dataset, train_classifier,
                                   classify_all_merchants)
    from currency_normaliser import normalise_transactions
    from renewal_predictor import predict_all_merchants

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
        scored_tc = classify_all_merchants(clustered, model)
        normed    = normalise_transactions(scored_tc)
        predicted = predict_all_merchants(normed, reference_date='2026-04-25')
        results[bank] = score_all_merchants(predicted, n_months=1)

    return results


class TestIntegrationPDFs:

    def test_all_rows_have_score_fields_ncb(self, full_pipeline_scored):
        for t in full_pipeline_scored['NCB']:
            assert 'subscription_score' in t
            assert 'subscription_flag' in t

    def test_all_rows_have_score_fields_scotiabank(self, full_pipeline_scored):
        for t in full_pipeline_scored['Scotiabank']:
            assert 'subscription_score' in t

    def test_scores_in_0_to_1(self, full_pipeline_scored):
        for bank_rows in full_pipeline_scored.values():
            for t in bank_rows:
                assert 0.0 <= t['subscription_score'] <= 1.0

    def test_print_scored_merchants(self, full_pipeline_scored, capsys):
        all_rows: list[dict] = []
        for bank, bank_rows in full_pipeline_scored.items():
            seen: set[str] = set()
            for t in bank_rows:
                mid = t['merchant_id']
                if mid not in seen:
                    seen.add(mid)
                    all_rows.append({**t, '_bank': bank})

        all_rows.sort(key=lambda t: t['subscription_score'], reverse=True)

        W = 36
        print(f'\n{"=" * 80}')
        print(f'  Subscription Scorer — Real PDFs  (n_months=1)')
        print(f'{"=" * 80}')
        print(f'  {"Merchant":<{W}}  {"Score":>6}  {"Stab":>5}  '
              f'{"Per":>5}  {"Con":>5}  Flag')
        print(f'  {"-"*W}  {"-"*6}  {"-"*5}  {"-"*5}  {"-"*5}  {"-"*10}')
        for r in all_rows:
            flag = '[CONFIRMED]' if r['subscription_flag'] else \
                   '[POSSIBLE] ' if r['possible_flag']      else '           '
            print(f'  {r["merchant_id"]:<{W}}  {r["subscription_score"]:>6.4f}  '
                  f'{r["stability"]:>5.2f}  {r["periodicity"]:>5.2f}  '
                  f'{r["consistency"]:>5.2f}  {flag}')
        print(f'{"=" * 80}')

        assert 'Subscription Scorer' in capsys.readouterr().out


# ─────────────────────────────────────────────
# Integration tests — synthetic dataset
# ─────────────────────────────────────────────

@pytest.fixture(scope='module')
def scored_synthetic():
    if not os.path.exists(SYNTH_PATH):
        pytest.skip(f'Synthetic dataset not found: {SYNTH_PATH}')

    from evaluation import load_synthetic_dataset
    txns = load_synthetic_dataset(SYNTH_PATH)
    return score_all_merchants(txns, n_months=9)


class TestIntegrationSynthetic:

    def test_all_rows_have_score_fields(self, scored_synthetic):
        for t in scored_synthetic:
            assert 'subscription_score' in t

    def test_scores_in_0_to_1(self, scored_synthetic):
        for t in scored_synthetic:
            assert 0.0 <= t['subscription_score'] <= 1.0

    def test_some_merchants_confirmed(self, scored_synthetic):
        confirmed = [t for t in scored_synthetic if t['subscription_flag']]
        assert len(confirmed) > 0, 'Expected at least one confirmed subscription'

    def test_print_scored_synthetic_merchants(self, scored_synthetic, capsys):
        seen: set[str] = set()
        rows: list[dict] = []
        for t in scored_synthetic:
            mid = t['merchant_id']
            if mid not in seen:
                seen.add(mid)
                rows.append(t)
        rows.sort(key=lambda t: t['subscription_score'], reverse=True)

        W = 30
        print(f'\n{"=" * 82}')
        print(f'  Subscription Scorer — Synthetic Dataset  (n_months=9, '
              f'{len(rows)} merchants)')
        print(f'{"=" * 82}')
        print(f'  {"Merchant":<{W}}  {"Score":>6}  {"Stab":>5}  {"Per":>5}  '
              f'{"Con":>5}  {"Label":<15}  Flag')
        print(f'  {"-"*W}  {"-"*6}  {"-"*5}  {"-"*5}  {"-"*5}  {"-"*15}  {"-"*10}')
        for r in rows:
            flag  = '[CONFIRMED]' if r['subscription_flag'] else \
                    '[POSSIBLE] ' if r['possible_flag']      else '           '
            label = r.get('label', '?')[:15]
            print(f'  {r["merchant_id"]:<{W}}  {r["subscription_score"]:>6.4f}  '
                  f'{r["stability"]:>5.2f}  {r["periodicity"]:>5.2f}  '
                  f'{r["consistency"]:>5.2f}  {label:<15}  {flag}')
        print(f'{"=" * 82}')

        assert 'Synthetic Dataset' in capsys.readouterr().out
